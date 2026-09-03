"""이벤트 멤버(`..\\DATA\\*.BIN`)의 구조 — **문자열 풀과 그것을 가리키는 포인터**.

2026-09-03 실측(디스어셈블 + 인게임). 멤버는 두 구간이다:

```
[0]      u16 TEXT_BASE          ← 문자열 풀이 시작하는 오프셋
[2 .. TEXT_BASE)                 스크립트 — **바이트 스트림**(u16 배열이 아니다)
[TEXT_BASE .. ]                  문자열 풀 — 0xFFFF 로 갈린 16비트 코드열
```

스크립트에서 문자열을 가리키는 형태는 하나다:

```
0x90 <u16 V>      (0x90 다음 위치를 **짝수로 올림**하고 u16 을 읽는다)
   문자열 = TEXT_BASE + (V & ~1)
```

⇒ 근거는 어셈블러 `0x800384C4`~`0x800384FC` 다:

```
lw   v0, 0x54(fp)          ; 소스 커서(바이트)
addiu v1, v0, 2 ; sw       ; 커서 += 2
lhu  v1, 0x2e(fp)          ; 방금 읽은 u16 V
srl  v0, v1, 1 ; sll v1,v0,1 ; V & ~1
lw   v0, -0x1b7c(v0)       ; 전역 0x800DE484 = TEXT_BASE 의 RAM 주소
addu v1, v0, v1            ; 문자열 주소
```

🔴 **그래서 런 길이를 바꿀 수 있다.** 풀을 다시 싸고 V 를 다시 계산하면 된다.
   (그 전까지는 「런마다 같은 코드 수」가 계약이었다 — 이 모듈이 그 제약을 푼다.)

⚠ **0x90 을 그냥 스캔하면 안 된다.** 풀 안의 문자 코드에도 0x90 바이트가 있다(실측:
   전수 스캔 96.45%, 빗나간 건 전부 풀 안이었다). **스크립트 구간에서만** 찾는다.
"""

import struct

TERM = 0xFFFF
PTR_OP = 0x90


class ScriptError(Exception):
    pass


def text_base(mem):
    return struct.unpack("<H", mem[0:2])[0]


def pointer_sites(mem):
    """[(u16 오프셋, V)] — 스크립트 구간의 문자열 포인터 자리."""
    base = text_base(mem)
    out = []
    i = 2
    while i < base - 2:
        if mem[i] == PTR_OP:
            q = i + 1
            if q & 1:
                q += 1
            if q + 2 > base:
                break
            out.append((q, struct.unpack("<H", mem[q : q + 2])[0]))
            i = q + 2
        else:
            i += 1
    return out


def segments(mem):
    """[(시작 오프셋, [코드…])] — 풀의 0xFFFF 로 갈린 조각 전부(짧은 것도 남긴다)."""
    base = text_base(mem)
    out = []
    i = base
    cur = []
    start = base
    while i + 1 < len(mem):
        v = struct.unpack("<H", mem[i : i + 2])[0]
        if v == TERM:
            out.append((start, cur))
            cur = []
            start = i + 2
        else:
            cur.append(v)
        i += 2
    if cur:
        out.append((start, cur))
    return out


def parse(mem):
    """{base, pointers, segments, targets} — targets: 포인터가 실제로 가리키는 오프셋."""
    base = text_base(mem)
    ptrs = pointer_sites(mem)
    segs = segments(mem)
    starts = {s for s, _ in segs}
    targets = [(at, base + (v & ~1), (v & 1)) for at, v in ptrs]
    return {
        "base": base,
        "pointers": ptrs,
        "segments": segs,
        "targets": targets,
        "resolved": sum(1 for _, t, _ in targets if t in starts),
        "starts": starts,
    }


def rebuild(mem, new_segments):
    """풀을 새 코드열로 다시 싸고 **포인터를 다시 계산**한다.

    `new_segments` — 원본과 **같은 개수·같은 순서**의 [코드…] 목록. 길이는 달라도 된다.
    반환: 새 멤버 bytes. ⚠ 크기가 달라질 수 있다(호출자가 아카이브 재배치를 책임진다).

    🔴 **개수·순서를 지킨다.** 포인터는 「몇 번째 조각인가」로 다시 매핑하므로, 조각을
       합치거나 나누면 매핑이 통째로 어긋난다.
    """
    info = parse(mem)
    base = info["base"]
    segs = info["segments"]
    if len(new_segments) != len(segs):
        raise ScriptError(f"조각 수가 다르다: {len(new_segments)} (원본 {len(segs)})")

    # 옛 시작 → 새 시작
    remap = {}
    pool = bytearray()
    for (old_start, _), codes in zip(segs, new_segments, strict=True):
        remap[old_start] = base + len(pool)
        pool += struct.pack(f"<{len(codes)}H", *codes)
        pool += struct.pack("<H", TERM)

    out = bytearray(mem[:base]) + pool
    unresolved = 0
    for at, V in info["pointers"]:
        old = base + (V & ~1)
        if old not in remap:
            # 조각 시작이 아닌 0x90 자리 — 스크립트 안의 **데이터**로 본다. 건드리지 않는다.
            unresolved += 1
            continue
        new = remap[old] - base
        if new & 1:
            raise ScriptError("새 오프셋이 홀수다 — 풀은 항상 짝수로 붙는다")
        out[at : at + 2] = struct.pack("<H", new | (V & 1))

    # 🔴 되읽어 검산한다 — 「썼다」와 「다시 읽힌다」는 다른 말이다.
    #    포인터 개수가 같고, 풀린 것이 전부 새 조각 시작에 떨어져야 한다.
    back = parse(bytes(out))
    if len(back["pointers"]) != len(info["pointers"]):
        raise ScriptError(
            f"재구축 뒤 포인터 수가 달라졌다: {len(back['pointers'])} (원본 {len(info['pointers'])})"
        )
    if back["resolved"] != info["resolved"]:
        raise ScriptError(
            f"풀린 포인터 수가 달라졌다: {back['resolved']} (원본 {info['resolved']})"
        )
    return bytes(out), unresolved
