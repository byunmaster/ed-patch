"""UI 문안 정본의 계약 — 원본 없이 도는 회귀.

원본과의 대조(지문·길이)는 `uitext.py --check` 가 게이트에서 한다. 여기서는 파일의 모양과
**이 게임에서만 통하는 규약**을 박는다.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import font
import hangul_map
import textenc
import uitext

DISCS = ("ed3", "ed4")


class TestUiText(unittest.TestCase):
    def test_shape(self):
        for disc in DISCS:
            p = uitext.canon_path(disc)
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as f:
                doc = json.load(f)
            self.assertEqual(doc["disc"], disc)
            for k, v in doc["strings"].items():
                self.assertTrue(k.startswith("0x"), k)
                self.assertEqual(len(v["jp"]), 8, f"{k}: 지문은 sha1 앞 8자")
                self.assertTrue(
                    v["kr"], k
                )  # 공백만인 문안은 일부러 비운 조각이다(「は」「い」의 「い」)

    def test_only_codes_the_game_has(self):
        """🔴 부호는 **전각만** 있다 — `.`·`,` 는 코드표에 없다.

        없는 글자를 쓰면 빌드가 그 줄을 통째로 건너뛴다(조용히 사라지는 게 아니라 알리지만,
        애초에 안 쓰는 게 맞다). 한글은 자리를 받으므로 검사에서 뺀다.
        """
        for disc in DISCS:
            if not os.path.exists(uitext.canon_path(disc)):
                continue
            have = set(textenc.charmap(disc).values()) | set(textenc.CONTROL.values())
            have |= set(hangul_map.PUNCT)  # 우리가 원본 자리에 다시 굽는 부호(, .)
            have.add("\n")  # 0x0001 — 설명문 창의 개행(`hangul_map.encode`)
            bad = set()
            for row in uitext.load(disc).values():
                for ch in row["kr"]:
                    if (
                        "가" <= ch <= "힣" or ch == " " or ch in font.SPLIT
                    ):  # 나눈 글리프도 자리를 받는다
                        continue
                    if ch not in have:
                        bad.add(ch)
            self.assertFalse(bad, f"{disc}: 코드표에 없는 글자 {sorted(bad)}")

    def test_korean_punctuation_maps_to_real_codes(self):
        """🔴 마침표·쉼표는 **원본 자리(2=。 · 1=、)를 다시 구워** 쓴다 — 자리를 새로 안 쓴다.

        옛 이름은 `test_no_ascii_punctuation` 이었고 「반각은 이 게임에 없다」고 못 박고 있었다.
        0x01 을 줄바꿈으로 오해한 데서 온 규칙이다(2026-09-07 정정).
        """
        self.assertEqual(hangul_map.PUNCT, {",": 0x01, ".": 0x02, "?": 0x04, "!": 0x05})
        self.assertEqual(textenc.CONTROL[0x01], "、")

    def test_scanner_blind_spot_recovered(self):
        """🔴 `dump_names.strings()` 는 **바로 앞이 종결이 아닌** 문자열을 앞 자료와 한 덩어리로
        읽고 버린다. 두 부류다(uitext 머리 주석):

        ① 표 바로 뒤 첫 항목 — 표의 마지막 오프셋 값이 앞에 붙는다. `exetext.glued_entries` 가
           표에서 되살린다: `戦闘設定`(커맨드 창 맨 위) · `ページ`(페이지 목록 1번 줄, 09-27 마스터
           캡처 「ページ 1」) · `見`(소지품 창 見る).
        ② 표가 아닌 자료 뒤 — `uitext.EXTRA_SITES` 로 사람이 확인한 자리만: `はい`(0x10BC).

        ⚠ 09-26 에는 ①을 「앞 워드 0x182 가 미매핑 코드」로 오진했다 — 그 값은 표 0xA10B0 의
        마지막 오프셋이었다. 이 테스트는 자리가 **복구되는지**와 **일반 스캐너가 여전히 못
        보는지**(전제가 안 바뀌었는지)를 같이 지킨다.
        """
        disc = "ed3"
        want = {0xA10CC: "戦闘設定", 0xA13E4: "ページ", 0x9D188: "見", 0x10BC: "はい"}
        _, ss = uitext.sites(disc)
        for off, jp in want.items():
            self.assertIn(off, ss, f"0x{off:X} 자리가 사라졌다")
            self.assertEqual(ss[off]["jp"], jp)

        # 전제 확인 — 일반 스캐너는 여전히 이 자리를 혼자 힘으로 못 찾는다.
        # (찾게 되면 되살리는 장치가 불필요해진 것이니 그때 이 assert 와 장치를 같이 정리한다.)
        import dump_names

        cm = textenc.charmap(disc)
        data = uitext.exe_bytes(disc)
        labels = dump_names.REGIONS[disc]
        found = {
            o
            for r in dump_names.split(
                dump_names.regions(dump_names.strings(data, cm, max_len=64, newline=True)), labels
            )
            for o in r["offs"]
        }
        for off in want:
            self.assertNotIn(off, found, f"0x{off:X}: 일반 스캐너가 이제 찾는다 — 전제가 바뀌었다")

    def test_pack_fixed_pads_shrunk_strings_instead_of_leaving_slack(self):
        """🔴 실측 사고(ED3, 2026-09-26) — 표 없는(길이 고정) 자리도 표 있는 자리와 같은
        함정이다. 메시지속도 값 목록(「보통」「느림」)이 이 경로로 들어가는데, 짧아진 자리를
        그냥 `TERM_FFFF` 로 끊자 순차 스캔이 그걸 「목록 끝」으로 읽어 「느림」이 안 보였다."""
        import struct

        exe = bytearray(20)
        struct.pack_into("<4H", exe, 0, 0x40, 0x41, 0x42, 0x8000)  # 원본 3코드 + 종결
        uitext.pack_fixed(exe, 0, [0x50], orig_len=3, orig_term=0x8000, pad_code=0x99)
        got = struct.unpack_from("<4H", exe, 0)
        self.assertEqual(
            got, (0x50, 0x99, 0x99, 0x8000), "짧아진 만큼 채움 글자로 늘고 원본 종결 그대로"
        )

    def test_pack_fixed_without_pad_code_falls_back_to_old_shape(self):
        """`pad_code` 가 없으면(공백 글자가 없는 디스크) 예전처럼 짧게 쓰고 만다."""
        import struct

        exe = bytearray(20)
        struct.pack_into("<4H", exe, 0, 0x40, 0x41, 0x42, 0x8000)
        uitext.pack_fixed(exe, 0, [0x50], orig_len=3, orig_term=0x8000, pad_code=None)
        got = struct.unpack_from("<2H", exe, 0)
        self.assertEqual(got, (0x50, 0x8000))
