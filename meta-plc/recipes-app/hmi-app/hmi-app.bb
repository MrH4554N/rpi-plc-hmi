SUMMARY = "HMI Application for PLC Control"
LICENSE = "CLOSED"

S = "${UNPACKDIR}"

# 1. Khai báo thêm file mô hình và scaler vào SRC_URI
SRC_URI = " \
    file://hmi_fx_ai.py \
    file://hmi-app.service \
    file://model.onnx \
    file://scaler.json \
"

inherit systemd

SYSTEMD_SERVICE:${PN} = "hmi-app.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_install() {
    # Copy app python vào /usr/bin/
    install -d ${D}${bindir}
    install -m 0755 ${UNPACKDIR}/hmi_fx_ai.py ${D}${bindir}/

    # Copy service vào thư mục quản lý của systemd
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/hmi-app.service ${D}${systemd_system_unitdir}/

    # 2. Tạo thư mục /usr/share/hmi-app/ và copy model AI vào đó
    install -d ${D}${datadir}/${PN}
    install -m 0644 ${UNPACKDIR}/model.onnx ${D}${datadir}/${PN}/
    install -m 0644 ${UNPACKDIR}/scaler.json ${D}${datadir}/${PN}/
}

# Khai báo các thư viện phụ thuộc
RDEPENDS:${PN} += " \
    python3-pyqt5 \
    qtwayland \
    python3-pyqtgraph \
    python3-pymodbus \
    python3-paho-mqtt \
    python3-numpy \
    python3-smbus2 \
    python3-pi-ina219 \
    python3-onnxruntime \
    python3-json \
"

# Đảm bảo Yocto gom tất cả vào image cuối cùng
FILES:${PN} += " \
    ${bindir}/hmi_fx_ai.py \
    ${systemd_system_unitdir}/hmi-app.service \
    ${datadir}/${PN}/* \
"