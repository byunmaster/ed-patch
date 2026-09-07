"""ED3 리소스 뱅크의 LZSS — 해제기는 `/0.BIN` 의 `0x0604718C` 다.

`/SYSTEM/BATTLE.BIN` 은 **이름 붙은 리소스 뱅크**다 — `[BE32 항목크기][이름 NUL][스트림]`
이 58 개 이어진다(`menu.chr` · `status.spr` · `skill.spr` …). 스트림이 이 형식이다.

    [LE32 푼 길이] 뒤로 스트림
    플래그 바이트 하나가 뒤따르는 여덟 조각의 성격을 정한다(MSB 부터).
      1 → 리터럴 한 바이트
      0 → 매치: [링 위치 1B(절대 0~255)] + 길이
    🔴 **길이는 매치 둘이 바이트 하나를 나눠 쓴다** — 첫 매치가 길이 바이트를 읽어
      **상위 니블+2**를 쓰고, **하위 니블은 아껴 뒀다가 다음 매치가** 쓴다.
      리터럴이 사이에 끼어도 아껴 둔 니블은 살아 있다.
    링 버퍼 256B, 0 으로 시작, 쓰기 위치는 **0xEF** 부터.

⚠ 창이 256B 라 흔한 LZSS 인코더를 못 쓴다(오프셋이 상대 거리가 아니라 **절대 위치**다).
"""

import struct

RING = 256
START = 0xEF
MAXLEN = 17  # 니블 + 2


def decode(src, pos):
    """`(푼 bytes, 스트림 끝 오프셋)`."""
    n = struct.unpack_from("<I", src, pos)[0]
    p = pos + 4
    ring = bytearray(RING)
    rp = START
    out = bytearray()
    flags = nf = 0
    pend = None
    while len(out) < n:
        if nf == 0:
            flags = src[p]
            p += 1
            nf = 8
        bit = (flags >> 7) & 1
        flags = (flags << 1) & 0xFF
        nf -= 1
        if bit:
            c = src[p]
            p += 1
            out.append(c)
            ring[rp] = c
            rp = (rp + 1) & 0xFF
        else:
            where = src[p]
            p += 1
            if pend is None:
                lb = src[p]
                p += 1
                ln = (lb >> 4) + 2
                pend = lb & 0xF
            else:
                ln = pend + 2
                pend = None
            for i in range(ln):
                c = ring[(where + i) & 0xFF]
                out.append(c)
                ring[rp] = c
                rp = (rp + 1) & 0xFF
    return bytes(out), p


def _run(data, i, ring, rp, where):
    """`where` 에서 복사하면 몇 바이트가 맞나 — **링에 되쓰는 것까지** 흉내낸다."""
    r = bytearray(ring)
    w = rp
    n = 0
    while n < MAXLEN and i + n < len(data):
        c = r[(where + n) & 0xFF]
        if c != data[i + n]:
            break
        r[w] = c
        w = (w + 1) & 0xFF
        n += 1
    return n


def _best(data, i, ring, rp):
    bn = bw = 0
    for w in range(RING):
        if ring[w] != data[i]:
            continue
        n = _run(data, i, ring, rp, w)
        if n > bn:
            bn, bw = n, w
            if n == MAXLEN:
                break
    return bn, bw


def encode(data, lazy=True):
    """`data` → 스트림 bytes. 원본보다 작게 나오는 것을 확인하고 쓴다.

    ⓘ `lazy` 는 **게으른 매칭** — 한 칸 미뤄 더 길게 잡히면 리터럴로 흘린다.
      실측(`status.spr` 8,192B): 끄면 2,088B · 켜면 **2,076B**(원본 2,096B).
    """
    ring = bytearray(RING)
    rp = START
    out = bytearray(struct.pack("<I", len(data)))
    flagpos = flags = nf = 0
    pend_at = None
    i = 0
    while i < len(data):
        if nf == 0:
            flagpos = len(out)
            out.append(0)
            flags = 0
            nf = 8
        bn, bw = _best(data, i, ring, rp)
        if lazy and bn >= 2 and i + 1 < len(data):
            r2 = bytearray(ring)
            r2[rp] = data[i]
            n2, _ = _best(data, i + 1, r2, (rp + 1) & 0xFF)
            if n2 > bn:
                bn = 0
        if bn >= 2:
            flags = (flags << 1) & 0xFF
            out.append(bw)
            if pend_at is None:
                pend_at = len(out)
                out.append((bn - 2) << 4)
            else:
                out[pend_at] |= bn - 2
                pend_at = None
            for k in range(bn):
                c = ring[(bw + k) & 0xFF]
                ring[rp] = c
                rp = (rp + 1) & 0xFF
            i += bn
        else:
            flags = ((flags << 1) | 1) & 0xFF
            c = data[i]
            out.append(c)
            ring[rp] = c
            rp = (rp + 1) & 0xFF
            i += 1
        nf -= 1
        out[flagpos] = (flags << nf) & 0xFF
    return bytes(out)


def entries(bank):
    """`[(이름, 항목 오프셋, 항목 크기, 스트림 오프셋)]` — 뱅크를 훑는다."""
    out = []
    off = 0
    while off < len(bank) - 8:
        size = struct.unpack_from(">I", bank, off)[0]
        if size == 0 or size > len(bank) - off:
            break
        z = bank.find(b"\x00", off + 4)
        out.append((bank[off + 4 : z].decode("ascii"), off, size, z + 1))
        off += size
    return out
