#!/usr/bin/env python3
"""`line_dict.json` 의 **이름 층**(`src: name`)이 **지금 사전**과 갈렸나.

    python3 tools/check_line_dict_names.py

## 왜 있나 (2026-10-07, 새턴 세션)

`export_line_dict.py:_add_names()` 가 `shared/glossary`·`textmap/monsters_ed2` 를 읽어
이름 정본과 그 정형문(`〜과의 전투다` 등)을 `line_dict.json` 에 **그 시점 사전 값으로** 구워
넣는다. 사전이 나중에 바뀌어도(마스터 판정) **재수출을 안 돌리면 이 층은 안 따라온다** —
실측: 炎の剣=불의 검·ガイド=가이드·バルアズス島=바라즈스섬·盗賊=도둑 판정(10-07) 뒤에도
옛 값(불꽃의 검·안내원·바르아즈스섬·도적) 13자리씩이 박혀 있었다(관리자 전수 훑기로 발견).

`line_dict.json` 은 **새턴의 유일한 번역 저본**이라(이 레포 PS1 이식판 중 다른 소비자가
아직 없다) 이 층이 낡으면 **새턴 화면에 옛 이름이 그대로 나간다** — 표 검사
(`check_glossary.py` 류)는 이 파일을 안 보므로 못 잡는다.

## 방법

`export_line_dict.py._add_names({}, {})` 를 **빈 딕셔너리로 다시 호출**해 지금 사전 기준
이름 층을 새로 만들고, 커밋된 `line_dict.json` 의 `src: name` 자리와 **하나씩 비교**한다.
`_add_names` 는 `k in out` 이면 건너뛰므로 빈 딕셔너리로 부르면 이름 층 전체가 나온다.

⚠ **이 게이트가 재수출을 대신하지 않는다.** 사전이 바뀌면 사람이(또는 세션이) 다시
`python3 tools/export_line_dict.py` 를 돌려야 한다 — 이 게이트는 **그걸 깜빡했을 때** 운다.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from export_line_dict import OUT, _add_names


def check():
    with open(OUT, encoding="utf-8") as f:
        committed = json.load(f)["lines"]

    fresh = {}
    _add_names(fresh, {})

    bad = []
    for k, e in committed.items():
        if e.get("src") != "name":
            continue
        want = fresh.get(k)
        if want is None:
            # 사전에서 아예 빠진 이름 — 재수출이 알아서 지운다, 여기선 안 본다
            continue
        if want["t"] != e["t"]:
            bad.append((k, e["t"], want["t"]))
    return len(committed), bad


def main():
    n, bad = check()
    mark = "✅" if not bad else "❌"
    print(f"     {mark} line_dict 이름 층 사전 대조 {n:,}자리 — 잔존 {len(bad)}건")
    for k, old, new in bad[:10]:
        print(f"        🔴 {k}: {old!r} (사전은 {new!r})")
    if bad:
        raise SystemExit(
            f"line_dict.json 이름 층 {len(bad)}건이 지금 사전과 갈렸다 — "
            "`python3 tools/export_line_dict.py` 로 재수출한다"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
