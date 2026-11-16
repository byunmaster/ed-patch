"""공용 판정기(`scripts/check/master_rulings.py --game md-ed2`)가 읽는 말뭉치 — 씬 대본 스트림 + textmap 의 `ours` 문자열.

자리는 `<씬>-<모듈>:<오프셋>`(대본) · `textmap/<파일>/<경로>`(전투·시스템·자막), 갈래는 "script" · "textmap".
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common


def corpus():
    """→ [(자리, 갈래, 문안)]"""
    out = []
    for f in sorted((common.GAME_DIR / "script").glob("*.json")):
        for off, e in json.loads(f.read_text(encoding="utf-8"))["streams"].items():
            out.append((f"{f.stem}:{off}", "script", e.get("ours") or ""))

    def rec(src, x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "ours" and isinstance(v, str):
                    out.append((src, "textmap", v))
                else:
                    rec(f"{src}/{k}", v)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                rec(f"{src}/{i}", v)

    for f in ("battle.json", "sysmsg.json", "captions.json"):
        p = common.GAME_DIR / "textmap" / f
        if p.exists():
            rec(f"textmap/{f}", json.loads(p.read_text(encoding="utf-8")))
    return out
