"""일괄 캡처(prune 뒤) → 검수용 시트. 쪽마다 메시지 영역을 잘라 3열 × 8행(24쪽)씩 한 장에 모으고, 쪽마다 단위 주소·쪽 번호 꼬리표를 붙인다.

    python3 sheets.py <out 폴더> <시트 폴더>      # 산출: s0000.png … + index.tsv(시트·칸 → 단위·쪽)
시트는 사람·검수 서브에이전트가 눈으로 본다. 원문 포함 자료라 커밋 금지.
"""
import glob
import os
import sys

from PIL import Image, ImageDraw

out, dst = sys.argv[1], sys.argv[2]
os.makedirs(dst, exist_ok=True)
W, H, LBL = 256, 96, 11
COLS, ROWS = 3, 8
items = []
for ud in sorted(glob.glob(f"{out}/c*/raw/*")):
    for pi, f in enumerate(sorted(glob.glob(ud + "/*.png"))):
        items.append((os.path.basename(ud), pi + 1, f))
idx = open(f"{dst}/index.tsv", "w")
for n in range(0, len(items), COLS * ROWS):
    sh = Image.new("RGB", (W * COLS, (H + LBL) * ROWS), (20, 20, 20))
    dr = ImageDraw.Draw(sh)
    for k, (u, p, f) in enumerate(items[n : n + COLS * ROWS]):
        x, y = (k % COLS) * W, (k // COLS) * (H + LBL)
        dr.text((x + 2, y), f"{u} p{p}", fill=(255, 255, 0))
        sh.paste(Image.open(f).convert("RGB"), (x, y + LBL))  # prune.py 가 이미 대화창 영역으로 잘라 둠
        idx.write(f"s{n // (COLS * ROWS):04d}\t{k}\t{u}\t{p}\n")
    sh.save(f"{dst}/s{n // (COLS * ROWS):04d}.png")
print("시트", (len(items) + COLS * ROWS - 1) // (COLS * ROWS), "쪽", len(items))
