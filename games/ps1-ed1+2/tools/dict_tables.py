"""정본(`shared/canon` — 고유명사 `nouns/` + 공통 문안)에서 읽는 이름·문안 표 — **게임 폴더에 이름 표를 두지 않는다**(마스터 2026-10-08).

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


def item(title="ed1"):
    return canon.table("item", title)


def monster(title="ed1"):
    return canon.table("monster", title)


def person(title="ed1"):
    return canon.table("person", title)


def place(title="ed1"):
    return canon.table("place", title)


def canon_table(category, title="ed1"):
    return canon.table(category, title)


def monsters_ed2():
    """{원문: 한글} — ED2 에 나오는 몬스터 이름. **키 목록만** 게임 폴더(`textmap/monsters_ed2_keys.json`)에 두고
    값은 정본(canon monster)에서 읽는다(마스터 10-08 — 게임 폴더에 자기 표를 두지 않는다)."""
    import json
    import os

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "textmap", "monsters_ed2_keys.json"), encoding="utf-8") as f:
        keys = json.load(f)["keys"]
    mon = monster()
    missing = [k for k in keys if k not in mon]
    assert not missing, f"ED2 몬스터 키가 사전에 없다: {missing[:5]} — 관리자에게 후보로"
    return {k: mon[k] for k in keys}


def monster_lines_ed2():
    """{원문: 한글} — ED2 몬스터 전투 대사. 정본(canon ed2)에 열쇠가 있는 것은 정본에서(`_canon_keys`),
    아직 없는 것만 `textmap/monster_lines_ed2.json` 에 남아 있다(관리자 후보 대기 — 마스터 10-08)."""
    import json
    import os

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "textmap", "monster_lines_ed2.json"), encoding="utf-8") as f:
        raw = json.load(f)
    canon = {}
    for cat in ("ui", "speaker", "system", "battle"):
        canon.update(canon_table(cat, "ed2"))
    out = {k: canon[k] for k in raw.get("_canon_keys", [])}
    out.update({k: v for k, v in raw.items() if not k.startswith("_")})
    return out
