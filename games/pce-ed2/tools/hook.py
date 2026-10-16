"""글리프 후킹 — 게임이 BIOS 글꼴을 부르기 직전의 **한 곳**에서 우리 한글 글리프를 낸다.

이음매(2026-10-12 실측): 뱅크 0x6C `$60D2` 가 `JSR $60EA`(4칸 특수 글리프 표 조회) → 미스면 BIOS `EX_GETFNT`.
`$60EA` 는 `$F9:$F8` = 코드를 받아 맞으면 24B 를 `$309B` 에 채우고 **C=0**, 아니면 C=1 로 돌아온다.
우리는 이 `JSR $60EA` 의 피연산자만 바꿔 우리 루틴(`HOOK_OFF`)을 부른다 — 리드 `F0~F8` 이면 글리프 풀에서 꺼내
`$309B` 에 24B 를 쓰고 C=0, 아니면 `JMP $60EA`(원래 흐름).

글리프 풀 = 본 프로그램 뱅크(0x68~0x71) 안의 **0xFF 패딩**(모듈 사이 · 뱅크 끝) — 디스크에서 읽혀 올라오는 칸이라
따로 CD_READ 가 필요 없다. 글리프는 16B 묶음(`font.pack`, 11×11)으로 칸에 이어 놓고, 풀 표(`CNT/BANK/ADLO/ADHI`)가 칸마다
(글리프 수 · 뱅크 · `$8000` 창 기준 주소)를 준다. 루틴은 칸의 뱅크를 **MPR4(`$8000`)에 잠깐** 걸어(SEI) 읽고 되돌린다.
호출 규약: 입력 `$F9`(리드) · `$F8`(트레일), 출력 `$309B`~24B · C=0(처리) / C=1(미스 → 원래 표).
스크래치 = `$EC~$EE`(BIOS 도 스크래치로 쓰는 자리).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asm
import font
import layout

SEAM_BANK, SEAM_OFF = 0x6C, 0x00D3  # `$60D2: JSR $60EA` 의 피연산자(2B)
SEAM_OLD = bytes([0xEA, 0x60])
ASCII_SEAM_BANK, ASCII_SEAM_OFF = 0x6C, 0x0451  # `$6450: JSR $6513`(ASCII 한 글자 그리기)의 피연산자 — 유일한 호출부
ASCII_SEAM_OLD = bytes([0x13, 0x65])
ASCII_DRAW = 0x6513
ORIG_CHECK = 0x60EA
GLYPH_BUF = 0x309B
WINDOW_MPR = 4  # 글리프 뱅크를 잠깐 거는 창 — `$8000`(씬 패키지가 쓰는 자리라 끝나면 되돌린다)
WINDOW = 0x8000
HOOK_BANK, HOOK_OFF = 0x6C, 0x1966  # 후킹 루틴 자리(0xFF 패딩) — 마운트 `$6000`(MPR3)

MAX_RUNS = 24
PKG_BASE = 0x41  # 씬 패키지가 올라온 첫 뱅크(ZP) — 실측 0x73
HDR_ENTRY = 12  # 패키지 머리표 항목 4(3바이트 × 4) = 메시지 표 포인터 [상대 뱅크][lo][hi]


def _routine(nruns: int) -> asm.Asm:
    a = asm.Asm(0x6000 + HOOK_OFF)  # 뱅크 0x6C 가 MPR3($6000)에 걸려 있을 때의 주소
    a.op("LDA", "zp", 0xF9)
    a.op("CMP", "imm", font.LEAD0)
    a.op("BCC", "rel", "orig")
    a.op("CMP", "imm", font.LEAD0 + font.MAX_LEADS + 1)  # F9(동적 조사)까지
    a.op("BCS", "rel", "orig")
    a.op("BRA", "rel", "main")
    a.label("orig")  # 우리 코드가 아니다 → 원래 표 조회(그쪽 RTS 가 우리 호출자에게 돌아간다)
    a.op("JMP", "abs", ORIG_CHECK)
    a.label("main")
    a.op("PHX")  # 원래 루틴은 X 를 안 건드린다 — 호출자를 위해 지킨다
    a.op("CMP", "imm", font.JOSA_LEAD)
    a.op("BNE", "rel", "glyph")
    a.op("JMP", "abs", "josa")
    a.label("glyph")
    a.op("SEC")
    a.op("SBC", "imm", font.LEAD0)
    a.op("TAX")  # X = 리드 번호
    a.op("LDA", "zp", 0xF8)
    a.op("SEC")
    a.op("SBC", "imm", font.TRAIL0)
    a.op("STA", "zp", 0xEC)
    a.op("STZ", "zp", 0xED)  # $ED:$EC = 트레일 번호
    a.op("CPX", "imm", 0)
    a.op("BEQ", "rel", "got")
    a.label("addl")  # += 220 * 리드 번호
    a.op("CLC")
    a.op("LDA", "zp", 0xEC)
    a.op("ADC", "imm", font.PER_LEAD)
    a.op("STA", "zp", 0xEC)
    a.op("BCC", "rel", "nc")
    a.op("INC", "zp", 0xED)
    a.label("nc")
    a.op("DEX")
    a.op("BNE", "rel", "addl")
    a.label("got")  # $ED:$EC = 글리프 번호
    a.op("LDA", "zp", 0xED)  # 정적 글리프 수(S) 이상이면 패키지 지역 표
    a.op("CMP", "abs", "SHI")
    a.op("BCC", "rel", "static")
    a.op("BNE", "rel", "tolocal")
    a.op("LDA", "zp", 0xEC)
    a.op("CMP", "abs", "SLO")
    a.op("BCC", "rel", "static")
    a.label("tolocal")
    a.op("JMP", "abs", "local")
    a.label("static")
    a.op("LDX", "imm", 0)
    a.label("find")  # 칸을 하나씩 건너뛰며 번호가 속한 칸을 찾는다
    a.op("LDA", "zp", 0xED)
    a.op("BNE", "rel", "sub")
    a.op("LDA", "zp", 0xEC)
    a.op("CMP", "absx", "CNT")
    a.op("BCC", "rel", "found")
    a.label("sub")
    a.op("SEC")
    a.op("LDA", "zp", 0xEC)
    a.op("SBC", "absx", "CNT")
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0xED)
    a.op("SBC", "imm", 0)
    a.op("STA", "zp", 0xED)
    a.op("INX")
    a.op("CPX", "imm", nruns)
    a.op("BCC", "rel", "find")
    a.op("PLX")
    a.op("JMP", "abs", "orig")  # 풀 밖 — 원래 흐름(BIOS)으로
    a.label("found")  # X = 칸, $EC = 칸 안 번호(0~254) → 오프셋 = 번호 × 16
    a.op("STZ", "zp", 0xED)
    for _ in range(4):
        a.op("ASL", "zp", 0xEC)
        a.op("ROL", "zp", 0xED)  # r*16
    a.op("CLC")
    a.op("LDA", "zp", 0xEC)
    a.op("ADC", "absx", "ADLO")
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0xED)
    a.op("ADC", "absx", "ADHI")
    a.op("STA", "zp", 0xED)  # ($EC) = 글리프 16B 의 창 주소
    a.op("PHP")
    a.op("SEI")
    a.op("TMA", "tma", WINDOW_MPR)
    a.op("PHA")
    a.op("LDA", "absx", "BANKS")
    a.op("TAM", "tam", WINDOW_MPR)
    a.op("LDY", "imm", 15)
    a.label("cp")  # 🔴 `SEI` 안에서는 16B 를 RAM(`GBUF`)에 복사만 한다 — 압축 풀기까지 하면 글자마다 인터럽트가 4줄 막혀 래스터 분할이 흔들린다(10-13)
    a.op("LDA", "izpy", 0xEC)
    a.op("STA", "absy", "GBUF")
    a.op("DEY")
    a.op("BPL", "rel", "cp")
    a.op("PLA")
    a.op("TAM", "tam", WINDOW_MPR)
    a.op("PLP")  # 인터럽트 복원 — 이 아래는 RAM 사본으로 푼다
    a.op("LDY", "imm", 0)
    a.op("LDX", "imm", 0)
    a.label("hi")  # 앞 11B = 행 0~10 의 위 8비트 → 출력 짝수 바이트
    a.op("LDA", "absy", "GBUF")
    a.op("STA", "absx", GLYPH_BUF)
    a.op("INX")
    a.op("INX")
    a.op("INY")
    a.op("CPY", "imm", 11)
    a.op("BCC", "rel", "hi")
    a.op("LDY", "imm", 15)
    a.label("pu")  # 뒤 5B(아래 3비트 열)를 스택에 S4..S0 순으로 — 40비트 레지스터가 된다
    a.op("LDA", "absy", "GBUF")
    a.op("PHA")
    a.op("DEY")
    a.op("CPY", "imm", 11)
    a.op("BCS", "rel", "pu")
    a.op("TSX")  # S0 = $2101,X … S4 = $2105,X
    a.op("LDA", "absx", 0x2105)
    a.op("AND", "imm", font.FLAG_BATCHIM)
    a.op("STA", "abs", "LASTB")  # 방금 그린 글자의 받침 플래그 — 다음 조사 토큰이 쓴다
    a.op("LDY", "imm", 1)
    a.label("row")  # 행마다 위 3비트 → 출력 홀수 바이트(비트 7~5), 레지스터를 3비트 왼쪽으로
    a.op("LDA", "absx", 0x2101)
    a.op("AND", "imm", 0xE0)
    a.op("STA", "absy", GLYPH_BUF)
    for _ in range(3):
        a.op("ASL", "absx", 0x2105)
        a.op("ROL", "absx", 0x2104)
        a.op("ROL", "absx", 0x2103)
        a.op("ROL", "absx", 0x2102)
        a.op("ROL", "absx", 0x2101)
    a.op("INY")
    a.op("INY")
    a.op("CPY", "imm", 23)
    a.op("BCC", "rel", "row")
    a.op("CLA")
    a.op("STA", "abs", GLYPH_BUF + 22)  # 행 11 은 비어 있다
    a.op("STA", "abs", GLYPH_BUF + 23)
    for _ in range(5):
        a.op("PLA")  # 스택의 40비트 레지스터 버리기
    a.op("PLX")
    a.op("CLC")
    a.op("RTS")
    a.label("josa")  # 리드 F9: 트레일 = 종류 k → 직전 글자의 받침으로 두 꼴 중 하나의 글리프 번호를 골라 보통 흐름으로
    a.op("LDA", "zp", 0xF8)
    a.op("SEC")
    a.op("SBC", "imm", font.TRAIL0)
    a.op("CMP", "imm", len(font.JOSA))
    a.op("BCC", "rel", "jok")
    a.op("PLX")
    a.op("JMP", "abs", "orig")
    a.label("jok")
    a.op("ASL")
    a.op("TAX")  # X = 종류*2 (받침 있음)
    a.op("LDA", "abs", "LASTB")
    a.op("BNE", "rel", "jhas")
    a.op("INX")  # 받침 없음 꼴
    a.label("jhas")
    a.op("LDA", "absx", "JLO")
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "absx", "JHI")
    a.op("STA", "zp", 0xED)
    a.op("JMP", "abs", "got")
    a.label("local")  # r = 번호 - S (0~254) → 패키지 머리표에서 지역 표 위치를 읽어 마지막 칸(LOC)에 채운다
    a.op("SEC")
    a.op("LDA", "zp", 0xEC)
    a.op("SBC", "abs", "SLO")
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0xED)
    a.op("SBC", "abs", "SHI")
    a.op("BNE", "rel", "lmiss0")
    a.op("LDA", "zp", 0xEC)
    a.op("PHA")  # r
    a.op("PHP")
    a.op("SEI")
    a.op("TMA", "tma", WINDOW_MPR)
    a.op("PHA")  # 창 원래 뱅크
    a.op("LDA", "zp", PKG_BASE)
    a.op("TAM", "tam", WINDOW_MPR)  # 패키지 첫 뱅크 → $8000
    a.op("LDA", "abs", WINDOW + HDR_ENTRY + 1)
    a.op("STA", "zp", 0xEC)  # 메시지 표 주소 lo
    a.op("LDA", "abs", WINDOW + HDR_ENTRY + 2)
    a.op("PHA")
    a.op("AND", "imm", 0x1F)
    a.op("ORA", "imm", 0x80)
    a.op("STA", "zp", 0xED)  # 창 hi
    a.op("PLA")
    for _ in range(5):
        a.op("LSR")
    a.op("CLC")
    a.op("ADC", "abs", WINDOW + HDR_ENTRY)  # + 상대 뱅크
    a.op("CLC")
    a.op("ADC", "zp", PKG_BASE)
    a.op("TAM", "tam", WINDOW_MPR)  # 메시지 표가 든 뱅크
    a.op("LDY", "imm", 0)
    a.op("LDA", "izpy", 0xEC)
    a.op("STA", "abs", "ADLO_LOC")  # 표 항목 0 = 지역 글리프 표 포인터(lo)
    a.op("LDY", "imm", 1)
    a.op("LDA", "izpy", 0xEC)
    a.op("PHA")
    a.op("ORA", "abs", "ADLO_LOC")
    a.op("BNE", "rel", "lok")
    a.op("PLA")  # 표 없음
    a.op("PLA")
    a.op("TAM", "tam", WINDOW_MPR)
    a.op("PLP")
    a.op("PLA")
    a.label("lmiss0")
    a.op("PLX")
    a.op("JMP", "abs", "orig")
    a.label("lok")
    a.op("PLA")
    a.op("PHA")
    a.op("AND", "imm", 0x1F)
    a.op("ORA", "imm", 0x80)
    a.op("STA", "abs", "ADHI_LOC")
    a.op("PLA")
    for _ in range(5):
        a.op("LSR")
    a.op("CLC")
    a.op("ADC", "zp", PKG_BASE)
    a.op("STA", "abs", "BANKS_LOC")
    a.op("PLA")
    a.op("TAM", "tam", WINDOW_MPR)
    a.op("PLP")
    a.op("PLA")
    a.op("STA", "zp", 0xEC)
    a.op("LDX", "imm", nruns)
    a.op("JMP", "abs", "found")
    # 풀 표 — 칸마다 (글리프 수 · 뱅크 · 창 주소 lo/hi)
    for name in ("CNT", "BANKS", "ADLO", "ADHI"):  # 칸 nruns 개 + 지역 표 칸(LOC = nruns) — 지역 칸은 호출 때마다 패키지 머리표에서 채운다(RAM 이라 쓸 수 있다)
        a.label(name)
        a.data(bytes(nruns + 1))
    a.labels["BANKS_LOC"] = a.labels["BANKS"] + nruns
    a.labels["ADLO_LOC"] = a.labels["ADLO"] + nruns
    a.labels["ADHI_LOC"] = a.labels["ADHI"] + nruns
    a.label("ascii")  # ASCII 한 글자(`$F9`)를 그리기 직전 — 받침 플래그를 맞춘다: 영문·부호 = 없음, 숫자 = 읽는 소리(영·일·삼·육·칠·팔은 있음). 레지스터는 지킨다
    a.op("PHA")
    a.op("PHX")
    a.op("LDA", "zp", 0xF9)
    a.op("SEC")
    a.op("SBC", "imm", 0x30)
    a.op("CMP", "imm", 10)
    a.op("BCS", "rel", "anone")
    a.op("TAX")
    a.op("LDA", "absx", "DIGB")
    a.op("BRA", "rel", "aset")
    a.label("anone")
    a.op("CLA")
    a.label("aset")
    a.op("STA", "abs", "LASTB")
    a.op("PLX")
    a.op("PLA")
    a.op("JMP", "abs", ASCII_DRAW)
    a.label("GBUF")  # 글리프 16B 사본(RAM)
    a.data(bytes(16))
    a.label("DIGB")  # 숫자 0~9 의 받침 플래그
    a.data(bytes(font.FLAG_BATCHIM if d in (0, 1, 3, 6, 7, 8) else 0 for d in range(10)))
    a.label("LASTB")  # 직전 글리프의 받침 플래그(RAM 이라 쓸 수 있다)
    a.data(b"\0")
    a.label("JLO")  # 조사 글리프 번호표 — 종류마다 (받침 있음, 없음) 16비트, 설치 때 채운다
    a.data(bytes(2 * len(font.JOSA)))
    a.label("JHI")
    a.data(bytes(2 * len(font.JOSA)))
    a.label("SLO")  # 정적 글리프 수 S(16비트) — 설치 때 채운다
    a.data(b"\0")
    a.label("SHI")
    a.data(b"\0")
    return a


def reserve(prog: layout.Prog) -> int:
    """후킹 루틴 자리를 자유 공간에서 뺀다. 반환 = 루틴 길이."""
    n = len(_routine(MAX_RUNS).bytes())
    prog.reserve(HOOK_BANK, HOOK_OFF, n)
    return n


def pool_capacity(prog: layout.Prog) -> int:
    """글리프 풀에 **실제로** 앉힐 수 있는 글리프 수 — `install` 과 같은 순서로 칸(최대 MAX_RUNS)을 채워 센다(칸마다 버려지는 16B 미만 꼬리만 손해)."""
    runs = 0
    total = 0
    for _bank, _off, ln in sorted(prog.runs_left(), key=lambda p: (-p[2], p[0], p[1])):
        while ln >= font.PACKED_BYTES and runs < MAX_RUNS:
            n = min(ln // font.PACKED_BYTES, 255)
            total += n
            runs += 1
            ln -= n * font.PACKED_BYTES
    return total


def install(prog: layout.Prog, glyph24: list[bytes], flags: list[int] | None = None, josa_idx: list[int] | None = None) -> None:
    """후킹 이음매 · 루틴 · 글리프 풀(남은 자유 공간 — 큰 칸부터 255개씩)을 장부에 적는다. `reserve` 뒤, 다른 자리 배정이 끝난 뒤에 부른다."""
    runs = []
    left = len(glyph24)
    for bank, off, ln in sorted(prog.runs_left(), key=lambda p: (-p[2], p[0], p[1])):
        while left > 0 and ln >= font.PACKED_BYTES and len(runs) < MAX_RUNS:
            n = min(left, ln // font.PACKED_BYTES, 255)
            runs.append((bank, off, n))
            off += n * font.PACKED_BYTES
            ln -= n * font.PACKED_BYTES
            left -= n
    if left > 0:
        raise ValueError(
            f"글리프 {len(glyph24)} 개가 풀에 안 들어간다 (+{left}) — 자유 공간 {sum(p[2] for p in prog.runs_left())}B"
        )
    a = _routine(MAX_RUNS)
    cnt, banks, adlo, adhi = (bytearray(MAX_RUNS) for _ in range(4))
    for k, (bank, off, n) in enumerate(runs):
        cnt[k], banks[k] = n, bank
        win = WINDOW + off
        adlo[k], adhi[k] = win & 0xFF, win >> 8
    code = bytearray(a.bytes())
    for k, idx in enumerate(josa_idx or []):  # 조사 글리프 번호(종류*2 + 꼴)
        code[a.labels["JLO"] - a.org + k] = idx & 0xFF
        code[a.labels["JHI"] - a.org + k] = idx >> 8
    code[a.labels["SLO"] - a.org] = len(glyph24) & 0xFF
    code[a.labels["SHI"] - a.org] = len(glyph24) >> 8
    p = a.labels["CNT"] - a.org
    for i, arr in enumerate((cnt, banks, adlo, adhi)):
        code[p + i * (MAX_RUNS + 1) : p + i * (MAX_RUNS + 1) + MAX_RUNS] = arr
    assert prog.o(SEAM_BANK, SEAM_OFF, 2) == SEAM_OLD, "이음매 원본 바이트가 다르다"
    assert prog.o(ASCII_SEAM_BANK, ASCII_SEAM_OFF, 2) == ASCII_SEAM_OLD, "ASCII 이음매 원본 바이트가 다르다"
    prog.put(ASCII_SEAM_BANK, ASCII_SEAM_OFF, (a.labels["ascii"]).to_bytes(2, "little"), "hook seam ascii $6450")
    prog.put(SEAM_BANK, SEAM_OFF, a.org.to_bytes(2, "little"), "hook seam $60D2")
    prog.put(HOOK_BANK, HOOK_OFF, bytes(code), "hook routine")
    i = 0
    for bank, off, n in runs:
        blob = b"".join(font.pack(g, flags[i + j] if flags else 0) for j, g in enumerate(glyph24[i : i + n]))
        prog.put(bank, off, blob, f"glyph run {bank:02X}+{off:04X}")
        prog.reserve(bank, off, len(blob))
        i += n
