"""**검사기 자신의 커버리지** — 초록불이 「없다」가 아니라 「안 봤다」였던 자리들.

체크리스트 4-B 가 말하는 그 함정이다. 여기 있는 둘은 **실제로 물렸다**(2026-09-03):
화면엔 일본어가 떠 있는데 덤퍼는 그 문자열을 아예 안 만들었고, 스캐너는 그걸
「번역된 자리」로 넘겼다. 둘 다 **원본 없이** 도는 회귀로 못 박는다.
"""

import os
import sys
import unittest

_T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _T)

import dump_scn
import scan_untranslated as S


class Dumper(unittest.TestCase):
    def test_fullwidth_space_is_printable_enough(self):
        """🔴 파이썬의 `str.isprintable()` 은 전각 공백(U+3000)에 **False** 를 준다.

        이 게임은 폭을 맞추느라 전각 공백을 잔뜩 쓴다 — 그대로 두면 그런 문자열이
        통째로 「데이터」로 걸러져 **덤프에 아예 안 들어온다.** 실측: 33개가 빠져 있었고
        그중 `ED1SCN27` 셋은 화면에 일본어로 남아 있었다.
        """
        self.assertFalse("　".isprintable(), "파이썬 동작이 바뀌었다 — 주석을 다시 본다")
        raw = "『　　ほしぞら館へ\n　　　　ようこそ !　』".encode("cp932")
        self.assertTrue(dump_scn.plausible_text(raw), "전각 공백이 많으면 텍스트가 아니라고 한다")
        self.assertEqual(dump_scn.classify(raw + b"\x00", 0), "string")

    def test_binary_is_still_rejected(self):
        """⚠ 넓히고도 **바이너리는 여전히 걸러야 한다** — 안 그러면 오탐이 밀려든다."""
        self.assertFalse(dump_scn.plausible_text(bytes(range(1, 40))))
        self.assertFalse(dump_scn.plausible_text(b"\x00\x01"))


class Scanner(unittest.TestCase):
    def test_capped_string_backs_off_one_byte(self):
        """🔴 `MAXLEN` 에서 자르면 **두 바이트 글자의 한복판**일 수 있다.

        그때 디코드가 실패하는데, 스캐너는 그걸 「우리 슬롯 코드가 들어갔다 = 번역됐다」로
        읽어 **일본어가 그대로인 자리를 조용히 넘겼다**(실측: `ED1SCN27` 0x5A9C, 127B).
        SJIS 는 최대 2바이트라 한 바이트만 물러서면 된다.
        """
        # ⚠ 반각 하나를 앞에 둬 **바이트 수를 홀수로 민다** — 그래야 상한이 글자 한복판에
        #   떨어진다(전각만이면 짝수라 안 갈라져 이 함정을 못 재현한다).
        s = "!" + "星空館へようこそ" * 20
        raw = s.encode("cp932")[: S.MAXLEN]
        with self.assertRaises(UnicodeDecodeError):
            raw.decode("cp932")  # 전제: 정확히 글자 한복판에서 잘린다
        self.assertIsNotNone(S._decode(raw, capped=True), "잘린 것을 못 읽는다")
        self.assertIsNone(S._decode(raw, capped=False), "안 잘린 자리는 물러서면 안 된다")

    def test_our_slot_codes_still_read_as_translated(self):
        """⚠ 물러서기가 **번역된 자리까지 살려 내면** 안 된다 — 그건 우리 글자다."""
        self.assertIsNone(S._decode(b"\x85\x40\x85\x41\x85\x42", capped=True))
