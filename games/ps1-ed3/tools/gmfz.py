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
        elif op & 0x40:
            # 🔴 쌍 반복 — 다음 **두 바이트**를 (op & 0x3F) + 1 번 되풀이한다(10-24, 장 끝 띠 시트 `C_203` 에서 발견:
            #    `41 48 0e` → 48 0e 48 0e). 이걸 모르면 이 토큰 뒤가 통째로 밀려 「줄이 밀린 그림」·「짧게 풀림」이 된다.
            if i + 1 >= n:
                break
            out += comp[i : i + 2] * ((op & 0x3F) + 1)
            i += 2
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


def _tokens(data):
    """데이터 → 토큰 목록 — ("L", 바이트열) 리터럴 · ("R", 횟수, 바이트) 반복 · ("P", 횟수, 두 바이트) 쌍 반복."""
    toks = []
    lit = bytearray()
    i = 0
    n = len(data)

    def flush():
        nonlocal lit
        while lit:
            k = min(len(lit), 64)  # 🔴 리터럴도 최대 64 — 원본 1,814멤버가 64 를 안 넘는다
            toks.append(("L", bytes(lit[:k])))
            lit = lit[k:]

    while i < n:
        j = i
        while j < n and data[j] == data[i] and j - i < 64:  # 🔴 반복 런은 최대 64 — op 0x40~0x7F 는 쌍 반복(`decompress`)이다
            j += 1
        r1 = j - i
        k = 1
        if i + 1 < n:
            while k < 64 and i + 2 * k + 2 <= n and data[i + 2 * k : i + 2 * k + 2] == data[i : i + 2]:
                k += 1
        if k >= 2 and 2 * k > r1:  # 쌍 반복이 더 많이 덮는다(맵 워드 같은 16비트 자료)
            flush()
            toks.append(("P", k, bytes(data[i : i + 2])))
            i += 2 * k
        elif r1 >= 2:  # 원본 압축기와 같게 — 2개도 반복 런(원본 11,014건)
            flush()
            toks.append(("R", r1, data[i]))
            i = j
        else:
            lit += data[i : i + 1]
            i += 1
    flush()
    return toks


def _emit(toks):
    out = bytearray()
    for t in toks:
        if t[0] == "L":
            out.append(0x80 | (len(t[1]) - 1))
            out += t[1]
        elif t[0] == "R":
            out.append(t[1] - 1)
            out.append(t[2])
        else:
            out.append(0x40 | (t[1] - 1))
            out += t[2]
    return bytes(out)


def compress(data):
    """되감기 — 리터럴 런과 반복 런으로 나눈다.

    ⚠ 원본과 **바이트 동일한** 압축을 목표로 하지 않는다(원 압축기의 선택을 모른다).
       빌드는 「풀면 같은가」로 검증한다 — `decompress(wrap(x))[0] == x`.
    """
    return _emit(_tokens(data))


def compress_to(data, length):
    """스트림 길이를 **정확히** `length` 로 — 토큰을 쪼개 늘린다(리터럴 둘로 +1, 반복 둘로 +2).

    🔴 게임은 아카이브 멤버의 **끝까지** 스트림을 읽는다(10-24 실측 — 원본 7장 시트 모두 스트림이 멤버 길이와 정확히 같다).
       짧게 압축해 0 으로 채우면 꼬리 0 이 `00 00`(반복 런)으로 읽혀 버퍼가 넘치고 맵이 검게 뜬다.
       그래서 멤버 길이를 줄일 수 없으면(`arcpack` 은 크기를 그대로 둔다) 스트림을 길이에 맞춘다.
    """
    toks = _tokens(data)
    need = length - len(_emit(toks))
    if need < 0:
        raise GmfzError(f"압축 {length - need}B 가 멤버 {length}B 보다 크다")
    while need > 0:
        k = next((i for i, t in enumerate(toks) if t[0] == "L" and len(t[1]) >= 2), None)
        if k is not None:
            t = toks[k][1]
            toks[k : k + 1] = [("L", t[:1]), ("L", t[1:])]
            need -= 1
            continue
        k = next((i for i, t in enumerate(toks) if t[0] == "R" and t[1] == 2), None)
        if k is not None:  # 반복 2 → 리터럴 2 (+1)
            toks[k] = ("L", bytes([toks[k][2]]) * 2)
            need -= 1
            continue
        k = next((i for i, t in enumerate(toks) if t[0] == "R" and t[1] >= 2), None)
        if k is not None and need >= 2:
            _, n, b = toks[k]
            toks[k : k + 1] = [("R", 1, b), ("R", n - 1, b)]
            need -= 2
            continue
        k = next((i for i, t in enumerate(toks) if t[0] == "P" and t[1] >= 2), None)
        if k is not None and need >= 3:
            _, n, b = toks[k]
            toks[k : k + 1] = [("P", 1, b), ("P", n - 1, b)]
            need -= 3
            continue
        raise GmfzError("토큰을 더 쪼갤 수 없다")
    return _emit(toks)


def wrap(data, kind=0):
    """압축 + 헤더."""
    return bytes([MAGIC, kind]) + b"\x01\x03" + struct.pack("<I", len(data) - 1) + compress(data)


def wrap_to(data, member_len, kind=0):
    """헤더 + 스트림 = 멤버 길이 `member_len` 정확히."""
    return (
        bytes([MAGIC, kind])
        + b"\x01\x03"
        + struct.pack("<I", len(data) - 1)
        + compress_to(data, member_len - 8)
    )
