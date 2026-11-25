"""블록 141 파티 합류 레코드 — 소니아 이름(`83 5C 83 6A 83 41` + `06`). scene.py 가 못 보는 문안 스트림 밖 자료다.

    python3 tools/party_template.py --check

합류 이벤트가 이 레코드 0x40B 를 세 번째 파티 칸(`$FF1E3C`)으로 복사하고, HUD 이름칸은 그 이름을 리소스 4(12×12)로 그린다.
리소스 4 는 가타카나 자리를 한글 음절로 다시 쓴 글꼴이라 **가타카나 코드가 남으면 엉뚱한 음절(「거거거」)로 나온다**(2026-11-05 실측).
`party_rec`(롬 0x333E2, 넷)에는 소니아가 없어 이 레코드가 유일한 원천이다. 이름은 정본(`shared/canon`)에서 읽고 같은 길이(6B)로 덮는다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

sys.path.insert(0, str(common.ROOT))
from shared import canon

BLOCK = 141
JP = "ソニア"


def _kr() -> str:
    kr = canon.lookup(JP, None, "ed1")
    if not kr:
        raise SystemExit(f"블록 141 파티 레코드 {JP}: 정본에 없다")
    return kr


def chars() -> set[str]:
    return set(_kr())


def new_block(orig: bytes, cs) -> bytes:
    """`name+06` 꼴이 블록에 딱 하나일 때 같은 길이로 덮는다(대사 속 이름은 06 으로 안 끝나 걸리지 않는다)."""
    old = JP.encode("cp932")
    pat = old + b"\x06"
    if orig.count(pat) != 1:
        raise SystemExit(
            f"블록 141 파티 레코드 {JP}: 레코드가 {orig.count(pat)}곳이다(하나여야 한다)"
        )
    new = cs.encode(_kr())
    if len(new) != len(old):
        raise SystemExit(f"블록 141 파티 레코드 {JP}: 길이가 안 맞는다 {len(new)}B ≠ {len(old)}B")
    at = orig.index(pat)
    out = bytearray(orig)
    out[at : at + len(old)] = new
    return bytes(out)


if __name__ == "__main__":
    print(f"  블록 {BLOCK} {JP} → {_kr()} ({len(JP.encode('cp932'))}B)")
