"""전수 촬영 결과 → 검수용 모음 그림(타일 20장) + 기대 문안 목록 — 검수 세션(서브에이전트)이 그림을 보고 기대 문안과 대조한다.

    python3 sweep_sheets.py <sweep 폴더>      (폴더 안 index.tsv · 위 폴더의 rom_text.tsv 를 읽는다)
산출: `<폴더>/sheets/NNN.png`(타일 번호 1~20, 위→아래 · 왼→오) · `NNN.txt`(타일 → 열쇠 · 줄 번호 · 기대 문안 — 롬 바이트를 글리프 비트맵으로 되읽은 한글).
기대 문안의 `<16>화자<14>` = 화자 머리, `/` = 줄바꿈, `<13>` = 쪽 끝(키 대기), `<0e>`·`<1c>`·`<1a ..>` 같은 제어는 변수·연출이라 그림과 다를 수 있다.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

PER = 20
COLS = 4


def main() -> int:
    d = Path(sys.argv[1])
    exp = {}
    for ln in (d.parent / "rom_text.tsv").read_text().splitlines():
        k, t = ln.split("\t", 1)
        exp[k] = t
    rows = [ln.split("\t") for ln in (d / "index.tsv").read_text().splitlines() if not ln.startswith("-")]
    out = d / "sheets"
    out.mkdir(exist_ok=True)
    tiles = []
    for name, key, lines, kn in rows:
        tiles.append((name, key, lines, kn))
    for s in range(0, len(tiles), PER):
        chunk = tiles[s : s + PER]
        ims = [Image.open(d / n[0]) for n in chunk]
        w, h = ims[0].size
        rws = (len(ims) + COLS - 1) // COLS
        sheet = Image.new("RGB", (COLS * (w + 4), rws * (h + 12)), (40, 40, 40))
        dr = ImageDraw.Draw(sheet)
        txt = []
        for i, (im, (name, key, lines, kn)) in enumerate(zip(ims, chunk, strict=True)):
            x, y = (i % COLS) * (w + 4), (i // COLS) * (h + 12)
            dr.text((x + 2, y), f"#{i + 1} {kn}", fill=(255, 255, 0))
            sheet.paste(im, (x, y + 11))
            exps = " ‖ ".join(f"[{key}:{j}] {exp.get(f'{key}:{j}', '?')}" for j in lines.split(","))
            txt.append(f"#{i + 1} (쪽 {kn}) {exps}")
        n = s // PER
        sheet.save(out / f"{n:03d}.png")
        (out / f"{n:03d}.txt").write_text("\n".join(txt) + "\n")
    print(f"모음 {(len(tiles) + PER - 1) // PER}장 · 타일 {len(tiles)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
