#!/usr/bin/env python3
"""최종 이미지에 **구워진 글리프끼리 비트맵이 같은 쌍**이 있으면 실패한다.

**왜.** ss-ed1+2 에서 글꼴을 구울 때 행 맞춤(dy)이 쉼표 꼬리 행을 잘라 반각 쉼표가 마침표와 **같은 비트맵**이
됐고, 문안의 쉼표 3,983곳이 전부 마침표로 그려졌다(10-19). 원본 글꼴 파일에는 문제가 없고 **구운 결과**에만 있는
결함이라 원본을 보는 검사로는 못 잡는다 — 롬에서 읽어 비교한다(체크리스트 「검사기 자신의 커버리지」).

**무엇을 비교하나**(대사창이 그리는 표 셋, ED.EXE·ED2.EXE 둘 다):
  · 반각 글리프 표(8×11, 11B) — 색인 0~175(ASCII 0x21~0x7E · 반각 가타카나·우리 반각 한글 코드). 주소 = 표 base + 색인 × 11
  · 전각 가나·기호 블록(11×16, 22B) — 0x800F1BA0 / 0x800CD538 부터 한자 블록 직전까지
  · 한글 음절 슬롯(한자 블록 위에 구운 2,350자, 22B)
빈 글리프(공백)는 뺀다.

**허용**: 원판 폰트가 원래 같은 모양인 쌍 — 그리스·키릴 문자가 로마자와 같은 꼴, 괘선·줄표(―와 ─ 류). 아래
`ALLOWED_KANA_GROUPS` 가 그 목록이고, 빌드가 새로 만든 쌍(우리가 구운 글리프끼리 같음)은 여기 없으면 실패다.
허용 목록은 최종 이미지 기준이다 — 원판에는 로마자(Ａ…)가 낀 더 큰 묶음이었는데 우리가 로마자 슬롯을 구워 묶음이 작아졌다.

  python3 tools/check_glyph_pairs.py            # 검사(이미지가 없으면 「안 쟀다」로 실패)
  python3 tools/check_glyph_pairs.py -v         # 쌍 전부 출력
"""

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import font_map as F
import hangul_map as H

from common import BUILD_DIR, extract

IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"

# {실행파일: (LBA, 크기, 반각 표 base 파일 오프셋, 게임 키)} — patch_hangul_glyph_table.EXES 와 같은 값
EXES = {
    "ED.EXE": (257, 1021952, 0xF4F78, "ED1"),
    "ED2.EXE": (756, 872448, 0xD0910, "ED2"),
}
HALF_COUNT = 176  # 색인 0~175 — ASCII 0x21~0x7E(0~93) · 0xA1~0xDF 구간(색인 = 코드 − 0x40 …)까지 덮는다
KANA_COUNT = 524  # (한자 블록 base − 가나 블록 base) / 22 — ED·ED2 같다

# 원판 폰트에 원래 있던 같은 모양(가나 블록 색인). 두 EXE 가 같은 값이다(폰트가 통째로 옮겨졌을 뿐).
ALLOWED_KANA_GROUPS = {
    (28, 492),
    (34, 493),
    (183, 459),
    (185, 477),
    (187, 464),
    (194, 386),
    (197, 416, 474),
    (198, 476),
    (204, 414),
    (206, 481),
    (207, 479),
    (378, 426),
    (380, 429),
    (382, 431),
    (384, 440),
    (389, 439),
    (392, 441),
    (393, 442),
    (394, 443),
    (396, 445),
    (398, 447),
    (399, 448),
    (420, 478),
}


def groups(table):
    """{비트맵: [색인…]} 에서 2개 이상인 묶음만 — 빈 글리프는 호출 쪽에서 이미 뺐다."""
    return sorted(tuple(v) for v in table.values() if len(v) > 1)


def half_groups(buf, base):
    t = collections.defaultdict(list)
    for i in range(HALF_COUNT):
        g = bytes(buf[base + i * 11 : base + i * 11 + 11])
        if any(g):
            t[g].append(i)
    return groups(t)


def kana_groups(buf, game):
    kb = F.ram_to_ed_file(F.FONT_BASE[game]["kana"])
    t = collections.defaultdict(list)
    for i in range(KANA_COUNT):
        g = bytes(buf[kb + i * 22 : kb + i * 22 + 22])
        if any(g):
            t[g].append(i)
    return groups(t)


def hangul_groups(buf, game):
    t = collections.defaultdict(list)
    for ch in H.SYL_INDEX:
        o = F.kanji_glyph_ed_offset(H.syllable_sjis(ch), game)
        g = bytes(buf[o : o + 22])
        if any(g):
            t[g].append(ch)
    return groups(t)


def audit(bufs):
    """{실행파일: {"half": [...], "kana": [허용 밖], "hangul": [...]}} — 비어 있어야 통과."""
    bad = {}
    for exe, (_lba, _size, base, game) in EXES.items():
        b = bufs[exe]
        k = [g for g in kana_groups(b, game) if g not in ALLOWED_KANA_GROUPS]
        bad[exe] = {"half": half_groups(b, base), "kana": k, "hangul": hangul_groups(b, game)}
    return bad


def main(argv):
    verbose = "-v" in argv
    if not os.path.exists(IMG):
        print(f"  ❌ 안 쟀다 — 빌드 이미지가 없다: {IMG}")
        return 1
    bufs = {exe: bytes(extract(lba, size, path=IMG)) for exe, (lba, size, _b, _g) in EXES.items()}
    bad = audit(bufs)
    n = 0
    for exe, d in bad.items():
        for kind, gs in d.items():
            for g in gs:
                n += 1
                print(f"  ❌ {exe} {kind} 글리프 같은 비트맵: {g}")
    if verbose:
        for exe, (_l, _s, base, game) in EXES.items():
            print(f"  (참고) {exe} 가나 블록 허용 묶음 {len(kana_groups(bufs[exe], game))}")
    if n:
        print(f"  ❌ 구운 글리프끼리 같은 비트맵 {n}묶음 — 글꼴 굽기(행 맞춤·잘림)를 본다")
        return 1
    print("  ✅ 구운 글리프끼리 같은 비트맵 0묶음 (반각 표 · 가나 블록 허용 밖 · 한글 슬롯)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
