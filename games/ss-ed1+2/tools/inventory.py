"""덤프한 텍스트를 「무엇을 번역해야 하나」 관점으로 집계한다.

work/derived/scn_jp/*.json → work/review/inventory.md + inventory.json
⚠ 원문을 담으므로 review/ 아래다(커밋 금지).

분류는 소재(파일)와 형태(블록/문자열·서식 인자 유무)로만 한다 — 의미 분류는
사람이 볼 표에서 하고, 여기서는 「어디에 몇 개가 있는가」를 세는 데 집중한다.
"""

import glob
import json
import os
import re

import common

REVIEW = os.path.join(common.WORK_DIR, "review")

CATS = [
    ("ED1 씬 대사", re.compile(r"^ED1SCN\d+$")),
    ("ED2 씬 대사", re.compile(r"^ED2SCN\d+$")),
    ("ED2 몬스터 전투", re.compile(r"^ED2MON\d+$")),
    ("ED1 본체(시스템·아이템·전투)", re.compile(r"^ED$")),
    ("ED2 본체(시스템·아이템·전투)", re.compile(r"^ED2$")),
    ("ED1 초기화", re.compile(r"^ED1INIT$")),
]


def cat_of(tid):
    for name, pat in CATS:
        if pat.match(tid):
            return name
    return "기타"


def main():
    src = os.path.join(common.OUT_DIR, "scn_jp")
    docs = [json.load(open(p)) for p in sorted(glob.glob(f"{src}/*.json"))]
    if not docs:
        raise SystemExit(f"덤프가 없다 — 먼저 dump_scn.py. ({src})")

    stat = {}
    for d in docs:
        c = cat_of(d["table_id"])
        s = stat.setdefault(c, {"files": 0, "block": 0, "string": 0, "chars": 0, "fmt": 0})
        s["files"] += 1
        for e in d["entries"]:
            s[e["kind"]] += 1
            s["chars"] += len(e["text"])
            if "%d" in e["text"] or "%s" in e["text"]:
                s["fmt"] += 1

    os.makedirs(REVIEW, exist_ok=True)
    lines = [
        "# 새턴 ED1+2 번역 대상 집계",
        "",
        "| 소재 | 파일 | 대사블록 | 문자열 | 문자수 | 서식인자 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    tot = {"files": 0, "block": 0, "string": 0, "chars": 0, "fmt": 0}
    for c, s in stat.items():
        lines.append(
            f"| {c} | {s['files']} | {s['block']:,} | {s['string']:,} | {s['chars']:,} | {s['fmt']} |"
        )
        for k in tot:
            tot[k] += s[k]
    lines.append(
        f"| **합계** | {tot['files']} | {tot['block']:,} | {tot['string']:,} | {tot['chars']:,} | {tot['fmt']} |"
    )

    with open(os.path.join(REVIEW, "inventory.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(REVIEW, "inventory.json"), "w") as f:
        json.dump(stat, f, ensure_ascii=False, indent=1)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
