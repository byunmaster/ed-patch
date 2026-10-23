"""도구 사용 문구 촬영(마스터 10-19 밤샘 검수 — 도구·주문을 한 번씩 써 본다) — 디버그 메뉴 ITEM 으로 소모 도구를 소지품에 넣고, 필드 메뉴 「사용」 목록의 항목을 하나씩 골라 나오는 메시지를 쪽마다 찍는다.

    python3 itemuse.py --iso <디버그 이미지> --out <폴더> [--pages 6 7 8]
산출: `<out>/<번호>_<쪽>.png`(화면 아래 대화창 부근) · `index.tsv`(사용 번호 · 쪽 수 · 항목 이름은 그림 안).
⚠ 필드 사용 — 전투 안 사용 문구는 `battle_sweep` 의 전투 로그 몫(전투 사용은 따로).
"""

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pceview
from PIL import Image


def open_debug_item(e):
    e.press("run+ii", 10, 30)
    e.press("down", 5, 15)
    e.press("down", 5, 15)
    e.press("i", 5, 30)


def add_pages(e, pages: list[int]) -> None:
    """ITEM 목록의 쪽(0 부터)마다 일곱 칸을 모두 소지품에 넣는다."""
    open_debug_item(e)
    for _ in range(max(pages) + 1):
        pass
    cur = 0
    for p in pages:
        while cur < p:
            e.press("right", 5, 25)
            cur += 1
        for _ in range(7):
            e.press("i", 5, 20)
            e.press("down", 5, 10)
    e.press("ii", 5, 30)
    e.press("ii", 5, 30)  # 목록 · 디버그 닫기 → 게임 메뉴


def use_list_state(e, path: str) -> None:
    e.press("down", 5, 15)
    e.press("i", 5, 40)  # 사용 목록
    e.save(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bram", default="/root/save/pce-ed2/ed2.sav")
    ap.add_argument("--pages", type=int, nargs="*", default=[6, 7, 8])
    ap.add_argument("--max", type=int, default=24)
    a = ap.parse_args()
    import romtag

    desc = romtag.check(a.iso)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "rom.txt").write_text(desc + "\n")
    cue = str(Path(a.iso).with_suffix(".cue"))
    e = pceview.boot_field(cue, a.bram)
    add_pages(e, a.pages)
    st = out / "_list.state"
    use_list_state(e, str(st))
    Image.fromarray(e.frame_img).save(out / "list_0.png")
    idx = []
    first = None
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
        shots = []
        e.press("i", 5, 5)
        for i in range(70):
            e.run(10)
            c = hashlib.md5(e.frame_img[130:214, 28:214].tobytes()).hexdigest()
            if c not in seen and pceview.ink(e.frame_img) >= 25:  # 대사창에 글이 있는 쪽만
                seen.add(c)
                f = out / f"{k:02d}_{len(shots):02d}.png"
                Image.fromarray(e.frame_img).save(f)
                shots.append(f.name)
            if i % 5 == 4:
                e.press("i", 4, 4)
        idx.append(f"{k}\t{len(shots)}")
        print(k, len(shots), flush=True)
    (out / "index.tsv").write_text("\n".join(idx) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
