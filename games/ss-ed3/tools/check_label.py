"""**라벨**(이름표·메뉴 딱지)이 자리마다 다르게 옮겨졌나 — 정적 일관성 검사.

대사는 같은 원문이라도 **말 상대와 화자가 다르면** 달리 옮기는 게 맞다(실측: 같은 원문이
두 가지 이상으로 옮겨진 블록 90 중 대부분이 그 부류다). 그래서 여기서는 **판단이 들어갈
자리가 없는 것**만 본다 — 이름표다.

    라벨 = 개행·페이지넘김이 없고 · 문장부호(。？！…)가 없고 · 짧다(≤ RUNE_MAX 자)

🔴 **이름표가 갈리면 화면에서 같은 사람이 두 이름으로 보인다.** 실측으로 잡힌 것들:
`ルドルフ王` 이 「루돌프 왕」6 · 「루돌프왕」3, `ブリット隊長` 이 「브리트 대장」7 ·
「브리트대장」1, `ウドルの兵士`·`カーリー王妃` 도 같은 꼴(띄어쓰기만 갈렸다).
⚠ **띄어쓰기 하나라도 갈리면 잡는다** — 화면 폭이 달라지고, 무엇보다 「어느 쪽이
정본인가」를 아무도 못 정한 채로 굳는다.

    python3 games/ss-ed3/tools/check_label.py
    python3 games/ss-ed3/tools/check_label.py --all   # 라벨이 아닌 것까지 (참고용)

⚠ 게이트다 — 라벨이 갈리면 실패한다. 대사 쪽 흔들림은 `--all` 로 볼 뿐 실패로 안 친다.
"""

import argparse
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

RUNE_MAX = 12  # 이보다 길면 라벨로 안 본다
PUNCT = "。、？！…・「」『』"


def is_label(jp):
    return (
        jp
        and len(jp) <= RUNE_MAX
        and not any(c in jp for c in "\n\f")
        and not any(c in jp for c in PUNCT)
    )


def scan():
    """`{JP: {KR: [자리…]}}`."""
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for f in sorted(glob.glob(os.path.join(C.OUT_DIR, "map_jp", "MAP*.json"))):
        stem = os.path.basename(f)[:-5]
        p = os.path.join(C.GAME_DIR, "script", f"{stem}.json")
        if not os.path.exists(p):
            continue
        with open(f, encoding="utf-8") as fh:
            jp = json.load(fh)["blocks"]
        with open(p, encoding="utf-8") as fh:
            kr = json.load(fh)
        for i, b in enumerate(jp):
            k = kr.get(str(i))
            if k:
                by[b["text"]][k].append(f"{stem}#{i}")
    return by


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="라벨이 아닌 블록까지 본다(참고용)")
    a = ap.parse_args()

    by = scan()
    bad = []
    loose = 0
    for jp, kinds in by.items():
        if len(kinds) < 2:
            continue
        if is_label(jp):
            bad.append((jp, kinds))
        else:
            loose += 1
            if a.all:
                print(f"  ⓘ {jp[:40]!r}")
                for kr, at in sorted(kinds.items(), key=lambda x: -len(x[1])):
                    print(f"       {len(at):>3}회  {kr[:40]!r}  {at[:3]}")
    for jp, kinds in sorted(bad):
        print(f"  ❌ {jp!r} 가 {len(kinds)} 가지로 갈렸다")
        for kr, at in sorted(kinds.items(), key=lambda x: -len(x[1])):
            print(f"       {len(at):>3}회  {kr!r}  {at[:4]}")
    print(
        f"라벨 흔들림 {len(bad)} · 대사 흔들림 {loose}(참고) / 원문 {len(by):,}"
    )
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
