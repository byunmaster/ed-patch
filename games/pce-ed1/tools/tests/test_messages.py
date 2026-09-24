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


if __name__ == "__main__":
    unittest.main()
