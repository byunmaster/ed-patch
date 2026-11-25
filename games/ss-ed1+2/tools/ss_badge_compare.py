#!/usr/bin/env python3
"""**ED2 몬스터 상태 배지 — 원판과 우리 롬을 같은 상태로 띄워 나란히(3배) 찍는다**(헤드리스 하네스, 롬·이미지는 안 고친다 — RAM 쓰기뿐).

    python3 tools/ss_badge_compare.py --out <폴더> --which orig|ours|pair [--group 62]

몬스터 표(`0x0609F560`, 스트라이드 104)의 상태 바이트 `+0x49 독 · +0x4A 묵 · +0x4B 주 · +0x4C 잠 · +0x4D 혼`(칸마다 하나 — 값은 1, 2~는 배지 없음)을
첫 몬스터에 쓰고 **그 몬스터 HP 가 바뀌는 동작(공격)** 을 한 번 일으켜 라벨을 다시 그리게 한 뒤 화면을 찍는다(devlog 10-10 「ED2 상태 비트 맵」).
파티 기절은 아트라스 전투 사본(`0x0609E690`) `+0x46 = 1`.
같은 시드(같은 그룹·같은 입력)로 원판(`common.ORIG_CUE`)과 우리 빌드를 한 번씩 돌려 상태마다 한 장씩 찍고, 배지 부분을 3배로 키워 나란히 붙인다.
"""

import argparse
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import ss_battle_sweep as B
import ss_headless as H

STATUS = (("독", 0x49), ("묵", 0x4A), ("주", 0x4B), ("잠", 0x4C), ("혼", 0x4D))
PARTY = tuple((f"p{o:02x}", ("party", o)) for o in range(0x40, 0x50) if o != 0x46)  # 파티 상태 칸 탐색 — 아트라스 전투 사본 +0x46 = 기절(실측), 나머지는 미확인


def be32(b):
    return int.from_bytes(b, "big")


def shoot(cue, group, outdir, tag, party=False):
    """`cue` 이미지로 상태마다 한 장 — `[(상태, 프레임)]`."""
    so = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    h = H.Harness(so, cue, outdir, bkr=B.DEFAULT_BKR)
    nav = os.path.join(H.CACHE, "beetle-saturn", f"ed2_field_{B.image_key(cue)}.state")
    if not os.path.exists(nav):
        B.boot_to_field(h)
        h.save(nav)
    out = []
    for name, off in (("없음", None),) + (PARTY if party else STATUS + (("기절", "faint"),)):
        assert B.start_battle(h, nav, group), "조우 안 걸림"
        n = 0
        while not B.is_menu(h.frame) and n < 400:
            h.run(3)
            n += 3
            for pc in B.PARTY_COPIES:
                h.poke(pc + 4, h.peek(pc + 8, 4))
        B.fill_names(h, "ed2")
        h.run(30)
        if off == "faint":
            h.poke(B.PARTY + 0x46, b"\x01")
        elif isinstance(off, tuple):
            h.poke(B.PARTY + off[1], b"\x01")
        elif off is not None:
            h.poke(B.MON + off, b"\x01")
        # 상태 라벨은 그 몬스터 HP 가 바뀌어야 다시 그려진다 — 공격 한 번
        for b in ("up", "up", "left", "left", "right", "right", "c"):
            h.press(b, 4, 8)
        # 공격 문구가 지나가고 다음 메뉴가 올 때까지 — 도중 프레임 중 메뉴 화면을 쓴다
        n = 0
        got = None
        while n < 1500:
            for pc in B.PARTY_COPIES:
                h.poke(pc + 4, h.peek(pc + 8, 4))
            h.run(3)
            n += 3
            if n > 150 and B.is_menu(h.frame):
                got = h.frame.copy()
                break
        out.append((name, got if got is not None else h.frame.copy()))
        Image.fromarray(out[-1][1]).save(os.path.join(outdir, f"{tag}_{name}.png"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--group", type=int, default=62)
    ap.add_argument("--cue", default=None)
    ap.add_argument("--party", action="store_true", help="몬스터 대신 파티 상태 칸(+0x40~0x4F)을 하나씩 1 로 써 본다")
    ap.add_argument("--which", choices=("orig", "ours", "pair"), required=True, help="코어를 한 프로세스에서 둘 못 띄운다(세그폴트) — orig·ours 를 따로 돌리고 pair 로 붙인다")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.which == "orig":
        shoot(common.ORIG_CUE, a.group, a.out, "orig", a.party)
    elif a.which == "ours":
        shoot(a.cue or os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.cue"), a.group, a.out, "ours", a.party)
    else:
        import glob

        for fo in sorted(glob.glob(os.path.join(a.out, "orig_*.png"))):
            name = os.path.basename(fo)[5:-4]
            fu = os.path.join(a.out, f"ours_{name}.png")
            io, iu = Image.open(fo).convert("RGB"), Image.open(fu).convert("RGB")
            w, hh = io.size
            sheet = Image.new("RGB", (w * 3 * 2 + 8, hh * 3), (40, 40, 40))
            sheet.paste(io.resize((w * 3, hh * 3), Image.NEAREST), (0, 0))
            sheet.paste(iu.resize((w * 3, hh * 3), Image.NEAREST), (w * 3 + 8, 0))
            sheet.save(os.path.join(a.out, f"pair_{name}.png"))
    print("완료", a.which)


if __name__ == "__main__":
    main()
