"""전투 문구 조립 공백 게이트·조각 참조 패치를 합성 EXE 로 못 박는다."""

import pathlib
import struct
import sys

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import check_battle_number_space as C
import hangul_map as H
import patch_battle_frag_space as F

LUI, ADDIU = 0x0F, 0x09


def enc(s):
    return F.enc(s)


def build(strings, calls):
    """strings: {이름: bytes}, calls: [이름…] — 이름 순서대로 `lui a1 · addiu a1,a1` 참조를 심은 가짜 EXE.
    문자열은 코드 뒤 데이터에 놓는다. 반환 (buf, {이름: RAM 주소})."""
    code = len(calls) * 8 + 8
    data_off = F.EXE_HDR + code
    addr, blob = {}, b""
    for k, v in strings.items():
        addr[k] = F.EXE_RAM_BASE + (data_off - F.EXE_HDR) + len(blob)
        blob += v + b"\x00"
    words = []
    for k in calls:
        a = addr[k]
        hi, lo = (a >> 16) & 0xFFFF, a & 0xFFFF
        if lo >= 0x8000:
            hi += 1
        words += [(LUI << 26) | (5 << 16) | (hi & 0xFFFF), (ADDIU << 26) | (5 << 21) | (5 << 16) | lo]
    buf = bytearray(F.EXE_HDR) + b"".join(struct.pack("<I", w) for w in words) + b"\0" * 8 + blob
    return bytes(buf), addr


def test_number_then_hangul_word_is_flagged():
    s = {"n": b"%c%d%c", "f": enc("회복되었다.\n")}
    buf, _ = build(s, ["n", "f"])
    bad = C.audit(buf)
    assert [b[0] for b in bad] == ["수치 뒤 붙음"]


def test_number_then_space_or_unit_is_ok():
    s = {"n": b"%d", "a": enc(" 회복되었다.\n"), "u": enc("포인트 올랐다.\n"), "p": enc("의 피해!!\n")}
    for frag in ("a", "u", "p"):
        buf, _ = build(s, ["n", frag])
        assert C.audit(buf) == [], frag


def test_double_space_is_flagged():
    s = {"h": b"%s ", "f": enc(" 숨었다.")}
    buf, _ = build(s, ["h", "f"])
    assert [b[0] for b in C.audit(buf)] == ["공백 이중"]


def test_sites_without_number_are_found():
    s = {"n": b"%d", "f": enc(" 회복되었다.\n")}
    buf, _ = build(s, ["n", "f", "f"])  # 둘째 참조 앞에도 수치 서식이 창 안에 있어 둘 다 수치 자리
    assert F.sites(buf) == []
    far = {"n": b"%d", "f": enc(" 회복되었다.\n"), "p": b"x" * 4}
    buf2, _ = build(far, ["f"])  # 수치 서식 참조 없이 조각만
    assert len(F.sites(buf2)) == 1


if __name__ == "__main__":
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            v()
            print(f"  ok  {k}")
