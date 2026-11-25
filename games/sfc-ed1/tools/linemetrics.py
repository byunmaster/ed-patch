"""줄·쪽 나눔 지표 — 번역 규칙 2-16 (전 기종, 마스터 10-26)을 **조판 결과**로 전수 계수한다.

사람·에이전트 눈이 아니라 기계 지표로 잡는다(마스터 「qa, style을 돌렸는데도 이런게 나오면 의미가 없는것 같네」).
대상 = 대사 구역(`typeset.region` == 씬)의 번역 조각 전량, 빌드와 같은 조판기(`typeset.Typesetter`)의 결과.

  (a) 쪽 끝 한 어절 고아 쪽 — 두 줄 이상인 쪽의 마지막 줄이 한 어절(한글이 든)
  (b) 문장 중간 한 낱말로 끝나는 쪽 — 문장 끝 부호로 끝나지 않는 쪽의 마지막 줄이 한 어절
  (c) 문장 중간 손 개행 — 번역 원고의 개행이 조판 결과에도 남았고, 앞 글이 문장 끝이 아니다
  (d) 절째 내리면 들어가는데 쪼갠 줄 — 줄이 넘쳐 이어진 문장에서 그 줄이 시작한 절이 다음 줄에 통째로 들어간다
  (f) 퇴행 — 규칙 전에 없던 끊김 가운데 본용언+보조용언·관형사 고아·명사구를 가른 것, 규칙 전엔 한 줄이던 문장을 쪼갠 것(0 이어야 한다 — 단 쪽 끝 고아를 없애며 치른 절 경계·한 줄 문장은 뺀다)
  (g) 보조용언·관형사 고아·명사구가 갈린 줄 끝 전량(원래부터 있던 것 포함 — 줄이는 방향)
  (h) 창 분배 — `<FF>` 로 이어진 대사창이 둘 이상인 글에서 마지막 창에 한 어절만 남은 것(a 와 다르다 — 줄이 아니라 창)
  (h2) 창 수를 안 늘리고 고르게 나눌 수 있는데 이웃 창의 줄 수 차가 2 이상인 것
  (e) [명사+명사] 굳은 구(「노예⏎상인」)가 줄 끝·첫머리로 갈린 곳 — 앞 어절이 조사·어미·관형형·부사로 안 끝나고 같은 이음이 대사 전량에 2회 이상

    python3 tools/linemetrics.py            # 지표 + 예
    python3 tools/linemetrics.py --check    # 기준선(linemetrics_baseline.json)보다 늘면 실패
    python3 tools/linemetrics.py --freeze   # 기준선을 지금 값으로 내린다(래칫 — 줄어들 때만)
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import typeset

BASELINE = common.GAME_DIR / "linemetrics_baseline.json"
PAGE_BREAK = ("<FF>", "<EF>", "<FE>", "<E0>")
END_PUNCT = set(".!?…」』~")
_HEADER = re.compile(r"<E3>.*?\n?<E1>", re.S)
_CTRL = re.compile(r"<[^>]*>")
_HANGUL = re.compile(r"[가-힣]")
KINDS = ("a", "b", "c", "d", "e", "f", "g", "h", "h2")


_pages = typeset.page_rows


def _sentence_end(word: str) -> bool:
    return bool(word) and word[-1] in END_PUNCT


def orphan_pages(res: str) -> tuple[list[str], list[str]]:
    """(a) 쪽 끝 한 어절 고아 · (b) 문장 중간 한 낱말로 끝나는 쪽 — 해당 쪽의 마지막 두 줄 글을 돌려 준다."""
    a, b = [], []
    for lines in _pages(res):
        last = lines[-1]
        if len(last) != 1 or not _HANGUL.search(last[0]):
            continue
        sample = " / ".join(" ".join(w) for w in lines[-2:])
        if len(lines) >= 2:
            a.append(sample)
            if not _sentence_end(last[0]):
                b.append(sample)
    return a, b


def soft_newlines(kr: str, res: str) -> list[str]:
    """(c) 번역 원고의 문장 중간 개행(앞 글이 문장 끝이 아니고 뒤가 글) 가운데 조판기가 공백으로 안 읽고 손 개행으로 남긴 것.
    장 제목 카드는 줄이 곧 연출이라 센 대상이 아니다."""
    out = []
    kept = typeset.soften(kr) if typeset.LINERULES else kr
    spans = typeset.LAST_SPANS
    for m in re.finditer(r"\n", kr):
        i = m.start()
        before = _CTRL.sub("", kr[:i])[-1:]
        after = kr[i + 1 : i + 2]
        if not before or before in END_PUNCT or before in " \n:,;" or after in ("<", "", " ", "\n") or kr[i - 1 : i] == ">":
            continue
        if typeset._keep_nl(kr, i):  # 장 제목 카드 · 앞 어절이 절 경계인 줄 끝은 손 개행이 아니라 절 나눔이다
            continue
        if typeset._TAGLINE.fullmatch(kr[max(0, i - 7) : i]):  # 파티 화자 표지 줄 — 머리다
            continue
        soft = next((sf for lo, hi, sf in spans if lo <= i < hi), False) if typeset.LINERULES else False
        if (kept[i] if soft else "\n") == "\n":
            out.append(_CTRL.sub("", kr[max(0, i - 14) : i]) + "⏎" + _CTRL.sub("", kr[i + 1 : i + 14]))
    return out


clause_splits = typeset.clause_misses
noun_splits = typeset.noun_splits


def bonded_breaks(res: str) -> list[str]:
    """(g) 갈리면 안 되는 이음(보조용언·관형사·명사구)이 줄 사이로 갈린 자리."""
    return [f"{a} / {b}" for a, b in typeset.break_pairs(res) if typeset._bad_break(a, b)]


regressions = typeset.regressions


def _logical(res: str) -> list[str]:
    """쪽·화자 머리 단위의 글(개행 포함) 목록 — 한 쪽 안에서 줄 나눔을 본다."""
    res = _HEADER.sub("", res)
    return [p for p in re.split(r"<FF>|<EF>|<FE>|<E0>", res) if p.strip()]


def measure(items: list[dict]) -> tuple[dict[str, int], dict[str, list[str]]]:
    ts = typeset.Typesetter()
    dm = typeset._dict()
    ml = ts.ml
    cnt = dict.fromkeys(KINDS, 0)
    ex: dict[str, list[str]] = {k: [] for k in KINDS}
    for it in items:
        if typeset.region(it["addr"]) != "씬":
            continue
        kr = it["kr"]
        res = ts(kr, it["addr"])
        a, b = orphan_pages(res)
        c = soft_newlines(kr, res)
        d = clause_splits(res, dm, ml)
        e = noun_splits(res)
        before = typeset.wrap(kr, dm, ml, rules=False)
        f = regressions(before, res)
        if typeset.orphan_count(res) < typeset.orphan_count(before):  # 쪽 끝 고아(2-16 ③)를 없애며 치른 절 경계·한 줄 문장 — 조판기가 받아들인 교환(마스터 10-31)
            f = [x for x in f if not x.startswith(("절 경계 상실", "문장 쪼갬"))]
        if any(x.startswith("절 경계 상실") for x in f):  # 2-10 한 줄 문장이 합치며 치른 절 경계 상실은 받는다(마스터 10-10 규칙 — 객관) — 그 규칙 없이도 있던 상실만 센다
            typeset.ONELINE = False
            try:
                off = typeset.Typesetter()(kr, it["addr"])
            finally:
                typeset.ONELINE = True
            if off != res and not any(x.startswith("절 경계 상실") for x in regressions(before, off)):
                f = [x for x in f if not x.startswith("절 경계 상실")]
        g = bonded_breaks(res)
        h, h2 = typeset.window_issues(res)
        sb0, pb0 = typeset.window_boundaries(typeset.wrap(kr, dm, ml, rules=False))
        sa0, pa0 = typeset.window_boundaries(res)
        if sa0 < sb0 or pa0 > pb0:
            f = f + [f"창 경계 퇴행 {it['id']}: 문장 끝 경계 {sb0}→{sa0} · 목적어/주어 뒤 경계 {pb0}→{pa0}"]
        if typeset.LINERULES and typeset.token_nl_lost(kr, res):
            f = f + [f"제어 조각 합침 {it['id']}"]
        if not typeset._same_text(typeset.wrap(kr, dm, ml, rules=False), res) and typeset.LINERULES:
            f = f + [f"글 보존 어긋남 {it['id']}"]
        for k, v in zip(KINDS, (a, b, c, d, e, f, g, h, h2), strict=True):
            cnt[k] += len(v)
            ex[k] += [f"{it['id']} {x}" for x in v]
    return cnt, ex


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--show", type=int, default=6)
    args = ap.parse_args()
    cnt, ex = measure(typeset.targets())
    print("줄·쪽 나눔 지표(씬) — a 쪽끝 고아 {a} · b 문장중간 한 낱말 쪽 {b} · c 손 개행 {c} · d 절째 내림 놓침 {d} · e 명사구 갈림 {e} · f 퇴행 {f} · g 나쁜 끊김 총 {g} · h 마지막 창 한 어절 {h} · h2 창 줄 수 불균형 {h2}".format(**cnt))
    if args.show:
        for k in KINDS:
            for x in ex[k][: args.show]:
                print(f"  [{k}] {x}")
    base = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else None
    if args.freeze:
        if base and any(cnt[k] > base[k] for k in KINDS):
            raise SystemExit(f"🔴 기준선보다 늘었다 {base} → {cnt} — 동결 안 함(래칫)")
        BASELINE.write_text(json.dumps(cnt, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"기준선 갱신 {cnt}")
        return
    if args.check:
        if base is None:
            raise SystemExit("🔴 기준선이 없다 — --freeze 로 만든다")
        up = {k: (base[k], cnt[k]) for k in KINDS if cnt[k] > base[k] and k != "h2"}  # h2(창 줄 수 불균형)는 재지 않는다 — 창 사이로 줄을 옮겨 고르지 않는다(규칙 2-17)
        if up:
            raise SystemExit(f"🔴 줄·쪽 나눔 지표가 기준선보다 늘었다 {up}")
        print(f"✅ 기준선 이내 {base}")


if __name__ == "__main__":
    main()
