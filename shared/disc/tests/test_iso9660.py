"""ISO9660 리더 회귀 — **원본 없이 돈다**(합성 이미지를 그 자리에서 만든다).

⚠ 여기서 지키려는 것 하나: `user_off` 를 틀리게 주면 **밀린 바이트를 조용히 읽는 게
아니라 곧바로 운다**. 새턴(MODE1) 도구가 PS1(MODE2 Form1) 이미지를 여는 사고가 실제 위험이다.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from shared.disc import MODE1_USER_OFF, MODE2_FORM1_USER_OFF, Disc, digests
from shared.disc.iso9660 import SECTOR, USER_SIZE


def _dirrec(name: bytes, lba: int, size: int, is_dir: bool) -> bytes:
    """ISO9660 디렉터리 레코드 — 리더가 보는 자리만 채운다(날짜·양끝 엔디언은 생략)."""
    body = bytearray(33 + len(name))
    body[2:6] = lba.to_bytes(4, "little")
    body[10:14] = size.to_bytes(4, "little")
    body[25] = 0x02 if is_dir else 0x00
    body[32] = len(name)
    body[33:] = name
    if len(body) % 2:  # 레코드 길이는 짝수
        body += b"\x00"
    body[0] = len(body)
    return bytes(body)


def _build(path, user_off, payload=b"HELLO-ISO", nsec=26):
    """LBA 16 PVD · 20 루트 · 21 `/SYSTEM` · 22~ 파일."""
    img = bytearray(nsec * SECTOR)

    def put(lba, data):
        base = lba * SECTOR
        img[base + 15] = 0x01  # MODE1 표시(리더는 안 보지만 실물에 맞춘다)
        for i in range(0, len(data), USER_SIZE):
            b = base + (i // USER_SIZE) * SECTOR + user_off
            chunk = data[i : i + USER_SIZE]
            img[b : b + len(chunk)] = chunk

    pvd = bytearray(USER_SIZE)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[156 : 156 + 34] = _dirrec(b"\x00", 20, USER_SIZE, True)
    put(16, bytes(pvd))

    root = _dirrec(b"\x00", 20, USER_SIZE, True) + _dirrec(b"\x01", 20, USER_SIZE, True)
    root += _dirrec(b"SYSTEM", 21, USER_SIZE, True)
    root += _dirrec(b"ROOT.BIN;1", 25, len(payload), False)
    put(20, root)

    sub = _dirrec(b"\x00", 21, USER_SIZE, True) + _dirrec(b"\x01", 20, USER_SIZE, True)
    sub += _dirrec(b"KANJI12.FON;1", 22, len(payload), False)
    put(21, sub)

    put(22, payload)
    put(25, payload)
    with open(path, "wb") as f:
        f.write(img)


class TestIso9660(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.img = os.path.join(self.tmp.name, "fake.bin")

    def tearDown(self):
        self.tmp.cleanup()

    def test_파일목록과_내용(self):
        _build(self.img, MODE1_USER_OFF)
        with Disc(self.img, user_off=MODE1_USER_OFF) as d:
            # LBA 순으로 정렬되고 `;1` 버전 접미어는 걷힌다
            self.assertEqual([n for n, _, _ in d.files()], ["/SYSTEM/KANJI12.FON", "/ROOT.BIN"])
            self.assertEqual(d.read("/SYSTEM/KANJI12.FON"), b"HELLO-ISO")
            self.assertEqual(d.find("/ROOT.BIN")[1:], (25, 9))
            self.assertRaises(KeyError, d.read, "/없다.BIN")

    def test_섹터를_걸치는_파일(self):
        """`read_extent` 가 섹터 경계를 넘어 이어 붙이는가 — 대사 파일은 늘 여러 섹터다."""
        payload = bytes(range(256)) * 24  # 6,144B = 정확히 3섹터
        _build(self.img, MODE1_USER_OFF, payload)
        with Disc(self.img, user_off=MODE1_USER_OFF) as d:
            self.assertEqual(d.read("/SYSTEM/KANJI12.FON"), payload)
            # 낱개 섹터의 유저 데이터만 집어 온다(raw 2352 가 아니다)
            self.assertEqual(d.sector_user(22), payload[:USER_SIZE])

    def test_user_off_가_틀리면_운다(self):
        """🔴 밀린 바이트를 조용히 읽지 않는다 — 새턴 도구로 PS1 이미지를 여는 사고."""
        _build(self.img, MODE1_USER_OFF)
        with Disc(self.img, user_off=MODE2_FORM1_USER_OFF) as d:
            with self.assertRaises(ValueError) as cm:
                d.files()
            self.assertIn("user_off", str(cm.exception))

    def test_digests(self):
        p = os.path.join(self.tmp.name, "x.bin")
        with open(p, "wb") as f:
            f.write(b"abc")
        self.assertEqual(
            digests(p), {"size": 3, "sha1": "a9993e364706816aba3e25717850c26c9cd0d89d"}
        )


if __name__ == "__main__":
    unittest.main()
