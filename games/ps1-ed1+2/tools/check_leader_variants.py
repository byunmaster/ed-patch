#!/usr/bin/env python3
"""리더별 대사 변형 감사 — 같은 자리를 파티원 수만큼 나눠 둔 JP 블록이 **다 덮였는가**.

**왜(유저 QA 2026-08-08).** PS1 은 같은 대사를 리더별로 **다른 블록**에 둔다
(`セリオス: お前だな!!` · `リュナン: き、きさまだな!!` · `ソニア: あなたね!!` · `ゲイル: てめーか!!`).
정발은 그걸 한 엔트리의 `\x06` 변형으로 묶어 두고, 우리는 블록마다 변형을 골라 붙인다.
그래서 **한 블록만 빠지거나 두 블록이 같은 변형을 물어도** 화면에서는 그 리더로 플레이할
때만 드러난다 — 다른 리더로 지나가면 영영 안 보인다(실측: `ん!?`/`お!?` 가 둘 다 `오 !?`,
`어떻게 이런곳에서.` 가 세리오스판에만).

판정: 화자가 **파티원 이름 또는 `%s`** 인 블록을 이웃끼리 묶고(id 근접 + 본문 유사),
묶음 안에서 ① 미배정이 섞였는가 ② 배정 좌표가 겹치는가 를 본다. 겹침 자체는 정상일 수
있다(정발이 변형을 안 나눠 둔 자리) — **묶음의 다른 멤버는 다른 좌표인데 둘만 같으면** 의심.

    python3 tools/check_leader_variants.py [ED1SCN2] [--report]
"""

import json
import os
import sys
from difflib import SequenceMatcher

os.environ.setdefault("LOCK_BYPASS", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import OUT_DIR, REVIEW_DIR

LEADERS = ("セリオス", "リュナン", "ロー", "ゲイル", "ソニア")
GAP = 6  # 같은 자리로 볼 id 거리
SIM = 0.55  # 본문 유사도 하한(어투가 달라 낮게 잡는다)


def _plate(body):
    """블록 선두 화자 플레이트 이름(없으면 None)."""
    if not body.startswith("{c}"):
        return None
    end = body.find("{c}", 3)
    return body[3:end] if end > 0 else None


def _core(body):
    """화자·제어 태그를 뺀 본문(유사도 비교용)."""
    t = body
    for tag in ("{c}", "{n}", "\\x25\\x73"):
        t = t.replace(tag, " ")
    return " ".join(t.split())


def families(game, scn):
    doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{game}SCN{scn}.json"), encoding="utf-8"))
    rows = []
    for e in doc["entries"]:
        body = e.get("body") or e.get("text") or ""
        p = _plate(body)
        if p in LEADERS or p == "\\x25\\x73":
            # 넷째 칸은 **화자 플레이트를 뺀 본문** — 이름이 다르다고 다른 대사는 아니다.
            # 묶기(유사도)는 종전대로 `_core` 로 하고, 이건 "원판이 같은 문안인가" 판정용이다.
            rows.append(
                (e["entry_id"], p, _core(body), _core(body.replace(f"{{c}}{p}{{c}}", "", 1)))
            )
    out, cur = [], []
    for r in rows:
        if (
            cur
            and r[0] - cur[-1][0] <= GAP
            and SequenceMatcher(None, cur[-1][2], r[2]).ratio() >= SIM
        ):
            cur.append(r)
        else:
            if len(cur) >= 2:
                out.append(cur)
            cur = [r]
    if len(cur) >= 2:
        out.append(cur)
    return out


def main():
    game = "ED1"
    scenes = [a for a in sys.argv[1:] if a.startswith("ED")] or [
        f"{game}SCN{i}" for i in range(1, 7)
    ]
    import reinsert_kr_pilot as R

    total = bad = 0
    lines = ["# 리더별 대사 변형 감사", ""]
    for scn in scenes:
        n = int(scn.split("SCN")[1])
        tr, _, _ = R.load_translations(f"{game}_SCN{n}", scn)
        ov = R._load_overrides().get(scn, {})

        def coord(eid, ov=ov, tr=tr):
            v = ov.get(str(eid))
            if isinstance(v, dict) and "table" in v:
                return f"{v['table']}#{v['entry_id']}{v.get('chain', '')}"
            return "(정렬)" if eid in tr else None

        hits = []
        for fam in families(game, n):
            total += 1
            cs = [(eid, p, coord(eid)) for eid, p, _, _ in fam]
            miss = [c for c in cs if c[2] is None]
            seen, bodies = {}, {}
            for (_eid, p, c), (_e2, _p2, _sim, body) in zip(cs, fam, strict=True):
                if c:
                    seen.setdefault(c, []).append(p)
                    bodies.setdefault(c, set()).add(body)
            # ⚠ **원판이 이미 같은 문안이면 좌표 공유가 정답**이다. PS1 은 리더별로 블록을
            # 나눠 두되 어투가 갈리지 않는 대사는 **바이트까지 똑같이** 둔다(세리오스·류난의
            # `まだだ!!`, 세리오스·류난·소니아의 `ラルフさん!`). 이걸 안 빼면 정상 배정 둘이
            # 영구 의심으로 남는다(SCN3 jp2~7 · SCN5 jp1020~1023 실측 2026-08-11).
            dup = {c: v for c, v in seen.items() if len(v) > 1 and len(bodies[c]) > 1}
            # 묶음 안에 서로 다른 좌표가 있는데 일부만 겹친다 = 의심
            suspect = dup and len(seen) > 1
            if miss or suspect:
                bad += 1
                hits.append((cs, miss, dup if suspect else {}))
        if hits:
            lines.append(f"## {scn} — {len(hits)}묶음")
            for cs, _miss, dup in hits:
                lines.append("")
                for eid, p, c in cs:
                    mark = " ❌미배정" if c is None else (" ⚠겹침" if c in dup else "")
                    lines.append(f"- jp{eid} [{p}] → {c or '—'}{mark}")
            lines.append("")
        print(f"  {scn}: 묶음 중 의심 {len(hits)}건")
    print(f"리더 변형 묶음 {total}개 · 의심 {bad}개")
    if "--report" in sys.argv:
        os.makedirs(REVIEW_DIR, exist_ok=True)
        p = os.path.join(REVIEW_DIR, "leader_variants.md")
        open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        print(f"  → {p}")


if __name__ == "__main__":
    main()
