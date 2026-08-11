#!/usr/bin/env python3
"""**꼬리 잘림**을 센다 — 만들어는 냈는데 화면에 안 나오는 문안.

구조 계약의 반대쪽이다. 창 수가 **모자라면** 소프트락이라 게이트가 빌드에서 뺀다
(`window_deficit`). **넘치면** 엔진이 원본 `%c` 수만큼만 읽고 멈추므로 뒤가 조용히
사라진다 — 죽지 않으니 아무도 안 알려준다. 그래서 따로 센다.

두 갈래이고 원인이 다르다:

- **창 수 초과** — 정발 엔트리가 JP 보다 페이지가 많은데 슬라이스 없이 통째로 물었다.
  PS1 이 대사를 줄이면서 블록을 갈랐는데 정발은 한 엔트리에 다 갖고 있는 자리다.
- **창당 줄 수 초과** — 한 창이 하드 리밋(`LINES_PER_PAGE`, 이름창이 있으면 −1)을 넘었다.
  ⚠ 이 부류는 대개 **이웃 블록과 중복**이다 — 뒤 문장을 이웃이 이미 맡고 있는데 이쪽이
  엔트리 전문을 물어서 넘친다(jp716 실측 2026-08-11).
- **연쇄 줄 수 초과** — 블록 하나로는 리밋을 지키는데 **다음 블록과 합쳐서** 넘는다.
  엔진은 `%c` 를 만나야 창을 지우므로, `%c` 없이 끝난 블록은 다음 것과 **한 창에 이어
  붙는다**(무기점 jp702~703, 유저 QA 2026-08-11 — 이름 1 + 본문 6 = 7줄). JP 는 같은 자리가
  3줄이라 **원본에선 절대 안 드러난다**: 한국어가 길어져서만 생기는 결손이다.
  ⚠ 연쇄를 `%c` 로 자를 때 **이름 헤더**(개행 없는 짧은 조각 + 다음 조각이 개행으로 시작)를
  갈라야 한다 — 안 그러면 화자 분기(`%c세리오스%c…%c류난%c…`)가 통째로 한 창으로 잡혀
  오탐이 쏟아진다(실측 7건 중 3건이 그랬다).

⚠ **`build_candidate` 를 직접 부른다** — 재배치·제외(`size`)를 거치기 전 값이다. 제외된
블록은 애초에 안 쓰이니 여기 뜨는 건 "쓰이는데 잘리는" 것뿐이다.

  python3 tools/check_tail_cut.py          # 요약
  python3 tools/check_tail_cut.py -v       # 잘리는 문안까지
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R  # noqa: E402

NAME_MAX = 8  # 이름 헤더로 볼 최대 글자 수


def windows(text):
    """[(이름, 본문)] — `%c` 로 갈리는 창. 이름 헤더는 창을 지우지 않으니 다음 창에 붙인다."""
    segs = text.split("%c")
    out, name = [], None
    for k, s in enumerate(segs):
        nxt = segs[k + 1] if k + 1 < len(segs) else ""
        if s and "\n" not in s and len(s) <= NAME_MAX and nxt.startswith("\n"):
            name = s
            continue
        if s.strip():
            out.append((name, s))
            name = None
    return out


def chained(made):
    """{eid: 렌더} → [(연쇄 eid 목록, 이어 붙인 렌더)] — `%c` 없이 끝나면 다음 블록이 잇는다."""
    eids, i, out = sorted(made), 0, []
    while i < len(eids):
        chain, text = [eids[i]], made[eids[i]]
        while (
            not text.rstrip("\n").endswith("%c")
            and i + 1 < len(eids)
            and eids[i + 1] == eids[i] + 1
        ):
            i += 1
            chain.append(eids[i])
            text += made[eids[i]]
        if len(chain) > 1:
            out.append((chain, text))
        i += 1
    return out


def visible(b, n):
    """엔진이 실제로 읽는 부분 — 원본 `%c` 개수까지."""
    out, cnt = bytearray(), 0
    for i in range(len(b)):
        out += b[i : i + 1]
        if b[i : i + 1] == R.MC:
            cnt += 1
            if cnt >= n:
                break
    return bytes(out)


def _report(name, win, lines, runs, spare, verbose):
    bad = len(win) + len(lines) + len(runs)
    print(
        f"  {'✅' if not bad else '⚠'} {name}: 창 수 초과 {len(win)} · 줄 수 초과 {len(lines)}"
        f" · 연쇄 줄 수 초과 {len(runs)}"
    )
    for eid, a, b, cand in win:
        print(f"      jp{eid}  창 {a} → {b}")
        if verbose:
            cut = cand.rstrip(b"\x00")[len(visible(cand, a)) :]
            print(f"        잘림: {cut.decode('cp932', 'ignore')[:70]!r}")
    for eid, k, n in lines:
        print(f"      jp{eid}  창#{k} {n}줄 (리밋 {R.LINES_PER_PAGE})")
    for chain, n, nm, body in runs:
        print(f"      jp{chain[0]}~{chain[-1]}  이어 붙어 {n}줄" + (f" (이름 {nm})" if nm else ""))
        if verbose:
            for ln in body.strip("\n").split("\n"):
                print(f"        {ln}")
    for eid, a, b, _c in spare if verbose else ():
        print(f"      · jp{eid}  종단만 {a} → {b} (잃는 글자 없음)")
    return bad


def scan(verbose=False):
    tot = 0
    cur, win, lines, spare, made = None, [], [], [], {}

    def close():
        """씬 하나를 마무리 — 연쇄는 그 씬 전부가 모여야 셀 수 있다."""
        runs = []
        for chain, text in chained(made):
            for nm, body in windows(text):
                n = body.strip("\n").count("\n") + 1 + (1 if nm else 0)
                if n > R.LINES_PER_PAGE:
                    runs.append((chain, n, nm, body))
        return _report(cur, win, lines, runs, spare, verbose)

    for name, eid, jp, cand, _t in R.iter_candidates():
        if name != cur:
            if cur:
                tot += close()
            cur, win, lines, spare, made = name, [], [], [], {}
        made[eid] = R.render_bytes(cand)
        n = jp.count(R.MC)
        if cand.count(R.MC) > n:
            # ⚠ **잃는 문안이 있을 때만 꼬리 잘림이다.** 원본이 종단 없는 조각(`%c%s%c`
            # 아이템 감싸기 등)이면 우리가 종단을 하나 더 내도 잘리는 글자가 없다 —
            # 그건 흐름 표식 차이지 표시 손실이 아니다(jp786 실측 2026-08-11).
            cut = cand.rstrip(b"\x00")[len(visible(cand, n)) :].replace(R.MC, b"").strip()
            (win if cut else spare).append((eid, n, cand.count(R.MC), cand))
        for k, seg in enumerate(cand.rstrip(b"\x00").split(R.MC)[:n]):
            if seg and seg.count(b"\x0a") + 1 > R.LINES_PER_PAGE:
                lines.append((eid, k, seg.count(b"\x0a") + 1))
    if cur:
        tot += close()
    print(f"\n{'✅ 꼬리 잘림 없음' if not tot else f'⚠ 꼬리 잘림 {tot}건'}")
    return tot


if __name__ == "__main__":
    sys.exit(1 if scan("-v" in sys.argv) else 0)
