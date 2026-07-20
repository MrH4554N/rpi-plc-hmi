import sys
import time
import json
import numpy as np
import onnxruntime as ort
from ina219 import INA219, DeviceRangeError
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QMessageBox, 
                             QGroupBox, QFormLayout, QSpinBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

from pymodbus.client import ModbusSerialClient
import paho.mqtt.client as mqtt

# ==========================================
# CẤU HÌNH ĐƯỜNG DẪN AI TRONG YOCTO
# ==========================================
MODEL_PATH = "/usr/share/hmi-app/model.onnx"
SCALER_PATH = "/usr/share/hmi-app/scaler.json"

# ==========================================
# LUỒNG NGẦM: Đọc PLC, Cảm biến & AI
# ==========================================
class AIWorkerThread(QThread):
    suggestion_ready = pyqtSignal(str)
    telemetry_update = pyqtSignal(dict)
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.is_running = True
        self.ai_counter = 0 
        
        # 1. Khởi tạo Modbus cho PLC Mitsubishi
        self.plc_client = ModbusSerialClient(
            port='/dev/ttyUSB0',  
            baudrate=9600, 
            timeout=1
        )
        
        # 2. Khởi tạo cảm biến INA219 (I2C) - Điện trở Shunt thường là 0.1 ohm
        self.SHUNT_OHMS = 0.1
        try:
            self.ina = INA219(self.SHUNT_OHMS)
            self.ina.configure()
            self.ina_ready = True
        except Exception as e:
            self.status_update.emit(f"Lỗi khởi tạo INA219: {str(e)}")
            self.ina_ready = False

        # 3. Khởi tạo MQTT
        self.mqtt_client = mqtt.Client()
        try:
            self.mqtt_client.connect("broker.hivemq.com", 1883, 60) # Thay bằng broker thực tế
        except:
            pass

        # 4. Khởi tạo AI (ONNX & Scaler)
        self.ai_ready = False
        try:
            with open(SCALER_PATH, 'r') as f:
                self.scaler_data = json.load(f)
            self.ort_session = ort.InferenceSession(MODEL_PATH)
            self.ai_ready = True
        except Exception as e:
            self.status_update.emit(f"Không thể load AI: {str(e)}")

    def run(self):
        while self.is_running:
            current_speed = 0
            voltage = 0.0
            current = 0.0
            power = 0.0
            
            # --- ĐỌC PLC ---
            if self.plc_client.connect():
                try:
                    response = self.plc_client.read_holding_registers(address=0x0000, count=1, slave=1)
                    if not response.isError():
                        current_speed = response.registers[0]
                except Exception:
                    pass

            # --- ĐỌC CẢM BIẾN INA219 ---
            if self.ina_ready:
                try:
                    voltage = self.ina.voltage()
                    current = self.ina.current() / 1000.0 # Đổi mA sang A
                    power = self.ina.power() / 1000.0     # Đổi mW sang W
                except DeviceRangeError as e:
                    self.status_update.emit("Lỗi quá tải INA219")
            
            # --- CẬP NHẬT GIAO DIỆN ---
            self.telemetry_update.emit({
                "speed": current_speed,
                "voltage": voltage,
                "current": current,
                "power": power
            })

            # --- CHẠY AI & ĐẨY MQTT (Mỗi 5 chu kỳ ~ 2.5s) ---
            self.ai_counter += 1
            if self.ai_counter >= 5:
                # Đẩy MQTT
                payload = json.dumps({"speed": current_speed, "voltage": voltage, "current": current})
                try:
                    self.mqtt_client.publish("conveyor/telemetry", payload)
                except:
                    pass

                # Chạy AI nếu đã load thành công
                if self.ai_ready:
                    try:
                        # Chuẩn hóa dữ liệu (Giả sử model nhận 2 input là speed và current)
                        mean = self.scaler_data.get('mean', [0, 0])
                        scale = self.scaler_data.get('scale', [1, 1])
                        
                        input_arr = np.array([[current_speed, current]], dtype=np.float32)
                        input_scaled = (input_arr - mean) / scale
                        
                        input_name = self.ort_session.get_inputs()[0].name
                        ai_result = self.ort_session.run(None, {input_name: input_scaled})
                        
                        # Xử lý kết quả đầu ra thành đề xuất
                        suggested_speed = int(ai_result[0][0][0])
                        ai_output = f"Đề xuất từ MPC: Điều chỉnh tần số về {suggested_speed}Hz để tối ưu."
                        self.suggestion_ready.emit(ai_output)
                    except Exception as e:
                        print("Lỗi suy luận AI:", e)

                self.ai_counter = 0

            time.sleep(0.5)

    def stop(self):
        self.is_running = False
        self.plc_client.close()
        self.mqtt_client.disconnect()
        self.wait()

# ==========================================
# LUỒNG CHÍNH: Giao diện HMI Kiosk
# ==========================================
class HMIMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI PLC HMI - Kiosk Mode")
        self.resize(800, 480) 
        
        self.setup_ui()
        
        self.ai_thread = AIWorkerThread()
        self.ai_thread.suggestion_ready.connect(self.display_ai_suggestion)
        self.ai_thread.telemetry_update.connect(self.update_telemetry_ui)
        self.ai_thread.start()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        title = QLabel("HỆ THỐNG ĐIỀU KHIỂN BĂNG CHUYỀN TÍCH HỢP AI")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #2c3e50;")
        main_layout.addWidget(title)

        content_layout = QHBoxLayout()
        
        # --- CỘT TRÁI: GIÁM SÁT ---
        left_column = QVBoxLayout()
        group_telemetry = QGroupBox("Giám sát Thông số")
        group_telemetry.setStyleSheet("font-size: 16px; font-weight: bold;")
        form_layout = QFormLayout()
        
        self.lbl_speed = QLabel("0 Hz")
        self.lbl_voltage = QLabel("0.0 V")
        self.lbl_current = QLabel("0.0 A")
        self.lbl_power = QLabel("0.0 W")
        
        for lbl in [self.lbl_speed, self.lbl_voltage, self.lbl_current, self.lbl_power]:
            lbl.setStyleSheet("color: #2980b9; font-weight: bold; font-size: 18px;")
            
        form_layout.addRow("Tốc độ băng tải:", self.lbl_speed)
        form_layout.addRow("Điện áp nguồn:", self.lbl_voltage)
        form_layout.addRow("Cường độ dòng:", self.lbl_current)
        form_layout.addRow("Công suất tiêu thụ:", self.lbl_power)
        group_telemetry.setLayout(form_layout)
        
        group_manual = QGroupBox("Điều khiển Thủ công")
        group_manual.setStyleSheet("font-size: 16px; font-weight: bold;")
        manual_layout = QHBoxLayout()
        
        self.spin_speed = QSpinBox()
        self.spin_speed.setRange(0, 100)
        self.spin_speed.setSuffix(" Hz")
        self.spin_speed.setStyleSheet("font-size: 18px; padding: 5px;")
        
        self.btn_manual_write = QPushButton("GHI TỐC ĐỘ")
        self.btn_manual_write.setStyleSheet("background-color: #3498db; color: white; font-weight: bold; padding: 10px;")
        self.btn_manual_write.clicked.connect(self.manual_speed_write)
        
        manual_layout.addWidget(QLabel("Cài đặt:"))
        manual_layout.addWidget(self.spin_speed)
        manual_layout.addWidget(self.btn_manual_write)
        group_manual.setLayout(manual_layout)
        
        left_column.addWidget(group_telemetry)
        left_column.addWidget(group_manual)
        content_layout.addLayout(left_column, stretch=1)

        # --- CỘT PHẢI: TRỢ LÝ AI ---
        group_ai = QGroupBox("Trợ lý AI Tối ưu Hóa (MPC)")
        group_ai.setStyleSheet("font-size: 16px; font-weight: bold;")
        ai_layout = QVBoxLayout()
        
        self.ai_display_label = QLabel("Đang thu thập dữ liệu...")
        self.ai_display_label.setAlignment(Qt.AlignCenter)
        self.ai_display_label.setStyleSheet("font-size: 18px; color: #e74c3c; border: 2px dashed #e74c3c; padding: 10px;")
        self.ai_display_label.setWordWrap(True)
        ai_layout.addWidget(self.ai_display_label)

        self.btn_apply = QPushButton("ÁP DỤNG ĐỀ XUẤT AI")
        self.btn_apply.setStyleSheet("background-color: #27ae60; color: white; font-size: 16px; font-weight: bold; padding: 15px;")
        self.btn_apply.clicked.connect(self.apply_ai_changes)
        self.btn_apply.setEnabled(False)

        self.btn_reject = QPushButton("BỎ QUA")
        self.btn_reject.setStyleSheet("background-color: #7f8c8d; color: white; font-size: 16px; font-weight: bold; padding: 15px;")
        self.btn_reject.clicked.connect(self.reject_changes)
        self.btn_reject.setEnabled(False)

        ai_layout.addWidget(self.btn_apply)
        ai_layout.addWidget(self.btn_reject)
        group_ai.setLayout(ai_layout)
        
        content_layout.addWidget(group_ai, stretch=1)
        main_layout.addLayout(content_layout)

    def update_telemetry_ui(self, data):
        self.lbl_speed.setText(f"{data['speed']} Hz")
        self.lbl_voltage.setText(f"{data['voltage']:.1f} V")
        self.lbl_current.setText(f"{data['current']:.3f} A")
        self.lbl_power.setText(f"{data['power']:.1f} W")

    def display_ai_suggestion(self, suggestion_text):
        self.ai_display_label.setText(suggestion_text)
        self.btn_apply.setEnabled(True)
        self.btn_reject.setEnabled(True)
        # Trích xuất số Hz để lưu tạm, dùng khi bấm "Áp dụng"
        try:
            self.suggested_hz = int([int(s) for s in suggestion_text.split() if s.isdigit()][0])
        except:
            self.suggested_hz = 45 # Default fallback

    def manual_speed_write(self):
        target_speed = self.spin_speed.value()
        self.write_speed_to_plc(target_speed, "thủ công")

    def apply_ai_changes(self):
        self.write_speed_to_plc(self.suggested_hz, "từ thuật toán MPC")
        self.reset_ui()

    def write_speed_to_plc(self, speed, source):
        if self.ai_thread.plc_client.is_socket_open():
            try:
                self.ai_thread.plc_client.write_register(address=0x0001, value=speed, slave=1)
                QMessageBox.information(self, "Thành công", f"Đã ghi lệnh {source}: {speed}Hz xuống PLC!")
            except Exception as e:
                QMessageBox.critical(self, "Lỗi", f"Không thể ghi: {str(e)}")
        else:
             QMessageBox.information(self, "Chế độ Test", f"(Giả lập) Đã ghi lệnh {source}: {speed}Hz xuống PLC!")

    def reject_changes(self):
        self.reset_ui()

    def reset_ui(self):
        self.ai_display_label.setText("Đang chờ chu kỳ AI tiếp theo...")
        self.btn_apply.setEnabled(False)
        self.btn_reject.setEnabled(False)

    def closeEvent(self, event):
        self.ai_thread.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HMIMainWindow()
    window.show()
    sys.exit(app.exec_())