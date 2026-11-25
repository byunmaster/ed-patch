#!/usr/bin/env python3
"""줄·쪽 나눔 지표 — 규칙 2-16 을 사람 눈이 아니라 **조판 결과의 숫자**로 센다(마스터 10-26).

`wrap_pages` 의 **출력을 가로채** 센다(`check_line_breaks` 와 같은 방식 — 창 수 계약·하드개행이
들어간 실제 조판만 정확하다). 후보 조판도 잡히므로 같은 쪽 나열은 한 번만 센다.

지표 다섯(전부 낮을수록 좋다 — 래칫: 기준선보다 늘면 실패, 줄면 `--freeze`):
  a  쪽 끝 한 어절 고아     쪽 마지막 줄이 한 어절이고 문장이 다음 쪽으로 이어진다
  b  문장 중간 한 낱말 쪽   a 중에서 그 한 낱말이 다음 쪽 첫 어절과 한 덩어리(`split_reason`)
  e  굳은 명사구 갈림       [명사+명사] 이음이 줄 끝·첫머리로 갈렸다(앞 어절이 조사·어미·관형형·부사로 안 끝나고, 같은 이음이 대사 전량에 2회 이상)
  c  문장 중간 손 개행      조판기에 들어온 문안의 손 개행(`\n`·HARD_NL)이 **문장 끝이 아닌 자리**에 있다
  d  절째 내리면 들어가는데 쪼갠 줄
                            한 줄에서 시작한 절(쉼표 뒤~)이 다음 줄에 걸쳐 갈렸는데, 그 절 전체를
                            다음 줄 하나에 모으면 폭 안에 든다

  python3 tools/check_page_split.py             # 요약 + 기준선 대비
  python3 tools/check_page_split.py --report    # → work/review/page_split.md (정발 문안 없음, 우리 문안)
  python3 tools/check_page_split.py --freeze    # 기준선 갱신(줄었을 때만)
"""

import json
import os
import sys

os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from common import REVIEW_DIR
from text import krwrap as K

HARD_NL = R.HARD_NL
BASELINE = os.path.join(os.path.dirname(__file__), "..", "page_split_baseline.json")
SENT_END = ".?!…」』”~"
CLAUSE_END = ",，"
WIDTH = 14.0


def _sentence_done(line: str) -> bool:
    return bool(line) and line.rstrip()[-1] in SENT_END


def _wid(words):
    return K.text_width(" ".join(words))


def metrics_for_pages(pages):
    """쪽 나열 하나의 (a, b, d) 사례 [(지표, 문맥)]."""
    out = []
    for i, pg in enumerate(pages):
        if not pg:
            continue
        last = pg[-1].split()
        final_page = i == len(pages) - 1
        if len(last) == 1 and not final_page and not _sentence_done(pg[-1]):
            nxt = pages[i + 1][0].split() if pages[i + 1] else []
            out.append(("a", pg))  # 쪽 마지막 줄이 한 어절이고 문장이 다음 쪽으로 이어진다
            if nxt and K.split_reason(last[-1], nxt[0]):
                out.append(("b", pg))  # 그 한 낱말이 다음 쪽 첫 어절과 한 덩어리(본용언+보조용언 등)
        for j in range(len(pg) - 1):
            cur, nxt = pg[j].split(), pg[j + 1].split()
            if not cur or not nxt or _sentence_done(pg[j]) or pg[j].rstrip()[-1] in CLAUSE_END:
                continue
            start = 0
            for k, w in enumerate(cur):
                if w[-1] in CLAUSE_END:
                    start = k + 1
            if start == 0 or start >= len(cur):
                continue
            end = len(nxt)
            for k, w in enumerate(nxt):
                if w[-1] in CLAUSE_END or w[-1] in SENT_END:
                    end = k + 1
                    break
            else:
                continue  # 절이 그 다음 줄로 더 이어진다 — 대상 아님
            if end != len(nxt):
                continue  # 다음 줄 중간에서 절이 끝난다 — 내려도 줄이 안 비는 이어 쓰기, 대상 아님
            if _wid(cur[start:] + nxt) <= WIDTH:
                out.append(("d", pg[j : j + 2]))
    return out


PARTICLES = ("은", "는", "이", "가", "을", "를", "의", "에", "에게", "와", "과", "도", "로", "으로", "만", "에서", "께서", "이다", "이라고")
NOT_NOUN = {"이제", "대체", "어찌", "얼마", "잠깐", "몹시", "지금", "아직", "방금", "역시", "정말", "제발", "부디"}


def noun_lexicon(allseq):
    """조사가 붙은 꼴이 대사 어딘가에 있는 어절만 명사로 본다(형태소 분석기가 없어 코퍼스로 근사 — 어미·부사는 조사 꼴이 거의 없다)."""
    toks = set()
    for _scn, pages in allseq:
        for pg in pages:
            toks.update(" ".join(pg).split())
    toks = {t.rstrip(".,!?…」』”~") for t in toks}
    nouns = set()
    for t in toks:
        for pt in PARTICLES:
            if len(t) > len(pt) + 1 and t.endswith(pt):
                nouns.add(t[: -len(pt)])
    return nouns - NOT_NOUN


def _nounish(w: str, lex) -> bool:
    return w in lex


def split_pairs(pages):
    """쪽 나열의 줄 경계 (앞 어절, 뒤 어절) 목록 — 쪽 안과 쪽 사이 모두."""
    out = []
    flat = [ln for pg in pages for ln in pg]
    for a, b in zip(flat, flat[1:]):
        wa, wb = a.split(), b.split()
        if wa and wb:
            out.append((wa[-1], wb[0]))
    return out


def hand_newlines(text: str):
    """문장 중간의 하드개행 위치 수와 문맥."""
    out = []
    for m in range(len(text)):
        if text[m] not in (HARD_NL, "\n"):
            continue
        before = text[:m].rstrip().rstrip("}")
        before = before.rsplit("{p}", 1)[-1].rstrip()
        if before and before[-1] not in SENT_END:
            out.append(text[max(0, m - 12) : m + 12].replace(HARD_NL, "↵").replace("\n", "↵"))
    return out


def collect():
    orig, seen = K.wrap_pages, []

    def spy(*a, **kw):
        pages = orig(*a, **kw)
        seen.append((a[0] if a else kw.get("text", ""), pages))
        return pages

    K.wrap_pages = R.kr_wrap_pages = spy
    cases, dedup, ddup, allseq = [], set(), set(), []
    try:
        for scn, lba, size in R.SCN_FILES:
            seen.clear()
            R.build_scene(scn, lba, size, False, False)
            for text, pages in seen:
                key = tuple(tuple(p) for p in pages)
                if key not in dedup:
                    dedup.add(key)
                    allseq.append((scn, pages))
                    for kind, ctx in metrics_for_pages(pages):
                        cases.append((scn, kind, " / ".join(ctx)))
                if text not in ddup:
                    ddup.add(text)
                    for ctx in hand_newlines(text):
                        cases.append((scn, "c", ctx))
    finally:
        K.wrap_pages = R.kr_wrap_pages = orig
    cases += noun_phrase_splits(allseq)
    return cases


def noun_phrase_splits(allseq):
    """지표 e — 같은 이음이 대사 전량에 2회 이상인 [명사+명사]가 줄 경계로 갈린 곳."""
    from collections import Counter

    lex = noun_lexicon(allseq)
    bigram = Counter()
    for _scn, pages in allseq:
        for pg in pages:
            ws = " ".join(pg).split()
            bigram.update(zip(ws, ws[1:]))
    out = []
    for scn, pages in allseq:
        for a, b in split_pairs(pages):
            if bigram[(a, b)] >= 2 and _nounish(a, lex) and _nounish(b, lex) and not K.split_reason(a, b):
                out.append((scn, "e", f"{a} ⏎ {b}"))
    return out


def main():
    cases = collect()
    cnt = {k: sum(1 for c in cases if c[1] == k) for k in "abcde"}
    base = None
    if os.path.exists(BASELINE):
        base = json.load(open(BASELINE))
    print("줄·쪽 나눔 지표 — " + " · ".join(f"{k} {cnt[k]}" for k in "abcde"), end="")
    if base:
        print(" (기준선 " + " · ".join(f"{k} {base.get(k, "-")}" for k in "abcde") + ")")
    else:
        print(" (기준선 없음)")
    if "--report" in sys.argv:
        os.makedirs(REVIEW_DIR, exist_ok=True)
        path = os.path.join(REVIEW_DIR, "page_split.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# 줄·쪽 나눔 지표 {cnt}\n")
            for scn, kind, ctx in cases:
                f.write(f"\n- {scn} [{kind}] {ctx}\n")
        print(f"  → {path}")
    if "--freeze" in sys.argv:
        if base and any(cnt[k] > base.get(k, 10**9) for k in "abcde"):
            print("  ✗ 기준선보다 늘었다 — 얼리지 않는다")
            sys.exit(1)
        json.dump(cnt, open(BASELINE, "w"), indent=1)
        print("  기준선 갱신")
        return
    if base and any(cnt[k] > base.get(k, 0) for k in "abcde"):
        print("  ❌ 기준선보다 늘었다 — 줄·쪽 나눔 규칙(2-16) 위반이 새로 생겼다")
        sys.exit(1)


if __name__ == "__main__":
    main()
