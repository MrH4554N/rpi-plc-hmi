SUMMARY = "ONNX Runtime Precompiled Wheel for Yocto"
LICENSE = "CLOSED"

# Yêu cầu file này phải có mặt trong thư mục files/
SRC_URI = "file://onnxruntime_aarch64.whl"

inherit python3native python3-dir
DEPENDS += "python3 python3-pip-native"
do_unpack[noexec] = "1"

do_install() {
    install -d ${D}${PYTHON_SITEPACKAGES_DIR}
    export PIP_DISABLE_PIP_VERSION_CHECK=1
    pip3 install --no-cache-dir --no-deps --target ${D}${PYTHON_SITEPACKAGES_DIR} ${WORKDIR}/onnxruntime_aarch64.whl
}

FILES:${PN} += "${PYTHON_SITEPACKAGES_DIR}/*"
