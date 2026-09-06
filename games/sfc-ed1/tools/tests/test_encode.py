"""한글 인코더 — **원본 없이** 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import text  # noqa: F401, I001
import encode


class Encode(unittest.TestCase):
    def setUp(self):
        self.rep = encode.repertoire(["어이, 잠깐 기다려. 병사가 은는을를 검…"])
        self.idx = {ch: i for i, ch in enumerate(self.rep)}

    def test_왕복(self):
        s = "어이, 잠깐\n기다려.<E0>"
        e = encode.encode(s, self.idx)
        self.assertEqual([k for k, *_ in e.parts], ["bytes", "ctrl"])
        self.assertEqual(encode.decode_kr(e.parts[0][1], self.rep), "어이, 잠깐\n기다려.")

    def test_한글은_2바이트_반각은_1바이트(self):
        e = encode.encode("어 1.", self.idx)
        b = e.parts[0][1]
        self.assertEqual(len(b), 2 + 1 + 1 + 1)
        self.assertIn(b[0], encode.LEADS)
        self.assertEqual(b[2:], bytes([0x10, 0x01, 0x83]))

    def test_사전_뒤_조사는_빌드가_확정(self):
        e = encode.encode("{D3:08}{이/가} 검{을/를}", self.idx, {"D3:08": "병사"})
        self.assertEqual(e.parts[0], ("dict", "{D3:08}", bytes([0xD3, 0x08])))
        self.assertEqual(encode.decode_kr(e.parts[1][1], self.rep), "가 검을")
        self.assertEqual(e.runtime_josa, 0)

    def test_런타임_치환_뒤_조사는_코드(self):
        e = encode.encode("{D6}{은/는}", self.idx)
        self.assertEqual(e.parts[0], ("dict", "{D6}", bytes([0xD6])))
        self.assertEqual(e.parts[1][1], bytes([encode.JOSA_LEAD, encode.JOSA_BASE + 0]))
        self.assertEqual(e.runtime_josa, 1)

    def test_라벨과_제어(self):
        e = encode.encode(
            "로드<FA:0C00><EF>저장<@>하다<E0>",
            self.idx | {"로": 0, "드": 1, "저": 2, "장": 3, "하": 4, "다": 5},
        )
        self.assertEqual(
            [k for k, *_ in e.parts], ["bytes", "ctrl", "ctrl", "bytes", "label", "bytes", "ctrl"]
        )

    def test_매핑_없는_글자는_실패(self):
        with self.assertRaises(ValueError):
            encode.encode("abc", self.idx)
        with self.assertRaises(ValueError):
            encode.encode("힣", self.idx)  # 레퍼토리 밖


if __name__ == "__main__":
    unittest.main()
