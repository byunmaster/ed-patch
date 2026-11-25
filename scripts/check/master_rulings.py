"""마스터 판정 문안 잠금 — 공용 판정기. 게임은 `master_rulings.json`(판정)과 말뭉치 어댑터만 갖는다.

    python3 scripts/check/master_rulings.py --game ss-ed3      # 게임 게이트가 부른다(rc 1 = 위반)

🔴 **왜**(마스터 10-29·30). 검수·재조판·동기화가 「원문에 있으니」로 마스터 판정을 이겼다 — 새턴 III 「로그 씨」가
세 번 되살아났고, 10-30 전수 대조에서 PS1 I·II 8블록 · SFC II 2 · PS1 III 2 가 되돌려져 있었다. 판정이 문서에만
있으면 아무도 안 읽는다. 그날 열한 게임이 각자 같은 검사기를 베껴 만들었다(773줄) — 판정 규칙의 뜻이 게임마다
갈리지 않게 판정기는 여기 하나로 둔다(DRY · 둘째 소비자 실재). 게임마다 다른 건 「문안이 어디 있나」뿐이다.

── 게임 쪽 ────────────────────────────────────────────────────────────────
`games/<게임>/master_rulings.json` — {"rulings": [판정, …]}. 원문(JP)은 적지 않는다(저작권 게이트).
`games/<게임>/tools/rulings_corpus.py` — `corpus()` → `[(자리, 갈래, 문안)]`. 자리는 판정의 `block` 이 가리키는
이름(씬·키·주소 등 게임 마음), 갈래는 `scope` 로 거를 때 쓰는 이름("script" · "ui" · "title" …).

── 판정 한 건의 꼴(모두 선택) ──────────────────────────────────────────────
  id · 판정(사람이 읽는 근거 — 마스터 말씀과 날짜)
  forbid: [글]           말뭉치 어디에도 없어야 하는 글
  forbid_re: [정규식]     같은 뜻의 정규식(옛 이름 forbid_regex 도 받는다)
  scope: "갈래"           forbid·forbid_re 를 그 갈래에만
  except_blocks: [자리]   forbid·forbid_re 에서 뺄 자리(옛 이름 allow_blocks)
  allow_only: {has, blocks}   그 글은 이 자리들에만 있어도 된다(그 밖엔 위반)
  require: [{block, has | is | lacks}]   그 자리에 글이 있어야/정확히 그 글이어야(쪽 끝 \\f·\\n 무시)/없어야
  lacks: [{block, lacks}]  require 의 lacks 와 같음(옛 꼴)
"""

import argparse
import importlib.util
import json
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def check(rulings, corpus):
    """판정 목록 · 말뭉치 `[(자리, 갈래, 문안)]` → (위반 `[(id, 설명)]`, 집계 dict)."""
    by = {}
    for src, _cat, text in corpus:
        by.setdefault(src, text)
    bad = []
    n = {"판정": len(rulings), "금지": 0, "필수": 0}
    for r in rulings:
        rid, why = r.get("id", "?"), str(r.get("판정", ""))[:50]
        pool = [(s, t) for s, c, t in corpus if r.get("scope") in (None, c)]
        skip = set(r.get("except_blocks", [])) | set(r.get("allow_blocks", []))
        for pat in r.get("forbid", []):
            n["금지"] += 1
            bad += [
                (rid, f"{s} 에 「{pat}」 — {why}") for s, t in pool if s not in skip and pat in t
            ]
        for pat in r.get("forbid_re", []) + r.get("forbid_regex", []):
            n["금지"] += 1
            rx = re.compile(pat)
            bad += [
                (rid, f"{s} 에 /{pat}/ — {why}") for s, t in pool if s not in skip and rx.search(t)
            ]
        ao = r.get("allow_only")
        if ao:
            n["금지"] += 1
            ok = set(ao.get("blocks", []))
            bad += [
                (rid, f"{s} 에 「{ao['has']}」(허용 자리 밖) — {why}")
                for s, t in pool
                if ao["has"] in t and s not in ok
            ]
        for q in r.get("require", []) + r.get("lacks", []):
            n["필수"] += 1
            v = by.get(q["block"])
            if "is" in q:
                good, want = v is not None and v.rstrip("\f\n") == q["is"], f"「{q['is']}」 그대로"
            elif "lacks" in q:
                good, want = v is not None and q["lacks"] not in v, f"「{q['lacks']}」 없이"
            else:
                good, want = v is not None and q["has"] in v, f"「{q['has']}」"
            if not good:
                where = "자리가 없다" if v is None else "어긋남"
                bad.append((rid, f"{q['block']} — {want} ({where}) — {why}"))
    return bad, n


def load_adapter(game):
    p = os.path.join(REPO, "games", game, "tools", "rulings_corpus.py")
    if not os.path.isfile(p):
        return None
    sys.path.insert(0, os.path.dirname(p))  # 어댑터가 게임 `common` 을 임포트한다
    spec = importlib.util.spec_from_file_location(f"rulings_corpus_{game}", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    a = ap.parse_args(argv)
    path = os.path.join(REPO, "games", a.game, "master_rulings.json")
    if not os.path.isfile(path):
        print(f"  마스터 판정 문안 — {a.game}: master_rulings.json 없음(안 쟀다)")
        return 1
    mod = load_adapter(a.game)
    if mod is None:
        print(f"  마스터 판정 문안 — {a.game}: tools/rulings_corpus.py 없음(안 쟀다)")
        return 1
    with open(path, encoding="utf-8") as f:
        rulings = json.load(f)["rulings"]
    corpus = list(mod.corpus())
    bad, n = check(rulings, corpus)
    extra = getattr(mod, "extra", None)  # 말뭉치로 못 나타내는 게임 고유 대조(롬 주소 등)
    if extra:
        for r in rulings:
            bad += [(r.get("id", "?"), m) for m in extra(r)]
    print(
        f"  마스터 판정 문안 — 판정 {n['판정']} · 금지 {n['금지']} · 필수 {n['필수']}"
        f" · 훑은 문안 {len(corpus)} · 위반 {len(bad)}"
    )
    for rid, m in bad[:20]:
        print(f"    ✗ [{rid}] {m}")
    if len(corpus) == 0:
        print("    ✗ 말뭉치가 비었다 — 0 은 통과가 아니라 「안 쟀다」")
        return 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
