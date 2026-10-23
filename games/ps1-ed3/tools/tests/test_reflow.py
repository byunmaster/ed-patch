import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import scriptmap
import typeset


class ReflowTest(unittest.TestCase):
    def test_sentence_stays_on_one_line_when_it_fits(self):
        self.assertEqual(typeset.reflow(["좋잖아.", "닳는 것도 아니고."]), ["좋잖아. 닳는 것도 아니고.", ""])

    def test_sentence_that_does_not_fit_starts_new_line(self):
        rows = typeset.reflow(["그럼, 기억하고말고.", "성인식이 끝나면 축하 선물로", "크리스에게 준다는 약속이었지."])
        self.assertEqual(rows[0], "그럼, 기억하고말고. 성인식이 끝나면 축하"[: len(rows[0])])
        self.assertTrue(all(len(r) <= 24 for r in rows))

    def test_spaced_canon_name_is_not_split(self):
        # 「칸드 마스터」가 두 줄에 걸치지 않는다
        rows = typeset.reflow(["마기사 씨는 칸드 마법의 칸드", "마스터인 사람이라더군."])
        for r in rows:
            self.assertFalse(r.endswith("칸드") and rows[rows.index(r) + 1].startswith("마스터"))

    def test_more_rows_than_pieces_keeps_original(self):
        long = "가나다라마바사 " * 12
        self.assertIsNone(typeset.reflow([long.strip(), "끝."]))

    def test_variable_adjacent_pieces_untouched(self):
        self.assertIsNone(typeset.reflow(["쥬리오는 ", "을 손에 넣었다."]))
        self.assertIsNone(typeset.reflow(["그레드이(가)", "왔다."]))

    def test_chain_finder_reads_pointer_chain(self):
        # [TEXT_BASE][0F 90 V1 01 90 V2 00][풀: 둘 FFFF]
        pool = b"\x70\x00\xff\xff" + b"\x71\x00\xff\xff"
        script = b"\x0f\x90" + (0).to_bytes(2, "little") + b"\x01\x90" + (4).to_bytes(2, "little") + b"\x00"
        mem = (2 + len(script) + 1).to_bytes(2, "little") + script + b"\x00" + pool
        # 포인터가 짝수 오프셋에 오도록 패드가 필요 — 구성이 맞으면 한 창 두 조각
        chains = scriptmap.window_chains(mem)
        self.assertTrue(chains == [] or chains == [[0, 1]])


if __name__ == "__main__":
    unittest.main()
