"""마스터 판정 잠금의 말뭉치 어댑터 — 공용 판정기(`scripts/check/master_rulings.py`)가 부른다. 판정은 `master_rulings.json`.

문안은 `script/*.json`(씬) · `textmap/battle.json` · `textmap/sysmsg.json` 의 `ours`(우리 문안)다. 원문(JP)은 판정 파일에 적지 않는다.
"""

import json

import common


def corpus() -> list[tuple[str, str, str]]:
    """`[(자리, 갈래, 문안)]` — 씬 `씬NNN:off`(script) · 전투 `battle:해시` · 시스템 `sysmsg:off`."""
    out: list[tuple[str, str, str]] = []
    for f in sorted((common.GAME_DIR / "script").glob("*.json")):
        for k, v in json.loads(f.read_text(encoding="utf-8"))["streams"].items():
            out.append((f"씬{f.stem}:{k}", "script", v["ours"]))
    for name in ("battle", "sysmsg"):
        d = json.loads((common.GAME_DIR / "textmap" / f"{name}.json").read_text(encoding="utf-8"))
        for k, v in d.items():
            if isinstance(v, dict) and isinstance(v.get("ours"), str):
                out.append((f"{name}:{k}", name, v["ours"]))
    return out
