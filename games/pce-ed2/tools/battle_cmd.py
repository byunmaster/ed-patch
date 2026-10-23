"""전투 안 「사용」·「주문」 문구 촬영(마스터 10-20 — 슬라임 강제 전투에서 커맨드로 고르는 길).

디버그 ITEM 으로 소모 도구를 넣고 필드를 걸어 슬라임과 만난 뒤(전투 번호 `$3233`=38), 전투 커맨드 창에서 「사용」(또는 「주문」)을 골라 목록의 k 번째를 쓰고 로그 창을 쪽마다 찍는다.

    python3 battle_cmd.py --iso <디버그 이미지> --out <폴더> [--pages 6 7] [--max 12] [--mode use|spell]
"""

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import itemuse
import pceview
from PIL import Image


def to_battle(e, out: Path) -> str:
    """필드를 좌우로 걸어 슬라임과 만나는 순간 상태를 저장한다(최대 3000프레임)."""
    path = str(out / "battle.state")
    steps = ["right", "left"]
    for f in range(60):
        e.hold(steps[f % 2])
        for _ in range(100):
            e.run(1)
            if e.peek(0x3233, 1)[0] == 38:
                e.hold(None)
                e.save(path)
                return path
    e.hold(None)
    raise SystemExit("슬라임과 못 만났다")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bram", default="/root/save/pce-ed2/ed2.sav")
    ap.add_argument("--pages", type=int, nargs="*", default=[6, 7])
    ap.add_argument("--max", type=int, default=12)
    ap.add_argument("--mode", default="use", choices=["use", "spell"])
    a = ap.parse_args()
    import romtag

    desc = romtag.check(a.iso)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "rom.txt").write_text(desc + "\n")
    e = pceview.boot_field(str(Path(a.iso).with_suffix(".cue")), a.bram)
    if a.mode == "use":
        itemuse.add_pages(e, a.pages)
        e.press("ii", 5, 60)  # 게임 메뉴 닫기
    st = to_battle(e, out)
    first = None
    summary: list[tuple[int, int, int]] = []
    for k in range(a.max):
        e.load(st)
        e.run(240)  # 나타남 문구 · 커맨드 창
        Image.fromarray(e.frame_img).save(out / f"{k:02d}_cmd.png") if k == 0 else None
        e.press("down", 5, 20)  # 공격 → 사용(주문은 오른쪽)
        if a.mode == "spell":
            e.press("up", 5, 20)
            e.press("right", 5, 20)
        e.press("i", 5, 40)
        for _ in range(k):
            e.press("down", 5, 15)
        h = hashlib.md5(e.frame_img[40:200, 100:250].tobytes()).hexdigest()  # 목록 창(커서 위치가 다르면 다르다)
        if k and h == first:
            break
        if k == 0:
            first = h
            Image.fromarray(e.frame_img).save(out / "list_0.png")
        seen = set()
        m = 0
        total = 0
        prev = None
        e.press("i", 5, 5)
        for i in range(100):
            e.run(10)
            c = hashlib.md5(e.frame_img[130:214, 28:214].tobytes()).hexdigest()
            stable = c == prev  # 앞 표본과 같음 = 더 안 그려지는 중
            prev = c
            if c not in seen and stable:
                seen.add(c)
                total += 1
                if pceview.has_cursor(e.frame_img):  # ▽ 가 보이고 두 표본 연속 같은 쪽(글자가 다 나온 쪽)만 저장
                    Image.fromarray(e.frame_img[130:214, 14:214]).save(out / f"{k:02d}_{m:02d}.png")
                    m += 1
            if i % 6 == 5:
                e.press("i", 4, 4)
        print(k, m, f"(▽ 쪽 {m} / 서로 다른 프레임 {total})", flush=True)
        summary.append((k, m, total))
    (out / "summary.tsv").write_text("항목\t▽쪽\t다른프레임\n" + "\n".join(f"{k}\t{m}\t{t}" for k, m, t in summary) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
