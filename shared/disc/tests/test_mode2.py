"""MODE2/2352 Form1 섹터 쓰기 회귀 — **원본 없이 돈다**(합성 섹터).

🔴 지키는 것: **EDC 만 고치고 ECC 를 두는 사고**(`mode1` 테스트와 같은 이유 — 실기에서만 터진다)와
**MODE1 규칙을 PS1 에 쓰는 사고**(EDC 범위·ECC 헤더 처리가 다르다).
"""

import importlib.util
import io
import os
import random
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, ROOT)
from shared.disc import mode1, mode2
from shared.disc.guard import Guard, WriteGuard
from shared.disc.iso9660 import SECTOR, USER_SIZE

U = mode2.USER_OFF


def _sector(lba, payload=b"", form2=False):
    sec = bytearray(SECTOR)
    sec[0:12] = b"\x00" + b"\xff" * 10 + b"\x00"
    sec[12:16] = bytes([0, 2, lba % 75, 0x02])
    sec[16:20] = sec[20:24] = bytes([0, 0, 0x20 if form2 else 0x08, 0])
    body = (
        ((payload * (USER_SIZE // max(1, len(payload)) + 1))[:USER_SIZE])
        if payload
        else bytes(USER_SIZE)
    )
    sec[U : U + USER_SIZE] = body
    if not form2:
        mode2.sector_fix(sec)
    return bytes(sec)


def _image(nsec):
    return io.BytesIO(b"".join(_sector(i, bytes([i & 0xFF, 7])) for i in range(nsec)))


class TestSector(unittest.TestCase):
    def test_멱등(self):
        a = bytearray(_sector(3, b"abc"))
        b = bytearray(a)
        mode2.sector_fix(b)
        self.assertEqual(a, b)

    def test_EDC는_16부터_2071(self):
        sec = bytearray(_sector(3, b"xyz"))
        want = mode1.edc_compute(bytes(sec[16:2072])).to_bytes(4, "little")
        self.assertEqual(bytes(sec[2072:2076]), want)

    def test_헤더는_ECC_계산_뒤_복원된다(self):
        sec = bytearray(_sector(5, b"q"))
        self.assertEqual(bytes(sec[12:16]), bytes([0, 2, 5, 0x02]))

    def test_유저_한_바이트가_패리티를_바꾼다(self):
        a = bytearray(_sector(1, b"A"))
        b = bytearray(a)
        b[U + 100] ^= 0xFF
        mode2.sector_fix(b)
        self.assertNotEqual(a[0x81C:0x930], b[0x81C:0x930])
        self.assertNotEqual(a[2072:2076], b[2072:2076])

    def test_Form2는_대상이_아니다(self):
        with self.assertRaises(AssertionError):
            mode2.sector_fix(bytearray(_sector(2, form2=True)))

    def test_EDC_범위가_MODE1_과_다르다(self):
        """MODE1 은 0~2063, Form1 은 16~2071 — 같은 섹터에 두 규칙을 쓰면 값이 달라야 한다(규격을 섞는 사고)."""
        sec = _sector(4, b"zz")
        self.assertNotEqual(mode1.edc_compute(sec[0:2064]), mode1.edc_compute(sec[16:2072]))


class TestWrite(unittest.TestCase):
    def test_바뀐_섹터만_센다(self):
        f = _image(8)
        n = mode2.write_user_data(f, 2, b"\x42" * 100, label="t")
        self.assertEqual(n, 1)
        f.seek(2 * SECTOR + U)
        self.assertEqual(f.read(100), b"\x42" * 100)
        # EDC/ECC 가 맞게 다시 계산됐다
        f.seek(2 * SECTOR)
        sec = bytearray(f.read(SECTOR))
        again = bytearray(sec)
        mode2.sector_fix(again)
        self.assertEqual(sec, again)

    def test_같은_데이터는_섹터를_안_건드린다(self):
        f = _image(4)
        f.seek(1 * SECTOR + U)
        cur = f.read(USER_SIZE)
        self.assertEqual(mode2.write_user_data(f, 1, cur, label="t"), 0)

    def test_사전조건이_틀리면_쓰기_전에_실패(self):
        f = _image(4)
        before = f.getvalue()
        with self.assertRaises(WriteGuard):
            mode2.write_user_data(f, 1, b"new", label="t", expect=b"nope")
        self.assertEqual(f.getvalue(), before)

    def test_무변경_구간_침범은_실패(self):
        f = _image(4)
        g = Guard()
        g.add(1, USER_SIZE, [("보호", 0, 16, "same")])
        before = f.getvalue()
        with self.assertRaises(WriteGuard):
            mode2.write_user_data(f, 1, b"\xee" * 32, label="침범", guard=g)
        self.assertEqual(f.getvalue(), before)

    def test_섹터를_걸쳐_쓴다(self):
        f = _image(6)
        data = bytes(range(256)) * 12  # 3072B = 1.5 섹터
        self.assertEqual(mode2.write_user_data(f, 2, data, label="t"), 2)
        f.seek(2 * SECTOR)
        got = mode2.read_user_data(f, 2, len(data))
        self.assertEqual(got, data)

    def test_디렉터리_파일크기_LE_BE(self):
        f = _image(4)
        rec = bytearray(USER_SIZE)
        rec[100] = 40  # 레코드 길이
        mode2.write_user_data(f, 1, bytes(rec), label="dir")
        mode2.set_file_size(f, 1, 100, 0x01020304, label="size")
        got = mode2.read_user_data(f, 1, USER_SIZE)
        self.assertEqual(got[110:114], bytes([4, 3, 2, 1]))
        self.assertEqual(got[114:118], bytes([1, 2, 3, 4]))

    def test_selftest_손_안_댄_섹터는_일치(self):
        import tempfile

        f = _image(5)
        with tempfile.NamedTemporaryFile(delete=False) as t:
            t.write(f.getvalue())
        try:
            self.assertEqual(mode2.selftest(t.name, range(5)), [])
        finally:
            os.unlink(t.name)


class TestEquivalenceWithEd3(unittest.TestCase):
    """이전 대응 — ps1-ed3 의 `common.py` 사본과 **같은 바이트**를 내야 옮겨 탈 수 있다(원본 불필요, 파일이 있을 때만)."""

    def test_랜덤_섹터_동치(self):
        path = os.path.join(ROOT, "games", "ps1-ed3", "tools", "common.py")
        if not os.path.exists(path):
            self.skipTest("games/ps1-ed3/tools/common.py 없음")
        spec = importlib.util.spec_from_file_location("ed3_common_ref", path)
        ref = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ref)
        rng = random.Random(7)
        for lba in range(6):
            body = bytes(rng.randrange(256) for _ in range(USER_SIZE))
            new = bytearray(_sector(lba, b"x"))
            new[U : U + USER_SIZE] = body
            mode2.sector_fix(new)
            old = bytearray(_sector(lba, b"x"))
            old[U : U + USER_SIZE] = body
            old[2072:2076] = ref.edc_compute(bytes(old[16:2072])).to_bytes(4, "little")
            ref.ecc_update(old)
            self.assertEqual(new, old, f"lba {lba}")


if __name__ == "__main__":
    unittest.main()
