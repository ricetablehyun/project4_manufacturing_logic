"""Insert a Morph transition (Fade fallback) into every slide of a pptx."""

import re
import sys
import zipfile

MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
P159 = "http://schemas.microsoft.com/office/powerpoint/2015/09/main"
P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
TRANSITION = (
    f'<mc:AlternateContent xmlns:mc="{MC}">'
    f'<mc:Choice xmlns:p159="{P159}" Requires="p159">'
    f'<p:transition spd="slow" xmlns:p14="{P14}" p14:dur="1500">'
    '<p159:morph option="byObject"/></p:transition></mc:Choice>'
    '<mc:Fallback><p:transition spd="slow"><p:fade/></p:transition></mc:Fallback>'
    "</mc:AlternateContent>"
)
SLIDE = re.compile(r"ppt/slides/slide\d+\.xml$")
OLD = re.compile(r"<p:transition.*?</p:transition>|<p:transition[^>]*/>")


def main(src: str, dst: str) -> None:
    count = 0
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if SLIDE.match(item.filename):
                xml = OLD.sub("", data.decode("utf8"))
                if "</p:clrMapOvr>" not in xml:
                    raise ValueError(f"no clrMapOvr in {item.filename}")
                xml = xml.replace("</p:clrMapOvr>", "</p:clrMapOvr>" + TRANSITION, 1)
                data = xml.encode("utf8")
                count += 1
            zout.writestr(item, data)
    print("morph on", count, "slides")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
