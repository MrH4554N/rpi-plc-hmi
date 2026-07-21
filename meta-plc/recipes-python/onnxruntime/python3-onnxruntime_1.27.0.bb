SUMMARY = "ONNX Runtime Python package (Pre-compiled for ARM64 Python 3.13)"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

S = "${UNPACKDIR}"

# 1. Thêm lại cờ ;unpack=0 để Yocto giữ nguyên file zip, cho phép ta tự giải nén
SRC_URI = "https://files.pythonhosted.org/packages/5e/7d/e6bb1c6445c94f708c38cd8fbb7bf0264108c33498b9445c93e60fe6d329/onnxruntime-1.27.0-cp313-cp313t-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl;downloadfilename=onnxruntime.zip;unpack=0"

# 2. Mã băm bảo mật
SRC_URI[sha256sum] = "54c0c4e9202c36c4ecdb1f3443f5dfbfd5ee3b54d1362c4b4c6134110e74fb32"

inherit python3-dir

# Chỉ cần khai báo phụ thuộc để có lệnh unzip
DEPENDS += "unzip-native"

INSANE_SKIP:${PN} += "already-stripped architecture"

do_install() {
    install -d ${D}${PYTHON_SITEPACKAGES_DIR}
    
    # 3. Trỏ đúng vào UNPACKDIR (nơi Yocto 5.x chứa mã nguồn tải về) thay vì WORKDIR
    unzip -q ${UNPACKDIR}/onnxruntime.zip -d ${D}${PYTHON_SITEPACKAGES_DIR}/
}

FILES:${PN} += "${PYTHON_SITEPACKAGES_DIR}/*"

RDEPENDS:${PN} += " \
    python3-numpy \
    python3-protobuf \
    python3-flatbuffers \
"