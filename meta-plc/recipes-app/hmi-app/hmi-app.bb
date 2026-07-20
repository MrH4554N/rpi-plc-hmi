SUMMARY = "HMI Application for PLC Control"
LICENSE = "CLOSED"

SRC_URI = " \
    file://hmi_fx_ai.py \
    file://hmi-app.service \
"

inherit systemd

SYSTEMD_SERVICE:${PN} = "hmi-app.service"
SYSTEMD_AUTO_ENABLE = "enable"

do_install() {
    # Copy app python vào /usr/bin/
    install -d ${D}${bindir}
    install -m 0755 ${WORKDIR}/hmi_fx_ai.py ${D}${bindir}/

    # Copy service vào thư mục quản lý của systemd
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/hmi-app.service ${D}${systemd_system_unitdir}/
}

# Khai báo các thư viện phụ thuộc để app có thể chạy
RDEPENDS:${PN} += "python3-pyqt5 python3-pyserial python3-numpy python3-smbus2"
