import sys
import time
import json
import threading
from collections import deque
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QGroupBox, 
                             QFormLayout, QSpinBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
import pyqtgraph as pg

# --- THƯ VIỆN PHẦN CỨNG & AI ---
from pymodbus.client import ModbusSerialClient
import paho.mqtt.client as mqtt
import onnxruntime as ort
import numpy as np

try:
    from ina219 import INA219 # Thư viện đọc cảm biến dòng/áp I2C
    INA219_AVAILABLE = True
except ImportError:
    INA219_AVAILABLE = False

# --- CẤU HÌNH ĐƯỜNG DẪN YOCTO ---
MODEL_PATH = "/usr/share/hmi-app/model.onnx"
MQTT_BROKER = "192.168.1.100" # Đổi thành IP broker của nhà máy hoặc cloud
MQTT_PORT = 1883
PLC_PORT = "/dev/ttyUSB0"

# Cấu hình địa chỉ Modbus (Tùy thuộc vào thiết lập module Mitsubishi FX)
# Ví dụ: D120 offset là 120, D8116 offset là 8116
ADDR_D120_SPEED = 120 
ADDR_D8116_CMD = 8116 

# ==========================================
# CỬA SỔ ĐỒ THỊ THỜI GIAN THỰC
# ==========================================
class GraphWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Giám sát Đồ thị Thời gian thực")
        self.resize(1024, 600) # Chuẩn kích thước màn hình Raspberry Pi 7 inch
        self.setStyleSheet("background-color: #1e1e1e; color: #ffffff;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        pg.setConfigOption('background', '#1e1e1e')
        pg.setConfigOption('foreground', '#dcdcdc')
        self.graph_widget = pg.GraphicsLayoutWidget()
        layout.addWidget(self.graph_widget)
        
        self.plot_v = self.graph_widget.addPlot(title="<span style='color: #f1c40f; font-size: 13pt;'>Điện áp (V)</span>")
        self.plot_i = self.graph_widget.addPlot(title="<span style='color: #00bcd4; font-size: 13pt;'>Dòng điện (A)</span>")
        self.graph_widget.nextRow()
        self.plot_speed = self.graph_widget.addPlot(title="<span style='color: #e74c3c; font-size: 13pt;'>Tốc độ thực tế (D120)</span>", colspan=2)
        
        for p in [self.plot_v, self.plot_i, self.plot_speed]:
            p.showGrid(x=True, y=True, alpha=0.3)
            
        self.curve_v = self.plot_v.plot(pen=pg.mkPen('#f1c40f', width=2))
        self.curve_i = self.plot_i.plot(pen=pg.mkPen('#00bcd4', width=2))
        self.curve_speed = self.plot_speed.plot(pen=pg.mkPen('#e74c3c', width=2))
        
        self.max_points = 150
        self.data_v = deque([0]*self.max_points, maxlen=self.max_points)
        self.data_i = deque([0]*self.max_points, maxlen=self.max_points)
        self.data_speed = deque([0]*self.max_points, maxlen=self.max_points)

    def update_data(self, data):
        self.data_v.append(data['voltage'])
        self.data_i.append(data['current'])
        self.data_speed.append(data['speed'])
        
        self.curve_v.setData(self.data_v)
        self.curve_i.setData(self.data_i)
        self.curve_speed.setData(self.data_speed)

# ==========================================
# LUỒNG NGẦM (WORKER THREAD)
# ==========================================
class HardwareWorkerThread(QThread):
    suggestion_ready = pyqtSignal(str, int) # Trả về chuỗi hiển thị và con số tốc độ
    telemetry_update = pyqtSignal(dict) 
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.is_running = True
        self.ai_counter = 0 
        
        # 1. Khởi tạo Modbus PLC
        self.plc_client = ModbusSerialClient(port=PLC_PORT, baudrate=9600, timeout=1)
        
        # 2. Khởi tạo INA219 (Giao tiếp I2C)
        if INA219_AVAILABLE:
            self.ina = INA219(shunt_ohms=0.1, address=0x40)
            self.ina.configure()
            
        # 3. Khởi tạo MQTT Client
        self.mqtt_client = mqtt.Client(client_id="RPI_HMI_01")
        try:
            self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.mqtt_client.loop_start()
        except Exception as e:
            print(f"Không thể kết nối MQTT: {e}")
            
        # 4. Khởi tạo AI Model (ONNX) và Scaler
        try:
            self.ort_session = ort.InferenceSession("/usr/share/hmi-app/model.onnx")
            
            # Đọc file scaler.json
            with open("/usr/share/hmi-app/scaler.json", "r") as f:
                self.scaler_data = json.load(f)
                
            self.ai_ready = True
        except Exception as e:
            print(f"Lỗi tải model ONNX hoặc Scaler: {e}")
            self.ai_ready = False
            self.scaler_data = None

    def run(self):
        self.plc_client.connect()
        while self.is_running:
            current_speed, voltage, current, power = 0, 0.0, 0.0, 0.0
            
            # --- ĐỌC PLC ---
            try:
                res = self.plc_client.read_holding_registers(address=ADDR_D120_SPEED, count=1, slave=1)
                if not res.isError():
                    current_speed = res.registers[0]
            except Exception as e:
                self.status_update.emit(f"Lỗi PLC: {e}")

            # --- ĐỌC INA219 ---
            if INA219_AVAILABLE:
                try:
                    voltage = self.ina.voltage()
                    current = self.ina.current() / 1000.0 # Chuyển mA sang A
                    power = self.ina.power() / 1000.0
                except Exception:
                    pass

            # --- ĐẨY LÊN GIAO DIỆN & MQTT ---
            telemetry_data = {
                "speed": current_speed, "voltage": voltage, 
                "current": current, "power": power
            }
            self.telemetry_update.emit(telemetry_data)
            
            # Publish MQTT Telemetry
            self.mqtt_client.publish("factory/conveyor/telemetry", json.dumps(telemetry_data))

            # --- CHẠY AI TỐI ƯU HÓA (Mỗi 10 chu kỳ ~ 5s) ---
            self.ai_counter += 1
            if self.ai_counter >= 10 and self.ai_ready:
                try:
                    # 1. Chuẩn hóa dữ liệu (Scaling)
                    if self.scaler_data:
                        # Thay thế (value - mean) / scale tương ứng cho 3 biến: Áp, Dòng, Tốc độ
                        v_scaled = (voltage - self.scaler_data["mean"][0]) / self.scaler_data["scale"][0]
                        i_scaled = (current - self.scaler_data["mean"][1]) / self.scaler_data["scale"][1]
                        s_scaled = (current_speed - self.scaler_data["mean"][2]) / self.scaler_data["scale"][2]
                        input_data = [[v_scaled, i_scaled, s_scaled]]
                    else:
                        input_data = [[voltage, current, current_speed]]
                    
                    # 2. Chuyển sang Float32 (Định dạng chuẩn của ONNX)
                    input_array = np.array(input_data, dtype=np.float32)
                    
                    # 3. Chạy Inference
                    ort_inputs = {self.ort_session.get_inputs()[0].name: input_array}
                    ort_outs = self.ort_session.run(None, ort_inputs)
                    
                    recommended_speed = int(ort_outs[0][0])
                    msg = f"Đề xuất tối ưu: Chuyển tốc độ sang {recommended_speed} để đạt hiệu suất tốt nhất."
                    self.suggestion_ready.emit(msg, recommended_speed)
                except Exception as e:
                    print(f"Lỗi AI: {e}")
                
                self.ai_counter = 0 

            time.sleep(0.5)

    def write_speed(self, raw_command):
        """Được gọi từ luồng chính khi cần ghi xuống PLC"""
        try:
            self.plc_client.write_register(address=ADDR_D8116_CMD, value=raw_command, slave=1)
            # Publish log hành động lên MQTT
            self.mqtt_client.publish("factory/conveyor/control", json.dumps({"cmd_d8116": raw_command}))
        except Exception as e:
            self.status_update.emit(f"Lỗi ghi PLC: {e}")

    def stop(self):
        self.is_running = False
        self.mqtt_client.loop_stop()
        self.plc_client.close()
        self.wait()

# ==========================================
# LUỒNG CHÍNH: GIAO DIỆN HMI
# ==========================================
class HMIMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI PLC HMI")
        # CHẾ ĐỘ KIOSK: Bỏ thanh tiêu đề và full màn hình
        self.setWindowFlags(Qt.FramelessWindowHint)
        
        self.graph_window = None 
        self.current_ai_speed = 0 # Lưu trữ tốc độ AI đề xuất
        
        self.setStyleSheet("""
            QMainWindow { background-color: #f4f6f9; }
            QGroupBox { background-color: #ffffff; border: 1px solid #dcdde1; border-radius: 8px; font-size: 14px; font-weight: bold; }
            QPushButton { border-radius: 6px; font-weight: bold; font-size: 14px; color: white; }
            QPushButton:hover { opacity: 0.9; }
            QPushButton:disabled { background-color: #bdc3c7; color: #7f8c8d; }
        """)
        
        self.setup_ui()
        
        self.hw_thread = HardwareWorkerThread()
        self.hw_thread.suggestion_ready.connect(self.display_ai_suggestion)
        self.hw_thread.telemetry_update.connect(self.update_telemetry_ui)
        self.hw_thread.status_update.connect(self.display_status)
        self.hw_thread.start()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Header (Có nút tắt app để dev dễ thoát Kiosk mode)
        header_layout = QHBoxLayout()
        title = QLabel("HỆ THỐNG ĐIỀU KHIỂN BĂNG CHUYỀN TÍCH HỢP AI")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1e272e;")
        
        btn_exit = QPushButton("✖ THOÁT")
        btn_exit.setStyleSheet("background-color: #e74c3c; padding: 10px;")
        btn_exit.setFixedWidth(100)
        btn_exit.clicked.connect(self.close)
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(btn_exit)
        main_layout.addLayout(header_layout)

        content_layout = QHBoxLayout()
        
        # --- CỘT TRÁI ---
        left_column = QVBoxLayout()
        group_telemetry = QGroupBox("Giám sát Thông số (INA219 & PLC)")
        form_layout = QFormLayout()
        
        self.lbl_speed = QLabel("0")
        self.lbl_voltage = QLabel("0.0 V")
        self.lbl_current = QLabel("0.0 A")
        self.lbl_power = QLabel("0.0 W")
        self.lbl_status = QLabel("Hệ thống sẵn sàng") # Thay thế QMessageBox
        self.lbl_status.setStyleSheet("color: #e67e22; font-weight: normal; font-size: 12px;")
        
        for lbl in [self.lbl_speed, self.lbl_voltage, self.lbl_current, self.lbl_power]:
            lbl.setStyleSheet("color: #0984e3; font-weight: bold; font-size: 16px;")
            
        form_layout.addRow("Tốc độ thực tế (D120):", self.lbl_speed)
        form_layout.addRow("Điện áp nguồn:", self.lbl_voltage)
        form_layout.addRow("Cường độ dòng điện:", self.lbl_current)
        form_layout.addRow("Công suất tiêu thụ:", self.lbl_power)
        form_layout.addRow("Trạng thái kết nối:", self.lbl_status)
        group_telemetry.setLayout(form_layout)
        
        group_manual = QGroupBox("Điều khiển Thủ công")
        manual_layout = QHBoxLayout()
        
        self.spin_speed = QSpinBox()
        self.spin_speed.setRange(0, 600)
        self.spin_speed.setStyleSheet("font-size: 15px; padding: 6px;")
        
        self.btn_manual_write = QPushButton("GHI TỐC ĐỘ")
        self.btn_manual_write.setStyleSheet("background-color: #0984e3; padding: 10px 15px;")
        self.btn_manual_write.clicked.connect(self.manual_speed_write)
        
        manual_layout.addWidget(QLabel("Tốc độ:"))
        manual_layout.addWidget(self.spin_speed)
        manual_layout.addWidget(self.btn_manual_write)
        group_manual.setLayout(manual_layout)
        
        self.btn_toggle_graph = QPushButton("📊 MỞ BIỂU ĐỒ THỜI GIAN THỰC")
        self.btn_toggle_graph.setStyleSheet("background-color: #6c5ce7; padding: 12px;")
        self.btn_toggle_graph.clicked.connect(self.toggle_graph_window)
        
        left_column.addWidget(group_telemetry)
        left_column.addWidget(group_manual)
        left_column.addWidget(self.btn_toggle_graph)
        content_layout.addLayout(left_column, stretch=1) 

        # --- CỘT PHẢI ---
        group_ai = QGroupBox("Trợ lý AI Tối ưu Hóa")
        ai_layout = QVBoxLayout()
        
        self.ai_display_label = QLabel("Đang thu thập dữ liệu...")
        self.ai_display_label.setAlignment(Qt.AlignCenter)
        self.ai_display_label.setStyleSheet("font-size: 15px; color: #d63031; background-color: #fff5f5; border: 2px dashed #fab1a0; border-radius: 6px; padding: 15px;")
        self.ai_display_label.setWordWrap(True)
        ai_layout.addWidget(self.ai_display_label)

        self.btn_apply = QPushButton("✔ ÁP DỤNG ĐỀ XUẤT AI")
        self.btn_apply.setStyleSheet("background-color: #00b894; padding: 12px;")
        self.btn_apply.clicked.connect(self.apply_ai_changes)
        self.btn_apply.setEnabled(False)

        ai_layout.addWidget(self.btn_apply)
        ai_layout.addStretch() 
        group_ai.setLayout(ai_layout)
        
        content_layout.addWidget(group_ai, stretch=1) 
        main_layout.addLayout(content_layout)

    # --- HÀM QUY ĐỔI TOÁN HỌC ---
    def calculate_raw_command(self, target_speed):
        if target_speed == 0:
            return 0
        raw_value = int(4.087 * target_speed + 1402)
        if raw_value < 2000: return 2000
        if raw_value > 4000: return 4000
        return raw_value

    def toggle_graph_window(self):
        if self.graph_window is None or not self.graph_window.isVisible():
            self.graph_window = GraphWindow()
            # Mở đồ thị dạng Fullscreen luôn
            self.graph_window.showFullScreen() 
            self.btn_toggle_graph.setText("📊 ĐÓNG BIỂU ĐỒ")
            self.btn_toggle_graph.setStyleSheet("background-color: #d63031; padding: 12px;")
        else:
            self.graph_window.close()
            self.graph_window = None
            self.btn_toggle_graph.setText("📊 MỞ BIỂU ĐỒ THỜI GIAN THỰC")
            self.btn_toggle_graph.setStyleSheet("background-color: #6c5ce7; padding: 12px;")

    def update_telemetry_ui(self, data):
        self.lbl_speed.setText(f"{data['speed']}")
        self.lbl_voltage.setText(f"{data['voltage']:.1f} V")
        self.lbl_current.setText(f"{data['current']:.2f} A")
        self.lbl_power.setText(f"{data['power']:.1f} W")
        
        if self.graph_window and self.graph_window.isVisible():
            self.graph_window.update_data(data)

    def display_status(self, msg):
        self.lbl_status.setText(msg)

    def display_ai_suggestion(self, suggestion_text, recommended_speed):
        self.ai_display_label.setText(suggestion_text)
        self.current_ai_speed = recommended_speed
        self.btn_apply.setEnabled(True)

    def manual_speed_write(self):
        target_speed = self.spin_speed.value()
        raw_command = self.calculate_raw_command(target_speed)
        self.hw_thread.write_speed(raw_command)
        self.display_status(f"Đã ghi thủ công: {target_speed} (Raw: {raw_command})")

    def apply_ai_changes(self):
        raw_command = self.calculate_raw_command(self.current_ai_speed)
        self.hw_thread.write_speed(raw_command)
        self.display_status(f"Đã áp dụng AI: {self.current_ai_speed} (Raw: {raw_command})")
        
        self.ai_display_label.setText("Đang chờ chu kỳ AI tiếp theo...")
        self.btn_apply.setEnabled(False)

    def closeEvent(self, event):
        self.hw_thread.stop()
        if self.graph_window:
            self.graph_window.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Ẩn con trỏ chuột nếu xài màn hình cảm ứng toàn thời gian
    # app.setOverrideCursor(Qt.BlankCursor) 
    window = HMIMainWindow()
    window.showFullScreen() # Chạy chế độ Kiosk toàn màn hình
    sys.exit(app.exec_())