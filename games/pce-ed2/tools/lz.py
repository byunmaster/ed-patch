"""ED2 대본 스트림 LZ — 게임 디코더(뱅크 0x68 `$5776~$57F0`, 입력 포인터 ZP `$31/$32`)를 그대로 옮겼다.

역공학 근거(2026-10-12, emucap — docs/status.md 「텍스트 엔진 조사」):

    플래그 바이트 = 8비트씩 MSB 부터 — 1 = 리터럴 1B, 0 = 링 되참조
    되참조 = 1B 링 절대 인덱스 + **길이 4비트(+2 → 2~17)**
    길이 4비트는 플래그가 아니라 **본 바이트열의 니블 쌍**에서 온다 — 첫 번째 되참조가 바이트 하나를
    통째로 읽어 상위 니블을 쓰고, 다음 되참조는 그 바이트의 하위 니블을 쓴다(그 사이 바이트는 안 읽는다)
    링 = 256B(뱅크 0x87 `$E000`), 0 으로 초기화, 쓰기 인덱스는 0xEF 에서 시작
    초기화(`$5796`)는 링 비우기 · 쓰기 인덱스 · 플래그 카운터 · 니블 토글 — 포인터는 호출자가 준다

ED1 의 `lz.py` 와 다른 점은 **길이를 읽는 자리**뿐이다(ED1 = 플래그 스트림 4비트).
출력 길이는 스트림에 없다 — 게임은 한 바이트씩 당긴다(줄 끝 `00` 을 세며 목표 줄까지).

**512B 링 변형(642 전용, 마스터 10-22 「3은 일단 a」)**: 덩이 첫 바이트가 `7C`(표식 — 256B 스트림은 첫 토큰이 늘 리터럴이라 최상위 비트가 1 이어서 겹치지 않는다)이면
뒤는 512B 링(뱅크 0x87 `$EE00~$EFFF`) 스트림이다. 같은 플래그·니블 포장인데 되참조 니블 4비트를 **길이 3비트(+2 → 2~9) + 링 인덱스 9번째 비트**로 쪼갠다
(바이트로 8비트 + 니블 1비트 = 9비트 인덱스). 쓰기 인덱스는 같은 `0xEF` 에서 시작하고 링은 비우지 않는다(인코더가 쓴 적 없는 칸을 가리키지 않는다).
디코더 변형은 `lzring.py`(프로그램 쪽 루틴).

검증: 에뮬 체크포인트 다섯(링 256B · 쓰기 인덱스 · 포인터 · 니블 토글)이 이 디코더 상태와 바이트까지 일치
(`stream.py` 의 ANCHOR — 게이트가 원본에서 다시 잰다).
"""

RING = 256
WIDX0 = 0xEF
MIN_LEN = 2
MAX_LEN = 17
RING2 = 512  # 512B 링 변형
MAX_LEN2 = 9  # 길이 3비트 + 2
MARK2 = 0x7C  # 덩이 첫 바이트 표식 — 최상위 비트가 0 이라 정상 스트림(첫 토큰이 리터럴 → 최상위 1)과 겹치지 않고, 원판 80개 패키지의 메시지 표가 가리키는 어느 덩이도 이 값으로 시작하지 않는다(10-22 전수)


def walk(src: bytes, pos: int, auto512: bool = False):
    """출력 바이트마다 (바이트, 입력 위치, 쓰기 인덱스, 링)을 낸다 — 링은 호출자가 바꾸지 말 것(복사해 쓴다).
    `auto512` 이고 첫 바이트가 표식(`7C`)이면 512B 링 변형으로 푼다(표식 1B 는 입력 위치에 포함)."""
    if auto512 and src[pos] == MARK2:
        yield from _walk512(src, pos + 1)
        return
    ring = bytearray(RING)
    widx = WIDX0
    flags = 0
    cnt = 0
    nib = None
    while True:
        if cnt == 0:
            flags = src[pos]
            pos += 1
            cnt = 8
        bit = (flags >> 7) & 1
        flags = (flags << 1) & 0xFF
        cnt -= 1
        if bit:
            b = src[pos]
            pos += 1
            ring[widx & 0xFF] = b
            widx += 1
            yield b, pos, widx & 0xFF, ring
        else:
            ridx = src[pos]
            pos += 1
            if nib is None:
                v = src[pos]
                pos += 1
                n, nib = v >> 4, v & 15
            else:
                n, nib = nib, None
            for k in range(n + MIN_LEN):
                b = ring[(ridx + k) & 0xFF]
                ring[widx & 0xFF] = b
                widx += 1
                yield b, pos, widx & 0xFF, ring


def _walk512(src: bytes, pos: int):
    """512B 링 변형 — 표식 뒤부터. 되참조 니블 = 길이(하위 3비트, +2) | 링 인덱스 9번째 비트(상위 1비트)."""
    ring = bytearray(RING2)
    widx = WIDX0
    flags = 0
    cnt = 0
    nib = None
    while True:
        if cnt == 0:
            flags = src[pos]
            pos += 1
            cnt = 8
        bit = (flags >> 7) & 1
        flags = (flags << 1) & 0xFF
        cnt -= 1
        if bit:
            b = src[pos]
            pos += 1
            ring[widx % RING2] = b
            widx += 1
            yield b, pos, widx % RING2, ring
        else:
            ridx = src[pos]
            pos += 1
            if nib is None:
                v = src[pos]
                pos += 1
                n, nib = v >> 4, v & 15
            else:
                n, nib = nib, None
            ridx |= (n >> 3) << 8
            for k in range((n & 7) + MIN_LEN):
                b = ring[(ridx + k) % RING2]
                ring[widx % RING2] = b
                widx += 1
                yield b, pos, widx % RING2, ring


def decode(src: bytes, pos: int, out_len: int, auto512: bool = False) -> tuple[bytes, int]:
    """(출력, 소비한 입력 끝 위치). 게임처럼 필요한 만큼만 푼다."""
    out = bytearray()
    for b, p, _w, _r in walk(src, pos, auto512):
        out.append(b)
        pos = p
        if len(out) >= out_len:
            break
    return bytes(out), pos


def encode(data: bytes) -> bytes:
    """탐욕 인코더 — 게임 디코더와 같은 링 상태를 굴리며 최장 일치를 고른다(산출물만 결정적이면 된다).

    ⚠ 오버랩(참조가 쓰기 커서를 넘어 자기 출력을 다시 읽음)은 디코더가 한 바이트마다 링에 쓰므로
    시뮬레이션으로 길이를 잰다. 플래그 바이트·니블 바이트는 **필요한 순간의 위치**에 자리를 잡고 나중에 채운다.
    """
    out = bytearray()
    ring = bytearray(RING)
    widx = WIDX0
    flag_pos = -1
    flag_cnt = 0
    nib_pos = -1  # 하위 니블이 비어 있는 니블 바이트(없으면 -1)
    i, n = 0, len(data)
    while i < n:
        best_len, best_idx = 0, 0
        max_len = min(MAX_LEN, n - i)
        if max_len >= MIN_LEN:
            for ridx in range(RING):
                sim = {}
                ln = 0
                while ln < max_len:
                    p = (ridx + ln) & 0xFF
                    b = sim.get(p, ring[p])
                    if b != data[i + ln]:
                        break
                    sim[(widx + ln) & 0xFF] = b
                    ln += 1
                if ln > best_len:
                    best_len, best_idx = ln, ridx
                    if ln == max_len:
                        break
        if flag_cnt == 0:
            flag_pos = len(out)
            out.append(0)
            flag_cnt = 8
        flag_cnt -= 1
        if best_len >= MIN_LEN:
            out.append(best_idx)
            v = best_len - MIN_LEN
            if nib_pos < 0:
                nib_pos = len(out)
                out.append(v << 4)
            else:
                out[nib_pos] |= v
                nib_pos = -1
            for k in range(best_len):
                b = ring[(best_idx + k) & 0xFF]
                ring[widx & 0xFF] = b
                widx += 1
            i += best_len
        else:
            out[flag_pos] |= 1 << flag_cnt
            out.append(data[i])
            ring[widx & 0xFF] = data[i]
            widx += 1
            i += 1
    return bytes(out)


def _emit(data: bytes, toks: list) -> bytes:
    """토큰열 → 스트림(플래그 비트 · 니블 쌍 포장은 탐욕 인코더와 같다)."""
    out = bytearray()
    flag_pos = -1
    flag_cnt = 0
    nib_pos = -1
    for t in toks:
        if flag_cnt == 0:
            flag_pos = len(out)
            out.append(0)
            flag_cnt = 8
        flag_cnt -= 1
        if t[0] == "M":
            _k, ridx, ln = t
            out.append(ridx)
            v = ln - MIN_LEN
            if nib_pos < 0:
                nib_pos = len(out)
                out.append(v << 4)
            else:
                out[nib_pos] |= v
                nib_pos = -1
        else:
            out[flag_pos] |= 1 << flag_cnt
            out.append(t[1])
    return bytes(out)


def encode_opt(data: bytes) -> bytes:
    """최적 파싱(동적 계획) 인코더 — 링 창 256B · 길이 2~17 · 리터럴 9비트 / 되참조 13비트로 비용을 매겨 가장 짧은 토큰열을 고른다.
    링은 출력의 마지막 256바이트와 같으므로(쓰기 인덱스 0xEF 시작) 거리 d(1~256)의 되참조는 `data[i-d+k]` 와 비교하면 된다
    (겹침 포함). 결과는 `decode` 로 원문과 같음을 호출자가 검산한다(`repack` 이 그렇게 한다)."""
    n = len(data)
    INF = 1 << 60
    cost = [INF] * (n + 1)
    cost[n] = 0
    choice: list = [None] * (n + 1)
    last: dict[bytes, list[int]] = {}  # 2바이트 → 최근 위치들(앞에서부터 쌓는다)
    cands: list[list[tuple[int, int]]] = [[] for _ in range(n)]  # i → [(거리, 최대 길이)]
    for i in range(n):
        if i + 1 < n:
            key = data[i : i + 2]
            lst = last.setdefault(key, [])
            best = []
            for j in reversed(lst):
                d = i - j
                if d > RING:
                    break
                ln = 2
                m = min(MAX_LEN, n - i)
                while ln < m and data[i + ln] == data[j + ln]:
                    ln += 1
                best.append((d, ln))
            cands[i] = best
            lst.append(i)
    for i in range(n - 1, -1, -1):
        c, ch = cost[i + 1] + 9, ("L", data[i])
        for d, ln in cands[i]:
            for l in range(MIN_LEN, ln + 1):
                v = cost[i + l] + 13
                if v < c:
                    c, ch = v, ("M", d, l)
        cost[i], choice[i] = c, ch
    toks = []
    i = 0
    while i < n:
        ch = choice[i]
        if ch[0] == "L":
            toks.append(ch)
            i += 1
        else:
            _k, d, l = ch
            toks.append(("M", ((WIDX0 + i) - d) & 0xFF, l))
            i += l
    return _emit(data, toks)


def encode_opt512(data: bytes) -> bytes:
    """512B 링 변형 최적 파싱 — 표식(`7C`) + 스트림. 창 512B · 길이 2~9 · 리터럴 9비트 / 되참조 13비트(256B 판과 같다 — 길이 비트를 줄여 인덱스 비트를 얻었다).
    링은 비우지 않으므로 거리 d(1~512)는 이 덩이 안에서 이미 쓴 바이트만 가리킨다(`d <= i`)."""
    n = len(data)
    INF = 1 << 60
    cost = [INF] * (n + 1)
    cost[n] = 0
    choice: list = [None] * (n + 1)
    last: dict[bytes, list[int]] = {}
    cands: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    for i in range(n):
        if i + 1 < n:
            key = data[i : i + 2]
            lst = last.setdefault(key, [])
            best = []
            for j in reversed(lst):
                d = i - j
                if d > RING2:
                    break
                ln = 2
                m = min(MAX_LEN2, n - i)
                while ln < m and data[i + ln] == data[j + ln]:
                    ln += 1
                best.append((d, ln))
            cands[i] = best
            lst.append(i)
    for i in range(n - 1, -1, -1):
        c, ch = cost[i + 1] + 9, ("L", data[i])
        for d, ln in cands[i]:
            for l in range(MIN_LEN, ln + 1):
                v = cost[i + l] + 13
                if v < c:
                    c, ch = v, ("M", d, l)
        cost[i], choice[i] = c, ch
    toks = []
    i = 0
    while i < n:
        ch = choice[i]
        if ch[0] == "L":
            toks.append(ch)
            i += 1
        else:
            _k, d, l = ch
            toks.append(("M", ((WIDX0 + i) - d) % RING2, l))
            i += l
    return bytes([MARK2]) + _emit512(toks)


def _emit512(toks: list) -> bytes:
    """토큰열 → 스트림. 니블 = (길이-2) | 인덱스 9번째 비트 << 3, 포장은 256B 판과 같다."""
    out = bytearray()
    flag_pos = -1
    flag_cnt = 0
    nib_pos = -1
    for t in toks:
        if flag_cnt == 0:
            flag_pos = len(out)
            out.append(0)
            flag_cnt = 8
        flag_cnt -= 1
        if t[0] == "M":
            _k, ridx, ln = t
            out.append(ridx & 0xFF)
            v = (ln - MIN_LEN) | (ridx >> 8) << 3
            if nib_pos < 0:
                nib_pos = len(out)
                out.append(v << 4)
            else:
                out[nib_pos] |= v
                nib_pos = -1
        else:
            out[flag_pos] |= 1 << flag_cnt
            out.append(t[1])
    return bytes(out)
