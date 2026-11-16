"""창 호출별로 어떤 문자열을 그리는지 잡는 런타임 덫(시험 전용, 제품 롬 불변 — RAM 에만 쓴다).

두 함수 입구에 RAM 스텁을 꽂아 호출을 링 로그에 쓴다(로그 한 칸 32B):
  창 열기 `0x80015B20(a0=x, a1=y, a2=열, a3=행)`  → tag 1, 호출 위치 = ra-8
  글 그리기 `0x80017334(a0=창 구조체, a1=문자열 포인터, …)` → tag 2, 창 구조체의 x·y·열·행을 같이 적는다
창 구조체 x·y 는 인자에서 160·120 을 뺀 값이다(`ui_tour.wins`). 열기 이벤트와 (x,y,열) 로 이어 열기 호출 위치별 문자열 집합을 낸다.
⚠ 상태를 불러오면 RAM 이 되돌아가 스텁이 사라진다 — `install` 을 로드 뒤마다 부르고 `drain` 을 로드 앞마다 부른다.
헤드리스 코어는 `dialog_harness` 를 import 하면 drc 가 꺼진다(켜져 있으면 덫이 안 걸려 「0회」 거짓이 난다) — 양성 대조: 늘 지나는 창이 로그에 있어야 한다.
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness as D  # noqa: F401,E402
import headless_ps1 as H  # noqa: E402
from mipsasm import asm  # noqa: E402

LOG = 0x801B3000
CAP = 1500  # 칸 128B × 1500 = 192KB (창 구조체 0x801EF9C8 앞에서 끝난다)
FN_OPEN, FN_DRAW = 0x80015B20, 0x80017334
STUBS = {FN_OPEN: 0x801B2000, FN_DRAW: 0x801B2200}
EXTRA_FNS = [int(x, 16) for x in os.environ.get("WT_EXTRA", "").split(",") if x]  # 다른 그리기 경로 입구(태그 3부터) — 인자 a0~a3 와 ra 만 적는다
for _i, _f in enumerate(EXTRA_FNS):
    STUBS[_f] = 0x801B2400 + 0x100 * _i

_COMMON = """
    lui $t0, 0x801b
    ori $t0, $t0, 0x3000
    lw $t1, 0($t0)
    nop
    slti $t8, $t1, {cap}
    beq $t8, $zero, SKIP
    nop
    addiu $t1, $t1, 1
    sw $t1, 0($t0)
    sll $t2, $t1, 7
    addu $t2, $t2, $t0
    sw $a0, 0($t2)
    sw $a1, 4($t2)
    sw $a2, 8($t2)
    sw $a3, 12($t2)
    addiu $t3, $zero, {tag}
    sw $t3, 16($t2)
    sw $ra, 20($t2)
{extra}
SKIP:
"""
_STR_COPY = """
    srl $t7, $a1, 21
    addiu $t7, $t7, -0x400
    sltiu $t8, $t7, 4
    beq $t8, $zero, SKIP
    nop
    addiu $t9, $zero, 0
CP:
    addu $t7, $a1, $t9
    lw $t8, 0($t7)
    nop
    addu $t7, $t2, $t9
    sw $t8, 32($t7)
    addiu $t9, $t9, 4
    slti $t8, $t9, 48
    bne $t8, $zero, CP
    nop
"""
_DRAW_EXTRA = """
    lhu $t3, 2($a0)
    lhu $t4, 4($a0)
    lhu $t5, 6($a0)
    lhu $t6, 8($a0)
    sh $t3, 24($t2)
    sh $t4, 26($t2)
    sh $t5, 28($t2)
    sh $t6, 30($t2)
"""


def _stub(fn, tag, o1, o2):
    text = _COMMON.format(cap=CAP, tag=tag, extra=(_DRAW_EXTRA + (_STR_COPY if tag in (2, 3) else "")) if tag in (2, 3, 4) else "")
    words = list(asm(text, STUBS[fn])[0])
    words += [o1, o2, 0x08000000 | (((fn + 8) >> 2) & 0x3FFFFFF), 0]
    return b"".join(w.to_bytes(4, "little") for w in words)


def install(e):
    e.poke(LOG, bytes(8))
    for tag, fn in [(1, FN_OPEN), (2, FN_DRAW)] + [(3 + i, f) for i, f in enumerate(EXTRA_FNS)]:
        o1, o2 = struct.unpack("<2I", e.peek(fn, 8))
        e.poke(STUBS[fn], _stub(fn, tag, o1, o2))
        e.poke(fn, (0x08000000 | ((STUBS[fn] >> 2) & 0x3FFFFFF)).to_bytes(4, "little") + b"\0\0\0\0")


def drain(e):
    """로그를 읽어 [(tag, a0, a1, a2, a3, ra, x, y, 열, 행, 문자열 코드열|None)] — 문자열은 지금 RAM 에서 읽는다(표 문자열은 정적)."""
    n = struct.unpack("<I", e.peek(LOG, 4))[0]
    out = []
    for k in range(1, min(n, CAP) + 1):
        a0, a1, a2, a3, tag, ra = struct.unpack("<6I", e.peek(LOG + 128 * k, 24))
        x, y, c, r = struct.unpack("<hhHH", e.peek(LOG + 128 * k + 24, 8))
        codes = None
        if tag in (2, 3) and 0x80000000 <= a1 < 0x80800000:
            raw = struct.unpack("<24H", e.peek(LOG + 128 * k + 32, 48))  # 호출 시점에 복사해 둔 문자열(스택 버퍼도 안 사라진다)
            codes = []
            for v in raw:
                if v in (0, 0x8000, 0x8002, 0xFFFF):
                    break
                codes.append(v)
        out.append((tag, a0, a1, a2, a3, ra, x, y, c, r, codes, e.peek(LOG + 128 * k + 32, 48).hex() if tag in (2, 3) else None))
    e.poke(LOG, bytes(4))
    return out


def link(events):
    """[(열기 호출 위치, 열기 인자(x,y,열,행), 문자열 코드열…)] — 그리기 이벤트를 가장 가까운 앞선 같은 (x,y,열) 열기에 잇는다."""
    opens, res = [], {}
    for ev in events:
        tag, a0, a1, a2, a3, ra, x, y, c, r, codes = ev
        if tag == 1:
            opens.append((ra - 8, None))
            res.setdefault(ra - 8, {"args": (a0, a1, a2, a3), "strs": set(), "draws": 0})
        elif tag == 2 and codes is not None:
            for site, _a in reversed(opens):
                st = res[site]["args"]
                if (st[0] - 160) == x and (st[1] - 120) == y and (st[2] & 0xFF) == c:
                    res[site]["strs"].add(tuple(codes))
                    res[site]["draws"] += 1
                    break
    return res


def main():
    """사용: wintrace.py <cue> <card.mcr> <출력.json>  — 필드 △ 메뉴 항목 순회(ui_tour 와 같은 입력)."""
    import json

    cue, card, out = sys.argv[1:4]
    import shutil

    tmp = "/tmp/claude-0/card_wt.mcr"
    shutil.copy(card, tmp)
    e = H.Emu(cue, card=tmp)
    e.run(600)
    for _ in range(11):
        e.press("circle", 8, 60)
        e.run(120)
    e.run(200)
    e.press("triangle", 8, 40)
    e.run(40)
    base = out + ".state"
    e.save(base)
    allev = []
    for i in range(5):
        e.load(base)
        e.run(1)
        install(e)
        for _ in range(i):
            e.press("down", 8, 20)
        for _k in range(4):
            e.press("circle", 8, 40)
            e.run(30)
            for _ in range(2):
                e.press("down", 8, 15)
        allev += drain(e)
    json.dump(allev, open(out, "w"))
    print("이벤트", len(allev), "열기", sum(1 for x in allev if x[0] == 1), "그리기", sum(1 for x in allev if x[0] == 2))


if __name__ == "__main__":
    main()
