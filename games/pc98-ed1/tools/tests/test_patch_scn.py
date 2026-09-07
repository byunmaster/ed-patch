"""재삽입기의 **사전조건**만 본다 — 합성 데이터라 원본이 없어도 돈다.

🔴 규칙을 코드 주석으로 두면 다음 사람이 조건 하나를 더하다 되살린다. 그래서 규칙을
   **결과로 확인하는 함수**를 두고, 그 함수가 **정말 보는지**를 여기서 못 박는다
   (2026-09-07: 초록불이 「없다」가 아니었던 자리를 여러 번 밟았다).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import patch_scn


class JumpClobber(unittest.TestCase):
    """`0F <addr16>` 의 주소 두 바이트에 문안을 쓰면 점프가 어긋난다."""

    # 0F 3B E0 = 창(0xE03B)으로 뛴다. 뒤이어 텍스트.
    JMP = bytes([patch_scn.JUMP, 0x3B, 0xE0]) + b"ABCDEF"
    # 0F C3 95 = 목적지가 창이 아니다 — 전투 청크의 `0F` 는 데이터다(policy).
    DAT = bytes([patch_scn.JUMP, 0xC3, 0x95]) + b"ABCDEF"

    def test_주소_첫바이트를_덮으면_죽는다(self):
        with self.assertRaises(SystemExit):
            patch_scn.check_no_jump_clobber([(101, b"", b"xx")], {100: self.JMP})

    def test_주소_둘째바이트를_덮어도_죽는다(self):
        with self.assertRaises(SystemExit):
            patch_scn.check_no_jump_clobber([(102, b"", b"xx")], {100: self.JMP})

    def test_주소_뒤부터는_괜찮다(self):
        patch_scn.check_no_jump_clobber([(103, b"", b"xx")], {100: self.JMP})

    def test_목적지가_창이_아니면_점프가_아니다(self):
        """전투 청크의 `0F` 까지 잡으면 넣을 수 있는 자리를 헛되이 버린다."""
        patch_scn.check_no_jump_clobber([(101, b"", b"xx")], {100: self.DAT})

    def test_ASM_호출_주소도_본다(self):
        """분기만 보면 `0C`·`15`(ASM 호출)의 주소를 놓친다 — 실측 54자리."""
        asm = bytes([0x15, 0x11, 0xE8]) + b"ABCDEF"
        with self.assertRaises(SystemExit):
            patch_scn.check_no_jump_clobber([(101, b"", b"xx")], {100: asm})

    def test_청크_밖은_안_본다(self):
        patch_scn.check_no_jump_clobber([(9999, b"", b"xx")], {100: self.JMP})


if __name__ == "__main__":
    unittest.main()
