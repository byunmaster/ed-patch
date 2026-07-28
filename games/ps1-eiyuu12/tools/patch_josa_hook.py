"""동적 조사 훅 — 문자열 버퍼의 조사 병기(은(는)·이(가)·을(를))를 정확 조사로 재작성.

런타임 %s 치환 자리(캐릭터·몬스터·아이템 이름)는 빌드 시점에 앞말을 모름 → 병기로 넣어두고,
표시 경로에서 이 루틴이 버퍼를 1패스 스캔해 [음절][조사A][(][조사B][)] 패턴을 앞 음절의
종성 유무(비트테이블)로 조사 하나로 축약한다(4B 좌시프트).
설계·조사 이력: docs/josa-hook-devlog.md. 종성 판정 근거: shared/text/josa.py.

훅은 **두 지점**(둘 다 같은 josa_fix를 부르고, 병기가 없으면 무동작이라 멱등):
  1. `HOOK_ADDR` 0x800B2054 — 워크슬롯 조립 직후. 줄 단위(64B, cross-line 결합 포함).
  2. `PREWRAP_CALL` 0x800B1D60 — **자동 개행 삽입 전** 평문(128B). 개행 폭 계산이
     미해결 병기(3슬롯)로 이뤄져 줄이 이르게 갈리던 문제를 없앤다(HANDOFF #2/#3).
배치: ED.EXE의 검증된 클린 0런 2개(PLACE_JOSA_RAM / PLACE_DATA_RAM).
진단: `JOSA_NOOP=1`(훅 1 무력화) · `JOSA_NOPREWRAP=1`(훅 2만 제외) · `--selftest`.
"""

import os
import struct
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import hangul_map  # noqa: E402

sys.path.insert(0, __file__.rsplit("/games/", 1)[0] + "/shared")
from text.josa import batchim  # noqa: E402

# ── 슬롯 코드 상수 ──────────────────────────────────────────────────────────
SYL_LO, SYL_HI = 0x889F, 0x94FC  # 가~마지막 음절 슬롯 (hangul_map 배치)
BASE_LIN = 94  # 가(0x889F)의 (hi-0x88)*188+cell 값 — idx = lin - BASE_LIN
PAREN_L, PAREN_R = 0x28, 0x29  # 반각 ( ) — 전투 인코더(patch_items.enc)는 ASCII 1바이트 폴백

# (조사A(받침), 조사B(무받침)) 슬롯 코드
PAIRS = [
    (hangul_map.syllable_sjis(a), hangul_map.syllable_sjis(b))
    for a, b in (("은", "는"), ("이", "가"), ("을", "를"))
]


def build_bit_table():
    """음절 인덱스 → 종성 유무 1bit (294B). LSB-first per byte."""
    syls = sorted(hangul_map.SYL_INDEX, key=lambda ch: hangul_map.SYL_INDEX[ch])
    bits = bytearray((len(syls) + 7) // 8)
    for i, ch in enumerate(syls):
        if batchim(ch):
            bits[i // 8] |= 1 << (i % 8)
    return bytes(bits)


def sjis_to_idx(code):
    """슬롯 SJIS → 음절 인덱스 (전수 검증된 산식 — 행당 188셀, 0x7F 스킵)."""
    hi, lo = code >> 8, code & 0xFF
    cell = lo - 0x40 - (1 if lo > 0x7F else 0)
    return (hi - 0x88) * 188 + cell - BASE_LIN


def fix_buffer(buf: bytearray, table: bytes, cross: int | None = 66, limit: int = 64) -> int:
    """파이썬 시뮬레이터 — asm 루틴(assemble_routine)과 **동일 의미**. 반환: 치환 수.

    buf: 스캔 시작 위치. 조립본은 [02][이름][01][조사]… 형태(02=이름색 시작, 01=복귀).
    공백·01/02는 prev(앞 음절) 유지, 숫자·영문(0x30~0x7A)은 무받침 마커(가), 그 외
    1바이트는 prev 리셋. 병기 [음절][조사A][(][조사B][)]를 종성 유무로 축약(4B 좌시프트).

    limit: 스캔 상한(asm의 a1). 워크슬롯 줄 = 64, prewrap 평문 = 128.
    cross: 조사A가 줄 끝(다음 바이트 null)일 때 '(조사B)'를 찾을 **다음 워크슬롯 인덱스**
    (asm의 a2 = 절대 포인터). 게임 자체 조판이 병기를 두 슬롯으로 가른 경우를 결합한다
    (유저 QA 07-28). `None`이면 cross-line 비활성 — asm에서는 a2에 zero guard 주소를
    넘겨 같은 효과를 낸다(0 바이트는 '('가 아니므로 판정이 자연히 실패)."""
    i, prev, fixed = 0, None, 0
    limit = min(limit, len(buf))
    while i < limit and buf[i]:
        b = buf[i]
        if b < 0x81 or b == 0xFF:  # 1바이트(반각·공백·제어)
            if b in (0x20, 0x01, 0x02):
                pass  # 공백·색제어 → prev 유지
            elif 0x30 <= b <= 0x7A:
                prev = SYL_LO  # 숫자·영문 → 무받침 마커('가')
            else:
                prev = None
            i += 1
            continue
        code = (b << 8) | buf[i + 1]
        if prev is not None and SYL_LO <= prev <= SYL_HI:  # 앞이 음절일 때만
            for a, bb in PAIRS:
                if code != a:
                    continue
                # pb(괄호 시작): 같은 줄 i+2, 없고 조사A가 줄 끝(null)이면 다음 줄 cross
                if buf[i + 2] == PAREN_L:
                    pb = i + 2
                elif (
                    buf[i + 2] == 0
                    and cross is not None
                    and len(buf) > cross + 3
                    and buf[cross] == PAREN_L
                ):
                    pb = cross
                else:
                    continue
                if (buf[pb + 1] << 8 | buf[pb + 2]) != bb or buf[pb + 3] != PAREN_R:
                    continue
                idx = sjis_to_idx(prev)
                has = table[idx // 8] >> (idx % 8) & 1
                chosen = a if has else bb
                buf[i] = chosen >> 8
                buf[i + 1] = chosen & 0xFF
                j = pb  # 4B 좌시프트: memmove(pb ← pb+4, 널 포함)
                while True:
                    src = j + 4
                    buf[j] = buf[src] if src < len(buf) else 0
                    if buf[j] == 0 and (src >= len(buf) or buf[src] == 0):
                        break
                    j += 1
                fixed += 1
                break
        prev = code
        i += 2
    return fixed


# ── MIPS 수조립 ─────────────────────────────────────────────────────────────
def _r(op, rs, rt, rd, sh, fn):
    return op << 26 | rs << 21 | rt << 16 | rd << 11 | sh << 6 | fn


def _i(op, rs, rt, imm):
    return op << 26 | rs << 21 | rt << 16 | (imm & 0xFFFF)


REG = {
    n: i
    for i, n in enumerate(
        "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 "
        "s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra".split()
    )
}


class Asm:
    def __init__(self, base):
        self.base, self.words, self.labels, self.fixups = base, [], {}, []

    def label(self, name):
        self.labels[name] = len(self.words)

    def emit(self, w):
        self.words.append(w)

    def branch(self, op, rs, rt, target):
        self.fixups.append((len(self.words), target, "b"))
        self.emit(_i(op, REG[rs], REG[rt], 0))

    def resolve(self):
        for pos, target, _kind in self.fixups:
            off = self.labels[target] - (pos + 1)
            self.words[pos] |= off & 0xFFFF
        return b"".join(struct.pack("<I", w) for w in self.words)

    # 편의 명령
    def li16(self, rt, imm):  # 0<=imm<0x10000
        self.emit(_i(0x0D, 0, REG[rt], imm))  # ori rt, zero, imm

    def lui(self, rt, imm):
        self.emit(_i(0x0F, 0, REG[rt], imm))

    def ori(self, rt, rs, imm):
        self.emit(_i(0x0D, REG[rs], REG[rt], imm))

    def addiu(self, rt, rs, imm):
        self.emit(_i(0x09, REG[rs], REG[rt], imm))

    def lbu(self, rt, off, base):
        self.emit(_i(0x24, REG[base], REG[rt], off))

    def sb(self, rt, off, base):
        self.emit(_i(0x28, REG[base], REG[rt], off))

    def sll(self, rd, rt, sh):
        self.emit(_r(0, 0, REG[rt], REG[rd], sh, 0))

    def srl(self, rd, rt, sh):
        self.emit(_r(0, 0, REG[rt], REG[rd], sh, 2))

    def srlv(self, rd, rt, rs):
        self.emit(_r(0, REG[rs], REG[rt], REG[rd], 0, 6))

    def or_(self, rd, rs, rt):
        self.emit(_r(0, REG[rs], REG[rt], REG[rd], 0, 0x25))

    def addu(self, rd, rs, rt):
        self.emit(_r(0, REG[rs], REG[rt], REG[rd], 0, 0x21))

    def subu(self, rd, rs, rt):
        self.emit(_r(0, REG[rs], REG[rt], REG[rd], 0, 0x23))

    def andi(self, rt, rs, imm):
        self.emit(_i(0x0C, REG[rs], REG[rt], imm))

    def sltiu(self, rt, rs, imm):
        self.emit(_i(0x0B, REG[rs], REG[rt], imm))

    def sltu(self, rd, rs, rt):
        self.emit(_r(0, REG[rs], REG[rt], REG[rd], 0, 0x2B))

    def beq(self, rs, rt, target):
        self.branch(0x04, rs, rt, target)

    def bne(self, rs, rt, target):
        self.branch(0x05, rs, rt, target)

    def nop(self):
        self.emit(0)

    def jr(self, rs):
        self.emit(_r(0, REG[rs], 0, 0, 0, 8))

    def mul_188(self, rd, rs, tmp):
        """rd = rs*188 = rs*192 - rs*4."""
        self.sll(rd, rs, 7)  # rs*128
        self.sll(tmp, rs, 6)  # rs*64
        self.addu(rd, rd, tmp)  # rs*192
        self.sll(tmp, rs, 2)  # rs*4
        self.subu(rd, rd, tmp)  # rs*188


def assemble_routine(free_base, table_addr, pairs_addr):
    """josa_fix(a0=str, a1=스캔 길이, a2=cross-line 후보 ptr) — 데이터 구동 쌍 루프
    (구 3쌍 언롤 860B → ~360B로 압축, 07-27).

    클린 0런이 최대 524B라 언롤판이 들어갈 자리가 없다(구판이 크래시한 0x801059A0은
    런타임 워크램으로 판명 — 덤프 실측 +0x3~+0x101A 기록). 레지스터: t0=ptr, t1=prev,
    t2=cur, t3/t4/t6=스크래치, t5=테이블, t7=쌍 ptr, t8=A코드, t9=B코드, v1=남은 쌍 수,
    at=스캔 상한. a0~a2 보존, v0 미사용(훅 복귀 직후 원명령이 재적재).
    쌍 데이터(pairs_addr): [A_hi A_lo B_hi B_lo]×3 (빅엔디언 바이트 그대로).

    a1/a2 파라미터화(07-28): 워크슬롯 줄 스캔(a1=64, a2=a0+66)과 prewrap 평문 스캔
    (a1=128, a2=zero guard로 cross 비활성)을 **한 루틴으로** 공유한다 — josa 런이 524B로
    꽉 차 사본을 둘 공간이 없다. cross 비활성을 별도 분기 대신 zero guard 주소로 푸는 건
    명령 추가 없이(=런 여유 8B 보존) 같은 효과를 내기 때문."""
    a = Asm(free_base)
    a.lui("t5", table_addr >> 16)
    a.ori("t5", "t5", table_addr & 0xFFFF)
    a.addu("t0", "a0", "zero")
    a.li16("t1", 0)
    a.addu("at", "a0", "a1")  # 스캔 상한 = a0 + a1

    a.label("scan")
    a.sltu("t3", "t0", "at")
    a.beq("t3", "zero", "done")
    a.nop()
    a.lbu("t2", 0, "t0")
    a.nop()
    a.beq("t2", "zero", "done")
    a.nop()
    a.sltiu("t3", "t2", 0x81)
    a.beq("t3", "zero", "twobyte")
    a.nop()
    # 1바이트: 공백(0x20)·색제어(0x01,0x02)는 prev 유지, 나머지는 prev 무효화
    a.li16("t3", 0x20)
    a.beq("t2", "t3", "adv1")
    a.nop()
    a.sltiu("t3", "t2", 3)  # 0x01/0x02 (0x00은 위에서 종료)
    a.bne("t3", "zero", "adv1")
    a.nop()
    # 반각 숫자(0x30~0x39)·영문자(0x41~0x5A,0x61~0x7A): 정발이 주문 레벨명(레지나01) 뒤
    # 조사를 **무받침으로 통일**하고(DOSBox 실측 07-27), 엔진이 동종 몬스터에 붙이는 식별자
    # (부엉이A/B — 런타임 append)도 알파벳이라 무받침이어야 한다(유저 지적 07-27). prev를
    # '가'(SYL_LO, 받침 0)로 세팅하면 기존 병기 판정이 자동으로 B(무받침: 는/가/를)를 뽑는다.
    # 3범위 → 단일범위 0x30~0x7A 압축(cross-line 공간 확보 07-28): 사이 부호(0x3A~40,0x5B~60)도
    # 포함되나 조사 선행이 드물고 무받침이 무난 — 등가에 가깝고 위험 없음.
    a.addiu("t3", "t2", -0x30)
    a.sltiu("t3", "t3", 0x7A - 0x30 + 1)  # 0x30~0x7A 숫자·영문(+사이부호)
    a.beq("t3", "zero", "notdigit")
    a.nop()
    a.ori("t1", "zero", SYL_LO)  # 숫자/영문 → '가' 마커(무받침)
    a.beq("zero", "zero", "adv1")
    a.nop()
    a.label("notdigit")
    a.li16("t1", 0)
    a.label("adv1")
    a.addiu("t0", "t0", 1)
    a.beq("zero", "zero", "scan")
    a.nop()

    a.label("twobyte")
    a.lbu("t3", 1, "t0")
    a.nop()
    a.sll("t2", "t2", 8)
    a.or_("t2", "t2", "t3")  # t2 = cur code

    # prev가 음절 범위일 때만 병기 검사
    a.beq("t1", "zero", "setprev")
    a.nop()
    a.ori("t3", "zero", SYL_LO)
    a.sltu("t4", "t1", "t3")
    a.bne("t4", "zero", "setprev")
    a.nop()
    a.ori("t3", "zero", SYL_HI)
    a.sltu("t4", "t3", "t1")
    a.bne("t4", "zero", "setprev")
    a.nop()

    # 쌍 루프: t7 = pairs, v1 = 3
    a.lui("t7", pairs_addr >> 16)
    a.ori("t7", "t7", pairs_addr & 0xFFFF)
    a.li16("v1", 3)
    a.label("pairloop")
    a.lbu("t8", 0, "t7")  # A hi
    a.lbu("t3", 1, "t7")  # A lo
    a.sll("t8", "t8", 8)
    a.or_("t8", "t8", "t3")
    a.bne("t2", "t8", "nextpair")
    a.nop()
    # ( B ) 확인 — 괄호 시작 pb(v0). 같은 줄 t0+2에 '(' 없고 조사A가 줄 끝(t0+2==0)이면
    # a2(다음 워크슬롯 시작)를 본다 — 게임 자체 조판이 병기를 두 워크슬롯으로 가른 cross-line
    # 케이스(요슈아의 눈을 / (를) 사용했다). 이후 B/R 확인·좌시프트 전부 pb 기준(유저 QA 07-28).
    a.addiu("v0", "t0", 2)  # same-line 후보: pb = t0+2
    a.lbu("t3", 0, "v0")
    a.li16("t4", PAREN_L)
    a.beq("t3", "t4", "pbok")  # t0+2 == '(' → same-line
    a.nop()
    a.bne("t3", "zero", "nextpair")  # t0+2 != null → 줄 중간(줄 끝 아님) → cross 아님
    a.nop()
    a.addu("v0", "a2", "zero")  # cross-line 후보: pb = a2 (zero guard면 판정 실패 → 비활성)
    a.lbu("t3", 0, "v0")
    a.li16("t4", PAREN_L)
    a.bne("t3", "t4", "nextpair")  # 다음 줄도 '(' 아님 → next pair
    a.nop()
    a.label("pbok")
    a.lbu("t9", 2, "t7")  # B hi
    a.lbu("t3", 3, "t7")  # B lo
    a.sll("t9", "t9", 8)
    a.or_("t9", "t9", "t3")
    a.lbu("t3", 1, "v0")  # B at pb+1,+2
    a.lbu("t4", 2, "v0")
    a.sll("t3", "t3", 8)
    a.or_("t3", "t3", "t4")
    a.bne("t3", "t9", "nextpair")
    a.nop()
    a.lbu("t3", 3, "v0")  # PAREN_R at pb+3
    a.li16("t4", PAREN_R)
    a.bne("t3", "t4", "nextpair")
    a.nop()
    # idx = (prev_hi-0x88)*188 + cell - 94
    a.srl("t3", "t1", 8)
    a.addiu("t3", "t3", -0x88)
    a.mul_188("t4", "t3", "t6")
    a.andi("t3", "t1", 0xFF)
    a.addiu("t3", "t3", -0x40)
    a.sltiu("t6", "t3", 0x40)  # lo-0x40 < 0x40 ↔ lo < 0x80 (0x7F 스킵 전)
    a.bne("t6", "zero", "cell_ok")
    a.nop()
    a.addiu("t3", "t3", -1)
    a.label("cell_ok")
    a.addu("t4", "t4", "t3")
    a.addiu("t4", "t4", -BASE_LIN)
    # bit = table[idx>>3] >> (idx&7) & 1
    a.srl("t3", "t4", 3)
    a.addu("t3", "t5", "t3")
    a.lbu("t6", 0, "t3")
    a.andi("t7", "t4", 7)  # t7(쌍 ptr) 재사용 — 치환 후 setprev로 가므로 안전
    a.srlv("t6", "t6", "t7")
    a.andi("t6", "t6", 1)
    a.bne("t6", "zero", "write")  # 받침 → A(t8)
    a.nop()
    a.addu("t8", "t9", "zero")  # 무받침 → B
    a.label("write")
    a.srl("t3", "t8", 8)
    a.sb("t3", 0, "t0")
    a.sb("t8", 1, "t0")  # sb는 하위 8bit만
    # 4B 좌시프트: memmove(pb ← pb+4, 널 포함) — pb는 괄호 시작(같은 줄 t0+2 또는 다음 줄 a0+66)
    a.addu("t3", "v0", "zero")
    a.label("mv")
    a.lbu("t4", 4, "t3")
    a.nop()
    a.sb("t4", 0, "t3")
    a.bne("t4", "zero", "mvnext")
    a.nop()
    a.beq("zero", "zero", "setprev")
    a.nop()
    a.label("mvnext")
    a.addiu("t3", "t3", 1)
    a.beq("zero", "zero", "mv")
    a.nop()
    a.label("nextpair")
    a.addiu("t7", "t7", 4)
    a.addiu("v1", "v1", -1)
    a.bne("v1", "zero", "pairloop")
    a.nop()

    a.label("setprev")
    a.addu("t1", "t2", "zero")
    a.addiu("t0", "t0", 2)
    a.beq("zero", "zero", "scan")
    a.nop()

    a.label("done")
    a.jr("ra")
    a.nop()
    return a.resolve()


# ── 훅 결합 (ED.EXE 전투 텍스트 조립 함수) ──────────────────────────────────
# 훅 지점: 0x800B2054 (조립 완료 직후, 렌더 직전 — 워크버퍼에 완성 조립본 존재,
# 2026-07-20 DuckStation 인게임 확정). 워크 = 0x801190B0 + 줄*66, 최대 6줄.
# ⚠ 07-27 재설계: 훅을 **2워드**(0x800B2054=j stub, 0x800B2058=nop)로 교체 —
# 1워드 훅은 다음 명령(lw v1,0x28(fp))이 j의 지연 슬롯으로 선실행되고 복귀 후 재실행됐다
# (load라 무해였지만 정리). 원명령 2개를 stub 끝에서 재현하고 0x800B205C로 복귀.
HOOK_ADDR = 0x800B2054
HOOK_ORIG = 0x87C20016  # lh v0, 0x16(fp)
HOOK_ORIG2 = 0x8FC30028  # lw v1, 0x28(fp)
HOOK_RESUME = 0x800B205C
WORK_BASE = 0x801190B0
LINE_STRIDE = 66  # 줄 슬롯 stride(HANDOFF 렌더러 실측 — 텍스트 0x40 + 메타 2)
LINE_LIMIT = 64  # 워크슬롯 1줄의 텍스트 바이트(stride − 메타 2)
FP = 30
GP = 28

# ── 훅 2: 자동 개행(prewrap) 앞 early-resolve — HANDOFF #2/#3 ────────────────
# 메시지 박스 경로(정적 RE 07-28, capstone):
#   0x800B1D50 strcpy(fp+0x18, msg)        ← 호출자 스택 128B 사본(fp+0x18~fp+0x98)
#   0x800B1D60 jal 0x800ACE18              ← **자동 개행 삽입기**(글자단위, 최대 29열)
#                                            폭 넘치면 0x0A를 끼워 제자리 재작성(strcpy 복귀)
#   0x800B1D7C jal 0x800B1E58              ← 0x0A로만 잘라 워크슬롯(0x801190B0+k*66)에 조립
#                                            ↳ 기존 훅 0x800B2054가 여기서 병기 해결
#   0x800B1DF0 jal 0x800B2410 → 0x800AD3A8 ← 워크 줄을 그리며 남은 초과분만 재차 개행
# 즉 **개행은 기존 훅보다 먼저 결정된다** → 폭 계산이 미해결 병기(을(를)=3슬롯)로 이뤄져
# 줄이 이르게 갈렸다("세리오스는 횃불을 사 / 용했다" — 유저 재현 07-28).
# 해법: prewrap **호출 자체를 가로채** 평문에서 병기를 먼저 해결한다. 0x800ACE18의 호출자는
# 이 한 곳뿐이고(전수 jal 스캔), 버퍼는 호출자 전용 스택 사본이며 결과는 항상 짧아진다.
# prewrap·assemble 모두 자체적으로 strlen을 다시 재므로 길이 불일치도 없다.
PREWRAP_ADDR = 0x800ACE18  # 자동 개행 삽입기
PREWRAP_CALL = 0x800B1D60  # 유일 호출 지점 (jal 0x800ACE18, 지연 슬롯은 nop)
PREWRAP_CALL_ORIG = 0x0C000000 | ((PREWRAP_ADDR >> 2) & 0x03FFFFFF)
PREWRAP_LIMIT = 128  # 호출자 스택 버퍼 fp+0x18~fp+0x98


def assemble_hook_stub(stub_base, josa_addr, noop=False):
    """0x800B2054에서 j로 진입. 워크 6줄(0x801190B0 + k*66)을 전부 josa_fix로 스캔 —
    훅이 줄 조립마다 재진입하므로 멱등 다중 스캔은 무해하고, "현재 줄" 인덱스를 계산할
    필요가 없다(구판 크래시 1차 원인 = 진입 시점 gp+0x440 미세팅 동적 계산).

    ra·s0·s1을 sp에 저장/복원. josa_fix는 t*·at·v1만 clobber — v0/v1은 복귀 직후
    원명령이 재적재하므로 안전. a0는 훅 지점에서 죽은 레지스터(루프B가 재설정).

    noop=True: josa 스캔·프레임을 전부 빼고 **원명령 2개 + 복귀**만 한다. 훅 지점 자체
    (j 재진입 타겟 0x800B2054 포함 두 경로)와 지연 슬롯 처리가 안전한지 josa_fix와 분리해
    A/B로 확인하기 위한 진단 스텁(HANDOFF 재개절차 2)."""
    if noop:
        a = Asm(stub_base)
        a.emit(HOOK_ORIG)  # lh v0, 0x16(fp)
        a.emit(HOOK_ORIG2)  # lw v1, 0x28(fp)
        a.emit(0x08000000 | ((HOOK_RESUME >> 2) & 0x03FFFFFF))  # j 0x800B205C
        a.nop()
        return a.resolve()
    a = Asm(stub_base)
    a.addiu("sp", "sp", -16)
    a.emit(_i(0x2B, REG["sp"], REG["ra"], 4))  # sw ra, 4(sp)
    a.emit(_i(0x2B, REG["sp"], REG["s0"], 8))  # sw s0, 8(sp)
    a.emit(_i(0x2B, REG["sp"], REG["s1"], 12))  # sw s1, 12(sp)
    a.lui("s0", WORK_BASE >> 16)
    a.ori("s0", "s0", WORK_BASE & 0xFFFF)  # s0 = 워크 줄 포인터
    a.li16("s1", 6)  # 줄 수
    a.label("slot")
    a.addu("a0", "s0", "zero")
    a.li16("a1", LINE_LIMIT)  # 스캔 상한 = 줄 텍스트 64B
    a.addiu("a2", "s0", LINE_STRIDE)  # cross-line 후보 = 다음 워크슬롯
    a.lui("t3", josa_addr >> 16)
    a.ori("t3", "t3", josa_addr & 0xFFFF)
    a.emit(_r(0, REG["t3"], 0, REG["ra"], 0, 9))  # jalr ra, t3
    a.nop()
    a.addiu("s0", "s0", LINE_STRIDE)
    a.addiu("s1", "s1", -1)
    a.bne("s1", "zero", "slot")
    a.nop()
    a.emit(_i(0x23, REG["sp"], REG["ra"], 4))  # lw ra, 4(sp)
    a.emit(_i(0x23, REG["sp"], REG["s0"], 8))  # lw s0, 8(sp)
    a.emit(_i(0x23, REG["sp"], REG["s1"], 12))  # lw s1, 12(sp)
    a.addiu("sp", "sp", 16)
    a.emit(HOOK_ORIG)  # lh v0, 0x16(fp)
    a.emit(HOOK_ORIG2)  # lw v1, 0x28(fp)
    a.emit(0x08000000 | ((HOOK_RESUME >> 2) & 0x03FFFFFF))  # j 0x800B205C
    a.nop()
    return a.resolve()


def assemble_prewrap_stub(stub_base, josa_addr, zero_addr):
    """훅 2 스텁 — `jal 0x800ACE18`(prewrap) 자리에 끼어들어 **평문 병기부터 해결**한 뒤
    원래 대상으로 꼬리 점프한다. 상세 근거는 위 PREWRAP_* 상수 주석.

    진입 시 a0 = 문자열(호출 지연 슬롯이 nop이라 이미 세팅됨). josa_fix를 a1=128(평문 상한),
    a2=zero guard(cross-line 비활성)로 호출하고 ra를 그대로 유지해 `j 0x800ACE18` —
    prewrap이 호출자(0x800B1D68)에게 직접 복귀한다(스택 프레임 누수 없음).
    a0 저장/복원은 josa_fix가 a0를 보존하더라도 계약을 명시적으로 붙들기 위한 것."""
    a = Asm(stub_base)
    a.addiu("sp", "sp", -8)
    a.emit(_i(0x2B, REG["sp"], REG["ra"], 4))  # sw ra, 4(sp)
    a.emit(_i(0x2B, REG["sp"], REG["a0"], 0))  # sw a0, 0(sp)
    a.li16("a1", PREWRAP_LIMIT)
    a.lui("a2", zero_addr >> 16)
    a.ori("a2", "a2", zero_addr & 0xFFFF)
    a.emit(0x0C000000 | ((josa_addr >> 2) & 0x03FFFFFF))  # jal josa_fix
    a.nop()
    a.emit(_i(0x23, REG["sp"], REG["a0"], 0))  # lw a0, 0(sp)
    a.emit(_i(0x23, REG["sp"], REG["ra"], 4))  # lw ra, 4(sp)
    a.addiu("sp", "sp", 8)
    a.emit(0x08000000 | ((PREWRAP_ADDR >> 2) & 0x03FFFFFF))  # j 0x800ACE18 (ra 유지 = 꼬리호출)
    a.nop()
    return a.resolve()


def build_and_patch(ed: bytearray):
    """조사 훅 결합 — 검증된 클린 0런 2개에 [josa_fix] / [테이블+쌍+stub] 배치 후
    0x800B2054/58을 j stub/nop으로 패치.

    ⚠ 배치 이력: 구판은 0x801059A0(0런처럼 보였으나 **런타임 워크램** — 필드·전투 덤프
    실측 +0x3~+0x101A 기록)에 놓아 코드가 덮여 크래시했다(07-26 도너 검증에서 규명).
    현 위치는 3중 검증(파일 0·참조 0건·런타임 덤프 0 유지) 통과한 도너 풀 예약분."""
    table = build_bit_table()
    table += b"\x00" * (-len(table) % 4)  # ⚠ 스텁 4정렬 — j 인코딩이 하위 2비트를 버린다
    zero_guard = b"\x00\x00\x00\x00"  # cross-line 비활성용 상수 0 (josa_fix a2)
    pairs = b"".join(struct.pack(">HH", a, b) for a, b in PAIRS)  # 빅엔디언 코드 그대로
    josa_addr = PLACE_JOSA_RAM
    table_addr = PLACE_DATA_RAM
    zero_addr = table_addr + len(table)
    pairs_addr = zero_addr + len(zero_guard)
    josa = assemble_routine(josa_addr, table_addr, pairs_addr)
    stub_addr = pairs_addr + len(pairs)
    assert stub_addr % 4 == 0, "스텁 비정렬"
    noop = os.environ.get("JOSA_NOOP") == "1"  # 진단 A/B: josa 없이 훅 지점 안전성만 검증
    stub = assemble_hook_stub(stub_addr, josa_addr, noop=noop)
    pre_addr = stub_addr + len(stub)
    pre_stub = assemble_prewrap_stub(pre_addr, josa_addr, zero_addr)
    data = table + zero_guard + pairs + stub + pre_stub
    assert len(josa) <= 0x0BF7E8 - 0x0BF5DC, f"josa 루틴 {len(josa)}B — 런 초과"
    assert len(data) <= 0x0C1268 - 0x0C105C, f"데이터+스텁 {len(data)}B — 런 초과"

    def fo(ram):
        return ram - 0x80010000 + 0x800

    for ram, blob in ((josa_addr, josa), (table_addr, data)):
        p = fo(ram)
        assert all(b == 0 for b in ed[p : p + len(blob)]), f"배치 영역 0 아님 @0x{ram:08X}"
        ed[p : p + len(blob)] = blob
    hp = fo(HOOK_ADDR)
    assert struct.unpack_from("<I", ed, hp)[0] == HOOK_ORIG, "훅 지점 원명령 불일치"
    assert struct.unpack_from("<I", ed, hp + 4)[0] == HOOK_ORIG2, "훅 지점+4 원명령 불일치"
    ed[hp : hp + 4] = struct.pack("<I", 0x08000000 | ((stub_addr >> 2) & 0x03FFFFFF))
    ed[hp + 4 : hp + 8] = struct.pack("<I", 0)  # nop (지연 슬롯 정리)
    # 훅 2: prewrap 호출 지점의 jal 타깃만 우리 스텁으로 — 원명령 재현이 필요 없는 1워드 패치.
    pp = fo(PREWRAP_CALL)
    assert struct.unpack_from("<I", ed, pp)[0] == PREWRAP_CALL_ORIG, "prewrap 호출 원명령 불일치"
    if os.environ.get("JOSA_NOPREWRAP") != "1":  # 진단 A/B: 훅 2만 빼고 빌드
        ed[pp : pp + 4] = struct.pack("<I", 0x0C000000 | ((pre_addr >> 2) & 0x03FFFFFF))
    return len(josa) + len(data), josa_addr, stub_addr, pre_addr


# 배치: 도너 검증(07-26) 통과 클린 0런 2개 — reinsert DONOR_RUNS에서 예약 제외됨.
PLACE_JOSA_RAM = 0x0BF5DC - 0x800 + 0x80010000  # 루틴 (런 524B)
PLACE_DATA_RAM = 0x0C105C - 0x800 + 0x80010000  # 테이블 294B + 쌍 12B + 스텁


ED_LBA, ED_SIZE = 257, 1021952


def main():
    """build.py 체인용 — 최종 디스크의 ED.EXE에 조사 훅을 제자리 결합."""
    from common import WORK_DIR, extract, write_user_data

    target = os.path.join(WORK_DIR, "Eiyuu Densetsu (KR).bin")
    if not os.path.exists(target):
        raise SystemExit(f"대상 이미지 없음: {target} — build.py 먼저")
    ed = bytearray(extract(ED_LBA, ED_SIZE, path=target))
    size, josa_addr, stub_addr, pre_addr = build_and_patch(ed)
    with open(target, "r+b") as f:
        n = write_user_data(f, ED_LBA, ed)
    print(
        f"조사 훅: {size}B (josa 0x{josa_addr:08X}, stub 0x{stub_addr:08X}, "
        f"prewrap stub 0x{pre_addr:08X}) → 0x{HOOK_ADDR:08X}·0x{PREWRAP_CALL:08X} 훅, "
        f"섹터 {n}개 수정"
    )


# ── 셀프테스트: MIPS 미니 인터프리터 ────────────────────────────────────────
# 파이썬 시뮬(fix_buffer)만 맞으면 **어셈블된 바이트가 틀려도 통과**한다 — 소프트락 이력이
# 있는 훅이라 실제 인코딩을 돌려본다. josa_fix가 쓰는 명령만 구현(지연 슬롯 포함).
_SPECIAL = {  # funct → (rd 계산)
    0x00: lambda rs, rt, sh: (rt << sh) & 0xFFFFFFFF,  # sll
    0x02: lambda rs, rt, sh: (rt & 0xFFFFFFFF) >> sh,  # srl
    0x06: lambda rs, rt, sh: (rt & 0xFFFFFFFF) >> (rs & 31),  # srlv
    0x21: lambda rs, rt, sh: (rs + rt) & 0xFFFFFFFF,  # addu
    0x23: lambda rs, rt, sh: (rs - rt) & 0xFFFFFFFF,  # subu
    0x25: lambda rs, rt, sh: rs | rt,  # or
    0x2B: lambda rs, rt, sh: int((rs & 0xFFFFFFFF) < (rt & 0xFFFFFFFF)),  # sltu
}


def _emulate(code, base, mem, regs, max_steps=100000):
    """code(base에 적재)를 jr $ra 까지 실행. mem = {addr: byte} (dict, 기본 0)."""
    r = [0] * 32
    for k, v in regs.items():
        r[REG[k]] = v
    pc, steps, pending = base, 0, None
    while True:
        if steps > max_steps:
            raise AssertionError("무한 루프 — 스캔 상한/종료 조건 확인")
        steps += 1
        w = struct.unpack_from("<I", code, pc - base)[0]
        op, rs, rt, rd, sh, fn = (
            w >> 26,
            (w >> 21) & 31,
            (w >> 16) & 31,
            (w >> 11) & 31,
            (w >> 6) & 31,
            w & 63,
        )
        imm = w & 0xFFFF
        simm = imm - 0x10000 if imm >= 0x8000 else imm
        nxt, target = pc + 4, None
        if op == 0 and fn == 8:  # jr
            if rs == REG["ra"]:
                return r, steps
            raise AssertionError("예상 밖 jr")
        elif op == 0:
            if fn in _SPECIAL:
                r[rd] = _SPECIAL[fn](r[rs], r[rt], sh)
            else:
                raise AssertionError(f"미구현 SPECIAL funct 0x{fn:02X}")
        elif op == 0x04:  # beq
            target = pc + 4 + simm * 4 if r[rs] == r[rt] else None
        elif op == 0x05:  # bne
            target = pc + 4 + simm * 4 if r[rs] != r[rt] else None
        elif op == 0x09:  # addiu
            r[rt] = (r[rs] + simm) & 0xFFFFFFFF
        elif op == 0x0B:  # sltiu
            r[rt] = int((r[rs] & 0xFFFFFFFF) < (simm & 0xFFFFFFFF))
        elif op == 0x0C:  # andi
            r[rt] = r[rs] & imm
        elif op == 0x0D:  # ori
            r[rt] = r[rs] | imm
        elif op == 0x0F:  # lui
            r[rt] = (imm << 16) & 0xFFFFFFFF
        elif op == 0x24:  # lbu
            r[rt] = mem.get((r[rs] + simm) & 0xFFFFFFFF, 0)
        elif op == 0x28:  # sb
            mem[(r[rs] + simm) & 0xFFFFFFFF] = r[rt] & 0xFF
        else:
            raise AssertionError(f"미구현 op 0x{op:02X}")
        r[0] = 0
        if pending is not None:  # 직전 명령이 지연 슬롯이었다 → 분기 성립 주소로
            nxt, pending = pending, None
        elif target is not None:
            pending = target
        pc = nxt


def _sjis(s):
    return b"".join(struct.pack(">H", hangul_map.syllable_sjis(c)) for c in s)


def _selftest():
    table = build_bit_table()
    table_pad = table + b"\x00" * (-len(table) % 4)
    zero_guard = b"\x00\x00\x00\x00"
    pairs = b"".join(struct.pack(">HH", a, b) for a, b in PAIRS)
    zero_addr = PLACE_DATA_RAM + len(table_pad)
    pairs_addr = zero_addr + len(zero_guard)
    josa = assemble_routine(PLACE_JOSA_RAM, PLACE_DATA_RAM, pairs_addr)
    stub_addr = pairs_addr + len(pairs)
    stub = assemble_hook_stub(stub_addr, PLACE_JOSA_RAM)
    pre_addr = stub_addr + len(stub)
    pre = assemble_prewrap_stub(pre_addr, PLACE_JOSA_RAM, zero_addr)
    data = table_pad + zero_guard + pairs + stub + pre
    print(
        f"데이터+스텁 {len(data)}B (테이블 {len(table_pad)} + guard 4 + 쌍 {len(pairs)} + "
        f"stub {len(stub)} + prewrap stub {len(pre)}) · josa {len(josa)}B "
        f"[런 한도 각 524B, 여유 josa {524 - len(josa)}B / 데이터 {524 - len(data)}B]"
    )
    assert len(josa) <= 524 and len(data) <= 524, "런 초과"

    # ── 워크슬롯(줄) 모드 케이스: (설명, 입력 줄들) — 각 1회 치환 기대 ──────
    P_L, P_R = bytes([PAREN_L]), bytes([PAREN_R])
    cases = [
        ("받침 O 같은 줄", [_sjis("류난") + _sjis("은") + P_L + _sjis("는") + P_R]),
        ("받침 X 같은 줄", [_sjis("네리아") + _sjis("은") + P_L + _sjis("는") + P_R]),
        (
            "이름색 제어코드",
            [b"\x02" + _sjis("류난") + b"\x01" + _sjis("이") + P_L + _sjis("가") + P_R],
        ),
        ("영문 식별자 → 무받침", [_sjis("부엉이") + b"A" + _sjis("을") + P_L + _sjis("를") + P_R]),
        ("cross-line", [_sjis("눈") + _sjis("을"), P_L + _sjis("를") + P_R + _sjis("사용")]),
    ]
    for desc, lines in cases:
        buf = bytearray()
        for ln in lines:
            buf += ln.ljust(LINE_STRIDE, b"\x00")
        buf += b"\x00" * LINE_STRIDE  # 다음 슬롯 여유
        sim = bytearray(buf)
        n_sim = fix_buffer(sim, table, cross=LINE_STRIDE, limit=LINE_LIMIT)
        BUF = 0x80100000
        mem = {BUF + i: b for i, b in enumerate(buf)}
        mem.update({PLACE_DATA_RAM + i: b for i, b in enumerate(data)})
        _emulate(
            josa,
            PLACE_JOSA_RAM,
            mem,
            {"a0": BUF, "a1": LINE_LIMIT, "a2": BUF + LINE_STRIDE, "ra": 0},
        )
        asm = bytes(mem.get(BUF + i, 0) for i in range(len(buf)))
        assert n_sim == 1, f"{desc}: 시뮬 치환 {n_sim}회(1 기대)"
        assert asm == bytes(sim), (
            f"{desc}: asm ≠ 시뮬\n asm={asm[:24].hex()}\n sim={bytes(sim[:24]).hex()}"
        )
        print(f"  ✓ {desc}: {asm[:20].hex()}")

    # ── prewrap 모드(평문·널종단, cross 비활성) ─────────────────────────────
    flat = _sjis("세리오스") + _sjis("은") + P_L + _sjis("는") + P_R + b" "
    flat += (
        _sjis("횃불") + _sjis("을") + P_L + _sjis("를") + P_R + b" " + _sjis("사용했다") + b"\x00"
    )
    sim = bytearray(flat) + b"\x00" * 8
    n_sim = fix_buffer(sim, table, cross=None, limit=PREWRAP_LIMIT)
    BUF = 0x80100000
    mem = {BUF + i: b for i, b in enumerate(flat)}
    mem.update({PLACE_DATA_RAM + i: b for i, b in enumerate(data)})
    # 스텁 경유(a0만 주고 a1/a2는 스텁이 세팅) — jal josa_fix를 인라인으로 대신 실행
    _emulate(josa, PLACE_JOSA_RAM, mem, {"a0": BUF, "a1": PREWRAP_LIMIT, "a2": zero_addr, "ra": 0})
    asm = bytes(mem.get(BUF + i, 0) for i in range(len(flat)))
    assert n_sim == 2, f"prewrap: 시뮬 치환 {n_sim}회(2 기대)"
    assert asm == bytes(sim[: len(flat)]), "prewrap: asm ≠ 시뮬"
    want = (
        _sjis("세리오스")
        + _sjis("는")
        + b" "
        + _sjis("횃불")
        + _sjis("을")
        + b" "
        + _sjis("사용했다")
    )
    assert asm.startswith(want), f"prewrap 결과 불일치: {asm.hex()}"
    print(f"  ✓ prewrap 평문 2치환: {asm[: len(want)].hex()}")
    # 길이 검증 — 병기 2개(각 4B) 제거 = 8B 단축, 폭 계산이 최종 글자수와 일치해야 한다.
    assert asm.index(0) == len(flat) - 1 - 8, "단축 길이 불일치"

    # zero guard가 cross-line을 실제로 비활성화하는지 (평문 끝 조사A + 뒤따르는 '(를)')
    edge = _sjis("눈") + _sjis("을") + b"\x00" + P_L + _sjis("를") + P_R + b"\x00"
    mem = {BUF + i: b for i, b in enumerate(edge)}
    mem.update({PLACE_DATA_RAM + i: b for i, b in enumerate(data)})
    _emulate(josa, PLACE_JOSA_RAM, mem, {"a0": BUF, "a1": PREWRAP_LIMIT, "a2": zero_addr, "ra": 0})
    assert bytes(mem.get(BUF + i, 0) for i in range(len(edge))) == edge, "zero guard 비활성 실패"
    print("  ✓ zero guard: cross-line 비활성 확인")

    from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs

    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    for name, blob in (("josa", josa), ("stub", stub), ("prewrap stub", pre)):
        n = sum(1 for _ in md.disasm(blob, 0))
        assert n == len(blob) // 4, f"{name}: capstone {n}/{len(blob) // 4} — 미디코드 명령"
        print(f"  ✓ capstone {name}: {n}/{len(blob) // 4} instr")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        _selftest()
    else:
        main()
