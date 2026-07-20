FILESEXTRAPATHS:prepend := "${THISDIR}:"
SRC_URI += "file://weston.ini"

do_install:append() {
    install -d ${D}${sysconfdir}/xdg/weston
    install -m 0644 ${WORKDIR}/weston.ini ${D}${sysconfdir}/xdg/weston/
}
