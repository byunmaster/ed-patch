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

    def test_청크_밖은_안_본다(self):
        patch_scn.check_no_jump_clobber([(9999, b"", b"xx")], {100: self.JMP})

    def test_주소가_아닌_인자도_잡는다(self):
        """🔴 2026-09-08 에 자를 넓혔다 — 종전엔 「목적지가 창(`0xExxx`)인가」로 걸러서
        `0x16`(길이 11)·`0x0C` 처럼 **주소가 아닌 인자**를 통째로 놓쳤다."""
        with self.assertRaises(SystemExit):
            patch_scn.check_no_jump_clobber([(101, b"", b"xx")], {100: self.DAT})

    def test_종결자_너머는_안_본다(self):
        """뒤로 훑다 종결자·화자 표식을 만나면 멈춘다 — 데이터 속 `0x16` 오탐을 막는다."""
        blob = bytes([0x16, 0x08, 0x0A, 0x06, 0x84, 0x00, 0x00, 0x1E]) + b"ABCD"
        patch_scn.check_no_jump_clobber([(109, b"", b"xx")], {100: blob})

    def test_길이_11_인자를_잡는다(self):
        # ⚠ 채움 바이트는 종결자도 옵코드도 아니어야 한다 — 아니면 훑기가 먼저 멈춘다
        blob = bytes([0x16]) + b"\x80" * 10 + b"ABCD"
        with self.assertRaises(SystemExit):
            patch_scn.check_no_jump_clobber([(105, b"", b"xx")], {100: blob})

    def test_ASM_호출_주소도_본다(self):
        """분기만 보면 `0C`·`15`(ASM 호출)의 주소를 놓친다 — 실측 54자리."""
        asm = bytes([0x15, 0x11, 0xE8]) + b"ABCDEF"
        with self.assertRaises(SystemExit):
            patch_scn.check_no_jump_clobber([(101, b"", b"xx")], {100: asm})


class HeadClobber(unittest.TestCase):
    """빈 화자 `1E 04` 뒤 두 바이트는 인자다 — 덮으면 문안을 읽기도 전에 뻗는다."""

    # … 1E 04 DD C3 <본문>
    BLOB = bytes([0x1E, 0x04, 0xDD, 0xC3]) + "スライム".encode("shift_jis")

    def test_인자_첫바이트를_덮으면_죽는다(self):
        with self.assertRaises(SystemExit):
            patch_scn.check_no_head_clobber([(102, b"", b"xx")], {100: self.BLOB})

    def test_인자_둘째바이트를_덮어도_죽는다(self):
        with self.assertRaises(SystemExit):
            patch_scn.check_no_head_clobber([(103, b"", b"xx")], {100: self.BLOB})

    def test_인자_뒤부터는_괜찮다(self):
        patch_scn.check_no_head_clobber([(104, b"", b"xx")], {100: self.BLOB})

    def test_빈_화자가_아니면_안_본다(self):
        blob = bytes([0x1E, 0x41, 0x04, 0xC3]) + b"ABCD"  # 이름이 든 화자
        patch_scn.check_no_head_clobber([(102, b"", b"xx")], {100: blob})


if __name__ == "__main__":
    unittest.main()
