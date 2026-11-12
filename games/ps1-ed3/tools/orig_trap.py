"""원판 디스크에서 「우리가 코드·자료 자리로 돌린 구간」이 실제로 실행되나 — 헤드리스 **덫 카운터** 점검 (11-07 관리자 결함 부류 알림).

    HEADLESS_DRC=disabled python3 tools/orig_trap.py --cue <원판.cue> --state <접촉 직전 헤드리스 상태> [--control] [--out <폴더>]

구간(R1·R2·SDK 오류 자리·죽은 함수)의 **모든 워드**를 `jal 0x80008000` 으로 덮는다. 0x80008000 의 스텁이 0x80007000 의 카운터를 1 올리고 돌아온다.
그 상태로 전투(접촉→자동전투→승리) · 필드 메뉴 투어 · 상점 메뉴·구매 목록 · 장 전환을 **주입으로** 돌리고(걷지 않는다 — 마스터 11-07) 카운터가 0 인지 본다.

🔴 **`HEADLESS_DRC=disabled` 가 필수다** — 기본(동적 변환 켬)에서는 덫이 안 먹는다(「헤드리스 JIT 덫」, 실측: 양성 대조가 0 으로 거짓).
   그래서 `--control` 은 **전투 개시 함수 0x8005FCF0 첫 워드에 같은 덫**을 심고 접촉하면 카운터가 올라가는지(실측 213) 본다 — 안 오르면 이 점검은 거짓이다.

주입 요령(이벤트 VM):
  · 버퍼 `D.BUF` 에 연산 바이트열 + `00 00`, `D.PTR`(0x800DD6F8)에 버퍼 주소 → 2~3프레임 뒤 PTR 을 0 으로 비운다(안 비우면 매 프레임 다시 돈다).
  · 상점 메뉴 = 연산 0x34 `34 <종류>` · 구매 목록 = 0x35 `35 <번호> <n> <품목 n바이트>` · 판매 창 = 0x36 `36 <n>` · 맵 이동 = 0x14 · 챕터 이동 = `14 02 FF <챕터>`.
  · 소지금(Pia) = u32 `0x800C11D0`. 소지품 주소는 아직 못 찾았다(구매·판매 핸들러가 함수 호출로 읽는다).
상태 파일은 git 밖 `.local/work/inbox/<게임>/` 에 둔다(원문·원본 RAM 포함).
"""

import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SETTLE", "0")
import dialog_harness as D
import headless_ps1 as H

REGIONS = [(0x8008A108, 428), (0x8008A428, 368), (0x8008CD94, 0x418), (0x8008DAD4, 1092)]
STUB_AT, CNT = 0x80008000, 0x80007000
STUB = [
    0x3C088000,
    0x8D097000,
    0x25290001,
    0xAD097000,
    0x03E00008,
    0,
]  # lui t0,0x8000 · lw t1,0x7000(t0) · addiu · sw · jr ra · nop
TRAP_WORD = 0x0C002000  # jal 0x80008000
PIA = 0x800C11D0
SHOP_LIST = bytes.fromhex(
    "34023504050a01761e0200"
)  # FT7010 의 실제 스크립트 꼴(상점 메뉴 + 구매 목록)


def arm(emu):
    emu.poke(STUB_AT, struct.pack("<6I", *STUB))
    emu.poke(CNT, b"\0\0\0\0")
    for a, n in REGIONS:
        emu.poke(a, struct.pack("<I", TRAP_WORD) * (n // 4))


def count(emu):
    return emu.u32(CNT)


def inject(emu, script, frames=3):
    emu.poke(D.BUF, script + b"\0\0")
    emu.poke(D.PTR, D.BUF.to_bytes(4, "little"))
    emu.run(frames)
    emu.poke(D.PTR, b"\0\0\0\0")


def contact(emu):
    emu.poke(0x800C05F8, struct.pack("<H", 999))
    emu.press("left", 200, 5)
    emu.press("up+left", 200, 5)
    emu.press("left", 120, 5)
    emu.press("circle", 4, 150)


def control(emu):
    """양성 대조 — 전투 개시 함수 첫 워드에 덫. 접촉하면 카운터가 올라야 한다."""
    emu.poke(STUB_AT, struct.pack("<6I", *STUB))
    emu.poke(CNT, b"\0\0\0\0")
    emu.poke(0x8005FCF0, struct.pack("<I", TRAP_WORD))
    contact(emu)
    emu.run(300)
    return count(emu)


def tour(emu, out):
    log = []

    def mark(s):
        log.append((s, count(emu)))
        print(s, count(emu), flush=True)

    arm(emu)
    contact(emu)
    mark("contact")
    for k in ("square", "down", "circle", "circle", "cross", "cross"):  # □ 창 → 자동전투
        emu.press(k, 20 if k != "down" else 10, 60)
    for _ in range(0, 6000, 60):
        emu.run(60)
        emu.poke(0x800C05F8, struct.pack("<H", 999))
    emu.shot(os.path.join(out, "battle.png"))
    mark("battle")
    for _ in range(12):
        emu.press("circle", 4, 70)
    emu.run(300)
    for k in ["circle", "down", "circle", "circle", "cross", "cross", "down", "circle", "cross", "cross", "down", "circle", "cross", "down", "circle", "cross", "cross", "cross"]:
        emu.press(k, 8, 40)
    mark("menu")
    emu.press("cross", 8, 60)
    emu.poke(PIA, struct.pack("<I", 9999))
    inject(emu, SHOP_LIST)
    emu.run(200)
    for k in ("up", "circle", "circle"):
        emu.press(k, 8, 70)
    emu.shot(os.path.join(out, "shop.png"))
    mark("shop")
    with open(os.path.join(out, "trap_log.json"), "w") as f:
        json.dump(log, f)
    return log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cue", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--out", default=".")
    ap.add_argument("--control", action="store_true")
    a = ap.parse_args()
    if os.environ.get("HEADLESS_DRC") != "disabled":
        raise SystemExit(
            "🔴 HEADLESS_DRC=disabled 로 돌려야 한다 — 기본 설정에서는 덫이 안 먹어 0 이 거짓이다"
        )
    emu = H.Emu(a.cue)
    emu.run(5)
    emu.load(a.state)
    emu.run(3)
    if a.control:
        n = control(emu)
        print("양성 대조 카운터", n)
        raise SystemExit(0 if n > 0 else 1)
    os.makedirs(a.out, exist_ok=True)
    log = tour(emu, a.out)
    raise SystemExit(1 if any(n for _s, n in log) else 0)


if __name__ == "__main__":
    main()
