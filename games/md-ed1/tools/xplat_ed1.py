"""기종 간 같은 원문 대조(대본 씬) — MD 우리 문안 ↔ PS1(ps1-ed1+2) 문안.

    python3 tools/xplat_ed1.py --out <tsv>

PS1 정본(`ps1_reuse.corpus`)과 **원문이 같은 스트림만** 맞붙여(`match_pages`) 글자(한글·숫자·영문)만 비교한다.
부호·공백·조사 훅·이름 자리·화자 머리는 걷는다 — 글자가 다른 줄만 낸다. 열: 씬:키 · 우리 · PS1 · 부호만 다른가.
⚠ 출력엔 우리·PS1 한글 문안만 있다(원문 일본어 없음). 기준 게임 워크트리는 읽기만 한다.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import ps1_reuse as pr
import scene
import textmap

KEEP = re.compile(r"[^0-9A-Za-z가-힣]")


def squash(s: str, keep_punct: bool = False) -> str:
    s = re.sub(r"<1e>.*?<04>", "", s)
    s = re.sub(r"<[0-9a-f:|]+[^>]*>", "", s)
    s = re.sub(r"\{[a-z]\}", "", s)
    s = re.sub(r"[\x00-\x1f]", "", s)
    s = re.sub(r"은\(는\)|이\(가\)|을\(를\)|과\(와\)|으로\(로\)", "", s)
    if keep_punct:
        return re.sub(r"\s+", "", s)
    return KEEP.sub("", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cp = pr.corpus()
    bl = archives.blocks(common.rom(), archives.ARCHIVES["script"][0])
    rows, tot, same, punct = [], 0, 0, 0
    for n, (_, b, _) in enumerate(bl):
        p = textmap.SCRIPT_DIR / f"{n:03d}.json"
        if not p.exists():
            continue
        cur = json.loads(p.read_text(encoding="utf-8"))["streams"]
        mod = scene.parse_module(b)
        for off in sorted(mod.streams):
            ent = cur.get(f"{off:04x}")
            st = mod.streams[off]
            if not ent or not ent.get("ours") or pr.header_text(st) is not None:
                continue
            _sp, pages = pr.stream_pages(st)
            if not pages:
                continue
            m = pr.match_pages(pages, cp)
            if not m:
                continue
            ps1 = "".join(x[2] for x in m)
            if any(pr.has_placeholder(x[2]) and False for x in m):
                continue
            tot += 1
            ours = ent["ours"]
            if squash(ours) == squash(ps1):
                same += 1
                if squash(ours, True) != squash(ps1, True):
                    punct += 1
                continue
            rows.append((f"{n:03d}:{off:04x}", ours.replace("\f", " ¶ "), ps1.replace("\f", " ¶ ")))
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("키\t우리\tPS1\n")
        for r in rows:
            f.write("\t".join(x.replace("\t", " ").replace("\n", " ") for x in r) + "\n")
    print(f"맞붙은 스트림 {tot} · 글자 같음 {same}(그중 부호·공백만 다름 {punct}) · 글자 다름 {len(rows)}")


if __name__ == "__main__":
    main()
