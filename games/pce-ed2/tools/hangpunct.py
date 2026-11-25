"""줄 끝 매다는 부호 — 엔진 줄 꺾음 판정에서 `. , ! ?` 를 폭 4px 로만 센다(마스터 11-22 「마침표는 판정에서 빼고 오른쪽을 살짝 침범하는 건 허용」, PCE I 도 같음).

글자 앞 줄 끝 검사(뱅크 0x6C `$67CC`): `x_끝 = $73 + 폭` 을 `2*$79-1` 과 대조해 넘으면 줄을 꺾는다. 대사 글자는 폭 12px 로 도는데(`kagi.py` 머리말) 반각 부호는 그려지는 폭이 8px 이고 잉크는
그 안쪽 왼쪽 2~5px 라, 줄이 168px 에 딱 닿는 「…을 장비했습니다.」(172px)가 마침표 하나 때문에 둘로 갈렸다. 부호(`$F9` = `. , ! ?`)면 x_끝 을 `$73 + 1`(4px) 로 두어 시작 x ≤ 164px 이면 통과시킨다 — 도안이 틀 밖으로 나가는 건 최대 4px.
`$67D1: a5 79 0a 3a c5 75`(LDA $79 · ASL · DEC · CMP $75) → `4c stub ea ea ea`, stub 은 뱅크 0x6C 꼬리(0xFF 패딩)에서 부호면 `$75 = $73 + 1` 을 만들고 원래 넷을 되풀이한 뒤 `$67D7` 로 돌아간다(그 뒤 `BCS`).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout

BANK = 0x6C
SEAM = 0x07D1
SEAM_OLD = bytes.fromhex("a5790a3ac575")
STUB_OFF = 0x1FE0
STUB_ORG = 0x6000 + STUB_OFF
RET = 0x67D7
STUB = bytes.fromhex(
    "a5f9 c92e f00c c92c f008 c921 f004 c93f d005 a573 1a 8575 a579 0a 3a c575"
) + bytes([0x4C, RET & 0xFF, RET >> 8])


def reserve(prog: layout.Prog) -> int:
    prog.reserve(BANK, STUB_OFF, len(STUB))
    return len(STUB)


def install(prog: layout.Prog) -> None:
    assert prog.o(BANK, SEAM, 6) == SEAM_OLD, "줄 끝 검사 원본 바이트가 다르다"
    assert prog.o(BANK, STUB_OFF, len(STUB)) == b"\xff" * len(STUB), "꼬리 칸이 비어 있지 않다"
    prog.put(BANK, STUB_OFF, STUB, "hangpunct stub")
    prog.put(BANK, SEAM, bytes([0x4C]) + STUB_ORG.to_bytes(2, "little") + b"\xea\xea\xea", "hangpunct seam $67D1")
