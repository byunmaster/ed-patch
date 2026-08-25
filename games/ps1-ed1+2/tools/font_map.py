"""
SJIS → 폰트 글리프 위치 매핑. ED.EXE의 변환 루틴(0x800AE6C8~) 역분석 결과.

루틴 요약:
  - SJIS 2바이트를 합쳐 범위 판정으로 블록 베이스 선택
      0x8140~0x84BE (기호·영숫자·가나)  → RAM 0x800F1BA0  (로컬 인덱스는 별도 계산)
      0x889F~0x9872 (한자 1급, 亜~)     → RAM 0x800F48A8  (JIS 순차)
  - 글리프 주소 = 베이스 + 로컬인덱스 × 22   (글리프 = 11행 × 2바이트)

한자 블록은 표준 JIS X 0208 순차라 공식으로 계산 가능(한글 패치의 핵심 —
한자 슬롯을 한글로 덮어쓰고 해당 한자 SJIS 코드로 인코딩).
가나/기호 블록의 로컬 인덱스는 0x800AE768의 커스텀 계산이라 여기선 미구현.
"""

ED_TEXT_ADDR = 0x80010000
ED_FILE_BASE = 0x800  # ED.EXE text가 시작하는 파일 오프셋

KANJI_BASE_RAM = 0x800F48A8  # 亜 (JIS 16-1)
KANA_BASE_RAM = 0x800F1BA0  # 기호·가나 블록

# ── 게임별 폰트 블록 (2026-08-14 실측) ──────────────────────────────────────────
# 디스크에 실행파일이 둘이고(`ED.EXE` LBA 257 · `ED2.EXE` LBA 756) **각자 폰트를 들고 있다.**
# 그래서 ED1 에만 한글을 구우면 ED2 는 글자가 안 나온다 — 시스템 UI 도 SCN 대사도.
#
# 자리는 추측하지 않고 **바이트로 찾았다** — ED.EXE 원본의 亜 글리프 220B 를 떠서 ED2.EXE
# 에서 검색하니 한 곳에 걸렸고, 거기서 **68,293B(글리프 3,104자)가 연속 일치**한다.
# 가나 블록도 같은 방법으로 잡았는데 **두 블록의 오프셋 차이가 정확히 같다**(0x24668) —
# 폰트 배치가 통째로 그만큼 옮겨져 있을 뿐 구조는 동일하다는 뜻이다.
#
# ⚠ **원본에서 읽어야 한다.** 우리 빌드는 그 슬롯을 한글로 덮어쓰므로 산출물에서 뜨면
# 한글 글리프를 찾는 꼴이 된다(루트 CLAUDE.md 「원본이 어땠는가는 originals 에서」).
# 두 EXE 다 `t_addr = 0x80010000` · 헤더 0x800B 라 RAM↔파일 변환식은 한 벌로 족하다.
FONT_BASE = {
    "ED1": {"exe": "ED.EXE", "lba": 257, "kanji": 0x800F48A8, "kana": 0x800F1BA0},
    "ED2": {"exe": "ED2.EXE", "lba": 756, "kanji": 0x800D0240, "kana": 0x800CD538},
}
GLYPH_FIT = 3104  # 연속 일치가 보장된 글리프 수 — 우리가 쓰는 2,350 슬롯이 든다
GLYPH_STRIDE = 22  # 11행 × 2바이트
GLYPH_ROWS = 11
JIS_KANJI1_INDEX = (16 - 1) * 94  # 亜의 JIS 순차 인덱스 = 1410


def sjis_to_kuten(sjis):
    """SJIS 2바이트 → (구, 점). 표준 변환."""
    hi, lo = sjis >> 8, sjis & 0xFF
    if hi >= 0xE0:
        hi -= 0x40
    hi -= 0x81
    if lo >= 0x80:
        lo -= 1
    lo -= 0x40
    ku = hi * 2 + 1
    ten = lo
    if lo >= 94:
        ku += 1
        ten = lo - 94
    return ku, ten + 1


def jis_index(sjis):
    ku, ten = sjis_to_kuten(sjis)
    return (ku - 1) * 94 + (ten - 1)


def is_kanji1(sjis):
    return 0x889F <= sjis <= 0x9872


def is_kana_block(sjis):
    return 0x8140 <= sjis <= 0x84BE


def kanji_glyph_ram(sjis, game="ED1"):
    """한자 1급 SJIS → 글리프 RAM 주소. `game` 으로 실행파일을 고른다."""
    assert is_kanji1(sjis), f"0x{sjis:04X}는 한자 1급 범위 밖"
    base = FONT_BASE[game]["kanji"]
    return base + (jis_index(sjis) - JIS_KANJI1_INDEX) * GLYPH_STRIDE


def ram_to_ed_file(ram):
    """RAM 주소 → ED.EXE 파일 내 오프셋."""
    return ram - ED_TEXT_ADDR + ED_FILE_BASE


# 🔴 **가나·기호 블록은 JIS 순서가 아니다.** 자체 순서로 늘어서 있다 — 글리프를 그려서
# 확인했다(2026-08-24): 색인 0 부터 기호가 오고, **Ａ = 157**, `ａ` = 183, 그 뒤가 한자다.
# JIS 색인으로 잡으면(Ａ=220) 엉뚱한 글리프를 덮는다 — 실제로 한 번 그렇게 덮었다.
# ⚠ 그래서 이 블록은 **색인을 손으로 못 박고**, 쓰기 전에 `verify_latin` 으로 모양을 검산한다.
LATIN_A_INDEX = 157  # 전각 Ａ 의 블록 색인 (실측)


def latin_glyph_ed_offset(ch, game="ED1"):
    """전각 로마자 Ａ~Ｚ → 실행파일 오프셋."""
    i = ord(ch) - 0xFF21
    assert 0 <= i < 26, f"전각 대문자가 아니다: {ch!r}"
    return ram_to_ed_file(FONT_BASE[game]["kana"] + (LATIN_A_INDEX + i) * GLYPH_STRIDE)


def verify_latin(exe, game="ED1"):
    """덮기 전에 **원본이 정말 로마자인지** 모양으로 검산한다.

    🔴 색인이 한 칸만 어긋나도 조용히 남의 글리프를 덮는다(실측: JIS 색인으로 잡아 26자를
      엉뚱한 자리에 썼다). 잉크 상자만 보면 「글자처럼 생겼다」로 통과하므로 **모양**을 본다 —
      `Ｉ` 는 아주 좁고 `Ｗ` 는 아주 넓다. 둘이 다 맞으면 줄 전체가 맞은 것이다.
    """
    import numpy as np

    def ink_w(ch):
        o = latin_glyph_ed_offset(ch, game)
        bits = np.unpackbits(np.frombuffer(exe[o : o + GLYPH_STRIDE], np.uint8).reshape(11, 2), 1)
        xs = np.nonzero(bits)[1]
        return int(xs.max() - xs.min() + 1) if xs.size else 0

    wi, ww = ink_w("Ｉ"), ink_w("Ｗ")
    assert wi <= 4 and ww >= 8, (
        f"{game} 전각 로마자 자리가 아니다 — Ｉ 폭 {wi}(≤4 이어야) · Ｗ 폭 {ww}(≥8 이어야). "
        f"LATIN_A_INDEX={LATIN_A_INDEX} 를 다시 잰다."
    )


def kanji_glyph_ed_offset(sjis, game="ED1"):
    """한자 1급 SJIS → 그 게임 실행파일 안의 오프셋 (재삽입기가 쓸 값)."""
    return ram_to_ed_file(kanji_glyph_ram(sjis, game))


if __name__ == "__main__":
    # 프레임버퍼 매칭으로 확인된 주소와 대조 (王 0x800F593C, 子 0x800FA5B8, 오차 ±2)
    for ch, sjis, expect in [("王", 0x89A4, 0x800F593C), ("子", 0x8E71, 0x800FA5B8)]:
        got = kanji_glyph_ram(sjis)
        ku, ten = sjis_to_kuten(sjis)
        print(
            f"{ch} SJIS 0x{sjis:04X} 구점 {ku}-{ten} → RAM 0x{got:08X} "
            f"(파일 0x{kanji_glyph_ed_offset(sjis):X})  기대 0x{expect:08X}  "
            f"{'OK' if abs(got - expect) <= 2 else '!!'}"
        )


# ── 말줄임표 `…` (区1点36) ──────────────────────────────────────────────────────
# 원본 글리프는 점 셋이 x=1·5·9 에 고르게 퍼져 있어 **가로는 손댈 게 없다.** 다만 높이가
# `・` 와 같은 **중간**이라, 베이스라인에 찍히는 우리 온점(반각 ASCII)과 한 문장 안에서
# 어긋나 보인다(유저 인게임 판정 2026-08-24). 그래서 **세로로만 내린다** — 모양은 원본 그대로.
#
# 🔴 색인은 위 `LATIN_A_INDEX` 와 같은 함정이 있다(블록이 JIS 순서가 아니다). 다만 **区1 만은
# 통째로·JIS 순서 그대로** 들어 있다고 유도할 수 있다:
#     Ａ(区3点33) 의 JIS 색인 220 = 区1(94) + 区2(94) + 32, 블록 색인은 157 = 94 + 31 + 32.
#     → 区2 가 31칸으로 줄었을 뿐 **区1 은 94칸 그대로**다. 그래서 区1 은 `jis_index` 가 맞다.
# 그래도 유도는 유도라 쓰기 전에 `verify_ellipsis` 로 **모양을 검산**한다.
ELLIPSIS_SJIS = 0x8163  # …
PERIOD_SJIS = 0x8144  # ．(전각 온점) — 점 모양·베이스라인의 기준


def ku1_glyph_ed_offset(sjis, game="ED1"):
    """区1(기호) SJIS → 실행파일 오프셋. ⚠ 区1 밖은 블록 순서가 JIS 와 달라 못 쓴다."""
    ku, _ = sjis_to_kuten(sjis)
    assert ku == 1, f"区1 이 아니다: 0x{sjis:04X} (구 {ku}) — 이 블록은 JIS 순서가 아니다"
    return ram_to_ed_file(FONT_BASE[game]["kana"] + jis_index(sjis) * GLYPH_STRIDE)


def _glyph_rows(exe, sjis, game):
    """글리프 → 행마다 16비트 정수 11개."""
    o = ku1_glyph_ed_offset(sjis, game)
    g = exe[o : o + GLYPH_STRIDE]
    return [(g[r * 2] << 8) | g[r * 2 + 1] for r in range(GLYPH_ROWS)]


def _ink_rows(rows):
    ys = [r for r, w in enumerate(rows) if w]
    return (ys[0], ys[-1]) if ys else (None, None)


def verify_ellipsis(exe, game="ED1"):
    """덮기 전에 그 자리가 **정말 원본 `…`** 인지 모양으로 검산한다.

    🔴 색인이 한 칸만 어긋나면 조용히 남의 글리프를 덮는다(`verify_latin` 주석의 그 사고).
      잉크 유무만 보면 아무 글자나 통과하므로 **말줄임표에만 있는 성질**을 본다 —
      ① 잉크가 **두 행**뿐이고 ② 그 두 행이 **같은 모양**이며 ③ 점이 **셋**이다.
    """
    rows = _glyph_rows(exe, ELLIPSIS_SJIS, game)
    top, bot = _ink_rows(rows)
    ink = [w for w in rows if w]
    runs = 0
    w = rows[top] if top is not None else 0
    prev = 0
    for b in range(16):  # 켜진 칸의 덩어리 수 = 점 개수
        cur = w >> (15 - b) & 1
        runs += cur and not prev
        prev = cur
    assert (
        top is not None and bot - top == 1 and len(ink) == 2 and ink[0] == ink[1] and runs == 3
    ), (
        f"{game} `…` 자리가 아니다 — 잉크 행 {top}~{bot}({len(ink)}행) · 점 {runs}개. "
        f"기대: 두 행이 같은 모양 · 점 셋. 블록 색인을 다시 잰다."
    )


def ellipsis_baseline_glyph(exe, game="ED1"):
    """원본 `…` 를 **세로로만** 내려 전각 온점(`．`)과 같은 줄에 앉힌 22바이트 글리프.

    ⚠ 높이를 상수로 박지 않는다 — 두 실행파일이 각자 폰트를 들고 있어서
      (`FONT_BASE`) 기준을 **그 파일의 온점에서** 가져와야 어긋나지 않는다.
    """
    rows = _glyph_rows(exe, ELLIPSIS_SJIS, game)
    src_top, _ = _ink_rows(rows)
    dot_top, _ = _ink_rows(_glyph_rows(exe, PERIOD_SJIS, game))
    shift = dot_top - src_top
    out = [0] * GLYPH_ROWS
    for r, w in enumerate(rows):
        if w:
            assert 0 <= r + shift < GLYPH_ROWS, f"내릴 자리가 없다 (행 {r}+{shift})"
            out[r + shift] = w
    return b"".join(bytes([(w >> 8) & 0xFF, w & 0xFF]) for w in out)
