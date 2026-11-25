"""sfc-ed1 판정 잠금 어댑터 — 공용 판정기(`scripts/check/master_rulings.py`)가 읽는 말뭉치 `corpus()`.

자리 = 조각 id(`textmap/segments.json` 키), 갈래 = "script"(대사·시스템 문안 전량 — 한 갈래뿐).
"""

import json

import common

SEGMENTS = common.GAME_DIR / "textmap" / "segments.json"


def corpus():
    segs = json.loads(SEGMENTS.read_text(encoding="utf-8"))
    return [(k, "script", v["kr"]) for k, v in segs.items()]
