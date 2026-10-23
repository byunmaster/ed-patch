"""필드 메뉴 「사용」「주문」 실행 흐름 촬영 — 디버그 세이브(엘아스타 남서쪽 필드, 소지품 횃불 둘)에서 b → 사용/주문 → 항목 → 결과 문구. 메시지 속도 「멈춤」(`$FF1B05`=3) · 단계마다 화면이 멈춘 뒤 찍는다.

    python3 tools/use_flow.py [--out DIR]

시나리오: U0·U1 = 소지품 첫째·둘째(횃불) 사용 · S0 = 주문 첫째(레스) HP 가득 · S1 = HP 를 깎고 레스 · (주문 목록 끝까지 한 칸씩은 안 갔다).
산출 `DIR/<시나리오>_NN.png` + `sheet_<시나리오>.png`. ⚠ 메뉴 커서는 마지막 위치를 기억해 **b 직후엔 「기타」** 에서 시작한다 — 위로 4번이 「사용」, 5번이 「주문」(단계마다 화면이 멈춘 뒤 눌러 첫 입력이 무시되지 않는다).
"""

import ctypes as C
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_sweep as BS
import headless
import scene_sweep as S
from PIL import Image

OUT = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "sweep" / "use-cast"


def settle(c, maxf=400):
    prev = None
    for _ in range(maxf // 6):
        c.run(6)
        cur = c.frame[120:].copy()
        if (
            prev is not None
            and int((np.abs(cur.astype(int) - prev.astype(int)).sum(axis=2) > 0).sum()) < 40
        ):
            return
        prev = cur


def boot_field(c) -> bytes:
    """디버그 세이브 → 필드(엘아스타 남서쪽). 전투 무장은 하지 않는다(`BS.boot` 와 달리)."""
    sav = BS.SAVE.read_bytes()
    C.memmove(c.lib.retro_get_memory_data(0), sav, len(sav))
    c.run(1601)
    c.press("start", 20, 400)
    c.press("down", 20, 20)
    c.press("c", 15, 200)
    c.run(100)
    c.press("down", 8, 14)
    c.press("down", 8, 14)
    c.press("c", 15, 300)
    c.run(300)
    return c.save_state()


FLOWS = {
    "U0": (None, ["b", "up", "up", "up", "up", "c", "c", "c", "c", "c", "c"]),
    "U1": (None, ["b", "up", "up", "up", "up", "c", "down", "c", "c", "c", "c", "c"]),
    "S0": (None, ["b", "up", "up", "up", "up", "up", "c", "c", "c", "c", "c", "c"]),
    "S1": (100, ["b", "up", "up", "up", "up", "up", "c", "c", "c", "c", "c", "c", "c", "c"]),
    # 보통 속도 — 「…HP가 ▼ N 회복했다」의 수치 쪽은 `end 06` 조각이라 멈춤에서는 한 프레임도 안 남는다
    "S2": (
        100,
        ["b", "up", "up", "up", "up", "up", "c", "c", "c", "c", "c", "c", "c", "c", "c"],
        1,
    ),
}


def main() -> None:
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else OUT
    out.mkdir(parents=True, exist_ok=True)
    c = headless.Core(str(BS.ROM))
    st = boot_field(c)
    for tag, flow in FLOWS.items():
        hp, keys = flow[0], flow[1]
        speed = flow[2] if len(flow) > 2 else 3
        c.load_state(st)
        c.run(30)
        S.set_speed(c, speed)
        if hp is not None:
            c.poke(0xFF1DC0, hp.to_bytes(2, "big"))  # 파티원 0 현재 HP
        shots = []
        for i, key in enumerate(keys):
            c.press(key, 8, 20)
            settle(c)
            p = out / f"{tag}_{i:02d}.png"
            c.shot(str(p))
            shots.append(Image.open(p).convert("RGB"))
        cols = 4
        sh = Image.new("RGB", (320 * cols, 224 * ((len(shots) + cols - 1) // cols)))
        for i, im in enumerate(shots):
            sh.paste(im, ((i % cols) * 320, (i // cols) * 224))
        sh.save(out / f"sheet_{tag}.png")
        print(tag, "ok", flush=True)


if __name__ == "__main__":
    main()
