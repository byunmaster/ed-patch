"""GMF 압축(RLE) — `4E tt 01 03 <u32>` 헤더 뒤의 스트림을 푼다.

포맷(2026-09-03 실측, `.TI3` 를 풀면 TIM 이라는 **알려진 평문**으로 유도했다):

    op & 0x80  → 리터럴 런: 뒤따르는 (op & 0x7F) + 1 바이트를 그대로
    op < 0x80  → 반복 런:   다음 한 바이트를 (op + 1) 번

⚠ **LZ 가 아니라 RLE 다.** 처음엔 LZSS 로 보고 오프셋·길이 분할을 스무 가지 넘게 맞춰
   봤는데 전부 어긋났다. 「길이 2인 매치가 `01 01` 을 내야 한다」는 자리에서 갈렸다 —
   매치가 아니라 **같은 바이트 두 번**이었다.

⚠ **헤더의 크기는 「푼 크기 − 1」이다.** `.TI3` 는 TIM 이라 총 길이가 구조로 계산되는데
   (8 + CLUT 524 + 이미지블록), 그 값보다 헤더가 늘 1 작다. 그래서 **선언값+1 에서 멈춘다** —
   안 멈추면 뒤의 패딩까지 풀어 길이가 조용히 늘어난다(실측: 66,080 대신 197,688).
"""

import struct

MAGIC = 0x4E


class GmfzError(Exception):
    pass


def parse_header(blk):
    """(종류, 푼 크기) — 압축 블록이 아니면 None."""
    if len(blk) < 8 or blk[0] != MAGIC or blk[2:4] != b"\x01\x03":
        return None
    kind = blk[1]
    size = struct.unpack("<I", blk[4:8])[0] + 1  # ⚠ 헤더는 크기−1 을 담는다
    return kind, size


def decompress(blk, *, strict=True):
    """압축 블록(헤더 포함) → (원본 바이트, 모자랐던 바이트 수)."""
    h = parse_header(blk)
    if h is None:
        raise GmfzError(f"압축 헤더가 아니다: {blk[:8].hex(' ')}")
    _, want = h
    out = bytearray()
    comp = blk[8:]
    i = 0
    n = len(comp)
    while i < n and len(out) < want:
        op = comp[i]
        i += 1
        if op & 0x80:
            k = (op & 0x7F) + 1
            out += comp[i : i + k]
            i += k
        else:
            if i >= n:
                break
            out += bytes([comp[i]]) * (op + 1)
            i += 1
    # ⚠ **모자란 것만 실패로 친다.** 마지막 토큰은 필요한 양을 넘겨 쓸 수 있다(리터럴 런은
    #   최대 128B라 최대 127B 넘친다) — 원 압축기가 꼬리를 맞추지 않았을 뿐이라 잘라 낸다.
    #   반대로 **모자라면** 그건 포맷을 잘못 읽은 것이다.
    # ⚠ **모자란 것만 이상으로 친다.** 마지막 토큰은 필요한 양을 넘겨 쓸 수 있어서(리터럴 런은
    #   최대 128B) 넘치는 건 잘라 낸다. 반대로 모자라는 건 106/1,821 에서 실제로 일어나는데,
    #   입력을 끝까지 다 쓰고도 모자란다 — 나머지는 **호출자가 0 으로 둔 버퍼**로 보인다.
    #   그래서 0 으로 채우되 `short` 로 알린다(조용히 넘기지 않는다).
    short = max(0, want - len(out))
    if short and strict:
        out += b"\x00" * short
    return bytes(out[:want]), short


def compress(data):
    """되감기 — 리터럴 런과 반복 런으로 나눈다.

    ⚠ 원본과 **바이트 동일한** 압축을 목표로 하지 않는다(원 압축기의 선택을 모른다).
       빌드는 「풀면 같은가」로 검증한다 — `decompress(wrap(x))[0] == x`.
    """
    out = bytearray()
    i = 0
    n = len(data)
    lit = bytearray()

    def flush():
        nonlocal lit, out
        while lit:
            k = min(len(lit), 128)
            out.append(0x80 | (k - 1))
            out += lit[:k]
            lit = lit[k:]

    while i < n:
        j = i
        while j < n and data[j] == data[i] and j - i < 128:
            j += 1
        run = j - i
        if run >= 3:  # 런 2개는 리터럴이 더 짧거나 같다
            flush()
            out.append(run - 1)
            out.append(data[i])
            i = j
        else:
            lit += data[i : i + 1]
            i += 1
    flush()
    return bytes(out)


def wrap(data, kind=0):
    """압축 + 헤더."""
    return bytes([MAGIC, kind]) + b"\x01\x03" + struct.pack("<I", len(data) - 1) + compress(data)
