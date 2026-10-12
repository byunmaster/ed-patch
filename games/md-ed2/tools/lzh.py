"""대본 블록 전용 압축 `LZH` — 원본 LZ 에서 **리터럴만 정적 허프만**으로 바꾼 것 (파이썬 기준 구현 · 인코더).

    python3 tools/lzh.py --self-test    # 합성 자료 왕복
    python3 tools/lzh.py --stats        # 현재 정본으로 만든 대본 블록의 크기(원본 LZ ↔ LZH)

왜 — 한국어는 가나보다 LZ 압축이 훨씬 안 된다(리터럴이 대부분인데 원본 LZ 의 리터럴은 9비트). 대본 칸이 모자라 리터럴을
정적 허프만(대본 전 블록이 한 표를 쓴다)으로 줄인다. 그래픽 등 다른 아카이브는 원래 디코더 그대로다.

형식(디코더는 `lzh68k.py` — 68000, 대본 로더의 `jsr $DD4` 세 곳만 새 루틴으로 돌린다):

    블록 = BE16 출력 길이 + 비트열(MSB 먼저, 바이트 단위로 읽는다)
    0                 리터럴 — 허프만 기호 하나(정준 부호, 길이 ≤ MAXLEN)
    1 + 길이 + 거리   되참조 — 길이 = 3 + EG(KL) · 거리 = 1 + EG(KD) (겹쳐 복사 가능: 0 의 긴 줄은 거리 1)
    EG(k)(v): m = floor(log2((v >> k) + 1)) 개의 0, (v >> k) + 1 을 (m+1)비트, 그다음 v 의 아래 k비트
    표 = 길이별 부호 수 cnt[1..MAXLEN] (MAXLEN 바이트) + 정준 순서로 정렬한 기호 256 바이트(앞 nsym 개만 의미) — 롬에 그대로 둔다
"""

import heapq
import struct
import sys

MAXLEN = 12  # 허프만 부호 최대 길이
MINMATCH = 3
KL = 0  # 길이 EG 파라미터
KD = 4  # 거리 EG 파라미터
MAX_DIST = 8191
MAX_LEN = 4096
CHAIN = 400


# ── 비트 입출력 ──────────────────────────────────────────────────────────────
class BitWriter:
    def __init__(self):
        self.out = bytearray()
        self.acc = 0
        self.n = 0

    def bits(self, v: int, k: int) -> None:
        for i in range(k - 1, -1, -1):
            self.acc = (self.acc << 1) | ((v >> i) & 1)
            self.n += 1
            if self.n == 8:
                self.out.append(self.acc)
                self.acc = self.n = 0

    def finish(self) -> bytes:
        if self.n:
            self.out.append((self.acc << (8 - self.n)) & 0xFF)
            self.acc = self.n = 0
        return bytes(self.out)


class BitReader:
    def __init__(self, d: bytes, p: int):
        self.d, self.p, self.buf, self.n = d, p, 0, 0

    def bit(self) -> int:
        if self.n == 0:
            self.buf = self.d[self.p]
            self.p += 1
            self.n = 8
        self.n -= 1
        return (self.buf >> self.n) & 1

    def bits(self, k: int) -> int:
        v = 0
        for _ in range(k):
            v = (v << 1) | self.bit()
        return v


def eg_bits(v: int, k: int) -> int:
    return 2 * ((v >> k) + 1).bit_length() - 1 + k


def eg_put(w: BitWriter, v: int, k: int) -> None:
    q = (v >> k) + 1
    m = q.bit_length() - 1
    w.bits(0, m)
    w.bits(q, m + 1)
    w.bits(v & ((1 << k) - 1), k)


def eg_get(r: BitReader, k: int) -> int:
    m = 0
    while r.bit() == 0:
        m += 1
    q = (1 << m) | r.bits(m)
    return ((q - 1) << k) | r.bits(k)


# ── 허프만(정준) ─────────────────────────────────────────────────────────────
def huffman_lengths(freq: list[int], maxlen: int = MAXLEN) -> list[int]:
    """기호별 부호 길이(0 = 안 쓴다). 길이 상한을 넘으면 빈도를 눌러 다시 만든다(결정적)."""
    f = [c for c in freq]
    if sum(1 for c in f if c) == 1:
        return [1 if c else 0 for c in f]
    while True:
        heap = [(c, i, (i,)) for i, c in enumerate(f) if c]
        heapq.heapify(heap)
        ln = [0] * len(f)
        uid = len(f)
        while len(heap) > 1:
            c1, _a, s1 = heapq.heappop(heap)
            c2, _b, s2 = heapq.heappop(heap)
            for s in s1 + s2:
                ln[s] += 1
            uid += 1
            heapq.heappush(heap, (c1 + c2, uid, s1 + s2))
        if max(ln) <= maxlen:
            return ln
        f = [(c + 1) // 2 if c else 0 for c in f]


def make_table(lengths: list[int]) -> tuple[bytes, dict[int, tuple[int, int]]]:
    """부호 길이 → (롬 표 바이트, {기호: (부호, 길이)}). 정준 순서 = (길이, 기호값)."""
    cnt = [0] * (MAXLEN + 1)
    for ln in lengths:
        cnt[ln] += 1
    cnt[0] = 0
    syms = sorted((ln, s) for s, ln in enumerate(lengths) if ln)
    order = [s for _ln, s in syms]
    codes: dict[int, tuple[int, int]] = {}
    code = 0
    k = 0
    for ln in range(1, MAXLEN + 1):
        for _ in range(cnt[ln]):
            codes[order[k]] = (code, ln)
            code += 1
            k += 1
        code <<= 1
    table = bytes(cnt[1:]) + bytes(order) + b"\x00" * (256 - len(order))
    return table, codes


def parse_table(t: bytes) -> tuple[list[int], list[int]]:
    return list(t[:MAXLEN]), list(t[MAXLEN : MAXLEN + 256])


# ── 되참조 탐색 + 최소 비용 파싱 ───────────────────────────────────────────────
def _matches(data: bytes, i: int, heads: dict, lim: int):
    """i 에서 시작하는 일치 후보 [(길이, 거리)] — 거리가 가까운 것부터, 길이가 **늘어날 때만**."""
    key = data[i : i + 3]
    out = []
    best = MINMATCH - 1
    for t, j in enumerate(reversed(heads.get(key, ()))):
        if t >= CHAIN:
            break
        dist = i - j
        if dist > MAX_DIST:
            break
        m = 3
        while m < lim and data[j + m] == data[i + m]:
            m += 1
        if m > best:
            best = m
            out.append((m, dist))
            if m >= lim:
                break
    return out


def plan(data: bytes, litcost: list[int]) -> list[tuple]:
    """('lit', 바이트) · ('mat', 길이, 거리) 목록. 비용 = 비트 수(리터럴 = 1 + 허프만 길이, 되참조 = 1 + EG 길이 + EG 거리)."""
    n = len(data)
    INF = 1 << 60
    cost = [INF] * (n + 1)
    how: list[tuple | None] = [None] * (n + 1)
    cost[0] = 0
    heads: dict[bytes, list[int]] = {}
    # 길이 EG 비용이 바뀌는 문턱들(그 길이까지 쓰는 게 가장 싸다)
    for i in range(n):
        c0 = cost[i]
        lc = c0 + 1 + litcost[data[i]]
        if lc < cost[i + 1]:
            cost[i + 1], how[i + 1] = lc, ("lit", data[i])
        lim = min(MAX_LEN, n - i)
        if lim >= MINMATCH:
            cands = _matches(data, i, heads, lim)
            prev = MINMATCH - 1
            for m, dist in cands:
                db = eg_bits(dist - 1, KD)
                # prev+1..m 길이에서 이 거리를 쓴다 — 비용 계단의 끝과 m 만 본다
                lens = {m}
                q = 1
                while (
                    3 + (1 << q) - 1
                ) <= m:  # EG0 문턱: 길이-3+1 가 2의 거듭제곱일 때 비용이 오른다
                    lens.add(3 + (1 << q) - 2)
                    q += 1
                lens.update(range(max(prev + 1, MINMATCH), min(m, prev + 6) + 1))
                for ln in lens:
                    if ln <= prev or ln > m:
                        continue
                    cc = c0 + 1 + eg_bits(ln - MINMATCH, KL) + db
                    if cc < cost[i + ln]:
                        cost[i + ln], how[i + ln] = cc, ("mat", ln, dist, i)
                prev = m
        if i + 2 < n:
            heads.setdefault(data[i : i + 3], []).append(i)
    out: list[tuple] = []
    p = n
    while p > 0:
        h = how[p]
        assert h is not None
        if h[0] == "lit":
            out.append(h)
            p -= 1
        else:
            out.append(h[:3])
            p = h[3]
    out.reverse()
    return out


def encode_block(data: bytes, codes: dict[int, tuple[int, int]], pl: list[tuple]) -> bytes:
    w = BitWriter()
    for t in pl:
        if t[0] == "lit":
            w.bits(0, 1)
            code, ln = codes[t[1]]
            w.bits(code, ln)
        else:
            w.bits(1, 1)
            eg_put(w, t[1] - MINMATCH, KL)
            eg_put(w, t[2] - 1, KD)
    return struct.pack(">H", len(data)) + w.finish()


def decode_block(blk: bytes, table: bytes, p: int = 0) -> tuple[bytes, int]:
    """(출력, 쓴 바이트 수) — 정준 허프만을 puff 식으로 푼다(68000 디코더와 같은 순서)."""
    n = struct.unpack(">H", blk[p : p + 2])[0]
    cnt, sym = parse_table(table)
    r = BitReader(blk, p + 2)
    out = bytearray()
    while len(out) < n:
        if r.bit() == 0:
            code = first = index = 0
            for ln in range(MAXLEN):
                code |= r.bit()
                c = cnt[ln]
                if code - c < first:
                    out.append(sym[index + (code - first)])
                    break
                index += c
                first += c
                first <<= 1
                code <<= 1
            else:
                raise ValueError("허프만 부호가 표에 없다")
        else:
            ln = MINMATCH + eg_get(r, KL)
            dist = 1 + eg_get(r, KD)
            if dist > len(out):
                raise ValueError("거리가 출력을 넘는다")
            for _ in range(ln):
                out.append(out[-dist])
    if len(out) != n:
        raise ValueError("출력 길이가 헤더와 다르다")
    used = r.p - p
    return bytes(out), used


# ── 전 블록 일괄(표는 한 벌) ─────────────────────────────────────────────────
def build(blocks: list[bytes], rounds: int = 3) -> tuple[bytes, list[bytes]]:
    """대본 블록 전부 → (롬 표, 압축 블록들). 리터럴 비용을 허프만 길이로 되먹여 몇 번 다시 파싱한다(결정적)."""
    litcost = [8] * 256
    pls: list[list[tuple]] = []
    table = b""
    codes: dict[int, tuple[int, int]] = {}
    for _ in range(rounds):
        pls = [plan(b, litcost) for b in blocks]
        freq = [0] * 256
        for pl in pls:
            for t in pl:
                if t[0] == "lit":
                    freq[t[1]] += 1
        for s in range(
            256
        ):  # 안 나온 기호도 부호가 있어야 한다(되먹임 파싱이 리터럴로 쓸 수 있다) — 빈도 1
            freq[s] = max(freq[s], 1)
        lengths = huffman_lengths(freq)
        table, codes = make_table(lengths)
        litcost = list(lengths)
    comp = [encode_block(b, codes, pl) for b, pl in zip(blocks, pls, strict=True)]
    return table, comp


def pad(b: bytes) -> bytes:
    return b + b"\x00" * (len(b) & 1)


if __name__ == "__main__":
    import random

    if "--self-test" in sys.argv:
        random.seed(1)
        blocks = []
        for _ in range(4):
            words = [bytes(random.choices(range(0x81, 0xA0), k=2)) for _ in range(30)]
            b = b"".join(random.choice(words) for _ in range(800)) + bytes(500) + b"abc" * 50
            blocks.append(b)
        t, comp = build(blocks)
        for b, c in zip(blocks, comp, strict=True):
            out, _ = decode_block(c, t)
            assert out == b
        print("  LZH 합성 왕복 OK", [len(c) for c in comp], len(t))
