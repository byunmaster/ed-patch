"""check_jp_left_overlay 의 판정(참조되는 일본어 = 실패 · 참조 없는 일본어 = 죽은 데이터 · 한글 슬롯은 일본어 아님)을 합성 버퍼로 못 박는다."""

import pathlib
import struct
import sys

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import check_jp_left_overlay as C
import hangul_map as H

BASE = C.OVERLAY_BASE
JP = "ほげふが".encode("cp932")  # 가나 4자
KO = b"".join(H.syllable_sjis(c).to_bytes(2, "big") for c in "사봉이")  # 한글 슬롯 3자


def _lui(rt, hi):
    return (0x0F << 26) | (rt << 16) | (hi & 0xFFFF)


def _addiu(rt, rs, imm):
    return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _overlay(strings, ref_to=None):
    """앞에 코드 8B(참조 한 쌍) 뒤에 NUL 로 구분한 문자열들. ref_to=문자열 번호 → 그 문자열을 lui+addiu 로 참조."""
    body = b"\0" + b"\0".join(strings) + b"\0"
    code_len = 8
    offs, p = [], code_len + 1
    for s in strings:
        offs.append(p)
        p += len(s) + 1
    code = b"\0" * code_len
    if ref_to is not None:
        addr = BASE + offs[ref_to]
        hi, lo = (addr + 0x8000) >> 16, addr & 0xFFFF
        code = struct.pack("<II", _lui(2, hi), _addiu(2, 2, lo))
    return code + body, offs


def test_referenced_japanese_fails():
    buf, offs = _overlay([JP, KO], ref_to=0)
    rows = C.analyze("T", buf, BASE, 0)
    bad, dead = C.judge(rows)
    assert [r[1] for r in bad] == [offs[0]] and not dead


def test_unreferenced_japanese_is_dead_data():
    buf, offs = _overlay([JP, KO], ref_to=1)
    bad, dead = C.judge(C.analyze("T", buf, BASE, 0))
    assert not bad and [r[1] for r in dead] == [offs[0]]


def test_hangul_slot_codes_are_not_japanese():
    buf, _ = _overlay([KO], ref_to=0)
    assert C.analyze("T", buf, BASE, 0) == []


def test_reference_into_middle_of_string_counts():
    buf, offs = _overlay([JP], ref_to=0)
    mid = bytearray(buf)
    addr = BASE + offs[0] + 2  # 문자열 중간 조각을 가리킨다
    hi, lo = (addr + 0x8000) >> 16, addr & 0xFFFF
    mid[0:8] = struct.pack("<II", _lui(2, hi), _addiu(2, 2, lo))
    bad, _ = C.judge(C.analyze("T", bytes(mid), BASE, 0))
    assert len(bad) == 1


def test_allowed_list_is_empty():
    assert C.ALLOWED == set()


if __name__ == "__main__":
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            v()
            print(f"  ok  {k}")
