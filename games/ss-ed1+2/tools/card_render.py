"""장 끝 카드 **계산 렌더 시트**(실화면 아님) — 카드 첫 줄을 빌드 글리프(12px/반각 6px 칸)로 놓고 원판 줄의 가운데(빨강선)를 겹쳐 좌−우를 본다.

    python3 tools/card_render.py --out <png>

칸·위치는 `check_center` 와 같은 계산(8px 칸 → 6px 환산)이다. 실제 카드는 씬 이벤트 VM 경유라 직접 못 띄운다(status 「남은 일」)."""

import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import center_all as CA
import check_center as C
import common
import font
import patch_ui

W, S = 200, 3


def enc(s, syl):
    out = b""
    for ch in s:
        if ch in syl:
            out += font.sjis_of_index(syl[ch])
        elif ch == " ":
            out += b" "
        else:
            out += ch.encode("cp932")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    kanji, ascii_ = CA.glyphs()
    with open(os.path.join(common.GAME_DIR, "hangul_map_11kanji.json"), encoding="utf-8") as f:
        syl = json.load(f)["syllables"]
    _f, mm = common.open_image()
    cards = patch_ui._cards()
    rows = patch_ui.card_rows(mm, cards)
    tiles = []
    for r in rows:
        jp, ui = r[5], r[6]
        for how, kr in (("menu", ui),):
            if kr is None or (how == "scene" and kr == ui):
                continue
            l1 = kr.split("\n")[0].lstrip("\t")
            lead = len(l1) - len(l1.lstrip(" "))
            raw = enc(" " * lead + l1.strip(" "), syl)
            jl, jw = C.card_line(jp)
            kl, kw = C.card_line(kr)
            cx, ox = (jl + jw / 2) / 8 * 6, kl / 8 * 6
            im = Image.new("RGB", (W, 14), (0, 0, 120))
            px = im.load()
            x = int(ox)
            for wd, _l, _r, b in CA.parts(raw, kanji, ascii_):
                if wd == 12:
                    g = kanji[font.game_index(b) * 22 :][:22]
                    for rr in range(11):
                        v = int.from_bytes(g[rr * 2 : rr * 2 + 2], "big") >> 4
                        for c in range(12):
                            if v >> (11 - c) & 1 and 0 <= x + c < W:
                                px[x + c, rr + 1] = (255, 255, 255)
                x += wd
            big = im.resize((W * S, 14 * S), Image.NEAREST)
            ImageDraw.Draw(big).line(
                [(int(cx * S), 0), (int(cx * S), 14 * S)], fill=(255, 60, 60), width=1
            )
            t = Image.new("RGB", (W * S, 14 * S + 14), (20, 20, 20))
            t.paste(big, (0, 0))
            dd = 2 * (kl - (jl + (jw - kw) / 2))
            game = "ED1" if r[0] == "/ED.BIN" else "ED2"
            ImageDraw.Draw(t).text(
                (3, 14 * S + 1),
                f"{game} {r[0][-4:]}@{r[3]:#x} {how} L-R {dd:g}px (red=orig center)",
                fill=(255, 255, 120),
            )
            tiles.append(t)
    w, h = tiles[0].size
    cols = 2
    sh = Image.new("RGB", (cols * (w + 4), (-(-len(tiles) // cols)) * (h + 4) + 16), (0, 0, 0))
    ImageDraw.Draw(sh).text(
        (4, 2),
        "CALC RENDER - NOT A REAL SCREEN (12px font, half-cell 6px, line 1 only)",
        fill=(255, 200, 100),
    )
    for i, t in enumerate(tiles):
        sh.paste(t, ((i % cols) * (w + 4), 16 + (i // cols) * (h + 4)))
    sh.save(a.out)
    print(len(tiles))


if __name__ == "__main__":
    main()
