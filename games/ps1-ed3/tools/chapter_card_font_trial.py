"""序章 카드 글꼴 시험 — **정본이 아니다**. 재현용으로만 남긴다.

    python3 tools/chapter_card_font_trial.py --compare   # 원문·neodgm16·Galmuri14 석 줄 PNG

## 왜 이 파일이 있나 (2026-09-15)

序章 카드(`M01.DAT!DATA5.BIN[11]`)를 처음 구울 때 neodgm 16px 를 썼는데, 마스터가
「글자가 납작하다」고 지적했다. 재 보니 **원문 한자는 잉크 15행인데 neodgm 16px 의 한글
글리프는 13행뿐**이었다(em 은 16 이어도 한글이 그 안을 다 안 채운다). 더 키우면(18·20px)
계단(회색)이 55~59% 로 뭉갠다 — 이 글꼴에서 16px 위는 못 쓴다.

대안으로 `shared/fonts` 의 갈무리 BDF 를 전부 재서 **Galmuri14 가 14행**(원문 안 넘으면서
가장 가깝다, 비트맵이라 계단 0%)임을 확인했다. 석 줄 비교 PNG 를 마스터께 올렸는데
**마스터가 그래도 neodgm 을 골랐다**(「네오둥근모로 구워줘봐」, 09-15 — ps1-ed1+2 카드와
글꼴이 같아지는 쪽을 택함). ⇒ **정본은 neodgm 16px**(`assets/graphics/ed3/chapter_prologue.png`
+ `graphics_ed3.json`[11] `file`)이고, 이 파일은 **Galmuri14 로 되돌리고 싶어지면 다시
재는 수고를 안 하도록** 재현 경로만 남긴 것이다 — `graphics_ed3.json` 에는 안 걸려 있다.

## 실측값 (재판정 없이 그대로 씀)

| 글꼴 | 잉크 세로 | 계단(회색) | 비고 |
| --- | --- | --- | --- |
| 원문 한자(`序章　小さな巡礼者`) | 15행 | — | `M01.DAT!DATA5.BIN[11]` 실측 |
| **neodgm 16px(정본)** | **13행** | 0% | 채택 |
| neodgm 18px | 16행 | 59% | 계단 뭉갬, 기각 |
| neodgm 20px | 17행 | 55% | 계단 뭉갬, 기각 |
| Galmuri11 | 11행 | 0% | 원문과 더 멀다 |
| Galmuri14 | 14행 | 0% | **14행으로 최선이었으나 미채택** |
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import gmfz
import tim


def _parse_bdf(path):
    """BDF → `{코드포인트: {bbx, dwidth, rows}}`, ascent. `shared/fonts.load_bdf` 는 DWIDTH 를
    안 담아(고정 격자 굽기용이라 필요 없었다) 자유 위치 렌더에 쓰려고 따로 읽는다."""
    glyphs, ascent = {}, None
    with open(path, encoding="utf-8", errors="replace") as f:
        cp = bbx = dwidth = rows = None
        in_bitmap = False
        for line in f:
            t = line.split()
            if not t:
                continue
            if t[0] == "FONT_ASCENT":
                ascent = int(t[1])
            elif t[0] == "ENCODING":
                cp = int(t[1])
            elif t[0] == "DWIDTH":
                dwidth = int(t[1])
            elif t[0] == "BBX":
                bbx = tuple(int(v) for v in t[1:5])
            elif t[0] == "BITMAP":
                rows = []
                in_bitmap = True
            elif t[0] == "ENDCHAR":
                if cp is not None and cp >= 0 and bbx:
                    glyphs[cp] = {"bbx": bbx, "dwidth": dwidth, "rows": rows or []}
                cp = bbx = dwidth = rows = None
                in_bitmap = False
            elif in_bitmap:
                rows.append(int(t[0], 16))
    return glyphs, ascent


def render_bdf_line(path, text, color):
    """(투명 캔버스, (잉크 top, 잉크 bottom)) — `DWIDTH` 로 글자마다 칸을 밀며 한 줄에 얹는다."""
    from PIL import Image

    glyphs, ascent = _parse_bdf(path)
    cells = [(ch, glyphs.get(ord(ch))) for ch in text]
    total_w = sum((g["dwidth"] if g else 8) for _, g in cells)
    h = ascent + 4
    canvas = Image.new("RGBA", (total_w + 4, h), (0, 0, 0, 0))
    px = canvas.load()
    x0 = 0
    top, bot = 10**9, -1
    for _ch, g in cells:
        if g is None:
            x0 += 8
            continue
        w, gh, xo, yo = g["bbx"]
        nbits = ((w + 7) // 8) * 8
        for r, v in enumerate(g["rows"]):
            y = ascent - (yo + gh) + r
            if not 0 <= y < h:
                continue
            for x in range(w):
                if v & (1 << (nbits - 1 - x)):
                    xx = x0 + xo + x
                    if 0 <= xx < canvas.width:
                        px[xx, y] = color
                        top, bot = min(top, y), max(bot, y)
        x0 += g["dwidth"]
    return canvas, (top, bot)


def _card_image(disc="ed3", path_override=None):
    """현재 序章 카드 그림(RGBA) — `path_override` 로 originals 대신 특정 빌드를 볼 수 있다."""
    for path, (lba, size) in sorted(common.iso_files(disc).items()):
        if path == "/M01.DAT":
            data = common.read_lba(disc, lba, size, path=path_override)
            break
    try:
        raw, _ = gmfz.decompress(data)
        raw = bytes(raw)
    except Exception:  # noqa: BLE001 — 안 눌린 멤버가 더 많다
        raw = data
    _, ents = common.arc_parse(data)
    for nm, off, sz in ents:
        if nm.endswith("DATA5.BIN"):
            blob = bytes(data[off : off + sz])
            break
    ts = tim.find_all(blob)
    _, t = ts[11]
    return tim.to_image(t).convert("RGBA")


GREEN = (24, 132, 24, 255)
TEXT = "서장　작은 순례자"


def make_candidate(bdf_path):
    """원문 카드에서 초록만 지우고 그 BDF 로 새로 그린 RGBA — 굽지 않는다."""
    card = _card_image()
    px = card.load()
    w, h = card.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 255 and r == 24 and 120 <= g <= 140 and b == 24:
                px[x, y] = (0, 0, 0, 0)
    glyph, (top, bot) = render_bdf_line(bdf_path, TEXT, GREEN)
    gpx = glyph.load()
    cols = [x for x in range(glyph.width) if any(gpx[x, y][3] for y in range(glyph.height))]
    gx0, gx1 = min(cols), max(cols)
    ink_h = bot - top + 1
    paste_x = round(w / 2 - (gx1 - gx0 + 1) / 2) - gx0
    paste_y = round(33 - ink_h / 2) - top  # 33 = 원문 잉크 범위(y26~40)의 세로 중심
    card.alpha_composite(glyph, (paste_x, paste_y))
    return card


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", action="store_true", help="원문·neodgm16(정본)·Galmuri14 석 줄 PNG")
    ap.add_argument("--out", default="/tmp/chapter_card_compare.png")
    a = ap.parse_args()
    if not a.compare:
        ap.print_help()
        return 0
    from PIL import Image

    orig = _card_image()
    neodgm_note = "정본은 neodgm 16px — build.py --test 를 돌려 games/ps1-ed3/work/build/ 에서 본다"
    print(neodgm_note)
    galmuri14 = make_candidate(os.path.join(common.REPO, "shared", "fonts", "Galmuri14.bdf"))

    def preview(img):
        bg = Image.new("RGBA", img.size, (24, 24, 34, 255))
        bg.alpha_composite(img)
        return bg.convert("RGB")

    rows = [preview(orig), preview(galmuri14)]
    w_, h_ = rows[0].size
    out = Image.new("RGB", (w_, h_ * 2 + 4), (40, 40, 40))
    y = 0
    for im in rows:
        out.paste(im, (0, y))
        y += h_ + 4
    out.save(a.out)
    print(f"원문·Galmuri14 두 줄 → {a.out} (neodgm 정본은 실제 빌드에서 본다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
