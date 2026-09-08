"""번역 메모리의 정규화 — **원본 없이**, pykakasi 없이 돈다(순수 함수만)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import text  # noqa: F401  (common 보다 먼저)
import tm


class Normalize(unittest.TestCase):
    def test_가타카나는_히라가나로(self):
        self.assertEqual(tm.to_hira("セリオス"), "せりおす")

    def test_sfc_키는_제어와_구두점을_걷고_이름_중괄호를_벗긴다(self):
        jp = "<COLOR_C>{へいし}\n<COLOR_POP>おい、ちょっと　まて。<END>"
        self.assertEqual(tm.sfc_key(jp), "へいしおいちょっとまて")

    def test_ps1_토큰도_걷는다(self):
        self.assertEqual(
            tm._STRIP.sub("", "{c}侍女{c}{n}お出かけですか、王子さま？{n}"),
            "侍女お出かけですか王子さま",
        )

    def test_bigrams(self):
        self.assertEqual(tm.bigrams("あいう"), {"あい", "いう"})


if __name__ == "__main__":
    unittest.main()


class Textmap(unittest.TestCase):
    def test_토큰_계약(self):
        import textmap

        toks = ["<E3>", "{D3:08}", "<E1>", "<FF>", "<E0>"]
        self.assertIsNone(textmap.check_tokens("<E3>{D3:08}<E1>어이.<FF>잠깐<E0>", toks))
        self.assertIsNotNone(textmap.check_tokens("<E3>{D3:08}<E1>어이.<E0>", toks))  # <FF> 빠짐
        self.assertIsNotNone(
            textmap.check_tokens("<E3>{D3:08}<FF><E1>어이.<E0>", toks)
        )  # 제어 순서
        self.assertIsNone(
            textmap.check_tokens("{D1:02}{D0:03}<E0>", ["{D0:03}", "{D1:02}", "<E0>"])
        )  # 사전 어순 허용
