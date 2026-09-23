"""시나리오 컨테이너의 LZ 코덱 — 게임 로더(오버레이 $479C, 모드 6)를 그대로 옮겼다.

역공학 근거(2026-09-05, emucap 으로 $6E55 의 쓰기를 잡아 되짚었다 — docs/status.md 3절):

    스트림 = 헤더 1B (0 = 모드 6 그대로) + 비트 플래그가 섞인 바이트열
    플래그 비트는 MSB 부터 1비트씩 소비 — 1 = 리터럴 1B, 0 = 되참조
    되참조 = 1B **링 절대 인덱스** + 4비트 길이(+2 → 2~17)
    링 = 256B 이력 버퍼(RAM $3F00~$3FFF). 0 으로 초기화, 쓰기 인덱스는 **0xEF** 에서 시작
    출력 길이는 스트림에 없다 — 디렉터리 항목이 든다(containers.py)

⚠ 되참조는 상대 거리가 아니라 링 안의 절대 위치다. 링 초기값이 0 이라 「아직 안 쓴 자리」를
가리키는 참조는 0 을 낸다 — 인코더도 그 규칙을 그대로 지켜야 게임이 같은 바이트를 낸다.
"""

RING = 256
WIDX0 = 0xEF
MIN_LEN = 2
MAX_LEN = 17
HEADER = b"\x00"


class _Bits:
    def __init__(self, src: bytes, pos: int = 0):
        self.src, self.pos, self.buf, self.cnt = src, pos, 0, 0

    def bit(self) -> int:
        if self.cnt == 0:
            self.buf = self.src[self.pos]
            self.pos += 1
            self.cnt = 8
        self.cnt -= 1
        return (self.buf >> self.cnt) & 1

    def byte(self) -> int:
        b = self.src[self.pos]
        self.pos += 1
        return b


def decode(src: bytes, out_len: int, *, with_header: bool = True) -> tuple[bytes, int]:
    """(출력, 소비한 입력 바이트 수). out_len 은 디렉터리의 길이."""
    pos = 0
    if with_header:
        if src[0] != 0:
            raise ValueError(f"모르는 헤더 {src[0]:#04x} — 모드 6 만 안다")
        pos = 1
    r = _Bits(src, pos)
    ring = bytearray(RING)
    widx = WIDX0
    out = bytearray()
    while len(out) < out_len:
        if r.bit():
            b = r.byte()
            out.append(b)
            ring[widx & 0xFF] = b
            widx += 1
        else:
            ridx = r.byte()
            n = 0
            for _ in range(4):
                n = (n << 1) | r.bit()
            n += MIN_LEN
            for k in range(n):
                b = ring[(ridx + k) & 0xFF]
                out.append(b)
                ring[widx & 0xFF] = b
                widx += 1
                if len(out) >= out_len:
                    break
    return bytes(out), r.pos


class _BitWriter:
    """플래그 비트와 바이트가 한 스트림에 섞인다 — 플래그 바이트 자리를 비워 두고 채운다."""

    def __init__(self):
        self.out = bytearray()
        self.flag_pos = -1
        self.cnt = 0

    def bit(self, v: int) -> None:
        if self.cnt == 0:
            self.flag_pos = len(self.out)
            self.out.append(0)
            self.cnt = 8
        self.cnt -= 1
        if v:
            self.out[self.flag_pos] |= 1 << self.cnt

    def byte(self, b: int) -> None:
        self.out.append(b & 0xFF)


def encode(data: bytes, *, with_header: bool = True) -> bytes:
    """탐욕 인코더. 게임 디코더와 **같은 링 상태**를 굴리며 최장 일치를 고른다.

    링 참조는 「지금 링에 있는 바이트」기준이라 소스 오프셋이 아니라 링 인덱스를 찾는다.
    일치 길이가 2 면 2B(인덱스+플래그 몫) 로 리터럴 2B 와 같아 이득이 없지만 플래그 비트가
    1비트 줄어드니 쓴다(게임 인코더가 어떻게 했는지는 모른다 — 우리 산출물만 결정적이면 된다).
    """
    w = _BitWriter()
    ring = bytearray(RING)
    widx = WIDX0
    i = 0
    n = len(data)
    while i < n:
        best_len, best_idx = 0, 0
        # 링 절대 인덱스 256 곳을 전수 — 8KB 블록이라 충분히 싸다
        max_len = min(MAX_LEN, n - i)
        if max_len >= MIN_LEN:
            for ridx in range(RING):
                ln = 0
                # ⚠ 디코더는 한 바이트 낼 때마다 링에도 쓰므로, 참조가 쓰기 커서를 넘어 자기
                #   출력을 다시 읽을 수 있다(오버랩). 디코더 그대로 흉내 내 길이를 잰다.
                r2 = ring  # 읽기만 하되 오버랩은 아래서 시뮬레이션
                sim = {}
                while ln < max_len:
                    pos = (ridx + ln) & 0xFF
                    b = sim.get(pos, r2[pos])
                    if b != data[i + ln]:
                        break
                    sim[(widx + ln) & 0xFF] = b
                    ln += 1
                if ln > best_len:
                    best_len, best_idx = ln, ridx
                    if ln == max_len:
                        break
        if best_len >= MIN_LEN:
            w.bit(0)
            w.byte(best_idx)
            v = best_len - MIN_LEN
            for k in range(3, -1, -1):
                w.bit((v >> k) & 1)
            for k in range(best_len):
                b = ring[(best_idx + k) & 0xFF]
                ring[widx & 0xFF] = b
                widx += 1
            i += best_len
        else:
            w.bit(1)
            w.byte(data[i])
            ring[widx & 0xFF] = data[i]
            widx += 1
            i += 1
    return (HEADER if with_header else b"") + bytes(w.out)


def encode_optimal(data: bytes, *, with_header: bool = True) -> bytes:
    """최적 파싱 인코더 — 탐욕이 원래 슬롯을 몇 바이트 넘길 때만 쓴다(빌드의 대체 경로).

    링 내용은 파싱과 무관하게 **출력 이력**으로 정해진다(디코더가 낸 바이트를 차례로 링에 쓴다).
    그래서 자리 i 에서 링 칸 r 의 값 = 「i 이전에 그 칸에 마지막으로 쓰인 출력 바이트」(없으면 0) 이고,
    자리마다 최장 일치를 구해 두면 「리터럴 9비트 · 되참조 13비트(플래그 1 + 인덱스 8 + 길이 4)」
    의 최소 비트 경로를 뒤에서부터 DP 로 고를 수 있다. 짧은 일치는 긴 일치의 앞부분이라 따로 안 찾는다.
    ⚠ 탐욕보다 느리다(블록 하나에 수 초) — 그래서 기본값이 아니다.
    """
    n = len(data)

    def slot_val(t: int, pos: int) -> int:
        # 시각 t(출력 t 바이트를 낸 뒤) 링 칸 pos 의 값
        j = t - 1 - ((WIDX0 + t - 1 - pos) & 0xFF)
        return data[j] if j >= 0 else 0

    best = [(0, 0)] * n  # (최장 길이, 링 인덱스)
    for i in range(n):
        max_len = min(MAX_LEN, n - i)
        if max_len < MIN_LEN:
            continue
        bl, bi = 0, 0
        for ridx in range(RING):
            ln = 0
            while ln < max_len and slot_val(i + ln, (ridx + ln) & 0xFF) == data[i + ln]:
                ln += 1
            if ln > bl:
                bl, bi = ln, ridx
                if ln == max_len:
                    break
        best[i] = (bl, bi)
    INF = 1 << 60
    cost = [INF] * (n + 1)
    choice = [0] * (n + 1)
    cost[n] = 0
    for i in range(n - 1, -1, -1):
        cost[i], choice[i] = 9 + cost[i + 1], 1
        bl, _ = best[i]
        for ln in range(MIN_LEN, bl + 1):
            c = 13 + cost[i + ln]
            if c < cost[i]:
                cost[i], choice[i] = c, ln
    w = _BitWriter()
    i = 0
    while i < n:
        ln = choice[i]
        if ln == 1:
            w.bit(1)
            w.byte(data[i])
        else:
            w.bit(0)
            w.byte(best[i][1])
            v = ln - MIN_LEN
            for k in range(3, -1, -1):
                w.bit((v >> k) & 1)
        i += ln
    out = (HEADER if with_header else b"") + bytes(w.out)
    back, _ = decode(out, n, with_header=with_header)
    assert back == data, "최적 파싱 왕복 불일치"
    return out


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 4 or sys.argv[1] not in ("encode", "decode"):
        raise SystemExit(
            "쓰기: lz.py encode <in> <out> | lz.py decode <in> <out>  (decode 는 원 길이를 모른다 — containers.py 를 써라)"
        )
    from pathlib import Path

    raw = Path(sys.argv[2]).read_bytes()
    if sys.argv[1] == "encode":
        Path(sys.argv[3]).write_bytes(encode(raw))
    else:
        raise SystemExit("decode 는 출력 길이가 필요하다 — containers.py")
