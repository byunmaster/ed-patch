"""줄·쪽 나눔 지표(규칙 2-16, 마스터 10-26) — 대사 전량을 **조판 결과**(`script_kr.page_plan`)로 세는 기계 지표 · 래칫 게이트.

  a. 쪽 끝 한 어절 고아 — 쪽(3줄 단위)에 줄이 둘 이상인데 마지막 줄이 한 어절이고 앞 줄이 절 경계에서 안 끝난다(절 꼬리 조각)
  b. 문장 중간에서 끊긴 쪽의 한 낱말 줄 · 본용언+보조용언 자리에서 끊긴 쪽 (a 와 겹쳐도 따로 센다)
  c. 문장 중간 손 개행 — 합쳐 조판하지 않는 토막(rigid) 안 `01` 줄바꿈이 절 경계(문장 끝·쉼표·연결어미)가 아닌 곳(절 한복판)
  e. [명사+명사] 굳은 구(대사 전량에 같은 이음이 둘 이상)가 줄 끝·첫머리로 갈린 곳
  f. 퇴행 — 규칙이 **새로 만든** 나쁜 끊김(보조용언·의존명사·관형사 고아 · 전엔 한 줄이던 문장이 갈림). 래칫 0
  h. 창이 둘 이상인데 마지막 창에 한 어절만 남은 단위 · h2. 창 수를 안 늘리고 고르게(창 줄 수 차 1 이하) 나눌 수 있는데 차가 2 이상인 단위(래칫)
  g. 글 소실 — 규칙 끈 조판과 켠 조판의 쪽(토막) 글이 공백·개행 빼고 다르다(2-7 글 소실 불변식). 래칫 0
  d. 절째 내리면 들어가는데 쪼갠 줄 — 이 줄에서 시작한 절이 다음 줄에 통째로 들어간다
기준선(`linemetrics_baseline.json`)보다 **늘면 실패**, 줄면 `--freeze` 로 내린다(래칫).

    python3 tools/linemetrics.py [check|freeze|list]
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build
import script_kr
import typeset

BASELINE = os.path.join(HERE, "..", "linemetrics_baseline.json")
KEYS = ("a", "b", "c", "d", "e", "f", "g", "h", "h2")


def _lines(texts, pg, cols=typeset.COLS):
    out = []
    for i in pg:
        t = texts.get(i, "")
        for k in range(0, len(t), cols):
            ln = t[k : k + cols].rstrip(" ")
            if ln:
                out.append(ln)
    return out


def measure(members=None, rows_all=None):
    """({a,b,c,d: 개수}, {a,b,c,d: [(멤버, 첫 조각)…]}) — 번역된 대사 전량."""
    members = members if members is not None else build.identity_gate({})
    rows_all = rows_all if rows_all is not None else script_kr.load_all()
    cnt = {k: 0 for k in KEYS}
    where = {k: [] for k in KEYS}
    for key, rows in rows_all.items():
        mem = members[key]
        texts, _ = script_kr.page_plan(mem, rows)
        keep = typeset.RULES_216
        typeset.RULES_216 = False
        try:
            before, _ = script_kr.page_plan(mem, rows)
        finally:
            typeset.RULES_216 = keep
        for msg in typeset.windows(mem):
            for pg in msg:
                if not pg or any(i not in texts for i in pg if rows.get(i, {}).get("kr")):
                    continue
                if "".join("".join(before.get(i, "").split()) for i in pg) != "".join(
                    "".join(texts.get(i, "").split()) for i in pg
                ):
                    cnt["g"] += 1
                    where["g"].append((key[1], pg[0]))
                if pg.rigid:
                    if typeset.is_listish([texts.get(i, "") for i in pg]):
                        continue  # 항목 줄(사전·목록)은 손 개행을 지킨다 — 문장이 아니다
                    # c — 이어지는 조각 사이 줄바꿈이 문장 중간
                    prevs = [texts.get(i, "").strip() for i in pg]
                    for a, b in zip(prevs, prevs[1:], strict=False):
                        aw = a.split(" ")
                        if a and b and not typeset._is_bound(aw[-1], aw[-2] if len(aw) > 1 else ""):
                            cnt["c"] += 1
                            where["c"].append((key[1], pg[0]))
                    continue
                lines = _lines(texts, pg)
                if typeset.lonely_last(lines):
                    cnt["h"] += 1
                    where["h"].append((key[1], pg[0]))
                if not typeset.is_listish([texts.get(i, "") for i in pg]) and typeset.balance(" ".join(lines), lines, len(pg)):
                    cnt["h2"] += 1
                    where["h2"].append((key[1], pg[0]))
                lb = _lines(before, pg)
                if lb != lines:
                    r = typeset.regressions(lb, lines)
                    if r:
                        cnt["f"] += r
                        where["f"].append((key[1], pg[0]))
                for p0 in range(0, len(lines), typeset.PAGE_LINES):
                    pgl = lines[p0 : p0 + typeset.PAGE_LINES]
                    last = pgl[-1]
                    cont = p0 + typeset.PAGE_LINES < len(lines)
                    one = " " not in last
                    if len(pgl) >= 2 and one and not typeset._is_bound(pgl[-2].split(" ")[-1]):  # 앞 줄이 절 경계(문장 끝·쉼표·연결어미)에서 끝나면 그 한 낱말은 제 절이다(고아 아님)
                        cnt["a"] += 1
                        where["a"].append((key[1], pg[0]))
                    w = last.split(" ")
                    nxt = lines[p0 + typeset.PAGE_LINES].split(" ")[0] if cont else ""
                    if cont and len(pgl) >= 2 and (
                        (one and not typeset._END_RE.search(last))
                        or (typeset._AUX_PREV_RE.search(w[-1]) and typeset._AUX_RE.match(nxt))
                    ):
                        cnt["b"] += 1
                        where["b"].append((key[1], pg[0]))
                for k in range(len(lines) - 1):
                    if len(lines[k].split(" ")) >= 2 and typeset.is_nounphrase_split(lines[k], lines[k + 1]):
                        cnt["e"] += 1
                        where["e"].append((key[1], pg[0]))
                    w = lines[k].split(" ")
                    if len(w) < 2 or typeset._is_bound(w[-1], w[-2]):
                        continue
                    bs = [j for j in range(len(w) - 1) if typeset._is_bound(w[j], w[j - 1] if j else "")]
                    if not bs:
                        continue
                    j = bs[-1]
                    nx = lines[k + 1].split(" ")
                    e = next((t for t, x in enumerate(nx) if typeset._is_bound(x, nx[t - 1] if t else "")), None)
                    if e is None or len(" ".join(w[: j + 1]).replace(" ", "")) < typeset.MIN_HEAD:
                        continue
                    if typeset._fit(" ".join(w[j + 1 :] + nx[: e + 1]), typeset.COLS):
                        cnt["d"] += 1
                        where["d"].append((key[1], pg[0]))
    return cnt, where


def main(argv):
    mode = argv[1] if len(argv) > 1 else "check"
    cnt, where = measure()
    line = " · ".join(f"{k}={cnt[k]}" for k in KEYS)
    if mode == "list":
        for k in KEYS:
            print(k, cnt[k])
            for m, i in where[k]:
                print("  ", m, i)
        return 0
    if mode == "freeze" or not os.path.exists(BASELINE):
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(cnt, f, indent=1)
        print(f"기준선 기록 — {line}")
        return 0
    with open(BASELINE, encoding="utf-8") as f:
        base = json.load(f)
    worse = [k for k in KEYS if cnt[k] > base.get(k, 0)]
    better = [k for k in KEYS if cnt[k] < base.get(k, 0)]
    print(f"줄·쪽 나눔 지표 {line} (기준선 " + " · ".join(f"{k}={base.get(k, 0)}" for k in KEYS) + ")")
    if worse:
        print("🔴 기준선보다 늘었다: " + ", ".join(worse) + " — `list` 로 자리를 본다")
        return 1
    if better:
        print("⚠ 기준선보다 줄었다 — `freeze` 로 내린다: " + ", ".join(better))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
