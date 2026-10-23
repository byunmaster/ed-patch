"""대사창 ASCII 반각 전진 — 한 바이트 ASCII(`$20`~`$5F`)는 mode 0 창에서 전각 SJIS 로 바뀌어(`$69C0`) **12px** 씩 간다(쉼표·마침표·숫자 사이가 벌어진다 — 규칙 1-1 위반).
mode 2(`$2C0B & 3` = 2 — `06` 강조·전투 창이 쓰는 좁은 글꼴) 처리기 `$67E6` 은 같은 한 바이트를 BIOS 반각 글꼴로 **8px** 에 그린다(실측 10-19: `금AAA지` 간격 12 → 8).
해법: 한 바이트 문자 처리의 처리기 분기 `$676F: TAX; JMP ($67B9,X)` 앞에 — mode 0 이고 글자가 `$20`~`$5F` 이면 mode 2 처리기로 보낸다(`LDX #4`).
 `$676F: aa 7c b9 67` → `4c <stub> ea` , stub = `aa d0 08 a5 f9 c9 60 b0 02 a2 04 7c b9 67`(14B, 뱅크 0x71 끝 0xFF 런의 꼬리).
 ($60 공백 · `$61`~ 탁음 가나 · `$A0`~ 가나는 그대로 — 공백 4px 은 별도 경로.)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout

BANK = 0x71
SEAM = 0x076F
SEAM_OLD = bytes.fromhex("aa7cb967")
STUB_OFF = 0x1FF0
STUB_ORG = 0x6000 + STUB_OFF
STUB = bytes.fromhex("aa d0 08 a5 f9 c9 60 b0 02 a2 04 7c b9 67")


def reserve(prog: layout.Prog) -> int:
    prog.reserve(BANK, STUB_OFF, len(STUB))
    return len(STUB)


def install(prog: layout.Prog) -> None:
    assert prog.o(BANK, SEAM, 4) == SEAM_OLD, "반각 전진 이음매 원본 바이트가 다르다"
    prog.put(BANK, STUB_OFF, STUB, "narrow stub")
    prog.put(BANK, SEAM, bytes([0x4C]) + STUB_ORG.to_bytes(2, "little") + b"\xea", "narrow seam $676F")
