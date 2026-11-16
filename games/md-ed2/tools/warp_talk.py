"""마을 NPC 말걸기·상점 한 줄 촬영 — 상태를 올리고 (x,y)로 순간이동해 `face` 쪽을 본 뒤 키 열을 차례로 눌러 매번 화면을 남긴다.

    python3 tools/warp_talk.py STATE.st --sav SAV --at 0x32,0x10 --face up --keys c,c,c,b --out DIR

키: 버튼 이름(c 확인 · b 취소 · down …) 또는 `w60`(60프레임 기다림). 산출: DIR/NN_<키>.png + sheet.png + end.st.
가게 계산대는 NPC 칸에서 두 칸 아래에 선다(`warp_npcs.py --dy 2`). 상점: `c`(인사) → `삽니다/팝니다` 메뉴(도구점) → 목록 → `c`(고름) → 「…말이군요」, 팝니다는 `down` 한 번 뒤 `c`.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import warp
from PIL import Image


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("state")
    ap.add_argument("--rom", default=str(common.BUILD_DIR / common.BUILD_TAG / "ed2-kr.bin"))
    ap.add_argument("--sav", required=True)
    ap.add_argument("--at", required=True, help="x,y 타일")
    ap.add_argument("--face", default="up")
    ap.add_argument("--keys", default="c,c,c")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    c = warp.load(a.rom, a.sav, a.state)
    x, y = (int(v, 0) for v in a.at.split(","))
    warp.teleport(c, x, y)
    c.press(a.face, 6, 10)
    n = 0
    shots: list[Path] = []

    def snap(tag: str) -> None:
        nonlocal n
        p = out / f"{n:02d}_{tag}.png"
        c.shot(str(p))
        shots.append(p)
        n += 1

    snap("start")
    for k in a.keys.split(","):
        if k.startswith("w") and k[1:].isdigit():
            c.run(int(k[1:]))
            continue
        c.press(k, 6, 50)
        c.run(30)
        snap(k)
    (out / "end.st").write_bytes(c.save_state())
    cols = 4
    rows = (len(shots) + cols - 1) // cols
    m = Image.new("RGB", (320 * cols, 224 * rows))
    for i, p in enumerate(shots):
        m.paste(Image.open(p).convert("RGB"), ((i % cols) * 320, (i // cols) * 224))
    m.save(out / "sheet.png")
    print(f"{len(shots)}장 → {out}/sheet.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
