#!/usr/bin/env python3
"""**의성어가 원문 꼴을 지키는가** — 웃음소리는 인물을 가르는 표지다.

**왜.** 2026-08-20 에 `フォッフォッフォ`(노인)를 「훠훠훠」로 통일하다가 실피의
`ホッホッホッ` 까지 같은 그물에 걸어 네 블록을 잘못 고쳤다. 실피는 **여성 악역**이라
「오호호호」가 맞다 — **원문이 다른 낱말인데 우리 문안이 같아서** 일괄 치환에 삼켜진 것이다.
반대 방향의 사고도 실재했다: 같은 `わっはっは` 가 「왓하하」·「와핫핫」으로 갈려 있었다.

그래서 규칙을 기계로 셀 수 있게 못 박았다(`docs/policy.md` 「의성어는 원문 꼴을 지킨다」):

1. **JP 마디 하나 = 한국어 한 글자**
2. **촉음(`ッ`)이 붙은 마디는 받침 ㅅ** → `핫핫하`(끝만 민 글자) ↔ `핫핫핫`(끝도 촉음)
   ↔ `하하하`(촉음 없음). 셋이 **다 다른 원문**이다.
3. **한 원문 꼴 = 한 우리 꼴**

⚠ **예외는 한국어 관용형이 굳은 자리뿐**이고 표에 값으로 박아 둔다(`헤헤헤`·`히히히`·
`오호호호`·`헉헉`). 규칙이 아니라 표를 고쳐야 바뀐다 — 조용히 새는 걸 막는다.

  python3 tools/check_onomatopoeia.py       # 전 씬
  python3 tools/check_onomatopoeia.py -v    # 맞는 자리까지 전량
"""

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 원문 꼴 → 우리 꼴. ⚠ **긴 것부터** 본다(`ハッハッハ` 가 `ハッハッハッハ` 를 삼키면 안 된다).
CANON = {
    # 하(ハ) 계열 — 마디 수 + 촉음
    "ハハハ": "하하하",
    "ははは": "하하하",
    "ハッハッハ": "핫핫하",
    "はっはっは": "핫핫하",
    "ハッハッハッ": "핫핫핫",
    "はっはっはっ": "핫핫핫",
    "ハッハッハッハ": "핫핫핫하",
    "はっはっはっは": "핫핫핫하",
    "ワッハッハ": "왓핫하",
    "わっはっは": "왓핫하",
    "わっはっはっは": "왓핫핫하",
    "うわっはっは": "우왓핫하",
    "うわっはっはっはっはっ": "우왓핫핫핫핫",
    "ふわっはっはっは": "후왓핫핫하",
    "ガッハッハッ": "갓핫핫",
    "グッハッハッハ": "굿핫핫하",
    "フッハッハッハ": "훗핫핫하",
    "グワッハッハ": "구왓핫하",
    "グワッハッハッハ": "구왓핫핫하",
    "がははは": "가하하하",
    # 후(フ) 계열
    "ふっふっふ": "훗훗후",
    "ふっふっふっ": "훗훗훗",
    "フッフッフッ": "훗훗훗",
    # 호(ホ) 계열
    "ほっほっほっほ": "홋홋홋홋",
    "ウォホッホッ": "워홋홋",
    "フォッフォッフォ": "훠훠훠",
    "ふぉっふぉっふぉ": "훠훠훠",
    # ⚠ 관용 예외 — 「헷헷헤」·「힛힛히」가 한국어로 안 읽힌다. 끝 촉음만 살려 가른다.
    "へっへ": "헤헤",
    "へっへっへ": "헤헤헤",
    "ヘッヘッヘ": "헤헤헤",
    "ヘヘヘ": "헤헤헤",
    "ヘッヘッヘッ": "헤헤헷",
    "ヒヒヒ": "히히히",
    "ヒッヒッヒ": "히히힛",
    # ⚠ 관용 예외 — 실피는 **여성 악역**이라 노인의 「훠훠훠」와 갈라야 한다.
    "ホッホッホッ": "오호호호",
    # 뜻으로 옮기는 것
    "クックックッ": "쿡쿡쿡",
    "ハァハァ": "헉헉",
    "はぁはぁ": "헉헉",
}
_KEYS = sorted(CANON, key=len, reverse=True)


def jp_tokens(text):
    """원문에서 표에 있는 의성어를 **긴 것부터** 집어낸다(겹치면 긴 쪽이 이긴다)."""
    out, taken = [], [False] * len(text)
    for key in _KEYS:
        start = 0
        while (i := text.find(key, start)) >= 0:
            if not any(taken[i : i + len(key)]):
                for j in range(i, i + len(key)):
                    taken[j] = True
                out.append((i, key))
            start = i + 1
    return [k for _, k in sorted(out)]


def scan(verbose=False):
    bad, ok = [], 0
    for path in sorted(glob.glob(os.path.join(ROOT, "work", "derived", "scn_jp", "ED*SCN*.json"))):
        scn = os.path.basename(path)[:-5]
        try:
            with open(os.path.join(ROOT, "script", f"{scn}.json"), encoding="utf-8") as f:
                kr = json.load(f)
        except FileNotFoundError:
            continue
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)["entries"]
        for e in entries:
            v = kr.get(str(e["entry_id"]))
            if not isinstance(v, dict):
                continue
            toks = jp_tokens(e.get("text") or "")
            if not toks:
                continue
            t = v.get("t") or ""
            for key in dict.fromkeys(toks):
                want = CANON[key]
                if want in t:
                    ok += 1
                    if verbose:
                        print(f"    ✅ {scn} jp{e['entry_id']}  {key} → {want}")
                else:
                    bad.append((scn, e["entry_id"], key, want, t[:40]))
    for scn, eid, key, want, t in bad:
        print(f"    ❌ {scn} jp{eid}  {key} 는 「{want}」여야 한다  {t!r}")
    print(
        f"  {'✅' if not bad else '❌'} 의성어가 원문 꼴을 지킨다: 맞음 {ok} · 어긋남 {len(bad)}"
        + ("" if not bad else "  ← 원문 마디 수·촉음을 본다(policy.md)")
    )
    return len(bad)


if __name__ == "__main__":
    sys.exit(1 if scan("-v" in sys.argv) else 0)
