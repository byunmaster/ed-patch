"""음성 감사(마스터 11-03 「음성이 없으면 당연히 자막도 빼야지」) — 토막 wav 의 받아쓰기(Whisper)와 원문(JP) 줄을 가나 읽기로 대조해 줄마다
**있음 / 일부 / 없음 / 불가** 를 가른다. 결과는 `script/voice_audit.json`(원문 글자 없이 판정·근거·후보 시각만), 편집기 자료에는 `voice_editor_data.annotate_audit` 가 붙인다.

    받아쓰기 입력(커밋 안 함, 메인 트리 `.local/work/inbox/pce-ed1/voice-audit/`):
      wds/<토막>.json    소형(whisper-small) word 시각 20초 창 — 구절 시각 · 싱크 닻  (프로세스 RSS ≈ 4GB)
      chunks20/<토막>.json 대형(turbo) 텍스트 20초 창 — 교차 판정(둘 중 하나라도 「있음」이면 안 뺀다)
      🔴 large·30초 창 word 모드는 RSS 15GB 라 머신이 죽는다(11-03) — 소형 20초 창만.

    방법: 구절을 겹침 없이 모은 글자 흐름(읽기)과 원문 읽기를 difflib 으로 맞춰 조각별 일치율 → 있음 ≥60% · 일부 20~60% · 없음 <20%.
    불가 = 웃음·짧은 외침(읽기 12자 미만) · 원문 짝 없음 · 환각 청크 · 토막 전체가 안 맞음 · 쪽↔원문 대응 불확실. 음성 순서가 자막 순서와 다르면(`unordered`) 순서를 풀어 다시 맞춘다.
    싱크 후보는 `voice_envelope`(음량 포락선 발화 구간)에 줄을 DP 로 배정(닻 = 받아쓰기 첫 글자 시각).
"""
import difflib
import json
import math
import re
import sys
import unicodedata
import wave
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pykakasi

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import voice_editor_data

_MAIN = voice_editor_data.main_tree()
BASE = str(_MAIN / ".local" / "work" / "inbox" / "pce-ed1" / "voice-editor") + "/"
AUD = str(_MAIN / ".local" / "work" / "inbox" / "pce-ed1" / "voice-audit") + "/"
KKS = pykakasi.kakasi()
HALLU = ["ご視聴", "ご清聴", "チャンネル登録", "ありがとうございました", "字幕", "おやすみなさい", "Thank", "thank"]
CH_DIR = "wds"
SKIP = re.compile(r"[\s　「」『』（）()、。，．,.!！?？…・･\-ー〜～♪※]+")


def reading(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = SKIP.sub("", s)
    out = "".join(x["hira"] for x in KKS.convert(s))
    out = SKIP.sub("", out)
    return "".join(chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in out)  # 가타카나→히라가나


def robust_first(ts, k=3, span=2.0):
    """일치 글자 시각들 중 「span 초 안에 k 개 이상 모여 있는」 가장 이른 시각(우연히 맞은 낱글자를 거른다)."""
    ts = sorted(ts)
    for i, t in enumerate(ts):
        if sum(1 for u in ts[i:] if u <= t + span) >= min(k, len(ts)):
            return t
    return ts[0] if ts else None


def collapse_rep(t: str) -> str:
    """「ハッハッハ…」 환각 반복 접기: 같은 1~4자 조각이 4번 넘게 이어지면 4번까지만."""
    return re.sub(r"(.{1,4}?)\1{4,}", lambda m: m.group(1) * 3, t)


def is_hallu(t: str) -> bool:
    if any(h in t for h in HALLU):
        return True
    if len(t) > 30:
        u = len(set(t))
        if u / len(t) < 0.12:
            return True
    return False


def voiced_cdf(path, t0, t1):
    w = wave.open(path)
    sr = w.getframerate()
    w.setpos(int(t0 * sr))
    a = np.frombuffer(w.readframes(int((t1 - t0) * sr)), dtype=np.int16).astype(np.float32) / 32768
    if w.getnchannels() == 2:
        a = a.reshape(-1, 2).mean(1)
    hop = int(sr * 0.02)
    n = len(a) // hop
    e = np.sqrt((a[: n * hop].reshape(n, hop) ** 2).mean(1)) if n else np.zeros(1)
    return e


def env(path):
    w = wave.open(path)
    sr = w.getframerate()
    a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    if w.getnchannels() == 2:
        a = a.reshape(-1, 2).mean(1)
    hop = int(sr * 0.02)
    n = len(a) // hop
    return np.sqrt((a[: n * hop].reshape(n, hop) ** 2).mean(1)), hop / sr


def time_map(e, dt, t0, t1, nchars):
    """청크 [t0,t1] 안 글자 i 의 시각 — 유성(에너지) 누적을 시계로 균등 분배."""
    a, b = int(t0 / dt), int(t1 / dt)
    seg = e[a:b]
    thr = max(0.004, float(np.percentile(e, 20)) * 3)
    v = (seg > thr).astype(float) + 1e-3
    c = np.cumsum(v)
    c /= c[-1]
    ts = []
    for i in range(nchars):
        x = (i + 0.5) / nchars
        k = int(np.searchsorted(c, x))
        ts.append(t0 + min(k, len(seg) - 1) * dt)
    return ts


_SPK = {}


def speaker_jp(r):
    """행의 메시지 열쇠 → 원문 화자 이름(JP) — 원문 첫 줄이 화자 머리면 말한 글이 아니라 떼어 낸다."""
    sid = r["scene"]
    if sid not in _SPK:
        p = str(common.OUT_DIR / "messages" / f"scn{sid:03d}.json")
        try:
            _SPK[sid] = {m["key"]: (m.get("speaker") or "") for m in json.load(open(p))}
        except OSError:
            _SPK[sid] = {}
    return _SPK[sid].get(r["key"], "")


_ORD = {}


def chain_jp(rs, jp):
    sid = rs[0]["scene"]
    if sid not in _ORD:
        p = str(common.OUT_DIR / "messages" / f"scn{sid:03d}.json")
        try:
            _ORD[sid] = json.load(open(p))
        except OSError:
            _ORD[sid] = []
    ms = _ORD[sid]
    ks = [m["key"] for m in ms]
    if rs[0]["key"] not in ks:
        return jp
    i = ks.index(rs[0]["key"])
    need = 1.6 * sum(len(re.sub(r"\s", "", r["kr"])) for r in rs) * 1.6
    out = jp
    for m in ms[i + 1 : i + 8]:
        out += "\f" + m["jp"].lstrip("\n")
        if len(reading(out)) >= need:
            break
    return out


def segs_of(rows):
    """클립 행 → 메시지별 JP 쪽(조각) 목록 + 행↔조각 대응(길이 비례 DP)."""
    msgs = OrderedDict()
    for r in rows:
        msgs.setdefault(r["key"] if not r.get("greet") else "greet:" + str(r["idx"]), []).append(r)
    out = []  # (msgkey, [rows], [jp segs])
    for k, rs in msgs.items():
        jp = rs[0]["jp"]
        if sum(1 for r in rs if r["jp"].strip()) > 1:  # 행마다 원문이 따로 실린 이음 메시지 — 행 원문을 순서대로 쪽으로 쓴다
            jp = "\f".join(r["jp"].strip("\n") for r in rs if r["jp"].strip())
        if len(reading(jp)) < 4 and jp.strip() and rs[0]["scene"] >= 0:  # 머리(화자)만 있는 메시지 — 이어지는 메시지들의 원문을 필요한 만큼 붙인다
            jp = chain_jp(rs, jp)
        if not jp.strip():
            out.append((k, rs, []))
            continue
        spk = speaker_jp(rs[0])
        if spk and jp.lstrip("\n").startswith(spk):
            jp = jp.lstrip("\n")[len(spk):]
        first, _, rest = jp.lstrip("\n").partition("\n")
        if rest.strip() and len(first) <= 18 and not re.search(r"[。？！!?、…]", first):  # 문장부호 없는 짧은 첫 줄 = 이름·표제 머리
            jp = rest
        segs = [s.replace("\n", "") for s in re.split(r"[¶\f]", jp)]
        segs = [s for s in segs if reading(s)]
        out.append((k, rs, segs))
    return out


def map_pages(rs, segs):
    """KR 쪽 n 개 ↔ JP 조각 m 개 단조 대응. 쪽 i → (조각 j0..j1) 구간."""
    n, m = len(rs), len(segs)
    if n == m:
        return [(i, i + 1) for i in range(n)]
    kl = [max(1, len(re.sub(r"\s", "", r["kr"]))) for r in rs]
    jl = [max(1, len(reading(s))) for s in segs]
    R = sum(jl) / sum(kl)  # 이 메시지의 가나/한글 글자 비 — 메시지마다 맞춘다
    INF = 1e18
    S2 = 0.6

    def gc(lk, lj):  # Gale-Church 형 비용
        d = (lj - lk * R) / math.sqrt(max(lk * R, 1) * S2 * R)
        return d * d / 2

    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    bk = {}
    dp[0][0] = 0
    PRI = {(1, 1): 0.0, (1, 2): 2.4, (2, 1): 2.4, (1, 3): 4.5, (3, 1): 4.5}
    for i in range(n + 1):
        for j in range(m + 1):
            if dp[i][j] >= INF:
                continue
            for (di, dj), pr in PRI.items():
                ni, nj = i + di, j + dj
                if ni > n or nj > m:
                    continue
                c = gc(sum(kl[i:ni]), sum(jl[j:nj])) + pr
                if dp[i][j] + c < dp[ni][nj]:
                    dp[ni][nj] = dp[i][j] + c
                    bk[(ni, nj)] = (i, j)
    if dp[n][m] >= INF:
        return None
    path = []
    i, j = n, m
    while (i, j) != (0, 0):
        pi, pj = bk[(i, j)]
        path.append((pi, i, pj, j))
        i, j = pi, pj
    path.reverse()
    res = [None] * n
    for pi, i, pj, j in path:
        if i - pi == 1:
            res[pi] = (pj, j)
        else:  # 여러 쪽이 한 조각 — 쪽 글자 수 비례로 나눠 가진다(구간 = 누적 글자 수)
            cs = 0
            tl = sum(kl[pi:i])
            for q in range(pi, i):
                res[q] = (pj, j, cs, cs + kl[q], tl)
                cs += kl[q]
    return res


def audit_clip(clip, rows):
    cj = json.load(open(AUD + CH_DIR + "/" + clip + ".json"))
    wavp = BASE + "voice/" + clip + ".wav"
    e, dt = env(wavp)
    dur = cj["dur"]
    chunks = cj["chunks"]
    # STT 글자 흐름 — 구절(타임스탬프) 단위: 겹치는 창에서는 창 가운데에 가까운 구절을 고른다
    stream = []  # (char, time)
    unrel = []
    phs = []
    def synth(c):  # 구절 시각이 없는 창(텍스트만) — 문장 단위로 쪼개 글자 수 비례로 시각을 준다(판정용, 시각은 거칠다)
        sents = [x for x in re.split(r"(?<=[。！？!?])", c["text"]) if x.strip()]
        tl = sum(len(x) for x in sents) or 1
        out, cs = [], 0
        for x in sents:
            out.append({"text": x, "ts": [c["t0"] + (c["t1"] - c["t0"]) * cs / tl, c["t0"] + (c["t1"] - c["t0"]) * (cs + len(x)) / tl]})
            cs += len(x)
        return out

    for c in chunks:
        for p in (c.get("ph") or (synth(c) if c["text"] else [])):
            a0, a1 = p["ts"]
            cen = min(a0 - c["t0"], c["t1"] - a1) if c["t0"] > 0 or c["t1"] < dur - 0.01 else 99
            phs.append((cen, a0, a1, p["text"]))
    acc = []
    for cen, a0, a1, tx in sorted(phs, key=lambda x: -x[0]):
        ln = max(a1 - a0, 0.05)
        if any(min(a1, y1) - max(a0, y0) > 0.4 * ln for _, y0, y1, _ in acc):
            continue
        acc.append((cen, a0, a1, tx))
    acc.sort(key=lambda x: x[1])
    for cen, a0, a1, tx in acc:
        if is_hallu(tx):
            unrel.append((a0, a1))
            continue
        rd = reading(collapse_rep(tx))
        if not rd:
            continue
        idx_ = acc.index((cen, a0, a1, tx))
        nxt_ = acc[idx_ + 1][1] if idx_ + 1 < len(acc) else dur
        if a1 - a0 < 0.07 * len(rd):  # 구절 끝 시각이 비정상으로 짧다(창 끝 절단) — 다음 구절 시작까지 · 최대 글자당 0.16초로 늘린다
            a1 = min(max(nxt_, a0 + 0.1), a0 + 0.16 * len(rd))
        ts = time_map(e, dt, a0, min(a1, dur), len(rd)) if a1 - a0 > 0.1 else [a0] * len(rd)
        for ch, t in zip(rd, ts):
            stream.append((ch, t))
    S = "".join(ch for ch, _ in stream)
    msgs = segs_of(rows)
    script = []  # (char, seg id)
    segid = []  # (msgi, segj, jp)
    for mi, (k, rs, segs) in enumerate(msgs):
        for j, s in enumerate(segs):
            sid = len(segid)
            segid.append((mi, j, s))
            for ch in reading(s):
                script.append((ch, sid))
    T = "".join(ch for ch, _ in script)
    sm = difflib.SequenceMatcher(None, T, S, autojunk=False)
    match_t = {}  # script idx → time
    for a, b, n in sm.get_matching_blocks():
        if n >= 3:
            for q in range(n):
                match_t[a + q] = stream[b + q][1]
    # 조각별 통계
    seg_stat = {}
    pos = 0
    for sid, (mi, j, s) in enumerate(segid):
        L = len(reading(s))
        idxs = range(pos, pos + L)
        pos += L
        ts = [match_t[i] for i in idxs if i in match_t]
        frac = len(ts) / L if L else 0
        # 일치 글자 구간(연속 덩어리)
        spans = []
        cur = None
        for off, i in enumerate(idxs):
            if i in match_t:
                if cur is None:
                    cur = [off, off]
                else:
                    cur[1] = off
            else:
                if cur is not None and off - cur[1] > 3:
                    spans.append(tuple(cur))
                    cur = None
        if cur is not None:
            spans.append(tuple(cur))
        tmap = {off: match_t[i] for off, i in enumerate(idxs) if i in match_t}
        unordered = False
        if frac < 0.5 and L >= 8 and S:  # 음성 순서가 자막 순서와 다를 수 있다 — 순서를 풀고 이 조각만 스트림 전체와 맞춰 본다
            rd_ = reading(s)
            m2 = {}
            for a_, b_, n_ in difflib.SequenceMatcher(None, rd_, S, autojunk=False).get_matching_blocks():
                if n_ >= 3:
                    for q_ in range(n_):
                        m2[a_ + q_] = stream[b_ + q_][1]
            frac2 = len(m2) / L
            if frac2 >= max(0.5, frac + 0.3):
                unordered = True
                tmap, frac = m2, frac2
                ts = list(m2.values())
                spans = []
                cur = None
                for off in range(L):
                    if off in m2:
                        if cur is None:
                            cur = [off, off]
                        else:
                            cur[1] = off
                    elif cur is not None and off - cur[1] > 3:
                        spans.append(tuple(cur))
                        cur = None
                if cur is not None:
                    spans.append(tuple(cur))
        seg_stat[sid] = {"tmap": tmap, "frac": frac, "unordered": unordered, "t0": min(ts) if ts else None, "t1": max(ts) if ts else None, "spans": spans, "L": L}
    return msgs, segid, seg_stat, unrel, dur, e, dt


def silence_snap(e, dt, t, which, win=1.2):
    """시각 t 를 가까운 무음 경계로 — which='start': 무음 뒤 발성 시작(onset), 'end': 발성 뒤 무음(offset)."""
    thr = max(0.004, float(np.percentile(e, 20)) * 3)
    v = e > thr
    a = max(1, int((t - win) / dt))
    b = min(len(v) - 1, int((t + win) / dt))
    best = None
    for i in range(a, b):
        if which == "start" and (not v[i - 1]) and v[i]:
            # 무음이 0.12초 이상 이어진 뒤여야
            if i >= 6 and not v[i - 6 : i].any():
                d = abs(i * dt - t)
                if best is None or d < best[0]:
                    best = (d, i * dt)
        if which == "end" and v[i - 1] and (not v[i]):
            if i + 6 < len(v) and not v[i : i + 6].any():
                d = abs(i * dt - t)
                if best is None or d < best[0]:
                    best = (d, i * dt)
    return best[1] if best else t


if __name__ == "__main__":
    pass


LAUGH = re.compile(r"[うわふはひへほっ]{4,}")


def strip_laugh(r: str) -> str:
    return LAUGH.sub("", r)


def run_all(clips):
    data = json.load(open(BASE + "data.json"))
    out = []
    for clip in clips:
        rows = [r for r in data if r["clip"] == clip]
        try:
            msgs, segid, st, unrel, dur, e, dt = audit_clip(clip, rows)
        except FileNotFoundError:
            for r in rows:
                out.append({"clip": clip, "idx": r["idx"], "voice_match": "불가", "why": "받아쓰기 없음"})
            continue
        # 스트림 구멍(환각 청크 가운데 구간) — 시각으로
        holes = []
        cj = json.load(open(AUD + CH_DIR + "/" + clip + ".json"))["chunks"]
        for k, c in enumerate(cj):
            if is_hallu(c["text"]):
                holes.append((c["t0"] + (5.0 if k > 0 else 0), c["t1"] - (5.0 if k < len(cj) - 1 else 0)))
        # 조각 통계를 일치 글자 기준으로 다시: 웃음 제외 글자 비율
        sid_base = {}
        pos = 0
        for sid, (mi, j, s) in enumerate(segid):
            sid_base[sid] = pos
            pos += len(reading(s))
        # 인접 조각의 시각으로 못 맞춘 조각의 예상 구간
        def expected(sid):
            prev = next((st[q]["t1"] for q in range(sid - 1, -1, -1) if st[q]["t1"] is not None and st[q]["frac"] >= 0.3), 0.0)
            nxt = next((st[q]["t0"] for q in range(sid + 1, len(segid)) if st[q]["t0"] is not None and st[q]["frac"] >= 0.3), dur)
            return prev, nxt

        rowres = {}
        for mi, (k, rs, segs) in enumerate(msgs):
            if not segs:
                for r in rs:
                    kl_ = len(re.sub(r"\s", "", r["kr"]))
                    rowres[r["idx"]] = {"voice_match": "불가", "why": "원문(JP) 없음", "jlen": max(4, int(kl_ * 2.2)), "jlaugh": 0, "anc0": None, "anc1": None, "t": None, "sids": []}
                continue
            mp = map_pages(rs, segs)
            if mp is None:  # 대응 실패 → 메시지 전체를 쪽 글자 수 비례로 나눈다
                kls = [max(1, len(re.sub(r"\s", "", r["kr"]))) for r in rs]
                tl = sum(kls)
                cs = 0
                mp = []
                for kl_ in kls:
                    mp.append((0, len(segs), cs, cs + kl_, tl))
                    cs += kl_
            msg_sids = [sid for sid, (m_, j, s) in enumerate(segid) if m_ == mi]
            for ri, r in enumerate(rs):
                ent = mp[ri] if mp else None
                if ent is None:
                    rowres[r["idx"]] = {"voice_match": "불가", "why": "쪽↔원문 대응 실패"}
                    continue
                j0, j1 = ent[0], ent[1]
                part = (ent[2], ent[3] if len(ent) == 5 else ent[2] + 1, ent[4] if len(ent) == 5 else ent[3]) if len(ent) >= 4 else None
                sids = msg_sids[j0:j1]
                tot = 0
                hit = 0
                jlen = 0
                jlaugh = 0
                anc = []
                for sid in sids:
                    L_ = len(reading(segid[sid][2]))
                    jlen += (L_ * part[1] // part[2] - L_ * part[0] // part[2]) if part else L_
                ts = []
                frag = []
                for sid in sids:
                    rd = reading(segid[sid][2])
                    L = len(rd)
                    a0, a1 = 0, L
                    if part:
                        a0, a1 = L * part[0] // part[2], L * part[1] // part[2]
                    base = sid_base[sid]
                    laugh = set()
                    for m_ in LAUGH.finditer(rd):
                        laugh.update(range(m_.start(), m_.end()))
                    # 일치 판정은 st 의 match 가 아니라 spans 로 — spans 는 (off0, off1) 일치 덩어리
                    cover = set()
                    for s0, s1 in st[sid]["spans"]:
                        cover.update(range(s0, s1 + 1))
                    jlaugh += sum(1 for q in range(a0, a1) if q in laugh)
                    idxs = [q for q in range(a0, a1) if q not in laugh]
                    tot += len(idxs)
                    hit += sum(1 for q in idxs if q in cover)
                    for q in range(a0, a1):
                        if q in st[sid]["tmap"] and q not in laugh:
                            anc.append(st[sid]["tmap"][q])
                    cs = sorted(q for q in range(a0, a1) if q in cover)
                    if cs:
                        frag.append(segid[sid][2][: 0] + f"{cs[0]}-{cs[-1]}/{L}")
                    if st[sid]["t0"] is not None:
                        ts.append((st[sid]["t0"], st[sid]["t1"]))
                if tot < 4:
                    kl_ = len(re.sub(r"\s", "", r["kr"]))
                    why_ = "웃음·감탄만(받아쓰기 불능)" if kl_ <= 16 else "원문 짝 없음(이 메시지의 JP 가 머리뿐 — 대사 원문이 이음 메시지에 있음)"
                    rowres[r["idx"]] = {"voice_match": "불가", "why": why_, "jlen": max(jlen, kl_ * 2), "jlaugh": jlaugh, "sids": sids}
                    continue
                frac = hit / tot
                if frac >= 0.6:
                    vm = "있음"
                elif frac >= 0.2:
                    vm = "일부"
                else:
                    vm = "없음"
                why = f"일치 {hit}/{tot}자({frac:.0%})"
                if vm != "있음":
                    ex = [expected(sid) for sid in sids]
                    lo = min(x[0] for x in ex)
                    hi = max(x[1] for x in ex)
                    ov = sum(max(0, min(hi, b) - max(lo, a)) for a, b in holes)
                    last_ok = max([st[q]["t1"] for q in range(len(segid)) if st[q]["t1"] is not None and st[q]["frac"] >= 0.3] or [0.0])
                    trailing = all(sid > max([q for q in range(len(segid)) if st[q]["frac"] >= 0.3] or [-1]) for sid in sids)
                    tail_hallu = any(c["t1"] >= last_ok for c in cj if is_hallu(c["text"]))
                    if trailing and tail_hallu and vm == "없음":
                        vm, why = "불가", "끝부분 환각 청크(말 끝 뒤 무음에서 환각) — " + why
                    elif holes and hi > lo and ov / (hi - lo) > 0.5:
                        vm, why = "불가", f"환각 청크 구간({lo:.0f}~{hi:.0f}s) — " + why
                    elif vm == "없음":
                        why += f" · 앞뒤 일치 시각 {lo:.1f}~{hi:.1f}s 사이"
                rowres[r["idx"]] = {"voice_match": vm, "why": why, "jlen": jlen, "jlaugh": jlaugh, "exact": len(rs) == len(segs), "anc0": robust_first(anc), "unordered": any(st[q].get("unordered") for q in sids), "anc1": (max(anc) if anc else None), "frac": round(frac, 2), "span": frag, "t": ts[0][0] if ts else None, "t1": ts[-1][1] if ts else None, "sids": sids}
        # 후보 시각 — 유성 시간 축 위에서 글자 수 비례(말하는 줄만) → 무음 경계로 스냅
        order = [r["idx"] for r in rows]
        keys = [i for i in order if rowres.get(i, {}).get("voice_match") in ("있음", "일부") and rowres[i].get("t") is not None]
        thr = max(0.004, float(np.percentile(e, 20)) * 3)
        voiced = (e > thr).astype(float)
        V = np.concatenate([[0.0], np.cumsum(voiced) * dt])  # V[i]: i 번째 20ms 칸까지 누적 유성 초
        if keys:
            lens = []
            for i in keys:
                rr = rowres[i]
                L = 0
                for sid in rr["sids"]:
                    L += len(strip_laugh(reading(segid[sid][2])))
                lens.append(max(L, 3))
            tfirst = min(rowres[keys[0]]["t"], dur)
            tlast = rowres[keys[-1]]["t1"] if rowres[keys[-1]].get("t1") is not None else dur
            # 첫 줄 시작은 첫 일치 시각 이전의 발성 시작, 끝은 마지막 일치 뒤 발성 끝
            v0 = V[min(len(V) - 1, int(tfirst / dt))]
            v1 = V[min(len(V) - 1, int(tlast / dt))]
            tot = sum(lens)
            cum = 0
            starts = {}
            for i, L in zip(keys, lens):
                vt = v0 + (v1 - v0) * cum / tot
                k = int(np.searchsorted(V, vt))
                starts[i] = silence_snap(e, dt, k * dt, "start", win=1.0)
                cum += L
            starts[keys[0]] = silence_snap(e, dt, tfirst, "start", win=1.5)
            for n_, i in enumerate(keys):
                rr = rowres[i]
                rr["cand_start"] = round(starts[i], 2)
                if n_ + 1 < len(keys):
                    rr["cand_end"] = round(starts[keys[n_ + 1]], 2)
                else:
                    rr["cand_end"] = round(silence_snap(e, dt, tlast, "end", win=1.5), 2)
        for r in rows:
            rr = dict(rowres.get(r["idx"], {"voice_match": "불가", "why": "행 없음"}))
            rr["clip"], rr["idx"] = clip, r["idx"]
            if "cand_start" in rr and r.get("t_start") is not None and abs(rr["cand_start"] - r["t_start"]) > 0.5:
                rr["sync_off"] = round(rr["cand_start"] - r["t_start"], 2)
            out.append(rr)
    return out


# ---- 토막 전체 실행 ---------------------------------------------------------------------------------------------------------------------
SKIP_CLIPS = ("scn002", "scn006", "scn017")  # 마스터 확인 완료(11-03) — 대상 밖
LEAD, TAIL = 0.2, 0.5  # 자막 시작 = 발화 시작 −0.2초(약간 빨리 — 마스터 11-03), 끝 = 발화 끝 +0.5초(규칙 2-15)
ORDER = {"있음": 3, "일부": 2, "없음": 1, "불가": 0}


def build_rows(clips: list[str]) -> list[dict]:
    """토막마다 판정 + 소리 실측 후보. 소형(wds) 판정과 대형(chunks20) 판정 중 「음성에 있다」는 쪽을 따른다(거짓 「없음」 방지)."""
    global CH_DIR
    import voice_envelope as sync

    data = json.load(open(BASE + "data.json"))
    CH_DIR = "wds"
    small = {(x["clip"], x["idx"]): x for x in run_all(clips)}
    CH_DIR = "chunks20"
    large_clips = [c for c in clips if (Path(AUD) / "chunks20" / f"{c}.json").exists()]
    large = {(x["clip"], x["idx"]): x for x in run_all(large_clips)}
    out = []
    for clip in clips:
        rs = [r for r in data if r["clip"] == clip]
        fin = {}
        for r in rs:
            a, b = small[(clip, r["idx"])], large.get((clip, r["idx"]))
            x = dict(b if (b is not None and ORDER[b["voice_match"]] > ORDER[a["voice_match"]] and a.get("sids") != []) else a)
            x["anc0"] = a.get("anc0")  # 닻은 소형 word 시각에서
            if x["voice_match"] == "없음" and (x.get("jlen", 99) < 12 or not x.get("exact", False)):
                x["voice_match"], x["why"] = "불가", "짧은 줄·쪽 대응 불확실 — 받아쓰기로 못 가림 · " + x["why"]
            fin[r["idx"]] = x
        jp_rows = [i for i, x in fin.items() if x.get("sids")]
        if jp_rows and not any(fin[i]["voice_match"] in ("있음", "일부") for i in jp_rows):  # 토막 전체가 안 맞음 = 다른 대사이거나 말 없는 소리
            for i in jp_rows:
                if fin[i]["voice_match"] == "없음":
                    fin[i]["voice_match"], fin[i]["why"] = "불가", "이 토막에 음성과 맞는 줄이 없음(말 없는 소리이거나 다른 대사) — 마스터 청취 · " + fin[i]["why"]
        for x in fin.values():
            if x.get("unordered") and x["voice_match"] == "있음":
                x["why"] = "음성에 있음(음성 순서가 자막 순서와 다름) · " + x["why"]
        ok = [(r, fin[r["idx"]]) for r in rs if fin[r["idx"]]["voice_match"] in ("있음", "일부", "불가") and "jlen" in fin[r["idx"]] and not fin[r["idx"]].get("unordered")]
        cand = {}
        if ok:
            db, dur = sync.envelope(BASE + "voice/" + clip + ".wav")
            runs_, _ = sync.runs(db, min_gap=0.25, add=6)
            lens = [max(3, x["jlen"] + x.get("jlaugh", 0)) for _, x in ok]
            res = sync.assign(runs_, lens, [x.get("anc0") for _, x in ok], GB=4, AS=1)
            for k, ((r, x), (a, b)) in enumerate(zip(ok, res, strict=True)):
                nxt = res[k + 1][0] - LEAD if k + 1 < len(res) else dur
                s = max(0.0, a - LEAD)
                e = min(b + TAIL, nxt) if k + 1 < len(res) else min(b + TAIL, dur)
                anc = x.get("anc0")
                cand[r["idx"]] = (round(s, 2), round(max(e, s + 0.5), 2), anc is not None and abs(a - LEAD - anc) <= 1.0)
        for r in rs:
            x = fin[r["idx"]]
            row = {"clip": clip, "key": r["key"], "page": r["page"], "voice_match": x["voice_match"], "why": x["why"]}
            if r["idx"] in cand:
                row["cand_start"], row["cand_end"], row["sync_conf"] = cand[r["idx"]]
            out.append(row)
    return out


if __name__ == "__main__":
    data = json.load(open(BASE + "data.json"))
    clips = [c for c in dict.fromkeys(r["clip"] for r in data) if not c.startswith(SKIP_CLIPS) and c != "syscard" and (Path(AUD) / "wds" / f"{c}.json").exists()]
    spec = Path(common.GAME_DIR) / "script" / "voice_audit.json"
    old = json.loads(spec.read_text("utf-8")) if spec.exists() else {"_doc": "", "rows": []}
    keep = [r for r in old["rows"] if r["clip"].startswith(SKIP_CLIPS)]  # 마스터 확인 토막의 기록은 그대로
    rows = keep + build_rows(clips)
    spec.write_text(json.dumps({"_doc": old["_doc"], "rows": rows}, ensure_ascii=False, indent=1), "utf-8")
    print(f"{spec}: 토막 {len(clips)} · 줄 {len(rows)}")
