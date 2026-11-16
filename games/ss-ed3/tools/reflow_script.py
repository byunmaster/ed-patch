"""씬 대사를 **창 폭을 채워 어절 단위로 다시 나눈다** — 번역 규칙 2-6·2-10 (마스터 10-20 「ed3 도 어절단위 개행」).

    python3 games/ss-ed3/tools/reflow_script.py            # 무엇이 바뀌나만 본다
    python3 games/ss-ed3/tools/reflow_script.py --write    # script/MAP*.json 에 쓴다
    python3 games/ss-ed3/tools/reflow_script.py --show N   # 바뀌는 예 N 개

종전엔 대사가 **원문 줄 구조를 그대로** 따랐다(여러 줄 블록 9,856 중 9,160 이 앞 줄에 다음 줄 첫 어절이 들어갈 자리가 있는데도 끊겨 있었다).
쪽 넘김(`\\f`)은 원문 자리를 그대로 둔다. 한 쪽 안에서만 줄을 다시 짠다:
  · 문장(종결부호) 단위로 — 앞 줄 남은 칸에 문장이 통째로 들어가면 거기 잇고, 아니면 새 줄에서 시작한다(2-10). 한 줄보다 긴 문장만 어절 단위로 나눈다(`krwrap.wrap`).
  · **띄어 쓴 고유명사는 한 줄에** — 정본 `nouns` 의 공백 든 이름은 나눌 때 한 어절로 묶는다(줄바꿈 금지).
  · 한 쪽이 3 줄을 넘게 되면 그 쪽은 건드리지 않는다(원문 구조 유지). 나레이션(전각 공백 들여쓰기)·한 줄뿐인 쪽은 건드리지 않는다.
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import mapfile as M
import reinsert as R
import typeset as T

sys.path.insert(0, os.path.join(C.GAME_DIR, "..", ".."))
sys.path.insert(0, os.path.join(C.GAME_DIR, "..", "..", "shared"))
import canon  # noqa: E402
from shared.text import krwrap  # noqa: E402

GLUE = ""  # 이름 속 공백을 잠시 이 글자로 묶어 나누지 못하게 한다(폭은 공백과 같게 센다)
WIDTH = T.WIN_COLS
SCRIPT = os.path.join(C.GAME_DIR, "script")


def _cell(ch):
    return 0.5 if ch == GLUE else T.char_cols(ch)


def _names():
    """공백 든 정본 이름 — 긴 것 먼저."""
    return sorted({kr for _, _, kr in canon.all_names("ed3") if " " in kr}, key=len, reverse=True)


def protect(s, names):
    for n in names:
        if n in s:
            s = s.replace(n, n.replace(" ", GLUE))
    return s


def _fits(line):
    """엔진이 이 줄을 **접지 않나** — 줄 끝 글자가 시작하는 자리가 16.0 칸 이하여야 한다(`typeset.fold` — 반각 부호로 끝나면 16.5 칸까지)."""
    return len(T.fold(line.replace(GLUE, " "))) == 1


def _wrap_sentence(s, width):
    """한 줄보다 긴 문장을 어절 단위로 — `krwrap.wrap` 은 끝 글자 폭을 몰라, 접히는 줄이 나오면 한 칸 줄여 다시 나눈다."""
    for w in (width, width - 0.5, width - 1, width - 1.5, width - 2, width - 2.5, width - 3):
        out = krwrap.wrap(s, w, cell_width=_cell)
        # 줄 끝 쉼표는 `fix_line_commas` 가 지운다(규칙 2-13) — 쉼표 바로 뒤에서 나누면 글자가 사라지니 그런 나눔은 안 쓴다
        if all(_fits(x) for x in out) and not any(x.endswith(",") for x in out[:-1]):
            return out
    return None


def wrap_clause(sentence, width=WIDTH):
    """한 문장을 줄 폭 안에서 **절째 내려** 나눈다 — 번역 규칙 2-16 ②·③. 못 하면 None(낱말 하나가 한 줄보다 길다 등).

    · 줄이 넘치는 자리에서, 이 줄 안의 마지막 절 경계(문장 끝 > 쉼표 > 연결어미) 뒤부터 그 절 끝까지가 다음 줄에 통째로 들어가고
      앞 줄에 10칸 이상 남으면 거기서 끊는다(`check_linebreak.clause_tail` 과 같은 판정).
    · 본용언+보조용언 같은 한 덩어리 사이(`krwrap.split_reason`)는 끊지 않는다 — 앞 낱말을 다음 줄로 내린다.
    · 줄 끝에는 쉼표를 두지 않는다 — 글을 바꾸지 않으려고 쉼표를 빼는 대신 그 앞에서 끊는다(규칙 2-13)."""
    import check_linebreak as L

    words = [w for w in sentence.split(" ") if w]
    if not words or any(not _fits(w) for w in words):
        return None
    rows, i, n = [], 0, len(words)
    while i < n:
        j = i
        while j < n and _fits(" ".join(words[i : j + 1])):
            j += 1
        if j >= n:
            rows.append(" ".join(words[i:]))
            break
        k = j  # words[i:k] 가 이 줄
        for _ in range(
            2
        ):  # 덩어리를 가르거나 주어·목적어만 줄 끝에 남기면 앞 낱말을 내린다 — 두 번까지, 앞 줄이 6.5칸 밑으로 줄지 않을 때만
            if k > i + 1 and (
                L.bonded(words[k - 1], words[k])
                or L.split_phrase(words[k - 1], words[k])
                or L.josa_end(words[k - 1])
            ):
                if L.wcols(" ".join(words[i : k - 1])) < L.MIN_LEFT:
                    break
                k -= 1
        while k > i + 1 and words[k - 1].endswith(
            ","
        ):  # 줄 끝에 쉼표를 두지 않는다 — 글을 안 바꾸려고 빼지 않고 피한다
            k -= 1
        best = None
        for b in range(i, k - 1):  # 경계 어절 = words[b], 줄 끝 어절(k-1)은 뺀다
            kind = L.bkind(words[b])
            if (
                kind == 0
                or words[b].endswith(",")
                or L.bonded(words[b], words[b + 1])
                or L.split_phrase(words[b], words[b + 1])
            ):
                continue
            if L.wcols(" ".join(words[i : b + 1])) < L.MIN_LEFT:
                continue
            e = b + 1
            while e < n - 1 and L.bkind(words[e]) == 0:
                e += 1
            if not _fits(" ".join(words[b + 1 : e + 1])):
                continue
            if best is None or kind >= best[0]:
                best = (kind, b)
        if best:
            k = best[1] + 1
        rows.append(" ".join(words[i:k]))
        i = k
    return rows


def _join(lines):
    """줄을 공백으로 잇되, **문장 맨 앞 `…` 뒤는 붙인다**(번역 규칙 2-11 — `…그런 것처럼`)."""
    out = ""
    for x in (y.strip() for y in lines):
        out += (
            x
            if (not out or re.fullmatch(r"…+", out.split(" ")[-1]) and out.endswith("…"))
            else " " + x
        )
    return out


def ideal_lines(page, names, width=WIDTH):
    """제한(3 줄·줄 수 안 늚)을 걸지 않은 **이상적인** 재조판 줄 목록 — `None` 이면 못 나눈다(한 줄 쪽·나레이션 등)."""
    lines = [x for x in page.split("\n") if x.strip()]
    if not lines or any(x.startswith(T.NARR_INDENT) for x in lines):
        return None
    if len(lines) < 2 and _fits(lines[0]):
        return None  # 한 줄에 드는 한 줄 쪽
    joined = protect(_join(lines), names)
    out, cur = [], ""
    for s in krwrap.split_sentences(joined):
        if cur and _fits(cur + " " + s):
            cur += " " + s
            continue
        if cur:
            out.append(cur)
            cur = ""
        if _fits(s):
            cur = s
        else:
            w = wrap_clause(s, width) or _wrap_sentence(s, width)
            if w is None:
                return None
            out += w[:-1]
            cur = w[-1]
    if cur:
        out.append(cur)
    return [x.replace(GLUE, " ") for x in out]


def reflow_page(page, names, width=WIDTH, followed=False):
    """한 쪽(줄바꿈 `\\n` 으로 이은 문안) → 다시 나눈 쪽. 못 하면 원래 그대로."""
    import check_linebreak as L

    #   🔴 이미 규칙(2-16 ①②)에 걸리는 곳이 없으면 그대로 둔다 — 줄 맞춤 취향으로 4천 블록을 흔들지 않는다
    def issues(t):
        r = L.scan(t, names)
        bonded_cuts = sum(
            1 for pr in L._breaks(t) if L.bonded(*pr)
        )  # 「하면/되나요」 꼴 — 덩어리를 가른 줄 끝
        return len(r["c"]) + len(r["d"]) + len(r["e"]) + bonded_cuts

    #   🔴 표지판·지도·목록 꼴(전각 공백 정렬 · 전각 숫자 열)은 손 배치라 건드리지 않는다
    if "\u3000" in page or re.search(r"[０-９]", page):
        return page
    before = issues(page)
    if before == 0:
        return page
    out = ideal_lines(page, names, width)
    if out is None or len(out) > T.WIN_ROWS:
        return page  # 못 나누거나 창(3 줄)을 넘으면 건드리지 않는다
    new = "\n".join(out)
    if followed and len(out[-1].split(" ")) == 1 and not L.END_RE.search(out[-1]):
        return page  # 쪽 끝에 한 어절만 남기는 이동은 안 한다(a)
    return (
        new if issues(new) < before and not L.regress(page, new) else page
    )  # f — 나빠지는 이동은 거부


def feasible_for(data, blocks):
    """`열쇠 → (문안 → 칸 안에 들어가나)` — 재삽입(`reinsert.patch_blocks`)과 같은 길(① 폭 묶음 ② `1A` 채움 ③ 옛 길)을 그대로 물어본다.

    🔴 줄이 줄면 남는 바이트를 `1A` 채움이 흡수한다(종결 뒤 `FF FF` 패딩은 다음 대사가 안 불려 10-22 에 걷었다 — `reinsert.py` 머리 주석)."""

    def make(key):
        blk = blocks[int(key)]
        budget = len(blk["body"])
        jp = M.text_of(blk["body"])
        jo = T.overflows(jp)

        def ok(kr):
            kr = R.IJ.resolve(kr)
            if R.fit(kr, budget, jo, jp, cap=True)[0] is not None:
                return True
            if R.fit_fill(kr, budget, jo) is not None:  # 무동작 `1A` 채움 — 종결이 뭐든 된다
                return True
            return R.fit(kr, budget, jo, jp)[0] is not None

        return ok

    return make


def _letters(s):
    return re.sub(r"[\s,]", "", s.replace(GLUE, ""))  # 줄 끝 쉼표는 뺀다(규칙 2-13)


def reflow(text, names, ok=None):
    """`ok(문안)` 이 주어지면 그 문안이 칸에 들어갈 때만 쪽을 바꾼다 — 쪽마다 차례로 시험한다.

    🔴 줄 위치와 공백만 바뀌어야 한다 — 글자(공백·개행 빼고)가 달라지면 멈춘다(10-22: 줄 끝 쉼표가 지워져 나간 4건)."""
    out = _reflow(text, names, ok)
    assert _letters(out) == _letters(text), f"재조판이 글자를 바꿨다: {text!r} → {out!r}"
    return out


def _bad_end(rows, nxt_rows):
    """쪽 끝이 문장 도중에서 한 어절 줄이거나 다음 쪽 첫 어절과 한 덩어리를 가르나(`check_linebreak` a·b)."""
    import check_linebreak as L

    last = rows[-1].strip()
    if L.END_RE.search(last):
        return False
    wl = last.split(" ")
    return len(wl) == 1 or L.bonded(wl[-1], nxt_rows[0].strip().split(" ")[0])


def fix_pages(pages):
    """쪽 끝 고아(번역 규칙 2-16 ③) — 쪽 경계(`\\f`)를 한 줄 옮겨 푼다. 줄 내용은 안 바뀌고 `\\n` ↔ `\\f` 맞바꿈이라 길이가 그대로다.

    ① 쪽 끝 줄을 다음 쪽 머리로 내리거나 ② 다음 쪽 첫 줄을 이 쪽 끝으로 올린다 — 3 줄 안에서 새 고아를 안 만들 때만."""
    rows = [[r for r in pg.split("\n") if r.strip()] for pg in pages]
    for j in range(len(rows) - 1):
        a, b = rows[j], rows[j + 1]
        if not a or not b or not _bad_end(a, b):
            continue
        import check_linebreak as L

        if (
            len(a) >= 2
            and len(b) < T.WIN_ROWS
            and not _bad_end(a[:-1], [a[-1]])
            and L.page_cut_ok(a[-2])
        ):
            rows[j], rows[j + 1] = a[:-1], [a[-1]] + b
        elif (
            len(a) < T.WIN_ROWS
            and len(b) >= 2
            and not _bad_end([b[0]], b[1:])
            and L.page_cut_ok(b[0])
        ):
            rows[j], rows[j + 1] = a + [b[0]], b[1:]
    return ["\n".join(r) if r else pages[k] for k, r in enumerate(rows)]


WEIGHT = {
    "a": 10,
    "b": 10,
    "h": 10,
}  # 쪽 끝 고아·덩어리 가르는 쪽 끝·마지막 창 한 어절은 줄 맞춤 취향보다 무겁다


def _total_issues(text, names):
    import check_linebreak as L

    r = L.scan(text, names)
    return sum(len(r[k]) * WEIGHT.get(k, 1) for k in L.KINDS)


def repaginate(text, names):
    """문장이 `\\f` 를 가로지르는 블록을 **쪽 경계까지 새로** 짠다 — 번역 규칙 2-16 ①②③.

    블록 전체를 문장으로 모아 절째 줄을 나누고(`wrap_clause`), 같은 쪽 수 안에서 쪽 경계를 **문장 끝**에 두도록 DP 로 고른다
    (문장 도중 쪽 끝은 벌점, 한 어절 줄·덩어리를 가르는 쪽 끝은 큰 벌점). 한 쪽은 3 줄 이하. 못 짜면 None."""
    import check_linebreak as L

    pages = text.split(T.PAGE)
    P = len(pages)
    flat = _join([ln for pg in pages for ln in pg.split("\n") if ln.strip()])
    joined = protect(flat, names)
    rows, ends = [], []
    cur = ""
    for sent in krwrap.split_sentences(joined):
        if cur and _fits(cur + " " + sent):
            cur += " " + sent
            continue
        if cur:
            rows.append(cur)
            cur = ""
        if _fits(sent):
            cur = sent
        else:
            w = wrap_clause(sent)
            if w is None:
                return None
            rows += w[:-1]
            cur = w[-1]
    if cur:
        rows.append(cur)
    rows = [r.replace(GLUE, " ") for r in rows]
    n = len(rows)
    K = min(P, n)
    if n > 3 * K:
        return None
    INF = 10**9

    def brk(i):  # rows[i] 뒤에서 쪽을 끊는 값 — 문장 끝 0 · 절 경계 10 · 그 밖은 금지
        last = rows[i].strip()
        if L.END_RE.search(last):
            return 0
        wl = last.split(" ")
        if (
            len(wl) == 1
            or not L.page_cut_ok(last)
            or L.bonded(wl[-1], rows[i + 1].strip().split(" ")[0])
        ):
            return INF
        return 10

    def solve(K):
        mean = n / K
        best = [[INF] * (n + 1) for _ in range(K + 1)]
        back = [[0] * (n + 1) for _ in range(K + 1)]
        best[0][0] = 0
        for k in range(1, K + 1):
            for i in range(1, n + 1):
                for sz in (1, 2, 3):
                    j = i - sz
                    if j < 0 or best[k - 1][j] >= INF:
                        continue
                    b_ = brk(i - 1) if i < n else 0
                    if b_ >= INF:
                        continue
                    c = best[k - 1][j] + b_ + int(4 * (sz - mean) ** 2)
                    if c < best[k][i]:
                        best[k][i], back[k][i] = c, j
        if best[K][n] >= INF:
            return None
        cuts, i = [], n
        for k in range(K, 0, -1):
            j = back[k][i]
            cuts.append((j, i))
            i = j
        cuts.reverse()
        return best[K][n], cuts

    #   쪽 수는 원래 수(P)까지, 안 되면 한두 쪽 줄여서라도(쪽 끝을 문장 끝·절 경계에 두려고) — 줄인 쪽마다 벌점 3
    cand = []
    for k in range(K, max(0, -(-n // 3) - 1), -1):
        r = solve(k)
        if r:
            cand.append((r[0] + 3 * (K - k), k, r[1]))
    if not cand:
        return None
    _, _, cuts = min(cand)
    return T.PAGE.join("\n".join(rows[a:b]) for a, b in cuts)


def _reflow(text, names, ok=None):
    """인라인 이름 변수는 실제 이름 폭으로 바꿔 짜고 되돌린다(번역 규칙 2-16 ⑤)."""
    import check_linebreak as L

    #   🔴 끝의 개행(`…자를\n` — 뒤 블록으로 이어지는 0E 연결·빈 줄로 끝나는 구간)은 의미가 있다 — 떼어 두고 본문만 짜서 도로 붙인다
    tail = text[len(text.rstrip("\n")) :]
    if tail:
        body = text[: len(text) - len(tail)]
        return _reflow(body, names, (lambda t: ok(t + tail)) if ok else None) + tail
    ex, restore = L.expand_names(text)
    if ex is text or ex == text:
        return _reflow_guard(text, names, ok)
    out = _reflow_guard(ex, names, (lambda t: ok(restore(t))) if ok else None)
    return restore(out)


def _reflow_guard(text, names, ok=None):
    """블록 단위 안전판 — 고친 결과의 지표 합이 원래보다 늘면 원래대로 둔다(쪽 끝 고아가 새로 생기는 꼴을 막는다)."""
    out = _reflow_raw(text, names, ok)
    return text if out != text and _total_issues(out, names) > _total_issues(text, names) else out


def _reflow_raw(text, names, ok=None):
    if T.is_narration(text):
        return text
    if re.search(
        r"<[0-9A-F]{2}>", text
    ):  # 이름 폭을 못 넣은 그 밖의 제어 코드가 든 블록은 손 배치로 둔다
        return text
    if re.search(
        r"(^|[\s\f])…", text
    ):  # 「…」로 시작하는 낱말(말줄임 연출)은 붙임 규칙(2-11)과 얽혀 손 배치로 둔다
        return text
    pages = text.split(T.PAGE)
    new = [reflow_page(pg, names, followed=j < len(pages) - 1) for j, pg in enumerate(pages)]
    #   🔴 「앗」「엇?」「9」 같은 아주 짧은 쪽은 **한 박자**(감탄 · 값 앞의 멈춤)다 — 이웃 쪽과 합치거나 쪽 경계를 옮기지 않는다
    #   (MAP013#101 「합계가⏎9」 가 합쳐지자 창이 비어 뜨는 걸 재촬영이 잡았다 — 10-26)
    tiny = any(0 < len(re.sub(r"<[0-9A-F]{2}>|\s", "", pg)) <= 3 for pg in pages)
    if len(new) > 1 and not tiny:
        new = fix_pages(new)
    cand = T.PAGE.join(new)
    import check_linebreak as L

    if L.regress(text, cand):  # f — 쪽 경계 이동이 나쁘게 만들면 이 블록은 원래대로 둔다
        new, cand = list(pages), text
    if (
        not tiny and _total_issues(cand, names) > 0 and (re_ := repaginate(cand, names)) is not None
    ):  # c·d·e·h·h2 중 하나라도 있으면
        if (
            _total_issues(re_, names) < _total_issues(cand, names)
            and not L.regress(text, re_)
            and (ok is None or ok(re_))
        ):
            return re_
    if ok is None or ok(T.PAGE.join(new)):
        return T.PAGE.join(new)
    cur = list(pages)
    for j, pg in enumerate(new):
        if pg != pages[j]:
            trial = cur[:j] + [pg] + cur[j + 1 :]
            if ok(T.PAGE.join(trial)):
                cur = trial
    return T.PAGE.join(cur)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--show", type=int, default=0)
    a = ap.parse_args()
    names = _names()
    n_blk = n_chg = n_pg = 0
    shown = 0
    for f in sorted(glob.glob(os.path.join(SCRIPT, "MAP*.json"))):
        doc = json.load(open(f, encoding="utf-8"))
        dirty = False
        stem = os.path.basename(f)[:-5]
        with C.open_disc(1) as d:
            data = d.read(f"/MAP/{stem}.BIN")
        blocks = M.blocks(data)
        mk = feasible_for(data, blocks)
        for k, v in doc.items():
            if not isinstance(v, str) or ("\n" not in v and T.PAGE not in v):
                continue
            n_blk += 1
            new = reflow(v, names, mk(k))
            if new != v:
                n_chg += 1
                n_pg += sum(
                    1 for x, y in zip(v.split(T.PAGE), new.split(T.PAGE), strict=False) if x != y
                )
                doc[k] = new
                dirty = True
                if shown < a.show:
                    shown += 1
                    print(f"── {os.path.basename(f)} #{k}\n{v!r}\n{new!r}")
        if dirty and a.write:
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False, indent=1)
                fh.write("\n")
    print(
        f"여러 줄 블록 {n_blk} 중 {n_chg} 블록({n_pg} 쪽)이 바뀐다"
        + (" — 썼다" if a.write else " (미리보기 — --write)")
    )


if __name__ == "__main__":
    main()
