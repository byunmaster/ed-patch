"""사전(`shared/glossary`)·정본(`shared/canon`)에서 읽는 이름·문안 표 — **게임 폴더에 이름 표를 두지 않는다**(마스터 2026-10-08).

사전 = 고유명사(아이템·몬스터·인물·지명), 정본 = 그 밖의 공통 문안(메뉴 라벨 · 화자 호칭 · 시스템 메시지 · 전투 문구).
도구는 여기서 받는다 — 값을 고치려면 **관리자에게 요청**한다(사전·정본은 main 에서 마스터 확인 뒤에만 바뀐다).

⚠ 사전은 **상위집합**이다(이 게임이 안 쓰는 항목도 든다) — 표를 그대로 쓰는 자리는 JP 키를 찾는 쪽이라 무해하지만,
이름 목록 전체를 훑는 자리(`keep_together` 등)는 값이 늘 수 있다 — 이미지 sha1 로 확인한다.
"""

import os
import sys

_SHARED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import canon  # noqa: E402
import glossary  # noqa: E402


def item():
    return glossary.table("item")


def monster():
    return glossary.table("monster")


def person():
    return glossary.table("person")


def place():
    return glossary.table("place")


def canon_table(category, title="ed1"):
    return canon.table(category, title)
