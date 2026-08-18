#!/usr/bin/env python3
"""정발 대사 전문을 외부 맞춤법 검사기에 돌려 치환 후보를 뽑는다 — ps1-ed1+2 어댑터.

분류·API·보고서 생성은 **공용 엔진 `shared/text/spellcheck.py`** 가 한다(다른 게임에서도
쓴다). 여기서는 이 게임 몫만 맡는다 — 코퍼스를 어디서 긁는지(`dump_dos_corpus`),
결과를 어디에 쓰는지(REVIEW_DIR), 채택분을 어느 표에 넣는지(`dos_spelling_fixes.json`).

어투는 보존하고 띄어쓰기·오타만 고치는 기준(A급 = 공백만 차이)과 그 근거는 공용 엔진의
docstring 에 있다.

⚠ 산출물은 정발 문안이라 REVIEW_DIR(gitignore) 로만 나간다.
⚠ 외부 서비스에 정발 문안을 보낸다 — 유저 승인 하에만 실행할 것.

사용
  python3 tools/spellcheck_corpus.py ED1 ED2          # 전체(청크 병렬)
  python3 tools/spellcheck_corpus.py ED1 --limit 5    # 앞 5청크만(시험)
  python3 tools/spellcheck_corpus.py ED1 --report     # 캐시만으로 보고서 재생성
  python3 tools/spellcheck_corpus.py ED1 --apply      # A급을 replace 에 반영
"""

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_REPO, "shared"))

from common import REVIEW_DIR, ROOT  # noqa: E402
from dump_dos_corpus import OUT, collect  # noqa: E402
from text import spellcheck as sc  # noqa: E402

SPELL_JSON = os.path.join(ROOT, "dos_spelling_fixes.json")


def run(game, chunk, limit, report_only, jobs):
    os.makedirs(OUT, exist_ok=True)
    uniq = collect(game)
    keys = sorted(uniq)
    meta = {s: {"n": len(v["at"]), "inject": v["inject"]} for s, v in uniq.items()}
    print(f"{game}: 문장 {len(keys)}종 (주입코드 {sum(v['inject'] for v in uniq.values())})")

    cache_p = os.path.join(OUT, f"{game}_spell_cache.json")
    cache = json.load(open(cache_p, encoding="utf-8")) if os.path.exists(cache_p) else {}
    save = lambda c: json.dump(c, open(cache_p, "w", encoding="utf-8"), ensure_ascii=False)  # noqa: E731

    parts = sc.chunks(keys, chunk)
    n_new = len([p for p in parts if "\n".join(p) not in cache])
    print(f"  청크 {len(parts)}개 · 캐시 {len(parts) - n_new} · 요청 {0 if report_only else n_new}")
    if not report_only:
        sc.fetch(parts[:limit] if limit else parts, cache, jobs=jobs, on_save=save)

    changed, pairs, skewed = sc.collate(parts, cache, meta)
    known = json.load(open(SPELL_JSON, encoding="utf-8")).get("replace", [])
    auto, manual, dropped = sc.classify(pairs, known)

    p = os.path.join(OUT, f"{game}_spell_report.md")
    open(p, "w", encoding="utf-8").write(
        sc.report(
            f"{game} 맞춤법 검사 결과 (engram, proof)",
            len(keys),
            changed,
            auto,
            manual,
            dropped,
            skewed,
        )
    )
    json.dump(
        {"auto": [[x, y] for x, y, _ in auto], "manual": [[x, y] for x, y, _ in manual]},
        open(os.path.join(OUT, f"{game}_spell_pairs.json"), "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=1,
    )
    print(f"  → {os.path.relpath(p, REVIEW_DIR)} · A급 {len(auto)} · B급 {len(manual)}")
    return auto


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("games", nargs="*", default=["ED1"])
    ap.add_argument("--chunk", type=int, default=900, help="요청당 최대 글자 수")
    ap.add_argument("--jobs", type=int, default=4, help="동시 요청 수")
    ap.add_argument("--limit", type=int, default=0, help="요청 청크 수 제한(시험용)")
    ap.add_argument("--report", action="store_true", help="API 호출 없이 캐시로 보고서만")
    ap.add_argument("--apply", action="store_true", help="A급을 replace 에 반영")
    a = ap.parse_args()
    auto = []
    for g in a.games or ["ED1"]:
        auto += run(g, a.chunk, a.limit, a.report, a.jobs)
    if a.apply:
        add = sc.merge_replace(SPELL_JSON, auto)
        print(f"  dos_spelling_fixes.json: replace +{len(add)}")


if __name__ == "__main__":
    main()
