SUMMARY = "ONNX Runtime Python package (Pre-compiled for ARM64 Python 3.13)"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

# 1. Đường dẫn tải file wheel cho Python 3.13 (đã chèn link của bạn)
SRC_URI = "https://files.pythonhosted.org/packages/5e/7d/e6bb1c6445c94f708c38cd8fbb7bf0264108c33498b9445c93e60fe6d329/onnxruntime-1.27.0-cp313-cp313t-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl;downloadfilename=onnxruntime.zip"

# 2. Bạn điền mã SHA-256 vào đây
SRC_URI[sha256sum] = "<MÃ_SHA256>"

inherit python3-dir

DEPENDS += "unzip-native"

# Bỏ qua kiểm tra kiến trúc vì đã là file nhị phân cấp thấp build sẵn
INSANE_SKIP:${PN} += "already-stripped architecture"

do_unpack[depends] += "unzip-native:do_populate_sysroot"

do_install() {
    install -d ${D}${PYTHON_SITEPACKAGES_DIR}
    
    # Giải nén thẳng các module C++ (.so) và Python vào hệ thống
    unzip -q ${WORKDIR}/onnxruntime.zip -d ${D}${PYTHON_SITEPACKAGES_DIR}/
}

FILES:${PN} += "${PYTHON_SITEPACKAGES_DIR}/*"

RDEPENDS:${PN} += " \
    python3-numpy \
    python3-protobuf \
    python3-flatbuffers \
"
