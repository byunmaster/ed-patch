"""디버그 스위치 — `ED_DEBUG=1 ED_BUILD_TAG=test-debug python3 tools/build.py`(시험) · `ED_DEBUG=1 ED_BUILD_TAG=debug …`(마스터용, 롬 이름 「(DEBUG)」).

🔴 제품 롬에는 반영하지 않는다(마스터 10-16 「테스트용 디버그 빌드는 지금, 사용자용 진입로·번역은 나중」). 스위치가 꺼져 있으면
이 모듈은 아무것도 쓰지 않고, 켰는데 꼬리표가 `test-…` 도 `debug` 도 아니면 빌드를 거부한다(제품 칸에 섞이지 않게).
마스터 10-17 「다 쓸 수 있었으면 해. 인게임 QA 할 때 도움될듯」 — 꼬리표 `debug` 는 파일서버 목록에 나오고 롬 파일 이름이 「ed2-kr (DEBUG).bin」이다
(`rom_name()`) — 제품과 이름·md5 가 달라 세이브가 갈린다. 꼬리표 `debug` 인데 스위치가 꺼져 있으면 거부한다(「debug」 칸에 제품 롬이 섞이면 안 된다).

엔진이 가진 개발용 변수 `$FF01B2`(스프라이트 섀도 표 안이라 정상 플레이에선 0x61~0x63 이 될 수 없다)를 시험 빌드에서만 켠다 —
status.md 「숨은 콘텐츠」·「디버그 빌드」. 패치 둘, 바이트 둘(같은 길이 · 새 코드 없음):
  1. 부팅 초기화 `0x126E8` 의 `move.b #0,$FF016D`(RAM 이 이미 0 이라 중복) → `move.b #$62,$FF01B2` — 부팅 때 디버그 레벨 0x62 를 심는다.
     0x62 = C 를 누른 채 걷기(벽 통과) · C 단독+방향 `$FF00E2`=1(고속 이동, `0x188A6`).
  2. 타이틀 뒤 숨은 조합 `0x127BA` 의 `cmpi.b #$63,$FF01B2` → `#$62` — 타이틀을 지난 뒤 A+B+C 를 누른 채 100틱을 기다리고
     B 만 떼 A+C 가 되면 오프닝을 건너뛰고 엔딩 연출(스태프롤 끝까지)로 직행한다. 엔딩 직행은 SRAM 을 건드리지 않는다(실측 10-16).
"""

import os

from common import BUILD_TAG

ENV = "ED_DEBUG"
INIT_AT = 0x126E8  # move.b #0,$FF016D  (13FC 0000 00FF 016D)
INIT_OLD = bytes.fromhex("13fc000000ff016d")
INIT_NEW = bytes.fromhex("13fc006200ff01b2")  # move.b #$62,$FF01B2
CMP_AT = 0x127BA  # cmpi.b #$63,$FF01B2  (0C39 0063 00FF 01B2)
CMP_OLD = bytes.fromhex("0c39006300ff01b2")
CMP_NEW = bytes.fromhex("0c39006200ff01b2")
PATCHES = (("debug-init", INIT_AT, INIT_OLD, INIT_NEW), ("debug-combo", CMP_AT, CMP_OLD, CMP_NEW))


DEBUG_TAG = "debug"  # 마스터용 꼬리표 — 파일서버 목록에 나온다
TEST_PREFIX = "test-"  # 시험용 — 목록에 안 나온다


def enabled() -> bool:
    return os.environ.get(ENV) == "1"


def tag_ok(tag: str) -> bool:
    return tag == DEBUG_TAG or tag.startswith(TEST_PREFIX)


def rom_name(base: str = "ed2-kr") -> str:
    """디버그가 켜진 빌드의 롬 파일 이름 — 「ed2-kr (DEBUG).bin」. 꺼져 있으면 제품 이름."""
    return f"{base} (DEBUG).bin" if enabled() else f"{base}.bin"


def check_tag() -> None:
    """꼬리표와 스위치가 맞는지 — 어긋나면 빌드를 거부한다."""
    if enabled() and not tag_ok(BUILD_TAG):
        raise SystemExit(
            f"{ENV}=1 은 꼬리표 `test-…` 나 `debug` 에서만 켠다(지금 {BUILD_TAG!r}) — 제품 롬에 디버그를 넣지 않는다"
        )
    if not enabled() and BUILD_TAG == DEBUG_TAG:
        raise SystemExit(
            f"꼬리표 `{DEBUG_TAG}` 는 {ENV}=1 로만 굽는다 — 제품 롬이 디버그 칸에 섞이면 안 된다"
        )


def allowed() -> dict[str, tuple[int, int]]:
    """무변경 구간 검사에 허용 구간을 알린다 — 스위치가 꺼져 있으면 비어 있다(제품은 이 구간도 원본 그대로여야 한다)."""
    if not enabled():
        return {}
    return {label: (at, at + len(new)) for label, at, _old, new in PATCHES}


def apply(rom) -> int:
    """켜져 있을 때만 두 곳을 쓴다. 원본 바이트가 기대와 다르면 멈춘다. 쓴 곳 수를 돌려준다."""
    if not enabled():
        return 0
    check_tag()
    for label, at, old, new in PATCHES:
        if bytes(rom.buf[at : at + len(old)]) != old:
            raise SystemExit(
                f"[{label}] {at:#x} 의 원본 바이트가 기대와 다르다 — 엔진 주소가 밀렸나"
            )
        rom.write(label, at, new)
    return len(PATCHES)
