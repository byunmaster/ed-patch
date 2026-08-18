#!/usr/bin/env python3
"""동영상 EXE(오프닝·엔딩·크레딧)의 텍스트 풀을 구획별로 뜨고 정발 원문과 나란히 놓는다.

**왜 도구인가.** 이 층은 SCN 대사와 완전히 다른 파이프라인이라 `todo_untranslated` 도
`check_scn_jp_left` 도 여기를 안 본다. 그래서 「화면 일본어 전 씬 0」인데도 오프닝·엔딩에
일본어가 남아 있었다(2026-08-11 발견). 무엇이 남았는지 세는 자가 있어야 한다.

**구조(2026-08-11 실측).** 동영상 EXE 는 넷인데(`OPEN1`·`OPEN2`·`END1`·`END2`, 각 96,256B)
**텍스트 풀이 넷 다 내용상 동일하다**(고유 문자열 234개, 차집합 0). 각 EXE 는 자기 몫만
화면에 쓰지만 데이터는 통째로 들고 있다 — 그래서 **한 벌의 문안으로 넷을 다 덮으면**
어느 파일이 어느 화면을 돌리는지 몰라도 안전하다.

포인터 표가 구획을 가른다(OPEN1 기준 — 파일마다 조금씩 밀려 있다):

| 텍스트 오프셋   | 구획                       | 줄 | 정발 원본                      |
| --------------- | -------------------------- | -: | ------------------------------ |
| `0x974~0xEEE`   | ED1 오프닝                 | 50 | 완료(`textmap/opening.json`)   |
| `0xF38~0x11CC`  | **ED2 오프닝**             | 26 | `dos-ed2/OPENING.EXE` 0x99102~ |
| `0x1238~0x150F` | ED1 크레딧                 | 37 | — (사람 이름, 번역 안 함)      |
| `0x1518~0x1AAF` | **ED1 엔딩 내레이션·대사** | 59 | `dos-ed1/ENDING.EXE` 0x1973A~  |
| `0x1B5C`        | **ED2 엔딩 꼬리 한 줄**    |  1 | `dos-ed2/ENDING.DLL` 0x3EC3B~  |
| `0x1B7C~0x1E5F` | ED2 크레딧                 | 38 | — (사람 이름, 번역 안 함)      |
| `0x1E60~0x2400` | **ED2 엔딩 내레이션**      | 34 | `dos-ed2/ENDING.DLL` 0x3EC3B~  |

⚠ **크레딧이 두 벌**이고 ED2 쪽은 **역순으로 배치**돼 있다(스태프롤이 아래에서 위로
올라가는 연출이라 그렇다). 둘 다 사람 이름이라 번역 대상이 아니지만, 구획을 잘못 잡으면
엔딩 내레이션과 섞인다 — `0x1B5C` 한 줄(`そして少年は英雄となる…`)이 크레딧 사이에
끼어 있는 게 그 예다.

  python3 tools/dump_movie_text.py            # 구획 요약 + 남은 일본어 수
  python3 tools/dump_movie_text.py --review   # → work/review/movie_text.md (정발 대조표)
"""

import os
import re
import sys

from common import ORIG_BIN, REVIEW_DIR, ROOT, extract

MOVIE_EXES = (("OPEN1", 69), ("OPEN2", 116), ("END1", 163), ("END2", 210))
EXE_SIZE = 96256
TADDR = 0x80010000
DELTA = TADDR - 0x800  # RAM → 파일 오프셋
PTR_LO, PTR_HI = 0x13000, 0x16800  # 포인터 표가 사는 범위
TEXT_LO, TEXT_HI = 0x800, 0x2400  # 텍스트 풀

# 구획 — (이름, 텍스트 오프셋 하한, 상한, 정발 원본). 상한은 미포함.
SECTIONS = (
    ("ED1 오프닝", 0x974, 0xEF0, None),  # 완료 — dos-ed1/OPENING.EXE (textmap/opening.json)
    ("E1_OP TIM", 0xEF0, 0xF38, None),
    ("ED2 오프닝", 0xF38, 0x11D0, "dos-ed2/OPENING.EXE"),
    ("E2_OP TIM", 0x11D0, 0x1238, None),
    ("ED1 크레딧", 0x1238, 0x1510, None),  # 사람 이름 — 번역 안 함(유저 판단 2026-08-11)
    ("ED1 엔딩", 0x1518, 0x1AB0, "dos-ed1/ENDING.EXE"),
    ("E1_ED TIM", 0x1AB0, 0x1B5C, None),
    ("ED2 엔딩 꼬리", 0x1B5C, 0x1B7C, "dos-ed2/ENDING.DLL"),
    ("ED2 크레딧", 0x1B7C, 0x1E60, None),  # 사람 이름 — 번역 안 함
    ("ED2 엔딩", 0x1E60, 0x2400, "dos-ed2/ENDING.DLL"),
)

# 정발 원문이 사는 자리(실측). cp949, 공백이 `_` 로 들어간 파일도 있다.
KR_SPANS = {
    "dos-ed2/OPENING.EXE": (0x99102, 0x99680),
    "dos-ed1/ENDING.EXE": (0x1973A, 0x19D40),
    "dos-ed2/ENDING.DLL": (0x3EC3B, 0x3F200),
}
KANA = re.compile(r"[ぁ-んァ-ヴ一-龯]")
KR_RUN = re.compile(rb"(?:[\xB0-\xC8][\xA1-\xFE]|[\xA1-\xAF][\xA1-\xFE]|[ -~]){4,}")


def pool(name, lba):
    """{텍스트 오프셋: (문자열, [포인터 자리…])} — 포인터가 실제로 가리키는 것만."""
    d = extract(lba, EXE_SIZE, path=ORIG_BIN)
    out = {}
    for off in range(PTR_LO, PTR_HI, 4):
        v = int.from_bytes(d[off : off + 4], "little")
        f = v - DELTA
        if not (TEXT_LO <= f < TEXT_HI):
            continue
        end = d.find(b"\x00", f)
        try:
            s = d[f:end].decode("shift_jis")
        except UnicodeDecodeError:
            continue
        if len(s) < 2:
            continue
        out.setdefault(f, (s, []))[1].append(off)
    return out


def kr_lines(rel):
    """정발 원본의 그 구간에서 한글 줄을 순서대로."""
    path = os.path.join(ROOT, "..", "..", "originals", "kr", rel)
    if not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        d = f.read()
    if rel not in KR_SPANS:
        return []
    lo, hi = KR_SPANS[rel]
    out = []
    for m in KR_RUN.finditer(d, lo, hi):
        try:
            t = m.group().decode("cp949")
        except UnicodeDecodeError:
            continue
        if len(re.findall(r"[가-힣]", t)) < 2:
            continue
        out.append((m.start(), len(m.group()), t.replace("_", " ").strip()))
    return out


def main(review=False):
    p = pool(*MOVIE_EXES[0])
    print(f"{MOVIE_EXES[0][0]}: 포인터가 가리키는 문자열 {len(p)}개\n")
    print(f"{'구획':14} {'줄':>4} {'일본어 남음':>11}  정발 원본")
    lines = []
    for label, lo, hi, kr in SECTIONS:
        seg = sorted((f, s) for f, (s, _) in p.items() if lo <= f < hi)
        jp = sum(1 for _, s in seg if KANA.search(s))
        print(f"{label:14} {len(seg):>4} {jp:>11}  {kr or '—'}")
        lines.append((label, lo, hi, kr, seg))
    if not review:
        return 0

    os.makedirs(REVIEW_DIR, exist_ok=True)
    out = ["# 동영상 텍스트 정발 대조 — 오프닝·엔딩·크레딧", ""]
    out.append("⚠ 정발 문안을 담으므로 **커밋 금지**(work/review 는 gitignore).")
    out.append("")
    for label, lo, hi, kr, seg in lines:
        out.append(f"## {label}  (0x{lo:X}~0x{hi:X}, {len(seg)}줄)")
        out.append("")
        if kr is None:
            out.append("번역 대상 아님.")
            out.append("")
            continue
        krl = kr_lines(kr)
        out.append(f"정발 원본 `{kr}` — 후보 {len(krl)}줄")
        out.append("")
        out.append("| # | PS1 오프셋 | PS1 일문 | 정발 후보 |")
        out.append("| -: | - | - | - |")
        for i, (f, s) in enumerate(seg):
            k = krl[i] if i < len(krl) else None
            ks = f"`0x{k[0]:X}+{k[1]}` {k[2]}" if k else ""
            out.append(f"| {i} | `0x{f:04X}` | {s} | {ks} |")
        out.append("")
    path = os.path.join(REVIEW_DIR, "movie_text.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"\n→ {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--review" in sys.argv))
