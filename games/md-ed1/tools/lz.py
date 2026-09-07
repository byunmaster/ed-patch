"""md-ed1 LZ 코덱 — 롬 `$0C9E~$0DEE`(디컴프레서)를 옮긴 것. 왕복은 `tests/test_lz.py`.

블록 = `[LE16 압축길이-1][00][플래그 8비트][스트림 …]`. 스트림은 **플래그 워드(LE16, LSB 부터)와
데이터 바이트가 섞여** 있다 — 디코더가 비트가 떨어질 때마다 커서에서 2B 를 새로 읽는다.
첫 그룹만 8비트다(헤더의 넷째 바이트, 셋째 바이트는 안 쓴다).

    0            리터럴 1B
    1 0 dd       되참조, 거리 = 바이트(1~255)               + 길이 부호
    1 1 hhhhh dd 되참조, 거리 = h<<8|dd (13비트, 2~8191)   + 길이 부호
                 거리 0 = **끝**(다음 1B 가 0 이 아니면 새 청크가 이어진다)
                 거리 1 = **RLE**: f nnnn [dd] vv → vv 를 (n+14)회 (f=1 이면 n 은 12비트)
    길이 부호: 1=2 · 01=3 · 001=4 · 0001=5 · 0000 1 nnn = 6~13 · 0000 0 bb = 14~269

⚠ 길이 부호의 단항은 **1 이 멈춤**이다 — 처음에 반대로 읽어 첫 블록부터 갈렸다(devlog).
⚠ 되참조 최소 거리는 1 이고 **출력 시작을 넘는 참조는 없다**(링 초기화 같은 건 없다).
"""

import struct
import sys
from pathlib import Path

MAX_DIST = 8191
MAX_LEN = 269
RLE_MIN = 14
RLE_MAX = 0xFFF + 14


class _Bits:
    def __init__(self, d: bytes, p: int):
        self.d, self.p, self.buf, self.n = d, p, 0, 0

    def bit(self) -> int:
        if self.n == 0:
            self.buf = self.d[self.p] | (self.d[self.p + 1] << 8)
            self.p += 2
            self.n = 16
        b = self.buf & 1
        self.buf >>= 1
        self.n -= 1
        return b

    def bits(self, k: int) -> int:
        v = 0
        for _ in range(k):
            v = (v << 1) | self.bit()
        return v

    def byte(self) -> int:
        v = self.d[self.p]
        self.p += 1
        return v


def _length(r: _Bits) -> int:
    for n in (2, 3, 4, 5):
        if r.bit():
            return n
    if r.bit():
        return r.bits(3) + 6
    return r.byte() + 14


def decode(d: bytes, p: int) -> tuple[bytes, int]:
    """`p` 에서 블록 하나를 푼다 → (출력, 스트림이 끝난 오프셋). 청크가 이어지면 따라간다."""
    out = bytearray()
    while True:
        r = _Bits(d, p + 2)  # LE16 길이 헤더는 안 쓴다(디컴프레서도 건너뛴다)
        r.buf = (d[r.p] << 8) | d[r.p + 1]  # 게임은 BE16 으로 읽고 아래 8비트만 쓴다
        r.p += 2
        r.n = 8
        while True:
            if r.bit() == 0:
                out.append(r.byte())
                continue
            if r.bit() == 0:
                dist = r.byte()
                n = _length(r)
            else:
                dist = (r.bits(5) << 8) | r.byte()
                if dist == 0:
                    break
                if dist == 1:
                    long_ = r.bit()
                    n = r.bits(4)
                    if long_:
                        n = (n << 8) | r.byte()
                    out += bytes([r.byte()]) * (n + 14)
                    continue
                n = _length(r)
            if dist == 0 or dist > len(out):
                raise ValueError(f"거리 {dist} 가 출력({len(out)})을 넘는다 @{r.p:#x}")
            for _ in range(n):
                out.append(out[-dist])
        more = r.byte()
        p = r.p
        if more == 0:
            return bytes(out), p


def block_span(d: bytes, p: int) -> int:
    """헤더가 말하는 블록 길이(짝수 정렬). 색인 오프셋은 이걸로 이어진다."""
    n = struct.unpack("<H", d[p : p + 2])[0] + 1
    return n + (n & 1)


class _Writer:
    """플래그 그룹(첫 8비트, 이후 16비트)마다 [플래그][그 그룹의 데이터] 순으로 내보낸다.

    ⚠ 데이터 바이트는 **그 앞의 비트가 속한 그룹** 것이다 — 디코더는 비트를 읽은 직후 커서에서
    바이트를 읽고, 새 플래그 워드는 **다음 비트가 필요할 때** 읽는다. 그래서 그룹이 찼어도
    다음 비트가 올 때까지 내보내기를 미룬다.
    """

    def __init__(self):
        self.out = bytearray()
        self.flags: list[int] = []
        self.pending = bytearray()
        self.cap = 8

    def bit(self, b: int) -> None:
        if len(self.flags) == self.cap:
            self.flush()
        self.flags.append(b)

    def bits(self, v: int, k: int) -> None:
        for i in range(k - 1, -1, -1):
            self.bit((v >> i) & 1)

    def byte(self, v: int) -> None:
        self.pending.append(v)

    def flush(self) -> None:
        if not self.flags and not self.pending:
            return
        v = 0
        for i, b in enumerate(self.flags):
            v |= b << i
        if self.cap == 8:
            self.out += bytes([0, v])  # 게임이 BE16 으로 읽어 아래 바이트만 쓴다
        else:
            self.out += struct.pack("<H", v)
        self.out += self.pending
        self.flags, self.pending, self.cap = [], bytearray(), 16


def _find_match(data: bytes, i: int, heads: dict) -> tuple[int, int]:
    best_len, best_dist = 0, 0
    key = data[i : i + 3]
    if len(key) < 3:
        return 0, 0
    for j in reversed(heads.get(key, ())):
        dist = i - j
        if dist > MAX_DIST:
            break
        n = 0
        lim = min(MAX_LEN, len(data) - i)
        while n < lim and data[j + n] == data[i + n]:
            n += 1
        if n > best_len:
            best_len, best_dist = n, dist
            if n >= MAX_LEN:
                break
    return best_len, best_dist


def encode(data: bytes) -> bytes:
    """`decode(encode(x)) == x`. 탐욕 매칭 + 14 이상 동일 런은 RLE."""
    w = _Writer()
    heads: dict[bytes, list[int]] = {}
    i, n = 0, len(data)
    while i < n:
        # RLE
        run = 1
        while i + run < n and run < RLE_MAX and data[i + run] == data[i]:
            run += 1
        if run >= 16:
            w.bit(1)
            w.bit(1)
            w.bits(0, 5)
            w.byte(1)
            k = run - 14
            if k > 0xF:
                w.bit(1)
                w.bits(k >> 8, 4)
                w.byte(k & 0xFF)
            else:
                w.bit(0)
                w.bits(k, 4)
            w.byte(data[i])
            step = run
        else:
            m, dist = _find_match(data, i, heads)
            if m >= 2 and not (m == 2 and dist >= 256):
                w.bit(1)
                if dist < 256:
                    w.bit(0)
                    w.byte(dist)
                else:
                    w.bit(1)
                    w.bits(dist >> 8, 5)
                    w.byte(dist & 0xFF)
                if m <= 5:
                    w.bits(1, m - 1)  # 0…01 (m-2 개의 0 뒤 1)
                elif m <= 13:
                    w.bits(0, 4)
                    w.bit(1)
                    w.bits(m - 6, 3)
                else:
                    w.bits(0, 5)
                    w.byte(m - 14)
                step = m
            else:
                w.bit(0)
                w.byte(data[i])
                step = 1
        for j in range(i, min(i + step, n - 2)):
            heads.setdefault(data[j : j + 3], []).append(j)
        i += step
    # 끝: 거리 0 + more=0
    w.bit(1)
    w.bit(1)
    w.bits(0, 5)
    w.byte(0)
    w.flush()
    w.out.append(0)
    body = bytes(w.out)
    size = len(body) + 2
    return struct.pack("<H", size - 1) + body


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("encode", "decode"):
        raise SystemExit("쓰기: lz.py encode|decode <in> <out>   (decode 는 in 의 0 에서 한 블록)")
    src = Path(sys.argv[2]).read_bytes()
    if sys.argv[1] == "encode":
        out = encode(src)
    else:
        out, used = decode(src, 0)
        print(f"{used}B → {len(out)}B")
    Path(sys.argv[3]).write_bytes(out)
