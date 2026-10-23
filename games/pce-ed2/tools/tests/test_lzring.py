import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import layout
import lz
import lzring
import sim6280

# 복호기 기본 부품(플래그 비트 · 니블 · 초기화)을 같은 주소에 손으로 다시 지어 단다 — 원본 없이 도는 단위 시험이다(실제 롬과의 대조는 에뮬 대조 몫).
PRIMS = {
    0x575A: bytes.fromhex("85328631a90185356 0".replace(" ", "")),
    0x5763: bytes.fromhex("4635900c6635b231e631d002e63285330633 60".replace(" ", "")),
    0x5776: bytes.fromhex("a900d014b231e631d002e6328d8f574a4a4a4aee7757800 7 a9002 90f9c7757 60".replace(" ", "")),
    0x5796: bytes.fromhex("205a579c7757 a9ef8deb579cad57 60".replace(" ", "")),
    0x57AC: bytes.fromhex(
        "a900d031463590 0c6635b231e631d002e63285330633900ab231e631d002e632801cb231e631d002e6328de257"
        "207657 1a1a 8dad57 ad00e0 eee257 cead57 8d00e0 eeeb57 60".replace(" ", "")
    ),
}


def _machine(stream: bytes, base: int = 0x8000):
    b68 = bytearray(8192)
    for a, code in PRIMS.items():
        b68[a - 0x4000 : a - 0x4000 + len(code)] = code
    fc = lzring.fetch_code()
    fo = lzring._fetch_org()
    b68[fo - 0x4000 : fo - 0x4000 + len(fc)] = fc
    b6e = bytearray(8192)
    b6e[lzring.FETCH_JMP : lzring.FETCH_JMP + 3] = lzring.FETCH_JMP_OLD
    ic = lzring.init_code()
    b6e[lzring.INIT_OFF : lzring.INIT_OFF + len(ic)] = ic
    data = bytearray(8192 * 3)
    data[: len(stream)] = stream
    banks = {0x68: b68, 0x6E: b6e, 0x80: data[:8192], 0x81: data[8192:16384], 0x82: data[16384:], 0x87: bytearray(8192)}
    # MPR: 0=I/O 1=RAM 2=0x68 3=0x6E 4~6=데이터 7=링
    mpr = [0xFF, 0xF8, 0x68, 0x6E, 0x80, 0x81, 0x82, 0x87]
    return sim6280.Sim(banks, mpr, bytearray(8192))


def _run_stream(stream: bytes, n: int) -> bytes:
    m = _machine(stream)
    m.x, m.a = 0x00, 0x80  # 포인터 $8000
    m.run(0x6000 + lzring.INIT_OFF)
    out = bytearray()
    for _ in range(n):
        tgt = m.banks[0x6E][lzring.FETCH_JMP + 1] | m.banks[0x6E][lzring.FETCH_JMP + 2] << 8
        m.x, m.y = 0x55, 0x66
        m.run(tgt)
        out.append(m.a)
        assert (m.x, m.y) == (0x55, 0x66), "X·Y 를 건드렸다"
    return bytes(out)


class TestLzring(unittest.TestCase):
    def test_자리에_들어간다(self):
        self.assertLessEqual(len(lzring.init_code()), 69)  # 뱅크 0x6E 패딩 꼬리
        self.assertLessEqual(len(lzring.fetch_code()), 241)

    def test_이음매_원본_바이트가_맞게_짜였다(self):
        self.assertEqual(lzring.INIT_SEAM_OLD, bytes.fromhex("4c9657"))
        self.assertEqual(lzring.FETCH_JMP_OLD, bytes.fromhex("4cac57"))

    def test_512_스트림을_시뮬레이터가_파이썬과_같게_푼다(self):
        rnd = random.Random(7)
        for t in range(40):
            n = rnd.randint(1, 3000)
            base = bytes(rnd.choice(b"abcdefgh\x00\xaa") for _ in range(rnd.randint(1, 60)))
            data = bytes((base[i % len(base)] if rnd.random() < 0.7 else rnd.randrange(256)) for i in range(n))
            enc = lz.encode_opt512(data) + bytes(8)
            self.assertEqual(_run_stream(enc, n), data, t)

    def test_링이_두_쪽을_넘나든다(self):
        # 거리 512 에 가까운 되참조와 쓰기 인덱스의 쪽 넘김(1000B 넘게 쓴다)
        rnd = random.Random(3)
        blk = bytes(rnd.randrange(256) for _ in range(500))
        data = blk + bytes(rnd.randrange(256) for _ in range(40)) + blk + blk[:300]
        enc = lz.encode_opt512(data) + bytes(8)
        self.assertEqual(_run_stream(enc, len(data)), data)

    def test_256_스트림은_원판_경로로_간다(self):
        rnd = random.Random(5)
        data = bytes(rnd.choice(b"abcdefgh\x00") for _ in range(1500))
        enc = lz.encode_opt(data) + bytes(8)
        self.assertEqual(enc[0] & 0x80, 0x80)  # 첫 토큰은 늘 리터럴 — 표식(7C, 최상위 비트 0)과 겹치지 않는다
        m = _machine(enc)
        m.x, m.a = 0x00, 0x80
        m.run(0x6000 + lzring.INIT_OFF)
        self.assertEqual(m.banks[0x6E][lzring.FETCH_JMP + 1 : lzring.FETCH_JMP + 3], bytes([0xAC, 0x57]))

    def test_256_스트림도_같은_초기화를_거쳐_원판_루틴이_푼다(self):
        rnd = random.Random(9)
        data = bytes(rnd.choice(b"abcdefgh\x00") for _ in range(800))
        self.assertEqual(_run_stream(lz.encode_opt(data) + bytes(8), len(data)), data)

    def test_표식_뒤_덩이_길이_경계(self):
        for n in (1, 2, 3, 9, 10, 17, 18):
            data = bytes(range(n)) * 2
            enc = lz.encode_opt512(data) + bytes(8)
            self.assertEqual(_run_stream(enc, len(data)), data, n)


if __name__ == "__main__":
    unittest.main()
