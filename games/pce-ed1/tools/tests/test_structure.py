"""재배치 장부·구조 대조(`structure.py`) — 가짜 바이트로(원본 데이터 없이): 일부러 망가뜨린 사본에서 검사가 실제로 우는지."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import structure as S

A = b"\x82\xa0\x82\xa2"  # 가짜 글자 둘(전각 가나) — messages.parse 가 메시지로 잡으려면 두 글자 이상
HEAD = b"\x4c\x00\xa0" + bytes(5)
ORIG = HEAD + b"\x1f" + A + b"\x04" + A + A + b"\x01" + A + A + b"\x00" + bytes(6)  # 메시지 +8 ~ +32
M0, M1 = 8, 32


def new_block(text: bytes, tail: bytes = b"") -> bytes:
    """메시지 칸(+8~+32)에 `text` 를 쓰고 남는 칸은 0, 꼬리를 덧붙인 블록."""
    room = M1 - M0
    assert len(text) <= room
    return ORIG[:M0] + text + bytes(room - len(text)) + ORIG[M1:] + tail


def run(block: bytes):
    rec = S.BlockRec(1, 2, ORIG)
    rec.add("translate", ORIG, block)
    return S.analyze_block(rec)


class Structure(unittest.TestCase):
    def test_identical_has_no_rows_and_no_violations(self):
        rows, viol = run(ORIG)
        self.assertEqual((rows, viol), ([], []))

    def test_shorter_translation_zero_padded_is_ok(self):
        rows, viol = run(new_block(b"\x1f" + A + b"\x04" + A + b"\x00"))
        self.assertEqual(viol, [])
        self.assertEqual([k for _b, k, _c in rows], ["채움"])

    def test_fill_bytes_other_than_zero_are_violations(self):
        blk = bytearray(new_block(b"\x1f" + A + b"\x04" + A + b"\x00"))
        blk[M1 - 2 : M1] = b"\xff\xff"  # ss-ed3 에서 다음 블록 호출을 막은 그 채움
        _rows, viol = run(bytes(blk))
        self.assertTrue(any("0 이 아닌" in v for v in viol), viol)

    def test_changed_terminator_is_a_violation(self):
        _rows, viol = run(new_block(b"\x1f" + A + b"\x04" + A + b"\x06"))
        self.assertTrue(any("종료 바이트" in v for v in viol), viol)

    def test_missing_speaker_opening_is_a_violation(self):
        _rows, viol = run(new_block(A + b"\x00"))
        self.assertTrue(any("화자 열개" in v for v in viol), viol)

    def test_foreign_opcode_inside_text_is_a_violation(self):
        _rows, viol = run(new_block(b"\x1f" + A + b"\x04" + A + b"\x0d" + A + b"\x00"))
        self.assertTrue(any("낯선 옵코드" in v for v in viol), viol)

    def test_tail_jump_ok_and_broken_variants(self):
        tail_at = len(ORIG)
        jump = bytes([0x0F, (S.BASE + tail_at) & 0xFF, (S.BASE + tail_at) >> 8])
        text = b"\x1f" + A + b"\x04" + A + jump
        ok = new_block(text, tail=A + A + b"\x00")
        rows, viol = run(ok)
        self.assertEqual(viol, [])
        self.assertIn("꼬리 이음", [k for _b, k, _c in rows])
        # 꼬리가 종료 없이 끝난다
        _r, v = run(new_block(text, tail=A + A))
        self.assertTrue(any("종료도 점프도 없이" in x for x in v), v)
        # 꼬리 종료 바이트가 원본과 다르다
        _r, v = run(new_block(text, tail=A + A + b"\x07"))
        self.assertTrue(any("꼬리 조각 종료 바이트" in x for x in v), v)
        # 아무도 안 가리키는 덧붙임
        _r, v = run(new_block(b"\x1f" + A + b"\x04" + A + b"\x00", tail=A + b"\x00"))
        self.assertTrue(any("아무 점프·스텁도 가리키지 않는다" in x for x in v), v)

    def test_jump_target_outside_block_is_a_violation(self):
        text = b"\x1f" + A + b"\x04" + A + bytes([0x0F, 0xFF, 0xBF])
        _r, v = run(new_block(text))
        self.assertTrue(any("블록 밖" in x for x in v), v)

    def test_ledger_has_kinds_and_no_source_text(self):
        rows, _v = run(new_block(b"\x1f" + A + b"\x04" + A + b"\x00"))
        tsv = S.ledger_tsv(rows)
        self.assertIn("채움", tsv)
        self.assertNotIn(A.decode("cp932"), tsv)  # 원문·문장은 안 넣는다
        self.assertEqual(len(tsv.splitlines()[0].split("\t")), 8)


class ReferencedTerminator(unittest.TestCase):
    """다른 코드가 가리키는 종료 바이트(`0F` 목표)를 우리 점프가 덮으면 우는지 — 씬 12 라우엘 「오. 오시합니다」(10-22)."""

    def test_overwriting_a_jump_target_terminator_is_a_violation(self):
        import messages as MM

        orig = ORIG[:M1] + b"\x0f" + (MM.BASE + M1 - 1).to_bytes(2, "little") + bytes(3)  # 뒤 옵코드가 메시지 끝 `00` 으로 점프
        # 제자리 끝(종료 바이트 자리)까지 점프 주소로 덮은 사본
        bad = bytearray(orig)
        bad[M1 - 3 : M1] = b"\x0f\x00\xa1"
        rec = S.BlockRec(1, 2, orig)
        rec.add("translate", orig, bytes(bad) + bytes(8))
        _rows, viol = S.analyze_block(rec)
        self.assertTrue(any("점프 목표" in v for v in viol), viol)

    def test_unreferenced_terminator_may_be_overwritten_by_the_jump(self):
        rec = S.BlockRec(1, 2, ORIG)
        bad = bytearray(ORIG)
        bad[M1 - 3 : M1] = b"\x0f\x00\xa1"
        rec.add("translate", ORIG, bytes(bad) + bytes(8))
        _rows, viol = S.analyze_block(rec)
        self.assertFalse(any("점프 목표" in v for v in viol), viol)


class BattleStructure(unittest.TestCase):
    """전투 블록(`analyze_battle_block`) — 가짜 바이트(전각 가나 셋 + 종단 `0A`)."""

    LOAD = 0xC400
    T = b"\x82\xa0\x82\xa2\x82\xa4"  # あいう
    ORIG = b"\xff\xff\xff\xff" + T + b"\x0a" + b"\x00\x00\x00\x00"  # 본문 +4~+10, 종단 0A +10

    def run_(self, new: bytes):
        return S.analyze_battle_block("1:b0", self.ORIG, new, self.LOAD)

    def test_identical(self):
        rows, viol = self.run_(self.ORIG)
        self.assertEqual((rows, viol), ([], []))

    def test_shorter_with_return_jump_and_zero_pad(self):
        back = self.LOAD + 10  # 원래 종단 자리
        new = b"\xff\xff\xff\xff" + b"\x82\xa0" + bytes([0x0F, back & 0xFF, back >> 8]) + b"\x00" + b"\x0a" + b"\x00\x00\x00\x00"
        rows, viol = self.run_(new)
        self.assertEqual(viol, [])
        self.assertIn("복귀 점프", [k for _b, k, _c in rows])

    def test_nonzero_pad_after_return_jump_is_a_violation(self):
        back = self.LOAD + 10
        new = b"\xff\xff\xff\xff" + b"\x82\xa0" + bytes([0x0F, back & 0xFF, back >> 8]) + b"\xff" + b"\x0a" + bytes(4)
        _rows, viol = self.run_(new)
        self.assertTrue(any("0 이 아닌" in v for v in viol), viol)

    def test_original_terminator_must_stay_in_place(self):
        back = self.LOAD + 10
        new = b"\xff\xff\xff\xff" + b"\x82\xa0" + bytes([0x0F, back & 0xFF, back >> 8]) + b"\x00" + b"\x00" + bytes(4)
        _rows, viol = self.run_(new)
        self.assertTrue(any("종단 바이트" in v for v in viol), viol)

    def test_tail_piece_must_return_to_the_original_flow(self):
        tail_at = len(self.ORIG)
        head = bytes([0x0F, (self.LOAD + tail_at) & 0xFF, (self.LOAD + tail_at) >> 8])
        good_back = self.LOAD + 10
        base = b"\xff\xff\xff\xff" + head + b"\x00" * 3 + b"\x0a" + bytes(4)  # 머리 점프 + 0 채움 + 원래 종단
        tail = self.T + b"\x82\xa0" + bytes([0x0F, good_back & 0xFF, good_back >> 8])
        rows, viol = self.run_(base + tail)
        self.assertEqual(viol, [])
        self.assertIn("꼬리 이음", [k for _b, k, _c in rows])
        bad = self.T + b"\x82\xa0" + bytes([0x0F, (good_back + 3) & 0xFF, (good_back + 3) >> 8])
        _r, v = self.run_(base + bad)
        self.assertTrue(any("되돌아간다" in x for x in v), v)

    def test_unreferenced_tail_is_a_violation(self):
        _r, v = self.run_(self.ORIG + b"\x82\xa0\x00")
        self.assertTrue(any("아무 점프도 가리키지 않는다" in x for x in v), v)

    def test_bytes_outside_units_must_not_change(self):
        bad = bytearray(self.ORIG)
        bad[-1] = 0x55  # 문구·이름칸 밖
        _r, v = self.run_(bytes(bad))
        self.assertTrue(any("밖 바이트" in x for x in v), v)


class SysmsgStructure(unittest.TestCase):
    """시스템 메시지 제어 열(`analyze_sysmsg`) — 가짜 바이트."""

    def units(self):
        # 단위: 앞 `02` · 본문 · 뒤 `0A`
        return [{"addr": 0x8010, "off": 0x10, "room": 12, "lead": ["02"], "tail": ["0A"]}]

    def banks(self, raw: bytes, at: int = 0x10):
        b = bytearray(0x2000)
        b[at : at + len(raw)] = raw
        return {0x6D: bytes(b), 0x74: bytes(0x2000)}

    def test_lead_and_tail_kept(self):
        rows, viol = S.analyze_sysmsg(self.units(), self.banks(b"\x02\xf1\x01\xf1\x02\x0a"))
        self.assertEqual(viol, [])

    def test_missing_tail_terminator_is_a_violation(self):
        _r, viol = S.analyze_sysmsg(self.units(), self.banks(b"\x02\xf1\x01\xf1\x02\x00\x00"))
        self.assertTrue(viol, viol)

    def test_spilled_piece_is_followed_through_a_jump(self):
        # 원 자리 `0F <새 주소>` → 새 자리에 `02 본문 0A`
        jump = bytes([0x0F, 0x00, 0x81])  # 0x8100
        b = bytearray(0x2000)
        b[0x10 : 0x10 + 3] = jump
        b[0x100 : 0x100 + 6] = b"\x02\xf1\x01\xf1\x02\x0a"
        rows, viol = S.analyze_sysmsg(self.units(), {0x6D: bytes(b), 0x74: bytes(0x2000)})
        self.assertEqual(viol, [])
        self.assertTrue(rows)

    def test_original_body_jump_is_an_op_not_a_tail_link(self):
        # 원본 본문에 든 `0F 주소`(jp 에 {0F….})는 원본이 둔 옵코드라 따라가지 않고 지난다 — 뒤 꼬리 `0F 0A9F` 까지 읽혀야 한다
        u = [{"addr": 0x8010, "off": 0x10, "room": 12, "lead": ["02"], "tail": ["0F0A9F"], "jp": "x{02}y{0F0090}{02}z"}]
        raw = b"\x02\xf1\x01\x0f\x00\x90\x02\xf1\x01\x0f\x0a\x9f"
        _r, viol = S.analyze_sysmsg(u, self.banks(raw))
        self.assertEqual(viol, [])

    def test_label_separator_positions(self):
        o = bytes([1, 0, 1, 1, 0, 1]) + bytes(10)
        self.assertEqual(S.analyze_label_separators(o, o, 0, 6), [])
        n = bytes([1, 1, 0, 1, 0, 1]) + bytes(10)  # 구분자 자리가 한 칸 밀렸다
        self.assertTrue(S.analyze_label_separators(o, n, 0, 6))
        self.assertEqual(S.analyze_label_separators(o, n, 0, 6, {1: 2}), [])


if __name__ == "__main__":
    unittest.main()
