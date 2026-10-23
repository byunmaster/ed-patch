"""음성 자막 — 같은 장면 연속 두 줄 사이 틈이 0.5초 미만이거나 앞 줄 닫힘이 다음 줄 열림보다 늦으면 실패 (게이트).

    python3 games/ss-ed3/tools/check_voice_gaps.py          # 검사
    python3 games/ss-ed3/tools/check_voice_gaps.py --fix    # 앞 줄 닫힘을 다음 줄 열림에 붙인다(`dur` 를 고친다)

마스터 10-22 「0.5초 미만은 대사창 안없어지게 다 붙여놨던 것 같은데 다시 벌어졌네」 — 앞 줄 닫힘(`t + dur`)과 다음 줄 열림(`t`) 사이가
0 < 틈 < 0.5초면 창이 깜박 사라진다. 붙이면(틈 0) 다음 줄이 갈아 끼운다.
**같은 자리(위/아래) 겹침(틈 < 0)도 실패**다(마스터 10-23 「닫힘이 다음 대사보다 늦으면 다음 대사 열림과 맞춰두는 게 좋지 않을까」) — 앞 줄 닫힘을 다음 줄
열림에 맞춰 자른다(열림은 손대지 않는다). 화면은 다음 줄이 창을 갈아 끼우므로 그대로다. **다른 자리**(앞 줄 위 → 다음 줄 아래 등) 겹침은 위·아래 창이 동시에
떠 있는 게 의도일 수 있어 그대로 두고 목록만 찍는다.
시계 장면은 `items`, 후크 장면(V01·V17~V19)은 자막이 있는 칸(`_t` = 열림)이다 — `voice_editor_data.slots` 와 같은 읽기.
구조상 붙일 수 없는 줄은 `voice_gap_allow.json`(`{"V01": [5, …]}` — 앞 줄 번호, 1부터)에 사유와 함께 적는다.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

SCRIPT = os.path.join(C.GAME_DIR, "script", "voice.json")
ALLOW = os.path.join(C.GAME_DIR, "voice_gap_allow.json")
LIMIT = 0.5
EPS = 0.0005


def slots(ent):
    """자막이 있는 칸의 원본 dict 목록과 열림 시각 — `voice_editor_data.slots` 와 같은 순서."""
    if ent.get("items"):
        return [(it, float(it["t"])) for it in ent["items"]]
    out = []
    for h in ent["hooks"]:
        if h.get("lines") and not h.get("preload"):
            m = re.match(r"\s*([0-9.]+)", str(h.get("_t", "")))
            out.append((h, float(m.group(1)) if m else 0.0))
    return out


def _pos(h):
    return h.get("pos", "bottom")


def gaps(doc, allow=None, other_pos=None):
    """`[(장면, 앞 줄 번호, 앞 줄 닫힘, 다음 줄 열림, 틈, 앞 칸 dict)]` — 틈 < 0.5초(겹침 포함, 같은 자리만), 예외 제외.

    `other_pos` 리스트를 주면 다른 자리 겹침을 거기에 `(장면, 번호, 닫힘, 열림, 틈)` 으로 담는다(실패 아님)."""
    allow = allow or {}
    out = []
    for vid in sorted(k for k in doc if re.fullmatch(r"V\d\d", k)):
        sl = slots(doc[vid])
        for i, ((a, ta), (b, tb)) in enumerate(zip(sl, sl[1:]), start=1):
            dur = float(a.get("dur", 0))
            if dur <= 0:
                continue  # `dur: 0` = 「다음 칸까지」 — 이미 붙어 있다
            g = round(tb - (ta + dur), 3)
            if g >= LIMIT or abs(g) <= EPS:
                continue
            if g < 0 and _pos(a) != _pos(b):
                if other_pos is not None:
                    other_pos.append((vid, i, round(ta + dur, 2), tb, g))
                continue
            if i not in allow.get(vid, []):
                out.append((vid, i, round(ta + dur, 2), tb, g, a))
    return out


def main():
    doc = json.load(open(SCRIPT, encoding="utf-8"))
    allow = json.load(open(ALLOW, encoding="utf-8")) if os.path.exists(ALLOW) else {}
    allow = {k: v for k, v in allow.items() if not k.startswith("_")}
    other = []
    bad = gaps(doc, allow, other)
    if "--fix" in sys.argv:
        for vid, i, end, nxt, g, a in bad:
            ta = end - a["dur"]
            a["dur"] = round(nxt - ta, 2)
        if bad:
            with open(SCRIPT, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=1)
                f.write("\n")
        print(f"틈·겹침 {len(bad)}곳을 맞췄다(겹침 {sum(1 for b in bad if b[4] < 0)})")
        return 0
    for vid, i, end, nxt, g, _ in bad:
        print(f"  ❌ {vid} #{i}: 닫힘 {end} → 다음 열림 {nxt} ({'겹침' if g < 0 else '틈'} {g}초)")
    for vid, i, end, nxt, g in other:
        print(f"  ⓘ {vid} #{i}: 다른 자리 겹침(닫힘 {end} > 다음 열림 {nxt}) — 위·아래 창 동시 표시일 수 있어 그대로")
    if bad:
        print(f"❌ 음성 자막 틈·겹침 {len(bad)}곳 — `--fix` 로 붙이거나 구조상 못 붙이면 voice_gap_allow.json 에 사유와 함께")
        return 1
    print("✅ 음성 자막 연속 줄 사이에 0.5초 미만 틈·같은 자리 겹침 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
