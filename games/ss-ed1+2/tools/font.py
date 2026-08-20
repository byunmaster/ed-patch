"""새턴 폰트 — 지오메트리 정본 + 한글 슬롯 배정 계산.

실측(2026-08-19, 근거는 docs/status.md):
  11KANJI.FON  96,250B = 4,375 글리프 × 22B (16bit × 11행, 실제 획은 11×11)
               인덱스 = (구-1)*94 + (점-1)  ← 코드로 확정(ED.BIN 0x0607D6AA~)
               SJIS→JIS 변환은 표준(0x0607D600). 가나·기호·한자가 **한 배열**이다.
  11ASCII.FON   2,805B = 255 글리프 × 11B (8×11) — 반각
  KANJI.FON   249,792B = 7,806 글리프 × 32B (16×16) — **TITLE.BIN 전용**
  ASCII/KANA.FON 4,096B = 256 × 16B (8×16) — 본체 미참조

로드는 LWRAM 고정 주소: 11KANJI→0x20280000, 11ASCII→0x20298000.
둘 사이 여유는 0x800(2,048B)뿐이라 **파일 크기를 늘리지 않는다**(93글리프분).

한글은 「안 쓰는 글리프 슬롯을 덮어쓰고 그 슬롯의 SJIS 코드로 인코딩」한다 —
PS1 과 같은 수법인데, 새턴은 대상이 EXE 가 아니라 파일 하나라 훨씬 싸다.
"""

import glob
import json
import os

import common

FON_KANJI = "/11KANJI.FON"
FON_ASCII = "/11ASCII.FON"
GLYPH_STRIDE = 22
GLYPH_ROWS = 11
GLYPH_CELL = 11  # 실제 획이 차지하는 폭(열 12~15 는 전부 0)
KANJI_GLYPHS = 4375
KANJI_KU = 16  # JIS 1급 한자가 시작하는 구 — 이 앞은 기호·가나·미정의
LOAD_KANJI = 0x20280000
LOAD_ASCII = 0x20298000
HEADROOM = LOAD_ASCII - LOAD_KANJI - 96250  # 파일 뒤 여유 바이트


def jis_index(ch):
    """문자 → 글리프 인덱스. EUC-JP 로 구/점을 얻는다(JIS 와 같은 좌표계)."""
    try:
        b = ch.encode("euc_jp")
    except UnicodeEncodeError:
        return None
    if len(b) != 2:
        return None
    return (b[0] - 0xA1) * 94 + (b[1] - 0xA1)


def sjis_of_index(idx):
    """글리프 인덱스 → 그 슬롯을 가리키는 SJIS 2바이트."""
    ku, ten = divmod(idx, 94)
    ku += 1
    ten += 1
    c1 = 0x81 + (ku - 1) // 2 if ku <= 62 else 0xC1 + (ku - 63) // 2
    if ku % 2:
        c2 = ten + 0x3F + (1 if ten >= 64 else 0)
    else:
        c2 = ten + 0x9E
    return bytes((c1, c2))


def game_index(b):
    """게임 자신의 계산을 그대로 재현한다 — `ED.BIN` 0x0607D600(SJIS→JIS) +
    0x0607D6AA~(인덱스). 상수는 실측(cmp 0xDF · add -129).

    우리 `sjis_of_index()` 가 게임과 어긋나면 화면에 엉뚱한 글자가 나오는데
    빌드도 테스트도 통과한다 — 그래서 검산기를 코드 안에 둔다.
    """
    hi, lo = b[0], b[1]
    r0 = hi - 0x40 if hi > 0xDF else hi
    r3 = (-129 + r0) * 2
    if lo > 127:
        r0, lo = r3 + 34, lo - 126
    else:
        r0, lo = r3 + 33, lo - 31
    jis = ((r0 & 0xFF) << 8) + lo
    ku, ten = (jis >> 8) - 0x20, (jis & 0xFF) - 0x20
    return (ku - 1) * 94 + (ten - 1)


def used_indices():
    """원본 텍스트가 실제로 쓰는 글리프 인덱스 — 덮어쓰면 안 되는 슬롯."""
    used = set()
    for p in glob.glob(os.path.join(common.OUT_DIR, "scn_jp", "*.json")):
        for e in json.load(open(p))["entries"]:
            for ch in e["text"]:
                i = jis_index(ch)
                if i is not None and 0 <= i < KANJI_GLYPHS:
                    used.add(i)
    return used


def free_slots():
    """한글을 넣을 수 있는 슬롯. 원본이 쓰는 글자는 무조건 보존한다.

    **한자 구간(ku≥16)을 먼저 준다.** 빈 글리프가 더 많은 쪽은 ku 6~8·10~15 인데
    거기는 JIS 미정의 구역이라 (a) 표준 코덱으로 인코딩이 안 되고 (b) 게임의 다른
    경로(창 폭 계산·반각 판정)가 그 코드를 어떻게 보는지 **미검증**이다.
    한자 구간은 원본이 이미 쓰던 코드라 그 경로들이 통과를 보장한다.
    """
    f, mm = common.open_image()
    try:
        for path, lba, size in common.iso_files(mm):
            if path == FON_KANJI:
                data = common.read_extent(mm, lba, size)
                break
        else:
            raise SystemExit("11KANJI.FON 을 못 찾았다")
    finally:
        mm.close()
        f.close()
    used = used_indices()
    kanji, other = [], []
    for i in range(KANJI_GLYPHS):
        if i in used:
            continue
        (kanji if i // 94 + 1 >= KANJI_KU else other).append(i)
    return kanji + other


def main():
    common.verify_source()
    used = used_indices()
    slots = free_slots()
    safe = sum(1 for i in slots if i // 94 + 1 >= KANJI_KU)
    print(f"11KANJI.FON: {KANJI_GLYPHS} 글리프, 원본 사용 {len(used)}, 여유 {len(slots)}")
    print(f"  그중 한자 구간(권장) {safe} · 미정의/기호 구간 {len(slots) - safe}")
    print(f"파일 뒤 여유 {HEADROOM}B = 글리프 {HEADROOM // GLYPH_STRIDE}자 (크기 유지 권장)")

    bad = [i for i in range(KANJI_GLYPHS) if game_index(sjis_of_index(i)) != i]
    print(f"게임 루틴 대조: 불일치 {len(bad)} / {KANJI_GLYPHS}")
    ex = slots[0]
    print(f"예: 슬롯 {ex} → SJIS {sjis_of_index(ex).hex()}")


if __name__ == "__main__":
    main()
