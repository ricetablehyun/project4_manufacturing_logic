"""Build the presentation script markdown from the deck's speaker notes.

usage: python gen_script.py deck.pptx transitions.json out.md
"""

import json
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

VIDEO = 60  # seconds of the silent demo video on slide 14
RATES = (5.0, 5.5)  # non-space characters per second
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
FIX = {1: "도입: 시연 장면", 2: "도입: 4시간 57분", 4: "표지", 28: "마무리"}


def paras(xml):
    root = ET.fromstring(xml)
    return ["".join(t.text or "" for t in p.iter(A + "t")) for p in root.iter(A + "p")]


def is_text(p):
    return p.strip() and not re.fullmatch(r"\d+", p.strip())


def mmss(s):
    return f"{int(s // 60)}분 {int(s % 60):02d}초"


def main(deck, trp, out):
    z = zipfile.ZipFile(deck)
    with open(trp) as f:
        tr = json.load(f)
    n = len([f for f in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", f)])
    rows, body, tot = [], [], dict.fromkeys(RATES, 0.0)
    for i in range(1, n + 1):
        ps = [p.strip() for p in paras(z.read(f"ppt/slides/slide{i}.xml")) if is_text(p)]
        rels = z.read(f"ppt/slides/_rels/slide{i}.xml.rels").decode()
        name = re.search(r'Target="\.\./notesSlides/(notesSlide\d+\.xml)"', rels).group(1)
        note = "\n".join(p for p in paras(z.read("ppt/notesSlides/" + name)) if is_text(p))
        chars = len(re.sub(r"\s", "", note))
        morph = tr.get(str(i), "fade") == "morph"
        extra = 0.8 + (1.25 if morph else 0.5)
        sec = {}
        for r in RATES:
            speech = chars / r
            sec[r] = (max(speech, VIDEO) if i == 14 else speech) + extra
            tot[r] += sec[r]
        head = FIX.get(i, ps[1] if len(ps) > 1 else ps[0])
        cum = tot[5.0]
        kind = "모핑" if morph else "페이드"
        rows.append(
            f"| {i} | {head} | {kind} | {sec[5.0]:.0f}초 | {int(cum // 60)}:{int(cum % 60):02d} |"
        )
        body.append(f"## {i}. {head}\n\n{note}\n")
    intro = [
        "# 공프4 기말발표 대본 (기준본)",
        "",
        "PPT `공프4_기말발표_PPT.pptx`의 발표자 노트와 글자 하나까지 같습니다. "
        "노트를 고치면 이 파일도 다시 만듭니다.",
        "",
        f"- 슬라이드 {n}장. 시연 영상은 **14장**(약 {VIDEO}초, 소리 없음)이며, "
        "영상이 나오는 동안 14장 대본을 말합니다.",
        f"- 예상 총 시간: **보통 속도(1초에 5글자, 공백 제외) 약 {mmss(tot[5.0])}**. "
        f"빠르게(1초에 5.5글자) 읽으면 약 {mmss(tot[5.5])}입니다. "
        f"영상 {VIDEO}초, 전환(모핑 1.25초·페이드 0.5초), 장마다 0.8초 쉼을 더한 값이며, "
        "실제 녹음 시간은 리허설로 확인해야 합니다.",
        "- '움직임'이 모핑인 장은 앞 장의 도형이 이어서 움직입니다. "
        "클릭 한 번이면 넘어가고, 장 안에 따로 클릭할 애니메이션은 없습니다.",
        "- 용어는 처음 나올 때 쉬운 말을 먼저 하고 이름을 붙였습니다: 묶음=LOT, 제품 하나=Unit, "
        "출하검사 약속 시각=Gate, 제품 하나에 걸리는 평균 시간=Pace, 예상 완료 시각=Forecast, "
        "줄이 생기는 곳=병목, 닫힌 고리=폐루프.",
        "- 숫자 두 종류를 섞지 않습니다: **297분**은 시연 장면(U030에 480분 입력) "
        "한 번의 예측이고, "
        "**190분·1,523분·2,433분**은 별도 반복 실험(10/22 13:00 시작, 810회)의 평균입니다.",
        "",
        "| 장 | 제목 | 움직임 | 예상 시간(5글자/초) | 누적 |",
        "|---|---|---|---|---|",
    ]
    md = "\n".join(intro + rows) + "\n\n---\n\n" + "\n".join(body)
    with open(out, "w") as f:
        f.write(md)
    print(mmss(tot[5.0]), mmss(tot[5.5]))


if __name__ == "__main__":
    main(*sys.argv[1:4])
