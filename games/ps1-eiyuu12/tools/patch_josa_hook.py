"""동적 조사 훅 — 렌더 직전 문자열 버퍼의 조사 병기(은(는)·이(가)·을(를))를 정확 조사로 재작성.

전투 메시지의 런타임 %s 치환 자리는 빌드 시점에 앞말을 모름 → 병기로 넣어두고,
표시 직전에 이 루틴이 버퍼를 1패스 스캔해 [음절][조사A][(][조사B][)] 패턴을
앞 음절의 종성 유무(비트테이블)로 조사 하나로 축약한다(6B 좌시프트).
설계·조사 이력: docs/josa-hook-devlog.md. 종성 판정 근거: shared/text/josa.py.

배치(예정): ED.EXE 내 빈 영역(RAM FREE_BASE)에 [비트테이블 294B][루틴]을 싣고,
텍스트 렌더러 진입점(HOOK_ADDR — 라이브 특정 후 확정)에 j-훅.
현재 상태: 테이블·루틴 생성 + 파이썬 시뮬레이터 + capstone 자가검증까지. 훅 지점
확정 전이라 build.py 체인 미편입.
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


def fix_buffer(buf: bytearray, table: bytes) -> int:
    """파이썬 시뮬레이터 — asm 루틴과 동일 의미. 반환: 치환 수."""
    i, prev, fixed = 0, None, 0
    while i < len(buf) and buf[i]:
        b = buf[i]
        if b < 0x81 or b in (0xFF,):  # 1바이트(반각·공백·제어)
            # 조립본은 [02][이름][01][조사]… 형태(색상 제어코드 02=이름색 시작, 01=복귀).
            # 공백·색제어(01/02)는 prev(앞 음절) 유지 — 조사 앞의 01을 건너뛰고 이름을 봐야
            # 조사를 고른다(2026-07-20 인게임 확인). 반각 부호·개행 등은 prev 리셋.
            if b not in (0x20, 0x01, 0x02):
                prev = None
            i += 1
            continue
        code = (b << 8) | buf[i + 1]
        # 병기 패턴? code==조사A, 이어서 ( 조사B )
        for a, bb in PAIRS:
            if (
                code == a
                and i + 6 <= len(buf)
                and buf[i + 2] == PAREN_L
                and (buf[i + 3] << 8 | buf[i + 4]) == bb
                and buf[i + 5] == PAREN_R
                and prev is not None
                and SYL_LO <= prev <= SYL_HI
            ):
                idx = sjis_to_idx(prev)
                has = table[idx // 8] >> (idx % 8) & 1
                chosen = a if has else bb
                buf[i] = chosen >> 8
                buf[i + 1] = chosen & 0xFF
                # 4B 좌시프트 (널 포함) — 패턴 6B 중 2B만 남김
                j = i + 2
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
    """josa_fix(a0=str) — 데이터 구동 쌍 루프(구 3쌍 언롤 860B → ~360B로 압축, 07-27).

    클린 0런이 최대 524B라 언롤판이 들어갈 자리가 없다(구판이 크래시한 0x801059A0은
    런타임 워크램으로 판명 — 덤프 실측 +0x3~+0x101A 기록). 레지스터: t0=ptr, t1=prev,
    t2=cur, t3/t4/t6=스크래치, t5=테이블, t7=쌍 ptr, t8=A코드, t9=B코드, v1=남은 쌍 수,
    at=스캔 상한. a0 보존, v0 미사용(훅 복귀 직후 원명령이 재적재).
    쌍 데이터(pairs_addr): [A_hi A_lo B_hi B_lo]×3 (빅엔디언 바이트 그대로)."""
    a = Asm(free_base)
    a.lui("t5", table_addr >> 16)
    a.ori("t5", "t5", table_addr & 0xFFFF)
    a.addu("t0", "a0", "zero")
    a.li16("t1", 0)
    a.addiu("at", "a0", 64)  # 스캔 상한 = 워크 슬롯 1줄(66B stride) 내

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
    # 반각 숫자(0x30~0x39): 정발이 주문 레벨명(레지나01 등) 뒤 조사를 **무받침으로 통일**한다
    # (DOSBox 실측 2026-07-27). prev를 '가'(SYL_LO, 받침 0)로 세팅하면 기존 병기 판정이
    # 자동으로 B(무받침: 는/가/를)를 뽑는다 — 테이블·판정부 무변경. t2는 이미 1바이트값.
    a.addiu("t3", "t2", -0x30)
    a.sltiu("t3", "t3", 10)  # 0x30~0x39
    a.beq("t3", "zero", "notdigit")
    a.nop()
    a.ori("t1", "zero", SYL_LO)  # 숫자 → '가' 마커(무받침)
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
    # ( B ) 확인 — 괄호는 반각 1바이트
    a.lbu("t3", 2, "t0")
    a.li16("t4", PAREN_L)
    a.bne("t3", "t4", "nextpair")
    a.nop()
    a.lbu("t9", 2, "t7")  # B hi
    a.lbu("t3", 3, "t7")  # B lo
    a.sll("t9", "t9", 8)
    a.or_("t9", "t9", "t3")
    a.lbu("t3", 3, "t0")
    a.lbu("t4", 4, "t0")
    a.sll("t3", "t3", 8)
    a.or_("t3", "t3", "t4")
    a.bne("t3", "t9", "nextpair")
    a.nop()
    a.lbu("t3", 5, "t0")
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
    # 4B 좌시프트: memmove(t0+2 ← t0+6, 널 포함)
    a.addiu("t3", "t0", 2)
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
FP = 30
GP = 28


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


def build_and_patch(ed: bytearray):
    """조사 훅 결합 — 검증된 클린 0런 2개에 [josa_fix] / [테이블+쌍+stub] 배치 후
    0x800B2054/58을 j stub/nop으로 패치.

    ⚠ 배치 이력: 구판은 0x801059A0(0런처럼 보였으나 **런타임 워크램** — 필드·전투 덤프
    실측 +0x3~+0x101A 기록)에 놓아 코드가 덮여 크래시했다(07-26 도너 검증에서 규명).
    현 위치는 3중 검증(파일 0·참조 0건·런타임 덤프 0 유지) 통과한 도너 풀 예약분."""
    table = build_bit_table()
    table += b"\x00" * (-len(table) % 4)  # ⚠ 스텁 4정렬 — j 인코딩이 하위 2비트를 버린다
    pairs = b"".join(struct.pack(">HH", a, b) for a, b in PAIRS)  # 빅엔디언 코드 그대로
    josa_addr = PLACE_JOSA_RAM
    table_addr = PLACE_DATA_RAM
    pairs_addr = table_addr + len(table)
    josa = assemble_routine(josa_addr, table_addr, pairs_addr)
    stub_addr = pairs_addr + len(pairs)
    assert stub_addr % 4 == 0, "스텁 비정렬"
    noop = os.environ.get("JOSA_NOOP") == "1"  # 진단 A/B: josa 없이 훅 지점 안전성만 검증
    stub = assemble_hook_stub(stub_addr, josa_addr, noop=noop)
    assert len(josa) <= 0x0BF7E8 - 0x0BF5DC, f"josa 루틴 {len(josa)}B — 런 초과"
    assert len(table) + len(pairs) + len(stub) <= 0x0C1268 - 0x0C105C, "데이터+스텁 런 초과"

    def fo(ram):
        return ram - 0x80010000 + 0x800

    for ram, blob in ((josa_addr, josa), (table_addr, table + pairs + stub)):
        p = fo(ram)
        assert all(b == 0 for b in ed[p : p + len(blob)]), f"배치 영역 0 아님 @0x{ram:08X}"
        ed[p : p + len(blob)] = blob
    hp = fo(HOOK_ADDR)
    assert struct.unpack_from("<I", ed, hp)[0] == HOOK_ORIG, "훅 지점 원명령 불일치"
    assert struct.unpack_from("<I", ed, hp + 4)[0] == HOOK_ORIG2, "훅 지점+4 원명령 불일치"
    ed[hp : hp + 4] = struct.pack("<I", 0x08000000 | ((stub_addr >> 2) & 0x03FFFFFF))
    ed[hp + 4 : hp + 8] = struct.pack("<I", 0)  # nop (지연 슬롯 정리)
    return len(josa) + len(table) + len(pairs) + len(stub), josa_addr, stub_addr


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
    size, josa_addr, stub_addr = build_and_patch(ed)
    with open(target, "r+b") as f:
        n = write_user_data(f, ED_LBA, ed)
    print(
        f"조사 훅: {size}B (josa 0x{josa_addr:08X}, stub 0x{stub_addr:08X}) "
        f"→ 0x{HOOK_ADDR:08X} 훅, 섹터 {n}개 수정"
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        pass  # 아래 셀프테스트로 진행
    else:
        main()
        sys.exit(0)
    table = build_bit_table()
    pairs = b"".join(struct.pack(">HH", a, b) for a, b in PAIRS)
    pairs_addr = PLACE_DATA_RAM + len(table)
    josa = assemble_routine(PLACE_JOSA_RAM, PLACE_DATA_RAM, pairs_addr)
    stub_addr = pairs_addr + len(pairs)
    stub = assemble_hook_stub(stub_addr, PLACE_JOSA_RAM)
    print(
        f"테이블 {len(table)}B + 쌍 {len(pairs)}B + josa {len(josa)}B + stub {len(stub)}B"
        f" (런 한도: josa 524B, 데이터+스텁 524B)"
    )
    try:
        from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs

        md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
        nj = sum(1 for _ in md.disasm(josa, 0))
        ns = sum(1 for _ in md.disasm(stub, 0))
        print(f"capstone: josa {nj}/{len(josa) // 4}, stub {ns}/{len(stub) // 4} instr")
    except ImportError:
        pass
