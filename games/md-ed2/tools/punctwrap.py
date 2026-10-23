"""반각 부호(`. , ! ?`)는 줄 끝에서 몇 px 더 허용 — 엔진 자동 줄바꿈의 1px 꺾임을 없앤다(마스터 10-08, 엔딩 0004).

    python3 tools/punctwrap.py --check   # 후킹 자리가 원본 그대로인가
    python3 tools/punctwrap.py --asm     # 손인코딩 기계어를 디스어셈블로 되읽어 출력

## 왜

렌더러는 글자를 그리기 **전에** `$A990`(들어가나?)을 부르고 `$A9B8` 이 한계를 낸다:

    $A9B8  move.l d7,d1 ; subi.b #13,d1 ; cmp.b $FF2018.l,d1 ; rts     커서 바이트 > 행 폭 − 13 이면 넘침(캐리)

글자 시작이 `행 폭 − 13` 바이트(= 창 폭 − 26px)를 넘으면 그 글자가 다음 줄로 간다. 전각 글자(14px)에 맞춘 여유라
**반각 부호 한 글자(7px)가 1px 넘는 것만으로** 줄이 꺾인다(엔딩 0004 의 끝 「.」, 원판엔 없는 제약 꼴).
`$A990` 의 호출자는 둘뿐(`$985E` 전각 · `$98C6` 반각)이고 `$A9B8` 의 호출자는 `$A99C` 하나 — 반각 경로의 `d0` 는 글자 바이트다.

## 금칙 걸기(hang) 판정을 고친다 — 줄 끝 「!!」 둘째가 줄 머리 왼쪽에 그려지던 결함(마스터 10-20, qa 후보 2)

엔진은 줄 끝 넘침에서 **금칙 표**(`$C9F2`: `、。？！っッ` · ASCII `! ?` · 반각 `｡､ｯ`)의 글자를 줄바꿈 없이 그 자리에 **건다**(`$C9B8`, 호출자 `$C982` 하나).
건다/못 건다 판정 `$CA1E` 는 `d7`(= 행 폭)을 보게 짜였는데 `$C9B8` 이 `d7` 을 표 반복 카운터로 덮어써서(`move.l #$15,d7`) 항상 「건다」가 나온다.
건 글자는 한계가 없어, 반각 `!`·`?` 가 이어지면 버퍼 행 폭(112B)을 넘는 자리부터 **다음 스캔 행 맨 앞(= 화면의 줄 맨 왼쪽)** 으로 감긴다(`.`·`,` 는 표에 없어 정상 줄바꿈).
어절 줄넘김·punctwrap 둘 다 끈 롬에서도 같다 — 원판 엔진 자체의 성질(반각 부호 열 개를 이은 시험 줄로 재현).
고침: 카운터를 d3 로 옮기고(d7 보존), 한계를 `행 폭 − HANG_ROOM` 으로 하며, 못 걸면 공백으로 바꿔 그리지 않고 **줄바꿈**(캐리 세트)으로 보낸다 →
둘째 부호가 한계를 넘으면 어절 줄넘김이 앞 어절을 부호째 다음 줄로 보낸다. 한 개·두 개 부호가 줄 안에 들어가는 곳은 원래대로 걸린다.

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

SITE = 0xC9B0  # cmp.b $ff2018.l,d1 (6B)
ORIG = bytes.fromhex("b23900ff2018")
SLACK_BYTES = 2  # 4px
PUNCT = (0x2E, 0x2C, 0x21, 0x3F)  # . , ! ?
CAPTION_PITCH = 0x0E  # 자막 피치 14 — `$FF2014` (md-ed2 자막은 피치 14, 숫자 덩이만 잠깐 18)
CAPTION_EXTRA_BYTES = 7  # 자막에서만 +14px 더(합 9B=18px: 시작 214→232px) — 「사람들은 아트라스 왕자를 사랑하고,」 한 줄(231px)
CODE_LEN = 0x30
HANG_ROOM = 9  # 걸기(hang)는 커서 ≤ 행 폭 − 9B(18px) 일 때만 — 반각 부호(3B) + 잉크 번짐(`?` 는 한 열 더 넓다)이 버퍼 행 폭 안에 들어가는 끝
# (자리, 원본, 새 바이트, 뜻) — `$C9B8` 금칙 걸기 판정 고치기(아래 docstring)
HANG_PATCHES = (
    (0xC9BE, "2e3c00000015", "263c00000015", "표 반복 카운터 d7 → d3 (d7 은 행 폭이다)"),
    (0xC9D0, "51cffff2", "51cbfff2", "dbra d7 → dbra d3"),
    (0xCA20, "04010010", f"0401{HANG_ROOM:04x}", f"걸기 한계 행 폭 − 16 → − {HANG_ROOM}"),
    (
        0xC9E8,
        "303c0020023c00fe",
        "003c00014e714e71",
        "못 걸면 공백으로 바꿔 그리던 것 → 줄바꿈(캐리 세트, d0 는 그대로)",
    ),
)


def code() -> bytes:
    b = bytearray()
    for c in PUNCT[:-1]:
        b += struct.pack(">HH", 0x0C00, c)  # cmpi.b #c,d0
        b += bytes([0x67, 0x00])  # beq.s hit (변위는 아래에서)
    b += struct.pack(">HH", 0x0C00, PUNCT[-1])  # cmpi.b #?,d0
    b += bytes([0x66, 0x0E])  # bne.s plain (addq 2 + cmpi 8 + bne 2 + addq 2 = 14B 건너뜀)
    hit = len(b)
    b += struct.pack(">H", 0x5000 | (SLACK_BYTES << 9) | 0x01)  # addq.b #2,d1
    # 자막(피치 16, `$FF2014`)만 부호 허용을 더 넓힌다 — 대사창(피치 12)·그 밖은 위 4px 그대로
    b += struct.pack(">HH", 0x0C39, CAPTION_PITCH) + struct.pack(
        ">I", 0xFF2014
    )  # cmpi.b #16,$FF2014.l
    b += bytes([0x66, 0x02])  # bne.s plain
    b += struct.pack(">H", 0x5000 | (CAPTION_EXTRA_BYTES << 9) | 0x01)  # addq.b #3,d1
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
        *[(f"hang:{at:x}", at, bytes.fromhex(new)) for at, _o, new, _w in HANG_PATCHES],
    ]


def check(d: bytes) -> None:
    for at, orig, _new, what in HANG_PATCHES:
        if d[at : at + len(orig) // 2] != bytes.fromhex(orig):
            raise SystemExit(f"금칙 걸기 고침 자리 {at:#x} 가 원본이 아니다 — {what}")
    if d[SITE : SITE + 6] != ORIG:
        raise SystemExit(f"후킹 자리 {SITE:#x} 가 `cmp.b $ff2018.l,d1` 이 아니다")
    print(f"  반각 부호 줄 끝 허용 — 후킹 1 · 기계어 {len(code())}B (+{SLACK_BYTES * 2}px)")


if __name__ == "__main__":
    if "--asm" in sys.argv:
        import josa

        print("\n".join(josa.verify(code(), 0x1F0000)))
    else:
        check(common.rom())
