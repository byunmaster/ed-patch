"""대사 「」 반각 전진 — 「 」 글리프는 칸 12px 중 왼쪽 8열에만 그림이 있다(마스터 도안 D판 10-26, 가로줄 4px). 엔진은 2바이트 글자를 늘 12px(+3 니블) 간다.
그래서 해석기의 2바이트 글자 분기 `$6759: JMP $67C4`(모드 0) 를 stub 로 돌려 — 글자 코드(`$F9:$F8`)가 「/」 이면 `$67C4` 를 부른 뒤 커서를 1 니블(4px) 되돌린다 → 진행 8px.
 커서 = `$84` 비트 3 이 서 있으면 `$71`, 아니면 `$73`(뱅크 0x6C 처리기 `$6000`/`$6014` 의 전진 대상). 되돌리기 전에 줄넘김(커서가 줄었다)이 났으면 건드리지 않는다.
 글자 앞 줄 끝 검사(`$67CC`, 글자 시작 x + 12px > 줄)는 그대로 12px 로 돈다 — 조판기 `engine_wraps` 도 12px 로 잰다.
 코드는 확정된 글리프 번호로 stub 표에 박는다(정적 풀에 「」 가 있어야 한다). 모드 2(전투·강조 좁은 글꼴)는 안 건드린다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font
import layout

BANK = 0x71
SEAM = 0x0759
SEAM_OLD = bytes.fromhex("4cc467")
STUB_OFF = 0x1FB0
STUB_ORG = 0x6000 + STUB_OFF
HANDLER = 0x67C4
N = len(font.KAGI)
LEN = 0x35 + 2 * N


def reserve(prog: layout.Prog) -> int:
    prog.reserve(BANK, STUB_OFF, LEN)
    return LEN


def stub(codes: list[bytes]) -> bytes:
    """codes = KAGI 글자 순서의 코드 2B."""
    assert len(codes) == N
    tt, ll = STUB_ORG + 0x35, STUB_ORG + 0x35 + N
    h = HANDLER.to_bytes(2, "little")
    b = bytes(
        [0xA2, N - 1]  # 00 LDX #N-1
        + [0xBD, tt & 0xFF, tt >> 8]  # 02 loop: LDA TT,X
        + [0xC5, 0xF8]  # 05 CMP $F8
        + [0xD0, 0x07]  # 07 BNE nx
        + [0xBD, ll & 0xFF, ll >> 8]  # 09 LDA LL,X
        + [0xC5, 0xF9]  # 0C CMP $F9
        + [0xF0, 0x06]  # 0E BEQ H
        + [0xCA]  # 10 nx: DEX
        + [0x10, 0xEF]  # 11 BPL loop
        + [0x4C, h[0], h[1]]  # 13 JMP $67C4
        + [0xBF, 0x84, 0x0E]  # 16 H: BBS3 $84,B3
        + [0xA5, 0x73, 0x48, 0x20, h[0], h[1], 0x68, 0xC5, 0x73, 0xB0, 0x02, 0xC6, 0x73, 0x60]  # 19~26
        + [0xA5, 0x71, 0x48, 0x20, h[0], h[1], 0x68, 0xC5, 0x71, 0xB0, 0x02, 0xC6, 0x71, 0x60]  # 27~34 B3
        + [c[1] for c in codes]  # 35 TT
        + [c[0] for c in codes]  # LL
    )
    assert len(b) == LEN, len(b)
    return b


def install(prog: layout.Prog, codes: list[bytes]) -> None:
    assert prog.o(BANK, SEAM, 3) == SEAM_OLD, "「」 반각 이음매 원본 바이트가 다르다"
    prog.put(BANK, STUB_OFF, stub(codes), "kagi stub")
    prog.put(BANK, SEAM, bytes([0x4C]) + STUB_ORG.to_bytes(2, "little"), "kagi seam $6759")


def codes_for(chars: list[str]) -> list[bytes]:
    for c in font.KAGI:
        assert c in chars, f"「」 가 정적 글리프 풀에 없다: {c}"
    return [font.code(chars.index(c)) for c in font.KAGI]
