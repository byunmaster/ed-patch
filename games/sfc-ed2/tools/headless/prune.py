"""일괄 캡처 정리 — 대화창 영역(아래 96줄)으로 잘라 16색으로 줄인다.

dialog_sweep.lua 는 **창 안쪽이 DEB 프레임 안 변할 때까지 기다렸다가 찍고 그다음에 A 를 누른다**(sfc-ed1 MV_DEBOUNCE 와 같은 방식) —
그래서 `pNN.png` 는 글자가 다 나온 쪽이고 타이핑 중간 장은 애초에 안 찍힌다. 대기 한도를 넘으면 `pNN_timeout.png` 로 남기고 로그에 TIMEOUT 줄이 선다.
`manifest.tsv`(단위·쪽 수·timeout 쪽 수·검은 그림 수 — 0 이어야 한다) — timeout 이 0 이 아닌 단위는 그 번호만 대기를 늘려 다시 찍는다.

    python3 prune.py <out 폴더>   # <out>/c*/raw/<단위>/*.png → 제자리 교체 + <out>/manifest.tsv
"""
import glob
import os
import sys

from PIL import Image

REGD = (0, 128, 256, 224)
mp = f"{sys.argv[1]}/manifest.tsv"
done = set(l.split("\t")[0] for l in open(mp)) if os.path.exists(mp) else set()  # 이미 정리한 단위는 건너뛴다(여러 묶음이 같은 폴더를 쓴다)
man = open(mp, "a")
n = 0
for ud in sorted(glob.glob(f"{sys.argv[1]}/c*/raw/*")):
    if os.path.basename(ud) in done:
        continue
    fs = sorted(glob.glob(ud + "/*.png"))
    pages = [f for f in fs if os.path.basename(f).startswith("p")]
    tmo = [f for f in pages if "_timeout" in f]
    black = 0
    for f in fs:
        im = Image.open(f).convert("RGB")
        if im.size[1] > REGD[3] - REGD[1]:  # 이미 잘린 그림(높이 96)은 다시 자르지 않는다 — 다시 자르면 범위 밖이라 검은 그림이 된다(10-20 사고)
            im = im.crop(REGD)
            im.quantize(16, dither=Image.Dither.NONE).save(f, optimize=True)
        n += 1
        if im.getextrema() == ((0, 0), (0, 0), (0, 0)):
            black += 1
    man.write(f"{os.path.basename(ud)}\t{len(pages)}\t{len(tmo)}\t{black}\n")
print("처리", n)
