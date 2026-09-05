#!/usr/bin/env python3
"""**이름이 두 번 나가는가** — 원문이 제 창에 둔 이름을 우리 본문이 또 쓰는 자리.

**왜.** 원문은 이름을 **두 꼴**로 쓴다. 한 글자 차이라 눈으로 안 갈린다:

    꼴1  {c}ソニア{c}が 仲間になりました。   이름이 **제 창**에 있다 → 본문엔 조사만
    꼴2  {c}ランドーが 仲間になりました。{c}  이름이 **본문 안**에 있다 → 본문에 이름을 쓴다

꼴1 인데 본문에도 이름을 쓰면 파이프라인이 창에서 한 번, 본문에서 한 번 내보내
화면에 **「소니아소니아가 동료가 되었습니다.」**로 나간다(유저 QA 2026-08-19 실측).

⚠ **정적으로는 판정이 안 서던 자리다.** 검수가 「위험이 있다」로만 표시하고 인게임 확인을
남겨 뒀고(`docs/ed1-review-queue.md`), 유저가 실기로 확증했다. 그 판정을 여기 기계로 옮긴다.

**어떻게.** 원문의 `%c…%c` 창 안이 **고유명사 정본에 있는 이름**이면, 우리 `script/` 문안에
그 한국어 이름이 있으면 안 된다. ⚠ 이 판정은 정본이 인물 220·지명 97 로 채워진
2026-08-19 이후에야 가능해졌다 — 그전엔 「이름인지」를 알 방법이 없었다.

  python3 tools/check_name_echo.py        # 요약
  python3 tools/check_name_echo.py -v     # 자리마다
"""

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from common import OUT_DIR, ROOT

sys.path.insert(0, os.path.join(ROOT, "..", "..", "shared"))
import glossary as G

# 🔴 **창 뒤에 개행이 오면 화자 이름창이라 대상이 아니다.**
# `{c}シンディ{c}{n}신디, 같이.` 는 신디가 제 이름을 말하는 정상 대사고,
# `{c}ソニア{c}が 仲間に…` 는 **문장이 이어지는** 자리라 본문이 이름을 또 쓰면 겹친다.
# ⚠ 이 한 글자 차이가 전부다 — 넓게 잡으면 「제가 대통령인 한스입니다만」 같은 자기소개가
#   전부 오탐으로 쏟아진다(실측: 좁히기 전 14곳 중 12곳이 그 부류였다).
_WIN = re.compile(r"\{c\}([^{}]+)\{c\}(?!\{n\})")


def _canon():
    """JP 이름 → 우리 표기(인물·지명). 이름창에 오는 것은 이 둘뿐이다."""
    out = {}
    for cat in ("person", "place"):
        out.update(G.table(cat))
    return out


def scan(scenes=None, verbose=False):
    canon = _canon()
    bad = []
    for p in sorted(glob.glob(os.path.join(OUT_DIR, "scn_jp", "ED*SCN*.json"))):
        scn = os.path.basename(p)[:-5]
        if scenes and scn not in scenes:
            continue
        sp = os.path.join(ROOT, "script", f"{scn}.json")
        if not os.path.exists(sp):
            continue
        with open(sp, encoding="utf-8") as f:
            ours = json.load(f)
        with open(p, encoding="utf-8") as f:
            for e in json.load(f)["entries"]:
                t = (ours.get(str(e["entry_id"])) or {}).get("t") or ""
                if not t:
                    continue
                for jp_name in _WIN.findall(e.get("text") or ""):
                    kr = canon.get(jp_name.strip())
                    # ⚠ 짧은 이름은 다른 낱말에 묻힌다(`로우`↔`로우거`) — 낱말 경계를 본다.
                    if kr and re.search(rf"(?<![가-힣]){re.escape(kr)}", t):
                        bad.append((scn, e["entry_id"], jp_name.strip(), kr, t[:34]))
    print(f"  {'✅' if not bad else '❌'} 이름이 창과 본문에 겹친 곳 {len(bad)}")
    if verbose:
        for scn, eid, jp_name, kr, t in bad:
            print(f"      {scn} jp{eid}: 창 [{jp_name}={kr}] 인데 본문에도 — {t!r}")
    return len(bad)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = scan(set(args) if args else None, verbose=bool(args) or "-v" in sys.argv)
    sys.exit(1 if n else 0)
