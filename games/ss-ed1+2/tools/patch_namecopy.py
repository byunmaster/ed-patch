"""몬스터 이름(`…A`·`…B` 접미 포함) 고정 폭 복사를 **NUL 종단 복사**로 바꾼다 — ED2 몬스터 오버레이.

    python3 tools/patch_namecopy.py            # 조립·검산만
    python3 tools/patch_namecopy.py --apply    # 빌드 이미지에 넣는다

## 무엇이 문제였나 (2026-10-09, `check_fixed_copy` 를 오버레이로 넓히다 드러났다)

`/BIN/ED2MON02·03·06·08` 에는 이름을 **원문 길이만큼만** 언롤로 퍼 나르는 자리가 있다
(`mov.b @r1+,r3 · add #1,r2 · mov.b r3,@r2` × N). 목적지는 이름 버퍼 `0x0609F561` 이다.

    炎の騎士Ａ    10B (NUL 없음 — 고정 폭)   → 우리 `불꽃의 기사A` 12B  (뒤 2B 가 잘린다)
    砂もぐらＣ    10B + NUL = 11B            → 우리 `모래두더지C` 11B + NUL  (종단이 잘린다)
    木人Ａ        6B                         → 우리 `나무인간A` 9B

잘리면 이름 뒤에 **버퍼에 있던 이전 내용**이 이어져 로그에 깨진 이름(「나무인…」 + 꼬리)이 뜬다 — 등장 문구
(`patch_msgcopy.py`)와 같은 계통이다. 상수를 늘리려 해도 언롤이라 바이트로 박혀 있어 못 늘린다 →
`patch_crit_copy.py` 와 같이 **NUL 까지 도는 루프**로 바꾼다.

목적지 버퍼 폭: `0x0609F561` 주변 리터럴 전수 — 다음 필드가 `0x0609F578`(+0x17)에 한 번, 나머지는 `0x0609F5A8`(+0x47)
이다. 우리 이름은 최대 14B 라 넉넉하되 `LIMIT` 로 폭주는 막는다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_fixed_copy as C
import common
import patch_ui as U
import sh2

LIMIT = 24  # 복사 상한(바이트) — 우리 이름 최대 14B, 버퍼는 0x17 이상
FILES = [f"/BIN/ED2MON{i:02d}.BIN" for i in range(1, 11)]
UNIT = bytes.fromhex("631472012230")  # mov.b @r1+,r3 · add #1,r2 · mov.b r3,@r2
HEAD = bytes.fromhex("27206273")  # mov.b r2,@r7 · mov r7,r2   (첫 글자는 앞에서 r2 에 읽어 뒀다)
TAIL = bytes.fromhex("7201611063732210")  # add #1,r2 · mov.b @r1,r1 · mov r7,r3 · mov.b r1,@r2
# 변형 B — 목적지가 r2 에 이미 있고(앞에서 적재), 첫 UNIT 의 `add #1,r2` 자리에 **다른 명령(채움)** 이 끼어 있다:
#   mov.b @r1+,r3 · <채움> · mov.b r3,@r2 · (UNIT × n) · mov.b @r1,r1 · add #1,r2 · mov.b r1,@r2
FIRST_B = ("6314", None, "2230")
TAIL_B = bytes.fromhex("611072012210")


def _asm_fill(word):
    """첫 UNIT 에 끼어 있던 채움 명령 하나를 그대로 다시 낸다 — `mov #imm,rN` 과 `add #imm,rN` 만 안다."""
    op, n, imm = word >> 12, (word >> 8) & 15, word & 0xFF
    if op == 0xE:
        return f"mov   #{imm - 256 if imm > 127 else imm},r{n}"
    if op == 0x7:
        return f"add   #{imm - 256 if imm > 127 else imm},r{n}"
    return None


def routine_b(base, fill):
    """변형 B 대체 코드. 들어올 때 r1 = 소스 시작 · r2 = 목적지 시작."""
    if isinstance(fill, int):
        # 🔴 채움이 `mov.l @(d,pc),rN` 같은 **자리 의존 명령**이면 옮기면 리터럴 주소가 어긋난다 —
        #   원본 순서(`mov.b @r1+,r3 · 채움 · mov.b r3,@r2`)와 주소를 그대로 두고 그 뒤만 새로 쓴다.
        head = b"\x63\x14" + fill.to_bytes(2, "big")
        rest, body = routine_b(base + 4, None)
        return head + rest, body
    pre = f"{fill}\n        mov.b @r1+,r3" if fill else ""
    src = f"""
        {pre}
        mov.b r3,@r2                ; 첫 글자
        tst   r3,r3
        bt    done
        mov   #{LIMIT},r0
    copy:
        add   #1,r2
        mov.b @r1+,r3
        mov.b r3,@r2
        tst   r3,r3
        bt    done                  ; 🔴 NUL 까지 옮긴다
        add   #-1,r0
        tst   r0,r0
        bf    copy
    done:
        nop
    """
    return sh2.assemble(src.splitlines(), base)


def routine(base):
    """제자리 대체 코드. 들어올 때 r1 = 소스 둘째 바이트 · r2 = 첫 바이트 · r7 = 목적지 시작."""
    src = f"""
        mov.b r2,@r7                ; 첫 글자(앞에서 이미 읽어 r2 에 있다)
        tst   r2,r2
        bt    done
        mov   r7,r2
        mov   #{LIMIT},r0           ; 남은 칸 — 소스가 깨져도 이름 버퍼를 안 넘는다
    copy:
        add   #1,r2
        mov.b @r1,r3
        add   #1,r1
        mov.b r3,@r2
        tst   r3,r3
        bt    done                  ; 🔴 NUL 까지 옮긴다 — 고침의 전부
        add   #-1,r0
        tst   r0,r0
        bf    copy
    done:
        mov   r7,r3                 ; 원 코드가 끝에 하던 일(`mov r7,r3`)
    """
    return sh2.assemble(src.splitlines(), base)


def routine_head_short(base):
    """짧은 런용 NUL 복사(상한 없음 — 소스는 우리 문안이고 칸은 0x17B 이상). r1 = 둘째 글자 · r2 = 첫 글자 · r7 = 목적지."""
    code, _b = sh2.assemble(
        [
            "mov r7,r3",
            "copy:",
            "mov.b r2,@r3",
            "tst r2,r2",
            "bt done",
            "add #1,r3",
            "mov.b @r1+,r2",
            "bra copy",
            "nop",
            "done:",
            "mov r7,r3",
        ],
        base,
    )
    return code, _b


def failing(fname, orig, built):
    """고쳐야 할 언롤 자리 `[(런 오프셋, 복사 길이)]` — 우리 이름이 칸에 안 맞는 곳."""
    bad = {lit for lit, *_ in C.check(fname, orig, built, set())[0]}
    out = []
    for at, cap, srcs in C.sites(orig):
        if any(s[0] in bad for s in srcs):
            out.append((at, cap))
    return out


def build(fname, orig, at):
    """`(넣을 바이트, 오프셋, 복사 길이)` 또는 None — 머리(`mov.b r2,@r7 · mov r7,r2`)부터 꼬리까지를 루프로.

    언롤 개수 `n` 은 연속한 UNIT 을 **직접 센다**(`check_fixed_copy` 의 `cap` 은 꼬리 변형을 못 알아봐 하나 모자랄 수
    있다). 복사 길이 = 첫 글자 1 + n + 꼬리 1.
    """
    n = 0
    while bytes(orig[at + 6 * n : at + 6 * n + 6]) == UNIT:
        n += 1
    start = at - len(HEAD)
    end = at + 6 * n + len(TAIL)
    if bytes(orig[start:at]) != HEAD or bytes(orig[at + 6 * n : end]) != TAIL:
        return _build_b(fname, orig, at)
    size = end - start
    code, _body = routine(C.LOAD_BASE + start)
    assert len(code) <= size, f"{fname}: 새 코드 {len(code)}B > 자리 {size}B"
    return code + b"\x00\x09" * ((size - len(code)) // 2), start, n + 2


def _build_b(fname, orig, at):
    """변형 B — 첫 UNIT(`6314 <채움> 2230`, `check_fixed_copy` 의 런 **앞**에 붙어 있다) + 런 + 꼬리 B."""
    st = at - 6
    first = bytes(orig[st : st + 6])
    if first[0:2] != bytes.fromhex(FIRST_B[0]) or first[4:6] != bytes.fromhex(FIRST_B[2]):
        return None
    word = (first[2] << 8) | first[3]
    fill = (
        word if word >> 12 == 0xD else _asm_fill(word)
    )  # 0xD = mov.l @(d,pc),rN (목적지 주소 적재)
    if fill is None:
        return None
    n = 0
    while bytes(orig[at + 6 * n : at + 6 * n + 6]) == UNIT:
        n += 1
    end = at + 6 * n + len(TAIL_B)
    if bytes(orig[at + 6 * n : end]) != TAIL_B:
        return None
    code, _body = routine_b(C.LOAD_BASE + st, fill)
    size = end - st
    assert len(code) <= size, f"{fname}: 새 코드 {len(code)}B > 자리 {size}B"
    return code + b"\x00\x09" * ((size - len(code)) // 2), st, n + 2


# ── 둘째 패스: 고정 오프셋 복사(슬롯 B·C) · 공유 런으로 뛰어드는 복사 · 런 3 이하 (2026-10-19) ────────────
#
# 위 패스는 `add #1,r2` 연속 꼴만 안다. 그런데 몬스터 슬롯 1(B)은 **목적지를 슬롯 0 기준 고정 오프셋**으로 한 바이트씩 쓴다
#
#     mov.l 소스,r1 · (mov.b @r1+,r2 · add #104,r3 · mov.b r2,@r3 · mov r7,r3) × N · mov.b @r1,r1 · add #(104+N),r3 · mov.b r1,@r3
#
# 슬롯 2(C)는 `bra` 로 **다른 이름과 공유하는 런의 중간**에 뛰어든다(길이가 진입점으로 정해진다). 두 꼴 다 검산에서
# 통째로 빠져 「나무인愛」·「지팡이품」이 화면까지 갔다. 판정은 `check_fixed_copy.semantic_check`(효과를 돌려 잰다)가 하고,
# 여기는 그 목록의 자리를 **꼴별로** 고친다. 모르는 꼴은 조용히 넘기지 않고 실패시킨다.
#
# 고치는 법: 복사 명령만 `nop` 으로 비우고(리터럴을 읽는 `mov.l @(d,pc)` 등 **남의 명령은 제자리**) 앞쪽에 NUL 루프를 둔다.
# 비운 자리는 **패드**로 모아 뒀다가, 자리가 모자란 공유 런 진입(`bra` 4B)이 루프를 거기 두고 뛰어가게 한다.
NOP = b"\x00\x09"
F1_LOOP = 16  # mov · add · (mov.b · mov.b · add · tst · bf) · mov #0,r1
F2_LOOP = 14  # (mov.b · mov.b · add · tst · bf) · bra · mov #0,r1


def _w(d, o):
    return (d[o] << 8) | d[o + 1]


def _bra(at, tgt, delay=0xE100):
    """`bra tgt` + 지연 슬롯(기본 `mov #0,r1`) — `at` 은 bra 의 주소."""
    disp = (tgt - (at + 4)) // 2
    assert (tgt - (at + 4)) % 2 == 0 and -2048 <= disp <= 2047, f"bra 범위 밖: {at:X}→{tgt:X}"
    return (0xA000 | (disp & 0xFFF)).to_bytes(2, "big") + delay.to_bytes(2, "big")


def loop_f1(base, rb, imm0):
    """슬롯 B 대체: `r[rb]+imm0` 에 NUL 까지. 들어올 때 r1 = 소스."""
    code, body = sh2.assemble(
        [
            f"mov r{rb},r3",
            f"add #{imm0},r3",
            "copy:",
            "mov.b @r1+,r2",
            "mov.b r2,@r3",
            "add #1,r3",
            "tst r2,r2",
            "bf copy",
            "mov #0,r1",
        ],
        base,
    )
    assert len(code) == F1_LOOP == body
    return code


def loop_f2(base, bra_to):
    """공유 런 진입 대체: r1 = 소스 · r2 = 목적지. NUL 까지 옮기고 런의 출구(`bra_to`)로 간다."""
    code, _body = sh2.assemble(
        ["copy:", "mov.b @r1+,r3", "mov.b r3,@r2", "add #1,r2", "tst r3,r3", "bf copy"], base
    )
    assert len(code) == 12 and code[10:] == NOP  # 풀 정렬 nop 하나 — 떼고 bra 를 바로 붙인다
    return code[:10] + _bra(base + 10, bra_to)


def plan_f1(d, o):
    """고정 오프셋 복사 계획. `{오프셋: 바이트}` 와 패드 `(오프셋, 길이)` 또는 None."""
    if d[o] != 0xD1:
        return None
    p, n, imm0, rb, copy = o + 2, 0, None, None, []
    while _w(d, p) == 0x6214 and d[p + 2] == 0x73 and _w(d, p + 4) == 0x2320:
        imm = d[p + 3]
        if n == 0:
            imm0 = imm
        if imm != imm0 + n:
            return None
        copy += [p, p + 2, p + 4]
        n += 1
        p += 6
        if (_w(d, p) & 0xFF0F) == 0x6303:  # mov rB,r3
            if rb not in (None, (_w(d, p) >> 4) & 15):
                return None
            rb = (_w(d, p) >> 4) & 15
            copy.append(p)
            p += 2
        else:
            break
    if n < 3 or rb is None or imm0 + n > 127:
        return None
    seen, kept, end, addr = {"ld": 0, "add": 0}, [], None, -1
    for q in range(p, p + 12, 2):
        w = _w(d, q)
        if w == 0x6110:
            seen["ld"] += 1
            copy.append(q)
        elif (w >> 12) == 7 and (w & 0xFF) == imm0 + n:
            seen["add"] += 1
            addr = (w >> 8) & 15
            copy.append(q)
        elif (w & 0xF0FF) == 0x2010:
            if (w >> 8) & 15 != addr:
                return None
            copy.append(q)
            end = q + 2
            break
        elif (w >> 12) == 0xA:  # bra — 저장이 지연 슬롯에 있다. bra 는 제자리에 두고 슬롯만 비운다
            kept.append(q)
        elif (w >> 12) in (0x8, 0xB, 0x4) or w == 0x000B:
            return None  # 분기·호출은 모른다
        else:
            kept.append(q)
    if end is None or seen != {"ld": 1, "add": 1}:
        return None
    if kept and min(kept) < o + 2 + F1_LOOP:
        return None
    padend = min(kept) if kept else end
    return {
        "at": o,
        "rb": rb,
        "imm0": imm0,
        "n": n,
        "nop": copy,
        "end": end,
        "pad": (o + 2 + F1_LOOP, padend),
    }


def plan_f2m(d, base, o):
    """`bra` 로 공유 런 중간에 뛰어드는 복사. 계획 또는 None."""
    if d[o] != 0xD1:
        return None
    p, d2, seq = o + 2, None, []
    while p < o + 0x40:
        w = _w(d, p)
        if (w >> 12) == 0xA:
            break
        if (w >> 8) == 0xD2:
            d2 = p
        elif w not in (0x6314, 0x7201, 0x2230):
            return None
        seq.append(p)
        p += 2
    else:
        return None
    if d2 is None or _w(d, p + 2) not in (0x6314, 0x7201, 0x0009):
        return None
    w = _w(d, p)
    disp = ((w & 0xFFF) ^ 0x800) - 0x800
    x = base + p + 4 + disp * 2
    # 공유 런의 출구
    q = x - base
    while _w(d, q) in (0x6314, 0x7201, 0x2230):
        q += 2
    if _w(d, q) != 0x6110:
        return None
    rest, z, j = [], None, q
    for _ in range(4):
        wj = _w(d, j)
        if wj == 0x6110 or wj == 0x7201 or wj == 0x2210:
            rest.append(wj)
            j += 2
        elif (wj >> 12) == 0xA:
            dsp = ((wj & 0xFFF) ^ 0x800) - 0x800
            z = base + j + 4 + dsp * 2
            if _w(d, j + 2) != 0x2210:
                return None
            j += 4
            break
        else:
            break
    if z is None:
        if sorted(rest) != sorted([0x6110, 0x7201, 0x2210]):
            return None
        z = base + j
    code_at = max(o, d2) + 2
    return {
        "at": o,
        "d2": d2,
        "bra": p,
        "end": p + 4,
        "code_at": code_at,
        "z": z,
        "nop": [x for x in seq if x != d2] + [p, p + 2],
    }


def second_pass(fname, orig, built, base):
    """둘째 패스 계획 `{오프셋: 바이트}` — 의미 검사가 짚은 자리를 꼴별로 고친다. 못 고치는 꼴이 있으면 실패."""
    bad, _seen = C.semantic_check(orig, built, base)
    new = bytearray(built)
    pads, todo = [], []
    starts = sorted(pc - base for pc, *_r in bad)
    for o in starts:
        pl = plan_f1(new, o)
        if pl:
            for c in pl["nop"]:
                new[c : c + 2] = NOP
            code = loop_f1(base + o + 2, pl["rb"], pl["imm0"])
            new[o + 2 : o + 2 + F1_LOOP] = code
            pads.append(list(pl["pad"]))
        else:
            todo.append(o)
    rest = []
    for o in todo:
        # 머리가 `mov.b r2,@r7 · mov r7,r2` 인 짧은 런(3 이하) — 위 패스의 `build` 는 32B 라 안 들어간다. 상한 없는 짧은 꼴로 갈음
        if _w(new, o + 2) == 0x6214 and bytes(new[o + 6 : o + 10]) == HEAD:
            n = 0
            while bytes(new[o + 10 + 6 * n : o + 16 + 6 * n]) == UNIT:
                n += 1
            end = o + 10 + 6 * n + len(TAIL)
            if bytes(new[o + 10 + 6 * n : end]) == TAIL:
                code, _b = routine_head_short(base + o + 6)
                assert len(code) <= end - o - 6
                new[o + 6 : end] = code + NOP * ((end - o - 6 - len(code)) // 2)
                continue
        pl = plan_f2m(new, base, o)
        if not pl:
            rest.append(o)
            continue
        for c in pl["nop"]:
            new[c : c + 2] = NOP
        if pl["end"] - pl["code_at"] >= F2_LOOP:
            at = pl["code_at"]
            new[at : at + F2_LOOP] = loop_f2(base + at, pl["z"])
            pads.append([at + F2_LOOP, pl["end"]])
            continue
        # 자리가 모자란다 — 패드에 루프를 두고 `bra` 로 간다
        if pl["end"] - pl["code_at"] < 4:
            rest.append(o)
            continue
        for pd in pads:
            if pd[1] - pd[0] >= F2_LOOP and abs(pd[0] - o) < 3000:
                at = pd[0]
                pd[0] += F2_LOOP
                new[at : at + F2_LOOP] = loop_f2(base + at, pl["z"])
                new[pl["code_at"] : pl["code_at"] + 4] = _bra(
                    base + pl["code_at"], base + at, 0x0009
                )
                break
        else:
            rest.append(o)
    assert not rest, f"{fname}: 못 고친 이름 복사 {[hex(base + o) for o in rest]} — 새 꼴이다"
    return new


def second_main(apply, dst, files):
    """둘째 패스를 돌린다 — 이미지에서 현재 바이트를 읽어 의미 검사가 짚은 자리만 고친다."""
    f2, mm2 = common.open_image(dst)
    total = 0
    try:
        for fname in FILES + ["/ED.BIN"]:
            base = U.ptr_base(fname)
            C.LOAD_BASE = base
            lba, fsize = files[fname]
            orig = bytes(common.extract(fname))
            cur = bytes(common.read_extent(mm2, lba, fsize))
            bad, _n = C.semantic_check(orig, cur, base)
            if not bad:
                continue
            total += len(bad)
            for pc, ol, ou, n, why in bad:
                print(f"  ⚠ {fname}: 0x{pc:08X} 원본 {ol}B · 우리 {ou}B · 복사 {n}B — {why}")
            if not apply:
                continue
            new = bytes(second_pass(fname, orig, cur, base))
            left, _n = C.semantic_check(orig, new, base)
            assert not left, f"{fname}: 고친 뒤에도 잘리는 자리 {[hex(x[0]) for x in left]}"
            diff = [i for i in range(len(new)) if new[i] != cur[i]]
            chunks = []
            for i in diff:  # 16B 안쪽 틈은 한 덩이로 묶는다
                if chunks and i - chunks[-1][1] < 16:
                    chunks[-1][1] = i + 1
                else:
                    chunks.append([i, i + 1])
            with open(dst, "r+b") as f:
                for a, b in chunks:
                    common.write_at(
                        f, lba, fsize, a, new[a:b], label=f"{fname} 이름 복사(2)", expect=cur[a:b]
                    )
            print(f"  {fname}: 둘째 패스 {len(bad)}곳 · 바이트 덩이 {len(chunks)}")
    finally:
        mm2.close()
        f2.close()
    return total


def main():
    apply = "--apply" in sys.argv
    common.verify_source()
    _f, mm = common.open_image()
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    files = common.dst_files(dst, mm)
    if not os.path.exists(dst):
        raise SystemExit(f"먼저 다른 패처를 돌린다 — {dst} 가 없다")
    _fd, mmd = common.open_image(dst)
    total = 0
    for fname in FILES:
        C.LOAD_BASE = U.ptr_base(fname)
        orig = common.extract(fname)
        lba, fsize = files[fname]
        built = bytes(common.read_extent(mmd, lba, fsize))
        todo = failing(fname, orig, built)
        total += len(todo)
        for at, cap in todo:
            got = build(fname, orig, at)
            if got is None:
                print(
                    f"  ⚠ {fname}: 0x{C.LOAD_BASE + at:08X} — 머리·꼬리가 다른 변형이라 못 바꿨다 (칸 {cap}B)"
                )
                continue
            blob, start, cap = got
            was = bytes(orig[start : start + len(blob)])
            cur = bytes(built[start : start + len(blob)])
            print(f"{fname}: 0x{C.LOAD_BASE + start:08X} 언롤 {cap}B → 루프 ({len(blob)}B)")
            if apply:
                assert cur in (was, blob), f"{fname} 0x{start:X}: 원본도 우리 것도 아니다"
                with open(dst, "r+b") as f:
                    common.write_at(
                        f, lba, fsize, start, blob, label=f"{fname} 이름 복사", expect=cur
                    )
    mmd.close()
    second_main(apply, dst, files)
    if apply:
        print(f"  → 넣음 · {total}곳 (이미 넣었으면 0)")
        # 🔴 되읽기 — 넣은 뒤엔 어긋나는 언롤이 **0** 이어야 한다(`check_fixed_copy` 와 같은 눈금)
        _fd2, mm2 = common.open_image(dst)
        left = 0
        for fname in FILES:
            C.LOAD_BASE = U.ptr_base(fname)
            lba, fsize = files[fname]
            rest = failing(fname, common.extract(fname), bytes(common.read_extent(mm2, lba, fsize)))
            left += len(rest)
            for at, cap in rest:
                print(f"  ⚠ 남음 {fname}: 0x{C.LOAD_BASE + at:08X} 칸 {cap}B")
        mm2.close()
        assert left == 0, f"이름 복사가 어긋나는 언롤이 {left}곳 남았다"
        print("  ✅ 되읽기 — 어긋나는 이름 복사 0")
    else:
        print(f"  (검산만 — {total}곳 · 실제로 넣으려면 `--apply`)")


if __name__ == "__main__":
    main()
