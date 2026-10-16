#!/usr/bin/env python3
"""음성 단어 시각(`voice_words.py`)을 대사 문안에 맞춰 **쪽 끝 시각 초안**을 만든다 — `script/voice_sched.json` 의 `msgs[].ends` 재료.

    python3 tools/voice_align.py <씬> <음성 rel> <메시지 열쇠>...     # 초안 JSON 을 stdout 에

방법: 인식된 글자열과 원문 글자열(가나로 접고 부호·공백 뺀)을 `difflib` 으로 맞춰 메시지마다 [첫 글자 시각, 마지막 글자 시각] 을 얻는다. 못 맞춘 메시지는
이웃 닻 사이를 글자 수 비례로 채운다. 쪽 끝 = 메시지 안에서 쪽 글자 수 비례(원문 쪽 수와 같으면 원문 쪽 끝), 마지막 쪽은 메시지 끝 + 0.4초.
초안일 뿐이다 — 편집기에서 사람이 듣고 다듬는다.
"""

import difflib
import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import font
import messages as M
import typeset

REVIEW = common.REVIEW_DIR / "voice"
HOLD = 0.4  # 마지막 쪽은 말이 끝난 뒤 이만큼 더 둔다(초)
MIN_PAGE = 0.8  # 쪽이 이보다 짧게 뜨지 않게


def fold(s: str) -> str:
    """가나로 접고(NFKC · 가타카나→히라가나) 글자·가나·한자만 남긴다."""
    out = []
    for ch in unicodedata.normalize("NFKC", s):
        o = ord(ch)
        if 0x30A1 <= o <= 0x30F6:
            ch = chr(o - 0x60)
        if ch.isalnum():
            out.append(ch)
    return "".join(out)


def rec_chars(words: list[dict]) -> list[tuple[str, float]]:
    """인식 결과 → (글자, 시각) — 단어 안은 시작~끝을 글자 수로 나눈다."""
    out = []
    for w in words:
        txt = fold(w["w"])
        if not txt:
            continue
        a, b = w["t"]
        a = a if a is not None else (out[-1][1] if out else 0.0)
        b = b if b is not None else a + 0.3 * len(txt)
        for i, ch in enumerate(txt):
            out.append((ch, a + (b - a) * (i + 0.5) / len(txt)))
    return out


def load_block(sid: int) -> bytes:
    import containers

    for c in containers.scan():
        for b in c["blocks"]:
            if b["id"] == sid:
                return b["data"]
    raise SystemExit(f"씬 {sid} 블록을 못 찾았다")


def main() -> int:
    import voice_sched as VS

    sid, rel = int(sys.argv[1]), int(sys.argv[2])
    keys = sys.argv[3:]
    msgs = {m.key: m for m in M.parse(load_block(sid))}
    words = json.loads((REVIEW / f"words_r{rel}.json").read_text("utf-8"))
    rc = rec_chars(words)
    rec_str = "".join(c for c, _ in rc)
    # 원문 글자열 — 메시지마다 · 쪽마다 구간
    jp_str = ""
    spans: list[list[tuple[int, int]]] = []  # 메시지 → [(쪽 시작, 쪽 끝)]
    for k in keys:
        pgs = [p for p in msgs[k].jp.split("\f") if p.strip()] or [msgs[k].jp]
        sp = []
        for p in pgs:
            f = fold(p)
            sp.append((len(jp_str), len(jp_str) + len(f)))
            jp_str += f
        spans.append(sp)
    sm = difflib.SequenceMatcher(None, rec_str, jp_str, autojunk=False)
    jp2rec: dict[int, int] = {}
    for a, b, n in sm.get_matching_blocks():
        for d in range(n):
            jp2rec[b + d] = a + d
    ratio = sum(1 for _ in jp2rec) / max(1, len(jp_str))

    def span_time(lo: int, hi: int) -> tuple[float, float] | None:
        idx = [jp2rec[i] for i in range(lo, hi) if i in jp2rec]
        return (rc[min(idx)][1], rc[max(idx)][1]) if idx else None

    # 메시지 시각(닻) — 못 맞춘 건 이웃 사이를 글자 수로 채운다
    msg_t: list[tuple[float, float] | None] = [span_time(sp[0][0], sp[-1][1]) for sp in spans]
    total = rc[-1][1] if rc else 0.0
    for i, t in enumerate(msg_t):
        if t is not None:
            continue
        j = i
        while j >= 0 and msg_t[j] is None:
            j -= 1
        k = i
        while k < len(msg_t) and msg_t[k] is None:
            k += 1
        t_lo = msg_t[j][1] if j >= 0 else 0.0
        t_hi = msg_t[k][0] if k < len(msg_t) else total
        grp = list(range(j + 1, k))
        w = [spans[g][-1][1] - spans[g][0][0] for g in grp]
        acc = sum(w[: grp.index(i)])
        a = t_lo + (t_hi - t_lo) * acc / max(1, sum(w))
        b = t_lo + (t_hi - t_lo) * (acc + w[grp.index(i)]) / max(1, sum(w))
        msg_t[i] = (a, b)
    out = []
    last_end = 0.0
    for k, sp, t in zip(keys, spans, msg_t, strict=True):
        n = VS.pages_of(sid, k, msgs)
        t0, t1 = t
        if n == len(sp):
            ends = []
            for pi, (lo, hi) in enumerate(sp):
                pt = span_time(lo, hi)
                ends.append(pt[1] if pt else None)
            # 못 맞춘 쪽은 메시지 안 비례
            ends = [e if e is not None else t0 + (t1 - t0) * (sp[i][1] - sp[0][0]) / max(1, sp[-1][1] - sp[0][0]) for i, e in enumerate(ends)]
        else:
            tr = M.load_translations(sid).get(k)
            wts = [len(x) for x in tr["t"].split("\f")] if tr else [hi - lo for lo, hi in sp]
            if len(wts) != n:
                wts = [1] * n
            cum, ends = 0, []
            for w_ in wts:
                cum += w_
                ends.append(t0 + (t1 - t0) * cum / sum(wts))
        ends[-1] = max(ends[-1], t1) + HOLD
        fixed = []
        for e in ends:
            e = max(e, last_end + MIN_PAGE)
            fixed.append(round(e, 2))
            last_end = e
        out.append({"key": k, "ends": fixed})
    json.dump({"match": round(ratio, 2), "msgs": out}, sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
