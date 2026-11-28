"""Insert slide transitions into a pptx: Morph (Fade fallback) or a short Fade.

Usage: morph_post.py IN.pptx OUT.pptx [TRANSITIONS.json]
The JSON maps slide number -> "morph" | "fade". Without it every slide gets Morph.
"""

import json
import re
import sys
import zipfile

MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
P159 = "http://schemas.microsoft.com/office/powerpoint/2015/09/main"
P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
MORPH = (
    f'<mc:AlternateContent xmlns:mc="{MC}">'
    f'<mc:Choice xmlns:p159="{P159}" Requires="p159">'
    f'<p:transition spd="slow" xmlns:p14="{P14}" p14:dur="1250">'
    '<p159:morph option="byObject"/></p:transition></mc:Choice>'
    '<mc:Fallback><p:transition spd="med"><p:fade/></p:transition></mc:Fallback>'
    "</mc:AlternateContent>"
)
FADE = '<p:transition spd="fast"><p:fade/></p:transition>'
SLIDE = re.compile(r"ppt/slides/slide(\d+)\.xml$")
OLD = re.compile(r"<p:transition.*?</p:transition>|<p:transition[^>]*/>")


def main(src: str, dst: str, plan_path: str | None) -> None:
    plan = {}
    if plan_path:
        with open(plan_path, encoding="utf8") as fh:
            plan = {int(k): v for k, v in json.load(fh).items()}
    counts = {"morph": 0, "fade": 0}
    with (
        zipfile.ZipFile(src) as zin,
        zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout,
    ):
        for item in zin.infolist():
            data = zin.read(item.filename)
            match = SLIDE.match(item.filename)
            if match:
                kind = plan.get(int(match.group(1)), "morph")
                xml = OLD.sub("", data.decode("utf8"))
                if "</p:clrMapOvr>" not in xml:
                    raise ValueError(f"no clrMapOvr in {item.filename}")
                xml = xml.replace(
                    "</p:clrMapOvr>",
                    "</p:clrMapOvr>" + (MORPH if kind == "morph" else FADE),
                    1,
                )
                data = xml.encode("utf8")
                counts[kind] += 1
            zout.writestr(item, data)
    print("transitions", counts)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
