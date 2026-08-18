#!/usr/bin/env python3
"""우리가 쓴 문안(`ours`)이 정말 "정발에 대응이 없는" 자리인지 되짚는다.

**왜 필요한가(2026-08-04 실측).** "정발에 대응 없음" 판정을 **LaBSE 의 JP↔KR 점수**로 했다.
그런데 그 점수는 언어가 다른 두 문장을 재는 것이라 약하다 — 홀드아웃에서 정밀도 79% 였다.
그래서 정발에 멀쩡히 있는 대사를 "없다"고 보고 새로 쓴 자리가 나왔다(유저가 정발 디스크
스샷으로 잡았다: `왕자님, 저는 자라면 꼭 왕자님 부하가 될꺼예요` · `꼬끼요~ !?` ·
`자아, 루디아 성으로 가십시요`).

**여기서는 신호를 바꾼다 — 우리 한국어 ↔ 정발 한국어를 직접 잰다.** 같은 언어끼리라 훨씬
강하고, "이미 정발이 한 말을 우리가 다시 썼는가"를 정확히 묻는 질문이 된다.

⚠ 맵 제약을 건다. 정발 테이블은 맵에 묶여 있어(`scn_maps.table_maps`) 다른 마을 대사가
우연히 비슷해도 후보가 아니다. 제약을 안 걸면 노이즈가 답을 덮는다.
⚠ 이 도구는 **후보를 제시할 뿐** 배정하지 않는다 — 최종 판단은 사람이 한다.

  python3 tools/audit_ours.py            # 전 씬
  python3 tools/audit_ours.py ED1SCN2    # 특정 씬
"""

import difflib
import glob
import json
import os
import re
import sys

os.environ.setdefault("LOCK_BYPASS", "1")

from common import OUT_DIR, ROOT
from scn_maps import block_maps, table_maps

HIT, MAYBE = 0.62, 0.45  # 정발에 있음 / 확인 필요
_STRIP = re.compile(r"\{[^}]*\}|\\x[0-9A-Fa-f]{2}")
_NORM = re.compile(r"[\s.,!?~…·\-'\"]+")


def kr_pages(game):
    """[(table, entry_id, page_index, 본문)] — 정발 코퍼스를 페이지 단위로 편다."""
    out = []
    for p in sorted(glob.glob(os.path.join(OUT_DIR, "dos_kr", game, "*.json"))):
        doc = json.load(open(p, encoding="utf-8"))
        if not isinstance(doc, dict):
            continue
        table = f"{game}/{os.path.basename(p)[:-5]}"
        for e in doc.get("entries", []):
            if not isinstance(e, dict):
                continue
            for i, page in enumerate(re.split(r"\{p\}", e.get("text", ""))):
                body = _STRIP.sub("", page).replace("\n", " ").strip()
                if len(body) >= 2:
                    out.append((table, e["entry_id"], i, body))
    return out


def main():
    game = "ED1"
    only = next((a for a in sys.argv[1:] if a.startswith(game)), None)
    ov = json.load(open(os.path.join(ROOT, "align_overrides.json"), encoding="utf-8"))
    pages = kr_pages(game)
    learned, exempt = table_maps(game)
    print(f"정발 페이지 {len(pages):,}개와 대조\n")

    n_hit = n_maybe = n_none = 0
    for scn in range(1, 7):
        name = f"{game}SCN{scn}"
        if only and name != only:
            continue
        bm = block_maps(game, scn)
        for eid, e in sorted(ov.get(name, {}).items(), key=lambda kv: int(kv[0])):
            if not isinstance(e, dict) or "ours" not in e or not isinstance(e["ours"], str):
                continue
            mp = bm.get(int(eid))
            # 같은 맵의 테이블(+맵에 안 묶인 공용 테이블)만 후보
            cand = [c for c in pages if learned.get(c[0]) == mp or c[0] in exempt]
            if not cand:
                cand = pages
            o = _NORM.sub("", e["ours"])
            top = sorted(
                ((difflib.SequenceMatcher(None, o, _NORM.sub("", c[3])).ratio(), c) for c in cand),
                key=lambda x: -x[0],
            )[:2]
            r = top[0][0] if top else 0.0
            if r >= HIT:
                mark, n_hit = "❗정발에 있음", n_hit + 1
            elif r >= MAYBE:
                mark, n_maybe = "△ 확인 필요", n_maybe + 1
            else:
                n_none += 1
                continue
            print(f"{name} jp{eid:<5} {mark} ({r:.2f}) [{mp}]\n    우리: {e['ours'][:64]}")
            for rr, c in top:
                pg = f".{c[2]}" if c[2] else ""
                print(f"    정발 {c[0]}#{c[1]}{pg} ({rr:.2f}): {c[3][:64]}")
    print(f"\n정발에 있음 {n_hit} · 확인 필요 {n_maybe} · 대응 없음 {n_none}")


if __name__ == "__main__":
    main()
