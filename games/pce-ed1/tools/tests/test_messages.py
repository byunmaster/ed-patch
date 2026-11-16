"""씬 메시지 파서 — 분기 주소 가드. 원본 없이 돈다(블록을 손으로 짓는다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import messages as M

SJ = lambda s: s.encode("cp932")


class BranchOperandGuard(unittest.TestCase):
    """🔴 분기 옵코드의 주소 바이트가 글자로 읽혀 메시지 머리가 되면 **진행이 깨진다**.

    거기에 우리 문안을 쓰면 점프가 쓰레기 주소로 간다(화면이 아니라 진행). 씬 6,001 메시지
    중 86곳이 이렇게 걸려 있었다(devlog 09-07 ③, P4 선행 조건으로 미뤄져 있던 것을 09-15
    D2/D3 번역 착수 때 `battle.branch_operands`와 같은 축으로 포팅했다). 합성 데이터로
    **검사기가 정말 보는지** 시험한다.
    """

    # 리틀엔디언 `8D A0` = 전각 한 글자, 뒤에 진짜 SJIS 런(`あ`)이 바로 이어져야
    # SJIS_RUN 의 `{2,}` 조건을 채워 예전 스캐너가 여기서 런을 열었다.
    ADDR = 0xA08D

    def _block(self, op: int) -> bytes:
        """`op <주소>` + 가짜로 이어지는 SJIS 한 글자 + 진짜 화자 메시지 + 주소가 블록 끝에 닿게 패딩."""
        d = bytearray(bytes([op]) + self.ADDR.to_bytes(2, "little"))
        d += SJ("あ")  # 주소 바이트 바로 뒤에 진짜 SJIS 쌍을 붙여 SJIS_RUN 을 무는 미끼로 쓴다
        d += b"\x1f" + SJ("兵士") + b"\x04" + SJ("いうえお") + b"\x00"
        d += b"\0" * (self.ADDR - M.BASE + 2 - len(d))
        return bytes(d)

    def test_operand_that_decodes_as_sjis_is_not_a_message_head(self):
        for op in (0x0F, 0x10, 0x12, 0x15):
            with self.subTest(op=f"{op:02X}"):
                d = self._block(op)
                self.assertEqual(M.branch_operands(d), {1, 2}, "주소 자리를 못 봤다")
                # 가드가 없으면 SJIS_RUN 이 주소 자리(1)에서 런을 연다 — 미끼가 실제로 무는지 확인
                self.assertEqual(next(M.SJIS_RUN.finditer(d)).start(), 1, "시험 자체가 안 걸렸다")
                msgs = M.parse(d)
                heads = [m.start for m in msgs]
                self.assertNotIn(1, heads, f"{op:02X} 의 주소가 메시지 머리가 됐다")
                self.assertTrue(
                    any(m.speaker == "兵士" for m in msgs), "진짜 화자 메시지를 놓쳤다"
                )

    def test_data_0f_outside_block_is_not_treated_as_branch(self):
        """둘째 축 — 주소가 블록 밖이면 분기가 아니다(전투 청크의 `CMP #$0F` 즉치와 같은 부류)."""
        d = b"\xc9\x0f\xb0" + b"\x1f" + SJ("兵士") + b"\x04" + SJ("かきくけこ") + b"\x00"
        self.assertEqual(M.branch_operands(d), set(), "블록 밖 주소를 분기로 오탐했다")
        self.assertTrue(any(m.speaker == "兵士" for m in M.parse(d)))


class Scn000EntryBanner(unittest.TestCase):
    """씬 0(공용 블록 0) — 필드 입장 배너 지명표 46개가 다 번역됐나(마스터 09-27 지적:
    「エルアスタの町」가 그대로였다). 원본 파생물이 없는 트리는 건너뛴다."""

    def _block0(self):
        import containers as C

        try:
            found = C.scan()
        except (OSError, FileNotFoundError):
            return None
        for c in found:
            for b in c["blocks"]:
                if b["id"] == 0:
                    return b["data"]
        return None

    def test_banner_place_names_all_translated(self):
        data = self._block0()
        if data is None:
            self.skipTest("원본 파생물 없음")
        msgs = M.parse(data)
        trs = M.load_translations(0)
        place_msgs = [m for m in msgs if m.key in trs][:46]
        self.assertGreaterEqual(len(place_msgs), 46, "지명표 46개를 다 못 찾았다 — 원문이 바뀌었나")
        untranslated = [m.key for m in place_msgs if M.KANA.search(trs[m.key]["t"])]
        self.assertEqual(untranslated, [], "배너 지명에 일본어가 남았다")


if __name__ == "__main__":
    unittest.main()


class BlankFirstRow(unittest.TestCase):
    """🔴 화자 없는 새 창 앞에 메시지 **밖**으로 선 `01` — 창의 첫 행을 비운다(마스터 10-31 gon 009). `translate.blank_row_patches` 가 그 바이트만
    잡아 옵코드 `18`(인터프리터 점프표 `$6808 RTS`, 아무 일 안 함)로 바꾸고, 화자 머리 뒤 `04 01`(이름 줄 끝)은 두는지 — 합성 블록으로."""

    def test_leading_nl_before_fresh_window_is_neutralised(self):
        import translate as T

        for before in (b"\x07", b"\x00", b"\x00\x05"):  # 문장 끝 · 끝 뒤 페이지 지우기(씬 32 꼴) — 05 홀로는 앞 메시지 안의 쪽 넘김이라 같은 메시지다
            with self.subTest(before=before.hex()):
                d = b"\x1f" + SJ("兵士") + b"\x04" + SJ("かきくけこ") + before + b"\x01" + SJ("あいうえお") + b"\x00"
                p = T.blank_row_patches(d)
                self.assertEqual(p, [(d.index(before) + len(before), b"\x01", bytes([T.NOP_OP]))])
        d = b"\x1f" + SJ("兵士") + b"\x04\x01" + SJ("あいうえお") + b"\x00"  # 화자 머리 뒤 줄바꿈 — 그대로
        self.assertEqual(T.blank_row_patches(d), [])
        d = SJ("かきくけこ") + b"\x10\x00\xa0\x01" + SJ("あいうえお") + b"\x00"  # 이어 쓰는 창(호출 뒤) — 그대로
        self.assertEqual(T.blank_row_patches(d), [])
