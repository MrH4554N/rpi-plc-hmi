SUMMARY = "Python library for INA219 voltage and current sensor"
HOMEPAGE = "https://github.com/chrisb2/pi_ina219"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=e43d925d2ba7bbda2c1bd39dc5ddf3bc"

# Kế thừa 2 class mạnh nhất để xử lý thư viện Python
inherit pypi setuptools3

PYPI_PACKAGE = "pi-ina219"

# Khai báo mã băm để Yocto kiểm tra tính toàn vẹn của file tải về
SRC_URI[sha256sum] = "b0ef3aeb7bc8510842245b0a37e06a374668ba436eb4204d538eec1ea3988242"

# Khai báo các thư viện nền mà pi-ina219 cần để chạy
RDEPENDS:${PN} += " \
    python3-smbus \
    python3-logging \
"