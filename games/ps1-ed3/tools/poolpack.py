"""읽을거리 풀 재배치 + **사전 압축** — 메모·검사교본·사피 이야기를 원문 기반 번역 전량으로 넣는다(마스터 10-12 「재구성으로 넓혀보자」→「(가) 문자열 사전 압축」).

## 왜

풀(`uitext.POOLS`)은 영역이 꽉 차 있어(2,830·4,076코드) 번역이 일본어 한 줄보다 길면 못 넣었다. 번역을 줄이지 않으려고 **자리를 만든다**:
풀을 줄 단위로 다시 깔고(길이 재배정 + 표 오프셋 갱신), 글자쌍 사전 압축으로 바이트를 접는다.

```
풀 영역    [문자열들 …… 빈 칸 ……][코드(펼침 훅)][사전 2코드×N][버퍼 BUF_CODES 코드]
표         u16 오프셋(기준 주소 + 값) — 값이 0x8000 이상인 제어 항목(0x8000~0x8005)은 **그대로**
```

## 규약 (실행파일 디스어셈블로 확인한 것)

- 읽는 코드는 **둘뿐이다.** ① 범용 줄 재생기 `0x80022C90`(a1 = 표 포인터, a2 = 기준 주소) — 항목마다 `기준 + (값 & ~1)` 에서 코드를 읽어 `0xFFFF` 가
  나올 때까지 흘린다(`0xEEEE` 는 뒤 코드를 숫자로 찍고 계속, `0x0000` 은 그냥 빈 글리프 — 종결이 아니다). ② 목록 창(`0x80023500~`)이 풀1 제목을
  그리개 `0x8001A7E8`·`0x8001A40C` 로 바로 그린다(코드를 명령 버퍼로 **복사**하다가 최상위 비트가 선 코드에서 끝난다).
- 그래서 사전 코드는 **0x8000 미만**이어야 한다(그리개가 거기서 끝난다). `0x7800~` 를 쓴다(조사 표지 `0x7000~` 와 안 겹친다 — 조사 훅은 글리프 단계라 사전이 먼저 펼쳐진다).
- 펼침은 **그리기 직전**에 한다: ① `0x80022E30`(`addu a1,a0,a1` → `jal HOOK`)에서 기준 주소가 풀1·풀2 일 때만 펼친 버퍼를 `0x1C($fp)` 에 쓴다.
  ② 제목 그리개 호출 셋(`0x8002359C`·`0x800235F8`·`0x800236CC`)을 래퍼로 돌린다(a1 을 펼치고 원래 그리개로 꼬리 점프).
- 문자열 하나(표 항목이 가리키는 곳부터 `0xFFFF` 까지)가 펼쳐진 줄은 **버퍼에 들어가야** 한다 — 빌드가 센다.

## 불변식

- 같은 입력 → 같은 사전(동점은 쌍 값 순), 같은 바이트.
- 되읽어 펼친 **모든 표 항목의 코드열 = 정본에서 직접 만든 기대값**(`expected_streams` ↔ `read_streams`, 원본과 따로 계산한다).
- 안 건드린 제어 항목·표 크기·풀 밖 바이트는 그대로.
"""

import struct

import exetext

DICT_BASE = 0x7800  # 사전 코드 = DICT_BASE + 번호 (0x8000 미만 — 그리개가 거기서 끝난다)
DICT_MAX = 0x7FFF - DICT_BASE
DEPTH_MAX = 7  # 사전 안 사전의 깊이(펼침 보류 스택 8칸)
LINE_MAX = 24  # 한 문자열(줄)의 펼친 코드 수 상한 — 창 너비
BUF_CODES = 96  # 펼친 한 항목(이어 읽기 포함)의 최대 코드 수(종결 포함)
TERM_FFFF = 0xFFFF

LAYOUT = {
    "ed3": {
        "exe_off": 0x800,  # 파일 오프셋 → RAM: 0x80010000 + off - 0x800
        "pools": [
            {"table": 0x9D66C, "n": 226, "base": 0x9D830, "end": 0x9EE4C},
            {"table": 0x9EE4C, "n": 310, "base": 0x9F0B8, "end": 0xA10B0},
        ],
        "tail_pool": 1,  # 코드·사전·버퍼는 풀2 꼬리에 둔다
        "hook_player": 0x80022E30,
        "hook_player_orig": (0x00852821, 0xAFC5001C),  # addu a1,a0,a1 · sw a1,0x1c(fp)
        "draw_sites": [  # (RAM, 원래 표적) — 풀1 제목 그리개 호출 (뒤따르는 지연 슬롯은 nop)
            (0x8002359C, 0x8001A7E8),
            (0x800235F8, 0x8001A40C),
            (0x800236CC, 0x8001A7E8),
        ],
    }
}


def ram(off):
    return 0x80010000 + off - 0x800


def _u16(data, off):
    return struct.unpack_from("<H", data, off)[0]


# ── 원본 구조 읽기 ───────────────────────────────────────────────────────────────


def segments(data, pool):
    """[(오프셋, 코드열, 종결값)] — 풀 영역을 **이어 붙은 조각**으로 끝까지 걷는다(종결 = 최상위 비트가 선 코드 또는 0).

    🔴 `0x0000` 은 종결이 아니라 빈 글리프인데, 조각 경계로는 쓴다(번역 행의 오프셋이 그 경계다). 흐름(펼침)은 `0xFFFF` 에서만 끝난다.
    """
    out = []
    p = pool["base"]
    while p < pool["end"]:
        codes, term = exetext.raw_string(data, p, limit=400)
        if codes is None:
            raise ValueError(f"풀 조각이 끝나지 않는다: {p:#x}")
        out.append((p, codes, term))
        p += 2 * (len(codes) + 1)
    if p != pool["end"]:
        raise ValueError(f"풀 영역이 조각으로 안 떨어진다: 끝 {p:#x} ≠ {pool['end']:#x}")
    return out


def table_entries(data, pool):
    return list(struct.unpack_from(f"<{pool['n']}H", data, pool["table"]))


def check_entries(data, pool, segs):
    """표 항목(제어 제외)이 전부 조각 시작인가 — 아니면 재배치가 그 항목을 못 따라간다."""
    starts = {s[0] for s in segs}
    bad = [
        (i, v)
        for i, v in enumerate(table_entries(data, pool))
        if v < 0x8000 and pool["base"] + v not in starts
    ]
    if bad:
        raise ValueError(f"표 항목이 조각 시작이 아니다: {bad[:5]}")


def chain_from(segs, start_off):
    """표 항목이 가리키는 조각에서 `0xFFFF` 조각까지의 인덱스 목록."""
    idx = next(i for i, s in enumerate(segs) if s[0] == start_off)
    out = []
    while True:
        out.append(idx)
        if segs[idx][2] == TERM_FFFF:
            return out
        idx += 1
        if idx >= len(segs):
            raise ValueError("이어 읽기가 풀 밖으로 나간다")


# ── 사전 압축 (결정적 BPE) ───────────────────────────────────────────────────────


def build_dict(seqs, max_n=DICT_MAX):
    """(합병 목록 [(a, b)], 압축된 열) — 글자쌍을 새 코드로. 이득 = 쌍 횟수 − 2 코드(사전 항목)가 0 보다 클 때만.

    결정성: 횟수 큰 쌍 → 값이 작은 쌍. 깊이 제한(`DEPTH_MAX`). 프리픽스가 곧 최적해라 비용이 최소인 N 까지만 쓴다.
    """
    work = [list(s) for s in seqs]
    depth = {}
    merges = []
    total = sum(len(s) for s in work)
    best_n, best_cost = 0, total
    cost = total
    while len(merges) < max_n:
        cnt = {}
        for s in work:
            for a, b in zip(s, s[1:]):
                cnt[(a, b)] = cnt.get((a, b), 0) + 1
        cand = [
            (n, pr)
            for pr, n in cnt.items()
            if depth.get(pr[0], 0) < DEPTH_MAX and depth.get(pr[1], 0) < DEPTH_MAX
        ]
        if not cand:
            break
        n, (a, b) = min(cand, key=lambda x: (-x[0], x[1]))
        if n < 3:
            break
        new = DICT_BASE + len(merges)
        merges.append((a, b))
        depth[new] = 1 + max(depth.get(a, 0), depth.get(b, 0))
        cost += 2 - n  # 사전 항목 2코드 − 절약 n
        for i, s in enumerate(work):
            out, j = [], 0
            while j < len(s):
                if j + 1 < len(s) and s[j] == a and s[j + 1] == b:
                    out.append(new)
                    j += 2
                else:
                    out.append(s[j])
                    j += 1
            work[i] = out
        if cost < best_cost:
            best_n, best_cost = len(merges), cost
    # 최적 N 으로 다시 짠다(프리픽스)
    merges = merges[:best_n]
    work = [list(s) for s in seqs]
    for k, (a, b) in enumerate(merges):
        new = DICT_BASE + k
        for i, s in enumerate(work):
            out, j = [], 0
            while j < len(s):
                if j + 1 < len(s) and s[j] == a and s[j + 1] == b:
                    out.append(new)
                    j += 2
                else:
                    out.append(s[j])
                    j += 1
            work[i] = out
    return merges, work


def expand_codes(codes, merges):
    """사전 코드를 펼친다(펼침 훅의 파이썬 기준 구현 — 기계어와 같은 결과여야 한다). `0xFFFF` 를 만나면 거기서 끝낸다."""
    out = []
    for c in codes:
        stack = [c]
        while stack:
            x = stack.pop()
            if DICT_BASE <= x < 0x8000:
                a, b = merges[x - DICT_BASE]
                stack.append(b)
                stack.append(a)
            else:
                out.append(x)
        if out and out[-1] == TERM_FFFF:
            break
    return out


# ── 훅 기계어 ────────────────────────────────────────────────────────────────────


def hook_source(buf, dct, hook_base):
    """(어셈블리, 라벨) — 펼침 + 줄 재생기 훅 + 제목 그리개 래퍼 둘.

    레지스터 규약: 펼침은 a1(입력·출력)·t0~t7·스택 32B 만 쓴다. a0·a2·a3·t8·t9·ra·fp·v0·v1 은 보존한다.
    """
    return f"""
expand:
    addiu sp, sp, -32
    lui   t0, {buf >> 16}
    ori   t0, t0, {buf & 0xFFFF}
    move  t1, a1
    lui   t2, {dct >> 16}
    ori   t2, t2, {dct & 0xFFFF}
    addiu t3, sp, 32
    addiu t7, sp, 32
nextsrc:
    lhu   t4, 0(t1)
    addiu t1, t1, 2
dcode:
    sltiu t5, t4, {DICT_BASE}
    bne   t5, zero, lit
    nop
    andi  t5, t4, 0x8000
    bne   t5, zero, lit
    nop
    addiu t4, t4, -{DICT_BASE}
    sll   t4, t4, 2
    addu  t4, t2, t4
    lhu   t5, 2(t4)
    lhu   t4, 0(t4)
    addiu t3, t3, -4
    sh    t5, 0(t3)
    j     dcode
    nop
lit:
    sh    t4, 0(t0)
    addiu t0, t0, 2
    ori   t5, zero, 0xffff
    beq   t4, t5, done
    nop
    beq   t3, t7, nextsrc
    nop
    lhu   t4, 0(t3)
    addiu t3, t3, 4
    j     dcode
    nop
done:
    lui   a1, {buf >> 16}
    ori   a1, a1, {buf & 0xFFFF}
    addiu sp, sp, 32
    jr    ra
    nop
"""


def hook_entries(p1_base, p2_base, draw_a, draw_b):
    return f"""
hook_player:
    addu  a1, a0, a1
    lui   t8, {p1_base >> 16}
    ori   t8, t8, {p1_base & 0xFFFF}
    beq   a0, t8, hp_do
    nop
    lui   t8, {p2_base >> 16}
    ori   t8, t8, {p2_base & 0xFFFF}
    bne   a0, t8, hp_plain
    nop
hp_do:
    move  t9, ra
    jal   expand
    nop
    move  ra, t9
hp_plain:
    sw    a1, 0x1c(fp)
    jr    ra
    nop
wrap_a:
    move  t9, ra
    jal   expand
    nop
    move  ra, t9
    j     {draw_a:#x}
    nop
wrap_b:
    move  t9, ra
    jal   expand
    nop
    move  ra, t9
    j     {draw_b:#x}
    nop
"""


# ── 재배치 ────────────────────────────────────────────────────────────────────────


class PoolPackError(Exception):
    pass


def _assemble(disc, buf, dct, base):
    import engine_patch

    L = LAYOUT[disc]
    p1 = ram(L["pools"][0]["base"])
    p2 = ram(L["pools"][1]["base"])
    text = hook_source(buf, dct, base) + hook_entries(p1, p2, L["draw_sites"][0][1], L["draw_sites"][1][1])
    words, labels = engine_patch.asm(text, base)
    return words, labels


def resolve_rows(rows, encode):
    """({오프셋: 코드열}, [인코딩 못 한 오프셋]) — 글리프 자리가 없는 글자가 든 행은 원문 그대로 둔다(조용히 빼지 않고 알린다)."""
    ok, skipped = {}, []
    for off, kr in sorted(rows.items()):
        try:
            ok[off] = list(encode(kr))
        except KeyError:
            skipped.append(off)
    return ok, skipped


def plan(exe_orig, disc, rows, encode):
    """쓰기 전에 다 계산한다. rows = {오프셋: 번역문(`kr`)} — 풀 행만. 반환: dict(새 풀 바이트·표·훅·통계)."""
    L = LAYOUT[disc]
    pools = L["pools"]
    all_segs = []
    starts = {}
    for pi, pool in enumerate(pools):
        segs = segments(exe_orig, pool)
        check_entries(exe_orig, pool, segs)
        all_segs.append(segs)
        for k, s in enumerate(segs):
            starts[s[0]] = (pi, k)
    # 새 코드열(원문 조각은 그대로, 번역이 있으면 교체)
    new_codes = [[list(s[1]) for s in segs] for segs in all_segs]
    coded, skipped = resolve_rows(rows, encode)
    for off, codes in sorted(coded.items()):
        if off not in starts:
            continue  # 풀 조각이 아닌 행(표 영역 쓰레기 행 등)은 이 모듈 몫이 아니다
        pi, k = starts[off]
        if len(codes) > LINE_MAX:
            raise PoolPackError(f"{off:#x}: 줄이 {len(codes)} 코드 > {LINE_MAX} — 창 너비를 넘는다")
        new_codes[pi][k] = list(codes)
    flat = [c for pc in new_codes for c in pc]
    merges, comp = build_dict(flat)
    it = iter(comp)
    comp_codes = [[next(it) for _ in pc] for pc in new_codes]
    # 꼬리(코드·사전·버퍼) 크기 — 어셈블 크기는 주소와 무관하다
    words, _ = _assemble(disc, 0x80000000, 0x80000000, 0x80000000)
    code_bytes = 4 * len(words)
    dict_bytes = 4 * len(merges)
    buf_bytes = 2 * BUF_CODES
    tp = pools[L["tail_pool"]]
    tail_total = code_bytes + dict_bytes + buf_bytes
    tail_start = (tp["end"] - tail_total) // 4 * 4
    out_pools = []
    new_off = {}
    for pi, pool in enumerate(pools):
        limit = tail_start if pi == L["tail_pool"] else pool["end"]
        pos = pool["base"]
        for k, s in enumerate(all_segs[pi]):
            new_off[s[0]] = pos
            pos += 2 * (len(comp_codes[pi][k]) + 1)
        if pos > limit:
            raise PoolPackError(
                f"풀{pi + 1}: 필요 {pos - pool['base']}B > 영역 {limit - pool['base']}B "
                f"({pos - limit}B 넘친다) — 사전 {len(merges)}항목·꼬리 {tail_total}B 반영"
            )
        out_pools.append((pool, pos))
    code_off, dict_off = tail_start, tail_start + code_bytes
    buf_off = dict_off + dict_bytes
    words, labels = _assemble(disc, ram(buf_off), ram(dict_off), ram(code_off))
    # 새 바이트열
    patches = {}  # 파일 오프셋 → bytes
    for pi, (pool, end_pos) in enumerate(out_pools):
        blob = bytearray(pool["end"] - pool["base"])
        for k, s in enumerate(all_segs[pi]):
            o = new_off[s[0]] - pool["base"]
            cc = comp_codes[pi][k] + [s[2]]
            struct.pack_into(f"<{len(cc)}H", blob, o, *cc)
        patches[pool["base"]] = bytearray(blob)
        # 표
        ent = table_entries(exe_orig, pool)
        newent = [v if v >= 0x8000 else new_off[pool["base"] + v] - pool["base"] for v in ent]
        patches[pool["table"]] = struct.pack(f"<{pool['n']}H", *newent)
    tail = patches[tp["base"]]
    o = code_off - tp["base"]
    struct.pack_into(f"<{len(words)}I", tail, o, *words)
    o = dict_off - tp["base"]
    for a, b in merges:
        struct.pack_into("<HH", tail, o, a, b)
        o += 4
    # BUF 는 0 (이미 0)
    # 훅 자리 — 줄 재생기(`jal hook_player`)와 제목 그리개 셋(`jal wrap_a|wrap_b`)
    def jal(addr):
        return (3 << 26) | ((addr >> 2) & 0x3FFFFFF)

    sites = {L["hook_player"]: jal(labels["hook_player"])}
    for site, target in L["draw_sites"]:
        sites[site] = jal(labels["wrap_a" if target == L["draw_sites"][0][1] else "wrap_b"])
    return {
        "disc": disc,
        "patches": patches,
        "merges": merges,
        "words": words,
        "labels": labels,
        "code_off": code_off,
        "dict_off": dict_off,
        "buf_off": buf_off,
        "sites": sites,
        "skipped": skipped,
        "stats": {
            "pools": [(pool["end"] - pool["base"], end_pos - pool["base"]) for pool, end_pos in out_pools],
            "dict": len(merges),
            "raw_codes": sum(len(c) for c in flat),
            "comp_codes": sum(len(c) for pc in comp_codes for c in pc),
            "tail": tail_total,
        },
    }



def _fileoff(r):
    return r - 0x80010000 + 0x800


def apply(exe, disc, rows, encode):
    """실행파일 bytearray 에 풀 재배치 + 사전 + 훅을 쓴다. 반환: plan 사전(통계 포함).

    🔴 쓰기 전에 훅 자리의 원본 워드를 대조한다(다른 덤프거나 두 번 적용하면 거기서 선다 — 체크리스트 2).
    """
    L = LAYOUT[disc]
    pl = plan(bytes(exe), disc, rows, encode)
    a0, a1 = L["hook_player_orig"]
    got = struct.unpack_from("<2I", exe, _fileoff(L["hook_player"]))
    if tuple(got) != (a0, a1):
        raise PoolPackError(f"줄 재생기 훅 자리의 원본이 다르다: {got[0]:08x} {got[1]:08x} ≠ {a0:08x} {a1:08x}")
    for site, target in L["draw_sites"]:
        want = (3 << 26) | ((target >> 2) & 0x3FFFFFF)
        w = struct.unpack_from("<I", exe, _fileoff(site))[0]
        if w != want:
            raise PoolPackError(f"제목 그리개 호출 {site:#x} 의 원본이 다르다: {w:08x} ≠ {want:08x}")
    for off, blob in pl["patches"].items():
        exe[off : off + len(blob)] = blob
    for site, word in pl["sites"].items():
        struct.pack_into("<I", exe, _fileoff(site), word)
    return pl


# ── 되읽기 · 기대값 (서로 따로 계산한다) ───────────────────────────────────────────


def expected_streams(exe_orig, disc, rows, encode):
    """정본에서 직접 만든 기대값 — {(풀, 항목 번호): 펼친 코드열(종결 포함)}. 원본 구조 + 번역 행."""
    L = LAYOUT[disc]
    coded, _ = resolve_rows(rows, encode)
    out = {}
    for pi, pool in enumerate(L["pools"]):
        segs = segments(exe_orig, pool)
        for i, v in enumerate(table_entries(exe_orig, pool)):
            if v >= 0x8000:
                continue
            seq = []
            for k in chain_from(segs, pool["base"] + v):
                off, codes, term = segs[k]
                seq += list(coded[off] if off in coded else codes) + [term]
            out[(pi, i)] = seq
    return out


def read_streams(exe, disc, merges):
    """새 이미지를 표·사전으로 읽어 펼친 코드열 — {(풀, 항목 번호): 코드열}. 훅이 보게 될 그대로."""
    L = LAYOUT[disc]
    out = {}
    for pi, pool in enumerate(L["pools"]):
        for i, v in enumerate(table_entries(exe, pool)):
            if v >= 0x8000:
                continue
            p = pool["base"] + v
            raw = []
            while True:
                if p >= pool["end"]:
                    raise PoolPackError(f"풀{pi + 1} 항목 {i}: 종결 없이 풀 밖으로 나간다")
                w = _u16(exe, p)
                raw.append(w)
                p += 2
                if w == TERM_FFFF:
                    break
            out[(pi, i)] = expand_codes(raw, merges)
    return out


def verify(exe, exe_orig, disc, rows, encode, pl):
    """[사유] — 되읽은 모든 표 항목이 기대값과 같은가 · 제어 항목·표 크기 보존 · 펼친 길이가 버퍼에 드는가."""
    bad = []
    want = expected_streams(exe_orig, disc, rows, encode)
    got = read_streams(exe, disc, pl["merges"])
    for k in sorted(want):
        if got.get(k) != want[k]:
            bad.append(f"풀{k[0] + 1} 항목 {k[1]}: 되읽은 코드열이 정본과 다르다 ({len(got.get(k, []))} vs {len(want[k])}코드)")
        elif len(want[k]) > BUF_CODES:
            bad.append(f"풀{k[0] + 1} 항목 {k[1]}: 펼친 {len(want[k])}코드 > 버퍼 {BUF_CODES}")
    L = LAYOUT[disc]
    for pi, pool in enumerate(L["pools"]):
        a = table_entries(exe_orig, pool)
        b = table_entries(exe, pool)
        if len(a) != len(b) or any((x >= 0x8000 or y >= 0x8000) and x != y for x, y in zip(a, b)):
            bad.append(f"풀{pi + 1}: 제어 항목이 바뀌었거나 표 크기가 다르다")
    return bad
