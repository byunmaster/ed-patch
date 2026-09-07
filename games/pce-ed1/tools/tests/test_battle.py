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


class Messages(unittest.TestCase):
    def blk(self, tail: bytes) -> bytes:
        """레코드 하나 + 종단 + 꼬리(코드·문구)."""
        return rec(SJ("スライムＡ") + b"\x06") + b"\xff\xff\xff\xff" + b"\0" * 60 + tail

    def test_문구_범위와_종단(self):
        d = self.blk(SJ("スライムが現れた。") + b"\x07")
        u = B.msg_units(d)
        self.assertEqual(len(u), 1)
        self.assertEqual(B.render(u[0]["body"]), "スライムが現れた。")
        self.assertEqual(u[0]["term"], 0x07)
        self.assertEqual(u[0]["room"], len(SJ("スライムが現れた。")) + 1)

    def test_낀_제어코드는_먹고_흐름_옵코드는_끊는다(self):
        """🔴 `0F` 는 뒤에 주소 2B 를 달고 다닌다 — 글자로 먹으면 되쓸 때 점프 주소를 덮는다."""
        d = self.blk(SJ("あいう") + b"\x01" + SJ("えお") + b"\x0f\x34\xc5" + SJ("かきく") + b"\x07")
        got = [B.render(u["body"]) for u in B.msg_units(d)]
        self.assertEqual(got, ["あいう{01}えお", "かきく"])

    def test_포인터_표는_글자가_아니다(self):
        """`40 C5 46 C5 …` 는 유효한 리드/트레일이지만 SJIS 로 안 풀린다 — 코드가 문구에 안 섞여야 한다."""
        d = self.blk(b"\x40\xc5\x46\xc5\x47\xc5\x49\xc5" + SJ("あいう") + b"\x07")
        got = [B.render(u["body"]) for u in B.msg_units(d)]
        self.assertEqual(got, ["あいう"])

    def test_참조가_조각을_끊는다(self):
        """코드가 덩이 중간을 가리키면 공유 조각이다 — 거기서 갈라야 문안이 남의 자리로 안 샌다."""
        body = SJ("あいう") + b"\x01" + SJ("えおか") + b"\x07"
        tail = b"\xa9\x00\x85\x20\xa9\x00\x85\x21"  # 자리표시자(뒤에서 주소를 채운다)
        d = bytearray(self.blk(body + tail))
        start = len(B.records(bytes(d))) * B.REC
        off = d.index(body, start)
        at = d.index(tail, start)
        mid = off + 7  # 「えお」 앞(あいう 6B + 개행 1B)
        d[at + 1] = (B.LOAD_ADDR + mid) & 0xFF
        d[at + 5] = (B.LOAD_ADDR + mid) >> 8
        got = [B.render(u["body"]) for u in B.msg_units(bytes(d))]
        self.assertEqual(got, ["あいう{01}", "えおか"])


class BranchOperandGuard(unittest.TestCase):
    """🔴 분기 옵코드의 주소 바이트가 글자로 읽혀 런 머리가 되면 **진행이 깨진다**.

    거기에 우리 문안을 쓰면 점프가 쓰레기 주소로 간다(화면이 아니라 진행). pc98 이 같은
    자리에서 물렸다(중계 2026-09-07). 합성 데이터로 **검사기가 정말 보는지** 시험한다.
    """

    # $C48D → 리틀엔디언 `8D C4` = 전각 「再」. 예전 스캐너는 바로 여기서 런을 열었다.
    ADDR = 0xC48D

    def _block(self, op: int) -> bytes:
        """레코드 0개(`FF` 로 디렉터리 종료) + `op <주소>` + 텍스트 + 주소가 닿게 패딩."""
        d = bytearray(b"\xff\x00" + bytes([op]) + self.ADDR.to_bytes(2, "little"))
        d += SJ("あいうえお") + b"\x00"
        d += b"\0" * (self.ADDR - B.LOAD_ADDR + 2 - len(d))
        return bytes(d)

    def test_operand_that_decodes_as_sjis_is_not_a_run_head(self):
        for op in (0x0F, 0x10, 0x12, 0x15):
            with self.subTest(op=f"{op:02X}"):
                d = self._block(op)
                self.assertEqual(B.branch_operands(d), {3, 4}, "주소 자리를 못 봤다")
                heads = [a for a, _b, _t in B.text_runs(d, 0)]
                self.assertNotIn(3, heads, f"{op:02X} 의 주소가 런 머리가 됐다")
                self.assertIn(5, heads, "진짜 텍스트 런을 놓쳤다")

    def test_data_0f_outside_block_is_not_treated_as_branch(self):
        """둘째 축 — 주소가 블록 밖이면 분기가 아니다(전투 청크의 `CMP #$0F` 즉치를 지킨다)."""
        d = b"\xff\x00\xc9\x0f\xb0" + SJ("かきくけこ") + b"\x00"
        self.assertEqual(B.branch_operands(d), set(), "블록 밖 주소를 분기로 오탐했다")
        self.assertIn(5, [a for a, _b, _t in B.text_runs(d, 0)])
