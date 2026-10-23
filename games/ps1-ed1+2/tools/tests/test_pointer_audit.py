"""최종 이미지 포인터 대조·쓰기 겹침 게이트(check_pointer_audit)의 **통과/불일치/겹침 실패 경로**를 합성 이미지로 못 박는다.

실물 이미지는 안 쓴다 — 작은 가짜 EXE 버퍼에 `lui`+`addiu` 참조와 문자열을 심는다.
"""

import os
import pathlib
import struct
import sys

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
os.environ.setdefault("LOCK_BYPASS", "1")

import check_pointer_audit as A

LUI, ADDIU = 0x0F, 0x09


def _lui(rt, hi):
    return struct.pack("<I", (LUI << 26) | (rt << 16) | hi)


def _addiu(rs, rt, lo):
    return struct.pack("<I", (ADDIU << 26) | (rs << 21) | (rt << 16) | (lo & 0xFFFF))


def _exe(size=0x1000):
    return bytearray(size)


def _put_ref(buf, at, addr):
    """at 에 lui t0,hi / addiu t0,t0,lo — 문자열 RAM 주소를 가리키는 참조."""
    hi, lo = addr >> 16, addr & 0xFFFF
    if lo >= 0x8000:
        hi += 1
    buf[at : at + 4] = _lui(8, hi)
    buf[at + 4 : at + 8] = _addiu(8, 8, lo)


def _ram(fo):
    return fo - A.EXE_HDR + A.EXE_RAM_BASE


def _pair(orig_text=b"\x82\xa0", new_text=b"AB", new_at=0x400):
    """원본(문자열 0x300) · 최종(문자열 new_at 로 옮김, 참조 갱신)."""
    orig = _exe()
    orig[0x300 : 0x300 + len(orig_text) + 1] = orig_text + b"\x00"
    _put_ref(orig, 0x100, _ram(0x300))
    final = _exe()
    final[new_at : new_at + len(new_text) + 1] = new_text + b"\x00"
    _put_ref(final, 0x100, _ram(new_at))
    return orig, final


def test_matching_pointer_passes():
    orig, final = _pair(new_text=b"AB")
    total, ok, bad, noref = A.audit_refs(orig, final, [("x", _ram(0x300), b"AB")])
    assert (total, ok, bad, noref) == (1, 1, [], [])


def test_pointer_to_wrong_string_is_caught():
    # 뒤 단계가 앞 문구를 덮어 포인터가 엉뚱한 문구를 가리키는 꼴 — 계획은 AB 인데 최종은 XY
    orig, final = _pair(new_text=b"XY")
    total, ok, bad, _ = A.audit_refs(orig, final, [("x", _ram(0x300), b"AB")])
    assert total == 1 and ok == 0 and len(bad) == 1 and bad[0][3] == b"XY"


def test_every_reference_site_is_checked_not_just_the_first():
    # 같은 문자열을 두 사이트가 가리키는데 둘째만 엉뚱한 곳으로 갱신됨 — 「첫 포인터만」 보면 놓친다
    orig, final = _pair(new_text=b"AB")
    _put_ref(orig, 0x200, _ram(0x300))
    final[0x500:0x503] = b"ZZ\x00"
    _put_ref(final, 0x200, _ram(0x500))
    total, ok, bad, _ = A.audit_refs(orig, final, [("x", _ram(0x300), b"AB")])
    assert total == 2 and ok == 1 and len(bad) == 1


def test_label_without_reference_is_reported_not_passed_silently():
    orig, final = _pair()
    _t, _k, _b, noref = A.audit_refs(orig, final, [("nope", _ram(0x380), b"AB")])
    assert noref == ["nope"]


def test_diff_spans_and_allowed_overlap():
    a = bytes(32)
    b = bytearray(a)
    for i in (4, 5, 6, 20):
        b[i] = 1
    spans = A.to_spans(A.diff_offsets(a, bytes(b)))
    assert spans == [(4, 7), (20, 21)]
    # 허용 구간 안은 통과, 밖은 새 겹침
    assert A.spans_outside(spans, [(0, 8)]) == [(20, 21)]
    assert A.spans_outside([(4, 7)], [(0, 8)]) == []
    # 허용 구간에 걸치기만 하고 넘치면 새 겹침이다
    assert A.spans_outside([(6, 9)], [(0, 8)]) == [(6, 9)]


def test_allowed_overlap_is_exactly_the_documented_contract():
    assert A.ALLOWED_OVERLAP["ED.EXE"] == [(0x4EA0, 0x4EAB)]  # 11바이트 — 머리말의 암묵 계약
    assert A.ALLOWED_OVERLAP["ED2.EXE"] == []


def test_place_name_restoration_is_only_explained_by_exact_slots():
    ok_row = (0x9A1F0, b"AB", b"ABCD")  # 지명 복원이 한 음절(+2B) 늘린 자리
    other_off = (0x1234, b"AB", b"ABCD")  # 다른 자리의 +2B 는 설명 안 됨
    wrong_len = (0x9A1F0, b"AB", b"ABCDEF")  # 허용 자리라도 길이가 다르면 설명 안 됨
    assert A.sys_mismatch_unexplained([ok_row]) == []
    assert A.sys_mismatch_unexplained([other_off, wrong_len]) == [other_off, wrong_len]


def test_stale_or_missing_image_is_not_a_pass(tmp_path):
    assert "없음" in A.stale_reason(str(tmp_path / "nope.bin"))


def test_baseline_signature_changes_when_the_final_string_changes():
    assert A.mon_signature(b"AB") != A.mon_signature(b"AC")
    assert A.mon_signature(b"AB") == A.mon_signature(b"AB")


if __name__ == "__main__":
    import tempfile

    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            if "tmp_path" in v.__code__.co_varnames[: v.__code__.co_argcount]:
                with tempfile.TemporaryDirectory() as d:
                    v(pathlib.Path(d))
            else:
                v()
            print(f"  ok  {k}")
