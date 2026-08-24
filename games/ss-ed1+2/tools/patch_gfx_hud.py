"""HUD 인명 한글화 — `SCR*.2D` 안의 **그림 글자**를 다시 그린다 (패널 아홉 · 112×40).

    python3 tools/patch_gfx_hud.py            # 미리보기만 → work/review/scr/
    python3 tools/patch_gfx_hud.py --apply    # 빌드 이미지에 넣는다

⚠ **자막(`patch_title.py --apply`)을 먼저** 넣는다 — 빌드 사본을 그쪽이 만든다.

🔴 **인명은 문자열이 아니다.** `ED.BIN` 0x438 의 파티 기본 이름 표를 한글로 바꿔도 HUD 는
   그대로였다. 디스크에도 실행 중 RAM 에도 그 SJIS 는 없다 — 패널이 **이름까지 구워진
   그림**이고 게임은 그걸 VDP2 로 올릴 뿐이다(실기 VRAM 70셀이 파일과 바이트까지 같다).

## 자리 (실측 2026-08-24)

패널 하나가 14×5 셀 = 112×40. 시작 셀은 아래 `PANELS`. ⚠ **14 배수 격자가 아니고**,
같은 시작값이라도 편에 따라 그림이 4px 내려가 있다 — 그래서 **이름 띠는 매번 잰다**.

    이름 칸  x 4~44 (왼쪽 테두리 x 0~2, 오른쪽 x 47 부터 `EP`) · 잉크 9행 · 원본 시작 x 7
    바탕     칸 안은 전부 39(0,0,128) 단색 — 그래서 「39 아닌 건 전부 글자」로 지운다
    글자색   16(240,208,32). 원본은 안티에일리어스가 있지만 우리는 비트맵 폰트라 단색이다

Galmuri9 는 한글이 **9×9 · advance 10** 이라 이 칸에 딱 맞는다(넉 자 = 40px = 칸 폭).
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ),
        "shared",
    ),
)

import common
import dump_scr
from fonts import galmuri
from glossary import lookup

REVIEW = os.path.join(common.REVIEW_DIR, "scr")

# ── HUD 잔량 라벨 `あと` → 「남다」 (2026-08-24) ───────────────────────────────
# 🔴 **`SCR*.2D` 가 아니라 `/FRAME.DAT` 이다.** 패널엔 `EP` 가 구워져 있지만 표시를 바꾸면
#    게임이 **NBG0 비트맵**(숫자·게이지를 그리는 그 층)에 라벨을 그린다 — 그 원본이 여기다.
#    실기에서 EP 표시를 「남다」로 바꾼 뒤 NBG0 에서 화소를 떠 디스크 전량에서 찾아 짚었다.
#    `/FRAME.DAT` 은 HUD 스프라이트 시트다(숫자 두 벌 · 상태이상 한자 · 게이지 · `あと`).
# 🔴 **같은 스프라이트가 파일 둘에 있다**(2026-08-24, 유저 QA 로 발각). `/FRAME.DAT` 만
#    고쳤더니 화면은 그대로 `あと` 였다 — 필드 HUD 가 읽는 건 `/STAT.DAT` 쪽이다.
#    「한 자리를 고쳤다」는 「그 그림이 사라졌다」가 아니다 — 아래 `sweep_ato()` 가
#    **넣은 이미지 전량에서 원본 그림이 남아 있나**를 훑어 자동 실패시킨다.
FRAME = "/FRAME.DAT"
STAT = "/STAT.DAT"
ATO_SITES = ((FRAME, 0x1080), (STAT, 0x0000))
ATO_OFF = ATO_SITES[0][1]  # 도트를 뜨는 기준 자리 (둘은 바이트까지 같다)
ATO_STRIDE = 16  # 한 행 16B — 쓰는 건 앞 12B
ATO_W, ATO_H = 12, 10  # 12×10, 0행은 빈 줄이라 잉크는 1~9행(9행)
ATO_TOP = 1
ATO_BG, ATO_MAIN, ATO_SHADOW = 39, 35, 37  # 남색 바탕 / 밝은 파랑 획 / 음영
# 🔴 **음영은 가로다**(유저 지적 2026-08-24). 같은 줄의 `ＨＰ`·`ＭＰ` 는 밝은 획(35) 오른쪽
#    칸에만 어두운 색(37)이 붙는다 — 세로 성분이 없다(실측 `SCR1.2D` 패널). `+1,+1` 은
#    대각선이라 입체가 과하게 보인다. 인명 쪽도 같은 이유로 가로다(`draw()`).
# 🔴 **도트는 PS1 과 같은 것을 쓴다**(`ps1-ed1+2/tools/patch_hud_names.py:ATO_GLYPHS`).
#    창이 12px 라 6px/자 전용 도트가 필요한데, PS1 이 이미 그려 두었다. 두 이식판이 같은
#    라벨을 다르게 그릴 이유가 없다 — 인명 자리에서 따로 풀었다가 어긋난 전례가 있다.
# ── 상태이상 라벨 — 같은 시트의 10×10 한 글자 블록들 (2026-08-24) ──────────────
# 색은 블록마다 하나뿐이다(148 빨강 = 이상, 146 노랑 = 이로움). 바탕은 0(투명), 음영 없음.
# 표기는 **PS1 과 같다**(`ps1-ed1+2:STATUS_ROW1`) — 같은 게임의 같은 라벨이다.
# ⚠ `気絶` 은 여기 없다. 0x2480 의 16×15 는 글자가 아니라 디더 무늬였다(실측).
STATUS = [
    (0x2080, "毒", "독"),
    (0x2180, "黙", "묵"),
    (0x2600, "呪", "주"),
    (0x1E80, "眠", "잠"),
    (0x1F80, "乱", "혼"),  # 정발 표기 — 음차 「란」이 아니다
    (0x2280, "守", "수"),
    (0x2380, "跳", "반"),  # 跳ね返す = 반사
]
STATUS_BOX = 10  # 10×10 · 스트라이드는 `ATO_STRIDE` 와 같다

ATO_GLYPHS = [
    [  # 남
        "#...#.",
        "#...#.",
        "#...##",
        "###.#.",
        "......",
        ".####.",
        ".#..#.",
        ".#..#.",
        ".####.",
    ],
    [  # 다
        "###.#.",
        "#...#.",
        "#...##",
        "#...#.",
        "#...#.",
        "#...#.",
        "#...#.",
        "###.#.",
        "....#.",
    ],
]

# (파일, 시작 셀, JP 이름) — 순서는 파티 순서. 시작 셀은 프레임 대조로 찾았다.
PANELS = [
    ("/SCR1.2D", 1038, "セリオス"),
    ("/SCR1.2D", 1108, "リュナン"),
    ("/SCR1.2D", 1234, "ロー"),
    ("/SCR1.2D", 1304, "ソニア"),
    ("/SCR1.2D", 1374, "ゲイル"),
    ("/SCR2.2D", 1038, "アトラス"),
    ("/SCR2.2D", 1108, "ランドー"),
    ("/SCR2.2D", 1234, "フローラ"),
    ("/SCR2.2D", 1304, "シンディ"),
]
COLS, ROWS = 14, 5
W, H = COLS * 8, ROWS * 8
NAME_X = (4, 45)  # 이름 칸 — 왼쪽 테두리(x 0~2) 다음부터, `EP` 라벨(x 47) 앞에서 끊는다
# 🔴 **자리·피치·색은 PS1 과 한 벌이다**(`ps1-ed1+2/tools/patch_hud_names.py`). 같은 게임의
#   같은 패널이라 둘이 어긋나면 안 된다. 원본도 아홉 판 전부 x 7 에서 시작한다(실측).
#   ⚠ 넉 자를 advance 10 으로 그리면 `EP` 에 닿아서 그 둘만 왼쪽으로 밀었더니 **왼 여백이
#   판마다 달라졌다**(유저 QA 2026-08-24). 피치를 9 로 좁히면 아홉이 같은 자리에 선다.
NAME_X0 = 6  # 이름 시작 x — 아홉 판 공통
PITCH = 9  # 글자 간격. 넉 자 = 36px 로 원본(x 7~41)과 같은 폭에 든다
# ⚠ 세로도 끊어야 한다 — 같은 x 대역 아래쪽에 `Lv`(y 30 언저리)가 있고, 위 두 줄(y 0~1)은
#   패널 테두리다. 그 사이만 보면 「BG 아닌 것 = 이름」이 성립한다.
NAME_Y = (2, 19)
BG = 39  # 패널 안쪽 단색 (0,0,128)
FG = 16  # 인명 노랑 (240,208,32)
SH = 46  # 그림자 (80,64,96) — PS1 과 같다. 피치 9 에서 글자끼리 붙는 걸 이게 떼어 준다
FONT = "Galmuri9"
GLYPH_H = 9
GLYPH_W = 9  # Galmuri9 한글 글리프 폭


def panel_px(cells, start):
    """셀 `start` 부터 14×5 를 화면 배치대로 → (40,112) 색인 배열."""
    blk = cells[start : start + COLS * ROWS].reshape(ROWS, COLS, 8, 8)
    return blk.transpose(0, 2, 1, 3).reshape(H, W)


def px_to_cells(px):
    a = np.asarray(px, np.uint8).reshape(ROWS, 8, COLS, 8)
    return a.transpose(0, 2, 1, 3).reshape(COLS * ROWS * 64).tobytes()


def name_band(px):
    """이름 잉크의 세로 띠 `(y0, y1)` — 편마다 4px 어긋나 있어 **매번 잰다**.

    칸 안은 `BG` 단색이라 「`BG` 가 아닌 것」이 곧 글자다. 색인 목록을 손으로 안 든다.
    """
    x0, x1 = NAME_X
    ya, yb = NAME_Y
    ink = px[ya : yb + 1, x0 : x1 + 1] != BG
    ys = np.nonzero(ink.any(1))[0]
    assert ys.size, "이름 잉크를 못 찾았다"
    y0, y1 = ya + int(ys[0]), ya + int(ys[-1])
    assert y1 - y0 + 1 <= 12, f"이름 띠가 너무 두껍다 — y {y0}~{y1} (칸을 잘못 잡았다)"
    return y0, y1


def draw(px, kr, bdf):
    """이름 칸을 지우고 한글을 그린다(그림자 먼저). 반환: (새 배열, 바뀐 화소 수).

    🔴 **그림자는 가로다**(유저 지적 2026-08-24 · 원본 실측). 원본 `セリオス` 는 글자(16)
       오른쪽 칸에만 음영(46)이 붙는다 — 세로 성분이 없다. `+1,+1` 로 깔면 대각선이라
       획이 굵어 보이고 같은 줄의 `ＨＰ`·`ＭＰ` 와도 어긋난다.
       ⚠ **PS1 도 같은 자리가 대각선이다**(`ps1-ed1+2:patch_hud_names.py`) — 거기도 고쳐야 한다.
    """
    x0, x1 = NAME_X
    y0, y1 = name_band(px)
    out = px.copy()
    out[y0 : y1 + 2, x0 : x1 + 1] = BG  # +1행 = 그림자 자리
    ya, yb = NAME_Y
    left = np.unique(out[ya : yb + 1, x0 : x1 + 1])
    assert left.tolist() == [BG], f"칸에 원문 잔재가 남았다 — 색인 {left.tolist()}"
    need = (len(kr) - 1) * PITCH + GLYPH_W
    assert NAME_X0 + need <= x1, f"이름이 칸을 넘는다: {kr!r} → x {NAME_X0 + need - 1} > {x1}"
    bits = np.zeros((GLYPH_H, need), bool)
    for i, ch in enumerate(kr):
        assert bdf.has(ch), f"{FONT} 에 없는 글자: {ch!r}"
        g = bdf.bits(ch, rows=GLYPH_H, width=GLYPH_W, dy=GLYPH_H - bdf.ascent)
        bits[:, i * PITCH : i * PITCH + GLYPH_W] |= g.astype(bool)
    ys, xs = np.nonzero(bits)
    for dx, col in ((1, SH), (0, FG)):  # 가로 음영 — 위 주석
        out[y0 + ys, NAME_X0 + xs + dx] = col
    return out, int((out != px).sum())


def box(d, off, h, w):
    """`/FRAME.DAT` 에서 (h, w) 블록을 떠 온다(스트라이드 16B)."""
    rows = [d[off + y * ATO_STRIDE : off + y * ATO_STRIDE + w] for y in range(h)]
    return np.frombuffer(b"".join(rows), np.uint8).reshape(h, w)


def box_bytes(px, d, off):
    """블록 → 파일에 쓸 연속 바이트(스트라이드 16B · 남는 열은 원본 그대로)."""
    h, w = px.shape
    buf = bytearray(d[off : off + ATO_STRIDE * h])
    for y in range(h):
        buf[y * ATO_STRIDE : y * ATO_STRIDE + w] = px[y].tobytes()
    return bytes(buf)


def draw_status(old, kr, bdf):
    """10×10 칸에 한 글자. 색은 **그 칸이 쓰던 색 하나**를 그대로 쓴다."""
    used = {int(v) for v in np.unique(old)} - {0}
    assert len(used) == 1, f"상태 라벨 색이 하나가 아니다: {sorted(used)}"
    colr = used.pop()
    n = STATUS_BOX
    out = np.zeros_like(old)
    g = bdf.bits(kr, rows=GLYPH_H, width=GLYPH_W, dy=GLYPH_H - bdf.ascent)
    oy, ox = (n - GLYPH_H) // 2, (n - GLYPH_W) // 2
    ys, xs = np.nonzero(g)
    out[oy + ys, ox + xs] = colr
    return out, int((out != old).sum())


def ato_block(d, off=ATO_OFF):
    """`あと` 블록을 (10, 12) 로 떠 온다."""
    rows = [d[off + y * ATO_STRIDE : off + y * ATO_STRIDE + ATO_W] for y in range(ATO_H)]
    return np.frombuffer(b"".join(rows), np.uint8).reshape(ATO_H, ATO_W)


def draw_ato(old):
    """`あと` 자리를 지우고 「남다」를 그린다(가로 음영, 창 밖은 자른다)."""
    out = old.copy()
    out[:] = ATO_BG
    bits = np.zeros((len(ATO_GLYPHS[0]), ATO_W), bool)
    for i, g in enumerate(ATO_GLYPHS):
        for y, row in enumerate(g):
            for x, ch in enumerate(row):
                if ch == "#":
                    bits[y, i * 6 + x] = True
    ys, xs = np.nonzero(bits)
    for dx, colr in ((1, ATO_SHADOW), (0, ATO_MAIN)):  # 가로 음영 — 위 주석
        yy, xx = ATO_TOP + ys, xs + dx
        ok = (yy < ATO_H) & (xx < ATO_W)  # 창 밖은 자른다 — 옆 스프라이트를 물지 않게
        out[yy[ok], xx[ok]] = colr
    return out, int((out != old).sum())


def ato_bytes(px, d, off=ATO_OFF):
    """(10, 12) → 파일에 쓸 연속 바이트(스트라이드 16 · 뒤 4B 는 원본 그대로)."""
    buf = bytearray(d[off : off + ATO_STRIDE * ATO_H])
    for y in range(ATO_H):
        buf[y * ATO_STRIDE : y * ATO_STRIDE + ATO_W] = px[y].tobytes()
    return bytes(buf)


def main():
    apply = "--apply" in sys.argv
    common.verify_source()
    _f, mm = common.open_image()
    files = {p: (lba, size) for p, lba, size in common.iso_files(mm)}
    bdf = galmuri(FONT)

    raw = {}
    for path in {p for p, _s, _n in PANELS} | {FRAME, STAT}:
        lba, size = files[path]
        raw[path] = common.read_extent(mm, lba, size)
    parsed = {p: dump_scr.parse(d) for p, d in raw.items() if p not in (FRAME, STAT)}

    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if apply and not os.path.exists(dst):
        raise SystemExit(f"먼저 자막을 넣는다(patch_title.py --apply) — {dst} 가 없다")

    made = []
    for path, start, jp in PANELS:
        kr = lookup(jp, "person")
        assert kr, f"고유명사 정본에 없다: {jp}"
        old = panel_px(parsed[path]["cells"], start)
        new, n = draw(old, kr, bdf)
        made.append((path, start, jp, kr, new))
        print(f"  {path} 셀{start:4d}  {jp} → {kr} · 화소 {n} 변경")
        if not apply:
            continue
        lba, size = files[path]
        off = dump_scr.cell_base(raw[path]) + start * 64
        write(dst, lba, size, off, px_to_cells(new), px_to_cells(old), f"{path} HUD 패널")

    # ── 잔량 라벨 `あと` → 남다 (파일 둘 — 위 ATO_SITES 주석)
    old_ato = ato_block(raw[FRAME])
    new_ato, n = draw_ato(old_ato)
    for path, off in ATO_SITES:
        assert np.array_equal(ato_block(raw[path], off), old_ato), f"{path} 0x{off:X}: 원본이 다르다"
        print(f"  {path} 0x{off:X}  あと → 남다 · 화소 {n} 변경")
        if not apply:
            continue
        lba, size = files[path]
        write(
            dst,
            lba,
            size,
            off,
            ato_bytes(new_ato, raw[path], off),
            raw[path][off : off + ATO_STRIDE * ATO_H],
            f"{path} 잔량 라벨",
        )

    # ── 상태이상 라벨 일곱
    stat = []
    for off, jp, kr in STATUS:
        old_s = box(raw[FRAME], off, STATUS_BOX, STATUS_BOX)
        new_s, n = draw_status(old_s, kr, bdf)
        stat.append(new_s)
        print(f"  {FRAME} 0x{off:X}  {jp} → {kr} · 화소 {n} 변경")
        if apply:
            lba, size = files[FRAME]
            write(
                dst,
                lba,
                size,
                off,
                box_bytes(new_s, raw[FRAME], off),
                raw[FRAME][off : off + ATO_STRIDE * STATUS_BOX],
                f"{FRAME} 상태 라벨 {jp}",
            )

    preview(made, parsed, new_ato, stat)
    if apply:
        verify(dst, files, made, new_ato, stat)
    else:
        print("  (미리보기만 — 실제로 넣으려면 `--apply`)")


def write(dst, lba, size, off, want, was, label):
    """⚠ 원본이거나 이미 우리 것 — 둘 다 아니면 배치가 밀린 것이다(챕터 판과 같은 규칙)."""
    with open(dst, "r+b") as f:
        cur = common.read_extent(common.open_image(dst)[1], lba, size)[off : off + len(want)]
        if cur not in (was, want):
            raise SystemExit(f"{label}: 자리가 원본도 우리 것도 아니다 @0x{off:X}")
        ns = common.write_at(f, lba, size, off, want, label=label, expect=cur)
    print(f"      → 0x{off:X} · 섹터 {ns}")


def preview(made, parsed, ato, stat):
    from PIL import Image

    os.makedirs(REVIEW, exist_ok=True)
    pal = parsed[made[0][0]]["pal"]
    sheet = np.concatenate([m[4] for m in made], 0)
    im = Image.fromarray(pal[sheet])
    p = os.path.join(REVIEW, "hud_names_kr.png")
    im.resize((im.width * 3, im.height * 3), Image.NEAREST).save(p)
    q = os.path.join(REVIEW, "hud_ato_kr.png")
    strip = np.zeros((max(ato.shape[0], STATUS_BOX), ato.shape[1] + 2 + len(stat) * 12), np.uint8)
    strip[: ato.shape[0], : ato.shape[1]] = ato
    for k, sb in enumerate(stat):
        strip[:STATUS_BOX, ato.shape[1] + 2 + k * 12 : ato.shape[1] + 2 + k * 12 + STATUS_BOX] = sb
    ia = Image.fromarray(pal[strip])
    ia.resize((ia.width * 10, ia.height * 10), Image.NEAREST).save(q)
    print(f"미리보기 → {p} · {q}")


def verify(dst, files, made, ato, stat=None):
    """되읽기 — 넣은 이미지에서 패널을 다시 뜯어 우리가 그린 것과 대조한다."""
    _f2, mm2 = common.open_image(dst)
    cache = {}
    for path, start, _jp, _kr, new in made:
        if path not in cache:
            lba, size = files[path]
            cache[path] = dump_scr.parse(common.read_extent(mm2, lba, size))
        got = panel_px(cache[path]["cells"], start)
        assert np.array_equal(got, new), f"{path} 셀{start}: 되읽기 불일치"
    for path, off in ATO_SITES:
        lba, size = files[path]
        got = ato_block(common.read_extent(mm2, lba, size), off)
        assert np.array_equal(got, ato), f"{path} 0x{off:X} 잔량 라벨: 되읽기 불일치"
    lba, size = files[FRAME]
    dfr = common.read_extent(mm2, lba, size)
    for (off, jp, _kr), want in zip(STATUS, stat or [], strict=True):
        got = box(dfr, off, STATUS_BOX, STATUS_BOX)
        assert np.array_equal(got, want), f"상태 라벨 {jp}: 되읽기 불일치"
    mm2.close()
    print(f"되읽기 확인 — HUD 패널 {len(made)}장 + 잔량 라벨 {len(ATO_SITES)}곳 + 상태 라벨 {len(stat or [])}")
    sweep(dst)


def sweep(dst):
    """🔴 **원본 그림이 어디에도 남으면 안 된다.**

    자리를 하나 고치고 「됐다」로 넘어갔다가 화면에 그대로 `あと` 가 떴다(유저 QA
    2026-08-24). 같은 스프라이트가 `/FRAME.DAT` 과 `/STAT.DAT` 둘에 있었기 때문이다.
    개별 자리의 되읽기는 **그 자리만** 보므로 이 사고를 영원히 못 잡는다 —
    그래서 넣은 이미지의 **전 파일**에서 원본 지문을 찾는다.
    """
    _f, mm0 = common.open_image()
    fr = common.extract(FRAME, mm0)
    mm0.close()
    # 지문은 **잉크가 있는 행만** 잇는다(0행은 빈 줄이라 남의 스프라이트와도 맞는다).
    sigs = {"あと": fr[ATO_OFF + ATO_STRIDE : ATO_OFF + ATO_STRIDE * ATO_H]}
    for off, jp, _kr in STATUS:
        sigs[jp] = fr[off + ATO_STRIDE : off + ATO_STRIDE * STATUS_BOX]
    _f2, mm = common.open_image(dst)
    left = []
    for name, lba, size in common.iso_files(mm):
        if not 0 < size <= 8 << 20:
            continue
        blob = common.read_extent(mm, lba, size)
        left += [f"{jp}@{name}" for jp, sig in sigs.items() if blob.find(sig) >= 0]
    mm.close()
    assert not left, f"원본 라벨이 남았다 — {left}"
    print(f"전량 훑기 — 원본 라벨 {len(sigs)}종 잔존 0")


if __name__ == "__main__":
    main()
