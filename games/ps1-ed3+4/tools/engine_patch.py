"""엔진 패치 — 대사창 공백을 6px(반 칸)로 (VWF 축소판). 지금은 ED3 만.

🔴 2026-10-07 마스터 「대사창 공백 반각」 — 8px(2/3 칸)에서 6px(1/2 칸)로 내렸다(`typeset.WIDTHS` 가 같은 값을 쓴다).
   아래 본문의 「8px」 는 옛 값이다.

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
      ③ x = 틀.x + 12 + Σ(그 행에서 앞선 칸의 SLOTW) 를 스프라이트 두 벌(+0 · +0x5000)에 쓴다
         🔴 **틀.x = 틀 첫 스프라이트(= 격자 칸 수 바로 뒤, 왼쪽 위 모서리)의 x 다 — 핸들 x 가
         아니다**(2026-10-05). 창 이동(슬라이드)은 핸들 x 를 먼저 바꾸고 스프라이트는
         **op 6 이 첫 칸의 현재 x 를 기준으로 델타**(0x80019660)로 옮긴다. 그 사이에 훅이 핸들 x
         로 첫 칸을 미리 옮겨 놓으면 델타가 0 이 되어 **틀만 제자리에 남는다** — 팝업이 틀보다 8·16px
         앞서 글자가 왼쪽 테두리를 밟는(「세이브/로드 밀림」) 증상의 원인이다. 원판엔 훅이 없어 없다.

    🔴 **압축은 대사창(열 24)에서만 한다**(2026-10-05). 목록·상세 패널·팝업(열 3~14)은 페이지를 넘겨
    다시 그릴 때 **칸 폭 표(SLOTW)와 스프라이트 x 가 어긋나** 「라그픽 마을」의 「마」가 「ㅁ」으로 덮이고
    시간 숫자 사이가 벌어졌다(마스터: 페이지 2 갔다가 1 로 돌아오면 깨짐). 공백을 12px 로 두면
    같은 재현이 깨끗해 압축이 원인임을 확정했다. UI 창엔 이득도 없다(칸 수가 늘지 않는다).
    앞선 칸은 늘 먼저 올라오므로(색인 순 · 타자기 순) 그 폭은 이미 표에 있다.

격자 열 수를 24 → 32 로 올리면 공백이 좁아진 만큼 글자가 더 들어간다. 🔴 **그런데 지금은
24 다** — 32 로 올리면 `▼`(다음 페이지)가 사라지고 그 자리를 아직 못 찾았다(2026-09-07).

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
# `COLS == FRAME_COLS` 면 틀 보정 훅을 아예 안 넣는다(넣으면 오히려 원판과 달라진다).
# 🔴 **24 로 되돌렸다**(2026-09-07). 32 로 올리면 `▼`(다음 페이지)가 사라진다 — 열 24 빌드와
#    픽셀 대조로 **원인이 열 수임을 확정**했고(34픽셀, x 314~318), 그 x 를 계산하는 자리는
#    아직 못 찾았다(글리프 업로드·UV 기록·스크롤·`0x80039904` 넷 다 아니다).
#    ⚠ 열을 안 늘리면 공백 8px 의 **이득이 거의 없다**(한 줄 상한이 24 글리프 그대로다).
#    그래도 24 로 둔다 — 방침 「원판과 같아지면 픽스, 나아지면 개조」이고, 사라진 `▼` 는
#    유저가 매 창에서 보는 결함이다. 자리를 찾으면 그때 32 로 올린다.
COLS = 24
# 틀 폭(열) — 원판이 그리는 폭(288px). 격자를 늘렸을 때만 이 값으로 되돌린다.
# 유저 실측 2026-09-07: 열 32 로 올리자 틀이 그걸 따라 그려져 오른쪽 화면 밖으로 나갔다.
FRAME_COLS = 24
# 틀 밖 빈 칸을 보내는 거리(px). GPU 는 그리기 영역 밖 스프라이트를 안 그린다.
OFFSCREEN = 600

ED3 = {
    "cols_sites": (0x80039B30, 0x80039BA0, 0x80039BC8, 0x80039C04, 0x80039C2C),
    "cols_orig": 0x24060018,  # addiu a2, zero, 0x18
    "site_a": 0x80018ACC,
    "site_a_orig": (0x3C05800A, 0x24A5E170),  # lui a1,0x800a · addiu a1,a1,-0x1e90
    # 틀 — 오른쪽 변의 x 를 열 수에서 계산하는 자리(`lhu v1,0x14(fp)` · nop): 32 면 24 로 준다.
    "frame_edge": 0x80017D30,
    "frame_edge_orig": (0x97C30014, 0x00000000),
    # 격자 칸 · 위·아래 막대 루프의 x 전진(`addiu v1,v0,0xc` · `sh v1,0x2e(fp)`): 24번째까지는
    # +12, 25번째는 +612(화면 밖으로), 그 뒤는 +0. 빈 격자 칸은 **검은 캐시 타일**을 그리므로
    # (창 내부의 어두운 상자가 곧 격자 셀이다) 틀 밖에 두면 검은 띠가 되고, 마지막 칸 위에
    # 겹치면 반투명이 겹쳐 그 열만 진해진다 — 그래서 화면 밖이다. 글리프가 올라간 칸은 훅 A 가
    # x 를 다시 정하니 어디 있었든 상관없다. ⚠ 루프 횟수(32)는 건드리지 않는다 — 막대 타일도
    # 슬롯·스프라이트를 소비하므로 횟수를 줄이면 글리프 칸 배치가 통째로 어긋난다(09-07 실측:
    # 글자가 엉뚱한 칸으로 가 「크리」에서 멈춘 것처럼 보였다).
    "frame_bars": ((0x800178B0, "bar_top"), (0x80017AF0, "bar_top"), (0x8001804C, "bar_bot")),
    "frame_bar_orig": (0x2443000C, 0xA7C3002E),
    # `▼`(다음 페이지)는 글리프가 아니라 **열 수로 x 를 잡는 별도 자리**다 —
    # `lhu v1,0x649e(at)`(= 핸들+6 = 열) 뒤에 x 에 더한다. 열이 32 가 되며 화면 밖으로 나갔다.
    "prompt_site": 0x80039904,
    "prompt_orig": (0x9423649E, 0x00000000),
    "handles": 0x801D6498,  # 창 핸들 표 (22B × 12)
    "prims": 0x800CEA80,  # 스프라이트 배열 (20B × 0x400, 더블버퍼 +0x5000)
    "dead": 0x8008DAD4,
    "dead_len": 1092,
    "dead_sha1": "748d1ea80bb0dd5c9e2798f31bcea3d07f4c2fbc",
    "table_off": 0x244,  # 훅 코드 상한(옛 칸 종류 표 자리 — 지금은 안 쓰고 0 으로 지운다). 죽은 함수 끝(0x444)
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
        elif op in ("ori", "andi", "slti", "sltiu"):
            w = _i(
                {"ori": 0xD, "andi": 0xC, "slti": 0xA, "sltiu": 0xB}[op],
                _reg(a[1]),
                _reg(a[0]),
                int(a[2], 0),
            )
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
def hooks(disc, space_code, space_w, paren_codes=(0x7FFF, 0x7FFF), with_frame=None):
    """[워드] — 훅 본문(`dead` 에 놓인다). `verify` 까지 통과한 뒤 돌려준다.

    들어올 때(0x80018ACC 에서 jal): a2 = 코드, 0x10(fp) = 칸 색인 + 1. v0·v1·a0·a2 는 호출부가
    뒤에 쓰므로 **t 레지스터만** 쓴다. 돌아갈 때 a1 = 폰트 베이스(덮어쓴 두 명령을 대신한다).
    """
    p = PATCH[disc]
    fb_hi, fb_lo = font.FONTS[disc]["ram"] >> 16, font.FONTS[disc]["ram"] & 0xFFFF
    fb_lo = fb_lo - 0x10000 if fb_lo >= 0x8000 else fb_lo  # addiu 는 부호 확장
    fb_hi += 1 if fb_lo < 0 else 0
    src = f"""
      lh    t0, 0x10(fp)
      li    t1, 12
      li    t2, {space_code}
      addiu t0, t0, -1              # s = 칸 색인
      andi  t0, t0, 0x1ff           # 표 범위로
      beq   a2, t2, half            # 공백 → 반 칸
      li    t3, {paren_codes[0]}    # (지연 슬롯) 여는 괄호 `(` — 글리프 자리라 코드가 빌드마다 다르다
      beq   a2, t3, half
      li    t3, {paren_codes[1]}    # (지연 슬롯) 닫는 괄호 `)`
      beq   a2, t3, half
      sltiu t3, a2, 6               # (지연 슬롯) 코드 < 6 ?
      beq   t3, zero, keep          # 부호 코드가 아니면 12 그대로
      li    t2, 3                   # (지연 슬롯)
      beq   a2, t2, keep            # 3 은 부호가 아니다(PUNCT = 1 `,` · 2 `.` · 4 `?` · 5 `!`)
      slti  t3, a2, 1               # (지연 슬롯) 코드 0 ?
      bne   t3, zero, keep
      nop
    half:
      li    t1, {space_w}           # 공백·부호·괄호는 반 칸(6px) — 글리프의 잉크는 왼쪽 5열 안이다
    keep:
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
      li    t7, {COLS}
      bne   t8, t7, out             # 🔴 대사창(열 24)만 만진다 — 목록·패널·팝업은 엔진 자리 그대로(원판)
      mfhi  t5                      # (지연 슬롯) col
      lhu   t7, 8(t4)               # 행
      nop
      mult  t8, t7
      mflo  t7                      # 열×행 = 창의 칸 수
      nop
      addiu t7, t7, -1
      subu  t0, t7, t6              # A = 이 창에서 이 칸 뒤에 남은 칸 수(= 뒤에 타일이 있는 칸 수)
      lhu   t7, 0xa(t4)             # 스프라이트 시작
      lui   t3, {p["prims"] >> 16:#x}
      ori   t3, t3, {p["prims"] & 0xFFFF:#x}
      addu  t7, t7, t6              # + k
      sll   t9, t7, 2
      addu  t9, t9, t7              # ×5
      sll   t9, t9, 2               # ×20
      addu  t3, t3, t9              # t3 = 이 칸의 스프라이트(버퍼 0)
      # ── 줄 첫 칸이면 이 칸부터 창 끝까지(▼ 칸 빼고) 칸 자리를 원래 격자로 되돌린다.
      #    🔴 안 찍힌 줄은 **앞 글에서 당겨진 자리 그대로 남아** 뒤쪽이 뚫려 보였다(2~3줄짜리 대사 뒤의 빈 줄, 2026-10-07).
      #    글은 위에서 아래로 찍히니 줄 첫 칸에서 아랫줄까지 되돌리면 더 안 찍힌 줄도 원래 자리가 된다.
      bne   t5, zero, noreset
      nop
      lh    t7, 8(t3)               # x0 = 행 원점(줄 첫 칸은 훅이 안 건드린다)
      move  t8, t3                  # 스프라이트
      move  t2, t0                  # 되돌릴 칸 수 = 뒤에 남은 칸 수(▼ 칸 제외)
      move  t9, t7                  # x
      li    t4, 12
      li    t6, 24                  # 줄 안 남은 칸 수
    rl:
      sh    t9, 8(t8)
      sh    t9, 0x5008(t8)
      sh    t4, 16(t8)
      sh    t4, 0x5010(t8)
      addiu t9, t9, 12
      addiu t8, t8, 20
      addiu t6, t6, -1
      bne   t6, zero, rl2
      addiu t2, t2, -1              # (지연 슬롯) 남은 칸 수
      move  t9, t7                  # 줄이 끝나면 원점으로
      li    t6, 24
    rl2:
      bne   t2, zero, rl
      nop
    noreset:
      li    t6, 12
      sh    t6, 16(t3)              # 이 칸의 배경 폭을 12 로 되돌린다(앞 글자가 넓혀 놨을 수 있다)
      sh    t6, 0x5010(t3)
      li    t7, {COLS - 1}
      beq   t5, t7, out             # 마지막 칸 — 다음 칸이 없다
      nop
      # ── 안 찍힌 칸들을 이 글자 끝에 붙인다 — **칸 x 는 앞 칸 x + 앞 칸 폭**으로 이어진다(체인).
      #    🔴 안 찍힌 칸은 그동안 원래 격자 자리에 있어 줄 끝에 (절약한 폭)만큼 틈이 났다(대사창 배경이 뚫려 보임,
      #    2026-10-07). 뒤 칸들을 당겨 붙이고 **틈(S)을 폭에 나눠 얹어** 맨 끝(원래 자리)까지 배경을 잇는다.
      #    ⚠ 넓힌 칸은 **옆 타일 텍스처를 같이 읽는다** — 텍스처 한 줄이 타일 21개(u 0~240, 12 간격 — 실측: 스프라이트의
      #    u 가 0x00~0xf0)라 u+폭 이 252 를 넘으면 다른 그림의 텍셀이 배경에 비친다(색 점). **창의 타일은 칸 수만큼뿐**이라(마지막 줄은 12칸) 그 뒤도 쓰레기다 — 칸마다 늘릴 몫을 `min(240 − u, 12 × (뒤 칸 수 − 1))` 로 막는다(마지막 칸은 `▼` 타일).
      sll   t7, t5, 2
      addu  t7, t7, t5
      sll   t7, t7, 2               # col × 20
      subu  t7, t3, t7              # 행 첫 칸 스프라이트
      lh    t7, 8(t7)               # x0 = 행 원점
      lh    t9, 8(t3)               # 이 칸 x
      addiu t6, t5, 1               # col + 1
      sll   t2, t6, 2
      sll   t6, t6, 3
      addu  t6, t6, t2              # 12 × (col+1)
      addu  t9, t9, t1              # x_next = x + 폭(12 또는 6)
      addu  t6, t6, t7              # 원래 자리: x0 + 12(col+1)
      subu  t6, t6, t9              # S = 원래 자리 − x_next (절약한 폭, 0 이상)
      bgez  t6, sok
      nop
      move  t6, zero                # 음수면(이미 오른쪽으로 밀린 칸) 늘리지 않는다
    sok:
      li    t7, {COLS - 1}
      subu  t7, t7, t5              # 남은 칸 수
    fill:
      addiu t3, t3, 20              # 다음 칸 스프라이트
      addiu t0, t0, -1              # 이 칸 뒤에 남은 칸 수
      beq   t0, zero, out           # 🔴 창의 마지막 칸은 `▼`(다음 페이지) 자리다 — 건드리면 화살표 타일이 넓게 비친다
      nop
      sh    t9, 8(t3)               # .x (버퍼 0)
      sh    t9, 0x5008(t3)          # .x (버퍼 1)
      lbu   t8, 12(t3)              # u (텍스처 안 자리)
      li    t2, 240
      subu  t8, t2, t8              # 한 줄 끝까지 = 240 − u
      sll   t2, t0, 3
      sll   t1, t0, 2
      addu  t2, t2, t1              # 12 × (뒤에 타일이 있는 칸 수)
      addiu t2, t2, -12             # 마지막 칸(`▼` 타일)은 읽지 않는다 — 읽으면 회색 화살표 타일이 배경에 비친다
      slt   t1, t2, t8
      beq   t1, zero, capok
      nop
      move  t8, t2                  # 타일이 없는 곳은 읽지 않는다(마지막 텍스처 줄은 12칸뿐 — 그 뒤는 쓰레기 텍셀)
    capok:
      move  t2, t6                  # e = S
      slt   t1, t8, t2
      beq   t1, zero, haveE
      nop
      move  t2, t8                  # e = 상한
    haveE:
      addiu t1, t2, 12              # 폭 = 12 + e
      sh    t1, 16(t3)              # .w (버퍼 0)
      sh    t1, 0x5010(t3)          # .w (버퍼 1)
      addu  t9, t9, t1              # 다음 칸 x
      subu  t6, t6, t2              # S −= e
      addiu t7, t7, -1
      bne   t7, zero, fill
      nop
    out:
      lui   a1, {fb_hi:#x}
      jr    ra
      addiu a1, a1, {fb_lo}
    # ── 틀 오른쪽 변 — `lhu v1,0x14(fp)` 를 대신하되 32 면 24 를 준다. v0 는 살아 있다 — t0 만.
    framew:
      lhu   v1, 0x14(fp)
      li    t0, {COLS}
      bne   v1, t0, framew_out
      nop
      li    v1, {FRAME_COLS}
    framew_out:
      jr    ra
      nop
    # ── `▼` 자리 — `lhu v1,0x649e(at)` 를 대신한다. at 는 jal 이 안 건드린다.
    promptw:
      lhu   v1, 0x649e(at)
      li    t0, {COLS}
      bne   v1, t0, promptw_out
      nop
      li    v1, {FRAME_COLS}
    promptw_out:
      jr    ra
      nop
    # ── 격자·막대 x 전진 — 들어올 때 v0 = x, i = 방금 놓은 타일 번호. i < 23 → +12,
    #    i == 23 → +612(다음 타일부터 화면 밖), 23 < i < 31 → +0, i == 31 → −600(루프 뒤의 x 가
    #    24번째 칸 자리로 돌아온다 — 막대 끝의 **모서리 장식**이 그 x 에 그려진다). 0x2e(fp) 에 쓴다.
    bar_top:
      lh    t0, 0x32(fp)
      j     bar_step
      nop
    bar_bot:
      lh    t0, 0x26(fp)
      nop
    bar_step:
      slti  t1, t0, {FRAME_COLS - 1}
      bne   t1, zero, bar_plus12
      li    t1, {FRAME_COLS - 1}
      beq   t0, t1, bar_jump
      li    t1, {COLS - 1}
      beq   t0, t1, bar_back
      nop
      j     bar_out
      move  v1, v0
    bar_jump:
      j     bar_out
      addiu v1, v0, {12 + OFFSCREEN}
    bar_back:
      j     bar_out
      addiu v1, v0, {-OFFSCREEN}
    bar_plus12:
      addiu v1, v0, 12
    bar_out:
      jr    ra
      sh    v1, 0x2e(fp)
    """
    with_frame = (COLS != FRAME_COLS) if with_frame is None else with_frame
    if not with_frame:  # 열을 안 늘리면 틀 보정 코드는 쓰이지 않는다 — 빼서 훅 자리를 아낀다
        src = src.split("    # ── 틀 오른쪽 변")[0]
    words, labels = asm(src, p["dead"])
    verify(words, p["dead"])
    assert with_frame or 4 * len(words) <= p["table_off"], "훅 코드가 죽은 함수 자리를 넘는다"
    return words, labels


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
    if COLS != FRAME_COLS:
        # 열을 안 늘리면 틀 보정이 필요 없다 — 넣으면 오히려 원판과 달라진다.
        _expect(exe, p["frame_edge"], p["frame_edge_orig"], "틀 오른쪽 변")
        _expect(exe, p["prompt_site"], p["prompt_orig"], "▼ 자리")
        for f, _ in p["frame_bars"]:
            _expect(exe, f, p["frame_bar_orig"], "격자·막대 x 전진")
        for s in p["cols_sites"]:
            _expect(exe, s, (p["cols_orig"],), "창 열 수")

    parens = tuple(table.get(c, 0x7FFF) for c in "()")  # 없으면 어떤 코드와도 안 맞는 값
    words, labels = hooks(disc, table[" "], space_w, parens)
    struct.pack_into(f"<{len(words)}I", exe, d0, *words)
    t0 = d0 + p["table_off"]
    exe[t0 : t0 + p["table_len"]] = bytes(p["table_len"])

    def jal(target):
        return (3 << 26) | ((target >> 2) & 0x3FFFFFF)

    struct.pack_into("<II", exe, _off(p["site_a"]), jal(p["dead"]), 0)
    if COLS != FRAME_COLS:
        struct.pack_into("<II", exe, _off(p["frame_edge"]), jal(labels["framew"]), 0)
        struct.pack_into("<II", exe, _off(p["prompt_site"]), jal(labels["promptw"]), 0)
        for f, name in p["frame_bars"]:
            struct.pack_into("<II", exe, _off(f), jal(labels[name]), 0)
        for s in p["cols_sites"]:
            struct.pack_into("<I", exe, _off(s), (p["cols_orig"] & 0xFFFF0000) | COLS)
    return f"공백 {space_w}px · 열 {COLS}(틀 {FRAME_COLS}) · 훅 {len(words)}워드 @ {p['dead']:#x}"
