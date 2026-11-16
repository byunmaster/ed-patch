"""마스터가 직접 볼 상점 세이브 만들기(시험 전용, 제품 롬 불변) — 맵 이동·좌표·RAM 으로 서고 게임 안 세이브 메뉴로 저장한 뒤 메모리카드 영역을 `.mcr` 로 읽어 낸다.

   sh scripts/capture.sh python3 tools/make_shop_save.py <cue> <card.mcr> <맵:방향:인자> <NPC 슬롯|-> <피스카> <출력.mcr> <출력폴더> [키열]
카드는 사본에 올려 쓰고 원본은 안 건드린다. 키열 = 세이브 메뉴 조작(쉼표 목록) — 기본은 △ → 시스템 → 세이브 순서를 추정한 값이라 화면 확인으로 맞춘다.
"""

import ctypes as C
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import debug_warp as W  # noqa: E402
import debug_warp_npc as N  # noqa: E402
import dialog_harness as D  # noqa: E402

PISC = 0x80095C58


def card_bytes(e):
    mp, ms = e.core.retro_get_memory_data(0), e.core.retro_get_memory_size(0)
    return C.string_at(mp, ms)


def main():
    cue, card, spec, npc, pisc, outmcr, out = sys.argv[1:8]
    keys = sys.argv[8].split(",") if len(sys.argv) > 8 else []
    os.makedirs(out, exist_ok=True)
    tmp = out + "/card.mcr"
    shutil.copy(card, tmp)
    e = D.make_state(cue, tmp, out + "/base.state")
    name, d, a = spec.split(":")
    W.warp(e, name, int(d), bytes.fromhex(a), settle=200)
    if npc != "-":
        lst = {i: (x, y) for i, x, y in N.npcs(e)}
        x, y = lst[int(npc)]
        dx, dy, mv = (int(v) if v.lstrip("-").isdigit() else v for v in os.environ.get("NPCDIR", "0,1,up").split(","))
        N.teleport(e, x + dx, y + dy)
        e.press(mv, 12, 6)  # NPCDIR=dx,dy,바라볼 방향 — 울트 무기점은 0,-1,down(위에서 아래로)
    e.poke(PISC, int(pisc).to_bytes(4, "little"))
    e.run(30)
    e.shot(out + "/pos.png")
    before = card_bytes(e)
    for i, k in enumerate(keys):
        e.press(k, 8, 40)
        e.run(30)
        e.shot(f"{out}/k{i:02d}_{k}.png")
    if os.environ.get("FIND"):  # 환전 뒤 화면에 뜬 값(예 499995)을 RAM 에서 찾는다 — 소지금 주소 탐색
        import struct

        ram = e.peek(0x80000000, 0x200000)
        v = int(os.environ["FIND"])
        for fmt in ("<I", "<H"):
            if fmt == "<H" and v > 0xFFFF:
                continue
            pat = struct.pack(fmt, v)
            p0 = -1
            while (p0 := ram.find(pat, p0 + 1)) >= 0:
                print("FIND", fmt, hex(0x80000000 + p0), flush=True)
    after = card_bytes(e)
    print("카드 바뀐 바이트", sum(1 for p, q in zip(before, after, strict=False) if p != q), flush=True)
    open(outmcr, "wb").write(after)


if __name__ == "__main__":
    main()
