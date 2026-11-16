"""소리 실측 싱크(마스터 11-03 「싱크는 음성이 나오는 시간에 맞춰서」) — 대역 필터 음량 포락선으로 발화 구간을 잡고, 줄(글자 수 비례 + 받아쓰기 시각 닻)을 발화 사이 무음 경계에 DP 로 배정한다.
씬 2·6·17 마스터 값 대비 >0.5초 어긋남 1/4 · 8/13 · 2/20(11-03) — 확신 낮은 줄은 `sync_conf` 로 가른다."""
import wave

import numpy as np
from scipy.signal import butter, sosfiltfilt

HOP = 0.01


def load(path):
    w = wave.open(path)
    sr = w.getframerate()
    a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    if w.getnchannels() == 2:
        a = a.reshape(-1, 2).mean(1)
    return a, sr


def envelope(path):
    a, sr = load(path)
    sos = butter(4, [200, 3800], btype="band", fs=sr, output="sos")
    f = sosfiltfilt(sos, a)
    h = int(sr * HOP)
    n = len(f) // h
    x = f[: n * h].reshape(n, h)
    rms = np.sqrt((x**2).mean(1) + 1e-12)
    return 20 * np.log10(rms + 1e-9), len(a) / sr


def runs(db, min_gap=0.15, min_run=0.2, add=4.5):
    from scipy.ndimage import uniform_filter1d

    s = uniform_filter1d(db, 9)
    floor = np.percentile(s, 15)
    v = s > floor + add
    idx = np.flatnonzero(np.diff(np.concatenate([[0], v.astype(int), [0]])))
    rs = [[float(idx[i] * HOP), float(idx[i + 1] * HOP)] for i in range(0, len(idx), 2)]
    m = []
    for r in rs:
        if m and r[0] - m[-1][1] < min_gap:
            m[-1][1] = r[1]
        else:
            m.append(r)
    return [r for r in m if r[1] - r[0] >= min_run], float(floor + add)


def assign(runs_, lens, anchors, min_boundary_gap=0.12, GB=1.5, AS=5.0, FIRST=2.0, LATE=0.6):
    # 같은 시각을 가리키는 닻(한 구절을 나눠 가진 줄들)은 첫 줄만 쓴다
    anchors = list(anchors)
    for i in range(1, len(anchors)):
        if anchors[i] is not None and any(anchors[k] is not None and abs(anchors[k] - anchors[i]) < 0.3 for k in range(max(0, i - 3), i)):
            anchors[i] = None
    """lens[i] 글자 수, anchors[i] 받아쓰기 시각(없으면 None). 반환: 줄마다 (시작, 끝=마지막 발화 끝)."""
    n = len(lens)
    if n == 0 or not runs_:
        return []
    # 경계 후보 = 런 사이 무음. 런 k 의 앞 경계 = 런 k 의 시작.
    R = runs_
    gaps = [k for k in range(1, len(R)) if R[k][0] - R[k - 1][1] >= min_boundary_gap]
    cand = [0] + gaps  # 줄 시작이 될 수 있는 런 번호
    cum = np.concatenate([[0], np.cumsum([r[1] - r[0] for r in R])])  # 런까지 누적 유성 시간
    total = cum[-1]
    rate = total / sum(lens)
    C = len(cand)
    INF = 1e18
    dp = np.full((n + 1, C), INF)
    bk = np.zeros((n + 1, C), dtype=int)
    # dp[i][c]: 줄 i(0기반) 가 후보 c 에서 시작
    for c in range(C):
        k = cand[c]
        cost = 0.0
        if anchors[0] is not None:
            cost += ((R[k][0] - anchors[0]) / (AS if R[k][0] <= anchors[0] else AS * LATE)) ** 2
        cost += 0 if c == 0 else FIRST + 0.3 * (cum[k] / max(rate, 1e-6))  # 첫 줄 앞에 소리가 많이 남으면 벌점
        dp[0][c] = cost
    for i in range(1, n + 1):
        for c in range(C):
            k = cand[c] if i < n else len(R)
            if i == n and c != 0:
                break
            best = INF
            arg = 0
            for pc in range(c if i < n else C):
                if dp[i - 1][pc] >= INF:
                    continue
                if i < n and pc >= c:
                    continue
                pk = cand[pc]
                v = cum[k] - cum[pk] if i < n else cum[len(R)] - cum[pk]
                exp = lens[i - 1] * rate
                cost = dp[i - 1][pc] + ((v - exp) / max(exp, 0.5)) ** 2 * 1.0
                if i < n:
                    g = R[k][0] - R[k - 1][1]
                    cost -= min(g, 0.8) * GB
                    if anchors[i] is not None:
                        cost += ((R[k][0] - anchors[i]) / (AS if R[k][0] <= anchors[i] else AS * LATE)) ** 2
                if cost < best:
                    best, arg = cost, pc
            if best < INF:
                dp[i][c], bk[i][c] = best, arg
        if i == n:
            break
    # 마지막 줄 비용 포함해 끝에서 역추적: dp[n][0] 로 모음
    # (위 루프에서 i==n 은 c=0 칸에만 기록)
    path = [0] * (n + 1)
    c = 0
    for i in range(n, 0, -1):
        c = bk[i][c] if i == n else bk[i][c]
        path[i - 1] = c
    starts = [cand[path[i]] for i in range(n)]
    out = []
    for i in range(n):
        k0 = starts[i]
        k1 = starts[i + 1] if i + 1 < n else len(R)
        out.append((R[k0][0], R[k1 - 1][1]))
    return out


def assign2(R, lens, anchors, win_lo=1.0, win_hi=0.6, GB=4.0):
    """닻(받아쓰기 첫 글자 시각)이 있는 줄은 ±구간 안 가장 가까운 발화 시작에 붙이고, 닻 없는 줄은 앞뒤 닻 사이에서 DP 로 나눈다.
    반환: [(시작, 끝=그 줄 마지막 발화 끝, 출처 'anchor'|'dp')]"""
    n = len(lens)
    starts = [None] * n
    src = ['dp'] * n
    onsets = [r[0] for r in R]
    last = -1e9
    for i, a in enumerate(anchors):
        if a is None:
            continue
        c = [o for o in onsets if a - win_lo <= o <= a + win_hi]
        if c:
            o = min(c, key=lambda o: abs(o - a))
        else:
            o = max(a - 0.1, 0.0)
        if o <= last + 0.3:  # 단조 아님 — 닻 버림
            continue
        starts[i] = o
        src[i] = 'anchor'
        last = o
    # 닻 없는 줄 구간 DP
    i = 0
    while i < n:
        if starts[i] is not None:
            i += 1
            continue
        j = i
        while j < n and starts[j] is None:
            j += 1
        # 구간 [p..j-1] — p = i-1 이 닻 줄이면 그 줄도 포함
        p = i - 1 if i > 0 else i
        s0 = starts[p] if (i > 0 and starts[p] is not None) else 0.0
        s1 = starts[j] if j < n else 1e9
        sub = [r for r in R if r[0] >= s0 - 0.05 and r[1] <= s1 + 0.05 or (r[0] >= s0 - 0.05 and r[0] < s1)]
        lo = p
        hi = j
        if sub and hi - lo >= 1:
            out = assign(sub, lens[lo:hi], [None] * (hi - lo), GB=GB)
            for k, (a_, b_) in zip(range(lo, hi), out):
                if starts[k] is None:
                    starts[k] = a_
        else:
            for k in range(i, j):
                starts[k] = s0
        i = j
    res = []
    for k in range(n):
        nxt = starts[k + 1] if k + 1 < n else 1e9
        ends = [r[1] for r in R if starts[k] - 0.05 <= r[0] < nxt - 0.05]
        res.append((starts[k], max(ends) if ends else starts[k] + 1.0, src[k]))
    return res
