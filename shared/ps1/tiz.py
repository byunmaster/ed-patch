"""ED4 그림·맵 압축(`.TIZ` `.MAZ` `.MPZ`) — ED3 의 GMF RLE(`gmf_rle.py`)와 **다른 포맷**이다.

헤더 `kind(1B: 1|2) 03 size(u32=푼 크기) | 사전 64×u16 | 스트림`  (2026-10-24 해독 — 디스크의 8,867개 전부 풀린다)

- 사전 항목 u16: 상위 4비트 = 길이 n, 하위 12비트 = 블록 안 시작 오프셋. 사전 바이트열은 표 바로 뒤(134~)에 이어 붙고
  항목 k 의 오프셋은 앞 항목 오프셋 + 앞 항목 길이다. 쓰지 않는 항목은 0.
- 🔴 **사전이 비어 있으면(전부 0) 스트림은 134(=6+128)부터다.** 「사전 항목의 최대 끝」으로 시작을 잡으면 0 이 나와 틀린다.
- 스트림 op: `00~3F` 한 바이트를 (op+1)번 · `40~7F` **두 바이트 쌍**을 (op&3F)+1번 · `80~BF` 리터럴 (op&3F)+1바이트 ·
  `C0~FF` 사전 항목 (op&3F). 푼 크기에서 정확히 멈춘다(마지막 토큰이 넘치면 안 된다 — 넘치면 포맷을 잘못 읽은 것이다).
- kind 1·2 는 같은 해독기로 풀린다(차이는 미확인).

압축기는 없다 — 재삽입 몫이다(리터럴만으로 담아도 원 크기를 못 맞추면 쓸 수 없다는 점은 호출자가 본다).
"""

import struct

HEAD = 6
DICT_N = 64
STREAM_MIN = HEAD + DICT_N * 2  # 134


class TizError(Exception):
    pass


def parse_header(blk):
    """(kind, 푼 크기) — 이 포맷이 아니면 None."""
    if len(blk) < STREAM_MIN or blk[0] not in (1, 2) or blk[1] != 3:
        return None
    return blk[0], struct.unpack("<I", blk[2:6])[0]


def decompress(blk):
    """압축 블록(헤더 포함) → 푼 바이트열. 틀리게 읽히면 `TizError`(입력 부족·넘침·남음)."""
    h = parse_header(blk)
    if h is None:
        raise TizError(f"TIZ 헤더가 아니다: {bytes(blk[:8]).hex(' ')}")
    _, size = h
    ent = [struct.unpack_from("<H", blk, HEAD + 2 * i)[0] for i in range(DICT_N)]
    end = max([STREAM_MIN] + [(e & 0xFFF) + (e >> 12) for e in ent])
    dic = [bytes(blk[(e & 0xFFF) : (e & 0xFFF) + (e >> 12)]) for e in ent]
    i, n = end, len(blk)
    out = bytearray()
    while len(out) < size:
        if i >= n:
            raise TizError(f"입력이 모자란다 (푼 {len(out)}/{size})")
        op = blk[i]
        i += 1
        k = (op & 0x3F) + 1
        if op < 0x40:
            out += bytes([blk[i]]) * k
            i += 1
        elif op < 0x80:
            out += bytes(blk[i : i + 2]) * k
            i += 2
        elif op < 0xC0:
            out += blk[i : i + k]
            i += k
        else:
            out += dic[op & 0x3F]
    if len(out) != size:
        raise TizError(f"푼 크기가 선언과 다르다 {len(out)} (선언 {size})")
    if i != n:
        raise TizError(f"입력이 {n - i}B 남았다")
    return bytes(out)
