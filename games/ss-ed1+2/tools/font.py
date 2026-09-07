"""새턴 폰트 — 지오메트리 정본 + 한글 슬롯 배정 계산.

실측(2026-08-19, 근거는 docs/policy.md):
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

# ── 폰트가 둘이고 쓰는 자리가 다르다 (2026-08-21) ─────────────────────────────
# 본편 대사는 `11KANJI.FON`(16×11), **타이틀·오프닝·엔딩은 `KANJI.FON`(16×16)** 이다.
# 색인 규칙은 같고(`(구-1)*94 + (점-1)`) 스트라이드와 글리프 수만 다르다.
# ⚠ **원본이 쓰는 글자가 서로 다르다** — 본편은 `scn_jp/*.json`, 타이틀은 `title_jp.json`.
#   한쪽 기준으로 빈 슬롯을 고르면 다른 쪽 글자를 덮어쓴다.
FONTS = {
    "11kanji": {
        "path": FON_KANJI,
        "stride": 22,
        "glyphs": 4375,
        "src": "scn_jp",  # work/derived/scn_jp/*.json
        "what": "본편 대사 (16×11 · Galmuri11)",
    },
    "kanji": {
        "path": "/KANJI.FON",
        "stride": 32,
        "glyphs": 7806,  # 94 × 83구
        "src": "title",  # work/derived/title_jp.json
        "what": "타이틀·오프닝·엔딩 (16×16 · Neo둥근모)",
    },
}
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


def _source_chars(src):
    """그 폰트를 쓰는 원본 텍스트의 글자들."""
    if src == "scn_jp":
        for p in glob.glob(os.path.join(common.OUT_DIR, "scn_jp", "*.json")):
            with open(p, encoding="utf-8") as f:
                for e in json.load(f)["entries"]:
                    yield from e["text"]
        return
    path = os.path.join(common.OUT_DIR, "title_jp.json")
    if not os.path.exists(path):
        raise SystemExit(f"{path} 가 없다 — 먼저 dump_title.py")
    with open(path, encoding="utf-8") as f:
        for v in json.load(f).values():
            for t in v["lines"]:
                yield from t


def used_indices(name="11kanji"):
    """원본 텍스트가 실제로 쓰는 글리프 인덱스 — 덮어쓰면 안 되는 슬롯."""
    cfg = FONTS[name]
    used = set()
    for ch in _source_chars(cfg["src"]):
        i = jis_index(ch)
        if i is not None and 0 <= i < cfg["glyphs"]:
            used.add(i)
    return used


def free_slots(name="11kanji"):
    """한글을 넣을 수 있는 슬롯. 원본이 쓰는 글자는 무조건 보존한다.

    **한자 구간(ku≥16)을 먼저 준다.** 빈 글리프가 더 많은 쪽은 ku 6~8·10~15 인데
    거기는 JIS 미정의 구역이라 (a) 표준 코덱으로 인코딩이 안 되고 (b) 게임의 다른
    경로(창 폭 계산·반각 판정)가 그 코드를 어떻게 보는지 **미검증**이다.
    한자 구간은 원본이 이미 쓰던 코드라 그 경로들이 통과를 보장한다.
    """
    cfg = FONTS[name]
    used = used_indices(name)
    kanji, other = [], []
    for i in range(cfg["glyphs"]):
        if i in used:
            continue
        (kanji if i // 94 + 1 >= KANJI_KU else other).append(i)
    return kanji + other


def main():
    common.verify_source()
    for name, cfg in FONTS.items():
        try:
            used = used_indices(name)
        except SystemExit as e:  # 덤프가 아직 없을 수 있다 — 그 폰트만 건너뛴다
            print(f"{cfg['path']}: 건너뜀 — {e}")
            continue
        slots = free_slots(name)
        safe = sum(1 for i in slots if i // 94 + 1 >= KANJI_KU)
        print(
            f"{cfg['path']} ({cfg['stride']}B/글리프) — {cfg['what']}\n"
            f"  {cfg['glyphs']} 글리프 · 원본 사용 {len(used)} · 여유 {len(slots)}\n"
            f"  그중 한자 구간(권장) {safe} · 미정의/기호 구간 {len(slots) - safe}"
        )
    print(
        f"11KANJI.FON 파일 뒤 여유 {HEADROOM}B = 글리프 {HEADROOM // GLYPH_STRIDE}자 (크기 유지 권장)"
    )

    bad = [i for i in range(KANJI_GLYPHS) if game_index(sjis_of_index(i)) != i]
    print(f"게임 루틴 대조: 불일치 {len(bad)} / {KANJI_GLYPHS}")


# ── 문안 → 바이트 ─────────────────────────────────────────────────────────────
# 🔴 **한 줄짜리 규칙인데 네 곳에 손으로 적혀 있었다**(2026-08-29) — `patch_ui.encode` ·
#    `patch_ui.scn_encode` · `patch_scn._encode` · `patch_mon_names.encode` ·
#    `patch_title.encode`. 지금은 넷이 같은 답을 내지만(검산했다) **한 곳만 바뀌면 조용히
#    갈린다** — 표가 다른 인코딩으로 깔리면 화면에서만 드러난다.
# ⚠ 감싸는 규칙(널·채움·폭 검사)은 자리마다 다르니 그건 각자 둔다. 여기 있는 건 **글자
#   하나를 어떻게 바이트로 적나** 하나뿐이다.


def to_bytes(kr, plan):
    """우리 문안 → 바이트. 한글은 **슬롯 SJIS**, 나머지는 cp932.

    🔴 한글은 cp932 로 인코딩이 안 된다 — 안 쓰는 글리프 슬롯에 배정하고 **그 슬롯의
       SJIS 코드**로 적는다(`hangul_map_11kanji.json`, 이 게임의 근간).
    """
    return b"".join(plan[c][0] if plan and c in plan else c.encode("cp932") for c in kr)


def byte_len(kr):
    """바이트 수 — 슬롯에 든 글자는 전각 2B, 나머지는 cp932 길이.

    ⚠ `to_bytes` 와 **답이 같아야 한다**(회귀가 본다). 계획 없이도 재려고 근사하는데,
      슬롯 코드가 전부 2B 라 지금은 정확하다(실측 2026-08-29: 1,120자 전부 2B).
    """
    n = 0
    for ch in kr:
        try:
            n += len(ch.encode("cp932"))
        except UnicodeEncodeError:
            n += 2
    return n


if __name__ == "__main__":
    main()
