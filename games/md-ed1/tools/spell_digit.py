"""주문 이름 버퍼(`$FF3450`)의 레벨 숫자를 **반각**으로 — 「레지나１을」(전각 숫자, 좌우 여백) → 「레지나1을」(마스터 10-10, PS1 꼴).

`$3526` 이 주문 이름 버퍼를 만든다 — 이름 8B 복사 뒤 **레벨을 전각 숫자 워드**(`0x8250 + 레벨-1`)로 쓰고 `06` 을 붙인다(14B):

    3570  303C 8250        move.w #$8250,d0
    3574  D02C 0010        add.b  $10(a4),d0
    3578  34C0             move.w d0,(a2)+
    357A  14FC 0006        move.b #6,(a2)+

같은 14B 에 **반각 숫자 + 06 을 한 워드로** 쓰고 포인터는 한 칸 더 민다(뒤 필드 오프셋이 그대로여야 한다):

    3570  102C 0010        move.b $10(a4),d0        레벨-1
    3574  E148             lsl.w  #8,d0
    3576  0640 3106        addi.w #$3106,d0         (레벨-1+0x31)<<8 | 06
    357A  34C0             move.w d0,(a2)+
    357C  524A             addq.l #1,a2             +10 칸은 건드리지 않고 건너뜀

⚠ 이 버퍼는 필드 메뉴의 주문 목록도 쓴다 — 전각 폭이 반각으로 줄어 목록 정렬이 바뀔 수 있다(화면 확인 필요).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

AT = 0x3570
OLD = bytes.fromhex("303c8250d02c001034c014fc0006")
NEW = bytes.fromhex("102c0010e1480640310634c0524a")
assert len(OLD) == len(NEW) == 14


def plan() -> list[tuple[str, int, bytes]]:
    return [("spell-digit", AT, NEW)]


def check(d: bytes) -> None:
    if d[AT : AT + len(OLD)] != OLD:
        raise SystemExit("spell_digit: 0x3570 의 원본 명령이 다르다 — 주문 레벨 숫자 자리가 바뀌었다")
    print("  주문 레벨 숫자 — 전각 → 반각(14B 제자리)")


if __name__ == "__main__":
    check(common.rom())
