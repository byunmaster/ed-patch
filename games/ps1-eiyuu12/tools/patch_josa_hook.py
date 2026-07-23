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


def assemble_routine(free_base, table_addr):
    """josa_fix(a0=str) — t 레지스터만 사용(caller-saved), a0 보존.

    스캔 상태: t0=cur ptr, t1=prev code(0=없음), t2=cur code, t3/t4=스크래치,
    t5=테이블 베이스, t6/t7=패턴 비교, t8=쌍 테이블 ptr, t9=시프트용.
    """
    a = Asm(free_base)
    # 쌍 데이터는 루틴 뒤에 붙임: [A hi lo B hi lo]×3 (big-endian 코드 그대로)
    a.lui("t5", table_addr >> 16)
    a.ori("t5", "t5", table_addr & 0xFFFF)
    a.addu("t0", "a0", "zero")
    a.li16("t1", 0)
    a.addiu("at", "a0", 128)  # 스캔 상한 (조립본 최대 ~64B) — 널 없어도 폭주 방지

    a.label("scan")
    a.sltu("t3", "t0", "at")  # t0 < 상한?
    a.beq("t3", "zero", "done")  # 넘으면 종료
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
    a.li16("t3", 0x01)
    a.beq("t2", "t3", "adv1")
    a.nop()
    a.li16("t3", 0x02)
    a.beq("t2", "t3", "adv1")
    a.nop()
    a.li16("t1", 0)  # 그 외 1바이트 → prev 리셋
    a.label("adv1")
    a.addiu("t0", "t0", 1)
    a.beq("zero", "zero", "scan")
    a.nop()

    a.label("twobyte")
    a.lbu("t3", 1, "t0")
    a.nop()
    a.sll("t2", "t2", 8)
    a.or_("t2", "t2", "t3")  # t2 = cur code

    # 병기 후보? prev가 음절 범위일 때만 검사
    a.beq("t1", "zero", "setprev")
    a.nop()
    # prev in [SYL_LO, SYL_HI]?
    a.lui("t3", 0)
    a.ori("t3", "t3", SYL_LO)
    a.sltu("t4", "t1", "t3")
    a.bne("t4", "zero", "setprev")
    a.nop()
    a.ori("t3", "zero", SYL_HI)
    a.sltu("t4", "t3", "t1")
    a.bne("t4", "zero", "setprev")
    a.nop()

    # 쌍 테이블 순회: pairs = [(A,B)]×3, 루틴 뒤 데이터
    # (수조립 단순화를 위해 세 쌍을 펼쳐 비교)
    for k, (pa, pb) in enumerate(PAIRS):
        a.ori("t3", "zero", pa)
        a.bne("t2", "t3", f"pair{k}_no")
        a.nop()
        # ( B ) 확인 — 괄호는 반각 1바이트
        a.lbu("t3", 2, "t0")
        a.ori("t4", "zero", PAREN_L)
        a.bne("t3", "t4", f"pair{k}_no")
        a.nop()
        a.lbu("t3", 3, "t0")
        a.lbu("t4", 4, "t0")
        a.sll("t3", "t3", 8)
        a.or_("t3", "t3", "t4")
        a.ori("t4", "zero", pb)
        a.bne("t3", "t4", f"pair{k}_no")
        a.nop()
        a.lbu("t3", 5, "t0")
        a.ori("t4", "zero", PAREN_R)
        a.bne("t3", "t4", f"pair{k}_no")
        a.nop()
        # idx = (prev_hi-0x88)*188 + cell - 94
        a.srl("t3", "t1", 8)
        a.addiu("t3", "t3", -0x88)
        a.mul_188("t4", "t3", "t6")
        a.andi("t3", "t1", 0xFF)
        a.addiu("t3", "t3", -0x40)
        a.sltiu("t6", "t3", 0x40)  # lo-0x40 < 0x40  ↔ lo < 0x80 (0x7F 스킵 전)
        a.bne("t6", "zero", f"pair{k}_cell")
        a.nop()
        a.addiu("t3", "t3", -1)
        a.label(f"pair{k}_cell")
        a.addu("t4", "t4", "t3")
        a.addiu("t4", "t4", -BASE_LIN)
        # bit = table[idx>>3] >> (idx&7) & 1
        a.srl("t3", "t4", 3)
        a.addu("t3", "t5", "t3")
        a.lbu("t6", 0, "t3")
        a.andi("t7", "t4", 7)
        a.srlv("t6", "t6", "t7")
        a.andi("t6", "t6", 1)
        # chosen = has받침 ? A : B
        a.li16("t3", pa >> 8)
        a.li16("t4", pa & 0xFF)
        a.bne("t6", "zero", f"pair{k}_write")
        a.nop()
        a.li16("t3", pb >> 8)
        a.li16("t4", pb & 0xFF)
        a.label(f"pair{k}_write")
        a.sb("t3", 0, "t0")
        a.sb("t4", 1, "t0")
        # 4B 좌시프트: memmove(t0+2, t0+6, strlen+1)
        a.addiu("t3", "t0", 2)
        a.label(f"pair{k}_mv")
        a.lbu("t4", 4, "t3")
        a.nop()
        a.sb("t4", 0, "t3")
        a.bne("t4", "zero", f"pair{k}_mvnext")
        a.nop()
        a.beq("zero", "zero", "setprev")
        a.nop()
        a.label(f"pair{k}_mvnext")
        a.addiu("t3", "t3", 1)
        a.beq("zero", "zero", f"pair{k}_mv")
        a.nop()
        a.label(f"pair{k}_no")

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
# 2026-07-20 DuckStation 인게임 확정). 워크버퍼 = 0x801190B0 + idx*66,
# idx = lh gp+0x440 (게임 계산 복제). 원명령 lh v0,0x16(fp)를 stub 끝에서 실행.
HOOK_ADDR = 0x800B2054
HOOK_ORIG = 0x87C20016  # lh v0, 0x16(fp)
HOOK_RESUME = 0x800B2058
WORK_BASE = 0x801190B0
GP_IDX_OFF = 0x440  # lh gp+0x440 = 현재 렌더 라인 인덱스
FP = 30
GP = 28


def assemble_hook_stub(stub_base, josa_addr):
    """0x800B2054에서 j로 진입. 워크버퍼(0x801190B0 고정) 스캔 후 원명령 실행하고
    0x800B2058로 복귀.

    a0=워크버퍼로 josa_fix 호출. sp에 ra 저장/복원(게임 ra 보존). gp/fp/v0 등은
    josa_fix가 t0~t9만 clobber하므로 안전(진입 시점은 렌더 루프 시작 전).
    워크 주소는 고정 — DuckStation 실측상 병기 조립본은 항상 0x801190B0(idx=0 슬롯).
    idx*stride 동적 계산은 진입 시점 gp+0x440이 미세팅이라 폭주(크래시) → 제거."""
    a = Asm(stub_base)
    a.addiu("sp", "sp", -8)
    a.emit(_i(0x2B, REG["sp"], REG["ra"], 4))  # sw ra, 4(sp)
    a.lui("a0", WORK_BASE >> 16)
    a.ori("a0", "a0", WORK_BASE & 0xFFFF)  # a0 = 0x801190B0
    # josa_fix(a0)
    a.lui("t3", josa_addr >> 16)
    a.ori("t3", "t3", josa_addr & 0xFFFF)
    a.emit(_r(0, REG["t3"], 0, REG["ra"], 0, 9))  # jalr ra, t3
    a.nop()
    a.emit(_i(0x23, REG["sp"], REG["ra"], 4))  # lw ra, 4(sp)
    a.addiu("sp", "sp", 8)
    a.emit(HOOK_ORIG)  # 원명령: lh v0, 0x16(fp)
    # j HOOK_RESUME
    a.emit(0x08000000 | ((HOOK_RESUME >> 2) & 0x03FFFFFF))
    a.nop()
    return a.resolve()


def build_and_patch(ed: bytearray, place_ram: int):
    """비트테이블+josa_fix+훅stub을 place_ram에 싣고 0x800B2054를 j stub으로 패치.

    place_ram: ED.EXE 내 빈(0) 영역 RAM 주소. 레이아웃: [테이블][josa_fix][stub]."""
    table = build_bit_table()
    josa_addr = place_ram + len(table)
    josa = assemble_routine(josa_addr, place_ram)
    stub_addr = josa_addr + len(josa)
    stub = assemble_hook_stub(stub_addr, josa_addr)
    blob = table + josa + stub

    def fo(ram):
        return ram - 0x80010000 + 0x800

    p = fo(place_ram)
    assert all(b == 0 for b in ed[p : p + len(blob)]), "배치 영역이 0이 아님"
    ed[p : p + len(blob)] = blob
    # 0x800B2054 = j stub_addr
    jw = 0x08000000 | ((stub_addr >> 2) & 0x03FFFFFF)
    hp = fo(HOOK_ADDR)
    ed[hp : hp + 4] = struct.pack("<I", jw)
    return len(blob), josa_addr, stub_addr


# ED.EXE 배치 영역: 0런(0x80105959~, 4203B) 중 lui참조 3건(+3,+7,+3F) 뒤 4정렬 위치.
# 참조 대상(≤0x80105998)은 보존하고 그 뒤부터 코드/테이블을 싣는다.
PLACE_RAM = 0x801059A0


ED_LBA, ED_SIZE = 257, 1021952


def main():
    """build.py 체인용 — 최종 디스크의 ED.EXE에 조사 훅을 제자리 결합."""
    from common import WORK_DIR, extract, write_user_data

    target = os.path.join(WORK_DIR, "Eiyuu Densetsu (KR).bin")
    if not os.path.exists(target):
        raise SystemExit(f"대상 이미지 없음: {target} — build.py 먼저")
    ed = bytearray(extract(ED_LBA, ED_SIZE, path=target))
    fo = HOOK_ADDR - 0x80010000 + 0x800
    if int.from_bytes(ed[fo : fo + 4], "little") != HOOK_ORIG:
        raise SystemExit(f"훅 지점 0x{HOOK_ADDR:08X} 원명령 불일치 — 이미 패치됐거나 오프셋 오류")
    size, josa_addr, stub_addr = build_and_patch(ed, PLACE_RAM)
    with open(target, "r+b") as f:
        n = write_user_data(f, ED_LBA, ed)
    print(
        f"조사 훅: {size}B @ 0x{PLACE_RAM:08X} (josa 0x{josa_addr:08X}, stub 0x{stub_addr:08X}) "
        f"→ 0x{HOOK_ADDR:08X} 훅, 섹터 {n}개 수정"
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        pass  # 아래 셀프테스트로 진행
    else:
        main()
        sys.exit(0)
    table = build_bit_table()
    josa = assemble_routine(PLACE_RAM + len(table), PLACE_RAM)
    stub = assemble_hook_stub(PLACE_RAM + len(table) + len(josa), PLACE_RAM + len(table))
    total = len(table) + len(josa) + len(stub)
    print(
        f"테이블 {len(table)}B + josa {len(josa)}B + stub {len(stub)}B = {total}B @ 0x{PLACE_RAM:08X}"
    )
    try:
        from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs

        md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
        nj = sum(1 for _ in md.disasm(josa, 0))
        ns = sum(1 for _ in md.disasm(stub, 0))
        print(f"capstone: josa {nj}/{len(josa) // 4}, stub {ns}/{len(stub) // 4} instr")
    except ImportError:
        pass
