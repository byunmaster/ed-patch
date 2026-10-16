"""글리프 후킹 — 게임이 BIOS 글꼴을 부르기 직전의 **한 곳**에서 우리 한글 글리프를 낸다.

이음매(2026-10-12 실측): 뱅크 0x6C `$60D2` 가 `JSR $60EA`(4칸 특수 글리프 표 조회) → 미스면 BIOS `EX_GETFNT`.
`$60EA` 는 `$F9:$F8` = 코드를 받아 맞으면 24B 를 `$309B` 에 채우고 **C=0**, 아니면 C=1 로 돌아온다.
우리는 이 `JSR $60EA` 의 피연산자만 바꿔 우리 루틴(`HOOK_OFF`)을 부른다 — 리드 `F0~F8` 이면 글리프 풀에서 꺼내
`$309B` 에 24B 를 쓰고 C=0, 아니면 `JMP $60EA`(원래 흐름).

글리프 풀 = 본 프로그램 뱅크(0x68~0x71) 안의 **0xFF 패딩**(모듈 사이 · 뱅크 끝) — 디스크에서 읽혀 올라오는 칸이라
따로 CD_READ 가 필요 없다. 글리프는 18B 묶음(`font.pack`)으로 칸에 이어 놓고, 풀 표(`CNT/BANK/ADLO/ADHI`)가 칸마다
(글리프 수 · 뱅크 · `$8000` 창 기준 주소)를 준다. 루틴은 칸의 뱅크를 **MPR4(`$8000`)에 잠깐** 걸어(SEI) 읽고 되돌린다.
호출 규약: 입력 `$F9`(리드) · `$F8`(트레일), 출력 `$309B`~24B · C=0(처리) / C=1(미스 → 원래 표).
스크래치 = `$EC~$EE`(BIOS 도 스크래치로 쓰는 자리).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asm
import font

PROG_REL = 130  # 본 프로그램(뱅크 0x68~) 디스크 시작 — 뱅크 b 는 rel 130 + (b-0x68)*4
BANK0 = 0x68
BANK = 8192
SEAM_BANK, SEAM_OFF = 0x6C, 0x00D3  # `$60D2: JSR $60EA` 의 피연산자(2B)
SEAM_OLD = bytes([0xEA, 0x60])
ORIG_CHECK = 0x60EA
GLYPH_BUF = 0x309B
WINDOW_MPR = 4  # 글리프 뱅크를 잠깐 거는 창 — `$8000`(씬 패키지가 쓰는 자리라 끝나면 되돌린다)
WINDOW = 0x8000
HOOK_BANK, HOOK_OFF = 0x6C, 0x1966  # 후킹 루틴 자리(0xFF 패딩) — 마운트 `$6000`(MPR3)

# 본 프로그램 안의 0xFF 패딩(디스크 원본 · 런타임 첫 마을 상태 둘 다 0xFF 로 안 변함 — 2026-10-12 실측).
# (뱅크, 뱅크 안 오프셋, 길이). 후킹 루틴 칸(0x6C)은 앞쪽을 루틴이 쓰고 남는 꼬리를 풀에 준다.
PADDING = [
    (0x6B, 0x10C4, 3900),
    (0x71, 0x13FB, 3077),
    (0x6A, 0x15B0, 2640),
    (0x6C, 0x1966, 1690),
    (0x69, 0x1DB4, 588),
    (0x6D, 0x1DC5, 571),
    (0x70, 0x1E1A, 486),
    (0x6F, 0x1F3A, 198),
    (0x6E, 0x1F3C, 196),
]
MAX_RUNS = 8


def linear(bank: int, off: int) -> int:
    """뱅크:오프셋 → 데이터 트랙 유저 데이터 선형 바이트(rel*2048 + 오프셋)."""
    return PROG_REL * 2048 + (bank - BANK0) * BANK + off


def _routine(nruns: int) -> asm.Asm:
    a = asm.Asm(0x6000 + HOOK_OFF)  # 뱅크 0x6C 가 MPR3($6000)에 걸려 있을 때의 주소
    a.op("LDA", "zp", 0xF9)
    a.op("CMP", "imm", font.LEAD0)
    a.op("BCC", "rel", "orig")
    a.op("CMP", "imm", font.LEAD0 + font.MAX_LEADS)
    a.op("BCS", "rel", "orig")
    a.op("BRA", "rel", "main")
    a.label("orig")  # 우리 코드가 아니다 → 원래 표 조회(그쪽 RTS 가 우리 호출자에게 돌아간다)
    a.op("JMP", "abs", ORIG_CHECK)
    a.label("main")
    a.op("PHX")  # 원래 루틴은 X 를 안 건드린다 — 호출자를 위해 지킨다
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
    a.label("found")  # X = 칸, $EC = 칸 안 번호(0~254) → 오프셋 = 번호 × 18
    a.op("STZ", "zp", 0xED)
    a.op("LDA", "zp", 0xEC)
    a.op("STA", "zp", 0xEE)  # $ED:$EE = r
    a.op("ASL", "zp", 0xEE)
    a.op("ROL", "zp", 0xED)  # r*2
    a.op("LDA", "zp", 0xEE)
    a.op("PHA")
    a.op("LDA", "zp", 0xED)
    a.op("PHA")
    for _ in range(3):
        a.op("ASL", "zp", 0xEE)
        a.op("ROL", "zp", 0xED)  # r*16
    a.op("PLA")
    a.op("STA", "zp", 0xEC)  # r*2 의 상위
    a.op("PLA")
    a.op("CLC")
    a.op("ADC", "zp", 0xEE)
    a.op("STA", "zp", 0xEE)
    a.op("LDA", "zp", 0xED)
    a.op("ADC", "zp", 0xEC)
    a.op("STA", "zp", 0xED)  # $ED:$EE = r*18
    a.op("CLC")
    a.op("LDA", "zp", 0xEE)
    a.op("ADC", "absx", "ADLO")
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0xED)
    a.op("ADC", "absx", "ADHI")
    a.op("STA", "zp", 0xED)  # ($EC) = 글리프 18B 의 창 주소
    a.op("PHP")
    a.op("SEI")
    a.op("TMA", "tma", WINDOW_MPR)
    a.op("PHA")
    a.op("LDA", "absx", "BANKS")
    a.op("TAM", "tam", WINDOW_MPR)
    a.op("LDY", "imm", 0)
    a.op("LDX", "imm", 0)
    a.label("grp")  # 3B(두 행) → 4B
    a.op("LDA", "izpy", 0xEC)
    a.op("STA", "absx", GLYPH_BUF)
    a.op("INX")
    a.op("INY")
    a.op("LDA", "izpy", 0xEC)
    a.op("AND", "imm", 0xF0)
    a.op("STA", "absx", GLYPH_BUF)
    a.op("INX")
    a.op("LDA", "izpy", 0xEC)
    for _ in range(4):
        a.op("ASL")
    a.op("STA", "zp", 0xEE)
    a.op("INY")
    a.op("LDA", "izpy", 0xEC)
    for _ in range(4):
        a.op("LSR")
    a.op("ORA", "zp", 0xEE)
    a.op("STA", "absx", GLYPH_BUF)
    a.op("INX")
    a.op("LDA", "izpy", 0xEC)
    for _ in range(4):
        a.op("ASL")
    a.op("STA", "absx", GLYPH_BUF)
    a.op("INX")
    a.op("INY")
    a.op("CPX", "imm", font.GLYPH_BYTES)
    a.op("BCC", "rel", "grp")
    a.op("PLA")
    a.op("TAM", "tam", WINDOW_MPR)
    a.op("PLP")
    a.op("PLX")
    a.op("CLC")
    a.op("RTS")
    # 풀 표 — 칸마다 (글리프 수 · 뱅크 · 창 주소 lo/hi)
    a.label("CNT")
    a.data(bytes(nruns))
    a.label("BANKS")
    a.data(bytes(nruns))
    a.label("ADLO")
    a.data(bytes(nruns))
    a.label("ADHI")
    a.data(bytes(nruns))
    return a


def plan(nglyphs: int) -> list[tuple[int, int, int]]:
    """글리프 `nglyphs` 개를 놓을 칸 — [(뱅크, 오프셋, 글리프 수)]. 큰 패딩부터 채운다(칸 수를 줄인다).

    칸 하나가 255 개를 넘기지 않게 쪼갠다(루틴이 개수를 1바이트로 센다).
    """
    routine = _routine(MAX_RUNS).bytes()
    hook_end = HOOK_OFF + len(routine)
    pads = []
    for bank, off, ln in PADDING:
        if (bank, off) == (HOOK_BANK, HOOK_OFF):
            skip = (len(routine) + 1) & ~1  # 루틴 + 표 뒤부터
            off, ln = off + skip, ln - skip
        pads.append((bank, off, ln))
    runs = []
    left = nglyphs
    for bank, off, ln in sorted(pads, key=lambda p: -p[2]):
        while left > 0 and ln >= font.PACKED_BYTES and len(runs) < MAX_RUNS:
            n = min(left, ln // font.PACKED_BYTES, 255)
            runs.append((bank, off, n))
            off += n * font.PACKED_BYTES
            ln -= n * font.PACKED_BYTES
            left -= n
    assert hook_end < 0x2000
    if left > 0:
        raise ValueError(
            f"글리프 {nglyphs} 개가 풀(패딩 {sum(p[2] for p in PADDING)}B)에 안 들어간다 (+{left})"
        )
    return runs


def build(glyph24: list[bytes]) -> list[tuple[int, bytes, bytes | None, str]]:
    """(선형 바이트, 새 바이트, 기대 원본|None, 라벨) 목록 — 디스크에 쓸 후킹 패치 전부."""
    runs = plan(len(glyph24))
    a = _routine(MAX_RUNS)
    # 표 채우기 — 모자란 칸은 0 개
    cnt = bytearray(MAX_RUNS)
    banks = bytearray(MAX_RUNS)
    adlo = bytearray(MAX_RUNS)
    adhi = bytearray(MAX_RUNS)
    for k, (bank, off, n) in enumerate(runs):
        cnt[k], banks[k] = n, bank
        win = WINDOW + off
        adlo[k], adhi[k] = win & 0xFF, win >> 8
    code = bytearray(a.bytes())
    cnt_pos = a.labels["CNT"] - a.org
    code[cnt_pos : cnt_pos + MAX_RUNS] = cnt
    code[cnt_pos + MAX_RUNS : cnt_pos + 2 * MAX_RUNS] = banks
    code[cnt_pos + 2 * MAX_RUNS : cnt_pos + 3 * MAX_RUNS] = adlo
    code[cnt_pos + 3 * MAX_RUNS : cnt_pos + 4 * MAX_RUNS] = adhi
    out = [
        (linear(SEAM_BANK, SEAM_OFF), (a.org).to_bytes(2, "little"), SEAM_OLD, "hook seam $60D2"),
        (linear(HOOK_BANK, HOOK_OFF), bytes(code), b"\xff" * len(code), "hook routine"),
    ]
    i = 0
    for bank, off, n in runs:
        blob = b"".join(font.pack(g) for g in glyph24[i : i + n])
        out.append(
            (linear(bank, off), blob, b"\xff" * len(blob), f"glyph run {bank:02X}+{off:04X}")
        )
        i += n
    return out
