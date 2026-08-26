"""원문에 있던 것이 우리 문안에서 **사라지지 않았나** — 숫자 · 고유명사.

    python3 games/ss-ed3/tools/check_fidelity.py           # 옮긴 것 전량
    python3 games/ss-ed3/tools/check_fidelity.py MAP012    # 그 맵만
    python3 games/ss-ed3/tools/check_fidelity.py --quiet   # 건수만(게이트용)

🔴 **오역 중에 제일 조용한 것이 「빠뜨림」이다.** 문장은 매끄럽고, 길이도 맞고, 조판도
통과하는데 금액이 사라지거나 지명이 딴 것으로 바뀐다. 화면을 봐도 어색하지 않아서
플레이해 봐야 안다 — 그때는 이미 44 만 자가 쌓여 있다.

기계로 확실히 잴 수 있는 둘만 본다:

- **숫자** — 전각·반각 숫자를 정규화해 원문과 문안의 다중집합을 맞춘다.
  `５０００ピア` 의 5000 이 사라지거나 `８０` 이 `８` 이 되는 자리를 잡는다.
- **고유명사** — 원문에 나온 표제어(`glossary_manual.json`)의 정본 표기가 문안에 있는가.
  「라그나」로 옮겨야 할 것을 「라구나」로 쓴 자리, 아예 빠뜨린 자리를 잡는다.

⚠ **경고지 실패가 아니다.** 원문의 숫자를 우리말로 풀어 쓰는 자리가 있고(「１度」 →
「한번」), 고유명사를 대명사로 받는 자리도 있다. 사람이 보고 가른다.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import mapfile as M
import reinsert as R
import typeset as T

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DIGIT = str.maketrans("０１２３４５６７８９", "0123456789")
_NUM = re.compile(r"\d+")
# 🔴 **작은 수는 안 센다.** 우리말은 작은 수를 낱말로 삼켜 버린다 — 「１番」 → 「제일」 ·
#   「２日」 → 「이틀」 · 「２、３日」 → 「이삼 일」 · 「５つ」 → 「다섯」. 사전으로 못 따라가서
#   오탐만 쌓였다(실측: 7 → 34). 정작 조용히 틀리면 아픈 것은 **금액과 거리**다
#   (`５０００ピア` · `１１６４ミロ`) — 그건 반드시 숫자로 남으므로 두 자리 이상만 본다.
_MIN = 10
# ⚠ 두 자리 수도 낱말로 삼켜진다 — 「２０年」 → 「스무 해」 · 「１５歳」 → 「열다섯 살」.
#   문안에 **우리말 수사**가 보이면 그 블록은 넘어간다. 늘 켜지는 경고는 아무도 안 본다.
_KO_NUM = re.compile(
    r"하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉|열|스물|스무|서른|마흔|쉰|예순|일흔|여든|아흔|"
    r"한 |두 |세 |네 |첫|이틀|사흘|나흘|이삼|백|천|만 "
)


def numbers(s):
    return sorted(n for n in _NUM.findall(T.visible(s).translate(_DIGIT)) if int(n) >= _MIN)


def load_gloss():
    with open(os.path.join(GAME, "glossary_manual.json"), encoding="utf-8") as f:
        cats = json.load(f)["categories"]
    out = {}
    for name, c in cats.items():
        # ⚠ 기술명은 **일반 동사와 겹친다**(`投げる` = 「던지기」). 대사에 그 동사가 나올
        #   때마다 「고유명사가 빠졌다」고 울므로 표에서 뺀다.
        if name == "skill":
            continue
        for jp, kr in c.items():
            v = kr if isinstance(kr, str) else kr.get("kr")
            if v and len(jp) >= 2:
                out[jp] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stems", nargs="*")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    gloss = load_gloss()
    maps = {}
    for disc in (1, 2):
        with C.open_disc(disc) as d:
            for n, lba, size in sorted(d.files()):
                if not (n.startswith("/MAP/") and n.endswith(".BIN")):
                    continue
                stem = os.path.basename(n)[:-4]
                if stem not in maps:
                    maps[stem] = M.blocks(d.read_extent(lba, size))

    n_num = n_name = n_all = 0
    for stem in sorted(maps):
        if a.stems and stem not in a.stems:
            continue
        kr, _ = R.load_script(stem)
        bl = maps[stem]
        for k, v in sorted(kr.items(), key=lambda x: int(x[0])):
            i = int(k)
            if not 0 <= i < len(bl):
                continue
            jp = M.text_of(bl[i]["body"])
            n_all += 1

            want, got = numbers(jp), numbers(v)
            if want != got and not _KO_NUM.search(T.visible(v)):
                n_num += 1
                if not a.quiet:
                    print(f"  {stem}:{k}  숫자 원문 {want} → 문안 {got}")
                    print(f"    {jp[:40]!r}")
                    print(f"    {v[:40]!r}")

            miss = [f"{j}→{g}" for j, g in gloss.items() if j in jp and g not in v]
            if miss:
                n_name += 1
                if not a.quiet:
                    print(f"  {stem}:{k}  고유명사 {', '.join(miss[:4])}")
                    print(f"    {v[:44]!r}")

    print(
        f"숫자 어긋남 {n_num} · 고유명사 빠짐 {n_name} / 옮긴 블록 {n_all} — ⚠ 경고이지 실패가 아니다"
    )


if __name__ == "__main__":
    main()
