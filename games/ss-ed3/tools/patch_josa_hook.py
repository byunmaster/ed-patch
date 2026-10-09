"""동적 조사 훅 — 문안에 넣은 **병기**(`을(를)`)를 실행 중에 하나로 줄인다.

    python3 games/ss-ed3/tools/patch_josa_hook.py --check    # 조립 + 디스어셈블 검산
    python3 games/ss-ed3/tools/patch_josa_hook.py --sim      # 파이썬 모의로 축약 확인

🔴 **왜 런타임인가** — `%s` 자리에 꽂히는 건 아이템·인물 이름이라 빌드 때 앞말을 모른다.
   박아 두면 절반이 틀린다(듀르젤**은** · 방방**은** · 모리슨**은** · 알프레드 왕**은**).
   ⇒ 문안엔 **병기**를 넣고(`『%s』` 우회를 걷어낼 수 있다), 표시 직전에 종성으로 하나를 고른다.
   ⓘ 훅이 안 돌면 `을(를)` 그대로 보인다 — **틀리지는 않는다**(ps1-ed1+2 와 같은 규약).

## 훅 지점 — **점프 테이블이 아니라 코드 변위** (2026-08-31 인게임 확인)

메시지 선조판기의 점프 테이블(`0x06065608`) 83 칸을 우리 자리로 돌리는 방식은
**스텁이 아예 안 돌았다**(트램펄린에 표식 쓰기를 심어 확인 — `%s` 문구를 띄우는데도
표식이 안 찍혔다). 케이브를 바꿔도, 스텝으로 `jmp @r0` 가 우리 주소를 무는 걸 봐도
그 다음이 예외 핸들러였다. **캐시 통과 미러도 못 쓴다** — 표 칸이 부호 16비트 오프셋이라
대상이 `0x0605D608~0x0606D608` 안이어야 하고 미러(`0x26xxxxxx`)는 그 밖이다.

⇒ **`%s` 처리기 안의 명령 여섯을 밀어낸다.** 실행 중인 코드 한복판이라 도달 경로에
  의문이 없고, 밀어낸 코드가 **`r12`(인자 문자열)를 만들어 주므로** 인자를 다시 안 캔다.

    0x06065E5C  mov.l @r13,r0        0x06065E62  mov.l r0,@r13
    0x06065E5E  add   r14,r1         0x06065E64  mov.l @r1,r13
    0x06065E60  add   #4,r0          0x06065E66  mov.l @(4,r13),r12  ← 인자 문자열

  자리 조건 셋을 다 만족한다 — **분기·지연 슬롯 없음 · PC 상대 적재 없음 · 12B**
  (`mov.l @(1,pc),r0 · jmp @r0 · nop · nop` + 스텁 주소 4B 가 딱 들어간다).

💡 **이 방식은 자기검증이 된다** — 스텁이 안 돌면 `r12` 가 안 채워져 **화면에서 바로**
  드러난다(아이템 이름이 안 나온다). 「돌긴 도나?」를 따로 확인할 필요가 없다.

⚠ **관측은 스텁이 직접 하게 한다**(`routine(dbg=주소)`) — 인자·서식 포인터·종성 비트를
  흘리게 해서 `r14+0x1cc` 가 **이미 지정자 다음을 가리킨다**는 걸 잡았다(`+1` 을 붙였다가
  한 바이트 밀려 꼴 검사에서 매번 빠져나왔다). 이 어댑터는 `exec` 브레이크포인트가
  안 걸리고 `read` 도 인덱스 주소지정을 못 잡아, **코드가 스스로 말하게 하는 게 제일 빠르다.**

## 종성 판정

🔴 **슬롯은 연속이 아니다** — `assign()` 이 게임 한자가 쓰는 칸을 건너뛰어 배정한다
   (가=1410 · 검=1488 · 본=3513 · 초=4801). 그래서 「음절 색인」으로는 못 짚는다.
   **슬롯 번호**로 짚는다 — 한 선행 바이트에 188 칸이므로

    슬롯 = (c1-0x81)*188 + (c2-0x40) - (c2>0x7F)

   최소~최대 슬롯을 덮는 비트 표(실측 **490B**)를 곁에 둔다. 한글이 아닌 칸은 0 이라
   자연히 「종성 없음」으로 떨어진다.

⚠ **자리(코드 케이브)는 실측으로 고른다** — `/0.BIN` 의 0 런은 BSS 일 수 있다(실행 중
  RAM 을 읽어 확인한다). 「0 으로 찼으니 비었다」로 판단하지 않는다(「빈 공간의 VAB 함정」).
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
import hangul_map as H

from shared.text.josa import batchim

# ── 실측 좌표 ────────────────────────────────────────────────────────────────
BASE = 0x06004000  # /0.BIN 로드 주소 (IP.BIN 0xF0)
PCT_S = 0x06065E4C  # `%s` 처리기
FRAME_FMT = 0x1CC  # r14 + 이것 = 서식 문자열 포인터

#   ── 훅 자리 — `%s` 처리기 **안**의 6 명령을 밀어낸다 (분기·지연슬롯·PC 상대 없음)
#        0x06065E5C  mov.l @r13,r0        0x06065E62  mov.l r0,@r13
#        0x06065E5E  add   r14,r1         0x06065E64  mov.l @r1,r13
#        0x06065E60  add   #4,r0          0x06065E66  mov.l @(4,r13),r12  ← 인자 문자열
HOOK = 0x06065E5C
HOOK_LEN = 12
HOOK_RET = 0x06065E68  # 밀어낸 코드 다음 (`tst r12,r12`)
HOOK_ORIG = bytes.fromhex("60d231ec70042d026d125cd1")

#   🔴 **슬롯은 연속이 아니다** — `assign()` 이 게임 한자가 쓰는 칸을 건너뛰어 배정한다
#     (가=1410 · 검=1488 · 본=3513 · 초=4801). 그래서 「음절 색인」이 아니라 **슬롯 번호**로
#     표를 만든다. 슬롯 = `(c1-0x81)*188 + (c2-0x40) - (c2>0x7F)` (한 선행 바이트에 188 칸).
SLOT0 = None  # 최소 슬롯 (bit_table 이 채운다)
NBITS = None  # 표 비트 수

# 병기 쌍 (받침용, 무받침용)
PAIR_CHARS = (("은", "는"), ("이", "가"), ("을", "를"))

#   반각 숫자로 끝나는 이름의 받침 — 0 영·1 일·3 삼·6 육·7 칠·8 팔 은 있고 2·4·5·9 는 없다.
#   비트 N = 숫자 N 에 받침이 있나. 실측 계기: 「검사교본 1」(2026-08-31 유저 스크린샷).
DIGIT_BITS = 0b0111001011
PAREN_L, PAREN_R = ord("("), ord(")")  # 반각 — 정본이 그렇게 쓴다

#   🔴 **어절 접기**(마스터 10-10 「짧으면 한 줄, 길면 어절 개행 — 로그성 메시지니까 최대한 채우고 꽉 차면 어절 단위로」).
#   서식의 `%s` 바로 뒤에 접기 표지(0x1F)가 있으면 스텁이 **「공백 + 이름 + 서식 꼬리」를 한 덩이**로 만들어 공백 단위로 훑으며
#   줄 폭(`FOLD_LIMIT` 반칸)을 넘는 어절 앞 공백을 엔진 줄바꿈(0x0D)으로 바꾼다. 앞 문구 폭은 `prefix_w`(반칸)로 받는다.
FOLD_MARK = 0x1F
FOLD_LIMIT = 34  # 창 17칸 = 34 반칸
FOLD_BUF = 80  # 덩이를 만들 칸(바이트)
LIT_OFF = 0x200  # 스텁 안 상수 자리(코드 뒤) — 상수 36B 다음에 덩이 칸이 온다


def pairs_bytes(table=None):
    """`[A_hi A_lo B_hi B_lo] × 3` — 스텁이 표로 읽는다."""
    out = bytearray()
    for a, b in PAIR_CHARS:
        out += H.encode_kr(a, table) + H.encode_kr(b, table)
    return bytes(out)


def bit_table():
    """슬롯 번호 → 종성 1 비트. 표는 최소~최대 슬롯을 덮는다(바이트마다 LSB 먼저)."""
    global SLOT0, NBITS
    t = H.load()
    syl = {k: v for k, v in t.items() if len(k) == 1 and "가" <= k <= "힣"}
    SLOT0, hi = min(syl.values()), max(syl.values())
    NBITS = hi - SLOT0 + 1
    bits = bytearray((NBITS + 7) // 8)
    for ch, slot in syl.items():
        if batchim(ch):
            i = slot - SLOT0
            bits[i >> 3] |= 1 << (i & 7)
    return bytes(bits)


def slot_of(code):
    """슬롯 SJIS 2바이트 → 슬롯 번호. SJIS 2바이트 꼴이 아니면 `None`."""
    c1, c2 = code >> 8, code & 0xFF
    if not (0x81 <= c1 <= 0x9F) or c2 == 0x7F or not (0x40 <= c2 <= 0xFC):
        return None
    return (c1 - 0x81) * 188 + (c2 - 0x40) - (1 if c2 > 0x7F else 0)


def syl_index(code):
    """슬롯 SJIS → 표 색인. 한글 슬롯이 아니면 `None`."""
    if SLOT0 is None:
        bit_table()
    s = slot_of(code)
    if s is None:
        return None
    i = s - SLOT0
    return i if 0 <= i < NBITS else None


# ── 파이썬 모의 — 스텁과 **같은 뜻**이어야 한다 ──────────────────────────────
def batchim_of(arg: bytes, bits: bytes):
    """이름의 **마지막 글자**에 받침이 있나 → `0/1`, 못 정하면 `None`.

    🔴 「뒤 2 바이트」로 잡으면 안 된다 — 이름이 **반각으로 끝날 수 있다**
      (실측: 「검사교본 1」). 앞에서부터 훑어 마지막 글자를 찾고,
      반각이면 **숫자 읽는 소리**로 본다(`DIGIT_BITS`). 스텁과 같은 규칙이다.
    """
    p, last = 0, None
    while p < len(arg) and arg[p]:
        last = p
        p += 2 if arg[p] >= 0x80 else 1
    if last is None:
        return None
    c1 = arg[last]
    if c1 < 0x80:
        d = c1 - 0x30
        return (DIGIT_BITS >> d) & 1 if 0 <= d < 10 else 0
    if last + 1 >= len(arg):
        return None
    #   전각 숫자 `０`~`９`(0x824F~0x8258) — 반각과 같은 표(읽는 소리: 일→을 · 이→를 · 삼→을)
    if c1 == 0x82 and 0x4F <= arg[last + 1] <= 0x58:
        return (DIGIT_BITS >> (arg[last + 1] - 0x4F)) & 1
    idx = syl_index((c1 << 8) | arg[last + 1])
    if idx is None:
        return None
    return (bits[idx >> 3] >> (idx & 7)) & 1


def collapse(fmt: bytearray, at: int, arg: bytes, bits: bytes, pairs: bytes) -> bool:
    """`fmt[at:]` 의 병기를 `arg` 의 종성으로 줄인다 → 고쳤나.

    `at` 은 `'s'` 를 가리킨다. 병기는 그 다음부터 `[A][(][B][)]` 6 바이트다.
    """
    has = batchim_of(arg, bits)
    if has is None:
        return False

    p = at + 1
    if p + 6 > len(fmt) or fmt[p + 2] != PAREN_L or fmt[p + 5] != PAREN_R:
        return False
    a = bytes(fmt[p : p + 2])
    b = bytes(fmt[p + 3 : p + 5])
    if not any(a == pairs[i : i + 2] and b == pairs[i + 2 : i + 4] for i in range(0, 12, 4)):
        return False

    keep = a if has else b
    fmt[p : p + 2] = keep
    #   ⚠ 뒤를 4 바이트 당긴다 — NUL 까지 옮기고 꼬리는 NUL 로 덮는다
    end = fmt.index(0, p) if 0 in fmt[p:] else len(fmt)
    fmt[p + 2 : end - 4] = fmt[p + 6 : end]
    fmt[end - 4 : end] = b"\x00" * 4
    return True


# ── SH-2 조립 ────────────────────────────────────────────────────────────────
class Asm:
    """SH-2 미니 어셈블러 — 쓰는 꼴만. 라벨은 `bt`·`bf`·`bra` 에서 푼다.

    ⚠ **지연 슬롯을 자동으로 안 넣는다** — `bra`·`rts`·`jmp` 뒤엔 손으로 한 명령을 둔다.
      (레포 규율: 손인코딩 기계어는 디스어셈블로 검산한다 — `--check`.)
    """

    def __init__(self, base):
        self.base = base
        self.w = []
        self.lab = {}
        self.fix = []

    def _e(self, v):
        self.w.append(v & 0xFFFF)

    def here(self):
        return self.base + 2 * len(self.w)

    def label(self, n):
        self.lab[n] = self.here()

    # 자료 이동
    def mov(self, m, n):
        self._e(0x6003 | (n << 8) | (m << 4))

    def movi(self, i, n):
        #   ⚠ 역시 부호 8비트 — 128~255 는 `extu.b` 로 펴서 쓴다(아래 188·0x80 이 그 꼴).
        assert -128 <= i <= 255, f"mov #{i} 는 8비트 밖이다"
        self._e(0xE000 | (n << 8) | (i & 0xFF))

    def movbl(self, m, n):  # mov.b @Rm,Rn
        self._e(0x6000 | (n << 8) | (m << 4))

    def movbs(self, m, n):  # mov.b Rm,@Rn
        self._e(0x2000 | (n << 8) | (m << 4))

    def movwl(self, m, n):
        self._e(0x6001 | (n << 8) | (m << 4))

    def movws(self, m, n):
        self._e(0x2001 | (n << 8) | (m << 4))

    def movll(self, m, n):  # mov.l @Rm,Rn
        self._e(0x6002 | (n << 8) | (m << 4))

    def movls(self, m, n):  # mov.l Rm,@Rn
        self._e(0x2002 | (n << 8) | (m << 4))

    def movl_disp_l(self, d, m, n):  # mov.l @(disp,Rm),Rn  (disp 는 롱 단위)
        self._e(0x5000 | (n << 8) | (m << 4) | (d & 0xF))

    def movl_pc(self, n, target):  # mov.l @(disp,PC),Rn — target 은 4 정렬 주소
        d = (target - ((self.here() + 4) & ~3)) // 4
        assert 0 <= d <= 0xFF, (hex(target), d)
        self._e(0xD000 | (n << 8) | d)

    # 셈
    def add(self, m, n):
        self._e(0x300C | (n << 8) | (m << 4))

    def addi(self, i, n):
        #   🔴 **부호 8비트다.** `add #-0x81` 을 그냥 넣으면 `+127` 로 인코딩돼
        #     조용히 딴 값이 된다(2026-08-31 캡스톤 검산에서 잡혔다).
        assert -128 <= i <= 127, f"add #{i} 는 8비트 밖이다"
        self._e(0x7000 | (n << 8) | (i & 0xFF))

    def sub(self, m, n):
        self._e(0x3008 | (n << 8) | (m << 4))

    def mulu(self, m, n):  # mulu.w Rm,Rn → MACL
        self._e(0x200E | (n << 8) | (m << 4))

    def sts_macl(self, n):
        self._e(0x001A | (n << 8))

    def extub(self, m, n):
        self._e(0x600C | (n << 8) | (m << 4))

    def extuw(self, m, n):
        self._e(0x600D | (n << 8) | (m << 4))

    def andi(self, i):  # and #imm,R0
        self._e(0xC900 | (i & 0xFF))

    def and_(self, m, n):
        self._e(0x2009 | (n << 8) | (m << 4))

    def shll8(self, n):
        self._e(0x4018 | (n << 8))

    def shlr(self, n):
        self._e(0x4001 | (n << 8))

    def shlr2(self, n):
        self._e(0x4009 | (n << 8))

    def movb_ld(self, d, m):  # mov.b @(disp,Rm),R0
        self._e(0x8400 | (m << 4) | (d & 0xF))

    def movb_st(self, d, m):  # mov.b R0,@(disp,Rm)
        self._e(0x8000 | (m << 4) | (d & 0xF))

    def cmppz(self, n):
        self._e(0x4011 | (n << 8))

    def pushr(self, n):  # mov.l Rn,@-R15
        self._e(0x2F06 | (n << 4))

    def popr(self, n):  # mov.l @R15+,Rn
        self._e(0x60F6 | (n << 8))

    def cmpeq_i(self, i):  # cmp/eq #imm,R0
        self._e(0x8800 | (i & 0xFF))

    def cmpeq(self, m, n):
        self._e(0x3000 | (n << 8) | (m << 4))

    def cmphs(self, m, n):
        self._e(0x3002 | (n << 8) | (m << 4))

    def cmpgt(self, m, n):
        self._e(0x3007 | (n << 8) | (m << 4))

    def tst(self, m, n):
        self._e(0x2008 | (n << 8) | (m << 4))

    # 분기 (라벨)
    def _br(self, op, mask, lab):
        self.fix.append((len(self.w), op, mask, lab))
        self._e(0)

    def bt(self, lab):
        self._br(0x8900, 0xFF, lab)

    def bf(self, lab):
        self._br(0x8B00, 0xFF, lab)

    def bra(self, lab):
        self._br(0xA000, 0xFFF, lab)

    def jmp(self, n):
        self._e(0x402B | (n << 8))

    def nop(self):
        self._e(0x0009)

    def rts(self):
        self._e(0x000B)

    def bytes(self):
        for i, op, mask, lab in self.fix:
            pc = self.base + 2 * i
            d = (self.lab[lab] - (pc + 4)) // 2
            lo = -(mask + 1) // 2
            assert lo <= d <= mask // 2, (lab, d)
            self.w[i] = op | (d & mask)
        return b"".join(struct.pack(">H", x) for x in self.w)


def routine(free, tbl_addr, dbg=None, prefix_w=0, tbuf=0):
    """`%s` 처리기 안에서 **밀어낸 6 명령**을 실행하고, 병기를 줄인 뒤 되돌아간다.

    진입 시점(훅 자리 `0x06065E5C`): `r1 = 0x204` · `r13`·`r14` 유효 · `r0` 자유.
    밀어낸 코드가 끝나면 **`r12` 에 인자 문자열 포인터**가 들어온다 — 그걸 그대로 쓴다.

    ⚠ `r12`·`r13`·`r14` 는 안 건드린다(원본이 그 위에서 돈다). 나머지는 스택으로 살린다.
    ⓘ 쌍(을/를·은/는·이/가)인지까지는 안 본다 — 바로 뒤가 `(`…`)` 인 여섯 바이트 꼴은
      우리 병기 말고 나올 데가 없다.
    """
    LIT = LIT_OFF  # 상수 자리 (코드가 이 앞에 들어간다)
    a = Asm(free)
    lit = free + LIT

    # ── 밀어낸 6 명령 (0x06065E5C~0x06065E67) 그대로
    a.movll(13, 0)  # mov.l @r13,r0
    a.add(14, 1)  # add   r14,r1
    a.addi(4, 0)  # add   #4,r0
    a.movls(0, 13)  # mov.l r0,@r13
    a.movll(1, 13)  # mov.l @r1,r13
    a.movl_disp_l(1, 13, 12)  # mov.l @(4,r13),r12   ← 인자 문자열

    for r in (1, 2, 3, 4, 5, 6, 7):
        a.pushr(r)

    a.mov(12, 6)
    a.tst(6, 6)
    a.bt("outj")

    #   ── 마지막 **글자**를 앞에서부터 훑어 찾는다
    #     🔴 「뒤 2 바이트」로 잡으면 안 된다 — 이름이 **반각으로 끝날 수 있다**
    #       (실측 2026-08-31: 「검사교본 1」 → 마지막이 `1`(0x31)이라 슬롯이 음수가 되어
    #       판정을 포기하고 「검사교본 1을(를)」이 그대로 화면에 나왔다).
    a.mov(6, 0)  # p
    a.movi(0, 5)  # 마지막 글자 자리
    a.label("scan")
    a.movbl(0, 1)
    a.extub(1, 1)
    a.tst(1, 1)
    a.bt("scanned")
    a.mov(0, 5)
    a.movi(0x80, 3)
    a.extub(3, 3)
    a.cmphs(3, 1)  # 0x80 이상이면 2 바이트
    a.bf("one")
    a.addi(2, 0)
    a.bra("scan")
    a.nop()
    a.label("one")
    a.addi(1, 0)
    a.bra("scan")
    a.nop()
    a.label("scanned")
    a.tst(5, 5)
    a.bt("outj")
    a.movbl(5, 1)
    a.extub(1, 1)
    a.movi(0x80, 3)
    a.extub(3, 3)
    a.cmphs(3, 1)
    a.bt("two")

    #   ── 반각으로 끝난다 — **숫자면 읽는 소리로** 받침을 본다
    #     0 영·1 일·3 삼·6 육·7 칠·8 팔 은 받침이 있고 2·4·5·9 는 없다 → 0x01CB
    #     숫자가 아닌 반각(영문·부호)은 받침 없음으로 떨어뜨린다.
    a.mov(1, 0)
    a.addi(-0x30, 0)
    a.cmppz(0)
    a.bf("nobat")
    a.movi(10, 3)
    a.cmphs(3, 0)
    a.bt("nobat")
    a.movl_pc(1, lit + 24)
    a.label("dsh")
    a.tst(0, 0)
    a.bt("gotbit")
    a.shlr(1)
    a.addi(-1, 0)
    a.bra("dsh")
    a.nop()
    a.label("nobat")
    a.movi(0, 1)
    a.bra("gotbit")
    a.nop()
    a.label("outj")  # `bt` 는 ±256B 라 먼 `out` 은 여기를 거쳐 뛴다
    a.bra("out")
    a.nop()

    #   ── 두 바이트로 끝난다 — r1=c1, r2=c2
    a.label("two")
    a.mov(5, 0)
    a.addi(1, 0)
    a.movbl(0, 2)
    a.extub(2, 2)

    #   ── 전각 숫자(`０`~`９` = 0x824F~0x8258)면 반각과 같은 표로 — 「제１을」이 아니라 「제１을(일)」 소리대로
    a.movi(0x82, 3)
    a.extub(3, 3)  # ⚠ `cmp/eq #imm` 은 부호확장이라 0x82 를 못 잰다 — 레지스터로
    a.cmpeq(3, 1)
    a.bf("notfw")
    a.mov(2, 0)
    a.addi(-0x4F, 0)
    a.cmppz(0)
    a.bf("notfw")
    a.movi(10, 3)
    a.cmphs(3, 0)
    a.bt("notfw")
    a.movl_pc(1, lit + 24)
    a.bra("dsh")
    a.nop()
    a.label("notfw")

    # ── 슬롯 = (c1-0x81)*188 + (c2-0x40) - (c2>=0x80)
    a.mov(1, 0)
    a.addi(-0x80, 0)  # ⚠ -0x81 은 8비트 밖이라 둘로 쪼갠다
    a.addi(-1, 0)
    a.extub(0, 0)
    a.movi(188, 3)
    a.extub(3, 3)
    a.mulu(3, 0)
    a.sts_macl(0)
    a.mov(2, 3)
    a.addi(-0x40, 3)
    a.add(3, 0)
    a.movi(0x80, 3)
    a.extub(3, 3)
    a.cmphs(3, 2)
    a.bf("noskip")
    a.addi(-1, 0)
    a.label("noskip")

    # ── i = 슬롯 - SLOT0, 범위 확인
    a.movl_pc(3, lit + 0)
    a.sub(3, 0)
    a.cmppz(0)
    a.bf("out")
    a.movl_pc(3, lit + 4)
    a.cmphs(3, 0)
    a.bt("out")

    # ── 종성 비트 → r1
    a.mov(0, 7)
    a.movi(7, 3)
    a.and_(3, 7)
    a.shlr2(0)
    a.shlr(0)
    a.movl_pc(3, lit + 8)
    a.add(3, 0)
    a.movbl(0, 1)
    a.extub(1, 1)
    a.label("sh")
    a.tst(7, 7)
    a.bt("gotbit")
    a.shlr(1)
    a.addi(-1, 7)
    a.bra("sh")
    a.nop()
    a.label("gotbit")
    a.movi(1, 3)
    a.and_(3, 1)

    #   ── 서식 포인터 r2 = *(r14+0x1cc)
    #     ⚠ **이미 지정자 다음을 가리킨다**(= 병기 첫 바이트). `+1` 을 붙였다가
    #       한 바이트 밀려 꼴 검사에서 매번 빠져나왔다(2026-08-31 관측: r2=0x06013F03,
    #       병기는 0x06013F02). 스텁이 관측값을 흘리게 해서(`routine(dbg=…)`) 잡았다.
    a.movl_pc(0, lit + 12)
    a.mov(14, 2)
    a.add(0, 2)
    a.movll(2, 2)

    #   ⓘ `--debug` — 어디서 빠지는지 스텁이 직접 말하게 한다 (인자·서식·종성비트)
    if dbg is not None:
        a.movl_pc(3, lit + 20)
        a.movls(6, 3)
        a.addi(4, 3)
        a.movls(2, 3)
        a.addi(4, 3)
        a.movls(1, 3)

    #   ── 접기 표지(`%s` 바로 뒤 0x1F)가 있으면 건너뛴다 — 병기는 그 다음부터다
    a.movbl(2, 0)
    a.cmpeq_i(FOLD_MARK)
    a.bf("nomark")
    a.addi(1, 2)
    a.label("nomark")

    # ── 병기 꼴인가 — [A][(][B][)]
    a.movb_ld(2, 2)
    a.extub(0, 0)
    a.cmpeq_i(PAREN_L)
    a.bf("out")
    a.movb_ld(5, 2)
    a.extub(0, 0)
    a.cmpeq_i(PAREN_R)
    a.bf("out")

    # ── 종성이 없으면 B 를 앞으로
    a.tst(1, 1)
    a.bf("shift")
    a.movb_ld(3, 2)
    a.movb_st(0, 2)
    a.movb_ld(4, 2)
    a.movb_st(1, 2)

    # ── 뒤를 4 바이트 당긴다 (NUL 까지)
    a.label("shift")
    a.mov(2, 3)
    a.addi(2, 3)
    a.mov(2, 0)
    a.addi(6, 0)
    a.label("cp")
    a.movbl(0, 5)
    a.movbs(5, 3)
    a.extub(5, 5)
    a.tst(5, 5)
    a.bt("out")
    a.addi(1, 0)
    a.addi(1, 3)
    a.bra("cp")
    a.nop()

    a.label("out")
    #   ── 어절 접기 — 표지가 있을 때만(이름이 없으면 건너뛴다)
    a.tst(12, 12)
    a.bt("fin")
    a.movl_pc(0, lit + 12)
    a.mov(14, 2)
    a.add(0, 2)
    a.movll(2, 2)  # r2 = 서식 포인터(지정자 다음)
    a.movbl(2, 0)
    a.cmpeq_i(FOLD_MARK)
    a.bf("fin")
    a.movl_pc(7, lit + 28)  # r7 = 덩이 칸
    a.mov(7, 3)  # r3 = 쓰는 자리
    a.movi(0x20, 0)
    a.movbs(0, 3)
    a.addi(1, 3)
    a.mov(12, 4)
    a.label("cpn")  # 이름 복사
    a.movbl(4, 0)
    a.tst(0, 0)
    a.bt("cpnd")
    a.movbs(0, 3)
    a.addi(1, 4)
    a.addi(1, 3)
    a.bra("cpn")
    a.nop()
    a.label("cpnd")
    a.mov(2, 4)
    a.addi(1, 4)  # r4 = 서식 꼬리(표지 다음)
    a.label("cpt")  # 꼬리 복사 — NUL·종결(0x10)에서 멈춘다
    a.movbl(4, 0)
    a.tst(0, 0)
    a.bt("cptd")
    a.cmpeq_i(0x10)
    a.bt("cptd")
    a.movbs(0, 3)
    a.addi(1, 4)
    a.addi(1, 3)
    a.bra("cpt")
    a.nop()
    a.label("cptd")
    a.movbs(0, 2)  # 서식: 표지 자리에 종결 바이트(또는 NUL)
    a.movi(0, 0)
    a.movbs(0, 3)  # 덩이 끝 NUL
    a.addi(1, 2)
    a.movbs(0, 2)  # 서식 다음 바이트 NUL
    #   ── 어절 훑기: 공백마다 「다음 어절 폭」을 재서 줄 폭을 넘으면 그 공백을 0x0D 로
    a.movl_pc(5, lit + 32)  # r5 = 앞 문구 폭(반칸)
    a.mov(7, 3)
    a.label("fl")
    a.movbl(3, 0)
    a.tst(0, 0)
    a.bt("fd")
    a.mov(3, 4)
    a.addi(1, 4)
    a.movi(0, 6)  # r6 = 어절 폭
    a.label("ms")
    a.movbl(4, 0)
    a.tst(0, 0)
    a.bt("md")
    a.cmpeq_i(0x20)
    a.bt("md")
    a.movi(0x80, 1)
    a.extub(1, 1)
    a.extub(0, 0)
    a.cmphs(1, 0)  # r0 >= 0x80 이면 두 바이트 글자
    a.bf("ms1")
    a.addi(2, 6)
    a.addi(2, 4)
    a.bra("ms")
    a.nop()
    a.label("ms1")
    a.addi(1, 6)
    a.addi(1, 4)
    a.bra("ms")
    a.nop()
    a.label("md")
    a.mov(5, 1)
    a.add(6, 1)
    a.addi(1, 1)  # r1 = col + 1 + w
    a.movi(FOLD_LIMIT, 2)
    a.cmpgt(2, 1)  # r1 > 한도 ?
    a.bf("fits")
    a.movi(0x0D, 0)
    a.movbs(0, 3)  # 공백 → 줄바꿈
    a.mov(6, 5)  # 새 줄: col = w
    a.bra("nx")
    a.nop()
    a.label("fits")
    a.mov(1, 5)
    a.label("nx")
    a.mov(4, 3)
    a.bra("fl")
    a.nop()
    a.label("fd")
    a.mov(7, 12)  # 인자 = 덩이
    a.label("fin")
    for r in (7, 6, 5, 4, 3, 2, 1):
        a.popr(r)
    a.movl_pc(0, lit + 16)
    a.jmp(0)
    a.nop()

    code = a.bytes()
    assert len(code) <= LIT, f"코드가 상수 자리를 넘었다 ({len(code)}B > {LIT}B)"
    code += b"\x00" * (LIT - len(code))
    return code + struct.pack(
        ">IIIIIIIII",
        SLOT0,
        NBITS,
        tbl_addr,
        FRAME_FMT,
        HOOK_RET,
        dbg or 0,
        DIGIT_BITS,
        tbuf,
        prefix_w,
    )


# ── 자리 (실측으로 고른 셋) ─────────────────────────────────────────────────
#   🔴 **점프 테이블 값은 부호 16비트**다(`mov.w @(r0,r1),r1` 로 읽어 더한다) — 그래서
#     테이블 바탕에서 ±32KB 안에 있어야 한다. 스텁은 그 범위 밖이라 **트램펄린**을 둔다.
#   ⚠ 자리마다 근거가 다르다. 위험이 큰 쪽에 **데이터**를, 작은 쪽에 **코드**를 놓았다:
#     · 스텁     — **개발실 디버그 메뉴 문자열**(`debug`·`Dump Monster`·`本００`…).
#                  새턴판엔 개발실이 없다(devlog 2026-08-29, 대사 전수 파서로 확인).
#                  설령 열려도 **글자만 깨진다** — 코드가 아니라 문자열이다.
#     · 종성 표   — 실행 중 RAM 에서 0 임을 확인한 자리. 만약 게임이 여기를 쓰면
#                  **조사만 틀리고 안 죽는다**(표를 못 읽으면 병기 그대로 두는 쪽으로 떨어진다).
STUB = 0x06016080  # 240B — 디버그 문자열 (0x06016080~0x06016333, 691B)
STUB_ROOM = 0x0601_6333 - 0x0601_6080
TBL = 0x06076170  # 490B
TBL_ROOM = 864


def fold_prefix_w():
    """어절 접기 문구(`system_src.FOLD`)의 `%s` 앞 폭(반칸) — 그 문구의 **우리 문안**에서 잰다(앞 글이 바뀌면 같이 따라온다)."""
    import system_src as SS

    widths = set()
    for raw, kr in SS.sections().get("battle", {}).items():
        if SS.FOLD_MARK in kr:
            head = H.encode_kr(kr[: kr.index("%s")])
            widths.add(sum(2 if b >= 0x80 else 1 for b in _chars(head)))
    assert len(widths) == 1, f"접기 문구가 하나여야 한다 — 앞 폭 {sorted(widths)}"
    return widths.pop()


def _chars(b):
    """바이트열 → 글자 첫 바이트들(SJIS 2바이트는 하나로)."""
    i, out = 0, []
    while i < len(b):
        out.append(b[i])
        i += 2 if b[i] >= 0x80 else 1
    return out


def patch(data, prefix_w=13):
    """`/0.BIN` 에 훅을 넣는다 → `(새 bytes, 넣은 조각 수)`. 크기 불변.

    `prefix_w` = 어절 접기 문구의 `%s` 앞 폭(반칸) — 빌드가 그 문구의 우리 문안에서 재서 넘긴다."""
    out = bytearray(data)
    bits = bit_table()
    tbuf = STUB + LIT_OFF + 36
    code = routine(STUB, TBL, prefix_w=prefix_w, tbuf=tbuf) + b"\x00" * FOLD_BUF
    assert LIT_OFF + 36 + FOLD_BUF <= STUB_ROOM

    def put(addr, blob, room, expect=None):
        off = addr - BASE
        assert 0 <= off and off + len(blob) <= len(out), hex(addr)
        assert len(blob) <= room, f"{addr:#x}: {len(blob)}B > {room}B"
        cur = bytes(out[off : off + len(blob)])
        #   ⚠ **원본이 예상과 다르면 멈춘다** — 자리를 잘못 짚으면 조용히 딴 걸 덮는다.
        if expect == "zero":
            assert cur == bytes(len(blob)), f"{addr:#x} 가 0 이 아니다"
        elif expect:
            assert out[off : off + len(expect)] == expect, f"{addr:#x} 가 예상과 다르다"
        out[off : off + len(blob)] = blob

    put(STUB, code, STUB_ROOM, b"debug\x00")
    put(TBL, bits, TBL_ROOM, "zero")

    #   ── 훅 — 밀어낸 12B 를 「스텁으로 점프 + 상수」로 덮는다
    #     🔴 점프 테이블 칸을 돌리는 앞선 방식은 **스텁이 아예 안 돌았다**(2026-08-31).
    #        여기서는 **실행 중인 코드 한복판**을 덮으므로 도달 경로에 의문이 없다 —
    #        스텁이 안 돌면 `r12` 가 안 채워져 **화면에서 바로 드러난다**(자기검증).
    a = Asm(HOOK)
    a.movl_pc(0, HOOK + 8)
    a.jmp(0)
    a.nop()
    a.nop()
    hook = a.bytes() + struct.pack(">I", STUB)
    assert len(hook) == HOOK_LEN, len(hook)
    put(HOOK, hook, HOOK_LEN, HOOK_ORIG)

    assert len(out) == len(data)
    return bytes(out), 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="조립 + 디스어셈블 검산")
    ap.add_argument("--sim", action="store_true", help="파이썬 모의")
    a = ap.parse_args()

    bits, pr = bit_table(), pairs_bytes()
    print(f"종성 표 {len(bits)}B · 병기 쌍 {len(pr)}B")
    for ch in ("약초", "단검", "구슬", "검사교본", "듀르젤", "쥬리오"):
        i = syl_index(int.from_bytes(H.encode_kr(ch[-1]), "big"))
        print(
            f"  {ch}: 색인 {i} · 종성 {(bits[i >> 3] >> (i & 7)) & 1} (기대 {int(batchim(ch[-1]))})"
        )

    if a.sim:
        fmt = bytearray(H.encode_kr("%s을(를)\r팔았다.") + b"\x00" * 8)
        for name in ("약초", "단검"):
            f = bytearray(fmt)
            ok = collapse(f, f.index(ord("s")), H.encode_kr(name), bits, pr)
            from shared.text import sjis as SJ

            shown = SJ.decode(bytes(f), H.by_code() if hasattr(H, "by_code") else None)
            print(f"  {name}: 고침={ok} → {shown[:24]!r}")

    if a.check:
        import capstone as cs

        bit_table()
        code = routine(STUB, TBL)
        md = cs.Cs(cs.CS_ARCH_SH, cs.CS_MODE_SH2 | cs.CS_MODE_BIG_ENDIAN)
        md.skipdata = True
        n = 0
        for ins in md.disasm(code, STUB):
            print(f"  {ins.address:#010x} {ins.mnemonic:9} {ins.op_str}")
            n += 1
        print(f"→ {len(code)}B · {n} 명령")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
