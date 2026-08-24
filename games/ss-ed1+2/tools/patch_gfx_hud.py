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
    """이름 칸을 지우고 한글을 그린다(그림자 +1,+1 먼저). 반환: (새 배열, 바뀐 화소 수)."""
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
    for dy, dx, col in ((1, 1, SH), (0, 0, FG)):
        out[y0 + ys + dy, NAME_X0 + xs + dx] = col
    return out, int((out != px).sum())


def main():
    apply = "--apply" in sys.argv
    common.verify_source()
    _f, mm = common.open_image()
    files = {p: (lba, size) for p, lba, size in common.iso_files(mm)}
    bdf = galmuri(FONT)

    raw = {}
    for path in {p for p, _s, _n in PANELS}:
        lba, size = files[path]
        raw[path] = common.read_extent(mm, lba, size)
    parsed = {p: dump_scr.parse(d) for p, d in raw.items()}

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
        want, was = px_to_cells(new), px_to_cells(old)
        with open(dst, "r+b") as f:
            # ⚠ 원본이거나 이미 우리 것 — 둘 다 아니면 배치가 밀린 것이다(챕터 판과 같은 규칙).
            cur = common.read_extent(common.open_image(dst)[1], lba, size)[off : off + len(want)]
            if cur not in (was, want):
                raise SystemExit(f"{path} 셀{start}: 패널 자리가 원본도 우리 것도 아니다")
            ns = common.write_at(f, lba, size, off, want, label=f"{path} HUD 패널", expect=cur)
        print(f"      → 0x{off:X} · 섹터 {ns}")
    preview(made, parsed)
    if apply:
        verify(dst, files, made)
    else:
        print("  (미리보기만 — 실제로 넣으려면 `--apply`)")


def preview(made, parsed):
    from PIL import Image

    os.makedirs(REVIEW, exist_ok=True)
    pal = parsed[made[0][0]]["pal"]
    sheet = np.concatenate([m[4] for m in made], 0)
    im = Image.fromarray(pal[sheet])
    p = os.path.join(REVIEW, "hud_names_kr.png")
    im.resize((im.width * 3, im.height * 3), Image.NEAREST).save(p)
    print(f"미리보기 → {p}")


def verify(dst, files, made):
    """되읽기 — 넣은 이미지에서 패널을 다시 뜯어 우리가 그린 것과 대조한다."""
    _f2, mm2 = common.open_image(dst)
    cache = {}
    for path, start, _jp, _kr, new in made:
        if path not in cache:
            lba, size = files[path]
            cache[path] = dump_scr.parse(common.read_extent(mm2, lba, size))
        got = panel_px(cache[path]["cells"], start)
        assert np.array_equal(got, new), f"{path} 셀{start}: 되읽기 불일치"
    mm2.close()
    print(f"되읽기 확인 — HUD 패널 {len(made)}장")


if __name__ == "__main__":
    main()
