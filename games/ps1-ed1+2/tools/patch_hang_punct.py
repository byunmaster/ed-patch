#!/usr/bin/env python3
"""온점 매달기 — 꼬리 부호가 **줄 끝을 넘어** 앉게 한다(엔진 훅 둘 + 한계값 셋).

## 왜

원판 엔진의 줄 한계는 **29열**(전각 2열 · 반각 1열)이고 그게 곧 **창 틀**이다. 그런데 우리
조판기는 `WRAP = 14.0슬롯` = **28열**까지만 썼다. 코드 두 자리가 **글자 폭을 보지 않고**
마지막 열을 통째로 예약하기 때문이다:

- **prewrap** — 글자를 재기 **전에** `열 > 한계-1` 이면 무조건 끊는다. 전각이 마지막 열에서
  시작하면 한 열 삐져나가니 미리 막는 것인데, **반각까지 싸잡는다.**
- **드로어** — `열 == 한계` 면 그 자리에 **공백**(`20 00`)을 채우고 줄을 바꾼다(패딩 예약).

여기에 아이템창이 이름을 창 밖으로 살짝 뚫고 나가는 것과 같은 여유를 준다 —
**틀은 29열, 꼬리 부호(`.,!?)"'`)만 30열까지.** 실행파일의 한계값을 30 으로 올리고,
훅이 「전각·보통 반각은 29열까지」를 대신 지킨다. 그래서 훅은 **둘 그대로**다.

유저 요청(2026-08-26): "온점만 개행되는 경우 옆에 창을 조금 덮어쓰더라도 한 줄에 나오게."
2026-08-15 에 같은 질문이 나왔고 그때 결론이 **"남으면 엔진 prewrap 훅에 금칙처리"**
였다(devlog "온점 고아는 「우리가 안 꺾어서」였다"). 지금 그 자리다.

## 금칙 — 부호가 30열도 못 쓰면 앞 글자와 함께 내린다

30열까지 열어도 `!!` 처럼 부호가 둘이면 뒤엣것이 31열로 밀린다. 그때는 **한 글자 앞에서**
끊어 `…왔` / `다!!` 가 되게 한다. 이건 우리 발명이 아니라 **원판의 집안 규칙**이다 —
둘째 패스(`0x800ACFB8~`)에 이미 당김 표가 있다:

| `str[끊는 자리]` | 조치 |
| --- | --- |
| `!`(0x21) | 앞이 또 `!` 면 3바이트, 아니면 2바이트 당긴다 |
| 공백이고 다음이 `!` | 2바이트 |
| `。`(0x81 0x42) | 2바이트 |
| `\n` | 끊기 취소(0xFE) |

2바이트 = 전각 한 글자다. **우리 반각 온점(0x2E)만 이 표에 없어서** 혼자 떨어졌던 것이다.

## 안전

- 훅 지점·한계값 자리의 원명령을 **바이트로 대조**하고 다르면 죽는다(감사).
- 배치는 **VAB 헤더 패딩**(`vab.safe_len` 로 유도) — 조사 훅과 같은 수법이되 **다른 런**.
  ⚠ 「0 으로 차 있다」로 고르지 않는다(효과음 파괴 이력, 2026-07-29).
- 스텁은 `v0`·`v1`·`t0`~`t6` 만 건드린다. `t*` 는 prewrap **둘째 패스**에서만 쓰이고
  (`t0` 이 `0x800ACFB8` 부터), `v0`·`v1` 은 복귀 직후 원코드가 다시 적재한다(정적 확인).
- 드로어 꼴이 셋인데 **살아 있는 건 둘**이다 — 대사·전투가 쓰는 쪽(호출자 2곳)만 건다.
  나머지(`0x800A9A8C` 아래 4곳)는 문자열이 `s7` 이라 스택 적재가 다르다. 안 건다.
- 🔴 `reinsert_kr_pilot._hang_merge` 와 **한 몸**이다. 하나만 켜면 지금보다 나빠진다.
"""

import os
import re
import struct
import sys
from itertools import pairwise

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import vab
from patch_josa_hook import REG, Asm, _i, _r
from patch_josa_hook import site as josa_site

# ── 시그니처 (EXE 마다 주소가 달라 손으로 박지 않는다) ──────────────────────
# addiu v0,s6,-1 ; slt v0,v0,v1 ; beqz v0,.. ; sll v0,s2,0x10
SIG_PREWRAP = re.compile(rb"\xff\xff\xc2\x26\x2a\x10\x43\x00[\s\S]{2}\x40\x10\x00\x14\x12\x00")
# addiu v0,s4,-1 ; slt v0,v0,v1 ; beqz v0,.. ; slt v0,s4,v1
SIG_DRAW = re.compile(rb"\xff\xff\x82\x26\x2a\x10\x43\x00[\s\S]{2}\x40\x10\x2a\x10\x83\x02")

HALF_LO, HALF_N = 0x20, 0x5F  # 0x20..0x7E  = 반각
KANA_ADD, KANA_N = 0x5F, 0x3F  # 0xA1..0xDF = 반각(반각 가나)
HANG_TAIL = ".,!?)\"'"  # 매달 수 있는 꼬리 부호 — `reinsert_kr_pilot.HANG_TAIL` 과 같아야 한다
# 꼬리 부호는 전부 `0x20..0x3F` 라 **32비트 마스크 하나**로 판정한다(비교 7번 = 21명령이
# 7명령으로). 배치 런이 508B 뿐이라 스텁 크기가 그대로 제약이다.
assert all(0x20 <= ord(c) < 0x40 for c in HANG_TAIL), "마스크 범위 밖 꼬리 부호"
HANG_MASK = sum(1 << (ord(c) - 0x20) for c in HANG_TAIL)  # 0x80005286

# 🔴 **틀은 29열, 꼬리 부호만 30열까지.** `OVER = 0` 으로 두면 30열 확장이 통째로 꺼지고
# 틀 안(29열)까지만 매달린다 — 인게임에서 보기 나쁘면 **여기만** 되돌린다.
FRAME = 29  # 창 틀이 담는 열 수 (원판 한계값 `0x1d`)
OVER = 0  # 꼬리 부호가 **틀 밖으로** 더 나갈 수 있는 열 수
# 🔴 **0 이다.** 30열(틀 밖 한 칸)까지 열어 봤고 되돌렸다(2026-08-28, 유저 QA 넷) —
# 엔진이 「29열」을 전제하는 자리가 **넷**이고 층마다 같은 증상이 다시 났다:
#   ① prewrap 놓기 전(0x800ACF00)  ② prewrap 놓은 뒤(0x800ACF58)
#   ③ 드로어 그리기 뒤(0x800AD678) + 줄 채움 루프 셋(개행·패딩) → 창 테두리를 갉는다
#   ④ **줄 수 계산기(0x800ACC5C)** — 바이트 수를 29 로 나눠 올림한다(바이트=열).
#      30열 줄이 `ceil(30/29)=2줄` 로 계산돼 로그가 두 줄 내려가 **빈 줄**이 생긴다.
# ⇒ 29열은 엔진이 실제로 그리는 마지막 열이고, 30열은 **틀 밖**이다. 한 칸을 더 얻으려면
#   네 층을 다 고쳐야 하는데 이득(개행 466)보다 조용히 틀릴 여지가 크다.
COL_LIMIT = FRAME + OVER  # 실행파일에 새로 박는 한계값
# 🔴 **그냥 1 로 되돌리지 말 것.** 아래 `_bump_limit`·`_kill_autowrap`·`stub_after` 는 30열
# 판의 잔해이고, 그것만으로는 **넷째 층이 안 잡힌다** — 줄 수 계산기(`0x800ACC5C`)가 바이트
# 수를 29 로 나눠 올림해서 30열 줄을 2줄로 세고, 로그가 두 줄 내려가 **빈 줄**이 남는다.
# 열려면 그 계산기까지 고쳐야 한다. 안 그러면 2026-08-28 의 QA 넷을 그대로 다시 돈다.
assert OVER == 0, "30열을 열려면 줄 수 계산기(0x800ACC5C)부터 고쳐야 한다 — 위 주석"
ORIG_LIMIT = 0x1D

_BRANCH = {"j", "jr", "jal", "b", "beq", "bne", "beqz", "bnez", "blez", "bgtz"}


def fo(ram):
    return ram - 0x80010000 + 0x800


def _sra(a, rd, rt, sh):
    a.emit(_r(0, 0, REG[rt], REG[rd], sh, 3))


def _slt(a, rd, rs, rt):
    a.emit(_r(0, REG[rs], REG[rt], REG[rd], 0, 0x2A))


def _slti(a, rt, rs, imm):
    a.emit(_i(0x0A, REG[rs], REG[rt], imm & 0xFFFF))


def _lw(a, rt, off, base):
    a.emit(_i(0x23, REG[base], REG[rt], off))


def _j(a, target):
    a.emit(0x08000000 | ((target >> 2) & 0x03FFFFFF))


def _is_half(a, byte_reg, dest, t):
    """dest = 반각인가(1/0) — 엔진 폭 함수(`0x800AE430`)와 **같은 식**을 쓴다.

    ⚠ 판정이 엔진과 갈리면 우리 조판과 엔진이 어긋난다. 마스크를 더하지 않는 것까지 같다
    (`addiu -0x20` 이 음수면 `sltiu` 가 부호없이 커져 자연히 실패한다)."""
    a.addiu(dest, byte_reg, (-HALF_LO) & 0xFFFF)
    a.sltiu(dest, dest, HALF_N)  # 0x20..0x7E
    a.addiu(t, byte_reg, KANA_ADD)
    a.andi(t, t, 0xFF)
    a.sltiu(t, t, KANA_N)  # 0xA1..0xDF
    a.or_(dest, dest, t)


def _is_hang(a, byte_reg, dest, t, tag):
    """dest = 매달 수 있는 꼬리 부호인가(1/0) — `0x20..0x3F` 비트마스크 한 번."""
    a.addiu(t, byte_reg, (-HALF_LO) & 0xFFFF)
    a.sltiu(dest, t, 32)
    a.beq(dest, "zero", f"nohang{tag}")  # 범위 밖 → 0
    a.nop()
    a.lui(dest, HANG_MASK >> 16)
    a.ori(dest, dest, HANG_MASK & 0xFFFF)
    a.srlv(dest, dest, t)
    a.andi(dest, dest, 1)
    a.label(f"nohang{tag}")


def stub_prewrap(base, resume):
    """v0 = 「여기서 끊어야 하나」 — 원판의 `열 > 한계-1` 대신 **폭과 부호를 본다**.

    ① 이 글자가 제 한계를 넘어서 끝나면 끊는다. 한계는 **꼬리 부호면 30열, 아니면 29열**.
    ② 꼬리 부호가 30열을 다 쓰는데 **다음도 꼬리 부호**면(31열로 밀린다) 미리 끊는다 —
       원판이 `!`·`。` 에 하던 당김과 같은 꼴로 앞 글자와 함께 내려간다.

    레지스터: s1=열 · s0=인덱스 · s3=문자열 · s6=한계값(30).
    """
    a = Asm(base)
    a.sll("t0", "s1", 16)
    _sra(a, "t0", "t0", 16)  # t0 = 열
    a.sll("t1", "s0", 16)
    _sra(a, "t1", "t1", 16)
    a.addu("t1", "s3", "t1")  # t1 = &str[i]
    a.lbu("t2", 0, "t1")
    a.nop()  # 로드 지연
    _is_half(a, "t2", "t3", "v0")  # t3 = 반각인가
    _is_hang(a, "t2", "t4", "v0", "A")  # t4 = 꼬리 부호인가
    a.addiu("t5", "t0", 1)
    a.subu("t5", "t5", "t3")  # t5 = 이 글자가 끝나는 열
    a.addiu("t6", "zero", FRAME)
    if OVER:  # 틀 밖으로 나갈 수 있으면 꼬리 부호에만 더 준다
        a.addu("t6", "t6", "t4")
    _slt(a, "v0", "t6", "t5")
    a.bne("v0", "zero", "brk")  # 한계를 넘어 끝난다 → 끊는다
    a.nop()
    a.addiu("t6", "zero", FRAME + OVER)
    a.bne("t5", "t6", "no")  # 마지막 열을 다 쓰지 않았다 → 그대로
    a.nop()
    a.addiu("t6", "t1", 2)  # 금칙: 다음도 꼬리 부호면 31열로 밀린다
    a.subu("t6", "t6", "t3")
    a.lbu("t6", 0, "t6")
    a.nop()  # 로드 지연
    _is_hang(a, "t6", "v0", "t2", "B")
    a.bne("v0", "zero", "brk")
    a.nop()
    a.label("no")
    _j(a, resume)
    a.addu("v0", "zero", "zero")  # 지연 슬롯 — 끊지 않는다
    a.label("brk")
    _j(a, resume)
    a.addiu("v0", "zero", 1)  # 지연 슬롯 — 끊는다
    return a.resolve()


def stub_after(base, resume):
    """놓은 **뒤** 검사 — 매달린 부호 뒤에서는 끊지 않는다(안 그러면 **빈 줄**이 생긴다).

    원판은 `열 > s6` 이면 그 글자 **뒤에** 끊는 자리를 적는다. 부호를 30열에 앉히면 열이
    31이 되어 여기서 한 번 더 끊는데, 그 자리엔 원래 줄 구분(`\n`)이 있으므로 **개행이
    둘**이 되어 빈 줄이 된다(유저 QA 2026-08-28 스크린샷).
    ⇒ 열 31 이면 끊지 않는다. **31은 매달린 부호 뒤에서만 나온다** — 다른 글자가 30열에서
    끝나는 건 그리기 전 검사가 막는다. 뒤에 글자가 더 있으면 그 글자가 알아서 끊는다.
    """
    a = Asm(base)
    a.sll("v0", "s1", 16)
    _sra(a, "v0", "v0", 16)  # v0 = 놓고 난 뒤의 열
    a.addiu("v1", "zero", FRAME + OVER + 1)
    a.beq("v0", "v1", "no")  # 31 → 매달린 부호 뒤다
    a.addiu("v1", "zero", FRAME + OVER)  # 지연 슬롯
    _slt(a, "v0", "v1", "v0")  # 열 > 30 → 원판대로 끊는다
    _j(a, resume)
    a.nop()
    a.label("no")
    _j(a, resume)
    a.addu("v0", "zero", "zero")
    return a.resolve()


def stub_draw(base, normal, wrap, fall):
    """제 한계 안에서 끝나면 **정상 그리기**로, 아니면 줄바꿈으로.

    🔴 **틀 밖에서는 공백 패딩을 찍지 않는다.** 원판은 `열 == 한계` 에 공백 글리프
    (`0x801089D0` = `20 00`)를 찍고 줄을 바꾸는데, 한계를 30 으로 올렸으므로 그 공백이
    **틀 밖(30열)** 에 찍혀 창 오른쪽 테두리를 갉아먹는다 — 그것도 넘치든 말든 매번
    (유저 QA 2026-08-28: "넘치지 않아도 오른쪽 끝부분이 조금씩 깎이네").
    ⇒ 판정을 원판(`col > s4`)에 맡기지 않고 **틀(`FRAME`)** 로 직접 한다.
    그래서 30열에 실제로 무언가 그려지는 건 **매달린 꼬리 부호뿐**이다.

    레지스터: v1=열(원코드가 넘겨준다) · s3=소스 인덱스 · [sp+0x20]=문자열 · s4=한계값.
    """
    a = Asm(base)
    _lw(a, "t0", 0x20, "sp")
    a.sll("t1", "s3", 16)
    _sra(a, "t1", "t1", 16)
    a.addu("t1", "t0", "t1")  # &str[i]
    a.lbu("t2", 0, "t1")
    a.nop()  # 로드 지연
    _is_half(a, "t2", "t3", "v0")
    _is_hang(a, "t2", "t4", "v0", "D")
    a.addiu("t5", "v1", 1)
    a.subu("t5", "t5", "t3")  # 끝나는 열
    a.addiu("t6", "zero", FRAME)
    if OVER:
        a.addu("t6", "t6", "t4")  # 허용된 마지막 열
    _slt(a, "v0", "t6", "t5")
    a.bne("v0", "zero", "over")  # 한계 초과 → 줄을 바꾼다
    a.nop()
    _j(a, normal)  # 한계 안 → 그대로 그린다(29·30열 포함)
    a.nop()
    a.label("over")
    _slti(a, "v0", "v1", FRAME + 1)  # 열 <= 29 (틀 안) 인가
    a.bne("v0", "zero", "pad")
    a.nop()
    _j(a, wrap)  # 틀 밖 — 공백을 찍지 않고 줄만 바꾼다
    a.nop()
    a.label("pad")
    _j(a, fall)  # 틀 안 — 원판대로 공백을 채우고 줄을 바꾼다
    a.nop()
    return a.resolve()


def _fn_start(ed, off):
    """그 자리를 품은 함수의 시작 — 뒤로 훑어 `addiu $sp, $sp, -N` 프롤로그를 찾는다.

    ⚠ 「체크 − 고정 오프셋」으로 추정하지 말 것. 상수 하나가 「호출자 0곳」이라는 **거짓
    근거**를 만들어 살아 있는 드로어를 죽은 것으로 분류할 뻔했다(2026-08-28)."""
    for k in range(off & ~3, max(0, off - 0x600), -4):
        w = struct.unpack_from("<I", ed, k)[0]
        if (w & 0xFFFF8000) == 0x27BD8000:  # addiu sp, sp, 음수
            return k - 0x800 + 0x80010000
    raise SystemExit(f"0x{off:X} 의 함수 시작을 못 찾았다")


def _callers(ed, fn_ram):
    pat = struct.pack("<I", 0x0C000000 | ((fn_ram >> 2) & 0x03FFFFFF))
    return [i for i in range(0, len(ed) - 4, 4) if ed[i : i + 4] == pat]


def _one(rx, ed, what):
    hits = [m.start() for m in rx.finditer(bytes(ed))]
    if what == "draw":  # ⚠ 살아 있는 드로어가 **둘**이다(2026-08-28 실측):
        #   호출자 2곳 = 대사(`0x800B245C`) + `drawstr`(`0x800A9A60`, 그 아래 41곳) ← 우리 것
        #   호출자 1곳 = `0x800A9A8C`(4곳) — 문자열이 `[sp+0x20]` 이 아니라 **s7** 이다
        hits = [h for h in hits if len(_callers(ed, _fn_start(ed, h))) >= 2]
    assert len(hits) == 1, f"{what} 시그니처 {len(hits)}건 — 1건이어야 한다"
    return hits[0] - 0x800 + 0x80010000


def _btarget(ed, ram):
    """분기 명령의 목적지 RAM 주소."""
    w = struct.unpack_from("<I", ed, fo(ram))[0]
    off = w & 0xFFFF
    if off & 0x8000:
        off -= 0x10000
    return ram + 4 + off * 4


def _bump_limit(ed, prewrap_fn):
    """prewrap 의 `s5` 만 `0x1d` → `0x1e`. **드로어 `a3` 는 안 올린다.**

    🔴 드로어에는 「줄 나머지를 공백으로 채우는」 루프가 **셋**(개행 처리기 · 그 채움 루프 ·
    패딩 루프) 있고 전부 `a3` 까지 채운다. `a3` 를 올리면 그 공백이 **틀 밖에 찍혀 창
    테두리를 갉는다** — 넘치든 말든 매 줄(유저 QA 2026-08-28). 그래서 드로어 한계는 원판
    그대로 두고, **30열은 우리 훅만 안다**.
    prewrap 쪽은 올려야 한다 — 안 그러면 글자를 놓은 **뒤** 검사(`slt s6, 열`)가 29열에서
    끝난 줄 뒤에서 끊어 버려 부호가 다음 줄로 간다."""
    want = 0x24000000 | (REG["s5"] << 16) | ORIG_LIMIT  # addiu s5, zero, 0x1d
    for k in range(fo(prewrap_fn), fo(prewrap_fn) + 0x40, 4):
        if struct.unpack_from("<I", ed, k)[0] == want:
            struct.pack_into("<I", ed, k, (want & ~0xFFFF) | COL_LIMIT)
            return k - 0x800 + 0x80010000
    raise SystemExit("prewrap 한계값(s5=0x1d)을 못 찾았다")


# 그리기 뒤 자동 개행 — `slt v0,s4,v0 ; beq v0,zero,+4 ; addiu v0,s3,1`
SIG_AUTOWRAP = re.compile(rb"\x2a\x10\x82\x02\x04\x00\x40\x10\x01\x00\x62\x26")


def _kill_autowrap(ed):
    """그린 **뒤** 열이 한계를 넘으면 줄을 바꾸던 것을 **끈다**(분기를 무조건으로).

    꼬리 부호를 30열에 놓으려면 그 앞 글자(29열에서 끝난다) 뒤에서 줄이 바뀌면 안 된다.
    끄더라도 안전하다 — 다음 글자는 **그리기 전** 검사(우리 훅)가 받아서 줄을 바꾼다.
    ⚠ 안 끄면 증상이 둘로 나온다: 부호가 다음 줄로 가거나, 자동 개행 뒤 `\n` 이 또 한 줄을
    넘겨 **빈 줄**이 생긴다(유저 QA 2026-08-28 스크린샷)."""
    hits = [m.start() for m in SIG_AUTOWRAP.finditer(bytes(ed))]
    assert len(hits) == 1, f"자동 개행 시그니처 {len(hits)}건 — 1건이어야 한다"
    struct.pack_into("<I", ed, hits[0] + 4, 0x10000004)  # beq zero, zero, +4
    return hits[0] + 4 - 0x800 + 0x80010000


def free_run(ed, exclude, need):
    """VAB 헤더 패딩에서 **쓰지 않는** 런을 고른다 — 오프셋 오름차순 첫 자리(결정적).

    ⚠ 「0 으로 차 있다」로 고르지 않는다. `vab.safe_len` 이 파형 시작 직전까지를 유도한다
    (0런을 그대로 믿어 효과음을 깨뜨린 이력이 있다 — patch_josa_hook 배치 주석)."""
    for m in re.finditer(rb"\x00{96,}", bytes(ed)):
        off = (m.start() + 3) & ~3
        if any(abs(off - u) < 600 for u in exclude):
            continue
        safe = vab.safe_len(ed, off)
        if safe is None:
            continue
        avail = min(m.end() - off, safe)
        if avail >= need:
            return off, avail
    raise SystemExit(f"안전한 배치 자리를 못 찾았다 (필요 {need}B)")


def build_and_patch(ed: bytearray, game: str):
    st = josa_site(game)
    p = _one(SIG_PREWRAP, ed, "prewrap")
    d = _one(SIG_DRAW, ed, "draw")
    normal, wrap, fall = _btarget(ed, d + 8), _btarget(ed, d + 16), d + 20

    size = (
        len(stub_prewrap(0, p + 8))
        + len(stub_after(0, p + 0x5C))
        + len(stub_draw(0, normal, wrap, fall))
    )
    off, avail = free_run(ed, (st["josa_off"], st["data_off"]), size)
    base = off - 0x800 + 0x80010000
    s1 = stub_prewrap(base, p + 8)
    s1b = stub_after(base + len(s1), p + 0x5C) if OVER else b""
    s2 = stub_draw(base + len(s1) + len(s1b), normal, wrap, fall)
    blob = s1 + s1b + s2
    assert all(b == 0 for b in ed[off : off + len(blob)]), "배치 자리가 0이 아니다"
    ed[off : off + len(blob)] = blob

    for ram, want, target in (
        (p, 0x26C2FFFF, base),  # addiu v0, s6, -1
        *([(p + 0x50, 0x00021400, base + len(s1))] if OVER else []),  # 놓은 뒤 검사
        (d, 0x2682FFFF, base + len(s1) + len(s1b)),  # addiu v0, s4, -1
    ):
        got = struct.unpack_from("<I", ed, fo(ram))[0]
        assert got == want, f"{game} 훅 0x{ram:08X} 원명령 불일치: 0x{got:08X} != 0x{want:08X}"
        ed[fo(ram) : fo(ram) + 4] = struct.pack("<I", 0x08000000 | ((target >> 2) & 0x03FFFFFF))
    limits = [_bump_limit(ed, _fn_start(ed, fo(p))), _kill_autowrap(ed)] if OVER else []
    return {
        "prewrap": p,
        "draw": d,
        "base": base,
        "size": len(blob),
        "avail": avail,
        "limits": limits,
    }


def verify_asm(blob, base, name):
    """연속 디코드 + 지연 슬롯 검산 — 손인코딩 오타를 자동으로 잡는다(빌드 규율)."""
    from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs

    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    ins = list(md.disasm(blob, base))
    assert len(ins) == len(blob) // 4, f"{name}: capstone {len(ins)}/{len(blob) // 4} — 미디코드"
    assert ins[-1].mnemonic not in _BRANCH, f"{name}: 마지막이 분기 — 지연 슬롯이 없다"
    for a, b in pairwise(ins):
        assert not (a.mnemonic in _BRANCH and b.mnemonic in _BRANCH), (
            f"{name}: 0x{a.address:08X} 분기의 지연 슬롯이 또 분기다"
        )
    return len(ins)


def main():
    from common import BUILD_DIR, extract, write_user_data

    target = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")
    if not os.path.exists(target):
        raise SystemExit(f"대상 이미지 없음: {target} — build.py 먼저")
    for game in ("ED1", "ED2"):
        st = josa_site(game)
        ed = bytearray(extract(st["lba"], st["size"], path=target))
        r = build_and_patch(ed, game)
        verify_asm(bytes(ed[fo(r["base"]) : fo(r["base"]) + r["size"]]), r["base"], game)
        with open(target, "r+b") as f:
            n = write_user_data(f, st["lba"], ed, label=f"온점 매달기 ({game})")
        print(
            f"온점 매달기 [{game}]: {r['size']}B @0x{r['base']:08X} (여유 {r['avail'] - r['size']}B) "
            f"→ prewrap 0x{r['prewrap']:08X} · 드로어 0x{r['draw']:08X} 훅 · "
            f"한계 {FRAME}→{COL_LIMIT}열 {len(r['limits'])}곳, 섹터 {n}개 수정"
        )


if __name__ == "__main__":
    main()
