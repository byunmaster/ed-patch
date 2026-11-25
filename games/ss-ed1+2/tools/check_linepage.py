"""줄·쪽 나눔 전면 규칙 2-16 지표 — 대사 전량을 **조판한 결과**로 센다 (래칫: 기준선보다 늘면 실패).

    python3 tools/check_linepage.py              # 지표 표 + 기준선 대조 (늘면 종료코드 1)
    python3 tools/check_linepage.py --show 8     # 지표마다 표본
    python3 tools/check_linepage.py --list f.txt # 걸린 블록 목록(파일:오프셋) — 재촬영 단위 목록
    python3 tools/check_linepage.py --freeze     # 기준선을 지금 값으로 (줄었을 때만)

## 지표 (마스터 10-26 「qa, style을 돌렸는데도 이런게 나오면 … 의미가 없다」 — 눈이 아니라 기계 지표로 잡는다)

    a 쪽 끝 한 어절 고아     문장 중간에서 갈린 쪽의 다음 쪽이 **한 어절**뿐이다 (꼬리만 새 쪽에 떨어진다)
    b 한 낱말로 끝나는 쪽    문장 중간에서 끝나는 쪽의 마지막 줄이 **한 어절**이다 (앞 쪽 끝이 낱말 하나로 매달린다)
    c 문장 중간 손 개행      조판기에 들어가는 문안에 문장 중간 `\\n` 이 남았다 — 번역 원고의 줄 맞춤용 개행이 조판을 얽는다
    d 절째 내리면 들어가는데 쪼갠 줄   줄이 넘쳐 끊긴 자리에서, 그 줄에서 시작한 절이 다음 줄에 통째로 들어가는데 쪼갰다

쪽 = 창 끝(`\\x08`)으로 가른 한 장 · 글줄(`line_groups`) 하나. 화자 머리(`%c이름%c`)는 쪽 줄에 안 센다.
"""

import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import linerules as L
import patch_scn
import typeset_scn as T
from text.line_key import key as line_key

BASELINE = os.path.join(common.GAME_DIR, "linepage_baseline.json")
_SPACE_PUNCT = re.compile(r"[^\s%] +[!?.,！？](?![0-9])")
KEPT = [0]  # 보고 전용 — 절째 내리고 싶었으나 꼬리 줄·금칙 때문에 못 한 자리
METRICS = (
    "g 부호 앞 공백(2-2)",
    "h 마지막 창이 한 어절",
    "h2 창 줄 수 차 2 이상(고르게 나눌 수 있음)",
    "f 퇴행(새로 생긴 나쁜 끊김)",
    "e 굳은 명사구가 줄 끝에서 갈린 곳",
    "a 쪽 끝 한 어절 고아",
    "b 한 낱말로 끝나는 쪽",
    "c 문장 중간 손 개행",
    "d 절째 내리면 들어가는데 쪼갠 줄",
)


def _words(ln):
    return [w for w in ln.replace(T._NB, " ").split(" ") if w]


def scan_block(built):
    """조판된 블록 하나 → `{지표: [표본]}`.

    쪽 = 창 끝(`\\x08`)으로 가른 한 장, 그리고 창 전환(`%c`)으로 갈린 글줄. 같은 화자가 이어 말하는 동안(이름판이 끼지 않는 동안)
    문장이 쪽을 건너 이어진다고 본다 — 이름판이 오면 새 문장이다. 런타임 인자는 가장 긴 값으로 편다(`T.measure`)."""
    out = collections.defaultdict(list)
    segs, groups = T.line_groups(built)
    pages = []  # (줄 목록, 이름판 뒤 첫 쪽인가)
    fresh = True
    for gi, g in enumerate(groups):
        text = "%c".join(segs[i] for i in g)
        nxt = "%c".join(segs[i] for i in groups[gi + 1]) if gi + 1 < len(groups) else ""
        if "\n" not in text and nxt.startswith("\n"):
            fresh = True  # 화자 이름판 — 쪽이 아니다
            continue
        chain = []
        for pg in text.split("\x08"):
            ls = [ln for ln in T.measure(pg).split("\n") if ln.strip()]
            if ls:
                pages.append((ls, fresh))
                chain.append(ls)
                fresh = False
        # h2 — 쪽 둘이 줄 수 차 2 이상이고, 경계가 문장 끝이 아니며(문장 끝 경계는 옮기지 않는다), 고르게 나눈 자리가 절 경계일 때만 「고르게 나눌 수 있다」
        if len(chain) == 2 and abs(len(chain[0]) - len(chain[1])) >= 2:
            allv = chain[0] + chain[1]
            alt = len(allv) // 2
            w_b, w_a = _words(allv[len(chain[0]) - 1]), _words(allv[alt - 1])
            if w_b and w_a and L.bkind(w_b[-1]) != 3 and alt != len(chain[0]) and L.bkind(w_a[-1]):
                out["h2 창 줄 수 차 2 이상(고르게 나눌 수 있음)"].append(
                    str([len(c) for c in chain])
                )
    # h — 창이 둘 이상인 단위(같은 화자가 이어 말하는 동안)의 마지막 창이 한 어절
    unit = []
    for ls, fresh in pages + [([], True)]:
        if fresh and unit:
            if len(unit) >= 2 and len(unit[-1]) == 1 and len(_words(unit[-1][0])) == 1:
                out["h 마지막 창이 한 어절"].append(unit[-1][0])
            unit = []
        if ls:
            unit.append(ls)
    prev_open = False
    for k, (ls, fresh) in enumerate(pages):
        if fresh:
            prev_open = False
        last = _words(ls[-1])
        open_end = L.bkind(last[-1]) != 3
        nxt_cont = k + 1 < len(pages) and not pages[k + 1][1]  # 같은 화자로 이어지는 다음 쪽이 있다
        if prev_open and len(ls) == 1 and len(last) == 1:
            out["a 쪽 끝 한 어절 고아"].append(ls[0])
        if open_end and nxt_cont and len(last) == 1:
            out["b 한 낱말로 끝나는 쪽"].append(" / ".join(ls[-2:]))
        prev_open = open_end
    # d — 줄 사이 (쪽 안, 문단 안). 조판기의 절째 내리기(`clause_down`)가 **지금 내릴 자리**를 센다 — 내려 봐야 꼬리 줄·금칙이 생기는 자리(`kept`)는 위반이 아니다
    for ls, _fresh in pages:
        st = {}
        gl = [T.glue_line(ln) for ln in ls]
        T.clause_down(gl, T.COLS, st)
        for _ in range(st.get("noun", 0)):
            out["e 굳은 명사구가 줄 끝에서 갈린 곳"].append(" / ".join(ls[:3]))
        for _ in range(st.get("moved", 0)):
            out["d 절째 내리면 들어가는데 쪼갠 줄"].append(" / ".join(ls[:3]))
        KEPT[0] += st.get("kept", 0)
    return out


_ON = (T.SOFTNL, T.LINE_CLAUSE)


def scan():
    """`(블록 수, {지표: [(파일#오프셋, 표본)]})`."""
    canon = patch_scn.load_canon(quiet=True)
    _f, mm = common.open_image()
    canon = patch_scn.augment_names(canon, mm)
    hits = collections.defaultdict(list)
    n = 0
    for path in (p for p, _l, _s in common.iso_files(mm) if patch_scn.SCN_RE.match(p)):
        got = patch_scn.load(path)
        if not got:
            continue
        if not patch_scn.DIALOG_RE.match(path):
            continue  # 이야기 씬 대사 창만 — 메시지·표는 줄 넘김이 다르다
        _base, entries = got
        sites = patch_scn.sites_for(path)
        fn = path.split("/")[-1]
        for e in entries:
            jp = e.get("text", "")
            off = int(e["file_offset"], 16)
            built = patch_scn.canon_of(canon, jp, sites.get(off), path=path, off=off)
            tag = f"{fn}#{off:#x}"
            if not built:
                # 번역 경로를 안 타는 일본어 없는 원문(ASCII 뿐)도 부호 앞 공백을 본다 — 「90000000 Gold !!」 가 이쪽으로 새었다
                m = _SPACE_PUNCT.search(jp.replace("\n", "")) if jp and jp.isascii() else None
                if m:
                    hits["g 부호 앞 공백(2-2)"].append(
                        (tag, jp[max(0, m.start() - 10) : m.end() + 4].replace("\n", "⏎"))
                    )
                continue
            n += 1
            raw = patch_scn._scn_at(path, off)
            if raw is None:
                raw = canon.get(line_key(jp))
            if raw:
                fed = T.layout_input(jp, raw) if hasattr(T, "layout_input") else raw
                if L.mid_sentence_nl(fed):
                    hits["c 문장 중간 손 개행"].append((tag, fed.replace("\n", "⏎")[:40]))
            # g — 번역 규칙 2-2 부호 앞 공백 (일본어 없는 ASCII 원문 블록은 번역 경로를 안 타서 「90000000 Gold !!」 가 그대로 남았다, 10-26)
            m = _SPACE_PUNCT.search(built.replace("\n", "").replace("\x08", ""))
            if m:
                hits["g 부호 앞 공백(2-2)"].append(
                    (tag, built[max(0, m.start() - 10) : m.end() + 4].replace("\n", "⏎"))
                )
            for k, v in scan_block(built).items():
                hits[k] += [(tag, x) for x in v]
            # f — 규칙을 끈 조판과 견줘 나빠진 곳 (조판기는 걸리면 끈 쪽을 쓰므로 0 이어야 한다)
            T.SOFTNL = T.LINE_CLAUSE = False
            try:
                base = patch_scn.canon_of(canon, jp, sites.get(off), path=path, off=off)
            finally:
                T.SOFTNL, T.LINE_CLAUSE = _ON
            if base and base != built:
                for x in T.regress(base, built):
                    hits["f 퇴행(새로 생긴 나쁜 끊김)"].append((tag, x))
    mm.close()
    _f.close()
    return n, hits


def main():
    argv = sys.argv[1:]
    show = int(argv[argv.index("--show") + 1]) if "--show" in argv else 0
    n, hits = scan()
    cur = {m: len(hits.get(m, ())) for m in METRICS}
    print(
        f"  줄·쪽 나눔 2-16 [블록 {n:,}] — "
        + " · ".join(f"{m.split()[0]} {v}" for m, v in cur.items())
        + f"  (보고: 못 내린 자리 {KEPT[0]})"
    )
    for m in METRICS:
        for tag, x in hits.get(m, ())[:show]:
            print(f"      [{m}] {tag}: {x!r}")
    if "--list" in argv:
        tags = sorted({t for m in METRICS for t, _x in hits.get(m, ())})
        with open(argv[argv.index("--list") + 1], "w", encoding="utf-8") as f:
            f.write("\n".join(tags) + "\n")
    if "--freeze" in argv:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"  ✍ 기준선 갱신 {cur}")
        return 0
    try:
        with open(BASELINE, encoding="utf-8") as f:
            base = json.load(f)
    except OSError:
        print("  ⚠ 기준선 없음 — `--freeze` 로 만든다 (안 쟀다는 통과가 아니다)")
        return 1
    worse = {m: (base.get(m, 0), v) for m, v in cur.items() if v > base.get(m, 0)}
    better = {m: (base.get(m, 0), v) for m, v in cur.items() if v < base.get(m, 0)}
    if worse:
        print(
            "  🔴 기준선보다 늘었다 — "
            + " · ".join(f"{m.split()[0]} {a}→{b}" for m, (a, b) in worse.items())
        )
        return 1
    if better:
        print(
            "  ✅ 기준선 이하 (줄었다: "
            + " · ".join(f"{m.split()[0]} {a}→{b}" for m, (a, b) in better.items())
            + ") — `--freeze` 로 내린다"
        )
    else:
        print("  ✅ 줄·쪽 나눔 지표 — 기준선과 같다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
