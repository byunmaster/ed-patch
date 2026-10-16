"""엔딩 직행 시험 빌드 — 새 게임을 시작하면 대관식(패키지 38)부터 들어가 자연 경로로 엔딩·스태프롤까지 이어진다. 정본 빌드는 안 건드린다(`ED_ENDING_TEST=1` 일 때만).

원리(10-13 실측): 패키지 로더(`$3A44`, 뱅크 밖 RAM)가 패키지 번호 `n` 을 받아 rel `n×128+2` 에서 `$3B08+n` 섹터를 읽고 `$4000` 으로 뛴다.
타이틀 패키지(패키지 62 = rel 7938 의 +8섹터, 뱅크 `$8088`)의 표 `[새 게임, 이어하기] = [0x2C, 0x01]` 이 다음 패키지 번호가 된다 — 0x2C(44) = rel 5634 첫 필드 패키지.
대관식은 패키지 38(0x26)이라 0x2C 를 0x26 로 바꾼다(10-14 마스터: 41 로 바로 가면 대관식 자막을 못 본다). 38 → … → 스태프롤이 자연 경로로 이어지는 걸 에뮬로 확인했다. 엔딩 끝 패키지 41(= rel 5250 ×47, 0x29)로 바로 가려면 `ED_TEST_PKG=0x29`.
"""

import os

NEWGAME_LINEAR = 7946 * 2048 + 0x88  # rel 7946 오프셋 0x88(거울 +36864 는 Writer 가 같이 쓴다)
NEWGAME_ORIG, NEWGAME_END = 0x2C, int(os.environ.get("ED_TEST_PKG", "0x26"), 0)  # ED_TEST_PKG 로 다른 패키지(예: 스태프롤 직전 41 = 0x29)로도 직행한다


def enabled() -> bool:
    return os.environ.get("ED_ENDING_TEST") == "1"


def apply(w) -> None:
    w.put(NEWGAME_LINEAR, bytes([NEWGAME_END]), bytes([NEWGAME_ORIG]), f"직행 시험 — 새 게임 첫 패키지 44 → {NEWGAME_END}")
    print(f"  ⚠ 직행 시험 빌드 — 새 게임이 패키지 {NEWGAME_END} 로 시작한다")
