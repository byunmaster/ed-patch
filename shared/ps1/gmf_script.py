"""[ps1-ed3·ps1-ed4 의 `scriptmap.py` 를 하나로 — 순수 함수라 고친 곳 없음(두 사본은 ruff 가 `_v` 로 바꾼 한 줄 말고 같다). ED3 멤버는 `..\\DATA\\*.BIN`(풀 규격 595), ED4 는 `..\\BIN\\*.BIN`(표 규격 356 + 풀 규격 125).]

이벤트 멤버(`..\\DATA\\*.BIN`)의 구조 — **문자열 풀과 그것을 가리키는 포인터**.

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

## 🔴 ED4 는 규격이 다르다 — 오프셋 **표**를 낀다 (실측 2026-09-03)

같은 파서로 ED4 를 읽으면 포인터 적중이 **6.5%** 다. 같은 회사·같은 시기인데 층이 하나 더 있다:

```
[0]        u16 TEXT_BASE
[2 .. TEXT_BASE)             스크립트 — 문자열을 **색인**으로 가리킨다: `0x0F <u16 색인>`
[TEXT_BASE ..]  u16 표 N개    N = 표[0] / 2   (첫 항목이 곧 표의 길이다)
[TEXT_BASE + N*2 ..]         문자열 풀 — 문자열 i = TEXT_BASE + 표[i]
```

⇒ **ED4 는 포인터를 다시 쓸 필요조차 없다.** 색인은 그대로 두고 **표만 다시 계산**하면 된다.
   길이가 자유로운 건 ED3 과 같지만, 고쳐야 할 자리는 훨씬 적다.

계약을 전수로 쟀다(멤버 356): **중복 오프셋 0 · 표가 어긋난 자리 0 · 풀이 멤버 끝과 정확히
맞는 것 355/356.** 즉 표는 「앞 문자열이 끝난 자리」의 나열이고 풀 뒤에는 아무것도 없다.
⚠ 나머지 125 멤버(`*B.BIN` 등)는 이 규격이 아니다 — 아직 안 건드린다.
"""

import struct

TERM = 0xFFFF
PTR_OP = 0x90  # ED3 — `0x90 <u16 바이트오프셋>`
IDX_OP = 0x0F  # ED4 — `0x0F <u16 색인>` (표 적중 145/148 로 유도, 실측)

LAYOUT_POOL = "pool"  # ED3 — 풀을 곧장 가리킨다
LAYOUT_TABLE = "table"  # ED4 — 오프셋 표를 낀다


class ScriptError(Exception):
    pass


def text_base(mem):
    return struct.unpack("<H", mem[0:2])[0]


def table_len(mem):
    """ED4 규격이면 표의 항목 수, 아니면 None.

    첫 항목이 곧 표의 바이트 길이다(`N = 표[0] / 2`) — 표가 문자열 풀 바로 앞에 붙어 있어
    「첫 문자열까지의 거리」가 곧 표의 크기이기 때문이다.
    """
    base = text_base(mem)
    if not (2 < base < len(mem) - 2):
        return None
    t0 = struct.unpack_from("<H", mem, base)[0]
    if t0 % 2 or t0 < 2 or base + t0 > len(mem):
        return None
    n = t0 // 2
    tb = struct.unpack_from(f"<{n}H", mem, base)
    if any(tb[i] > tb[i + 1] for i in range(n - 1)) or base + tb[-1] >= len(mem):
        return None
    return n


def layout(mem):
    """이 멤버가 어느 규격인가. ⚠ **추측이 아니라 구조로 판정**한다(표가 단조·범위 안)."""
    return LAYOUT_TABLE if table_len(mem) is not None else LAYOUT_POOL


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


def dialogue_targets(mem):
    """([목표 수], [조각 시작을 못 맞힌 (자리, 목표)]) — **대사 포인터(`0x0F 0x90 <u16>`)** 만 본다(ED3 풀 규격).

    🔴 번역 단위 목록이 풀의 모든 `0xFFFF` 조각이라, 목록 밖 대사는 「포인터가 조각 시작을 못 맞히는」 꼴로만 생긴다(sfc-ed1 에서
    장면 대사 101개가 목록 밖이라 일본어로 남았다 — 10-18). 다른 연산자 뒤의 `0x90` 은 이벤트 VM 자료 바이트와 구별되지 않아(404개 중
    242개가 멤버 밖을 가리킨다) 게이트로 안 건다 — 개수만 센다(`parse` 의 `resolved`)."""
    if layout(mem) != LAYOUT_POOL:
        return [], []
    info = parse(mem)
    tot, miss = [], []
    for at, t, _odd in info["targets"]:
        p = at - 1 if mem[at - 1] == PTR_OP else at - 2
        if p >= 1 and mem[p - 1] == 0x0F:
            tot.append(t)
            if t not in info["starts"]:
                miss.append((at, t))
    return tot, miss


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


def _walk_stream(mem, base, n, ptr, limit=400):
    """([(색인 자리, 색인)], 끝 다음 오프셋) 또는 None — 메시지 해석기(ED4 `0x8003c98c`)가 읽는 그대로 걷는다.

    해석기는 연산 한 바이트를 읽는다: `0F` = 문자열 출력(연산 뒤 포인터가 홀수면 패딩 1, 이어서 u16 색인) · `00` = 메시지 끝 ·
    그 밖(`01`~`0E` 줄·쪽·동적 이름 삽입·대기, `10` 이상 글자 색)은 **피연산자 없는 한 바이트**다(점프표 `0x800103d0` 의 핸들러를 하나씩 읽었다).
    그래서 출력 사이에 어떤 바이트가 끼어도 된다(`0F 6c 00 02 0F 6d 00 05 0F 6e 00 01 …` — 색인이 연속). 출력이 하나 이상이고 `00` 으로 닫혀야 메시지다.
    """
    prints = []
    for _ in range(limit):
        if ptr >= base:
            return None
        b = mem[ptr]
        if b == IDX_OP:
            q = ptr + 1
            if q & 1:
                q += 1
            if q + 2 > base:
                return None
            v = struct.unpack_from("<H", mem, q)[0]
            if v >= n:
                return None
            prints.append((q, v))
            ptr = q + 2
        elif b == 0:
            return (prints, ptr + 1) if prints else None
        else:
            ptr += 1
    return None


def message_streams(mem):
    """[{p0, kind, prints:[(자리, 색인)], end}] — ED4 스크립트 안의 **메시지 스트림**(표 규격).

    VM 연산 `0F`(블록 시작) 다음부터 걷는 쪽(`kind='A'`)을 먼저 보고, 안 되면 `0F` 자신이 첫 출력인 스트림(`'B'`)으로 본다.
    🔴 옛 스캔(`0F` 뒤 정렬된 u16 이 표 안이면 출력)은 `0F 03 0F 00 68 00 01` 에서 앞 `0F` 를 출력으로 보고 `(0F,00)` = 색인 15 를 읽었다 — 가짜 색인 15 를
    만들고 진짜 출력을 건너뛴다(ps1-ed4 10-24: 조각 11% 가 「포인터 없음」). 흐름 바이트를 `00·01·02` 로 좁히는 것도 틀렸다(`05`·`06` 은 이름 삽입 연산이라 출력 사이에 낀다).
    실측(ED4 표 규격 356멤버, 조각 24,499): 옛 스캔 참조 23,405 → 이 걷기 24,057.
    """
    base = text_base(mem)
    n = table_len(mem)
    out = []
    p = 2
    while p < base - 3:
        if mem[p] != IDX_OP:
            p += 1
            continue
        r, kind = _walk_stream(mem, base, n, p + 1), "A"
        if r is None:
            r, kind = _walk_stream(mem, base, n, p), "B"
        if r is None:
            p += 1
            continue
        out.append({"p0": p, "kind": kind, "prints": r[0], "end": r[1]})
        p = r[1]
    return out


def table_sites(mem):
    """[(u16 오프셋, 색인)] — ED4 스크립트의 문자열 출력 자리. `message_streams` 의 출력을 펴 놓은 것."""
    return [site for st in message_streams(mem) for site in st["prints"]]


def table_segments(mem):
    """[(시작 오프셋, [코드…])] — 표가 가리키는 순서 그대로. **표 순서가 곧 순서다.**"""
    base = text_base(mem)
    n = table_len(mem)
    tb = struct.unpack_from(f"<{n}H", mem, base)
    out = []
    for x in tb:
        p = base + x
        codes = []
        while p + 1 < len(mem):
            v = struct.unpack_from("<H", mem, p)[0]
            if v == TERM:
                break
            codes.append(v)
            p += 2
        out.append((base + x, codes))
    return out


def parse_table(mem):
    base = text_base(mem)
    n = table_len(mem)
    segs = table_segments(mem)
    sites = table_sites(mem)
    return {
        "layout": LAYOUT_TABLE,
        "base": base,
        "table_len": n,
        "segments": segs,
        "pointers": sites,
        "targets": [(at, segs[v][0], 0) for at, v in sites],
        "resolved": len(sites),
        "starts": {s for s, _ in segs},
    }


def rebuild_table(mem, new_segments):
    """ED4 — 표와 풀을 다시 싼다. **스크립트는 손대지 않는다**(색인이 그대로다).

    🔴 「썼다」와 「다시 읽힌다」는 다른 말이다 — 끝에서 되읽어 표 길이·조각 수를 검산한다.
    """
    info = parse_table(mem)
    base, n = info["base"], info["table_len"]
    if len(new_segments) != n:
        raise ScriptError(f"조각 수가 다르다: {len(new_segments)} (표 {n})")
    tbl, pool = [], bytearray()
    for codes in new_segments:
        tbl.append(n * 2 + len(pool))
        pool += struct.pack(f"<{len(codes)}H", *codes) + struct.pack("<H", TERM)
    if tbl[0] != n * 2:
        raise ScriptError("표의 첫 항목은 표 자신의 길이여야 한다")
    if max(tbl) > 0xFFFF:
        raise ScriptError(f"풀이 u16 을 넘었다 ({max(tbl)}) — 이 멤버는 못 늘린다")
    # ⚠ 풀 뒤에 **뭔가 더 있는** 멤버가 하나 있다(`AR02000.BIN`, 73B). 스크립트로 보이는데
    #   무엇이 그 자리를 가리키는지 모른다 — 그대로 옮기되, **늘리는 건 막는다.**
    #   자리가 밀리면 조용히 깨질 수 있고, 조용히 깨지는 게 이 레포의 단골 사고다.
    old_end = info["segments"][-1][0] + len(info["segments"][-1][1]) * 2 + 2
    tail = bytes(mem[old_end:])
    if tail and len(pool) > old_end - (base + n * 2):
        raise ScriptError(f"풀 뒤에 자료 {len(tail)}B 가 있다 — 이 멤버는 늘릴 수 없다")
    out = bytearray(mem[:base]) + struct.pack(f"<{n}H", *tbl) + pool + tail
    back = parse_table(bytes(out))
    if back["table_len"] != n or len(back["segments"]) != n:
        raise ScriptError("재구축 뒤 표가 달라졌다")
    if [c for _, c in back["segments"]] != [list(c) for c in new_segments]:
        raise ScriptError("되읽은 조각이 넣은 것과 다르다")
    return bytes(out), 0


def window_chains(mem, info=None):
    """[[조각 번호…]] — 대사 창 하나(`0F 90 V (01 90 W)* 00` 시퀀스)가 이어 보이는 조각들. 조각 하나가 한 줄이다.

    포인터 자리 `q` 는 짝수 오프셋이고 이어지는 `01 90 W` 는 4바이트 뒤(`q+4`)다. 첫 포인터 앞은 `0F 90`(맞춤 패드 한 바이트 허용)이어야 한다.
    포인터가 조각 시작을 못 맞히면 그 창은 건너뛴다(이벤트 자료로 본다)."""
    if info is None:
        if layout(mem) != LAYOUT_POOL:
            return []
        info = parse(mem)
    idx = {s: i for i, (s, _c) in enumerate(info["segments"])}
    base = info["base"]
    sites = info["pointers"]
    at_of = {q: v for q, v in sites}
    out, used = [], set()
    for q, _v in sites:
        if q in used:
            continue
        i = q - 1
        if mem[i] != PTR_OP:
            i -= 1  # 맞춤 패드
        if i < 1 or mem[i] != PTR_OP or mem[i - 1] != 0x0F:
            continue
        chain, cq = [], q
        while True:
            t = base + (at_of[cq] & ~1)
            if t not in idx:
                chain = None
                break
            chain.append(idx[t])
            used.add(cq)
            if mem[cq + 2 : cq + 4] == b"\x01\x90" and (cq + 4) in at_of:
                cq += 4
                continue
            break
        if chain and mem[cq + 2 : cq + 3] == b"\x00":
            out.append(chain)
    return out


def parse(mem):
    """{base, pointers, segments, targets} — 규격을 판정해 알맞은 파서로 보낸다."""
    if layout(mem) == LAYOUT_TABLE:
        return parse_table(mem)
    base = text_base(mem)
    ptrs = pointer_sites(mem)
    segs = segments(mem)
    starts = {s for s, _ in segs}
    targets = [(at, base + (v & ~1), (v & 1)) for at, v in ptrs]
    return {
        "layout": LAYOUT_POOL,
        "base": base,
        "pointers": ptrs,
        "segments": segs,
        "targets": targets,
        "resolved": sum(1 for _, t, _ in targets if t in starts),
        "starts": starts,
    }


def rebuild(mem, new_segments, event_data=False):
    """풀을 새 코드열로 다시 싸고 **포인터를 다시 계산**한다.

    `new_segments` — 원본과 **같은 개수·같은 순서**의 [코드…] 목록. 길이는 달라도 된다.
    반환: 새 멤버 bytes. ⚠ 크기가 달라질 수 있다(호출자가 아카이브 재배치를 책임진다).

    `event_data=True` — 못 푼 `0x90` 자리(조각 시작이 아닌 곳을 가리키는 것)를 **이벤트 VM 데이터로 보고** 그대로 둔 채
    길이를 바꾼다(마스터 10-12 「재구성해」). 근거(실측, ED3 전수):
      · 못 푼 404 중 목표가 멤버 밖 242 · 조각 한복판 162 — 풀린 33,861 은 100% 조각 시작이다.
      · 자리가 `90 01 03 02 91 01 05 01` · `c0 90 61 60 00` 처럼 형제 opcode(0x91…)·좌표 사이에 낀 구조체 한복판이다.
      · 한복판 값이 같은 상수로 되풀이된다(예: `FT2001` 한 멤버에서 96 이 셋) — 포인터가 아니라 상수다.
    ⚠ 이 근거는 **정적 추정**이다(이벤트 VM 해독은 안 됐다). 그래서 되읽기 검산을 둘 더 건다 —
      ① 스크립트 구간 `[0, TEXT_BASE)` 은 **풀린 포인터 자리 말고는 바이트 단위로 같다**(못 푼 자리 포함) ② 풀린 포인터는
      **같은 번째 조각의 새 시작**을 가리킨다. 기본값(False)은 옛 방침(길이가 바뀌면 멈춘다).

    🔴 **개수·순서를 지킨다.** 포인터는 「몇 번째 조각인가」로 다시 매핑하므로, 조각을
       합치거나 나누면 매핑이 통째로 어긋난다.
    """
    if layout(mem) == LAYOUT_TABLE:
        return rebuild_table(mem, new_segments)
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
    #   🔴 못 푼 포인터(조각 한복판을 가리키는 `0x90` — 이벤트 VM 데이터로 본다)가 있는 멤버는
    #      **조각 길이를 못 바꾼다**: 그 포인터는 안 따라가서, 길이가 바뀌면 엉뚱한 자리를 가리킨다.
    #      조용히 깨지는 대신 여기서 멈춘다(「같은 길이로만」 152 멤버 — 이벤트 VM 해독 전까지).
    unresolved_n = sum(1 for _, V in info["pointers"] if base + (V & ~1) not in remap)
    if (
        unresolved_n
        and not event_data
        and any(len(new) != len(old) for (_, old), new in zip(segs, new_segments, strict=True))
    ):
        raise ScriptError(
            f"못 푼 포인터 {unresolved_n}개가 있는 멤버 — 조각 길이를 바꿀 수 없다(같은 길이로만)"
        )
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
    # event_data: 안 건드린 데이터 자리가 길이가 바뀐 뒤 우연히 조각 시작에 떨어질 수 있다 — 줄어드는 쪽만 오류다.
    if back["resolved"] < info["resolved"] or (
        back["resolved"] != info["resolved"] and not event_data
    ):
        raise ScriptError(
            f"풀린 포인터 수가 달라졌다: {back['resolved']} (원본 {info['resolved']})"
        )
    verify_rebuild(mem, bytes(out), info, new_segments)
    return bytes(out), unresolved


def verify_rebuild(mem, out, info, new_segments):
    """🔴 구조 검산 — 「썼다」와 「다시 읽힌다」 말고 **「안 건드릴 것을 안 건드렸다」** 를 바이트로 본다.

    ① 스크립트 구간은 풀린 포인터 자리(u16)만 다르다 — 못 푼 `0x90` 자리·이벤트 데이터는 바이트까지 같다.
    ② 풀린 포인터는 **같은 번째 조각의 새 시작**을 가리킨다(번째 = 옛 풀에서 그 조각의 순서).
    ③ 풀은 새 조각을 `0xFFFF` 로 닫아 순서대로 이어 붙인 것과 같다(꼬리 없음).
    """
    base = info["base"]
    if text_base(out) != base:
        raise ScriptError("재구축 뒤 TEXT_BASE 가 달라졌다")
    sites = {at for at, V in info["pointers"] if base + (V & ~1) in info["starts"]}
    touched = set()
    for at in sites:
        touched.update((at, at + 1))
    for i in range(base):
        if i not in touched and mem[i] != out[i]:
            raise ScriptError(f"스크립트 구간 {i:#x} 가 포인터 자리가 아닌데 바뀌었다")
    old_idx = {s: k for k, (s, _) in enumerate(info["segments"])}
    back = parse(out)
    new_start = [s for s, _ in back["segments"]]
    if len(new_start) != len(new_segments):
        raise ScriptError("재구축 뒤 조각 수가 달라졌다")
    for at, V in info["pointers"]:
        old = base + (V & ~1)
        if old not in old_idx:
            continue
        got = struct.unpack_from("<H", out, at)[0]
        if base + (got & ~1) != new_start[old_idx[old]] or (got & 1) != (V & 1):
            raise ScriptError(f"포인터 {at:#x} 가 {old_idx[old]}번째 조각의 새 시작을 안 가리킨다")
    pool = b"".join(struct.pack(f"<{len(c)}H", *c) + struct.pack("<H", TERM) for c in new_segments)
    if bytes(out[base:]) != pool:
        raise ScriptError("재구축 뒤 풀이 새 조각의 이음과 다르다")
