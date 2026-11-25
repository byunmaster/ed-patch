"""마스터 판정 말뭉치 어댑터 — 공용 판정기(`scripts/check/master_rulings.py`)가 읽는다.

`corpus()` → `[(자리, 갈래, 문안)]`. 문안은 공백·`/ ↵ ¶`·`%c`·`{name}`·`{p}`·제어 문자·「」·`【…】` 를 뺀 꼴로 내보낸다
(`norm` — 판정의 `has`·`is` 도 그 꼴로 적는다. 줄바꿈·쪽 나눔이 판정을 흔들지 않게).
자리: 씬 대사 `<씬 파일>#<번호>` · 제목·메뉴·시스템 `names_corpus` 자리 이름 · 제목 모음 `script/title.json[<구간>]`
(대사 말뭉치 밖의 엔딩 자막 같은 구간 — 구간 줄을 이어 한 자리로 둔다).
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import names_corpus as N

_STRIP = re.compile(r"[\s/↵¶]+|\{name\}|\{p\}|%c|[\x00-\x1f「」]|【[^】]*】")
_SCN = re.compile(r"scn:/BIN/(\w+)\.BIN#(\d+)$")


def norm(s):
    return _STRIP.sub("", (s or "").replace("허나", "하지만"))


def corpus():
    out = []
    for site, _jp, kr, *_ in N.pairs():
        if kr is None:
            continue
        m = _SCN.match(site)
        if m:
            out.append((f"{m.group(1)}#{m.group(2)}", "script", norm(kr)))
        else:
            out.append((site, "ui", norm(kr)))
    with open(os.path.join(C.GAME_DIR, "script", "title.json"), encoding="utf-8") as f:
        for sec, lines in json.load(f).items():
            if isinstance(lines, list):
                out.append((f"script/title.json[{sec}]", "title", "".join(norm(x) for x in lines)))
    return out
