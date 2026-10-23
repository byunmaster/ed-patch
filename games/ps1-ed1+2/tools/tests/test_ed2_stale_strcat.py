"""ED2MON 안 채운 버퍼 strcat 탐지(patch_ed2_stale_strcat.find_sites)를 합성 코드로 못 박는다."""

import pathlib
import struct
import sys

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import patch_ed2_stale_strcat as S

NOP = 0


def words(*ws):
    return b"".join(struct.pack("<I", w) for w in ws)


def test_stale_pattern_is_found():
    # strcat(s3, sp+0x18) 직후 sp+0x18 을 새로 채움 — 안 채운 버퍼를 붙이는 자리
    buf = words(NOP, S.JAL_STRCAT, S.ADDIU_A1_SP18, S.ADDIU_A0_SP18, NOP)
    assert S.find_sites(buf) == [4]


def test_normal_strcat_is_not_found():
    # sprintf 로 채운 뒤 strcat 하는 정상 호출은 직후에 a0=sp+0x18 을 다시 안 만든다
    buf = words(S.JAL_STRCAT, S.ADDIU_A1_SP18, NOP, NOP, NOP)
    assert S.find_sites(buf) == []


def test_other_call_is_not_found():
    buf = words(0x0C000000 | 0x1234, S.ADDIU_A1_SP18, S.ADDIU_A0_SP18, NOP)
    assert S.find_sites(buf) == []


if __name__ == "__main__":
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            v()
            print(f"  ok  {k}")
