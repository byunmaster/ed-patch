#!/usr/bin/env python3
"""정본 검사 진입점 — 게임 어댑터의 「원문 줄 · 우리 줄」을 공통 문안 정본(`shared/canon`)으로 잰다.

    python3 scripts/check/check_canon.py --game sfc-ed1          # 요약
    python3 scripts/check/check_canon.py --game sfc-ed1 --list   # 어긋난 자리 전부

사전(고유명사)과 정본(메뉴 라벨 · 화자 호칭 · 시스템 메시지 · 전투 문구)을 나눴다(마스터 2026-10-08).
어댑터는 이름 검사와 **같은 것**(`games/<게임>/tools/names_corpus.py`)을 쓴다 — 게임 몫이 늘지 않게.

- 어느 정본인가: 어댑터 `canon_title(자리)` → `TITLE == "ed3"` 면 ed3 → 어댑터 `CANON`(한 편짜리 게임) →
  그 밖엔 자리 이름이 `ED2…` 로 시작하는 단어를 품으면 ed2 · 아니면 ed1.
- 범위 밖: 어댑터 `CANON_SKIP`(자리 정규식) — 장면 대사 자리. 정본은 장면 대사를 다루지 않는다(마스터 10-08).
- 예외: `games/<게임>/canon_exceptions.json` — 이름 검사 예외와 같은 꼴(`approved` 가 있어야 친다).
- 🔴 **실패로 치는 건 게임이 전환을 마친 뒤**다 — 어댑터에 `CANON_GATE = True` 를 둔 게임만 어긋남이
  실패(종료 코드 1). 그 전엔 숫자만 보인다(사전 적용 라운드 2단계에서 게임마다 켠다). 늘 빨간불인
  게이트는 아무도 안 본다.
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "shared"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import canon
from check_names import _adapter, _is_kr


def _exceptions(game):
    path = os.path.join(ROOT, "games", game, "canon_exceptions.json")
    if not os.path.exists(path):
        return set(), []
    with open(path, encoding="utf-8") as f:
        raw = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    ok = {k for k, v in raw.items() if isinstance(v, dict) and v.get("approved")}
    return ok, sorted(set(raw) - ok)


def _title_of(mod):
    fn = getattr(mod, "canon_title", None)
    if fn:
        return fn
    if getattr(mod, "TITLE", "eiyuu") == "ed3":
        return lambda where: "ed3"
    if getattr(mod, "CANON", None):
        return lambda where: mod.CANON
    # ED1·ED2 합본(PS1·새턴)은 자리 이름에 `ED2…` 가 붙는다 — 대문자 그대로·단어 머리만(해시 속 ed2 를 피한다)
    return lambda where: "ed2" if re.search(r"(?<![0-9A-Za-z])ED2", str(where)) else "ed1"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)

    mod = _adapter(a.game)
    if mod is None and not _is_kr(a.game):
        print(f"정본 검사 [{a.game}] — 해당 없음(번역 트랙이 아니다)")
        return 0
    if mod is None:
        print(f"⚠ 정본 검사 어댑터 없음 — {a.game} 은 **안 쟀다**")
        return 2

    which = _title_of(mod)
    # 장면 대사는 정본 범위가 아니다(마스터 10-08 「PS1 이 정본인데 예외가 있어?」) — 정본은 메뉴·호칭·시스템·전투
    #   문구고, 같은 원문이라도 장면 대사는 장면 문체(정중체 등)로 옮긴다. 어댑터가 `CANON_SKIP`(자리 정규식)으로
    #   장면 대사 자리를 알려 주면 정본 검사에서 뺀다. 그래야 「예외」가 아니라 「범위 밖」으로 정직하게 셈한다.
    skip = re.compile(mod.CANON_SKIP) if getattr(mod, "CANON_SKIP", None) else None
    by_title = {}
    for item in mod.pairs():
        if skip and skip.search(str(item[0])):
            continue
        by_title.setdefault(which(item[0]), []).append(item)
    approved, unsigned = _exceptions(a.game)
    gate = bool(getattr(mod, "CANON_GATE", False))
    rc = 0
    for title in sorted(by_title):
        r = canon.audit(by_title[title], title)
        left = [h for h in r.mismatches if f"{h.where}|{h.jp}" not in approved]
        excused = len(r.mismatches) - len(left)
        print(
            f"정본 검사 [{a.game} · 정본 {title}] — 줄 {r.translated}/{r.units} · 정본 문안 출현 {len(r.hits)}"
            f" · 어긋남 {len(left)}"
            + (f" (승인 예외 {excused})" if excused else "")
            + f" · 판정 대기 {len(r.pending)}"
            + ("" if gate else " · (게이트 꺼짐 — 2단계 전환 뒤 켠다)")
        )
        for h in left if a.list else left[:10]:
            print(f"  ✗ {h.where}  [{h.category}] {h.jp} → 정본 「{h.canon}」 이 우리 줄에 없다")
        if not a.list and len(left) > 10:
            print(f"  … 외 {len(left) - 10} (--list)")
        if left and gate:
            rc = 1
    if unsigned:
        print(f"  ⚠ 승인 없는 예외 {len(unsigned)} — 예외로 안 쳤다: {', '.join(unsigned[:5])}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
