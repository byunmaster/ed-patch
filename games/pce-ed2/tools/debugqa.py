"""QA 전용 디버그 보강(`ED_DEBUG_QA=1`, 꼬리표 `qa-debug` 또는 `test-*`) — **제품 롬은 바이트 하나도 안 바뀐다**(이 모듈은 켜진 빌드에서만 쓴다).

원판 디버그 메뉴(`debugsw` 가 제품 롬에 숨김 제스처로 연다)에는 이동 속도 항목이 없고, 필드 이동 처리의 개발자 기능이 `$86` bit7(개발기 게이트) 뒤에 잠겨 있다:
뱅크 0x6A `$6086 BBR7 $86,$6091` — 게이트가 서 있으면 **I 를 누른 채 이동할 때 이동 속도 값 `$31EA` 를 `$40` 으로**(원래 `$31E9`) 쓴다.
제품 롬은 `$86` bit7 이 안 서므로 이 기능이 죽어 있다(`debugsw` 머리말). QA 빌드는 그 분기만 NOP×3 해 **필드에서 I 를 누른 채 걷기 = 고속 이동**이 되게 한다.
게이트(`$86` bit7)를 세우지 않는 까닭: 같은 비트를 읽는 다른 개발자 분기(전투 설정 창 등)가 흐름을 바꾼다(`debugsw` 머리말).
"""

import os

import common

SPEED_GATE = (0x6A, 0x086)  # `$6086` BBR7 $86,$6091
SPEED_GATE_ORIG = bytes.fromhex("7f8608")


def enabled() -> bool:
    if os.environ.get("ED_DEBUG_QA") != "1":
        return False
    if common.BUILD_TAG != "qa-debug" and not common.BUILD_TAG.startswith("test-"):
        raise SystemExit(
            "ED_DEBUG_QA=1 은 꼬리표가 qa-debug 또는 test- 로 시작할 때만 쓴다(제품 롬 불변)"
        )
    return True


def install(prog) -> int:
    assert prog.o(*SPEED_GATE, 3) == SPEED_GATE_ORIG, "이동 속도 분기 원본 바이트가 기대와 다르다"
    prog.put(SPEED_GATE[0], SPEED_GATE[1], bytes([0xEA, 0xEA, 0xEA]), "QA 디버그 — 필드 I 누른 채 고속 이동의 개발기 게이트 해제")
    return 1
