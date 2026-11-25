"""마스터 판정 잠금 말뭉치 어댑터 — 공용 판정기(`scripts/check/master_rulings.py`)가 부른다.

`corpus()` → `[(자리, 갈래, 문안)]`. 자리 = `SCnnn_멤버@조각색인`(대사, 갈래 "script") · `UI0x주소`(UI·읽을거리 풀, 갈래 "ui").
판정 자체는 `master_rulings.json`, 규칙의 뜻은 공용 판정기 머리말이 정본이다.
"""

import glob
import json
import os

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def corpus():
    out = []
    for f in sorted(glob.glob(os.path.join(GAME, "script", "ed3", "*.json"))):
        stem = os.path.basename(f)[:-5]
        with open(f, encoding="utf-8") as fh:
            for k, v in json.load(fh)["lines"].items():
                out.append((f"{stem}@{k}", "script", v["kr"]))
    with open(os.path.join(GAME, "ui_ed3.json"), encoding="utf-8") as fh:
        for k, v in json.load(fh)["strings"].items():
            out.append((f"UI{k}", "ui", v["kr"] if isinstance(v, dict) else str(v)))
    return out
