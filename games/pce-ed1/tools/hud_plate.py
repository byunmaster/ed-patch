"""HUD 글자판(A6) — 이름판 다섯 · 「あと」 · 상태 한자 일곱을 한글로 다시 그린다.

## 자리와 구조 (실측, 2026-09-26 — devlog 09-26 (2))

🔴 **HUD 는 스프라이트가 아니라 BG 타일이다**(09-15 기록의 「스프라이트」는 오진).
데이터 트랙 **rel 55 +0x32C, 1,013B** 가 **압축 묶음 하나**이고, 파일을 불러올 때 VRAM `$4000`
(타일 0x400~0x46F, 0x70개)으로 풀린다. 코덱은 `hud_lz.py`(텍스트 LZ 와 다르다).
⚠ 묶음 바로 뒤(`$8F21`)가 다음 서술자의 소스다 — **새 압축본이 1,013B 를 넘으면 안 된다.**

    타일(묶음 안 번호)  무엇
    0x00~0x0F           틀 조각 · 숫자
    0x10·0x11           「あと」(경험치표시 = 남다 일 때 EP 자리)
    0x12~0x19           HP · MP · EP · LV · /
    0x1A~0x39           상태 한자 여섯(眠乱毒黙守跳, 2×2) · 気絶(4×2, 0x22~0x29)
    0x3A~0x68           이름판 다섯(6×2)

**배치표**(BAT 스크립트)는 뱅크 0x6D = **rel 54 +0x761~** 에 무압축이다.
`ff <VRAM 주소 LE> <타일…> fe <타일…> …` — 칸 값은 **묶음 안 타일 번호**(하위 바이트, 팔레트·상위는 코드가 붙인다).
이름판 한 줄은 6칸 고정이라 **길이를 안 바꾸고 값만** 고친다.

🔴 **HUD 판은 스프라이트로 한 벌 더 덮인다**(2026-09-26 실측 — BG 만 고쳤더니 화면은 그대로였다,
BG 층만 켜면 한글이 보였다). 32×64 스프라이트 9장이 판 전체(바탕·틀·이름·라벨·숫자)를 다시 그린다.
그 글자 조각은 **뱅크 0x77 = rel 94~97 무압축**에 16×8 **조각**(64B = 평면 넷 × 8워드)으로 있고,
`$7DD5` 가 인라인 인자로 받은 **조각 번호 목록**(주소 = `$AFE1 + 번호×64`)을 VRAM `$7000`대로 옮긴다.
이름판 목록은 rel 55 에 무압축(판마다 6칸: 윗줄 3 · 아랫줄 3). 빈 조각은 공용이다 — 윗줄 07 · 아랫줄 03.
색은 BG 와 다르다: 바탕 1→8 · 틀 14→2 · 노랑 13→6 · 빨강 5→10 · 하늘 11→4.
"""

import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared"))

import canon  # shared/ — 공통 문안 정본(ED1 = PS1 씨앗)
import common
import hud_lz

from shared import fonts

BLOCK_REL = 55
BLOCK_OFF = 0x32C
BLOCK_LEN = 1013  # 원본 압축본 길이 = 상한
BANK_BLOCK_OFF = 0x800 + BLOCK_OFF  # 뱅크 0x6D 안 오프셋(rel 54 가 뱅크 첫 섹터)
NTILES = 0x70
BAT_REL = 54  # 뱅크 0x6D 첫 섹터
BAT_OFF = 0x761

# BG 팔레트 8 (미리보기 전용 — 세션 에뮬 pram 실측, 09-26)
PAL8 = [
    (0, 0, 0),
    (0, 0, 108),
    (144, 108, 0),
    (0, 0, 252),
    (0, 0, 0),
    (252, 36, 36),
    (0, 0, 0),
    (108, 72, 0),
    (0, 0, 0),
    (0, 252, 0),
    (0, 0, 0),
    (108, 252, 252),
    (0, 0, 0),
    (252, 252, 36),
    (252, 252, 252),
    (252, 252, 252),
]

def _person(jp: str) -> str:
    kr = canon.lookup(jp, "person", "ed1")
    assert kr, f"사전에 인물 {jp!r} 가 없다"
    return kr


def _ui(jp: str, fallback: str | None = None) -> str:
    kr = canon.lookup(jp, "ui", "ed1")
    if kr is not None:
        return kr
    assert fallback, f"정본 ui 에 {jp!r} 가 없다"
    return fallback


# 이름판: (배치표 안 오프셋, 원문, 한글) — 오프셋은 `ff` 바이트 자리(rel 54 기준). 한글은 **사전(person)에서 읽는다**(마스터 10-08)
PLATES = [
    (0x760, "セリオス", _person("セリオス")),
    (0x783, "リュナン", _person("リュナン")),
    (0x7A6, "ロー", _person("ロー")),
    (0x7C9, "ゲイル", _person("ゲイル")),
    (0x7EC, "ソニア", _person("ソニア")),
]
# 상태 한자: (타일 줄들, 원문, 한글) — PS1 `patch_sys_ui.STATUS_LABELS` · 새턴 `patch_gfx_hud.STATUS` 선례.
# 한글은 정본 ui 에서 읽는다 — 정본에 아직 없는 셋(守 跳 気絶)은 **정본 후보**라 값을 여기 둔다(관리자에게 올림, 10-08)
STATUS = [
    ([[0x1A, 0x1B], [0x1C, 0x1D]], "眠", _ui("眠")),
    ([[0x1E, 0x1F], [0x20, 0x21]], "乱", _ui("乱")),
    ([[0x2A, 0x2B], [0x2C, 0x2D]], "毒", _ui("毒")),
    ([[0x2E, 0x2F], [0x30, 0x31]], "黙", _ui("黙")),
    ([[0x32, 0x33], [0x34, 0x35]], "守", _ui("守")),
    (
        [[0x36, 0x37], [0x38, 0x39]],
        "跳",
        _ui("跳"),
    ),  # 跳ね返す = 반사(PS1 정발 표기) — PCE 엔 「呪」가 없다
    ([[0x26, 0x27, 0x22, 0x23], [0x28, 0x29, 0x24, 0x25]], "気絶", _ui("気絶")),
]
ATO = ([[0x10, 0x11]], "あと")

# 스프라이트 쪽
SPR_REL = 94  # 뱅크 0x77 (4섹터)
SPR_BASE = 0xFE1  # 조각 0 의 뱅크 안 오프셋
SPR_COLOR = {1: 8, 14: 2, 13: 6, 5: 10, 11: 4}
SPR_BLANK_TOP, SPR_BLANK_BOT = 0x07, 0x03  # 공용 빈 조각(윗줄 · 아랫줄)
# 이름판 조각 목록(rel 55 안 오프셋) — PLATES 와 같은 순서
SPR_LISTS = [0x1FF, 0x225, 0x297, 0x271, 0x24B]


# ── 묶음 ───────────────────────────────────────────────────────────────────


def block_sector(img=None):
    return common.track_data(BLOCK_REL, 1) if img is None else img


def tiles(sector=None):
    """묶음을 풀어 VRAM 배치 타일 0x70개(각 32B)."""
    sec = block_sector(sector)
    raw, end = hud_lz.decode(sec, BLOCK_OFF, NTILES * 32)
    assert end - BLOCK_OFF == BLOCK_LEN, f"압축본 길이가 {end - BLOCK_OFF}B — 원본이 아니다?"
    return [hud_lz.planar_to_vram(raw[i : i + 32]) for i in range(0, len(raw), 32)]


def tile_px(t):
    """VRAM 타일 32B → (8,8) 색 번호."""
    a = np.zeros((8, 8), dtype=np.uint8)
    for y in range(8):
        for x in range(8):
            b = 7 - x
            a[y, x] = (
                ((t[2 * y] >> b) & 1)
                | (((t[2 * y + 1] >> b) & 1) << 1)
                | (((t[16 + 2 * y] >> b) & 1) << 2)
                | (((t[17 + 2 * y] >> b) & 1) << 3)
            )
    return a


def px_tile(a):
    t = bytearray(32)
    for y in range(8):
        for x in range(8):
            c, b = int(a[y, x]), 7 - x
            t[2 * y] |= (c & 1) << b
            t[2 * y + 1] |= ((c >> 1) & 1) << b
            t[16 + 2 * y] |= ((c >> 2) & 1) << b
            t[17 + 2 * y] |= ((c >> 3) & 1) << b
    return bytes(t)


def grid(ts, rows):
    """타일 번호 줄들 → 한 장의 색 번호 배열."""
    return np.vstack([np.hstack([tile_px(ts[t]) for t in r]) for r in rows])


# ── 배치표 ─────────────────────────────────────────────────────────────────


def bat_sector():
    return common.track_data(BAT_REL, 1)


def plate_rows(sec, off):
    """`ff lo hi` 뒤 두 줄 6칸씩."""
    assert sec[off] == 0xFF, f"{off:#x} 가 배치표 머리가 아니다"
    top = list(sec[off + 3 : off + 9])
    assert sec[off + 9] == 0xFE
    bot = list(sec[off + 10 : off + 16])
    return [top, bot]


# ── 조판 ───────────────────────────────────────────────────────────────────


def _em_rows(font_name):
    """그 글꼴의 한글 세로 칸(윗줄, 아랫줄) — 받침 있는 「한」의 잉크로 잰다."""
    g = fonts.galmuri(font_name).bits("한", rows=24, width=24, dy=4)
    ys = np.nonzero(g)[0]
    return int(ys.min()), int(ys.max())


def ink(font_name, ch):
    """글리프를 (h, w) 0/1 로 — **가로는 잉크로 자르고 세로는 글꼴의 한글 칸 그대로** 둔다.

    ⚠ 세로까지 잉크로 자르면 안 된다(마스터 지적 2026-09-26) — 갈무리9 는 모든 음절의 윗줄이
    같고, 받침 없는 ㅗ·ㅡ 계열(오·스·로·소)만 아랫줄이 한 줄 짧다. 잉크 아랫줄을 맞추면 그 글자들이
    **1px 내려앉는다**(「세리오스」의 「오스」). 글꼴이 정한 세로 자리를 지킨다.
    """
    f = fonts.galmuri(font_name)
    g = f.bits(ch, rows=24, width=24, dy=4)
    ys, xs = np.nonzero(g)
    if not len(xs):
        return np.zeros((1, 1), dtype=np.uint8)
    top, bot = _em_rows(font_name)
    assert top <= ys.min() and ys.max() <= bot, f"「{ch}」가 한글 칸({top}~{bot}행) 밖으로 나간다"
    return g[top : bot + 1, xs.min() : xs.max() + 1]


def set_text(canvas, text, font_name, x0, y_base, color, pitch=None, gap=1):
    """글자를 왼쪽부터 놓는다 — 가로는 잉크 기준, 세로는 글꼴의 한글 칸 아랫줄을 y_base 에. pitch 가 없으면 잉크폭+gap."""
    x = x0
    for ch in text:
        g = ink(font_name, ch)
        h, w = g.shape
        ox = x + ((pitch - w) // 2 if pitch else 0)
        for yy in range(h):
            for xx in range(w):
                if g[yy, xx]:
                    canvas[y_base - h + 1 + yy, ox + xx] = color
        x += pitch if pitch else w + gap
    return x


def blank_like(a, bg, keep):
    """keep(색 번호 집합)만 남기고 나머지를 bg 로 — 틀은 두고 글자만 지운다."""
    out = a.copy()
    out[~np.isin(out, list(keep))] = bg
    return out


# ── 미리보기 ───────────────────────────────────────────────────────────────


def to_rgb(a, scale=4):
    im = Image.fromarray(np.array([[PAL8[c] for c in row] for row in a], dtype=np.uint8), "RGB")
    return im.resize((im.width * scale, im.height * scale), Image.NEAREST)


def sheet(pairs, path, scale=4, gap=6):
    """(원문 배열, 한글 배열) 목록 → 좌우로 놓은 한 장."""
    ims = [(to_rgb(a, scale), to_rgb(b, scale)) for a, b in pairs]
    w = max(a.width + gap * scale + b.width for a, b in ims)
    h = sum(max(a.height, b.height) + gap * scale for a, b in ims)
    out = Image.new("RGB", (w, h), (40, 40, 40))
    y = 0
    for a, b in ims:
        out.paste(a, (0, y))
        out.paste(b, (a.width + gap * scale, y))
        y += max(a.height, b.height) + gap * scale
    out.save(path)
    return path


# ── 스프라이트 조각 ─────────────────────────────────────────────────────────


def spr_bank():
    return common.track_data(SPR_REL, 4)


def to_piece(blk):
    """(8,16) BG 색 번호 → 스프라이트 조각 64B(평면 넷 × 8워드, LE)."""
    out = bytearray()
    for pl in range(4):
        for y in range(8):
            w = 0
            for x in range(16):
                if (SPR_COLOR[int(blk[y, x])] >> pl) & 1:
                    w |= 1 << (15 - x)
            out += bytes((w & 0xFF, w >> 8))
    return bytes(out)


def piece_off(i):
    return SPR_BASE + i * 64


def split_pieces(a):
    """(h, w) → [[조각 64B …] …] (행 8px · 열 16px)."""
    return [
        [to_piece(a[r : r + 8, c : c + 16]) for c in range(0, a.shape[1], 16)]
        for r in range(0, a.shape[0], 8)
    ]


def find_unique(bank, piece, what):
    i = bank.find(piece)
    assert i >= 0 and bank.find(piece, i + 1) < 0, f"스프라이트 조각을 하나로 못 짚는다 — {what}"
    return i


# ── 레벨 라벨 「LV」→「Lv」 (마스터 10-10: PS1 HUD 표기 그대로) ─────────────────────────────────────
# BG 타일 0x18(「L」 밑줄 둘 + 「V」) 과 스프라이트 조각 12(16×8 — 「LV」 한 장)를 같이 고친다. 「V」 는 5열 × 7행(열 3~7)이라
# 그 칸을 비우고 **소문자 v**(4행 · 열 3~7)를 아랫줄에 앉힌다. 「L」 은 그대로.
LV_TILE = 0x18
LV_PIECE = 12
LV_V_COL0 = 3  # 타일 안 「V」 첫 열
LV_V_SPR_COL0 = 11  # 조각 안 「V」 첫 열
LV_INK, LV_BG = 11, 1  # BG 색 번호(하늘 · 바탕)
LV_SMALL_V = [(3, 0), (3, 4), (4, 1), (4, 3), (5, 1), (5, 3), (6, 2)]  # (행, 「v」 안 열)


def piece_px(b):
    """스프라이트 조각 64B → (8,16) BG 색 번호 — `to_piece` 의 역."""
    inv = {v: k for k, v in SPR_COLOR.items()}
    a = np.zeros((8, 16), dtype=np.uint8)
    for y in range(8):
        for x in range(16):
            c = 0
            for pl in range(4):
                w = b[pl * 16 + y * 2] | (b[pl * 16 + y * 2 + 1] << 8)
                c |= ((w >> (15 - x)) & 1) << pl
            a[y, x] = inv[c]
    return a


def lv_lower(a, col0):
    """「V」 칸(열 col0..col0+4)을 비우고 소문자 「v」 를 그린다."""
    a = a.copy()
    a[0:7, col0 : col0 + 5] = LV_BG
    for r, c in LV_SMALL_V:
        a[r, col0 + c] = LV_INK
    return a


# ── 한글 그리기 ─────────────────────────────────────────────────────────────

NAME_FONT = (
    "Galmuri9"  # ⏳ 판정 대기 9-⑴ — 원문 글자 9~10px 에 가깝다(갈무리11 안은 판을 꽉 채운다)
)
NAME_BASE = 13  # 아랫선 행(원문 잉크 4~14 안)
# 원문 첫 잉크 열은 4 — 갈무리11 「세리오스」(잉크 42 + 사이 3 = 45px)가 47열 안에 들도록 한 칸 당긴다
NAME_X = 3
STATUS_FONT = "Galmuri11"
STATUS_BASE = 14
ATO_FONT = "Galmuri7"  # 원문 あと 잉크 7행(0~6)
ATO_BASE = 6
ATO_X = 2
ATO_GAP = 0  # 7px 두 글자(7+7)가 열 1~15 안에 들려면 붙여야 한다(사이 1 이면 16열)


def ink_color(a, frame):
    """틀·바탕 말고 쓰인 색(글자 색)."""
    cs = [c for c in np.unique(a) if c not in frame]
    return int(cs[0]) if cs else None


def draw_plate(orig, text):
    """이름판 48×16: 틀(행0·열0 = 14)과 바탕(1)을 두고 글자만 새로."""
    col = ink_color(orig, {1, 14})
    out = blank_like(orig, 1, {14})
    set_text(out, text, NAME_FONT, NAME_X, NAME_BASE, col)
    return out


def draw_status(orig, text):
    col = ink_color(orig, {1, 14})
    out = blank_like(orig, 1, {14})
    w = sum(ink(STATUS_FONT, c).shape[1] for c in text) + (len(text) - 1)
    set_text(out, text, STATUS_FONT, (out.shape[1] - w) // 2, STATUS_BASE, col)
    return out


NAMDA_DOTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "assets", "graphics", "namda.txt"
)


def load_dots(path):
    """마스터 도트판(`#`/`.`) → (8,16) 0/1. 0열은 판 테두리 자리라 비어 있어야 한다."""
    with open(path, encoding="utf-8") as fh:
        rows = [ln.rstrip("\n") for ln in fh if ln.strip()]
    assert len(rows) == 8 and all(len(r) == 16 and set(r) <= {"#", "."} for r in rows), (
        f"{path}: 8줄×16칸 #/. 가 아니다"
    )
    a = np.array([[c == "#" for c in r] for r in rows], dtype=np.uint8)
    assert not a[:, 0].any(), f"{path}: 0열(테두리)에 점이 있다"
    return a


def draw_ato(orig, text):
    """「あと」 자리 16×8. **「남다」는 마스터 도트가 정본**(2026-09-26, 갈무리7 판을 대체) — 그 밖의 말은 글꼴로."""
    col = ink_color(orig, {1, 14})
    out = orig.copy()
    out[:, 1:] = 1
    if text == "남다":
        out[load_dots(NAMDA_DOTS)[:, :] == 1] = col
    else:
        set_text(out, text, ATO_FONT, ATO_X, ATO_BASE, col, gap=ATO_GAP)
    return out


ATO_WORD = "남다"  # 경험치표시 값(`あと@경험치표시`)과 같은 말 — PS1 도 정발을 따라 「남다」(마스터 확인 09-26)


def preview(path, ato_word=ATO_WORD, name_font=None):
    global NAME_FONT, NAME_BASE
    if name_font:
        NAME_FONT, NAME_BASE = name_font, (13 if name_font == "Galmuri9" else 14)
    ts, bs = tiles(), bat_sector()
    pairs = []
    for off, _jp, kr in PLATES:
        a = grid(ts, plate_rows(bs, off))
        pairs.append((a, draw_plate(a, kr)))
    for rows, _jp, kr in STATUS:
        a = grid(ts, rows)
        pairs.append((a, draw_status(a, kr)))
    a = grid(ts, ATO[0])
    pairs.append((a, draw_ato(a, ato_word)))
    return sheet(pairs, path)


# ── 굽기 ───────────────────────────────────────────────────────────────────

FRAME_TILES = {
    0x00,
    0x01,
    0x02,
    0x03,
}  # 틀 모서리 · 윗줄 · 왼줄 · 빈칸 — 이름판에서 그대로 빌려 쓴다


def build(sector=None, bat=None, spr=None):
    """(새 묶음 섹터, 새 배치표 섹터, 요약). 원본 섹터 둘을 받아 한글판을 낸다.

    이름판은 **타일을 다시 배정한다** — 원문은 판끼리 타일을 나눠 썼고(류난·소니아의 0x47,
    글자 없는 칸의 윗줄 0x01), 한글은 글자 자리가 달라 그대로 못 쓴다. 다섯 판이 원래 쓰던
    타일(틀 넷 제외)을 **풀**로 삼아, 한글 판을 8×8 로 잘라 같은 것은 합치고 틀과 같은 칸은
    틀 타일을 가리킨다. 배치표는 **길이를 안 바꾸고 값만** 고친다.
    """
    sec = bytearray(block_sector(sector))
    bsec = bytearray(bat if bat is not None else bat_sector())
    obank = spr if spr is not None else spr_bank()
    bank = bytearray(obank)
    ts = [bytearray(t) for t in tiles(bytes(sec))]
    orig_ts = [bytes(t) for t in ts]

    # 레벨 라벨 「LV」→「Lv」 — BG 타일 · 스프라이트 조각을 같이(원본 모양을 확인하고 고친다)
    lv_o = tile_px(orig_ts[LV_TILE])
    assert lv_o[0, LV_V_COL0] == LV_INK and lv_o[6, LV_V_COL0 + 2] == LV_INK, "LV 타일이 원본이 아니다"
    ts[LV_TILE] = bytearray(px_tile(lv_lower(lv_o, LV_V_COL0)))
    lv_p = bytes(obank[piece_off(LV_PIECE) : piece_off(LV_PIECE) + 64])
    lv_pa = piece_px(lv_p)
    assert to_piece(lv_pa) == lv_p and lv_pa[0, LV_V_SPR_COL0] == LV_INK, "LV 조각이 원본이 아니다"
    bank[piece_off(LV_PIECE) : piece_off(LV_PIECE) + 64] = to_piece(lv_lower(lv_pa, LV_V_SPR_COL0))

    # 상태 글자 · あと — 제자리
    for rows, _jp, kr in STATUS:
        a = draw_status(grid(orig_ts, rows), kr)
        for r, row in enumerate(rows):
            for c, t in enumerate(row):
                ts[t] = bytearray(px_tile(a[r * 8 : r * 8 + 8, c * 8 : c * 8 + 8]))
    a = draw_ato(grid(orig_ts, ATO[0]), ATO_WORD)
    for c, t in enumerate(ATO[0][0]):
        ts[t] = bytearray(px_tile(a[:, c * 8 : c * 8 + 8]))

    # 스프라이트 쪽 상태 글자 · あと — 원문 조각을 찾아 제자리에
    for rows, jp, kr in STATUS + [(ATO[0], ATO[1], ATO_WORD)]:
        o, n = grid(orig_ts, rows), None
        n = draw_ato(o, kr) if rows is ATO[0] else draw_status(o, kr)
        for orow, nrow in zip(split_pieces(o), split_pieces(n), strict=True):
            for op, np_ in zip(orow, nrow, strict=True):
                i = find_unique(obank, op, jp)
                bank[i : i + 64] = np_

    # 스프라이트 쪽 이름판 — 조각 번호 목록을 다시 짠다(BG 와 같은 까닭)
    lists = [list(sec[o : o + 6]) for o in SPR_LISTS]
    blanks = {
        bytes(obank[piece_off(SPR_BLANK_TOP) : piece_off(SPR_BLANK_TOP) + 64]): SPR_BLANK_TOP,
        bytes(obank[piece_off(SPR_BLANK_BOT) : piece_off(SPR_BLANK_BOT) + 64]): SPR_BLANK_BOT,
    }
    # 풀: 판 목록에만 나오는 조각(공용 빈 조각과, 다른 데서도 쓸지 모르는 로우의 02·05 는 뺀다)
    spool = sorted({i for li in lists for i in li} - {SPR_BLANK_TOP, SPR_BLANK_BOT, 0x02, 0x05})
    sfree, sgiven = list(spool), {}

    # 이름판 — 풀에서 다시 배정
    plates = [(off, plate_rows(bsec, off), kr) for off, _jp, kr in PLATES]
    pool = sorted({t for _o, rows, _k in plates for r in rows for t in r} - FRAME_TILES)
    frames = {bytes(orig_ts[t]): t for t in sorted(FRAME_TILES)}
    given, free = {}, list(pool)
    for off, rows, kr in plates:
        a = draw_plate(grid(orig_ts, rows), kr)
        new_rows = []
        for r in range(2):
            row = []
            for c in range(6):
                tb = px_tile(a[r * 8 : r * 8 + 8, c * 8 : c * 8 + 8])
                if tb in frames:
                    t = frames[tb]
                elif tb in given:
                    t = given[tb]
                else:
                    if not free:
                        raise ValueError(f"이름판 타일 풀({len(pool)})이 모자란다 — {kr}")
                    t = given[tb] = free.pop(0)
                    ts[t] = bytearray(tb)
                row.append(t)
            new_rows.append(row)
        bsec[off + 3 : off + 9] = bytes(new_rows[0])
        bsec[off + 10 : off + 16] = bytes(new_rows[1])
        # 스프라이트
        k = PLATES.index(next(p for p in PLATES if p[0] == off))
        ids = []
        for prow in split_pieces(a):
            for pc in prow:
                if pc in blanks:
                    ids.append(blanks[pc])
                elif pc in sgiven:
                    ids.append(sgiven[pc])
                else:
                    if not sfree:
                        raise ValueError(f"스프라이트 조각 풀({len(spool)})이 모자란다 — {kr}")
                    i = sgiven[pc] = sfree.pop(0)
                    bank[piece_off(i) : piece_off(i) + 64] = pc
                    ids.append(i)
        sec[SPR_LISTS[k] : SPR_LISTS[k] + 6] = bytes(ids)
    for t in free:  # 남는 풀 타일은 빈칸으로 (압축이 줄고, 옛 가나가 남지 않는다)
        ts[t] = bytearray(orig_ts[0x03])

    raw = b"".join(hud_lz.vram_to_planar(bytes(t)) for t in ts)
    enc = hud_lz.encode(raw)
    if len(enc) > BLOCK_LEN:
        raise ValueError(f"압축본 {len(enc)}B > 자리 {BLOCK_LEN}B — 뒤 서술자의 소스를 덮는다")
    back, _ = hud_lz.decode(enc + bytes(4), 0, len(raw))
    assert back == raw, "인코더 왕복 불일치"
    sec[BLOCK_OFF : BLOCK_OFF + BLOCK_LEN] = enc + bytes(BLOCK_LEN - len(enc))
    used = len(pool) - len(free)
    sused = len(spool) - len(sfree)
    info = f"압축 {len(enc)}/{BLOCK_LEN}B · 이름판 타일 {used}/{len(pool)} · 스프라이트 조각 {sused}/{len(spool)}"
    global _LAST_LEN
    _LAST_LEN = len(enc)
    return bytes(sec), bytes(bsec), bytes(bank), info


_LAST_LEN = None


def compressed_len() -> int:
    """새 압축본 길이 — 꼬리 빈 공간(freespace)의 시작을 정한다."""
    if _LAST_LEN is None:
        build()
    return _LAST_LEN


def apply(f, touched):
    """ISO 에 제자리 되쓰기. `build.py` 가 부른다.

    ⚠ 두 섹터 다 **프로그램 뱅크 0x6D** 안이라 다른 코드 패치와 같은 섹터를 쓸 수 있다 —
    섹터 통째가 아니라 **바꾸는 범위만**(묶음 1,013B · 판마다 두 줄 6B) 원본 사전조건을 걸고 쓴다.
    """
    from shared.disc import mode1

    osec, obat, ospr = block_sector(), bat_sector(), spr_bank()
    sec, bsec, spr, info = build(osec, obat, ospr)
    # ⚠ 묶음 꼬리(실측 범위)는 빈 공간 ⓑ 라 시스템 문구가 쓴다 — 여기선 그 앞까지만(한 바이트는 한 패치만 쓴다)
    import freespace

    own = max(compressed_len() + 1, freespace.MEASURED_HUD_TAIL)
    spans = [(BLOCK_REL, BLOCK_OFF, own, sec, osec, "HUD 글자판 묶음")]
    for o in SPR_LISTS:
        spans.append((BLOCK_REL, o, 6, sec, osec, "HUD 스프라이트 조각 목록"))
    for i in range(SPR_BASE, len(spr) - 63, 64):  # 바뀐 조각(64B)만
        if spr[i : i + 64] != ospr[i : i + 64]:
            spans.append((SPR_REL, i, 64, spr, ospr, "HUD 스프라이트 조각"))
    assert spr[:SPR_BASE] == ospr[:SPR_BASE], "조각 영역 앞을 건드렸다"
    for off, _jp, kr in PLATES:
        for o in (off + 3, off + 10):
            spans.append((BAT_REL, o, 6, bsec, obat, f"HUD 이름판 배치표 {kr}"))
    for rel, o, n, new, old, label in spans:
        lba = common.T2_SECTOR + rel
        size = common.USER * (4 if rel == SPR_REL else 1)
        mode1.write_at(
            f, lba, size, o, new[o : o + n], label=f"{label} rel {rel}", expect=old[o : o + n]
        )
        touched.append((lba + o // common.USER, 1))
    return f"HUD 글자판 rel {BLOCK_REL}·{BAT_REL}·{SPR_REL}~{SPR_REL + 3}: {info}"


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "hud_preview.png"
    print(preview(out, *(sys.argv[2:4] or [])))
