"""줄머리 공백 skip 훅 — 폭 제한 문자열 드로어(0x800AD3A8)의 자동 줄바꿈 공백 렌더 제거.

엔진의 자동 줄바꿈(29 반각칼럼)은 공백을 먹지 않아, 꺾이는 자리에 공백이 걸리면
다음 줄 첫 칸에 공백이 렌더된다("세리오스에게는 / ␣맞지 않았다" 실측). JP는 공백이
없어 안 드러나던 문제 — 한글 띄어쓰기 도입으로 표면화. 데이터 우회(공백→개행 치환,
battle[9·27·345])는 임시방편이고, 이 훅이 근본 해결. 규명 이력: docs/status.md
"전투 텍스트 렌더러 규명" 절.

훅 지점 = 0x800AD604 (그리기 직전 수렴점). 구 HANDOFF 권장안(git 이력)(루프 헤드 0x800AD468)은
wrap ①(그리기 전 폭 검사 0x800AD5FC) 경로가 같은 이터레이션 안에서 현재 문자를
새 줄 1열에 그리므로 못 잡는 빈틈이 있다 — 0x800AD604는 직접 그리기와 wrap ①
폴스루가 모두 지나는 단일 지점이라 wrap ①·②·명시적 \n 뒤 공백을 전부 커버한다.

    0x800AD604  addiu v0, zero, 0x91   ← j stub 로 교체
    0x800AD608  sw    v0, 0x10(sp)     ← 딜레이 슬롯으로 그대로 실행(스테일 v0 저장
                                          — [sp+0x10]은 그리기 직전마다 재설정되므로
                                          무해, resume 경로에서 0x91 재기록)

stub 로직: s0(열)==1 && s3(소스 인덱스)>0 && str[s3]==0x20 이면 s3++ 후 종료조건
(s3<strlen) 재검사 — 계속이면 루프 헤드(딜레이 슬롯 관례 v0=s3<<16 재현), 끝이면
루프 탈출(0x800AD6AC). 아니면 원명령 2개 재현 후 0x800AD60C 복귀.
s3>0 조건 = 문자열 선두의 의도적 들여쓰기 보존.

클로버: t0·t1·t2·v0 — 이 구간에서 매번 새로 로드되는 스크래치(정적 확인).
파급: jal 0x800AD3A8 호출자는 2곳(0x800B245C 전투, 0x800A9A74 기타 텍스트)뿐.
"""

import struct
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from patch_josa_hook import REG, Asm, _i, _r  # noqa: E402

# ── 드로어 좌표 (0x800AD3A8 함수 내부, 정적 디스어셈블 확정) ────────────────
HOOK_ADDR = 0x800AD604
HOOK_ORIG = 0x24020091  # addiu v0, zero, 0x91
DELAY_ORIG = 0xAFA20010  # sw v0, 0x10(sp) — 훅 후에도 딜레이 슬롯으로 실행됨
RESUME = 0x800AD60C  # 원명령 재현 후 복귀 지점
LOOP_HEAD = 0x800AD468  # 루프 헤드 (진입 관례: v0 = s3<<16)
LOOP_EXIT = 0x800AD6AC  # s3>=strlen 탈출 지점
STR_SP = 0x20  # [sp+0x20] = 문자열 베이스 (lw)
LEN_SP = 0x30  # [sp+0x30] = strlen (lhu)

# 배치: ED.EXE 0런(0x80105959~ 4203B) 뒤쪽 — 앞쪽 0x801059A0은 조사 훅(보류) 예약분.
PLACE_RAM = 0x80105D00

ED_LBA, ED_SIZE = 257, 1021952


def _sra(a, rd, rt, sh):
    a.emit(_r(0, 0, REG[rt], REG[rd], sh, 3))


def _slt(a, rd, rs, rt):
    a.emit(_r(0, REG[rs], REG[rt], REG[rd], 0, 0x2A))


def _lw(a, rt, off, base):
    a.emit(_i(0x23, REG[base], REG[rt], off))


def _lhu(a, rt, off, base):
    a.emit(_i(0x25, REG[base], REG[rt], off))


def _sw(a, rt, off, base):
    a.emit(_i(0x2B, REG[base], REG[rt], off))


def _j(a, target):
    a.emit(0x08000000 | ((target >> 2) & 0x03FFFFFF))


def assemble_stub(base):
    a = Asm(base)
    a.li16("t1", 1)
    a.bne("s0", "t1", "resume")  # 열 != 1 → 줄머리 아님
    a.nop()
    a.beq("s3", "zero", "resume")  # 문자열 선두 → 들여쓰기 보존
    a.nop()
    _lw(a, "t0", STR_SP, "sp")
    a.sll("v0", "s3", 16)
    _sra(a, "v0", "v0", 16)
    a.addu("t1", "t0", "v0")
    a.lbu("t1", 0, "t1")
    a.nop()  # load delay
    a.li16("t2", 0x20)
    a.bne("t1", "t2", "resume")  # 공백 아님
    a.nop()
    a.addiu("s3", "s3", 1)  # 줄머리 공백 skip
    _lhu(a, "t1", LEN_SP, "sp")
    a.sll("v0", "s3", 16)
    _sra(a, "v0", "v0", 16)
    _slt(a, "t2", "v0", "t1")  # s3 < strlen ?
    a.beq("t2", "zero", "exit_loop")
    a.nop()
    a.sll("v0", "s3", 16)  # 루프 헤드 진입 관례(딜레이 슬롯 값) 재현
    _j(a, LOOP_HEAD)
    a.nop()
    a.label("exit_loop")
    _j(a, LOOP_EXIT)
    a.nop()
    a.label("resume")
    a.li16("v0", 0x91)
    _sw(a, "v0", 0x10, "sp")  # 원명령 2개 재현(딜레이 슬롯이 스테일 v0를 저장했음)
    _j(a, RESUME)
    a.nop()
    return a.resolve()


def build_and_patch(ed: bytearray, place_ram: int):
    def fo(ram):
        return ram - 0x80010000 + 0x800

    stub = assemble_stub(place_ram)
    p = fo(place_ram)
    assert all(b == 0 for b in ed[p : p + len(stub)]), "배치 영역이 0이 아님"
    ed[p : p + len(stub)] = stub
    ed[fo(HOOK_ADDR) : fo(HOOK_ADDR) + 4] = struct.pack(
        "<I", 0x08000000 | ((place_ram >> 2) & 0x03FFFFFF)
    )
    return len(stub)


def main():
    """build.py 체인용 — 최종 디스크의 ED.EXE에 줄머리 공백 훅을 제자리 결합."""
    import os

    from common import BUILD_DIR, extract, write_user_data

    target = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")
    if not os.path.exists(target):
        raise SystemExit(f"대상 이미지 없음: {target} — build.py 먼저")
    ed = bytearray(extract(ED_LBA, ED_SIZE, path=target))

    def fo(ram):
        return ram - 0x80010000 + 0x800

    got = struct.unpack_from("<II", ed, fo(HOOK_ADDR))
    if got != (HOOK_ORIG, DELAY_ORIG):
        raise SystemExit(
            f"훅 지점 0x{HOOK_ADDR:08X} 원명령 불일치({got[0]:08X} {got[1]:08X}) — "
            "이미 패치됐거나 오프셋 오류"
        )
    size = build_and_patch(ed, PLACE_RAM)
    with open(target, "r+b") as f:
        n = write_user_data(f, ED_LBA, ed)
    print(
        f"줄머리 공백 훅: stub {size}B @ 0x{PLACE_RAM:08X} → 0x{HOOK_ADDR:08X} 훅, 섹터 {n}개 수정"
    )


# ── 셀프테스트: 미니 MIPS 인터프리터로 stub 의미 검증 ───────────────────────
def _simulate(stub, s0, s3, string):
    """stub을 base부터 실행, (탈출 타깃, 레지스터, 스택메모리) 반환."""
    words = [int.from_bytes(stub[i : i + 4], "little") for i in range(0, len(stub), 4)]
    R = [0] * 32
    R[REG["s0"]], R[REG["s3"]] = s0, s3
    SP, STRB = 0x801FFE00, 0x80014000
    R[REG["sp"]] = SP
    mem = {SP + STR_SP + k: (STRB >> (8 * k)) & 0xFF for k in range(4)}
    mem[SP + LEN_SP] = len(string) & 0xFF
    mem[SP + LEN_SP + 1] = len(string) >> 8
    for i, b in enumerate(string):
        mem[STRB + i] = b

    def r8(ad):
        return mem.get(ad, 0)

    def step(pc):
        """명령 1개 실행, 분기/점프면 타깃 반환(아니면 None)."""
        w = words[(pc - PLACE_RAM) // 4]
        op = w >> 26
        rs, rt = (w >> 21) & 31, (w >> 16) & 31
        imm = w & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm
        if op == 0:
            rd, sh, fn = (w >> 11) & 31, (w >> 6) & 31, w & 63
            if fn == 0:
                R[rd] = (R[rt] << sh) & 0xFFFFFFFF
            elif fn == 3:
                v = R[rt] >> sh
                if R[rt] & 0x80000000:
                    v |= (0xFFFFFFFF << (32 - sh)) & 0xFFFFFFFF
                R[rd] = v
            elif fn == 0x21:
                R[rd] = (R[rs] + R[rt]) & 0xFFFFFFFF
            elif fn == 0x2A:
                a_ = R[rs] - (1 << 32 if R[rs] & 0x80000000 else 0)
                b_ = R[rt] - (1 << 32 if R[rt] & 0x80000000 else 0)
                R[rd] = 1 if a_ < b_ else 0
            else:
                raise AssertionError(f"미지원 funct {fn:#x}")
        elif op == 0x0D:
            R[rt] = R[rs] | imm
        elif op == 0x09:
            R[rt] = (R[rs] + simm) & 0xFFFFFFFF
        elif op == 0x23:
            ad = (R[rs] + simm) & 0xFFFFFFFF
            R[rt] = sum(r8(ad + k) << (8 * k) for k in range(4))
        elif op == 0x24:
            R[rt] = r8((R[rs] + simm) & 0xFFFFFFFF)
        elif op == 0x25:
            ad = (R[rs] + simm) & 0xFFFFFFFF
            R[rt] = r8(ad) | r8(ad + 1) << 8
        elif op == 0x2B:
            ad = (R[rs] + simm) & 0xFFFFFFFF
            for k in range(4):
                mem[ad + k] = (R[rt] >> (8 * k)) & 0xFF
        elif op == 4:
            if R[rs] == R[rt]:
                return pc + 4 + (simm << 2)
        elif op == 5:
            if R[rs] != R[rt]:
                return pc + 4 + (simm << 2)
        elif op == 2:
            return (pc & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
        else:
            raise AssertionError(f"미지원 op {op:#x}")
        return None

    pc, n = PLACE_RAM, 0
    while True:
        n += 1
        assert n < 200, "stub 폭주"
        target = step(pc)
        if target is None:
            pc += 4
            continue
        step(pc + 4)  # 딜레이 슬롯
        if not (PLACE_RAM <= target < PLACE_RAM + len(stub)):
            return target, R, mem
        pc = target


def _selftest():
    stub = assemble_stub(PLACE_RAM)
    print(f"stub {len(stub)}B ({len(stub) // 4} instr) @ 0x{PLACE_RAM:08X}")
    SP = 0x801FFE00
    cases = [
        # (설명, s0, s3, 문자열, 기대 탈출, 기대 s3)
        ("열!=1 → 원경로", 5, 3, b"ab cd", RESUME, 3),
        ("선두 공백 보존", 1, 0, b" abc", RESUME, 0),
        ("줄머리 비공백 → 원경로", 1, 2, b"abxcd", RESUME, 2),
        ("줄머리 공백 skip → 루프 헤드", 1, 2, b"ab cd", LOOP_HEAD, 3),
        ("말미 공백 skip → 루프 탈출", 1, 4, b"abcd ", LOOP_EXIT, 5),
    ]
    for desc, s0, s3, string, want_exit, want_s3 in cases:
        tgt, R, mem = _simulate(stub, s0, s3, string)
        ok = tgt == want_exit and R[REG["s3"]] == want_s3
        if tgt == RESUME:  # 원명령 재현 확인: v0=0x91, [sp+0x10]=0x91
            ok = ok and R[REG["v0"]] == 0x91 and mem.get(SP + 0x10) == 0x91
        if tgt == LOOP_HEAD:  # 딜레이 슬롯 관례 재현 확인
            ok = ok and R[REG["v0"]] == (want_s3 << 16) & 0xFFFFFFFF
        print(f"  {'PASS' if ok else 'FAIL'}: {desc} (exit 0x{tgt:08X}, s3={R[REG['s3']]})")
        assert ok, desc
    try:
        from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs

        md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
        n = sum(1 for _ in md.disasm(stub, PLACE_RAM))
        print(f"capstone: {n}/{len(stub) // 4} instr 디코드")
        assert n == len(stub) // 4
    except ImportError:
        pass
    print("셀프테스트 전부 PASS")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        _selftest()
    else:
        main()
