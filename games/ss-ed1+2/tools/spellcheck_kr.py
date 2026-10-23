#!/usr/bin/env python3
"""**우리 문안**(새턴 몫)을 외부 맞춤법 검사기에 돌려 띄어쓰기·오타 후보를 뽑는다 — ss-ed1+2 어댑터(규칙 3-1, 마스터 10-18 「외부검사기 ok」).

분류·API·보고서는 공용 엔진 `shared/text/spellcheck.py` 가 한다. 여기서는 이 게임 몫만 맡는다 —
코퍼스(`script/system.json` · `scn.json` · `ui.json` · `title.json` — 씬 대사 본편은 PS1 저본이라 PS1 쪽 라운드에서 검사한다),
캐시·보고서 자리(`work/review/`), 채택분 반영.

🔴 **A급(공백만 차이)만 반영 후보다.** B급(글자 바뀜)은 말투·고어체를 표준어로 미는 오작동이 섞여 **사람이 고른다**.
   주입 자리(`%s`·`%d`·`%c` 인자) 주변 제안은 공용 엔진이 A급에서 뺀다. **문장 단위**로 반영한다 — 그 문장의 치환쌍이 전부 채택 목록에 있을 때만.
⚠ 외부 서비스에 **우리 한국어 문안만** 보낸다(일본어 원문은 안 보낸다).
⚠ 이 검사기는 400 을 「너무 빠르다」로 준다 — 한 번에 하나씩, 쉬어 가며 받는다(`fetch_slow`).

    python3 tools/spellcheck_kr.py --limit 3      # 시험
    python3 tools/spellcheck_kr.py                # 전량 받기(오래 걸린다 — 뒤에 걸어 둔다)
    python3 tools/spellcheck_kr.py --report       # 캐시로 보고서만
    python3 tools/spellcheck_kr.py --apply        # 채택 목록(`spell_accept.json`)대로 script 에 반영
"""

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(_HERE))), "shared"))

import common as C
from text import spellcheck as sc

SCRIPT = os.path.join(C.GAME_DIR, "script")
CACHE = os.path.join(C.REVIEW_DIR, "spell_cache.json")
REPORT = os.path.join(C.REVIEW_DIR, "spell_report.md")
ACCEPT = os.path.join(C.GAME_DIR, "spell_accept.json")
SEG = re.compile(r"[\n]|%c")


def _strings(node):
    """JSON 값 속 문자열을 `(컨테이너, 키, 문자열)` 로 — 번역 문안 자리만."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k.startswith("_"):
                continue
            if isinstance(v, str):
                yield node, k, v
            else:
                yield from _strings(v)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                yield node, i, v
            else:
                yield from _strings(v)


SOURCES = {
    "system.json": ("lines",),
    "scn.json": ("lines",),
    "ui.json": ("msgs",),
    "title.json": None,  # 전부
}


def _docs():
    for name, keys in SOURCES.items():
        path = os.path.join(SCRIPT, name)
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        roots = [d[k] for k in keys] if keys else [v for k, v in d.items() if not k.startswith("_")]
        yield path, d, roots


def collect():
    """`{문장: {"n": 등장 수, "inject": 주입 인자가 있나}}` — 블록을 개행·창 넘김으로 쪼갠 조각(한글이 든 것만)."""
    uniq = {}
    for _p, _d, roots in _docs():
        for root in roots:
            for _c, _k, v in _strings(root):
                for s in SEG.split(v):
                    s = s.strip()
                    if not s or not re.search(r"[가-힣]", s):
                        continue
                    rec = uniq.setdefault(s, {"n": 0, "inject": bool(re.search(r"%[sd]", s))})
                    rec["n"] += 1
    return uniq


def accepted():
    if not os.path.exists(ACCEPT):
        return set()
    with open(ACCEPT, encoding="utf-8") as f:
        return {tuple(p) for p in json.load(f)["replace"]}


def apply_fixes(fix):
    """채택된 문장 치환을 script 에 반영 → 고친 문자열 수."""
    n = 0
    for path, d, roots in _docs():
        ch = 0
        for root in roots:
            for cont, key, v in list(_strings(root)):
                new = v
                for s in SEG.split(v):
                    t = s.strip()
                    if t in fix:
                        new = new.replace(t, fix[t], 1)
                if new != v:
                    cont[key] = new
                    ch += 1
        if ch:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
                f.write("\n")
            n += ch
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    meta = collect()
    sents = sorted(meta)
    parts = sc.chunks(sents, 1500)
    if a.limit:
        parts = parts[: a.limit]
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    os.makedirs(C.REVIEW_DIR, exist_ok=True)

    def save(c):
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False)

    if not a.report and not a.apply:
        sc.fetch_slow(parts, cache, on_save=save)
    changed, pairs, skewed = sc.collate(parts, cache, meta)
    auto, manual, dropped = sc.classify(pairs, known=accepted())
    md = sc.report("ss-ed1+2 우리 문안 맞춤법", len(sents), changed, auto, manual, dropped, skewed)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"  검사 문장 {len(sents)} · 제안 {len(changed)} · A급 {len(auto)} · B급 {len(manual)} · 부호 공백 {dropped} · 줄 대응 깨짐 {skewed} → {REPORT}")
    if a.apply:
        ok = accepted()
        fix = {}
        for x, y, _m in changed:
            pr = sc.min_pairs(x, y)
            if pr and all(p in ok for p in pr):
                fix[x] = y
        print(f"  반영 {apply_fixes(fix)}곳 ({len(fix)}문장)")


if __name__ == "__main__":
    main()
