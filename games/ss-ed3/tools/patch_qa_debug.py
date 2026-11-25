"""QA 전용 디버그 개조 — `ED_DEBUG_QA=1` 일 때만 `/0.BIN` 에 얹는다(제품 롬 바이트 불변).

🔴 **꼬리표가 `qa-` 로 시작해야 켠다**(`ED_BUILD_TAG=qa-debug`) — 제품 칸에 디버그 개조가 새지 않게 한다.
   스위치가 없으면 이 모듈은 **아무것도 안 한다**(`patch` 가 입력을 그대로 돌려준다).

기능 (원판 디버그 메뉴 `X+Y+Z` 위에 없는 것):

① 이동 속도 — 플레이어 한 프레임 이동량 dx/dy(`0x060793CC`/`0x060793D0`, 16.16 고정소수)는
   `방향표 `0x0601A28C`[방향] × 배정도 상수`(x `0x060084E4`=256.0 · y `0x060084EC`=192.0)로 만든다
   (필드 이동 함수 `0x06009xxx` 안 세 곳 — `0x06008C1C` · `0x06009000` · `0x060096BC` 가 같은 상수를 읽는다).
   두 상수를 `ED_QA_SPEED`(기본 2) 배로 키운다 — 한 프레임 이동이 그만큼 늘어 걷기가 빨라진다.
   (RE 경위: `docs/devlog.md` 11-19 「QA 디버그 RE 2차」)

② 벽 뚫기 — 이동 함수가 후보 좌표의 타일 충돌을 `0x06005044`(네 모서리 타일 속성) → `0x060053E0` 로 판정해
   결과 바이트를 `0x0608CE2E` 에 저장한다(`0x0600968C` `mov r0,r2` → `mov #0,r2`). 결과를 늘 0(통과)으로 저장한다.
   ED_QA_NOCLIP=0 이면 끈다. (RAM 실측: 패치 전 절벽 앞에서 좌표 정지, 후 통과)

③ 일반 조우 끄기 — ed3 전투는 필드 몬스터 접촉이 아니라 **지점 진입**이다. 필드 상태기계(`0x0600F518`, 상태 변수 `0x06093EEC`)는
   상태 3 에서 거리 판정 `0x0600561C` 이 참이면 상태 4 로 올려 전투(`0x06006718` → `0x06021324`)를 세운다. 그 분기를 막는다
   (`ED_QA_NOENC=0` 이면 끔). 이야기 전투는 스크립트 옵코드 `0x06015170`(상태 4 를 스스로 확인) 경로라 영향 밖이어야 한다.
"""

import os
import struct

BASE = 0x06004000  # /0.BIN 이 올라가는 주소(파일 오프셋 = 주소 − BASE)
SPEED_X = 0x060084E4  # 배정도 256.0
SPEED_Y = 0x060084EC  # 배정도 192.0
SPEED_ORIG = (256.0, 192.0)
NOCLIP_SITE = 0x0600968C  # mov r0,r2 (충돌 결과) — 0x0608CE2E 에 저장되기 직전
NOCLIP_ORIG = bytes.fromhex("6203")
NOCLIP_NEW = bytes.fromhex("e200")  # mov #0,r2
NOENC_SITE = 0x0600F57A  # tst r0,r0 — 필드 조우 상태기계 상태 3 에서 「위치 판정 참」이면 상태 4(전투)로 올리는 분기 앞
NOENC_ORIG = bytes.fromhex("2008")
NOENC_NEW = bytes.fromhex("0018")  # sett — 늘 「거짓」으로 보고 상태를 안 올린다


def enabled():
    if not os.environ.get("ED_DEBUG_QA"):
        return False
    tag = os.environ.get("ED_BUILD_TAG", "")
    if not tag.startswith("qa-"):
        raise SystemExit(
            f"ED_DEBUG_QA=1 은 꼬리표가 qa- 로 시작해야 한다(지금 {tag!r}) — 제품 칸에 새지 않게 막는다"
        )
    return True


def speed_factor():
    return float(os.environ.get("ED_QA_SPEED", "2"))


def patch(data):
    """`/0.BIN` bytes → 새 bytes(크기 불변). 스위치가 꺼져 있으면 입력 그대로."""
    if not enabled():
        return data
    out = bytearray(data)
    k = speed_factor()
    for addr, want in ((SPEED_X, SPEED_ORIG[0]), (SPEED_Y, SPEED_ORIG[1])):
        o = addr - BASE
        (got,) = struct.unpack(">d", out[o : o + 8])
        assert got == want, f"{addr:#x} 가 예상({want})과 다르다({got}) — 자리를 잘못 짚었다"
        out[o : o + 8] = struct.pack(">d", want * k)
    if os.environ.get("ED_QA_NOCLIP", "1") != "0":
        o = NOCLIP_SITE - BASE
        assert out[o : o + 2] == NOCLIP_ORIG, f"{NOCLIP_SITE:#x} 가 예상과 다르다 — 자리를 잘못 짚었다"
        out[o : o + 2] = NOCLIP_NEW
    if os.environ.get("ED_QA_NOENC", "1") != "0":
        o = NOENC_SITE - BASE
        assert out[o : o + 2] == NOENC_ORIG, f"{NOENC_SITE:#x} 가 예상과 다르다 — 자리를 잘못 짚었다"
        out[o : o + 2] = NOENC_NEW
    return bytes(out)
