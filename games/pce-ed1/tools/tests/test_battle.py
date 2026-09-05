"""전투 레코드 — 이름칸 읽기·되쓰기. 원본 없이 돈다(블록을 손으로 짓는다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import battle as B
import font
import lz

SJ = lambda s: s.encode("cp932")


def rec(name: bytes) -> bytes:
    """64B 레코드 — 앞 48B 는 능력치(안 건드린다), 뒤 16B 가 이름칸."""
    assert len(name) <= B.NAME_LEN
    return bytes(range(48)) + name + b"\0" * (B.NAME_LEN - len(name))


class Names(unittest.TestCase):
    def test_inline(self):
        blk = rec(SJ("スライムＡ") + b"\x06") + b"\xff" * 4 + b"\0" * 60
        self.assertEqual(
            [(r["jp"], r["ind"], r["tail"]) for r in B.records(blk)], [("スライムＡ", None, "")]
        )

    def test_indirect(self):
        """긴 이름은 `23 주소` + 꼬리. 주소는 $C400 기준이다."""
        long_at = 128
        nm = b"\x23" + (B.LOAD_ADDR + long_at).to_bytes(2, "little") + SJ("Ａ") + b"\x06"
        blk = bytearray(rec(nm) + b"\xff" * 4 + b"\0" * 60)
        blk[long_at : long_at + 21] = SJ("キャリオンクロ－ラ－") + b"\x06"
        r = B.records(bytes(blk))
        self.assertEqual(
            [(x["jp"], x["ind"], x["tail"]) for x in r], [("キャリオンクロ－ラ－Ａ", long_at, "Ａ")]
        )

    def test_reject_storage_slot(self):
        """긴 이름을 담아 두는 칸은 레코드가 아니다 — 표가 거기서 끝나야 한다(실측 rel 186 blk9)."""
        blk = rec(SJ("スライムＡ") + b"\x06") + rec(b"\x42\x0a" + SJ("ダークリッチ") + b"\x06")
        self.assertEqual(len(B.records(blk)), 1)

    def test_terminator(self):
        blk = rec(SJ("スライムＡ") + b"\x06") + b"\xff\xff\xff\xff" + b"\0" * 60 + rec(SJ("Ｘ"))
        self.assertEqual(len(B.records(blk)), 1)


class Patch(unittest.TestCase):
    def setUp(self):
        self.table, _ = font.build_table("슬라임캐리온크롤러")

    def test_inline_write(self):
        blk = rec(SJ("スライムＡ") + b"\x06") + b"\xff" * 4 + b"\0" * 60
        blocks = [{"src": B.BASE + 8, "len": len(blk), "packed": 0, "data": blk}]
        errs = []
        # patch_blocks 는 컨테이너를 읽으므로 여기선 같은 규칙을 직접 확인한다
        enc = font.encode("슬라임Ａ", self.table) + b"\x06"
        self.assertLessEqual(len(enc), B.NAME_LEN)
        out = bytearray(blk)
        out[B.NAME_OFF : B.NAME_OFF + B.NAME_LEN] = enc + b"\0" * (B.NAME_LEN - len(enc))
        blocks[0]["data"] = bytes(out)
        # 다시 깔고 풀면 같은 바이트여야 한다
        cont = B.pack(blocks)
        dl = (cont[0] | cont[1] << 8) - B.BASE
        src = cont[0] | cont[1] << 8
        ln = cont[2] | cont[3] << 8
        self.assertEqual(dl, 4)
        got, _ = lz.decode(cont[src - B.BASE :], ln)
        self.assertEqual(got, bytes(out))

    def test_pack_roundtrip(self):
        blocks = [
            {"data": bytes(range(256)) * 3},
            {"data": SJ("スライムがあらわれた。") * 4},
        ]
        cont = B.pack(blocks)
        dl = (cont[0] | cont[1] << 8) - B.BASE
        self.assertEqual(dl, 8)
        for i, b in enumerate(blocks):
            src = cont[i * 4] | cont[i * 4 + 1] << 8
            ln = cont[i * 4 + 2] | cont[i * 4 + 3] << 8
            got, _ = lz.decode(cont[src - B.BASE :], ln)
            self.assertEqual(got, b["data"])


if __name__ == "__main__":
    unittest.main()
