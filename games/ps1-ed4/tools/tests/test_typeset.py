"""조판 회귀 — **원본 없이 돈다**. 🔴 지키는 것: 줄은 24칸 이하 · 한 쪽은 3줄 한도(넘치는 글은 화면에서 조용히 사라진다) · 패딩이 엔진 접힘과 우리 줄 경계를 맞춘다."""

import struct
import unittest

import _path  # noqa: F401
import choice
import typeset

from shared.ps1 import gmf_script as sm

LONG = "시스템 보레 방금 정시 데터 공격 레벨 아니 어서 입도 시스템 보레 시스 방금 정시 데터 공격 레벨 아니 어서 입도"


def flow_member(n_lines, flows):
    """표 규격 합성 멤버 — `0F <색인> <흐름>` 이 4바이트 간격으로 이어진다(`flows` 는 줄마다의 뒤 바이트)."""
    script = b"\x00" + b"".join(
        b"\x0f" + struct.pack("<H", i) + bytes([flows[i]]) for i in range(n_lines)
    )
    if len(script) % 2:
        script += b"\x00"
    base = 2 + len(script)
    strings = [[0x40 + i] for i in range(n_lines)]
    pool, tbl = bytearray(), []
    for s in strings:
        tbl.append(n_lines * 2 + len(pool))
        pool += struct.pack(f"<{len(s)}H", *s) + struct.pack("<H", 0xFFFF)
    return struct.pack("<H", base) + script + struct.pack(f"<{n_lines}H", *tbl) + bytes(pool)


class TestRows(unittest.TestCase):
    def test_줄은_24칸_이하_어절_단위(self):
        for row in typeset.rows(LONG):
            self.assertLessEqual(len(row), 24)
            self.assertFalse(row.startswith(" ") or row.endswith(" "))
        self.assertEqual("".join(" ".join(typeset.rows(LONG)).split()), "".join(LONG.split()))

    def test_넘는_낱말은_운다(self):
        with self.assertRaises(typeset.TypesetError):
            typeset.rows("가" * 30)


class TestPad(unittest.TestCase):
    def test_마지막_줄_말고는_24칸으로_채운다(self):
        s = typeset.pad_rows(["가나", "다라"])
        self.assertEqual(len(s), 24 + 2)
        self.assertEqual(s[:2], "가나")
        self.assertEqual(s[2:24], " " * 22)
        self.assertEqual(s[24:], "다라")

    def test_엔진_접힘과_줄_경계가_같다(self):
        """엔진은 24글자째에서 접는다 — 패딩한 문자열을 24씩 자르면 우리 줄이 나와야 한다."""
        rws = typeset.rows(LONG)
        s = typeset.pad_rows(rws)
        folded = [s[i : i + 24].rstrip() for i in range(0, len(s), 24)]
        self.assertEqual(folded, rws)


class TestPage(unittest.TestCase):
    def test_첫_조각에_몰고_나머지는_비운다(self):
        segs = typeset.page_segments(["시스템 보레", "방금 정시"], 3)
        self.assertEqual(len(segs), 3)
        self.assertEqual(segs[1:], ["", ""])
        self.assertEqual(segs[0].replace(" ", ""), "시스템보레방금정시")

    def test_쪽_한도_3줄을_넘으면_운다(self):
        with self.assertRaises(typeset.TypesetError):
            typeset.page_segments([LONG + " " + LONG], 1)

    def test_빈_문장은_빈_조각(self):
        self.assertEqual(typeset.page_segments(["", " "], 2), ["", ""])


class TestPageLimit(unittest.TestCase):
    """🔴 줄이 사라질 수 있는 쪽은 실패 — 한 조각 안 접힌 줄이 3줄을 넘거나 쪽 도중에 걸치는 경우."""

    def test_조각마다_한_줄이면_네_줄이어도_쪽이_자동으로_넘어간다(self):
        m = flow_member(4, [1, 1, 1, 0])
        self.assertEqual(typeset.over_limit_pages(m, {0: 24, 1: 24, 2: 24, 3: 24}), [])

    def test_한_조각이_4줄이면_걸린다(self):
        m = flow_member(1, [0])
        self.assertEqual(typeset.over_limit_pages(m, {0: 73}), [([0], 0)])

    def test_쪽_도중에_걸치면_걸린다(self):
        m = flow_member(3, [1, 1, 0])
        self.assertEqual(
            typeset.over_limit_pages(m, {0: 30, 1: 30, 2: 24}), [([0, 1, 2], 1)]
        )  # row2 에서 2줄 → 4줄째 걸침
        self.assertEqual(
            typeset.over_limit_pages(m, {0: 24, 1: 30, 2: 24}), []
        )  # row1 + 2줄 = 3줄 딱 맞고 다음 조각은 새 쪽

    def test_한도_안은_통과(self):
        m = flow_member(3, [1, 1, 0])
        self.assertEqual(
            typeset.over_limit_pages(m, {0: 72, 1: 0, 2: 0}), []
        )  # 3줄 한 조각 + 빈 꼬리

    def test_빈_조각은_0줄(self):
        m = flow_member(2, [1, 0])
        self.assertEqual(typeset.over_limit_pages(m, {0: 0, 1: 24}), [])


class TestLineLimits(unittest.TestCase):
    def test_줄_한도_둘_글리프와_픽셀(self):
        text = "아니 어서 입도 시스템 보레 시스 방금 정시 데터 공격 레벨 12.5 아니 어서 입도"
        for row in typeset.rows(text):
            self.assertLessEqual(len(row), typeset.COLS)
            self.assertLessEqual(typeset.px_width(row), typeset.LINE_PX)

    def test_반각은_6px(self):
        self.assertEqual(typeset.px_width("가 1."), 12 + 6 + 6 + 6)

    def test_공백은_안_지운다(self):
        self.assertEqual(typeset.STRIP_AFTER, "")


def stream_member(after):
    """표 규격 합성 멤버 — VM `0F` 뒤에 출력 하나씩, 출력 `i` 뒤에 `after[i]` 바이트열(마지막은 `00` 으로 닫는다)."""
    buf = bytearray(b"\x0f")  # 오프셋 2 = VM 블록 시작
    for i, ops in enumerate(after):
        buf.append(0x0F)
        if (2 + len(buf)) & 1:
            buf.append(0)
        buf += struct.pack("<H", i) + ops
    n = len(after)
    body = bytes(buf) + b"\x00" * (len(buf) & 1)
    base = 2 + len(body)
    pool, tbl = bytearray(), []
    for i in range(n):
        tbl.append(n * 2 + len(pool))
        pool += struct.pack("<2H", 0x40 + i, 0xFFFF)
    return struct.pack("<H", base) + body + struct.pack(f"<{n}H", *tbl) + bytes(pool)


class TestPageSegments(unittest.TestCase):
    def test_줄이_조각보다_적으면_조각마다_한_줄_뒤는_빈_조각(self):
        out = typeset.page_segments(
            ["시스템 보레 방금 정시", "데이터 공격 레벨 아니 어서 입도 시스템"], 4
        )
        self.assertEqual(len(out), 4)
        self.assertTrue(all(len(x) <= typeset.COLS for x in out))
        self.assertEqual(out[3], "")

    def test_줄이_조각보다_많으면_남는_줄은_마지막_조각에_패딩으로(self):
        out = typeset.page_segments([LONG], 1)
        self.assertEqual(len(out), 1)
        self.assertGreater(len(out[0]), typeset.COLS)
        self.assertEqual(typeset.rows(out[0].replace(" " * 3, " ")) is not None, True)


class TestRigid(unittest.TestCase):
    def test_끼움_연산이_있으면_토막을_가르고_둘_다_rigid(self):
        # 0 -06(이름 삽입)-> 1 -01-> 2 -0106(줄바꿈 뒤 이름 삽입)-> 3 -00
        m = stream_member([b"\x06", b"\x01", b"\x01\x06", b"\x00"])
        w = typeset.windows(m)
        self.assertEqual([list(r) for r in w[0]], [[0], [1, 2], [3]])
        self.assertEqual([r.rigid for r in w[0]], [True, True, True])

    def test_01_02_뿐이면_합칠_수_있다(self):
        m = stream_member([b"\x01", b"\x02", b"\x00"])
        w = typeset.windows(m)
        self.assertEqual([list(r) for r in w[0]], [[0, 1], [2]])
        self.assertFalse(any(r.rigid for r in w[0]))

    def test_rigid_는_조각마다_한_줄이다(self):
        self.assertEqual(
            typeset.rigid_segments(["어빈은 ", "을(를) 얻었다."]), ["어빈은 ", "을(를) 얻었다."]
        )
        with self.assertRaises(typeset.TypesetError):
            typeset.rigid_segments([LONG])


class TestWindows(unittest.TestCase):
    def test_01은_같은_쪽_02는_쪽_넘김_그_밖은_메시지_끝(self):
        # 줄 0 -01-> 1 -02-> 2 -00(끝)-> 3 -01-> 4 -00
        m = flow_member(5, [1, 2, 0, 1, 0])
        self.assertEqual(sm.layout(m), sm.LAYOUT_TABLE)
        self.assertEqual(typeset.windows(m), [[[0, 1], [2]], [[3, 4]]])


if __name__ == "__main__":
    unittest.main()


class TestBreakChoice(unittest.TestCase):
    """줄 끊는 자리 고르기 — 같은 줄 수 안에서 문장 끝 > 쉼표 > 연결어미, 쪽 수 불변."""

    def test_문장_끝에서_끊는다(self):
        # 가짜 문장 — 탐욕 줄바꿈이면 「…할 / 일은」 처럼 문장 한복판이 갈린다
        t = "가나다라마바사 아자차카타파하. 거너더러머버서어 저처커터퍼 허고노도 모보소오."
        r = typeset.rows(t)
        self.assertEqual(r[0].split(" ")[-1][-1], ".")

    def test_줄_수는_늘지_않는다(self):
        t = "가나다라마바사 아자차카타파하. 거너더러머버서어 저처커터퍼 허고노도 모보소오. " * 2
        orig = typeset._refine
        try:
            typeset._refine = lambda text, out, cols: out
            base = typeset.rows(t)
        finally:
            typeset._refine = orig
        self.assertEqual(len(typeset.rows(t)), len(base))

    def test_감탄사_쉼표_뒤는_안_끊는다(self):
        self.assertGreater(typeset._break_cost("", "오,", "가나다"), typeset.COST_PLAIN)


class TestChoiceCols(unittest.TestCase):
    """선택지 창 열 — 가장 긴 선택지의 실제 폭(+엔진 자르기 18px)에 맞춘다."""

    def _mem(self, cols, idxs):
        # 앞 패딩 + `3B a 열 줄` + 선택지 `0F 색인 흐름`(색인은 짝수 자리)
        b = bytearray(b"\x00\x00" + bytes([choice.OP, 4, cols, len(idxs), 0]))
        for i in idxs:
            b += bytes([choice.TEXT]) + struct.pack("<H", i) + b"\x01"
        b += b"\x00" * 4
        return bytes(b)

    def test_넓힌다(self):
        mem = self._mem(4, [0, 1])
        found = choice.scan(mem, len(mem), 2)
        self.assertEqual([(f[1], f[2], f[3]) for f in found], [(4, 2, [0, 1])])
        out, log = choice.patch_cols(mem, len(mem), [[1] * 5, [1] * 3], fit=True)
        self.assertEqual(out[found[0][0] + 2], 6)  # (60+6)/12 올림
        self.assertEqual(log[0][1:], (4, 6))

    def test_줄인다(self):
        mem = self._mem(8, [0, 1])
        out, log = choice.patch_cols(mem, len(mem), [[1] * 3, [1] * 2], fit=True)
        self.assertEqual(out[choice.scan(mem, len(mem), 2)[0][0] + 2], 4)  # (36+6)/12 올림
        self.assertEqual(log[0][1:], (8, 4))

    def test_게이트_좁음_넓음을_잡는다(self):
        segs = [[1] * 5, [1] * 3]
        m0 = self._mem(4, [0, 1])
        ok, _ = choice.patch_cols(m0, len(m0), segs, fit=True)
        self.assertEqual(choice.verify(ok, len(ok), segs), [])
        narrow = self._mem(4, [0, 1])
        self.assertTrue(choice.verify(narrow, len(narrow), segs))
        wide = bytearray(ok)
        wide[choice.scan(ok, len(ok), 2)[0][0] + 2] = 15
        self.assertTrue(choice.verify(bytes(wide), len(wide), segs))

    def test_옛_규칙은_넓히기만_한다(self):
        wide = self._mem(8, [0, 1])
        self.assertEqual(choice.patch_cols(wide, len(wide), [[1] * 3, [1] * 2], fit=False)[0], wide)
        narrow = self._mem(4, [0, 1])
        _, log = choice.patch_cols(narrow, len(narrow), [[1] * 5, [1] * 3], fit=False)
        self.assertEqual(log[0][1:], (4, 6))  # 코드 수 5 + 여백 1

    def test_반각은_절반으로_센다(self):
        self.assertEqual(choice.need_cols([1, 1, 7, 1, 1], frozenset({7})), 5)  # 12*4+6+6=60 → 5
        self.assertEqual(choice.need_cols([1] * 40), choice.MAX_COLS)


class TestRule216(unittest.TestCase):
    """규칙 2-16 — 절째 내리기 · 쪽 끝 한 어절 고아 · 띄어 쓴 고유명사 한 줄 · 보조용언 자리 쪽 끊기."""

    def test_절째_내린다(self):
        # 「…테니까 아저씨를」에서 끊으면 절(아저씨를 찾아 주세요.)이 갈린다 → 절째 다음 줄로
        out = typeset._rules(["사례는 얀크 아저씨가 낼 테니까 아저씨를", "찾아 주세요."], 24)
        self.assertEqual(out, ["사례는 얀크 아저씨가 낼 테니까", "아저씨를 찾아 주세요."])

    def test_쪽_끝_한_어절_고아는_앞_낱말을_내린다(self):
        lines = ["가나다라마바사 아자차카타파", "하나둘셋넷다섯 여섯일곱여덟", "아홉열", "마지막줄입니다"]
        out = typeset._rules(["가나다라마바사 아자차카타파", "하나둘셋넷다섯 여섯일곱여덟", "마바사 아홉"] + ["끝."], 24)
        self.assertEqual(len(out), 4)
        self.assertNotEqual(out[2].count(" "), 0)
        del lines

    def test_띄어_쓴_고유명사는_안_가른다(self):
        self.assertIn(1, typeset._glued(["한", "마검", "크발을", "들었다"]) | {1})
        self.assertEqual(typeset._glued(["마검", "크발을", "들었다"]), {1})

    def test_보조용언_자리_쪽_끊기_금지(self):
        l1 = ["가나다라마바사 아자차카타파하", "거너더러머버서어 저처커터퍼허", "고노도로모보소아 이것 읽어", "주세요 부탁이에요."]
        out = typeset._rules(l1, 24)
        self.assertFalse(out[2].endswith("읽어"))


class TestRegressions(unittest.TestCase):
    def test_새_나쁜_끊김을_센다(self):
        # 「이런 / 물건이」 — 관형사 고아가 새로 생긴 꼴
        self.assertGreaterEqual(typeset.regressions(["어떤 사람이 있다는", "소문이다."], ["어떤", "사람이 있다는 소문이다."]), 1)

    def test_같은_끊김이면_0(self):
        a = ["가나다라마바 사아자차카", "타파하."]
        self.assertEqual(typeset.regressions(a, list(a)), 0)

    def test_문장이_새로_갈리면_센다(self):
        old = ["그건 좋다. 가나다 라마바.", "사아자."]
        new = ["그건 좋다. 가나다", "라마바. 사아자."]
        self.assertGreaterEqual(typeset.regressions(old, new), 1)
