"""토큰 자리(`tokenorder`) — 가짜 문장으로 옮기는 규칙과 판정을 고정한다(원문 인용 없음)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tokenorder as T  # noqa: E402


class TokenOrder(unittest.TestCase):
    def test_tail_header_and_dict_sentence(self):
        jp = "<COLOR_C>{あ}\n<COLOR_POP>いろは\nにほへと{ございます。}\n<END>"
        tokens = ["<E3>", "{D0:2A}", "<E1>", "{D5:10}", "<E0>"]
        kr = "가나다라.<E3>{D0:2A}<E1>{D5:10}<E0>"
        self.assertTrue(T.problems(jp, kr, tokens, True))
        out = T.fix(jp, kr, tokens, True)
        self.assertEqual(out, "<E3>{D0:2A}\n<E1>가나다라.<E0>")
        self.assertFalse(T.problems(jp, out, tokens, True))

    def test_head_controls_before_text(self):
        jp = "<IF_SET 07><JUMP 0e00>ひふみ\n<END>"
        tokens = ["<F0:07>", "<FA:0E00>", "<E0>"]
        self.assertEqual(
            T.fix(jp, "가나다.<F0:07><FA:0E00><E0>", tokens), "<F0:07><FA:0E00>가나다.<E0>"
        )

    def test_speaker_table_before_body(self):
        jp = "<CALL_TBL 0123456789><JUMP fe00>{あ}\n<JUMP 0c00>{い}\n{う}よむ\n<END>"
        tokens = ["<FD:0123456789>", "<FA:FE00>", "{D0:80}", "<FA:0C00>", "{D0:82}", "{D0:0A}", "<E0>"]
        kr = "{D0:84}\n{D0:0A} 가나다.<FD:0123456789><FA:FE00>{D0:80}<FA:0C00>{D0:82}<E0>"
        out = T.fix(jp, kr, tokens)
        self.assertTrue(out.startswith("<FD:0123456789><FA:FE00>{D0:80}\n<FA:0C00>{D0:82}\n"))
        self.assertFalse(T.problems(jp, out, tokens))

    def test_inline_name_dropped_at_tail(self):
        jp = "<COLOR_4>{あ}は\nいろは\n<COLOR_POP><END>"
        tokens = ["<E2>", "{D0:1C}", "<E1>", "<E0>"]
        self.assertEqual(
            T.fix(jp, "가나는 다라마.<E2>{D0:1C}<E1><E0>", tokens), "<E2>가나는 다라마.<E1><E0>"
        )

    def test_already_fine_is_untouched(self):
        jp = "<COLOR_C>{あ}\n<COLOR_POP>いろは\n<END>"
        tokens = ["<E3>", "{D0:2A}", "<E1>", "<E0>"]
        kr = "<E3>{D0:2A}\n<E1>가나다.<E0>"
        self.assertEqual(T.fix(jp, kr, tokens), kr)
        self.assertFalse(T.problems(jp, kr, tokens, True))


if __name__ == "__main__":
    unittest.main()
