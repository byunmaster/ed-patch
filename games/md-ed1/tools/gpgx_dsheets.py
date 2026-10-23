"""`gpgx_msgview.py` 가 낸 대사 PNG 의 창 띠만 잘라 한 장에 모은다(검수용 — 2배 확대, 칸마다 씬·스트림·쪽 꼬리표).

사용: `python3 gpgx_dsheets.py <PNG 폴더> <출력 폴더> [--per 20]`
산출: `sheet_NNN.png` + `sheets.json`(시트 → 칸 목록 — 검수 결과를 씬·줄 열쇠로 되짚는 색인).
"""

import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw

X0, X1, Y0, Y1 = 40, 300, 146, 224  # 대사창 띠(화면 320x224 안) — 이름 줄 + 최대 넷째 줄까지
LAB = 12
SCALE = 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--per", type=int, default=20)
    a = ap.parse_args()
    files = sorted(Path(a.src).glob("s[0-9][0-9][0-9]_*_*.png"))
    out = Path(a.dst)
    out.mkdir(parents=True, exist_ok=True)
    cw, ch = (X1 - X0) * SCALE, (Y1 - Y0) * SCALE
    cols = 2
    meta = {}
    for n in range(0, len(files), a.per):
        chunk = files[n : n + a.per]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cw * cols, (ch + LAB) * rows), (24, 24, 24))
        d = ImageDraw.Draw(sheet)
        cells = []
        for i, f in enumerate(chunk):
            m = re.match(r"s(\d+)_([0-9a-f]+v?\d?)_(\d+)", f.stem)
            tag = f"s{int(m.group(1))} {m.group(2)} p{m.group(3)}" if m else f.stem
            im = Image.open(f).convert("RGB").crop((X0, Y0, X1, Y1)).resize((cw, ch), Image.NEAREST)
            x, y = (i % cols) * cw, (i // cols) * (ch + LAB)
            d.text((x + 2, y), tag, fill=(255, 255, 0))
            sheet.paste(im, (x, y + LAB))
            cells.append({"file": f.name, "tag": tag})
        name = f"sheet_{n // a.per:03d}.png"
        sheet.save(out / name)
        meta[name] = cells
    (out / "sheets.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(len(files), "→", len(meta), "장")


if __name__ == "__main__":
    main()
