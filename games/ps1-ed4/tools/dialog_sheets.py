"""전·후 촬영(`dialog_sweep`) → 나란히 시트 + 화면 기계 검사.

    python3 tools/dialog_sheets.py <전 폴더> <후 폴더> <시트 폴더> [--per 12]

화면 검사(후 쪽마다): 넘침(창 안쪽 오른쪽 가장자리 너머 글자 픽셀) · 빈 쪽(글자 픽셀 없음) · 쪽 수 변화(▼) — 계산(조판 문자열)과 대조한다.
"""

import glob
import json
import os
import sys

from PIL import Image, ImageDraw

DLG = (0, 160, 320, 240)


def text_px(img):
    """대사창 안 글자 픽셀 — 흰색(본문) · 주황(이름) · 녹색(나레이션)."""
    px = img.convert("RGB").load()
    w, h = img.size
    out = []
    for y in range(172, 230):
        for x in range(8, w - 4):
            r, g, b = px[x, y]
            if (r > 200 and g > 200 and b > 200) or (g > 180 and r < 80 and b < 120):
                out.append((x, y))
    return out


def check_page(path):
    img = Image.open(path)
    t = text_px(img)
    over = any(x >= 306 for x, _y in t)
    return {"empty": len(t) < 8, "overflow": over}


def main(before, after, out, per=12):
    bi = {(t["member"], t["si"]): t for t in json.load(open(os.path.join(before, "index.json")))}
    ai = {(t["member"], t["si"]): t for t in json.load(open(os.path.join(after, "index.json")))}
    os.makedirs(out, exist_ok=True)
    rows, stats = [], {"streams": 0, "pages_before": 0, "pages_after": 0, "empty": 0, "overflow": 0, "diff_streams": 0}
    for k, a in ai.items():
        b = bi.get(k)
        if not b:
            continue
        stats["streams"] += 1
        stats["pages_before"] += len(b["shots"])
        stats["pages_after"] += len(a["shots"])
        differs = False
        n = max(len(a["shots"]), len(b["shots"]))
        for j in range(n):
            pa = os.path.join(after, a["shots"][j]) if j < len(a["shots"]) else None
            pb = os.path.join(before, b["shots"][j]) if j < len(b["shots"]) else None
            if pa:
                c = check_page(pa)
                stats["empty"] += c["empty"]
                stats["overflow"] += c["overflow"]
            same = pa and pb and open(pa, "rb").read() == open(pb, "rb").read()
            if not same:
                differs = True
                rows.append((k, j, pb, pa))
        stats["diff_streams"] += differs
    for s in range(0, len(rows), per):
        ch = rows[s : s + per]
        W, H = 320, 80
        im = Image.new("RGB", (W * 2 + 8, (H + 4) * len(ch)), (30, 30, 30))
        d = ImageDraw.Draw(im)
        for i, ((m, si), j, pb, pa) in enumerate(ch):
            y = i * (H + 4)
            if pb:
                im.paste(Image.open(pb).convert("RGB").crop(DLG), (0, y))
            if pa:
                im.paste(Image.open(pa).convert("RGB").crop(DLG), (W + 8, y))
            d.text((2, y), f"{m.split(chr(92))[-1][:-4]} s{si} p{j}", fill=(255, 255, 0))
        im.save(os.path.join(out, f"sheet_{s // per + 1:03d}.png"))
    stats["sheets"] = (len(rows) + per - 1) // per
    stats["diff_pages"] = len(rows)
    json.dump(stats, open(os.path.join(out, "stats.json"), "w"), indent=1)
    return stats


if __name__ == "__main__":
    print(main(sys.argv[1], sys.argv[2], sys.argv[3]))
