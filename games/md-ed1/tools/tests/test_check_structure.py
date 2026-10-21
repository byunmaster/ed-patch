"""구조 대조 검사가 **실제로 우는가** — 일부러 망가뜨린 가짜 모듈(원본 바이트 아님)로 본다(마스터 10-22).

모듈 = `lea d16(pc),a1; movea.w #MSG,a5` 뿌리 하나 + 이어 붙은 스트림 둘(끝 코드 06 사슬) — 글자는 전부 가짜 SJIS(「あ」「い」…).
"""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_structure as cs
import scene

LEA = b"\x43\xfa"
MSG = b"\x3a\x7c\x85\xe3"  # movea.w #$85E3,a5 — scene.MSG_IDS 에 든 문안 뿌리 표지


def module(stream_a: bytes, stream_b: bytes, extra: bytes = b"") -> bytes:
    """뿌리 lea 둘(A · B) + 스트림 A 바로 뒤에 B — A 의 끝 코드 06 뒤로 B 가 물리적으로 이어진다."""
    ent = len(LEA) + 2 + len(MSG)  # lea d16 + movea.w
    head_len = 2 * ent + 2  # + rts
    a_at = head_len
    b_at = a_at + len(stream_a)
    head = (
        LEA + struct.pack(">h", a_at - 2) + MSG
        + LEA + struct.pack(">h", b_at - (ent + 2)) + MSG
        + b"\x4e\x75"
    )
    assert len(head) == head_len
    return head + stream_a + stream_b + extra


A = b"\x82\xa0\x01\x82\xa2\x06"  # あ <01> い <06> — 끝 코드 06 → 다음 스트림이 물리적으로 이어진다
B = b"\x82\xa4\x82\xa6\x00"  # う え <00>


class CheckStructure(unittest.TestCase):
    def errs(self, orig: bytes, new: bytes):
        return cs.compare_module(orig, new)[0]

    def test_same_is_clean(self):
        m = module(A, B)
        self.assertEqual(self.errs(m, m), [])

    def test_reassembled_with_longer_text_and_page_break_is_clean(self):
        mod = scene.parse_module(module(A, B))
        sa = next(iter(sorted(mod.streams)))
        longer = [
            scene.Token(0, b"\x82\xa0\x82\xa0\x82\xa0", "text"),
            scene.Token(0, b"\x05", "ctl", 0x05),  # 쪽 넘김 추가 — 허용
            scene.Token(0, b"\x82\xa2", "text"),
            scene.Token(0, b"\x06", "end", 0x06),
        ]
        new = scene.reassemble(mod, {sa: longer})
        self.assertEqual(self.errs(module(A, B), new), [])

    def test_changed_control_byte_is_caught(self):
        bad = module(A[:-1] + b"\x07", B)  # 끝 코드 06 → 07
        self.assertTrue(self.errs(module(A, B), bad))

    def test_padding_between_chained_streams_is_caught(self):
        # ss-ed3 10-21 — 사슬 사이에 채움(FF FF)을 끼우면 이어 읽기가 끊긴다
        bad = module(A + b"\xff\xff", B)
        self.assertTrue(self.errs(module(A, B), bad))

    def test_text_dropped_from_chained_stream_is_caught(self):
        bad = module(A, b"\x00")  # B 의 글이 사라졌다
        self.assertTrue(self.errs(module(A, B), bad))


class StubAndHookRules(unittest.TestCase):
    """전투·시스템 메시지·자막 짝짓기 규칙 — pce-ed1 이 겪은 오진(**원본 본문 안의 `0F` 옵코드를 우리 이음 점프로 착각**)을 막는다."""

    def test_follow_stub_ignores_original_goto(self):
        orig = b"\x00" + b"\x0f\x00\x05" + b"\x00" * 8
        # 원본에도 같은 자리에 0F goto 가 있다 → 우리가 만든 스텁이 아니므로 따라가지 않는다
        self.assertEqual(cs._follow_stub(orig, orig, 1), 1)

    def test_follow_stub_follows_our_stub_only(self):
        orig = b"\x00" + b"\x82\xa0\x00" + b"\x00" * 8  # 원본 본문(글자)
        new = bytearray(orig)
        new[1:4] = b"\x0f\x00\x05"  # 우리가 본문을 옮기고 남긴 스텁 → 1+1+5
        self.assertEqual(cs._follow_stub(orig, bytes(new), 1), 7)

    def test_mid_body_goto_opcode_is_not_a_stub(self):
        orig = b"\x82\xa0\x0f\x00\x05\x00" + b"\x00" * 8  # 스트림 한복판의 goto
        self.assertEqual(cs._follow_stub(orig, orig, 0), 0)

    def test_particle_replaced_by_josa_hook_is_allowed(self):
        so = scene.parse_stream(b"\x0e\x82\xcd\x07", 0)  # <0e> は <07>
        sn = scene.parse_stream(b"\x0e\xec\x00\x07", 0)  # <0e> <ec00> <07>
        self.assertIsNone(cs._same(so, sn, "시스템", 0, b"", b""))

    def test_text_vanishing_without_hook_is_caught(self):
        so = scene.parse_stream(b"\x82\xa0\x82\xa2\x82\xa4\x82\xa6\x82\xa8\x07", 0)
        sn = scene.parse_stream(b"\x07", 0)
        self.assertIsNotNone(cs._same(so, sn, "시스템", 0, b"", b""))

    def test_must_adjoin_rule(self):
        end06 = scene.parse_stream(b"\x82\xa0\x06", 0)
        end07 = scene.parse_stream(b"\x82\xa0\x07", 0)
        self.assertTrue(cs._must_adjoin(end06, True))  # 06 은 값을 찍고 이어 읽는다
        self.assertTrue(cs._must_adjoin(end07, False))  # 참조 없는 사슬 꼬리
        self.assertFalse(cs._must_adjoin(end07, True))  # 07 뒤 스트림이 자기 참조를 가지면 이웃일 뿐
        self.assertFalse(cs._must_adjoin(end06, True, six=False))  # 전투: 06 뒤라도 다음 줄이 자기 lea 를 가지면 이웃일 뿐
        self.assertTrue(cs._must_adjoin(end06, False, six=False))  # 참조 없는 꼬리는 06 이든 어디든 바로 붙어야 한다


if __name__ == "__main__":
    unittest.main()
