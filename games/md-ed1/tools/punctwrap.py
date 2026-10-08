"""반각 부호(`. , ! ?`)는 줄 끝에서 몇 px 더 허용 — 엔진 자동 줄바꿈의 1px 꺾임을 없앤다(마스터 10-08, 엔딩 0004).

    python3 tools/punctwrap.py --check   # 후킹 자리가 원본 그대로인가
    python3 tools/punctwrap.py --asm     # 손인코딩 기계어를 디스어셈블로 되읽어 출력

## 왜

렌더러는 글자를 그리기 **전에** `$A990`(들어가나?)을 부르고 `$A9B8` 이 한계를 낸다:

    $A9B8  move.l d7,d1 ; subi.b #13,d1 ; cmp.b $FF2018.l,d1 ; rts     커서 바이트 > 행 폭 − 13 이면 넘침(캐리)

글자 시작이 `행 폭 − 13` 바이트(= 창 폭 − 26px)를 넘으면 그 글자가 다음 줄로 간다. 전각 글자(14px)에 맞춘 여유라
**반각 부호 한 글자(7px)가 1px 넘는 것만으로** 줄이 꺾인다(엔딩 0004 의 끝 「.」, 원판엔 없는 제약 꼴).
`$A990` 의 호출자는 둘뿐(`$985E` 전각 · `$98C6` 반각)이고 `$A9B8` 의 호출자는 `$A99C` 하나 — 반각 경로의 `d0` 는 글자 바이트다.

## 고치는 법

`$A9BE` 의 `cmp.b $FF2018.l,d1`(6B)을 `jmp 꼬리.l`(6B)로 바꾸고, 꼬리에서 `d0` 가 `. , ! ?` 면 `d1` 에 2바이트(4px)를 더한 뒤
원래 비교를 하고 `rts` 한다(복귀 주소는 `$A99C` 그대로). 허용 4px 는 안전하다 — 여유 26px 중 부호(7px)가 시작에서 4px 더 가도
창 끝에서 15px 이상 남는다. 전각 글자·숫자·가나 경로는 `d0` 가 달라 원래 비교 그대로다.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

SITE = 0xA9BE  # cmp.b $ff2018.l,d1 (6B)
ORIG = bytes.fromhex("b23900ff2018")
SLACK_BYTES = 2  # 4px
PUNCT = (0x2E, 0x2C, 0x21, 0x3F)  # . , ! ?
CODE_LEN = 0x30


def code() -> bytes:
    b = bytearray()
    for c in PUNCT[:-1]:
        b += struct.pack(">HH", 0x0C00, c)  # cmpi.b #c,d0
        b += bytes([0x67, 0x00])  # beq.s hit (변위는 아래에서)
    b += struct.pack(">HH", 0x0C00, PUNCT[-1])  # cmpi.b #?,d0
    b += bytes([0x66, 0x02])  # bne.s plain (addq 한 개 건너뜀)
    hit = len(b)
    b += struct.pack(">H", 0x5000 | (SLACK_BYTES << 9) | 0x01)  # addq.b #2,d1
    plain = len(b)
    b += bytes.fromhex("b23900ff2018")  # cmp.b $ff2018.l,d1
    b += struct.pack(">H", 0x4E75)  # rts
    # beq.s 변위 = hit − (그 명령 다음 자리)
    for i, pos in enumerate((4, 10, 16)):
        assert b[pos] == 0x67
        b[pos + 1] = hit - (pos + 2)
    assert len(b) <= CODE_LEN, len(b)
    return bytes(b)


def plan(at: int) -> list[tuple[str, int, bytes]]:
    return [
        ("punct-code", at, code()),
        ("punct-site", SITE, b"\x4e\xf9" + struct.pack(">I", at)),
    ]


def check(d: bytes) -> None:
    if d[SITE : SITE + 6] != ORIG:
        raise SystemExit(f"후킹 자리 {SITE:#x} 가 `cmp.b $ff2018.l,d1` 이 아니다")
    print(f"  반각 부호 줄 끝 허용 — 후킹 1 · 기계어 {len(code())}B (+{SLACK_BYTES * 2}px)")


if __name__ == "__main__":
    if "--asm" in sys.argv:
        import josa

        print("\n".join(josa.verify(code(), 0x1F0000)))
    else:
        check(common.rom())
