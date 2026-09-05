#!/usr/bin/env python3
"""**우리 번역 정본**을 외부 맞춤법 검사기에 돌려 치환 후보를 뽑는다 — ps1-ed1+2 어댑터.

분류·API·보고서는 **공용 엔진 `shared/text/spellcheck.py`** 가 한다. 여기서는 이 게임 몫만
맡는다 — 코퍼스를 어디서 긁는지(`script/*.json`), 결과를 어디에 두는지(REVIEW_DIR).

⚠ **자매품 `spellcheck_corpus.py` 와 가른 이유.** 저건 **정발 코퍼스**(`dump_dos_corpus`)를
긁어 `dos_spelling_fixes.json` 에 넣는다 — 정발을 저본으로 쓰던 시절의 도구다. 자체 번역으로
돌아선 뒤(2026-08-18) 검사 대상은 **우리 문안**이고, 채택분은 파생표가 아니라 **정본
`script/` 에 직접** 들어간다. 코퍼스도 산출물도 달라서 한 파일에 못 담는다.

🔴 **마크업을 벗겨 보낸다.** 우리 문안엔 `{p}`(창 나눔) · `{n}`(강제 개행) · `{c}`(인자
자리)와 센티널(`\\x1a` 이름 · `\\x17` 아이템 · `\\x1b` 수치)이 섞여 있다. 그대로 보내면
검사기가 그걸 오타로 보고 **치환쌍에 끌어들여** 구조를 깨뜨린다. 벗긴 문장만 보내고,
치환은 나중에 **원문안에 그 문자열이 그대로 있을 때만** 적용한다.

⚠ 마크업이 있던 블록은 `inject` 로 표시해 **A급(자동 반영)에서 뺀다** — 공용 엔진이 주입
자리 주변에서 조사를 지어내는 걸 이미 겪었다(그쪽 docstring).

⚠ **외부 서비스에 문안을 보낸다.** 우리가 쓴 번역이라 저작권 문제는 없지만 유출은 유출이다 —
유저 승인 하에만 돌린다(2026-08-19 승인).

  python3 tools/spellcheck_ours.py ED1 ED2         # 전체
  python3 tools/spellcheck_ours.py ED1 --limit 3   # 앞 3청크만(시험)
  python3 tools/spellcheck_ours.py ED1 --report    # 요청 없이 캐시로 보고서만
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from common import REVIEW_DIR, ROOT

sys.path.insert(0, os.path.join(ROOT, "..", "..", "shared"))
from text import spellcheck as sc

OUT = os.path.join(REVIEW_DIR, "spell_ours")
MARKUP = re.compile(r"\{[pnc]\}|[\x17\x1a\x1b]")


def collect(game):
    """`{문장: {at: [좌표], inject: 마크업이 있었나}}` — `script/<game>SCN*.json` 전량."""
    uniq = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "script", f"{game}SCN*.json"))):
        scn = os.path.basename(p)[:-5]
        with open(p, encoding="utf-8") as f:
            for eid, v in json.load(f).items():
                t = (v or {}).get("t") or ""
                bare = MARKUP.sub(" ", t).strip()
                bare = re.sub(r"\s+", " ", bare)
                if len(bare) < 2:
                    continue
                e = uniq.setdefault(bare, {"at": [], "inject": False})
                e["at"].append(f"{scn}:{eid}")
                e["inject"] |= bool(MARKUP.search(t))
    return uniq


def run(game, chunk, limit, report_only, jobs):
    os.makedirs(OUT, exist_ok=True)
    uniq = collect(game)
    keys = sorted(uniq)
    meta = {s: {"n": len(v["at"]), "inject": v["inject"]} for s, v in uniq.items()}
    print(f"{game}: 문장 {len(keys)}종 (마크업 보유 {sum(v['inject'] for v in uniq.values())})")

    cache_p = os.path.join(OUT, f"{game}_cache.json")
    cache = json.load(open(cache_p, encoding="utf-8")) if os.path.exists(cache_p) else {}

    def save(c):
        json.dump(c, open(cache_p, "w", encoding="utf-8"), ensure_ascii=False)

    parts = sc.chunks(keys, chunk)
    n_new = len([p for p in parts if "\n".join(p) not in cache])
    print(f"  청크 {len(parts)}개 · 캐시 {len(parts) - n_new} · 요청 {0 if report_only else n_new}")
    if not report_only:
        sc.fetch(parts[:limit] if limit else parts, cache, jobs=jobs, on_save=save)

    changed, pairs, skewed = sc.collate(parts, cache, meta)
    auto, manual, dropped = sc.classify(pairs)

    p = os.path.join(OUT, f"{game}_report.md")
    open(p, "w", encoding="utf-8").write(
        sc.report(
            f"{game} 우리 문안 맞춤법 (engram, proof)",
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
        open(os.path.join(OUT, f"{game}_pairs.json"), "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=1,
    )
    print(f"  → {os.path.relpath(p, REVIEW_DIR)} · A급 {len(auto)} · B급 {len(manual)}")
    return auto


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("games", nargs="+")
    ap.add_argument("--chunk", type=int, default=900, help="요청당 최대 **글자 수**")
    ap.add_argument("--limit", type=int, default=0, help="요청 청크 수 제한(시험용)")
    ap.add_argument("--jobs", type=int, default=4, help="동시 요청 수")
    ap.add_argument("--report", action="store_true", help="요청 없이 캐시로 보고서만")
    a = ap.parse_args()
    for g in a.games:
        run(g, a.chunk, a.limit, a.report, a.jobs)


if __name__ == "__main__":
    main()
