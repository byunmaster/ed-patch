"""마스터 판정 문안 잠금 — 말뭉치 어댑터. 판정기는 `scripts/check/master_rulings.py`(공용), 판정은 `master_rulings.json`."""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

SCRIPT = os.path.join(common.ROOT, "script")
UI = os.path.join(common.ROOT, "ui_ed4.json")


def corpus():
    """`[(자리, 갈래, 문안)]` — 대본 조각(`<아카이브>__<멤버>#<조각>`, "script") + UI 문자열(`UI@0x<오프셋>`, "ui")."""
    out = []
    for f in sorted(glob.glob(os.path.join(SCRIPT, "*.json"))):
        stem = os.path.basename(f)[: -len(".BIN.json")]
        with open(f, encoding="utf-8") as fh:
            for k, v in json.load(fh)["segments"].items():
                out.append((f"{stem}#{k}", "script", v.get("kr") or ""))
    with open(UI, encoding="utf-8") as fh:
        for k, v in json.load(fh)["strings"].items():
            out.append((f"UI@{k}", "ui", v.get("kr") or ""))
    return out
