"""마스터 판정 문안 잠금의 말뭉치 어댑터 — 공용 판정기(`scripts/check/master_rulings.py`)가 부른다.

판정 규칙의 뜻(forbid·require has/is/lacks …)은 공용 하나다. 이 게임이 정하는 건 「문안이 어디 있나」뿐 —
`corpus()` → `[(자리, 갈래, 문안)]`. 자리 = `MAPnnn#블록` · 서책/자막 파일 이름, 갈래 = `script`(맵 대사) · `book` · `voice`.
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

SCRIPT = os.path.join(C.GAME_DIR, "script")


def corpus():
    """맵 대사 블록 · 서책 · 음성·영상 자막."""
    out = []
    for f in sorted(glob.glob(os.path.join(SCRIPT, "MAP*.json"))):
        stem = os.path.basename(f)[:-5]
        with open(f, encoding="utf-8") as fh:
            for k, v in json.load(fh).items():
                if isinstance(v, str) and not k.startswith("_"):
                    out.append((f"{stem}#{k}", "script", v))
    for f in sorted(glob.glob(os.path.join(SCRIPT, "book", "*.json"))):
        with open(f, encoding="utf-8") as fh:
            out.append((os.path.basename(f), "book", fh.read()))
    for n in ("voice.json", "voice_credits.json", "movie.json"):
        f = os.path.join(SCRIPT, n)
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                out.append((n, "voice", fh.read()))
    return out
