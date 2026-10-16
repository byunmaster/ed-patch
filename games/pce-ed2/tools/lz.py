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

검증: 에뮬 체크포인트 다섯(링 256B · 쓰기 인덱스 · 포인터 · 니블 토글)이 이 디코더 상태와 바이트까지 일치
(`stream.py` 의 ANCHOR — 게이트가 원본에서 다시 잰다).
"""

RING = 256
WIDX0 = 0xEF
MIN_LEN = 2
MAX_LEN = 17


def walk(src: bytes, pos: int):
    """출력 바이트마다 (바이트, 입력 위치, 쓰기 인덱스, 링)을 낸다 — 링은 호출자가 바꾸지 말 것(복사해 쓴다)."""
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


def decode(src: bytes, pos: int, out_len: int) -> tuple[bytes, int]:
    """(출력, 소비한 입력 끝 위치). 게임처럼 필요한 만큼만 푼다."""
    out = bytearray()
    for b, p, _w, _r in walk(src, pos):
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
