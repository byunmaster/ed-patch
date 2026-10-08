"""고유명사는 **공용 사전**(`shared/glossary/ed3.json`)에서만 읽는다 — 게임 폴더에 JP→KR 표를 두지 않는다.

마스터 2026-10-08(사전 적용 라운드): 종전 `glossary_manual.json`(812)·`glossary_auto.json`(57 — 틀린 초벌)은 걷었다.
읽는 쪽 도구는 전부 여기를 거친다 — 표를 읽는 방식이 도구마다 달라 어긋나던 것을 한 곳으로 모은다.
사전이 새턴보다 넓다(PS1 쪽 이름이 더 들어 있다) — 원문에 안 나오는 이름은 어느 검사에도 안 걸린다.
고치는 길: 워커는 사전을 못 고친다 — 후보를 관리자에게(루트 CLAUDE.md 「고유명사는 사전 한 곳에만」).
"""

import os
import sys

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ),
        "shared",
    ),
)
import glossary as GL

TITLE = "ed3"


def categories():
    """`{범주: {JP: KR}}` — 사전 파일의 순서를 지킨다."""
    return {c: dict(t) for c, t in GL.load(TITLE)["categories"].items()}


def table():
    """`{JP: KR}` — 범주를 합친 한 사전(같은 JP 는 앞 범주가 이긴다. 겹치는 8 개는 KR 이 같다)."""
    out = {}
    for t in categories().values():
        for jp, kr in t.items():
            if isinstance(kr, str):
                out.setdefault(jp, kr)
    return out


def no_check():
    """일반 낱말과 겹쳐 「빠졌다」 강제를 빼는 열쇠."""
    return set(GL.load(TITLE).get("_no_check", ()))


def party(*jp):
    """파티원 JP → 사전 KR (없으면 바로 실패한다)."""
    t = categories()["person"]
    missing = [j for j in jp if j not in t]
    if missing:
        raise SystemExit(f"사전 person 에 없다: {missing}")
    return [t[j] for j in jp]
