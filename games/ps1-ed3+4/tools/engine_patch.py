"""엔진 패치 — 대사창 공백을 8px 로 (VWF 축소판). 지금은 ED3 만.

## 왜 엔진을 고치나

이 엔진은 글자 피치가 **코드당 12px 고정**이라 좁게 그려도 한 칸이다. 공백은 첫 씬 실측으로
전체 칸의 16%(1,785칸 중 278)라, 공백만 8px 로 보내면 **5% 남짓**을 번다(유저 판정 2026-09-07:
한글은 전각 유지, 공백만 반각).

## 렌더 구조 (2026-09-07, `ED3.EXE` 디스어셈블 + 에뮬 실측)

    창 열기   0x800174A0(x, y, cols, rows)  — 스프라이트 격자를 **글자를 모르는 채로** 미리 깐다.
              열 간격은 0x800178B0 `addiu v1,v0,0xc` (8 로 바꾸니 화면 전체가 8px 피치 — 증명).
              대사창은 0x80039B30.. 다섯 곳에서 (4, 4|0x9E, 24, 4) 로 연다.
    글리프    0x80018758 op 2 — 코드 → 폰트 18B → 4bpp 12×13 타일을 VRAM 캐시 칸(slot)에 올린다.
              0x80018AB4 가 코드를 읽고 0x80018ACC 가 폰트 베이스를 만든다.       ← 훅 A
    배정      없다 — 격자를 깔 때 칸 k 의 UV 가 캐시 슬롯 base+k 로 **고정**된다(0x8001783C).
              페이지가 바뀌어도 스프라이트는 안 건드리고 타일만 갈아 끼운다.
              ⚠ 그래서 「UV 를 쓰는 자리」(0x8001C7B4)에 건 훅은 한 번도 안 돌았다 — 플래그
              0x801D67FE 가 선 특수 경우에만 도는 함수였다(2026-09-07 실측).
    칸 색인   slot = 창.slotbase(+0xE) + 행(+0x14) × 열수(+6) + 열(+0x12)  (0x80039584)
    창 핸들   0x801D6498 부터 22B × 12 — +0 사용중 · +2 x(−160) · +4 y · +6 열 · +8 행 ·
              +0xA 스프라이트 시작 · +0xE 슬롯 시작. 스프라이트 배열 0x800CEA80(20B, 더블버퍼 +0x5000).

## 훅 하나 — 타일을 올리는 순간이 x 를 정할 수 있는 유일한 자리

    글리프를 올릴 때(slot, code 를 안다):
      ① SLOTW[slot] = 공백이면 8, 아니면 12
      ② slot 이 속한 창 핸들을 12개에서 찾는다(slotbase ≤ slot < slotbase + 열×행)
      ③ x = 창.x + 12 + Σ(그 행에서 앞선 칸의 SLOTW) 를 스프라이트 두 벌(+0 · +0x5000)에 쓴다
    앞선 칸은 늘 먼저 올라오므로(색인 순 · 타자기 순) 그 폭은 이미 표에 있다.

격자 열 수는 24 → 32 로 올린다(공백이 좁아진 만큼 한 줄에 글자가 더 들어가야 값이 난다).
슬롯 441 · 스프라이트 1,024 안에서 4×32 = 128 이라 여유가 있다.

## 어디에 넣나

코드와 표는 **죽은 함수** 0x8008DAD4(1,092B — jal 표적·점프표·lui/addiu 참조·분기 유입이 하나도
없는 프롤로그)에 넣는다. 이미지 안의 0 런은 전부 BSS 배열이라 못 쓴다(참조 스캔으로 확인).
⚠ 쓰기 전에 그 구간의 sha1 과 훅 자리의 원본 워드를 **대조한다** — 다른 덤프거나 두 번 적용하면
  거기서 선다(체크리스트 2).

## 검산

손 인코딩이라 `verify` 가 capstone 으로 셋을 본다 — ① 끊김 없이 디코드 ② 지연 슬롯에 분기가
없다 ③ **로드 지연**(R3000 은 lw/lhu/lbu 바로 다음 명령이 그 레지스터를 못 읽는다). ps1-ed1+2 의
`verify_asm` 과 같은 이유(그 트랙에서 반나절을 태웠다).
"""

import hashlib
import re
import struct

import capstone
import font

# 격자 열 수 — `typeset.COLS` 가 같은 값을 쓴다(한 줄에 들어가는 글리프 수의 상한).
COLS = 32

ED3 = {
    "cols_sites": (0x80039B30, 0x80039BA0, 0x80039BC8, 0x80039C04, 0x80039C2C),
    "cols_orig": 0x24060018,  # addiu a2, zero, 0x18
    "site_a": 0x80018ACC,
    "site_a_orig": (0x3C05800A, 0x24A5E170),  # lui a1,0x800a · addiu a1,a1,-0x1e90
    "handles": 0x801D6498,  # 창 핸들 표 (22B × 12)
    "prims": 0x800CEA80,  # 스프라이트 배열 (20B × 0x400, 더블버퍼 +0x5000)
    "dead": 0x8008DAD4,
    "dead_len": 1092,
    "dead_sha1": "748d1ea80bb0dd5c9e2798f31bcea3d07f4c2fbc",
    "table_off": 0x22C,  # SLOTW — 코드 뒤. 0x200B (칸 색인 & 0x1FF)
    "table_len": 0x200,
}
PATCH = {"ed3": ED3}  # ED4 는 렌더러가 따로라(0x800164F0) 아직 안 찾았다 — 없으면 건너뛴다

# ── 손 어셈블러 (MIPS I · 리틀엔디언) — 쓰는 명령만 ─────────────────────────────────
_R = {
    n: i
    for i, n in enumerate(
        [
            "zero",
            "at",
            "v0",
            "v1",
            "a0",
            "a1",
            "a2",
            "a3",
            "t0",
            "t1",
            "t2",
            "t3",
            "t4",
            "t5",
            "t6",
            "t7",
            "s0",
            "s1",
            "s2",
            "s3",
            "s4",
            "s5",
            "s6",
            "s7",
            "t8",
            "t9",
            "k0",
            "k1",
            "gp",
            "sp",
            "fp",
            "ra",
        ]
    )
}
_LOADS = {"lb": 0x20, "lh": 0x21, "lw": 0x23, "lbu": 0x24, "lhu": 0x25}
_STORES = {"sb": 0x28, "sh": 0x29, "sw": 0x2B}
_RTYPE = {"addu": 0x21, "subu": 0x23, "and": 0x24, "or": 0x25, "slt": 0x2A, "sltu": 0x2B}


def _reg(s):
    return _R[s.strip().lstrip("$")]


def _i(op, rs, rt, imm):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _r(fn, rs, rt, rd, sa=0):
    return (rs << 21) | (rt << 16) | (rd << 11) | (sa << 6) | fn


def asm(text, base):
    """[워드] — 라벨 2-pass. 한 줄 한 명령, 지연 슬롯은 손으로 채운다."""
    lines = [ln.split("#")[0].strip() for ln in text.strip().splitlines()]
    lines = [ln for ln in lines if ln]
    labels, body, pc = {}, [], base
    for ln in lines:
        if ln.endswith(":"):
            labels[ln[:-1]] = pc
            continue
        body.append((pc, ln))
        pc += 4
    words = []
    for pc, ln in body:
        op, _, rest = ln.partition(" ")
        a = [x.strip() for x in rest.split(",")] if rest else []

        def target(s):
            return labels[s] if s in labels else int(s, 0)

        if op == "nop":
            w = 0
        elif op in _LOADS or op in _STORES:
            m = re.match(r"(-?\w+)\((\$?\w+)\)", a[1])
            w = _i((_LOADS | _STORES)[op], _reg(m.group(2)), _reg(a[0]), int(m.group(1), 0))
        elif op == "addiu":
            w = _i(9, _reg(a[1]), _reg(a[0]), int(a[2], 0))
        elif op == "li":
            v = int(a[1], 0)
            assert -0x8000 <= v <= 0xFFFF, ln
            w = _i(9 if v < 0 else 0xD, 0, _reg(a[0]), v)
        elif op == "lui":
            w = _i(0xF, 0, _reg(a[0]), int(a[1], 0))
        elif op in ("ori", "andi", "slti"):
            w = _i({"ori": 0xD, "andi": 0xC, "slti": 0xA}[op], _reg(a[1]), _reg(a[0]), int(a[2], 0))
        elif op in _RTYPE:
            w = _r(_RTYPE[op], _reg(a[1]), _reg(a[2]), _reg(a[0]))
        elif op == "move":
            w = _r(0x21, _reg(a[1]), 0, _reg(a[0]))
        elif op in ("sll", "sra", "srl"):
            w = _r({"sll": 0, "srl": 2, "sra": 3}[op], 0, _reg(a[1]), _reg(a[0]), int(a[2], 0))
        elif op == "div":
            w = _r(0x1A, _reg(a[1]), _reg(a[2]), 0)
        elif op == "mult":
            w = _r(0x18, _reg(a[0]), _reg(a[1]), 0)
        elif op in ("mflo", "mfhi"):
            w = _r(0x12 if op == "mflo" else 0x10, 0, 0, _reg(a[0]))
        elif op == "jr":
            w = _r(8, _reg(a[0]), 0, 0)
        elif op in ("j", "jal"):
            w = ((2 if op == "j" else 3) << 26) | ((target(a[0]) >> 2) & 0x3FFFFFF)
        elif op in ("beq", "bne"):
            w = _i(4 if op == "beq" else 5, _reg(a[0]), _reg(a[1]), (target(a[2]) - pc - 4) >> 2)
        elif op in ("blez", "bgtz", "bgez", "bltz"):
            code, rt = {"blez": (6, 0), "bgtz": (7, 0), "bgez": (1, 1), "bltz": (1, 0)}[op]
            w = _i(code, _reg(a[0]), rt, (target(a[1]) - pc - 4) >> 2)
        else:
            raise ValueError(f"모르는 명령: {ln}")
        words.append(w & 0xFFFFFFFF)
    return words, labels


_BRANCH = {"j", "jal", "jr", "jalr", "beq", "bne", "blez", "bgtz", "bgez", "bltz", "beqz", "bnez"}
_ALL_SRC = _BRANCH | {"sb", "sh", "sw", "div", "divu", "mult", "multu"}


def verify(words, base):
    """손 인코딩 검산 — ① 끊김 없이 디코드 ② 지연 슬롯에 분기 없음 ③ 로드 지연 위반 없음.

    ⚠ 재조립 대조까지는 못 한다(capstone 은 디스어셈블러다). 의미는 사람이 본다.
    """
    md = capstone.Cs(
        capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN
    )
    blob = b"".join(struct.pack("<I", w) for w in words)
    ins = list(md.disasm(blob, base))
    if len(ins) != len(words):
        raise AssertionError(f"디코드가 끊겼다 — {len(ins)}/{len(words)} (base {base:#x})")

    def regs(s):
        return set(re.findall(r"\$\w+", s))

    for k, i in enumerate(ins):
        nxt = ins[k + 1] if k + 1 < len(ins) else None
        if nxt is None:
            continue
        if i.mnemonic in _BRANCH and nxt.mnemonic in _BRANCH:
            raise AssertionError(f"{i.address:#x}: 지연 슬롯에 분기가 또 있다 ({nxt.mnemonic})")
        if i.mnemonic in _LOADS or i.mnemonic in ("mflo", "mfhi"):
            dest = i.op_str.split(",")[0].strip()
            ops = [x.strip() for x in nxt.op_str.split(",")]
            src = ops if nxt.mnemonic in _ALL_SRC else ops[1:]
            if dest in regs(", ".join(src)):
                raise AssertionError(
                    f"{i.address:#x}: 로드 지연 — {nxt.mnemonic} 이 {dest} 를 바로 읽는다"
                )
    return "\n".join(f"{i.address:08x}  {i.mnemonic:6s} {i.op_str}" for i in ins)


# ── 훅 본문 ────────────────────────────────────────────────────────────────────────
def hooks(disc, space_code, space_w):
    """[워드] — 훅 본문(`dead` 에 놓인다). `verify` 까지 통과한 뒤 돌려준다.

    들어올 때(0x80018ACC 에서 jal): a2 = 코드, 0x10(fp) = 칸 색인 + 1. v0·v1·a0·a2 는 호출부가
    뒤에 쓰므로 **t 레지스터만** 쓴다. 돌아갈 때 a1 = 폰트 베이스(덮어쓴 두 명령을 대신한다).
    """
    p = PATCH[disc]
    slotw = p["dead"] + p["table_off"]
    fb_hi, fb_lo = font.FONTS[disc]["ram"] >> 16, font.FONTS[disc]["ram"] & 0xFFFF
    fb_lo = fb_lo - 0x10000 if fb_lo >= 0x8000 else fb_lo  # addiu 는 부호 확장
    fb_hi += 1 if fb_lo < 0 else 0
    src = f"""
      lh    t0, 0x10(fp)
      li    t1, 12
      li    t2, {space_code}
      addiu t0, t0, -1              # s = 칸 색인
      bne   a2, t2, keep
      andi  t0, t0, 0x1ff           # (지연 슬롯 — 늘 실행) 표 범위로
      li    t1, {space_w}
    keep:
      lui   t2, {slotw >> 16:#x}
      ori   t2, t2, {slotw & 0xFFFF:#x}
      addu  t3, t2, t0
      sb    t1, 0(t3)               # ① SLOTW[s] = 폭
      lui   t4, {p["handles"] >> 16:#x}
      ori   t4, t4, {p["handles"] & 0xFFFF:#x}
      li    t5, 12                  # ② 핸들 12개를 훑는다
    scan:
      lhu   t6, 0(t4)               # 사용중
      lhu   t7, 0xe(t4)             # slotbase
      beq   t6, zero, next
      lhu   t8, 6(t4)               # 열
      lhu   t9, 8(t4)               # 행
      subu  t6, t0, t7              # k = s - slotbase
      bltz  t6, next
      nop
      mult  t8, t9
      mflo  t9
      nop
      slt   t9, t6, t9              # k < 열×행 ?
      bne   t9, zero, found
      nop
    next:
      addiu t5, t5, -1
      bne   t5, zero, scan
      addiu t4, t4, 22
      j     out
      nop
    found:
      div   zero, t6, t8            # k / 열 → 나머지 = 열 번호
      lhu   t9, 2(t4)               # 창.x
      mfhi  t5                      # col
      move  t1, zero                # j = 0
      addiu t9, t9, 12              # ③ x = 창.x + 12 (격자 원점)
      subu  t3, t0, t5              # 행 첫 슬롯 = s - col
      andi  t3, t3, 0x1ff
      beq   t5, zero, place
      addu  t3, t2, t3              # &SLOTW[행 첫]
    sum:
      lbu   t7, 0(t3)
      addiu t1, t1, 1
      addiu t3, t3, 1
      addu  t9, t9, t7              # x += 앞선 칸 폭
      bne   t1, t5, sum
      nop
    place:
      lhu   t7, 0xa(t4)             # 스프라이트 시작
      lui   t3, {p["prims"] >> 16:#x}
      ori   t3, t3, {p["prims"] & 0xFFFF:#x}
      addu  t7, t7, t6              # + k
      sll   t1, t7, 2
      addu  t1, t1, t7              # ×5
      sll   t1, t1, 2               # ×20
      addu  t3, t3, t1              # 스프라이트
      sh    t9, 8(t3)               # .x (버퍼 0)
      addiu t3, t3, 0x5000
      sh    t9, 8(t3)               # .x (버퍼 1)
    out:
      lui   a1, {fb_hi:#x}
      jr    ra
      addiu a1, a1, {fb_lo}
    """
    words, _ = asm(src, p["dead"])
    verify(words, p["dead"])
    assert 4 * len(words) <= p["table_off"], "훅 코드가 표 자리를 침범한다"
    return words


def _off(ram):
    return ram - font.EXE_TADDR + font.EXE_HDR


def _expect(exe, ram, words, what):
    got = struct.unpack_from(f"<{len(words)}I", exe, _off(ram))
    if tuple(got) != tuple(words):
        raise SystemExit(
            f"🔴 엔진 패치 사전조건 — {what} {ram:#x} 의 원본이 다르다: "
            f"{' '.join(f'{w:08x}' for w in got)} ≠ {' '.join(f'{w:08x}' for w in words)}"
        )


def apply(exe, disc, table, space_w=None):
    """실행파일(bytearray)에 훅을 넣는다. 그 디스크에 패치가 없으면 None."""
    import typeset

    p = PATCH.get(disc)
    if p is None or " " not in table:
        return None
    space_w = typeset.WIDTHS[disc][" "] if space_w is None else space_w
    # 사전조건 — 다른 덤프거나 두 번 적용이면 여기서 선다
    d0 = _off(p["dead"])
    got = hashlib.sha1(bytes(exe[d0 : d0 + p["dead_len"]])).hexdigest()
    if got != p["dead_sha1"]:
        raise SystemExit(
            f"🔴 엔진 패치 사전조건 — 죽은 구간 {p['dead']:#x} 의 sha1 이 다르다 ({got[:12]})"
        )
    _expect(exe, p["site_a"], p["site_a_orig"], "훅 자리")
    for s in p["cols_sites"]:
        _expect(exe, s, (p["cols_orig"],), "창 열 수")

    words = hooks(disc, table[" "], space_w)
    struct.pack_into(f"<{len(words)}I", exe, d0, *words)
    t0 = d0 + p["table_off"]
    exe[t0 : t0 + p["table_len"]] = bytes(p["table_len"])
    jal_a = (3 << 26) | ((p["dead"] >> 2) & 0x3FFFFFF)
    struct.pack_into("<II", exe, _off(p["site_a"]), jal_a, 0)
    for s in p["cols_sites"]:
        struct.pack_into("<I", exe, _off(s), (p["cols_orig"] & 0xFFFF0000) | COLS)
    return f"공백 {space_w}px · 열 {COLS} · 훅 {len(words)}워드 @ {p['dead']:#x}"
