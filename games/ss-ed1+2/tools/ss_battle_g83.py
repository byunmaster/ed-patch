#!/usr/bin/env python3
"""ED2 그룹 83(최종장 이벤트 전투) 촬영 — 82 를 이기고 **같은 실행 안에서** 씬 45 래퍼로 83 을 부른다.

    .venv/bin/python tools/ss_battle_g83.py --cue <이미지.cue> --out <폴더> [--turns 15]

## 왜 이렇게
번호 83 은 진입 함수(`ED2.BIN 0x06037F44`)가 일반 초기화(파티 데이터 복사 84B·28B)를 건너뛰는 **연속 전투**다 — 직전 전투(82 고드윈 2세)가 남긴 상태를
이어받는다. 필드 상태에서 83 을 강제하거나 래퍼를 바로 불러도 몬스터 HP 가 0 이라 전투가 안 돌지만(2026-10-20 실측), 82 를 이기게 한 뒤 래퍼를 부르면
몬스터 번호 100(HP 8424)이 서고 명령 창이 뜬다. 래퍼 = `ED2SCN45.BIN` 파일 0x1338(번호를 RAM 표 `0x0609E41F + 20×색인` 첫 바이트에서 읽는다).
🔴 스테이트·RAM 쓰기는 조작용이다 — 문안은 이 캡처의 **화면**으로만 판정한다.
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ss_battle_sweep as B
import ss_headless as H
import ss_scene_sweep as S

TAB = 0x0609E41F  # 필드 적 개체 표(20B 칸) — 첫 바이트가 그룹 번호


def chain_start(cue):
    import common

    mm, fl = S.scene_files(common, cue)
    d45 = common.read_extent(mm, *fl["/BIN/ED2SCN45.BIN"])

    def start(h):
        # 필드 상태 → 스텁 설치 → 82 강제 → 이기기 → 래퍼로 83
        h.load(B_NAV[0])
        h.run(5)
        code, body = S.build_stub()
        S.verify_stub(code, body)
        h.poke(S.HOOK, code)
        for k in range(0, 0x20, 4):
            S.p32(h, S.MB + k, 0)
        h.poke(S.TICK, S.hook_patch())
        h.run(30)
        assert S.g32(h, S.MB + 20) > 0, "스텁이 안 불렸다"
        for a in B.GAME["sites"]:
            h.poke(a, bytes([B.GAME["op"], 82]))
        n = 0
        while B.be32(h.peek(B.MON + 0x1C, 4)) == 0 and n < 80:
            h.held = {H.BTN["right" if n % 2 == 0 else "left"]}
            h.run(40)
            h.held = set()
            h.run(5)
            n += 1
        if B.be32(h.peek(B.MON + 0x1C, 4)) == 0:
            return False
        for a in B.GAME["sites"]:
            h.poke(a, B.GAME["orig"])  # 더 이상 강제하지 않는다
        for t in range(0, 900, 3):  # 82 를 이긴다 — HP 1 로 묶고 공격 키
            B.fill_names(h, "ed2", t)
            if B.be32(h.peek(B.MON + 0x1C, 4)) > 1:
                h.poke(B.MON + 0x1C, struct.pack(">I", 1))
            h.run(3)
            if t % 45 == 0:
                h.press("c", 3, 0)
        h.poke(S.SCN_BASE, d45)
        h.poke(TAB, bytes([83]))
        S.p32(h, S.MB + 4, 0)
        S.p32(h, S.MB + 12, 0)
        S.p32(h, S.MB, S.SCN_BASE + 0x1338)
        for _ in range(40):
            h.run(30)
            if B.be32(h.peek(B.MON + 0x1C, 4)):
                return True
        return False

    return start


B_NAV = [None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cue", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--turns", type=int, default=15)
    ap.add_argument("--bkr", default=B.DEFAULT_BKR)
    a = ap.parse_args()
    B.GAME = B.GAMES["ed2"]
    B.FILL_NAMES = True
    so = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    os.makedirs(a.out, exist_ok=True)
    h = H.Harness(so, a.cue, a.out, bkr=a.bkr)
    nav = os.path.join(H.CACHE, "beetle-saturn", f"{B.GAME['state']}_{B.image_key(a.cue)}.state")
    if not os.path.exists(nav):
        B.boot_to_field(h)
        h.save(nav)
    B_NAV[0] = nav
    r = B.run_group(h, nav, 83, a.turns, a.out, B.inverse_map(), attempts=2, start=chain_start(a.cue))
    import json

    B.contact_sheet(os.path.join(a.out, "g83"))
    print(json.dumps(r, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
