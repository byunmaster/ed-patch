"""보스 직전 세이브에서 엔딩까지 이어 돌리기(시험 전용) — 새로 띄워 타이틀 「계속해서 시작」→ 로드 → 위로 걸어 이벤트 → 발두스 전투(보스 HP 칸 0x801FF9AA 에 값 씀) → 승리 → 엔딩 → Fin.

   sh scripts/capture.sh python3 tools/boss_save_chain.py <cue> <card.mcr> <출력폴더>
환경: HP(보스 HP 에 쓸 값, 기본 0) · POST(전투 뒤 ○ 횟수).
"""

import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness  # noqa: F401  (경로·drc 설정)
import headless_ps1 as H

BOSS = 0x801FF9AA
HERO = 0x801FF81A


def main():
    cue, card, out = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    shutil.copy(card, out + "/card.mcr")
    e = H.Emu(cue, card=out + "/card.mcr")
    e.run(600)
    for j in range(12):  # 타이틀 → 계속해서 시작 → 로드 → 페이지(PAGE2=1 이면 아래로 한 번) 슬롯1 → 예
        e.press("circle", 8, 60)
        e.run(120)
        if j == 5 and os.environ.get("PAGE2"):
            e.press("down", 8, 60)
            e.run(120)
            e.shot(out + "/a_page2.png")
    e.shot(out + "/a00_loaded.png")
    k = 0
    for i in range(8):  # 위로 몇 걸음 — 이벤트가 걸린다
        e.press("up", 10, 6)
        if i % 2 == 0:
            e.shot(f"{out}/a01_up{i}.png")
    battle = False
    nb = 0  # 몇 번째 전투인가 — 1번째 오크툼(위로 5), 2번째 발두스(오른쪽 7·위로 5)
    walks = [os.environ.get("WALK1", "up*5"), os.environ.get("WALK2", "right*7,up*5")]
    for i in range(int(os.environ.get("POST", "900"))):
        pat = os.environ.get("PAT", "circle").split(",") if battle and nb >= 2 else ["circle"]
        e.press(pat[i % len(pat)], 6, 50)  # PAT=발두스전의 입력 열(쉼표) — 대기 칸 등을 시험
        if i % 5 == 0:
            e.shot(f"{out}/b{k:04d}.png")
            k += 1
        if os.environ.get("DUMP") and i % 20 == 0:
            for u in range(6):
                r = struct.unpack("<5H", e.peek(0x801FF9A0 + 50 * u, 10))
                rr = struct.unpack("<2H", e.peek(0x801FF9A0 + 50 * u + 6, 4))
                print(i, u, [hex(x) for x in r[:2]], rr, struct.unpack("<H", e.peek(0x801FF9A0 + 50 * u + 10, 2))[0], flush=True)
        hd, uid = struct.unpack("<2H", e.peek(0x801FF9A0, 4))
        v = struct.unpack("<H", e.peek(BOSS, 2))[0]
        if hd == 0xC000 and uid == 1:  # 전투 중(유닛 배열 머리) — 1번 유닛(보스) HP 를 쓴다
            if not battle and v > 0:
                battle = True
                nb += 1
                print("전투 감지", i, "보스 HP", v, flush=True)
                for _ in range(10):
                    e.press("cross", 6, 20)
                e.run(
                    60 if nb < 2 else int(os.environ.get("SETTLE", "600"))
                )  # 발두스 전투는 시작 연출이 길다 — 입력이 먹힐 때까지 기다린다
                for tok in [] if (nb >= 2 and os.environ.get("NOWALK")) else walks[min(nb - 1, 1)].split(","):  # 보스 곁까지 걷기(방향키) — NOWALK=1 이면 발두스전은 걷지 않고 바로 HP 를 쓴다
                    d, m = tok.split("*")
                    for _ in range(int(m)):
                        e.poke(HERO, struct.pack("<H", 9999))
                        e.press(d, 12, 30)
                        e.run(30)
                        e.shot(f"{out}/w{k:04d}.png")
                        k += 1
                e.poke(BOSS, struct.pack("<H", int(os.environ.get("HP", "1"))))
            e.poke(HERO, struct.pack("<H", 9999))
            if nb >= 2 and os.environ.get("REHP"):
                e.poke(BOSS, struct.pack("<H", int(os.environ.get("HP", "1"))))
        elif battle:
            battle = False  # 전투가 끝났다 — 다음 전투를 기다린다
            print("전투 끝", i, flush=True)
    print("끝", k, flush=True)


if __name__ == "__main__":
    main()
