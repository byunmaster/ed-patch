"""시스템 카드 안내 화면 확인용 빌드(꼬리표 `syscard-check` — 마스터 목록에 보인다, 이름 `ed2 (SYSCARD)`로 세이브가 제품과 갈린다).

정상 시스템 카드(3.00)로는 카드 안내(패키지 20, rel 2562)가 안 뜬다 — 구형 BIOS 로 켜야 뜨는 화면이다. 이 빌드는 타이틀의 「다음 패키지 표」(`endtest` 와 같은 자리)를 고쳐
**새 게임 → 패키지 20**(카드 버전 안내: 「시스템 카드의 버전이 다릅니다」 · 「버전 3.00 이상의 시스템 카드를…」이 번갈아 뜬다)으로 보낸다.
다른 두 안내(「백업 RAM이 초기화되지 않았습니다」 · 「…빈 공간이 없습니다」)는 이어하기 쪽 — 제품 롬에서 **세이브 없이(백업 RAM 비움) 이어하기**를 고르면 앞의 것이 뜬다.
제품 롬(꼬리표 `pce-ed2`)은 바이트 하나도 안 바뀐다.
"""

import common
import endtest

CARD_PKG = 20  # 패키지 20 = rel 2562 (카드 안내)


def enabled() -> bool:
    return common.BUILD_TAG == "syscard-check"


def apply(w) -> None:
    w.put(endtest.NEWGAME_LINEAR, bytes([CARD_PKG]), bytes([endtest.NEWGAME_ORIG]), f"카드 확인 — 새 게임 첫 패키지 44 → {CARD_PKG}")
    print(f"  ⚠ 카드 안내 확인 빌드 — 새 게임이 패키지 {CARD_PKG}(시스템 카드 안내)로 시작한다")
