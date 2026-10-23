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
    for w in (width, width - 0.5, width - 1):
        out = krwrap.wrap(s, w, cell_width=_cell)
        if all(_fits(x) for x in out):
            return out
    return None


def _join(lines):
    """줄을 공백으로 잇되, **문장 맨 앞 `…` 뒤는 붙인다**(번역 규칙 2-11 — `…그런 것처럼`)."""
    out = ""
    for x in (y.strip() for y in lines):
        out += (x if (not out or re.fullmatch(r"…+", out.split(" ")[-1]) and out.endswith("…")) else " " + x)
    return out


def ideal_lines(page, names, width=WIDTH):
    """제한(3 줄·줄 수 안 늚)을 걸지 않은 **이상적인** 재조판 줄 목록 — `None` 이면 못 나눈다(한 줄 쪽·나레이션 등)."""
    lines = [x for x in page.split("\n") if x.strip()]
    if len(lines) < 2 or any(x.startswith(T.NARR_INDENT) for x in lines):
        return None
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
            w = _wrap_sentence(s, width)
            if w is None:
                return None
            out += w[:-1]
            cur = w[-1]
    if cur:
        out.append(cur)
    return [x.replace(GLUE, " ") for x in out]


def reflow_page(page, names, width=WIDTH):
    """한 쪽(줄바꿈 `\\n` 으로 이은 문안) → 다시 나눈 쪽. 못 하면 원래 그대로."""
    out = ideal_lines(page, names, width)
    if out is None:
        return page
    lines = [x for x in page.split("\n") if x.strip()]
    if len(out) > T.WIN_ROWS or len(out) > len(lines):
        return page  # 줄이 늘거나 창을 넘으면 원문 구조 유지
    return "\n".join(out)


def feasible_for(data, blocks):
    """`열쇠 → (문안 → 칸 안에 들어가나)` — 재삽입(`reinsert.patch_blocks`)과 같은 길(① 폭 묶음 ② 종결 뒤 무동작 ③ 옛 길)을 그대로 물어본다.

    🔴 줄이 줄면 줄 끝 공백으로 남는 바이트를 흡수할 자리도 준다 — 번역이 원문보다 훨씬 짧은 블록은 **원문 줄 수가 곧 패딩 자리**였다.
    그런 블록은 종결 뒤 무동작(`FF FF`)을 못 쓰는 꼴(뒤에 화자 전환이 이어지는 자리)이면 다시 못 나눈다 — 그 쪽은 원문 구조를 둔다."""

    def make(key):
        blk = blocks[int(key)]
        budget = len(blk["body"])
        jp = M.text_of(blk["body"])
        jo = T.overflows(jp)

        def ok(kr):
            kr = R.IJ.resolve(kr)
            if R.fit(kr, budget, jo, jp, cap=True)[0] is not None:
                return True
            if R.slack_ok(data, blk["off"], budget) and R.fit_slack(kr, budget, jo) is not None:
                return True
            if R.fit_fill(kr, budget, jo) is not None:  # 무동작 `1A` 채움 — 종결이 뭐든 된다
                return True
            return R.fit(kr, budget, jo, jp)[0] is not None

        return ok

    return make


def reflow(text, names, ok=None):
    """`ok(문안)` 이 주어지면 그 문안이 칸에 들어갈 때만 쪽을 바꾼다 — 쪽마다 차례로 시험한다."""
    if T.is_narration(text):
        return text
    pages = text.split(T.PAGE)
    new = [reflow_page(pg, names) for pg in pages]
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
            if not isinstance(v, str) or "\n" not in v:
                continue
            n_blk += 1
            new = reflow(v, names, mk(k))
            if new != v:
                n_chg += 1
                n_pg += sum(1 for x, y in zip(v.split(T.PAGE), new.split(T.PAGE), strict=False) if x != y)
                doc[k] = new
                dirty = True
                if shown < a.show:
                    shown += 1
                    print(f"── {os.path.basename(f)} #{k}\n{v!r}\n{new!r}")
        if dirty and a.write:
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False, indent=1)
                fh.write("\n")
    print(f"여러 줄 블록 {n_blk} 중 {n_chg} 블록({n_pg} 쪽)이 바뀐다" + (" — 썼다" if a.write else " (미리보기 — --write)"))


if __name__ == "__main__":
    main()
