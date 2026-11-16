"""디버그 이동 — 맵의 NPC 를 하나씩 찾아가 말을 건다(시험 전용, 제품 롬 불변, 캡처에 「디버그 이동」 표기).

살아 있는 NPC 배열(`0x80092532` 근처 — 플레이어 슬롯 `0x800924E6` 다음 76B 간격, 앞 두 u16 = 타일 x·y)을 읽어, 플레이어 좌표(`0x800924E6`·`0x801E7C7C` 의 x·y u16)를 그 곁으로 옮기고 ○ 를 누른다.
   sh scripts/capture.sh python3 tools/debug_warp_npc.py <cue> <card.mcr> <맵:방향:인자hex> <출력폴더> [최대 NPC 수]
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import debug_warp as W
import dialog_harness as D
import numpy as np
import PIL.Image as I

NPC0, STRIDE = 0x800924E6 + 0x4C, 0x4C
PLAYER = (0x800924E6, 0x801E7C7C)


def green(p):
    a = np.asarray(I.open(p).convert("RGB")).astype(int)
    return int(
        ((abs(a[..., 0] - 16) < 6) & (abs(a[..., 1] - 56) < 8) & (abs(a[..., 2] - 32) < 6)).sum()
    )


def _gray(p):
    return np.asarray(I.open(p).convert("L")).astype(int)


def npcs(e, n=40):
    out = []
    for i in range(n):
        x, y = struct.unpack("<hh", e.peek(NPC0 + i * STRIDE, 4))
        if 0 < x < 400 and 0 < y < 400:
            out.append((i, x, y))
    return out


def teleport(e, x, y):
    for a in PLAYER:
        e.poke(a, struct.pack("<hh", x, y))
    e.run(90)


def main():
    cue, card, spec, out = sys.argv[1:5]
    cap = int(sys.argv[5]) if len(sys.argv) > 5 else 40
    name, d, a = spec.split(":")
    os.makedirs(out, exist_ok=True)
    base = out + "/base.state"
    e = D.make_state(cue, card, base)
    W.warp(e, name, int(d), bytes.fromhex(a), settle=200)
    here = out + "/warped.state"
    e.save(here)
    lst = npcs(e)[:cap]
    if os.environ.get("NPC_ONLY"):  # 쉼표로 고른 슬롯 번호만(재촬영용)
        keep = {int(x) for x in os.environ["NPC_ONLY"].split(",")}
        lst = [r for r in lst if r[0] in keep]
    open(out + "/INDEX.txt", "w").write(  # noqa: SIM115
        f"디버그 이동 — {spec} NPC {len(lst)}명 순회(제품 롬 아님)\n"
    )
    print("npcs", lst, flush=True)
    for i, x, y in lst:
        for k, (dx, dy, mv) in enumerate(
            (dx * n, dy * n, mv)
            for n in (1, 2)
            for dx, dy, mv in ((0, 1, "up"), (0, -1, "down"), (1, 0, "left"), (-1, 0, "right"))
        ):
            e.load(here)
            e.run(1)
            teleport(e, x + dx, y + dy)
            e.press(mv, 12, 6)
            pre = f"{out}/pre.png"
            e.shot(pre)
            e.press("circle", 6, 60)
            p = f"{out}/{name}_n{i:02d}_{k}.png"
            e.shot(p)
            g = green(p)
            d = float(np.abs(_gray(p) - _gray(pre)).mean())
            if g > 800 or D.window_open(e):
                print(i, x, y, "ui", k, g, round(d, 1), flush=True)
                for j in range(1, 11):  # 대화·선택지를 ○ 로 따라가며 한 장씩
                    e.press("circle", 6, 70)
                    q = f"{out}/{name}_n{i:02d}_{k}_s{j:02d}.png"
                    e.shot(q)
                    if j > 1 and float(np.abs(_gray(q) - _gray(p)).mean()) < 0.3:
                        os.remove(q)
                        break
                    p = q
                break
            os.remove(p)
        else:
            print(i, x, y, "nothing", flush=True)


if __name__ == "__main__":
    main()
