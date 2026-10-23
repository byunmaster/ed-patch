"""주문 사용 문구 촬영 — 디버그 메뉴로 레벨을 올려(MP) 주문(MAGIC)을 넣고, 필드 메뉴 「주문」 목록의 항목을 하나씩 써서 나오는 메시지를 찍는다. `itemuse.py` 와 같은 꼴.

    python3 spelluse.py --iso <디버그 이미지> --out <폴더> [--levels 15] [--max 24]
"""

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pceview
from PIL import Image


def setup(e, levels: int, magic_pages: int) -> None:
    e.press("run+ii", 10, 30)
    e.press("down", 5, 15)  # LVL
    for _ in range(levels):
        e.press("i", 5, 40)
        e.press("i", 5, 10)
    e.press("down", 5, 15)  # ITEM · MAGIC 줄
    e.press("right", 5, 25)  # MAGIC
    e.press("i", 5, 30)
    for p in range(magic_pages):
        for _ in range(7):
            e.press("i", 5, 20)
            e.press("down", 5, 10)
        e.press("right", 5, 25)
    e.press("ii", 5, 30)
    e.press("ii", 5, 30)  # 목록 · 디버그 닫기 → 게임 메뉴


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bram", default="/root/save/pce-ed2/ed2.sav")
    ap.add_argument("--levels", type=int, default=15)
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--max", type=int, default=24)
    a = ap.parse_args()
    import romtag

    desc = romtag.check(a.iso)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "rom.txt").write_text(desc + "\n")
    e = pceview.boot_field(str(Path(a.iso).with_suffix(".cue")), a.bram)
    setup(e, a.levels, a.pages)
    e.press("i", 5, 40)  # 주문 → 인물
    e.press("i", 5, 40)  # 인물 선택 → 주문 목록
    st = out / "_list.state"
    e.save(str(st))
    Image.fromarray(e.frame_img).save(out / "list_0.png")
    first = None
    idx = []
    for k in range(a.max):
        e.load(str(st))
        e.run(2)
        for _ in range(k):
            e.press("down", 5, 8)
        h = hashlib.md5(e.frame_img[40:180, 100:250].tobytes()).hexdigest()
        if k and h == first:
            break
        if k == 0:
            first = h
        seen = set()
        n = 0
        e.press("i", 5, 5)
        for i in range(70):
            e.run(10)
            c = hashlib.md5(e.frame_img[130:214, 28:214].tobytes()).hexdigest()
            if c not in seen and pceview.ink(e.frame_img) >= 25:
                seen.add(c)
                Image.fromarray(e.frame_img).save(out / f"{k:02d}_{n:02d}.png")
                n += 1
            if i % 5 == 4:
                e.press("i", 4, 4)
        idx.append(f"{k}\t{n}")
        print(k, n, flush=True)
    (out / "index.tsv").write_text("\n".join(idx) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
