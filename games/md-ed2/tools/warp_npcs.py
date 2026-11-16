"""마을 NPC 일괄 말걸기 — 한 맵의 NPC 레코드(씬 모듈 머리 8B 항목: [0] 플래그 · [1] 루트 · [2] x · [3] y) 마다 바로 아래 칸으로 순간이동해 위를 보고 확인키를 눌러 대사·상점 화면을 모은다.

    python3 tools/warp_npcs.py STATE.st --sav SAV --out DIR [--presses 4]    # STATE = warp.py 로 마을에 들어간 상태

산출: DIR/NN_xXX_yYY_NNN.png(마지막 화면) + sheet.png(전부 한 장). 상점 NPC 는 화면에 목록 창이 뜬다.
가게 계산대는 `--dy 2`(계산대 한 칸 너머). 순간이동은 마을 안에서만 믿을 수 있다(warp.py 머리말).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import dialog
import warp
from PIL import Image, ImageDraw


def npc_records(mapid: int) -> list[tuple[int, int, int, int]]:
    """(레코드 오프셋, 루트 바이트, x, y) — 머리 워드 [2]..[3] 사이."""
    import importlib

    d0 = common.rom()
    t, ids, i = 0x19D96E, [], 0
    while True:
        w = int.from_bytes(d0[t + 2 * i : t + 2 * i + 2], "big")
        if w == 0xFFFF:
            break
        ids.append(w)
        i += 1
    n = ids.index(mapid)
    d = dialog.module(n // 4, n % 4).data
    hdr = [int.from_bytes(d[k : k + 2], "big") for k in range(0, 0x14, 2)]
    out = []
    for a in range(hdr[2], hdr[3], 8):
        if d[a] == 0x80:  # 빈 칸 표지
            continue
        out.append((a, d[a + 1], d[a + 2], d[a + 3]))
    importlib.invalidate_caches()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("state")
    ap.add_argument("--rom", default=str(common.BUILD_DIR / common.BUILD_TAG / "ed2-kr.bin"))
    ap.add_argument("--sav", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--presses", type=int, default=4)
    ap.add_argument("--dy", type=int, default=1, help="NPC 아래 몇 칸에 설지(가게 계산대는 2)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    c = warp.load(a.rom, a.sav, a.state)
    mid = warp.map_id(c)
    st = c.save_state()
    ims = []
    for k, (off, root, x, y) in enumerate(npc_records(mid)):
        c.load_state(st)
        c.run(2)
        warp.teleport(c, x, y + a.dy)
        c.press("up", 6, 10)
        for _ in range(a.presses):
            c.press("c", 6, 50)
            c.run(30)
        p = out / f"{k:02d}_x{x:02x}_y{y:02x}_{off:03x}.png"
        c.shot(str(p))
        im = Image.open(p).convert("RGB")
        ImageDraw.Draw(im).text((4, 100), f"{k}:{x:02x},{y:02x} r{root:02x}", fill=(255, 255, 0))
        ims.append(im)
    cols = 4
    rows = (len(ims) + cols - 1) // cols
    m = Image.new("RGB", (320 * cols, 224 * rows))
    for i, im in enumerate(ims):
        m.paste(im, ((i % cols) * 320, (i // cols) * 224))
    m.save(out / "sheet.png")
    print(f"맵 {mid:x} · NPC {len(ims)} → {out}/sheet.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
