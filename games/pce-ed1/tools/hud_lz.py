"""HUD 글자판 압축(LZSS 변종) — 디코더·인코더. `hud_plate.py` 가 쓴다.

게임 쪽 해제기는 `$479C`(초기화) · `$479F`(한 바이트) · 뱅크 0x68 에 있다(2026-09-26 실측,
devlog 09-26). 텍스트 LZ(`lz.py`)와 **다른 코덱**이다 — 09-15 의 가설 ⑵(텍스트 LZ 로 전 트랙
풀기)가 빈손이었던 이유가 이것이다.

    링 256B($3F00~) · 처음엔 전부 0 · 쓰기 포인터 0xEF(= 256 − 17)
    플래그 바이트 MSB 부터: 1 = 날바이트 1개
                            0 = 오프셋 1B(링 안 절대 위치) + 길이 4비트(플래그 흐름에서) → 2~17B
    ⚠ 길이 4비트는 **오프셋 바이트 뒤에서** 플래그 흐름을 이어 읽는다 — 그 사이에 플래그가
      바닥나면 새 플래그 바이트는 오프셋 바이트 **다음** 자리에 온다.

모드 8(`$4644`)은 이 흐름을 **32B 씩 평면 순서**(p0 8B · p1 8B · p2 8B · p3 8B)로 받아
VRAM 타일 배치(p0/p1 행 교차 16B + p2/p3 행 교차 16B)로 바꿔 쓴다 — `planar_to_vram`.
"""

RING = 256
RING_INIT = 0xEF
MIN_LEN, MAX_LEN = 2, 17


def decode(src, pos, nbytes, ptr=RING_INIT):
    """(풀린 바이트, 끝 위치)."""
    ring = bytearray(RING)
    out = bytearray()
    flags = nb = 0

    def bit():
        nonlocal flags, nb, pos
        if nb == 0:
            flags, nb = src[pos], 8
            pos += 1
        b = flags >> 7
        flags = (flags << 1) & 0xFF
        nb -= 1
        return b

    while len(out) < nbytes:
        if bit():
            c = src[pos]
            pos += 1
            ring[ptr] = c
            ptr = (ptr + 1) & 0xFF
            out.append(c)
        else:
            off = src[pos]
            pos += 1
            n = 0
            for _ in range(4):
                n = (n << 1) | bit()
            for _ in range(n + MIN_LEN):
                c = ring[off]
                off = (off + 1) & 0xFF
                ring[ptr] = c
                ptr = (ptr + 1) & 0xFF
                out.append(c)
    return bytes(out[:nbytes]), pos


def _match(ring, ptr, data, i):
    """링에서 data[i:] 와 가장 길게 맞는 (오프셋, 길이) — 복사 중 링이 바뀌는 것까지 흉내 낸다."""
    best_off, best_len = 0, 0
    limit = min(MAX_LEN, len(data) - i)
    for off in range(RING):
        r = bytearray(ring)
        p, o, n = ptr, off, 0
        while n < limit:
            c = r[o]
            if c != data[i + n]:
                break
            r[p] = c
            p = (p + 1) & 0xFF
            o = (o + 1) & 0xFF
            n += 1
        if n > best_len:
            best_off, best_len = off, n
            if n == limit:
                break
    return best_off, best_len


def encode(data, ptr=RING_INIT):
    """탐욕 + 한 칸 미루기(lazy). 게임 해제기와 같은 비트 순서로 낸다."""
    ring = bytearray(RING)
    out = bytearray()
    slot = None  # 지금 채우는 플래그 바이트의 out 위치
    nb = 0

    def put_bit(b):
        nonlocal slot, nb
        if nb == 0:
            slot, nb = len(out), 8
            out.append(0)
        if b:
            out[slot] |= 1 << (nb - 1)
        nb -= 1

    def feed(c):
        nonlocal ptr
        ring[ptr] = c
        ptr = (ptr + 1) & 0xFF

    i = 0
    while i < len(data):
        off, n = _match(ring, ptr, data, i)
        if n >= MIN_LEN and i + 1 < len(data):
            # lazy: 한 바이트 뒤에서 더 길게 맞으면 지금은 날바이트로 낸다
            r2 = bytearray(ring)
            r2[ptr] = data[i]
            _o2, n2 = _match(r2, (ptr + 1) & 0xFF, data, i + 1)
            if n2 > n + 1:
                n = 0
        if n >= MIN_LEN:
            put_bit(0)
            out.append(off)
            for k in range(3, -1, -1):
                put_bit(((n - MIN_LEN) >> k) & 1)
            for _ in range(n):
                feed(ring[off])
                off = (off + 1) & 0xFF
            i += n
        else:
            put_bit(1)
            out.append(data[i])
            feed(data[i])
            i += 1
    return bytes(out)


def planar_to_vram(t):
    """32B 평면 순서 → VRAM 타일 배치."""
    o = bytearray(32)
    for y in range(8):
        o[2 * y], o[2 * y + 1] = t[y], t[8 + y]
        o[16 + 2 * y], o[17 + 2 * y] = t[16 + y], t[24 + y]
    return bytes(o)


def vram_to_planar(v):
    o = bytearray(32)
    for y in range(8):
        o[y], o[8 + y] = v[2 * y], v[2 * y + 1]
        o[16 + y], o[24 + y] = v[16 + 2 * y], v[17 + 2 * y]
    return bytes(o)
