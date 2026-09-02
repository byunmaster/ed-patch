"""자체 코드표(코드 → 일본어 글자)를 **알려진 평문**으로 푼다.

카나 블록은 실측으로 이미 안다(`textenc.kana_map`). 남은 건 한자·기호인데, 같은 작품의
**새턴 ED3 는 대본이 생 SJIS** 라 그걸 평문으로 쓴다 — 카나만 남긴 「골격」이 새턴 문장과
일치하면, 골격 사이에 낀 미지 코드가 곧 그 자리의 글자다.

⚠ **이건 비결정적 제안 단계다.** 산출물(`charmap_<disc>.json`)이 정본이고, 빌드는 정본만
   읽는다(patcher-checklist 3). 새턴 덤프가 없는 머신에서도 빌드는 돌아야 한다.
⚠ **새턴의 한국어 문안은 쓰지 않는다** — 여기서 읽는 건 JP 원문뿐이고, 얻는 것도
   「코드 → 글자」 표다(patcher-checklist 10-D: 타이틀 사이는 원문 해시 사전으로만).
⚠ ED4 는 이 로제타가 없다 — `--from-disc ed3` 로 ED3 표를 밑에 깔고 어긋난 만큼만 푼다.
"""

import argparse
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import textenc

ROSETTA = os.path.join(
    common.main_repo(),
    ".claude",
    "worktrees",
    "ss-ed3",
    "games",
    "ss-ed3",
    "work",
    "derived",
    "map_jp",
)
ANCHOR_MIN = 5  # 이 길이 이상의 카나 연속을 닻으로 쓴다


def load_rosetta(path):
    """[페이지 문자열] — 새턴 JP 덤프의 블록을 페이지(\\f)로 갈라 모은다."""
    pages = []
    files = sorted(glob.glob(os.path.join(path, "*.json")))
    if not files:
        raise SystemExit(
            f"로제타(새턴 JP 덤프)가 없다: {path}\n"
            f"  `sh scripts/worktree.sh ss-ed3` 로 그 트리를 열고 덤프를 먼저 뜬다."
        )
    for p in files:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        for b in doc.get("blocks", []):
            t = b.get("text") or ""
            for page in t.split("\f"):
                if len(page) >= 6:
                    pages.append(page)
    return pages


def load_runs(disc):
    out = []
    for p in sorted(glob.glob(os.path.join(common.OUT_DIR, disc, "script", "*.json"))):
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        for r in doc["runs"]:
            out.append(r["codes"])
    return out


def tokenize(codes, known):
    """[(글자 or None, 코드)] — 아는 코드는 글자로, 0x00 은 버린다(비표시로 본다)."""
    toks = []
    for w in codes:
        if w == 0x00:
            continue
        toks.append((known.get(w), w))
    return toks


def anchors(toks):
    """[(시작, 길이, 문자열)] — 연속으로 아는 글자 구간, 긴 것부터."""
    out, i = [], 0
    while i < len(toks):
        if toks[i][0] is None:
            i += 1
            continue
        j = i
        while j < len(toks) and toks[j][0] is not None:
            j += 1
        if j - i >= ANCHOR_MIN:
            out.append((i, j - i, "".join(t[0] for t in toks[i:j])))
        i = j
    out.sort(key=lambda x: -x[1])
    return out


def solve(runs, pages, known):
    """{코드: Counter(글자)} — 골격이 통째로 맞는 짝에서만 표를 걷는다."""
    joined = "\x00".join(pages)
    starts, pos = [], 0
    for p in pages:
        starts.append(pos)
        pos += len(p) + 1
    votes = collections.defaultdict(collections.Counter)
    matched = ambiguous = 0
    for codes in runs:
        toks = tokenize(codes, known)
        if not any(t[0] is None for t in toks):
            continue  # 미지가 없으면 배울 게 없다
        anc = anchors(toks)
        if not anc:
            continue
        ai, alen, atext = anc[0]
        cands = []
        at = joined.find(atext)
        while at != -1 and len(cands) < 40:
            cands.append(at)
            at = joined.find(atext, at + 1)
        good = []
        for at in cands:
            # 페이지 안에서 토큰 수가 정확히 같아야 한다 (1코드 = 1글자)
            k = _page_index(starts, at)
            ps, pe = starts[k], starts[k] + len(pages[k])
            lo = at - ai
            if lo < ps or lo + len(toks) > pe:
                continue
            seg = joined[lo : lo + len(toks)]
            if any(ch is not None and ch != seg[i] for i, (ch, _) in enumerate(toks)):
                continue
            good.append(seg)
        if len(good) != 1:
            ambiguous += 1 if good else 0
            continue
        matched += 1
        seg = good[0]
        for i, (ch, code) in enumerate(toks):
            if ch is None:
                votes[code][seg[i]] += 1
    return votes, matched, ambiguous


def _page_index(starts, at):
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= at:
            lo = mid
        else:
            hi = mid - 1
    return lo


# ── JIS X 0208 순서 보간 ────────────────────────────────────────────────────
# 표가 **JIS 순서에서 안 쓰는 글자만 뺀 목록**이라는 것은 실측으로 확인했다
# (골격 대조로 배운 한자 870개에 순서 역전이 **0**건, 2026-09-03).
# 그러면 아는 두 자리 사이의 빈칸은 **셈만 맞으면 강제**된다 — 후보를 고를 여지가 없다.
# ⚠ 셈이 안 맞으면 **채우지 않는다**. 억지로 밀면 그 뒤가 통째로 한 칸씩 밀린다.

jis_order = textenc.jis_order


def fill_jis(known, kana):
    """아는 코드 사이 빈칸을 JIS 순서로 메운다. 반환: (채운 것, 못 채운 구간)"""
    order = jis_order()
    idx = {ch: i for i, ch in enumerate(order)}
    anchors = sorted((c, ch) for c, ch in known.items() if ch in idx and c not in kana)
    filled, gaps = {}, []
    for (c1, ch1), (c2, ch2) in zip(anchors, anchors[1:], strict=False):
        need = c2 - c1 - 1
        if need <= 0:
            continue
        i1, i2 = idx[ch1], idx[ch2]
        span = order[i1 + 1 : i2]
        if len(span) != need:
            gaps.append((c1, c2, need, len(span)))
            continue
        for k, ch in enumerate(span):
            filled[c1 + 1 + k] = ch
    return filled, gaps


def order_bounds(code, known, idx, kana):
    """이 코드의 글자가 들어갈 JIS 순서 창 (아래 이웃, 위 이웃)."""
    lo = hi = None
    for c, ch in known.items():
        if c in kana or ch not in idx:
            continue
        if c < code and (lo is None or c > lo[0]):
            lo = (c, idx[ch])
        elif c > code and (hi is None or c < hi[0]):
            hi = (c, idx[ch])
    return (lo[1] if lo else -1), (hi[1] if hi else 1 << 30)


def accept(votes, known, kana, min_votes, min_ratio):
    """채택 — 표가 많거나(통계), **JIS 순서 창 안에 들어가면**(구조) 받는다.

    ⚠ 구조 쪽이 더 세다. 표 하나짜리라도 순서가 강제하면 후보가 하나뿐이라 틀릴 여지가
      없고, 반대로 표가 아무리 많아도 순서를 어기면 그건 골격 오정렬이다.
    """
    order = jis_order()
    idx = {ch: i for i, ch in enumerate(order)}
    taken, rejected = {}, {}
    for code in sorted(votes):
        cnt = votes[code]
        if code in known:
            continue
        lo, hi = order_bounds(code, known, idx, kana)
        ok = [(ch, n) for ch, n in cnt.most_common() if ch in idx and lo < idx[ch] < hi]
        if not ok:
            # 순서를 못 쓰는 글자(기호·비 JIS)는 통계로만 본다
            (ch, n), tot = cnt.most_common(1)[0], sum(cnt.values())
            if n >= min_votes and n / tot >= min_ratio:
                taken[code] = ch
            else:
                rejected[code] = dict(cnt.most_common(4))
            continue
        ch, n = ok[0]
        tot = sum(cnt.values())
        if len(ok) == 1 or n / tot >= min_ratio or n >= min_votes:
            taken[code] = ch
        else:
            rejected[code] = dict(cnt.most_common(4))
    return taken, rejected


def enforce_order(learned, kana):
    """JIS 순서를 어기는 배정을 **버린다** — 최장 증가 부분열만 남긴다.

    표가 JIS 순서라는 건 구조 계약이다(역전 0건으로 확인). 역전이 생겼다면 그건 「예외적인
    글자」가 아니라 **골격이 어긋난 채 배운 것**이다. 남기면 그 자리만 틀리는 게 아니라
    이웃의 순서 창까지 망가뜨려 오염이 번진다.

    반환: (남긴 것, 버린 것)
    """
    order = jis_order()
    idx = {ch: i for i, ch in enumerate(order)}
    seq = [(c, ch) for c, ch in sorted(learned.items()) if c not in kana and ch in idx]
    import bisect

    tails, back, pos = [], [None] * len(seq), []
    for i, (_, ch) in enumerate(seq):
        j = bisect.bisect_left(tails, idx[ch])
        if j == len(tails):
            tails.append(idx[ch])
            pos.append(i)
        else:
            tails[j] = idx[ch]
            pos[j] = i
        back[i] = pos[j - 1] if j else None
    keep = set()
    i = pos[-1] if pos else None
    while i is not None:
        keep.add(seq[i][0])
        i = back[i]
    kept = {c: ch for c, ch in learned.items() if c in kana or c not in dict(seq) or c in keep}
    dropped = {c: ch for c, ch in learned.items() if c not in kept}
    return kept, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--rosetta", default=ROSETTA)
    ap.add_argument("--min-votes", type=int, default=2)
    ap.add_argument("--min-ratio", type=float, default=0.8, help="1위 글자가 차지해야 할 비율")
    ap.add_argument("--rounds", type=int, default=4, help="배운 표를 다시 넣어 반복")
    ap.add_argument("--fill-jis", action="store_true", help="아는 자리 사이를 JIS 순서로 메운다")
    ap.add_argument("--write", action="store_true", help="정본(charmap_<disc>.json)에 쓴다")
    a = ap.parse_args()

    pages = load_rosetta(a.rosetta)
    runs = load_runs(a.disc)
    known = dict(textenc.kana_map(a.disc))
    known[0x01] = "\n"
    print(f"로제타 페이지 {len(pages):,} · PS1 런 {len(runs):,} · 시작 기지 {len(known)}")

    learned, conflicts = {}, {}
    for rnd in range(a.rounds):
        votes, matched, amb = solve(runs, pages, known)
        kana_codes = set(textenc.kana_map(a.disc))
        taken, conflicts = accept(votes, known, kana_codes, a.min_votes, a.min_ratio)
        new = 0
        for code, ch in taken.items():
            known[code] = ch
            learned[code] = ch
            new += 1
        print(
            f"  {rnd + 1}회차: 일치 {matched:,} (모호 {amb:,}) · 새로 {new} · 누적 {len(learned)}"
        )
        if not new:
            break

    kana_m = textenc.kana_map(a.disc)
    learned, dropped = enforce_order(learned, set(kana_m))
    known = {c: ch for c, ch in known.items() if c not in dropped}
    if dropped:
        print(
            f"  순서 정합: {len(dropped)} 버림 — "
            + ", ".join(f"{c:03x}={ch}" for c, ch in list(dropped.items())[:8])
        )
    if a.fill_jis:
        filled, gaps = fill_jis(known, kana_m)
        for c, ch in filled.items():
            known.setdefault(c, ch)
            learned.setdefault(c, ch)
        print(f"  JIS 보간: {len(filled)} 채움 · 셈이 안 맞아 건너뛴 구간 {len(gaps)}")
        if gaps:
            print(
                "    "
                + ", ".join(
                    f"0x{a_:03x}~0x{b:03x}(빈칸 {n} vs JIS {m})" for a_, b, n, m in gaps[:6]
                )
            )
    kana = len(kana_m)
    print(
        f"\n표: 카나 {kana} + 배운 것 {len(learned)} = {kana + len(learned)}  · 미결 {len(conflicts)}"
    )
    if conflicts:
        sample = list(conflicts.items())[:8]
        print("  미결 예:", ", ".join(f"{c:03x}→{v}" for c, v in sample))

    if a.write:
        doc = {
            "disc": a.disc,
            "note": "코드 → 일본어 글자. 카나는 textenc.kana_map 이 계산하고 여기엔 안 담는다.",
            "source": "solve_charmap.py (새턴 ED3 JP 덤프를 알려진 평문으로 골격 대조)",
            "map": {f"{c:04x}": ch for c, ch in sorted(learned.items())},
        }
        p = textenc.charmap_path(a.disc)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        print(f"→ {p}")


if __name__ == "__main__":
    main()
