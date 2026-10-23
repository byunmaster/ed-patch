"""주문서로 주문 익히기 → 필드 주문 사용 문구 촬영(마스터 10-20 「진입로를 만든다」).

디버그 ITEM 으로 주문서 쪽(13~)을 소지품에 넣고, 필드 「사용」 목록에서 주문서를 골라 「누가 주문을 익힐까요? → 어디에 익힐까요?」 로 익힌 뒤,
「주문」 목록의 주문을 하나씩 써서 나오는 메시지를 찍는다. 익히는 쪽 흐름 화면도 같이 남긴다.

    python3 spellbook.py --iso <디버그 이미지> --out <폴더> [--pages 13 14 15] [--books 7] [--levels 60]
"""

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import itemuse
import pceview
from PIL import Image


def panel_row(e) -> int:
    """오른쪽 인물 칸의 파란 선택 띠가 몇 번째 줄인가(0~3), 없으면 -1."""
    import numpy as np

    a = e.frame_img[:, 232:316].astype(int)
    blue = ((a[:, :, 2] > 240) & (a[:, :, 0] < 30) & (a[:, :, 1] < 30)).sum(axis=1)
    ys = np.where(blue > 40)[0]
    return -1 if len(ys) == 0 else int((ys.mean() - 50) // 40)


def spell_list_open(e) -> bool:
    """필드 주문 목록 창(오른쪽 위 주황 틀)이 떠 있나."""
    import numpy as np

    a = e.frame_img[50:172, 140:214].astype(int)
    return int(((a[:, :, 0] > 240) & (a[:, :, 1] > 60) & (a[:, :, 1] < 90) & (a[:, :, 2] < 20)).sum()) > 160


def setup(e, levels: int, pages: list[int]) -> None:
    """디버그 메뉴: LVL 로 레벨을 올리고(MP) ITEM 쪽을 소지품에 넣은 뒤 게임 메뉴까지 연다(`spelluse.setup` 와 같은 순서)."""
    e.press("run+ii", 10, 30)
    e.press("down", 5, 15)  # LVL
    for _ in range(levels):
        e.press("i", 5, 40)
        e.press("i", 5, 10)
    e.press("down", 5, 15)  # ITEM · MAGIC 줄
    e.press("i", 5, 30)  # ITEM 목록
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bram", default="/root/save/pce-ed2/ed2.sav")
    ap.add_argument("--pages", type=int, nargs="*", default=[13, 14, 15])
    ap.add_argument("--books", type=int, default=7)
    ap.add_argument("--allow-stale", action="store_true")
    ap.add_argument("--max-spells", type=int, default=12)
    ap.add_argument("--levels", type=int, default=40)
    a = ap.parse_args()
    import romtag

    desc = romtag.check(a.iso, a.allow_stale)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "rom.txt").write_text(desc + "\n")
    e = pceview.boot_field(str(Path(a.iso).with_suffix(".cue")), a.bram)
    setup(e, a.levels, a.pages)
    n = [0]

    def shot(tag: str) -> None:
        Image.fromarray(e.frame_img).save(out / f"{n[0]:03d}_{tag}.png")
        n[0] += 1

    # 사용 → 주문서(목록 위에서 세 번째부터 — 횃불 둘 뒤) 를 차례로 익힌다
    e.press("down", 5, 15)
    e.press("i", 5, 40)
    shot("use_list")
    for b in range(a.books):
        for _ in range(2):
            e.press("down", 5, 8)
        e.press("i", 5, 150)  # 주문서 선택 → 누가(문구가 다 나올 때까지)
        shot(f"b{b}_who")
        for _ in range(6):  # 인물 칸 커서(파란 띠)를 첫 인물(아트라스) 줄로 — 위로(띠가 0번 줄이거나 안 보이면 멈춘다)
            if panel_row(e) in (-1, 0):
                break
            e.press("up", 5, 12)
        e.press("i", 5, 150)  # 인물
        shot(f"b{b}_where")
        for _ in range(b):  # 책마다 다른 주문 칸에 익힌다
            e.press("down", 5, 12)
        e.press("i", 5, 150)  # 칸
        for i in range(40):
            e.run(10)
            if i % 4 == 3:
                e.press("i", 4, 4)
        shot(f"b{b}_after")
        e.press("ii", 5, 30)
        e.press("ii", 5, 30)
        e.press("down", 5, 15)
        e.press("i", 5, 40)
    e.save(str(out / "_after.state"))
    # 익힌 주문을 필드 「주문」 목록에서 하나씩 쓴다 — 지도로 돌아와(창 없음) 게임 메뉴 → 주문 → 인물 → 목록 열기를 키 조합을 바꿔 가며 목록 창이 뜰 때까지 시도한다
    for _ in range(4):
        e.press("ii", 5, 40)
    base = out / "_map.state"  # 이 시점은 창 없는 지도(주문서 흐름 뒤) — 거기서 ii=게임 메뉴
    e.save(str(base))
    variants = [["ii", "i", "up", "i"], ["i", "i", "i"], ["i", "i", "up", "i"], ["i", "i", "down", "i"], ["i", "up", "i"], ["i", "down", "i"], ["i", "i", "up", "up", "i"], ["i", "i", "down", "down", "i"]]
    opened = None
    for v in variants:
        e.load(str(base))
        e.run(20)
        for key in v:
            e.press(key, 5, 70)
        shot("try_" + "_".join(v))
        if spell_list_open(e):
            opened = v
            break
    (out / "opened.txt").write_text(" ".join(opened) if opened else "열리지 않음")
    if not opened:
        return 1
    shot("spell_list")
    st = out / "_spells.state"
    e.save(str(st))
    first = None
    for k in range(a.max_spells):
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
        m = 0
        e.press("i", 5, 5)
        for i in range(70):
            e.run(10)
            c = hashlib.md5(e.frame_img[130:214, 28:214].tobytes()).hexdigest()
            if c not in seen and pceview.ink(e.frame_img) >= 25:
                seen.add(c)
                Image.fromarray(e.frame_img).save(out / f"sp{k:02d}_{m:02d}.png")
                m += 1
            if i % 5 == 4:
                e.press("i", 4, 4)
        print("spell", k, m, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
