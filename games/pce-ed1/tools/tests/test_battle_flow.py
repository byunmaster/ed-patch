"""전투 문구 되쓰기 — 옮기거나 줄여 써도 **종단 뒤 원래 흐름**(`0A`·`02` 이름 자리·다음 문구)으로 돌아와야 한다(10-21).

종단 바이트(`01`·`07` …)는 문장 끝이 아니라 다음 바이트로 이어지는 제어코드다. 합성 블록을 되써서 인터프리터 흉내(`0F` 점프를 따라 글자·제어코드를 모은다)로
원문과 같은 **제어코드 차례**가 나오는지 본다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import battle as B
import font

A = B.LOAD_ADDR


def sj(s: str) -> bytes:
    return s.encode("cp932")


def block() -> bytes:
    # 문구 둘이 `01 0A 02` 로 이어지는 흐름: 「ああああ」 01 0A 02 「いいいい」 07 — 레코드 없는 합성 블록
    return sj("ああああ") + bytes([0x01, 0x0A, 0x02]) + sj("いいいい") + bytes([0x07]) + b"\x00" * 4 + b"\xff" * 4


def walk(d: bytes, at: int) -> list[str]:
    """인터프리터 흉내 — `0F` 는 따라가고, 글자는 `ch`, 제어코드는 16진으로 모은다. `07` 에서 끝."""
    out, i, n = [], at, 0
    while n < 200 and i < len(d):
        n += 1
        c = d[i]
        if c == 0x0F:
            i = (d[i + 1] | d[i + 2] << 8) - A
        elif c >= 0x24:
            out.append("ch")
            i += 2
        else:
            out.append(f"{c:02X}")
            i += 1
            if c == 0x07:
                break
    return out


class Flow(unittest.TestCase):
    def setUp(self):
        self.table, _ = font.build_table(set("은는오리나아가다운하지만"))
        self.d = block()
        self.units = B.msg_units(self.d)
        self.assertEqual(len(self.units), 2)

    def patch(self, kr_a: str, kr_b: str):
        msgs = {B.msg_key(self.units[0]["body"]): kr_a, B.msg_key(self.units[1]["body"]): kr_b}
        data, errs, moved = bytearray(self.d), [], []
        B.patch_msgs(data, msgs, self.table, errs, "t", moved)
        B.check_moved(bytes(data), moved, errs, "t")
        return bytes(data), errs, moved

    def test_원문_흐름_제어코드_차례(self):
        self.assertEqual([x for x in walk(self.d, 0) if x != "ch"], ["01", "0A", "02", "07"])

    def test_자리를_넘겨_옮겨도_종단_뒤로_돌아온다(self):
        data, errs, moved = self.patch("은는오리나아가다운하지만", "나아")  # A: 12자(24B) > 8B 방 → 옮김
        self.assertEqual(errs, [])
        self.assertTrue(any(m["tgt"] is not None for m in moved))
        seq = walk(data, 0)
        self.assertEqual([x for x in seq if x != "ch"], ["01", "0A", "02", "07"])
        self.assertEqual(data[len(sj("ああああ"))], 0x01)  # 종단은 제자리

    def test_짧게_써도_찌꺼기를_안_읽고_종단으로_건너뛴다(self):
        data, errs, moved = self.patch("은는오", "나아")  # A: 3자(6B) < 8B → 앞당긴 종단이 아니라 0F 로 원래 종단 자리로
        self.assertEqual(errs, [])
        seq = walk(data, 0)
        self.assertEqual([x for x in seq if x != "ch"], ["01", "0A", "02", "07"])
        self.assertEqual(seq.count("ch"), 3 + 2)  # 한글 3자 + 둘째 문구 2자 — 원문 가나 찌꺼기 글자가 끼지 않았다

    def test_게이트는_점프를_깨면_실패한다(self):
        data, errs, moved = self.patch("은는오리나아가다운하지만", "나아")
        broken = bytearray(data)
        m = next(m for m in moved if m["tgt"] is not None)
        broken[m["tail_end"]] = 0x00  # 꼬리 끝 0F 를 지운다
        errs2: list[str] = []
        B.check_moved(bytes(broken), moved, errs2, "t")
        self.assertTrue(errs2)


class SimpleAndShort(unittest.TestCase):
    def setUp(self):
        self.table, _ = font.build_table(set("은는오리나아가다운하지만"))

    def test_화자_이름_칸은_점프_없이_제자리에_쓴다(self):
        # `1F 이름 04` — 이름 읽기는 종단까지 글자만 읽어 `0F` 를 못 따라간다(10-21 「규리게스게」)
        d = bytes([0x1F]) + sj("あああああ") + bytes([0x04, 0x01]) + sj("いいい") + bytes([0x05]) + b"\xff" * 4
        us = B.msg_units(d)
        self.assertEqual(us[0]["term"], 4)
        data, errs, moved = bytearray(d), [], []
        B.patch_msgs(data, {B.msg_key(us[0]["body"]): "은는오"}, self.table, errs, "t", moved)
        self.assertEqual((errs, moved), ([], []))
        self.assertNotIn(0x0F, data[: len(d)])  # 점프 없음
        # 종단 04 는 명령 흐름 안이라 **원래 자리**(방 끝)에 두고 앞을 반각 공백으로 채운다 — 앞당기고 0 을 채우면 `00`(끝)에서 멈춰 뒤 대사가 안 나온다(10-21)
        self.assertEqual(data[1 + 10], 0x04)
        self.assertEqual(bytes(data[1 + 6 : 1 + 10]), font.HALF_SPACE * 2)
        self.assertEqual(data[1 + 11], 0x01)  # 뒤 흐름이 그대로

    def test_한두_글자_가나_조각을_단위로_잡는다(self):
        d = bytes([0x02]) + sj("は") + bytes([0x01, 0x0A]) + b"\xff" * 4
        us = B.short_units(d, [])
        self.assertEqual([(u["off"], B.msg_jp(u["body"])) for u in us], [(1, "は")])
        data, errs, moved = bytearray(d), [], []
        B.patch_msgs(data, {B.msg_key(us[0]["body"]): "은/는"}, self.table, errs, "t", moved)
        self.assertEqual(errs, [])
        self.assertEqual(bytes(data[1:3]), font.josa_code("은/는"))


class Positional(unittest.TestCase):
    """같은 원문 조각이 한 블록에 둘 — 열쇠가 같아 문안이 하나뿐인데, 한 자리만 다르게 쓴다(`positional`)."""

    def setUp(self):
        self.table, _ = font.build_table(set("은는오리나아가다운하지만"))
        self.d = sj("ああああ") + bytes([0x01, 0x0A, 0x02]) + sj("ああああ") + bytes([0x01, 0x0A]) + b"\xff" * 4
        self.us = B.msg_units(self.d)
        self.key = B.msg_key(self.us[0]["body"])
        self.assertEqual(len(self.us), 2)
        self.assertEqual(self.key, B.msg_key(self.us[1]["body"]))
        self._orig = B._positional

    def tearDown(self):
        B._positional = self._orig

    def test_그_자리만_다르게_쓴다(self):
        B._positional = lambda: {f"9:0:{self.us[1]['off']:04X}": {"key": self.key, "t": "가다"}}
        data, errs = bytearray(self.d), []
        B.patch_msgs(data, {self.key: "은는오리"}, self.table, errs, "t", None, "9:0")
        self.assertEqual(errs, [])
        a, b = data[self.us[0]["off"] : self.us[0]["off"] + 8], data[self.us[1]["off"] : self.us[1]["off"] + 8]
        self.assertNotEqual(bytes(a[:4]), bytes(b[:4]))  # 첫 자리 「은는」 · 둘째 자리 「가다」

    def test_열쇠가_다르면_빌드가_운다(self):
        B._positional = lambda: {f"9:0:{self.us[1]['off']:04X}": {"key": "0" * 16, "t": "가다"}}
        errs = []
        B.patch_msgs(bytearray(self.d), {self.key: "은는오리"}, self.table, errs, "t", None, "9:0")
        self.assertTrue(errs)


if __name__ == "__main__":
    unittest.main()
