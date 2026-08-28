"""새턴 ED3 폰트 — 지오메트리 정본 + 한글 슬롯 여유 계산.

실측(2026-08-24):

    /SYSTEM/KANJI12.FON  140,544B = **7,808 글리프 × 18B**
                         12행 × 12비트를 **바이트 경계에 안 맞추고 밀착 패킹**(144비트)
                         색인 = `(구-1)*94 + (점-1)` — JIS X 0208 순차
    /SYSTEM/ASCII.FON      4,096B = **341 글리프 × 12B**(8×12) — 반각, 평문
                         색인 = **문자 코드 그대로**(`ord`), 행마다 1바이트
                         ⚠ 예전 주석의 「256 × 16B (8×16)」은 **오진**이었다(2026-08-28).
                         stride 16 으로 읽으면 어긋나 `A` 가 `W` 로 그려진다.

🔴 **「압축 추정」은 오진이었다.** 루트 `docs/ports-survey.md` 의 첫 측정이 stride
   22/24/32/48 만 보고 18 을 안 봤다. あ·い·ア·亜·一 을 렌더해 확인했고, 그래서 ED3 의
   폰트 관문은 없다. 새턴 ED1+2 의 `11KANJI.FON`(22B · 16×11)과 **색인 규칙은 같고
   기하만 다르다** — `shared/fonts.pack22()` 대신 `pack18()` 이 필요하다.

한글은 새턴 ED1+2 와 같은 수법으로 넣는다 — **안 쓰는 글리프 슬롯을 덮어쓰고 그 슬롯의
SJIS 코드로 인코딩**한다. 파일 하나라 EXE 를 건드릴 필요가 없다.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

FON_KANJI = "/SYSTEM/KANJI12.FON"
FON_ASCII = "/SYSTEM/ASCII.FON"

STRIDE = 18  # 글리프 한 자
ROWS = 12
CELL = 12  # 실제 획 폭(비트)
GLYPHS = 7808  # 140,544 / 18
KANJI_KU = 16  # JIS 1급 한자가 시작하는 구

# 반각(ASCII.FON) — 셀은 8비트인데 **화면 advance 는 6px**(전각의 0.5칸, 실기 확정).
#   그래서 글자는 전부 **열 0~4 에 왼쪽 붙임**으로 그려져 있고 열 5 하나가 자간이다
#   (실측 2026-08-28: 열 4 까지 쓰는 글자 75 · 열 5 까지는 `#` 하나뿐).
ASCII_STRIDE = 12
ASCII_ROWS = 12
ASCII_CELL = 8  # 셀 폭(비트) — 그리는 자리는 앞 6칸뿐이다
ASCII_ADV = 6  # 실제 advance
ASCII_GLYPHS = 341


def ascii_unpack(asc, code):
    """반각 글리프 → `(12, 8)` 0/1 배열. 색인은 **문자 코드 그대로**다."""
    g = asc[code * ASCII_STRIDE : (code + 1) * ASCII_STRIDE]
    return np.unpackbits(np.frombuffer(g, dtype=np.uint8)).reshape(ASCII_ROWS, ASCII_CELL)


def ascii_render(asc, code, on="█", off="·"):
    return ["".join(on if v else off for v in row) for row in ascii_unpack(asc, code)]


def ascii_cols(asc, code):
    """잉크가 든 열 목록 — 여백을 재는 자리다."""
    a = ascii_unpack(asc, code)
    return [c for c in range(ASCII_CELL) if a[:, c].any()]


def jis_index(ch):
    """문자 → 글리프 색인. EUC-JP 로 구/점을 얻는다(JIS 와 같은 좌표계)."""
    try:
        b = ch.encode("euc_jp")
    except UnicodeEncodeError:
        return None
    if len(b) != 2:
        return None
    return (b[0] - 0xA1) * 94 + (b[1] - 0xA1)


def sjis_of_index(idx):
    """글리프 색인 → 그 슬롯을 가리키는 SJIS 2바이트."""
    ku, ten = divmod(idx, 94)
    ku += 1
    ten += 1
    c1 = 0x81 + (ku - 1) // 2 if ku <= 62 else 0xC1 + (ku - 63) // 2
    c2 = (ten + 0x3F + (1 if ten >= 64 else 0)) if ku % 2 else (ten + 0x9E)
    return bytes((c1, c2))


def unpack(fon, idx):
    """글리프 하나 → `(12, 12)` 0/1 배열. **비트가 바이트 경계를 안 지킨다.**"""
    g = fon[idx * STRIDE : (idx + 1) * STRIDE]
    bits = np.unpackbits(np.frombuffer(g, dtype=np.uint8))
    return bits[: ROWS * CELL].reshape(ROWS, CELL)


def pack18(bits):
    """`(12, ≥12)` 0/1 → 18B. `unpack` 의 역 — 한글 글리프를 굽는 자리다."""
    grid = np.zeros((ROWS, CELL), dtype=np.uint8)
    h, w = min(ROWS, bits.shape[0]), min(CELL, bits.shape[1])
    grid[:h, :w] = bits[:h, :w]
    return np.packbits(grid.reshape(-1)).tobytes()


def is_blank(fon, idx):
    return not fon[idx * STRIDE : (idx + 1) * STRIDE].strip(b"\x00")


def render(fon, idx, on="█", off="·"):
    return ["".join(on if v else off for v in row) for row in unpack(fon, idx)]


def load(disc=1):
    """`(kanji_fon, ascii_fon)`."""
    with C.open_disc(disc) as d:
        return d.read(FON_KANJI), d.read(FON_ASCII)


def used_indices(srcs=None):
    """게임이 **실제로 쓰는** 글리프 색인 집합 — 소재 **전부**를 본다.

    ⚠ 빈 글리프로 자리를 고르면 안 된다 — 실측 **빈 슬롯이 1개뿐**이다(7,808 중).
    「그려는 있지만 이 게임 문안에 안 나오는 글자」가 우리가 덮어쓸 자리다.

    🔴 **소재를 하나라도 빠뜨리면 쓰는 글자를 덮어쓴다** — 화면에 엉뚱한 글자가 나오는데
    빌드도 테스트도 통과한다. 그래서 덤프 폴더를 **자리로** 찾는다(새 소재가 저절로 딸려
    온다). 지금은 `map_jp`(대사) + `sys_jp`(본체·시스템 문자열) 둘이다.
    """
    import glob
    import json

    srcs = srcs or [
        os.path.join(C.OUT_DIR, "map_jp", "*.json"),
        os.path.join(C.OUT_DIR, "sys_jp", "*.json"),
    ]
    paths = [q for s in srcs for q in sorted(glob.glob(s))]
    if not paths:
        raise SystemExit("덤프가 없다 — 먼저 dump_map.py · dump_sys.py 를 돌린다")
    used = set()

    def eat(s):
        for ch in s:
            i = jis_index(ch)
            if i is not None and 0 <= i < GLYPHS:
                used.add(i)

    for path in paths:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        for blk in rec.get("blocks", ()):
            eat(blk["text"])
        for s in rec.get("strings", ()):
            eat(s["text"])
        eat(rec.get("map_name", ""))
    return used


def free_slots(used=None):
    """덮어써도 되는 슬롯 — **한자 구역(구 16~)만** 고른다.

    ⚠ 앞쪽 구(1~15 기호·가나·로마자)는 손대지 않는다. 시스템 문구·UI 가 그 자리를
    쓰는데 우리 덤프에 아직 안 잡힌 소재가 있다(`SYSTEM/*`·`BTL/*` 미조사).
    """
    used = used if used is not None else used_indices()
    lo = (KANJI_KU - 1) * 94
    return [i for i in range(lo, GLYPHS) if i not in used]


def main():
    fon, asc = load()
    print(f"KANJI12 {len(fon):,}B = {len(fon) // STRIDE:,} 글리프 × {STRIDE}B")
    print(f"ASCII   {len(asc):,}B = {len(asc) // ASCII_STRIDE} 글리프 × {ASCII_STRIDE}B (8×12)")
    blank = sum(1 for i in range(GLYPHS) if is_blank(fon, i))
    print(f"빈 글리프 {blank:,} / {GLYPHS:,}  (← 자리는 여기서 못 고른다)")
    used = used_indices()
    free = free_slots(used)
    need = 2350
    print(f"쓰는 글리프 {len(used):,}  한자 구역 여유 {len(free):,}  (완성형 {need:,} 필요)")
    print(f"  → {'✅ 충분' if len(free) >= need else '❌ 모자란다'}")
    for ch in "あアい亜一水":
        i = jis_index(ch)
        print(f"\n{ch}  색인 {i}  SJIS {sjis_of_index(i).hex()}")
        for r in render(fon, i):
            print("   " + r)


if __name__ == "__main__":
    main()
