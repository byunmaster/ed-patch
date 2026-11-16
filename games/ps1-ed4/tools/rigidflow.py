"""끼움 토막(rigid) 안의 줄 끊는 자리 다시 고르기 — 규칙 2-16 (c). **조각 수·쪽 구조는 그대로, 줄 경계만** 옮긴다.

rigid 토막은 앞뒤에 이름·숫자를 끼우는 연산이 있어 **다른 토막과 합칠 수 없다.** 그러나 토막 **안**의 조각들(`01` 로만 이어진 줄들)은 끼움이 닿는 줄(첫 줄 앞 · 끝 줄 뒤)의
폭만 빼 두면 서로 다시 나눌 수 있다. 끼움 폭은 이름 최대 폭(`NAME_W`)·수 `NUM_W` 로 **보수적으로** 잡는다(넘치면 엔진이 낱말 한복판에서 접는다).
같은 조각이 여러 자리에서 쓰이면(`use > 1`) 모든 자리가 같은 꼬리를 공유할 때만 그 꼬리를 다시 나눈다(뒤 조각이 비면 앞 자리 줄이 안 맞는다).
"""

import collections
import re

import choice
import typeset

LOG = []  # (조각 첫 색인, 사유) — 못 고친 토막의 이유(지표 분류용)
NAME_W = 8
NUM_W = 6
INS_NAME = {5, 6, 8}
INS_NUM = {7}
FLOW = typeset.FLOW_OPS
_END_OR_COMMA = re.compile(r"([.?!…][\"'」』”’)]*|,)$")


def _ins_w(ops):
    return sum(NAME_W for o in ops if o in INS_NAME) + sum(NUM_W for o in ops if o in INS_NUM)


def _pre_suf_before(ops, prev_last_len):
    """첫 줄 앞 끼움 폭 — 연산에 줄 흐름이 있으면 그 뒤의 끼움만, 없으면 앞 조각 끝 줄 + 끼움."""
    f = max((i for i, o in enumerate(ops) if o in FLOW), default=None)
    if f is None:
        return prev_last_len + _ins_w(ops)
    return _ins_w(ops[f + 1 :])


def _suf_after(ops):
    """끝 줄 뒤 끼움 폭 — 줄 흐름 전의 끼움. 줄 흐름이 없으면 뒤 조각이 같은 줄에 이어 붙는다(알 수 없다 → None)."""
    f = next((i for i, o in enumerate(ops) if o in FLOW), None)
    if f is None:
        return None if ops else None
    return _ins_w(ops[:f])


def _mid(lines):
    return sum(1 for a in lines[:-1] if a and not _END_OR_COMMA.search(a))


def _wrap(words, caps_first, caps_last, k, cols):
    """정확히 `k` 줄 — 줄마다 폭 한도(첫 줄·끝 줄만 다르다), 끊는 값 최소. 못 하면 None."""
    m = len(words)
    glue = typeset._glued(words)
    best = {}

    def cap(line_i, total):
        c = cols
        if line_i == 0:
            c = caps_first
        if line_i == total - 1:
            c = min(c, caps_last) if line_i == 0 else caps_last
        return c

    def ok(line, c):
        return len(line) <= c and typeset.px_width(line) <= c * typeset.CELL_PX

    def solve(r, i):
        if (r, i) in best:
            return best[(r, i)]
        res = None
        li = k - r
        for j in range(i + 1, m + 1):
            line = " ".join(words[i:j])
            if not ok(line, cap(li, k)):
                break
            if r == 1:
                if j != m:
                    continue
                cand = (typeset.COST_SHORT if typeset._short(line) else 0, [line])
            else:
                if j == m:
                    break
                c = typeset._break_cost(words[j - 2] if j > 1 else "", words[j - 1], words[j])
                if c is None or j in glue:
                    continue
                sub = solve(r - 1, j)
                if sub is None:
                    continue
                cand = (c + (typeset.COST_SHORT if typeset._short(line) else 0) + sub[0], [line, *sub[1]])
            if res is None or cand[0] < res[0]:
                res = cand
        best[(r, i)] = res
        return res

    return solve(k, 0)


def reflow(mem, out, rows):
    """`out`({조각 색인: 문안}) 의 rigid 토막 안 줄 끊는 자리를 고친다(제자리). 바꾼 토막 수를 돌려준다."""
    streams = typeset.message_streams(mem)
    choices = {i for _p, _c, _r, idxs in choice.scan(mem, typeset.sm_text_base(mem), typeset.sm_table_len(mem)) for i in idxs}
    wins = typeset.windows(mem)
    runs = []  # (스트림, 토막, 토막 첫 출력 순번)
    for st, msg in zip(streams, wins, strict=True):
        n = 0
        for pg in msg:
            runs.append((st, pg, n))
            n += len(pg)
    occ = collections.defaultdict(list)
    for r, (_st, pg, _n) in enumerate(runs):
        for pos, i in enumerate(pg):
            occ[i].append((r, pos))
    changed = 0
    for r, (st, pg, n0) in enumerate(runs):
        if not pg.rigid or len(pg) < 2 or any(i in choices for i in pg):
            continue
        if any(i not in out or out[i] != out[i].strip() for i in pg):
            LOG.append((pg[0], "앞뒤 공백 조각"))
            continue
        txt = [out[i] for i in pg]
        if typeset.is_listish(txt):
            continue
        if _mid(txt) == 0 or not all(txt):
            continue
        # 꼬리 공유 — 가장 앞에서 시작하는 공유 꼬리
        start = None
        for j in range(len(pg)):
            tail = list(pg[j:])
            ok = all(
                runs[rr][1][pp:] == tail
                for rr, pp in occ[pg[j]]
            ) and all(len(occ[i]) == len(occ[pg[j]]) for i in tail)
            if ok:
                start = j
                break
        if start is None:
            LOG.append((pg[0], "꼬리 공유 안 됨(같은 조각이 다른 자리 다른 꼴)"))
            continue
        chain = list(pg[start:])
        if len(chain) < 2:
            LOG.append((pg[0], "공유 꼬리가 한 조각"))
            continue
        uses = occ[chain[0]]
        # 끼움 폭 — 모든 자리의 최댓값
        pre_w, suf_w, exact = 0, 0, False
        bad = False
        for rr, pp in uses:
            st2, pg2, nn0 = runs[rr]
            prints = st2["prints"]
            first = nn0 + pp
            last = nn0 + len(pg2) - 1
            if start == 0:
                if first == 0:
                    pre = 0
                else:
                    ops = typeset._gap_ops(mem, prints[first - 1][0], prints[first][0])
                    prev = out.get(prints[first - 1][1], "")
                    prev_last = len(prev[-typeset.COLS :].rstrip()) if prev else 0
                    pre = _pre_suf_before(list(ops), prev_last)
            else:
                pre = 0
            if last + 1 < len(prints):
                ops2 = typeset._gap_ops(mem, prints[last][0], prints[last + 1][0])
                sf = _suf_after(list(ops2))
                if sf is None:
                    bad = True
                    break
                suf = sf
            else:
                suf = 0
            pre_w, suf_w = max(pre_w, pre), max(suf_w, suf)
            exact = exact or suf > 0
        if bad or pre_w >= typeset.COLS - 4:
            LOG.append((pg[0], "끝 끼움이 뒤 조각과 같은 줄" if bad else "앞 끼움이 줄 대부분"))
            continue
        words = " ".join(out[i] for i in chain).split(" ")
        old = [out[i] for i in chain]
        best = None
        ks = [len(chain)] if exact else list(range(len(chain), 0, -1))
        for k in ks:
            got = _wrap(words, typeset.COLS - pre_w, typeset.COLS - suf_w, k, typeset.COLS)
            if got is None:
                continue
            cand = (_mid(got[1]), got[0], -k, got[1])
            if best is None or cand[:3] < best[:3]:
                best = cand
        if best is None or best[0] >= _mid(old):
            LOG.append((pg[0], "줄 폭 안에서 문장 끝에 못 맞춤" if best else "줄이 안 들어감"))
            continue
        new = best[3] + [""] * (len(chain) - len(best[3]))
        for i, t in zip(chain, new, strict=True):
            out[i] = t
        changed += 1
    return changed
