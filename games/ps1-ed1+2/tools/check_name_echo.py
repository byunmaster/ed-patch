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

# ⚠ **셋째 꼴을 검사기로 만들려다 접었다**(2026-09-12). 마스터 QA 에서 「이름창은 제대로
# 있는데 본문이 그 이름을 또 쓰는」 자리가 둘 나왔다(`ED2SCN5:484·487`). 축을 따로 짜서
# 「원문 본문엔 없는데 우리 본문엔 있는 이름」으로 재 봤더니 **45곳이 뜨는데 대부분 오탐**
# 이었다 — 「여기는 **도구점**입니다만」처럼 정상 한국어고, 원문이 같은 말을 **가나/한자로
# 갈라 써서** 문자열 대조가 헛돈다.
# ⇒ 진짜 꼴(`{p}이름{p}` 로 창을 따로 연 자리)로 좁히니 **전 코퍼스에 3곳**이고, 그 셋은
#   `check_window_nl` 이 이미 「창 앞 개행 결손」으로 보고하는 바로 그 블록이다.
# 🔴 **모집단이 없고 보고가 겹치므로 검사기를 안 싣는다.** 오탐 45짜리를 게이트에 얹으면
#   「늘 빨간불인 게이트는 아무도 안 본다」가 된다. 둘을 고친 근거는 커밋 349dc438.


def echoes(kr, t):
    """창 이름 `kr` 이 우리 본문 `t` 에서 **또** 나오는가.

    🔴 `{p}` 로 **이름을 제 조각으로 열어 둔 자리는 겹침이 아니다**(2026-10-07). 원문이 이름을 본문 안에 색칠해 두는
    꼴(`%cランドー%cのＨＰが…`)은 우리도 `란도{p}의 ＨＰ가{p}…` 로 **조각마다 창에 1:1** 로 채워야 이름이 방출 바이트에
    산다 — 이름 조각을 빼면(`의 ＨＰ가{p}{p}…`) 화면에서 이름이 사라진다(v1.0.0 ED2SCN4:519·558 실측). 이름이 조각 하나를
    통째로 차지하면(`{p}` 로 갈린 한 조각이 이름뿐) 그 창을 우리가 직접 채운 것이라 파이프라인이 한 번 더 내보내지 않는다.
    """
    if kr in [seg.strip() for seg in t.split("{p}")]:
        return False
    return bool(re.search(rf"(?<![가-힣]){re.escape(kr)}", t))


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
                    if kr and echoes(kr, t):
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
