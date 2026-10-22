"""전투·대사 일괄 산출 정리 — 메시지 창 캡처를 중복 없이 모아 군별 접촉 시트와 표(TSV)를 만든다.

    python3 report.py <출력 폴더(run.py 의 out)> <시트 폴더>

원문 JP 는 표에 안 넣는다(KR 이름만). 시트는 사람이 눈으로 본다(글리프·조사·줄바꿈·고아 부호·첫 칸 공백·빈 줄).
"""
import glob
import hashlib
import os
import re
import sys
from collections import defaultdict

from PIL import Image

out, sheets = sys.argv[1], sys.argv[2]
os.makedirs(sheets, exist_ok=True)
REG = (0, 148, 256, 218)  # 메시지 창(전투 화면 아래쪽) — 위쪽 몬스터·HUD 는 애니메이션이라 중복 판정에서 뺀다


def window_hash(im):
    return hashlib.md5(im.crop(REG).tobytes()).hexdigest()


def blank(im):
    c = im.crop(REG).convert("L")
    return len(set(c.tobytes())) < 6


if not glob.glob(f"{out}/*/raw/*_s*"):  # 대사 일괄(raw/<주소>/…) — 청크마다 단위별 고유 화면을 한 장에
    REGD = (0, 128, 256, 224)
    for chunk in sorted(glob.glob(f"{out}/c*")):
        rows = []
        for ud in sorted(glob.glob(f"{chunk}/raw/*")):
            seen, crops = set(), []
            for f in sorted(glob.glob(ud + "/*.png")):
                im = Image.open(f).convert("RGB").crop(REGD)
                h = hashlib.md5(im.tobytes()).hexdigest()
                if h not in seen:
                    seen.add(h)
                    crops.append(im)
            rows.append((os.path.basename(ud), crops[:6]))
        if not rows:
            continue
        sh = Image.new("RGB", (256 * 6, 96 * len(rows)), (0, 0, 0))
        for r, (_a, crops) in enumerate(rows):
            for c, im in enumerate(crops):
                sh.paste(im, (c * 256, r * 96))
        sh.save(f"{sheets}/{os.path.basename(chunk)}.png")
        with open(f"{sheets}/{os.path.basename(chunk)}.tsv", "w") as t:
            t.write("\n".join(f"{r}\t{a}\t{len(c)}" for r, (a, c) in enumerate(rows)) + "\n")
    print("대사 청크", len(glob.glob(f"{sheets}/c*.png")))
    sys.exit(0)

jobs = defaultdict(list)
for d in sorted(glob.glob(f"{out}/*/raw/*_s*")):
    m = re.search(r"/(\d+)_s(\d+)$", d)
    jobs[(int(m.group(1)), int(m.group(2)))].append(d)
segs_hit = defaultdict(set)
for lg in glob.glob(f"{out}/*/log.txt"):
    jobidx = {}
    for line in open(lg):
        p = line.split()
        if p and p[0] == "JOB":
            jobidx[int(p[1])] = int(p[2].split("=")[1])
        elif p and p[0] == "S":
            segs_hit[jobidx[int(p[1])]].add(p[3])
rows = []
for (idx, seed), dirs in sorted(jobs.items()):
    seen, crops = set(), []
    for d in dirs:
        for f in sorted(glob.glob(d + "/*.png")):
            if not (f.endswith("_p90.png") or "_end" in f):
                continue  # 타이핑 중간 프레임을 거른다 — 메시지 호출 90프레임 뒤와 끝 프레임만
            im = Image.open(f).convert("RGB")
            if blank(im):
                continue
            h = window_hash(im)
            if h in seen:
                continue
            seen.add(h)
            crops.append((f, im.crop(REG)))
    W, H = 256, REG[3] - REG[1]
    cols = 3
    n = len(crops)
    rowsn = (n + cols - 1) // cols
    cap = 24  # 시트 한 장 상한 — 넘으면 여러 장
    for part in range(0, n, cap):
        chunk = crops[part : part + cap]
        rr = (len(chunk) + cols - 1) // cols
        sh = Image.new("RGB", (W * cols, H * rr), (0, 0, 0))
        for i, (_f, c) in enumerate(chunk):
            sh.paste(c, ((i % cols) * W, (i // cols) * H))
        sh.save(f"{sheets}/g{idx:02d}_s{seed}_{part // cap + 1}.png")
    rows.append((idx, seed, n))
with open(f"{sheets}/table.tsv", "w") as t:
    t.write("군\tseed\t고유 화면 수\t실행된 문구 구간 수\n")
    for idx, seed, n in rows:
        t.write(f"{idx}\t{seed}\t{n}\t{len(segs_hit.get(idx, ()))}\n")
print(len(rows), "군")
