"""MODE1 섹터 쓰기 회귀 — **원본 없이 돈다**(합성 섹터).

🔴 지키는 것: **EDC 만 고치고 ECC 를 두는 사고**. 에뮬레이터는 무시하지만 실기 CD
컨트롤러는 낡은 패리티로 멀쩡한 데이터를 「정정」해 오히려 깨뜨린다 — 화면에 안 보이고
실기에서만 터지는 부류라, 자기검증이 없으면 아무도 못 잡는다.
"""

import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from shared.disc import mode1
from shared.disc.iso9660 import SECTOR, USER_SIZE


def _sector(lba, payload=b""):
    """싱크 + MODE1 헤더 + 유저 데이터로 섹터 하나를 짓고 EDC/ECC 를 채운다."""
    sec = bytearray(SECTOR)
    sec[0:12] = b"\x00" + b"\xff" * 10 + b"\x00"
    m, s, f = lba // (60 * 75), (lba // 75) % 60, lba % 75
    sec[12] = ((m // 10) << 4) | (m % 10)
    sec[13] = ((s // 10) << 4) | (s % 10)
    sec[14] = ((f // 10) << 4) | (f % 10)
    sec[15] = 0x01
    body = (
        (payload * (USER_SIZE // max(1, len(payload)) + 1))[:USER_SIZE]
        if payload
        else bytes(USER_SIZE)
    )
    sec[mode1.USER_OFF : mode1.USER_OFF + USER_SIZE] = body
    mode1.sector_fix(sec)
    return bytes(sec)


class TestSectorFix(unittest.TestCase):
    def test_멱등이다(self):
        """이미 맞는 섹터를 다시 고쳐도 바이트가 그대로여야 한다 — 자기검증의 근거다."""
        orig = _sector(150, b"\x01\x02\x03\x04")
        again = bytearray(orig)
        mode1.sector_fix(again)
        self.assertEqual(bytes(again), orig)

    def test_유저_데이터가_바뀌면_EDC_도_바뀐다(self):
        a = _sector(150, b"\x01")
        b = _sector(150, b"\x02")
        self.assertNotEqual(a[2064:2068], b[2064:2068])

    def test_ECC_도_같이_바뀐다(self):
        """🔴 EDC 만 다르고 P/Q 가 같으면 「고쳤다고 착각」한 것이다."""
        a = _sector(150, b"\x01")
        b = _sector(150, b"\x02")
        self.assertNotEqual(a[0x81C:0x8C8], b[0x81C:0x8C8])  # P
        self.assertNotEqual(a[0x8C8:0x930], b[0x8C8:0x930])  # Q

    def test_MODE1_이_아니면_거부한다(self):
        sec = bytearray(_sector(150))
        sec[15] = 0x02
        self.assertRaises(AssertionError, mode1.sector_fix, sec)

    def test_selftest_는_망가진_섹터를_잡는다(self):
        img = bytearray(_sector(0) + _sector(1, b"\xaa"))
        self.assertEqual(mode1.selftest(io.BytesIO(bytes(img)), lbas=(0, 1)), [])
        img[2064] ^= 0xFF  # EDC 한 바이트 훼손
        bad = mode1.selftest(io.BytesIO(bytes(img)), lbas=(0, 1))
        self.assertEqual([lba for lba, _ in bad], [0])


class TestWrite(unittest.TestCase):
    def setUp(self):
        self.img = bytearray(_sector(0) + _sector(1) + _sector(2))

    def _handle(self):
        return io.BytesIO(self.img)

    def test_쓰고_나면_자기검증을_통과한다(self):
        f = self._handle()
        mode1.write_user_data(f, 1, b"HELLO", label="테스트")
        out = f.getvalue()
        self.assertEqual(mode1.selftest(io.BytesIO(out), lbas=(0, 1, 2)), [])
        self.assertEqual(out[SECTOR + mode1.USER_OFF : SECTOR + mode1.USER_OFF + 5], b"HELLO")

    def test_섹터_경계를_넘어도_전부_고친다(self):
        f = self._handle()
        n = mode1.write_user_data(f, 0, b"\x5a" * (USER_SIZE + 10), label="걸침")
        self.assertEqual(n, 2)
        self.assertEqual(mode1.selftest(io.BytesIO(f.getvalue()), lbas=(0, 1, 2)), [])

    def test_사전조건이_틀리면_안_쓴다(self):
        """⚠ 이게 없으면 「배치가 밀렸는데 그 자리에 그냥 쓰는」 사고를 못 막는다."""
        f = self._handle()
        before = f.getvalue()
        with self.assertRaises(AssertionError):
            mode1.write_user_data(f, 1, b"XX", label="사전조건", expect=b"ZZ")
        self.assertEqual(f.getvalue(), before)

    def test_write_at_은_파일_밖을_거부한다(self):
        f = self._handle()
        with self.assertRaises(AssertionError):
            mode1.write_at(f, 0, 10, 8, b"XXXX", label="범위")

    def test_write_at_은_앞뒤를_보존한다(self):
        f = self._handle()
        mode1.write_user_data(f, 0, bytes(range(256)) * 8, label="바탕")
        mode1.write_at(f, 0, USER_SIZE, 100, b"\xee\xee", label="가운데")
        out = f.getvalue()
        u = out[mode1.USER_OFF : mode1.USER_OFF + USER_SIZE]
        self.assertEqual(u[100:102], b"\xee\xee")
        self.assertEqual(u[99], (bytes(range(256)) * 8)[99])
        self.assertEqual(u[102], (bytes(range(256)) * 8)[102])
        self.assertEqual(mode1.selftest(io.BytesIO(out), lbas=(0,)), [])


if __name__ == "__main__":
    unittest.main()
