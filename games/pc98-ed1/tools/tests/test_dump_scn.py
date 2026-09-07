"""덤퍼의 라운드트립 — **원본 없이** 돈다(루트 CLAUDE.md: 게임 테스트는 자리로 찾힌다).

원본을 읽는 검증은 `check.sh` 몫이고, 여기선 **문법 자체**만 본다.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dump_scn
import scn


class DecodeRoundTrip(unittest.TestCase):
    def rt(self, raw: bytes, expect: str, expect_kana: bool = True):
        text, end, kana = dump_scn.decode_run(raw, 0)
        self.assertEqual(text, expect)
        self.assertEqual(dump_scn.encode_run(text), raw[:end])
        self.assertEqual(kana, expect_kana)
        return end

    def test_전각_가나(self):
        raw = "おはよう".encode("shift_jis")
        self.rt(raw, "おはよう")

    def test_한자만이면_가나없음(self):
        raw = "王子".encode("shift_jis")
        self.rt(raw, "王子", expect_kana=False)

    def test_반각_가나는_1바이트다(self):
        raw = bytes([0xB1, 0xB2])  # ｱｲ
        end = self.rt(raw, "ｱｲ")
        self.assertEqual(end, 2)

    def test_개행은_구간을_안_끊는다(self):
        raw = "おはよう".encode("shift_jis") + b"\x01" + "王子".encode("shift_jis")
        self.rt(raw, "おはよう\\n王子")

    def test_끝에_붙은_개행은_코드다(self):
        """뒤에 텍스트가 없으면 개행은 구간 밖 — 안 그러면 재삽입에서 코드를 먹는다."""
        body = "おはよう".encode("shift_jis")
        text, end, _ = dump_scn.decode_run(body + b"\x01\x00", 0)
        self.assertEqual(text, "おはよう")
        self.assertEqual(end, len(body))

    def test_종료코드에서_멈춘다(self):
        raw = "おはよう".encode("shift_jis")
        text, end, _ = dump_scn.decode_run(raw + b"\x00" + "王子".encode("shift_jis"), 0)
        self.assertEqual(text, "おはよう")
        self.assertEqual(end, len(raw))

    def test_깨진_SJIS_에서_멈춘다(self):
        raw = "おはよう".encode("shift_jis") + b"\x82\x00"
        text, end, _ = dump_scn.decode_run(raw, 0)
        self.assertEqual(text, "おはよう")
        self.assertEqual(end, 8)


class Directory(unittest.TestCase):
    def test_섹터키_표기(self):
        self.assertEqual(scn.format_key((0x10, 0x00, 0x20)), "10.00.20")

    def test_예외표가_살아있다(self):
        """머리[6] 을 못 믿는 자리 — 지워지면 시나리오 파싱이 통째로 밀린다."""
        self.assertEqual(scn.CHUNK_COUNT_OVERRIDE[(0x20, 0x00, 0x20)], 2)
        self.assertEqual(scn.CHUNK_COUNT_OVERRIDE[(0x26, 0x01, 0x22)], 3)


class SectorModel(unittest.TestCase):
    def test_섹터ID_기저를_상수로_안_쓴다(self):
        """디스크마다 대역이 다르다 — 고정 base 를 되살리면 event/program 이 조용히 밀린다."""
        import common

        self.assertFalse(hasattr(common, "SECTOR_BASE"))
        self.assertEqual(common.SECTOR_COUNT, 1232)


if __name__ == "__main__":
    unittest.main()


class SysStrings(unittest.TestCase):
    """Event·Program 은 x86 코드가 대부분이라 자가 다르다."""

    def setUp(self):
        import dump_sys

        self.m = dump_sys

    def test_전각만_이어_붙인다(self):
        raw = "王子".encode("shift_jis") + bytes([0xB1]) + "です".encode("shift_jis")
        text, end = self.m.fullwidth_run(raw, 0)
        self.assertEqual(text, "王子")
        self.assertEqual(end, 4)

    def test_반각_가나는_구간을_안_연다(self):
        """🔴 이걸 허용하면 x86 코드가 통째로 텍스트로 잡힌다(Event 오탐 28,652건)."""
        text, end = self.m.fullwidth_run(bytes([0xB1, 0xB2, 0xB3]), 0)
        self.assertEqual(text, "")
        self.assertEqual(end, 0)

    def test_순한자도_받는다(self):
        """🔴 2026-09-08 에 자를 넓혔다 — 종전엔 `any(kana)` 라 **순한자 UI 를 통째로
        버렸다**(필드 커맨드 창의 `呪文`·`装備` 가 화면에 깨진 한글로 떴다).
        축은 「가나가 있나」가 아니라 **「가나든 한자든 하나라도 있나」**다."""
        self.assertEqual(
            self.m.dump("環讌茫韓環".encode("shift_jis")),
            [{"o": 0, "n": 10, "t": "環讌茫韓環"}],
        )

    def test_가나가_있으면_건진다(self):
        raw = "王子の旅立ち".encode("shift_jis")
        got = self.m.dump(raw)
        self.assertEqual([b["t"] for b in got], ["王子の旅立ち"])


class Font(unittest.TestCase):
    """한글 글리프 표 — 원본이 없어도 폰트만 있으면 돈다."""

    def setUp(self):
        import font

        self.f = font

    def test_완성형_2350자다(self):
        self.assertEqual(len(self.f.ksc_syllables()), 2350)

    def test_힣은_완성형에_없다(self):
        """2,350자는 KS X 1001 이지 현대 한글 전부가 아니다 — 착각하면 표가 밀린다."""
        self.assertNotIn("힣", self.f.ksc_syllables())

    def test_pack32_는_행당_2바이트_MSB다(self):
        import numpy as np

        bits = np.zeros((16, 16), dtype=np.uint8)
        bits[0, 0] = 1  # 첫 행 맨 왼쪽
        bits[1, 15] = 1  # 둘째 행 맨 오른쪽
        packed = self.f.pack32(bits)
        self.assertEqual(len(packed), 32)
        self.assertEqual(packed[0:2], b"\x80\x00")
        self.assertEqual(packed[2:4], b"\x00\x01")

    def test_표_지문이_얼려져_있다(self):
        """폰트나 렌더가 바뀌면 여기가 먼저 운다(제1 원칙 — 결정적 빌드)."""
        self.assertTrue(self.f.TABLE_SHA1)
        self.assertEqual(len(self.f.TABLE_SHA1), 40)


class SjisToJis(unittest.TestCase):
    """SJIS → JIS 구·점. **정답은 codecs 가 안다** — 손으로 적은 기대값을 믿지 않는다
    (실제로 손기대값이 틀려서 멀쩡한 코드를 고칠 뻔했다)."""

    def test_codecs_와_일치한다(self):
        from census_sjis import sjis_to_jis

        for ch in "亜あアン、々熙漢字国王子旅立":
            sjis = ch.encode("shift_jis")
            jis = ch.encode("iso2022_jp")[3:-3]
            want = (jis[0] - 0x20, jis[1] - 0x20)
            self.assertEqual(sjis_to_jis(sjis[0], sjis[1]), want, ch)


class Tables(unittest.TestCase):
    """고정 stride 이름 표 — 우측정렬을 놓치지 않는가."""

    def setUp(self):
        import tables

        self.t = tables

    def test_우측정렬_표를_찾는다(self):
        """🔴 섬 시작만 보면 못 찾는다 — 아이템 표가 실제로 그랬다."""
        recs = []
        # ⚠ 한 글자 이름은 섬으로 안 잡힌다(MIN_CHARS=2) — 실제 아이템 표도 거기서 끊겨
        #   106 + 9 두 묶음으로 잡힌다.
        for name in [
            "何もない",
            "ナイフ",
            "幅広のつるぎ",
            "鉄のやり",
            "銀の杖",
            "大根",
            "金塊",
            "薬草",
            "毒消し",
            "鉄の盾",
        ]:
            enc = name.encode("shift_jis")
            recs.append(b" " * (14 - len(enc)) + enc + b"\x0a\x01\x10\x03\xff\x61")
        blob = b"\x00" * 32 + b"".join(recs) + b"\x00" * 32
        got = self.t.scan(blob)
        self.assertTrue(got, "표를 하나도 못 찾았다")
        best = max(got, key=lambda g: g["n"])
        self.assertEqual(best["stride"], 0x14)
        names = self.t.read_table(blob, best["off"], best["stride"], best["name_len"], best["n"])
        self.assertIn("何もない", names)
        self.assertIn("金塊", names)


class Reuse(unittest.TestCase):
    """문안 사전에 붙이려면 **덤퍼 표기를 PS1 꼴로** 맞춰야 한다."""

    def setUp(self):
        import reuse

        self.r = reuse

    def test_화자와_꼬리마커를_붙인다(self):
        """🔴 꼬리 `%c` 를 빠뜨리면 중립꼴이 한 글자 달라 **열쇠가 통째로 안 맞는다**
        (실측: 붙는 줄이 0.2% 로 보였다)."""
        got = self.r.normalise({"s": "兵士", "t": "この上は\\nなっておる。"})
        self.assertEqual(got, "%c兵士%c\nこの上は\nなっておる。%c")

    def test_화자가_없어도_꼬리는_붙인다(self):
        self.assertEqual(self.r.normalise({"t": "はい。"}), "はい。%c")

    def test_PS1_과_같은_열쇠가_나온다(self):
        from text.line_key import key

        ps1 = "{c}兵士{c}{n}この上は 国王さまの{n}お部屋になっておる。{c}"
        mine = self.r.normalise({"s": "兵士", "t": "この上は 国王さまの\\nお部屋になっておる。"})
        self.assertEqual(key(mine), key(ps1))


class MemMap(unittest.TestCase):
    """폰트 자리의 전제 — 상수가 바뀌면 12절 판독이 무너진다."""

    def setUp(self):
        import memmap

        self.m = memmap

    def test_첫_뱅크는_256KB다(self):
        self.assertEqual(self.m.FIRST_BANK_SEG * 16, 256 * 1024)
        self.assertEqual(self.m.BANK_STEP_SEG * 16, 128 * 1024)
        self.assertEqual(self.m.PAGE_SEG * 16, 8 * 1024)

    def test_한글이_한_뱅크에_들어간다(self):
        """서브셋을 안 뜨는 근거 — 페이지 열 장이면 완성형 전부가 들어간다."""
        page = self.m.PAGE_SEG * 16
        need = -(-self.m.HANGUL_BYTES // page)
        self.assertLessEqual(need, self.m.PAGES_PER_BANK)
        self.assertEqual(need, 10)
