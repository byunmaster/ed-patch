"""마스터 판정 문안 잠금 — 말뭉치 어댑터. 판정기는 `scripts/check/master_rulings.py`(공용)."""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

SCRIPT = os.path.join(C.ROOT, "script")
HOTFIX = os.path.join(C.ROOT, "hotfix", "script")


def corpus():
    """`[(씬#번호, "script", 문안)]` — 제품 script 위에 핫픽스 덮개(`t` 가 있는 항목)를 얹은 값."""
    out = []
    for f in sorted(glob.glob(os.path.join(SCRIPT, "ED*SCN*.json"))):
        scene = os.path.basename(f)[:-5]
        hot = {}
        hf = os.path.join(HOTFIX, scene + ".json")
        if os.path.exists(hf):
            with open(hf, encoding="utf-8") as fh:
                hot = json.load(fh)
        with open(f, encoding="utf-8") as fh:
            blocks = json.load(fh)
        for eid, v in blocks.items():
            if eid.startswith("_") or not isinstance(v, dict):
                continue
            h = hot.get(eid)
            t = h["t"] if isinstance(h, dict) and "t" in h else v.get("t")
            if isinstance(t, str):
                out.append((f"{scene}#{eid}", "script", t))
    return out
