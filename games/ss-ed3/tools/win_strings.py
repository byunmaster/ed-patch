"""윈도 정발(신 영웅전설Ⅲ 하얀마녀, 1999) 문자열 뽑기 — **표기 대조용**.

우리 표기 정본은 「정발 표기가 있으면 따른다」인데(`glossary_manual._doc`), 정발이 **둘이다** —
만트라 **DOS** 판과 1999 **윈도** 판. 둘이 갈리는 자리가 실제로 있다(`칫타`/`치타` ·
`우돌`/`우들` · `안델라`/`안데라` · `카렉`/`캐라크`). 그래서 둘 다 읽을 수 있어야 한다.

🔴 **게임 본체(`ED3_DT*.dat`)는 아직 못 읽는다.** `LB DAT` 아카이브인데 멤버가 압축이라
(리터럴 구간만 평문으로 샌다 — 한 파일에 한글 300자 남짓) 통째로는 안 나온다.
대신 **2018 팬 확장팩**(`ed3_expansion.exe`, .NET)이 대사창에 일러스트를 띄우려고
**장면 이름 · 화자 이름 · 대사 일부를 UTF-16 으로 박아 두었다.** 그걸 읽는다.

    python3 tools/win_strings.py            # work/review/win_strings.txt 로
    python3 tools/win_strings.py --diff     # 정본과 대조 — 어디가 갈리나

⚠ 뽑은 문안은 **원저작물**이다. `work/review/` 밖으로 내보내지 않는다(루트 「저작권」).
"""

import argparse
import json
import os

import common as C

EXE = os.path.join(C.ROOT, "originals", "kr", "win-ed3", "ed3_expansion.exe")
#   ⚠ 앞쪽 9MB 는 일러스트다. 한글 밀도를 재면 0x900000 부터가 문자열 무더기다.
DATA_FROM = 0x900000
KEEP = set(" ,.!?~…·()「」『』0123456789:;/'\"-　―ㆍ’‘“”")


def _ok(c):
    return "가" <= c <= "힣" or "A" <= c <= "Z" or "a" <= c <= "z" or c in KEEP


def strings(path, start=DATA_FROM, least=2):
    """UTF-16LE 로 이어지는 한글 문자열. 이미지 잡음은 「한글 2자 이상」으로 걸러진다."""
    with open(path, "rb") as f:
        b = f.read()
    out, cur = [], []
    for i in range(start, len(b) - 1, 2):
        c = chr(b[i] | (b[i + 1] << 8))
        if _ok(c):
            cur.append(c)
            continue
        s = "".join(cur).strip()
        if len(s) >= 2 and sum("가" <= x <= "힣" for x in s) >= least:
            out.append(s)
        cur = []
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=EXE)
    ap.add_argument("--diff", action="store_true", help="정본·DOS 코퍼스와 대조")
    a = ap.parse_args()
    if not a.exe or not os.path.exists(a.exe):
        raise SystemExit(f"윈도 정발이 없다: {a.exe}")

    ss = strings(a.exe)
    os.makedirs(C.REVIEW_DIR, exist_ok=True)
    out = os.path.join(C.REVIEW_DIR, "win_strings.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(ss) + "\n")
    ko = sum(sum("가" <= x <= "힣" for x in s) for s in ss)
    print(f"윈도 문자열 {len(ss):,} · 한글 {ko:,}자 → {out}")

    if not a.diff:
        return
    win = "\n".join(ss)
    with open(os.path.join(C.OUT_DIR, "kr_corpus.json"), encoding="utf-8") as f:
        dos = json.load(f)
    with open(os.path.join(C.GAME_DIR, "glossary_manual.json"), encoding="utf-8") as f:
        cats = json.load(f)["categories"]

    def dos_n(v):
        return sum(n for k, n in dos.items() if v in k)

    ok, only_dos, none = [], [], []
    for cat in ("person", "place"):
        for jp, kr in cats[cat].items():
            (ok if kr in win else only_dos if dos_n(kr) else none).append((jp, kr, dos_n(kr)))
    print(f"\n정본 {len(ok) + len(only_dos) + len(none)}")
    print(f"  ✅ 윈도에도 그대로  {len(ok)}")
    print(
        f"  ⚠ DOS 에만        {len(only_dos)}  — 윈도 표기가 다를 수 있다(문자열이 일부라 없다고 단정 못 한다)"
    )
    print(f"  ❔ 둘 다 없음      {len(none)}")
    for jp, kr, n in sorted(only_dos, key=lambda r: -r[2])[:40]:
        print(f"     {jp:14} {kr:10} DOS {n:>4}회")


if __name__ == "__main__":
    main()
