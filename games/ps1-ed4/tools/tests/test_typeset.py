"""조판 회귀 — **원본 없이 돈다**. 🔴 지키는 것: 줄은 24칸 이하 · 한 쪽은 3줄 한도(넘치는 글은 화면에서 조용히 사라진다) · 패딩이 엔진 접힘과 우리 줄 경계를 맞춘다."""

import struct
import unittest

import _path  # noqa: F401
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
