"""전투 시스템 문구(승리 보상·경험·레벨업) 촬영 탐침(시험 전용) — 세이브 03 에서 필드 전투에 들어가 **적 유닛 HP 칸(0x801FF9A0 배열)을 0 으로 써** 승리 연출을 부른다.

   sh scripts/capture.sh python3 tools/battle_msg_probe.py <cue> <card.mcr> <슬롯 내림> <출력폴더>
환경: EXP(무술 경험 u16 을 넣을 값 — 문턱 직전이면 레벨업 문구가 뜬다) · MAXTRY(걸음 수)
"""

import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import replay

ARR = 0x801FF9A0


def units(e):
    """필드 전투 적 유닛 — 헤더 0xC000 칸을 램 한 구역에서 찾는다(적 수에 따라 시작 자리가 달라진다). [(주소, id, 최대 HP, 현재 HP)]"""
    blk = e.peek(0x801FF800, 0x800)
    out = []
    for o in range(0, 0x7C0, 2):
        if struct.unpack_from("<H", blk, o)[0] == 0xC000 and struct.unpack_from("<H", blk, o + 2)[0] in range(1, 9):
            out.append((0x801FF800 + o, struct.unpack_from("<H", blk, o + 2)[0], struct.unpack_from("<H", blk, o + 6)[0], struct.unpack_from("<H", blk, o + 10)[0]))
    return out


def main():
    cue, card, slot, out = sys.argv[1:5]
    os.makedirs(out, exist_ok=True)
    tmp = out + "/card.mcr"
    shutil.copy(card, tmp)
    e = replay.boot(cue, tmp, int(slot))
    if os.environ.get("EXP"):
        e.poke(0x8007BA44, struct.pack("<H", int(os.environ["EXP"])))
    seq = ["right"] * 3 + ["down"] * 3 + ["right"] * 3 + ["up"] * 3
    e.shot(f"{out}/00_boot.png")
    for i in range(13):  # auto_battle(10-31)과 같은 입력 — 필드 적 쪽으로 걷는다
        e.press(seq[i % 12], 45, 4)
    e.shot(f"{out}/01_after13.png")
    for i in range(int(os.environ.get("MAXTRY", "12"))):
        e.press("down", 100, 4)
        e.run(int(os.environ.get("WAIT", "120")))
        e.shot(f"{out}/d{i:02d}.png")
        us = units(e)
        if us:
            print("전투", i, us, flush=True)
            break
    else:
        e.shot(f"{out}/02_nofind.png")
        print("전투 못 찾음")
        return
    e.shot(f"{out}/a_battle.png")
    # 적 HP 를 0 으로 쓰고 ○ 로 영웅이 행동하게 한다 — 승리 문구(보상·경험·레벨업)를 찍는다
    def exps():
        return struct.unpack("<2H", e.peek(0x8007BA44, 2) + e.peek(0x8007BA48, 2))

    print("경험(무술·마술) 전", exps(), flush=True)
    if os.environ.get("WAITMODE"):  # 영웅은 대기만 — 적이 다가와 치는 적 행동·피해 문구를 찍는다(영웅 HP 는 매번 9999 로 써 둔다)
        k = 0
        for _t in range(int(os.environ["WAITMODE"])):
            e.poke(0x801FF81A, struct.pack("<H", 9999))
            e.press("up", 6, 10)
            e.press("circle", 6, 10)
            for _ in range(int(os.environ.get("SHOTS", "5"))):
                e.run(int(os.environ.get("STEP", "20")))
                e.shot(f"{out}/w{k:03d}.png")
                k += 1
            if not units(e):
                print("전투 끝", _t, flush=True)
                break
        return
    hp_val = int(os.environ.get("EHP", "0"))
    for a, _uid, _mx, _hp in units(e):
        e.poke(a + 10, struct.pack("<H", hp_val))
    if os.environ.get("AUTO"):  # EHP=1 이면 영웅이 직접 쳐서 처치 — 경험·레벨업 문구가 뜬다(`ending_run.auto_turns` 로 적에게 다가가 공격)
        import ending_run

        os.environ.setdefault("BUFF", "120")
        ending_run.auto_turns(e, out, int(os.environ["AUTO"]))
        return
    k = 0
    for _j in range(int(os.environ.get("POST", "14"))):  # 대기 → ○ 짝을 되풀이하며 쪽마다 촬영 — 승리 창은 ○ 두세 번에 사라진다
        e.press("up", 6, 10)
        e.press("circle", 6, 10)
        for _ in range(int(os.environ.get("SHOTS", "6"))):
            e.run(int(os.environ.get("STEP", "12")))
            e.shot(f"{out}/v{k:03d}.png")
            k += 1
        print("경험 후", _j, exps(), flush=True)
    return
    # 적 = 맨 앞부터 영웅 앞까지 — 영웅 id 를 모르니 처음에는 읽기만 하고 모든 유닛 정보를 남긴다
    e.run(120)
    e.shot(f"{out}/a_battle2.png")
    print(units(e), flush=True)


if __name__ == "__main__":
    main()
