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


_KATA = re.compile(r"[ァ-ヴー]")
#   ⚠ 지명 뒤의 보통명사는 **한국어에서 활용한다** — `ルピナス湖`=「루피나스 호수」인데
#     본문은 「루피나스 **호숫가**」다(사이시옷). 뒷말을 빼고 **앞의 고유부만** 센다.
_PLACE_TAIL = (
    "湖",
    "川",
    "島",
    "城",
    "山地",
    "街道",
    "関所",
    "砦",
    "塔",
    "村",
    "海岸",
    "海岸線",
    "森",
)


def _standalone(j, jp):
    """`j` 가 `jp` 안에 **낱말로** 있나.

    ⚠ 가타카나 이름은 **더 긴 가타카나 낱말의 일부**로 걸린다 — `コル`(콜)이 `コルク`(코르크,
    「병뚜껑」)에 먹혀 「콜이 빠졌다」고 울었다(실측). 정본 안에서만 겹침을 보는 걸로는
    못 잡는다(`コルク` 는 고유명사가 아니라 정본에 없다). 그래서 **앞뒤가 가타카나면 뺀다.**

    ⚠ **숫자 바로 뒤의 가타카나는 이름이 아니라 단위다** — `３ベン回る`(3 번 돌다)의 `ベン`
    이 인물 `ベン`(벤)으로 걸려 「벤이 빠졌다」고 울었다(MAP037 실측 2026-08-27). 이름이
    수 바로 뒤에 조사 없이 붙는 자리는 없으므로 그 자리는 뺀다.
    """
    kata = all(_KATA.match(c) for c in j)
    i = jp.find(j)
    while i >= 0:
        if not kata:
            return True
        a = jp[i - 1] if i else ""
        b = jp[i + len(j) : i + len(j) + 1]
        digit = a.translate(_DIGIT).isdigit() if a else False
        if not digit and not _KATA.match(a or " ") and not _KATA.match(b or " "):
            return True
        i = jp.find(j, i + 1)
    return False


def _need(jp, kr):
    """문안에 있어야 할 최소 조각.

    ⚠ 지명은 **고유부만** 본다 — 뒷말이 한국어에서 활용한다(`ルピナス湖`=「루피나스 호수」
    인데 본문은 「루피나스 **호숫가**」).
    """
    return kr.split()[0] if jp.endswith(_PLACE_TAIL) and " " in kr else kr


def _has(kr, v):
    """문안 `v` 에 이름 `kr` 이 있나.

    ⚠ **관형격 「의」는 칸이 좁으면 떨어진다** — 아이템 이름 「진홍의 불꽃」(11B)이 선택지
    라벨 칸 8B 에 안 들어가 「진홍불꽃」이 됐다(MAP041 실측). 둘은 **같은 것으로 읽히므로**
    이름이 갈린 게 아니다(「파도길」/「물결소리 길」과 다르다). 줄인 꼴도 있는 것으로 친다.

    ⚠ **떨어질 때 띄어쓰기까지 없어지지는 않는다** — 「라우알의 파도」 뒤에 또 관형격이
    오면(`파도의 근원`) 「의」가 겹쳐 읽기 나빠서 앞을 떨군다: 「라우알 파도의 근원」.
    이 꼴은 붙여 쓴 「라우알파도」가 아니라 **공백이 남은 「라우알 파도」**이다. 처음엔 이걸
    못 알아봐서, 검사기를 달래려고 문안에 「의」를 겹쳐 넣을 뻔했다(2026-08-28).
    """
    if kr in v:
        return True
    if " " not in kr:
        return False
    return kr.replace("의 ", "").replace(" ", "") in v or kr.replace("의 ", " ") in v


def load_gloss():
    with open(os.path.join(GAME, "glossary_manual.json"), encoding="utf-8") as f:
        raw = json.load(f)
    cats = raw["categories"]
    #   ⚠ 일반 낱말과 겹치는 이름은 「빠졌다」가 늘 거짓이다 — `チップ` 는 칩이자 팁이고
    #     `リッチ` 는 인물이자 「풍족한」이다. 표기는 정본에 남기고 **강제만 뺀다.**
    skip = set(raw.get("no_check", ()))
    out = {}
    for name, c in cats.items():
        # ⚠ 기술명은 **일반 동사와 겹친다**(`投げる` = 「던지기」). 대사에 그 동사가 나올
        #   때마다 「고유명사가 빠졌다」고 울므로 표에서 뺀다.
        if name == "skill":
            continue
        for jp, kr in c.items():
            v = kr if isinstance(kr, str) else kr.get("kr")
            if v and len(jp) >= 2 and jp not in skip:
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

            # ⚠ **긴 이름에 먹힌 짧은 이름**을 빼지 않으면 영원히 우는 자리가 생긴다 —
            #   `ティラスイール`(티라스일) 안에 별개 인물 `イール`(이르)가 들어 있어,
            #   원문에 나라 이름만 나와도 「이르가 빠졌다」고 울었다(실측 8건).
            hit = [j for j in gloss if _standalone(j, jp)]
            hit = [j for j in hit if not any(o != j and j in o and o in jp for o in hit)]
            miss = [f"{j}→{gloss[j]}" for j in hit if not _has(_need(j, gloss[j]), v)]
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
