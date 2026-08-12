#!/usr/bin/env python3
"""**이름창에 남의 이름이 뜨는가** — 원문 화자 헤더와 우리 화자를 대조한다.

**왜.** 번역 정본(`script/`)의 화자(`s`)는 배정 시대 초안에서 물려받았는데, 그건 **정발
엔트리의 화자**라서 PS1 원문과 어긋난 자리가 있다. 바즈눈 성 알현이 전형이다 — 세리오스·
류난·게일의 대사가 전부 `크레아 왕비` 이름표를 달고 나간다(2026-08-12 전수에서 발견).

⚠ **화자맵이 정답은 아니다.** `_speaker_map` 은 JP 이름 → 정발 이름 대응표라 **우리가 정한
표기**와 어긋난다 — `ジェルマン` 을 `젤만` 으로 주지만 우리 정본은 `제르만` 이고(유저 확정
2026-08-11), `大盗賊 ゲイル` 을 `게일` 로 뭉개면 손자 게일과 구분이 사라진다. 그래서 두
층을 가른다:

- **인물이 다르다** — 이름이 서로 겹치지 않는다. **진짜 오류**다.
- **표기가 다르다** — 한쪽이 다른 쪽을 품거나 글자가 겹친다(`제르만`/`젤만` ·
  `대도 게일`/`게일` · `한스 대통령`/`한스`). 우리 표기를 따른다.

⚠ 원문에 **헤더가 없는 블록**(앞 블록에서 이어지는 말)은 보지 않는다 — 파이프라인이
원문 헤더 유무로 이름창 방출을 정하므로, 우리 `s` 가 남아 있어도 화면에 안 나간다.

  python3 tools/check_speakers.py            # 전 씬
  python3 tools/check_speakers.py ED1SCN4    # 한 씬
  python3 tools/check_speakers.py --all      # 표기 차이까지(판정 참고용)

정본에 `"sx": true` 를 달면 그 블록은 검사에서 빠진다(정체를 숨긴 인물 등 의도적 불일치).
"""

import difflib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R  # noqa: E402
from patch_sys_ui import SCN_FILES  # noqa: E402

SCRIPT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "script")


def _same_person(ours, canon):
    """표기 차이인가(같은 인물인가). 품음 관계이거나 글자가 많이 겹치면 같은 사람으로 본다."""
    a, b = ours.replace(" ", ""), canon.replace(" ", "")
    if a in b or b in a:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.5


def _script(scn):
    p = os.path.join(SCRIPT_DIR, f"{scn}.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    p = os.path.join(R.ROOT, "work", "review", f"draft_{scn}.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def candidates(scn):
    """[(블록, 우리 화자, JP 이름, 정발 대응, 다른 인물인가)]"""
    d = _script(scn)
    out = []
    for _s, eid, jp, _c, _t in R.iter_candidates((scn,)):
        k = str(eid)
        if k not in d or not R.jp_has_header(jp) or R.jp_header_is_fmt(jp):
            continue
        try:
            name = jp[2 : jp.find(R.MC, 2)].decode("cp932")
        except (UnicodeDecodeError, ValueError):
            continue
        canon = R._speaker_map().get(name)
        ent = d[k] or {}
        ours = ent.get("s")
        # ⚠ **일부러 다른 이름을 쓰는 자리가 있다** — 정체를 숨긴 인물이 이름을 밝히기 전까지
        # `갇힌 사람` 처럼 나오다가 소개 뒤에 실명으로 바뀌는 연출이다(게일 `jp560`, 유저 확인
        # 2026-08-12). 정본에 `"sx": true` 를 달면 여기서 뺀다.
        if not canon or not ours or ours == canon or ent.get("sx"):
            continue
        out.append((eid, ours, name, canon, not _same_person(ours, canon)))
    return out


def scan(scenes=None, show_all=False):
    tot = 0
    for scn, _l, _z in SCN_FILES:
        if scenes and scn not in scenes:
            continue
        rows = candidates(scn)
        wrong = [r for r in rows if r[4]]
        tot += len(wrong)
        print(
            f"  {'✅' if not wrong else '⚠'} {scn}: 남의 이름 {len(wrong)}곳"
            f" (표기 차이 {len(rows) - len(wrong)})"
        )
        for eid, ours, name, canon, bad in rows:
            if bad or show_all:
                mark = "⚠" if bad else "  "
                print(f"      {mark} jp{eid}: 우리 [{ours}] ← 원문 [{name} = {canon}]")
    print(
        f"\n{'✅ 남의 이름 없음' if not tot else f'⚠ 남의 이름 {tot}곳'}"
        "\n  ⚠ 표기 차이는 **우리 표기가 맞다** — 편차 대장"
        "(docs/jeongbal-deviations.md)이 정본이고, `_speakers` 에 등록하면 여기서 사라진다."
    )
    return tot


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    sys.exit(1 if scan(set(args) if args else None, "--all" in sys.argv) else 0)
