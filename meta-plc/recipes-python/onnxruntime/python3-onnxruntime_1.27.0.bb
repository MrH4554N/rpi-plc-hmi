SUMMARY = "ONNX Runtime Python package (Pre-compiled for ARM64 Python 3.13)"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

S = "${UNPACKDIR}"

# Đảm bảo bạn tải đúng bản wheel phù hợp với môi trường Python của Yocto (lưu ý chữ 't' trong cp313t)
SRC_URI = "https://files.pythonhosted.org/packages/5e/7d/e6bb1c6445c94f708c38cd8fbb7bf0264108c33498b9445c93e60fe6d329/onnxruntime-1.27.0-cp313-cp313t-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl;downloadfilename=onnxruntime.zip;unpack=0"
SRC_URI[sha256sum] = "54c0c4e9202c36c4ecdb1f3443f5dfbfd5ee3b54d1362c4b4c6134110e74fb32"

inherit python3-dir

DEPENDS += "unzip-native"

# Vô hiệu hóa các bước biên dịch C/C++ mặc định
do_configure[noexec] = "1"
do_compile[noexec] = "1"

# Bổ sung các cờ bỏ qua QA check khắt khe của Yocto đối với file .so
INSANE_SKIP:${PN} += "already-stripped architecture file-rdeps libdir"

do_install() {
    install -d ${D}${PYTHON_SITEPACKAGES_DIR}
    
    # Trỏ đúng vào UNPACKDIR như bạn đã viết
    unzip -q ${UNPACKDIR}/onnxruntime.zip -d ${D}${PYTHON_SITEPACKAGES_DIR}/
}

FILES:${PN} += "${PYTHON_SITEPACKAGES_DIR}/*"

RDEPENDS:${PN} += " \
    python3-core \
    python3-numpy \
    python3-protobuf \
    python3-flatbuffers \
"