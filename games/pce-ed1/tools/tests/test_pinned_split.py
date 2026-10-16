"""안쪽 참조(pinned) 조각내기 · 표 꼬리 건너뛰기 · 종료 없는 조각이 자리를 딱 채울 때 — 원본 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import messages as M

SJ = lambda s: s.encode("cp932")


def ptr_setup(addr: int) -> bytes:
    """`LDA #lo; STA $10; LDA #hi; STA $11` — 분할 즉치 포인터(참조로 읽힌다)."""
    return bytes([0xA9, addr & 0xFF, 0x85, 0x10, 0xA9, addr >> 8, 0x85, 0x11])


def block_with_ref(cut_chars: int):
    """코드(포인터 하나) 뒤에 메시지 하나 — 포인터는 메시지의 `cut_chars` 번째 글자를 가리킨다."""
    text = SJ("おはようございます。") + b"\x00"
    head = b"\x4c\x03\xa0"  # 머리 점프(표가 아니다)
    code_len = len(head) + 8 + 1
    start = code_len
    code = head + ptr_setup(M.BASE + start + 2 * cut_chars) + b"\x60"
    return code + text, start, start + len(text)


class Pinned(unittest.TestCase):
    def test_글자_경계_참조는_거기서_조각낸다(self):
        blk, start, end = block_with_ref(3)
        msgs = M.parse(blk)
        self.assertEqual([m.jp for m in msgs], ["おはよ", "うございます。"])
        self.assertFalse(msgs[0].terminated)  # 앞 조각은 종료 없음
        self.assertEqual((msgs[0].start, msgs[0].end, msgs[1].start), (start, start + 6, start + 6))
        self.assertTrue(msgs[1].terminated)
        self.assertFalse(any(m.pinned for m in msgs))

    def test_글자_한가운데_참조는_우연이라_무시한다(self):
        blk, start, end = block_with_ref(3)
        blk = bytearray(blk)
        blk[5] += 1  # 포인터를 한 바이트 옮긴다 → 2바이트 글자 한가운데
        msgs = M.parse(bytes(blk))
        self.assertEqual([m.jp for m in msgs], ["おはようございます。"])

    def test_조각난_메시지를_넣어도_참조_자리는_안_움직인다(self):
        blk, start, end = block_with_ref(3)
        msgs = M.parse(blk)
        new0 = b"\xf0\x24" * 3  # 6B — 자리를 딱 채운다(점프 없이 이어진다)
        new1 = b"\xf0\x25" * 12 + b"\x00"  # 넘친다 → 블록 끝으로
        out = M.splice(blk, [(msgs[0], new0), (msgs[1], new1)])
        self.assertEqual(out[start : start + 6], new0)  # 점프 없이 그대로
        self.assertEqual(out[start + 6 : start + 18], new1[:12])  # 뒤 조각은 참조 자리에서 시작해 들어가는 만큼 쓰고
        self.assertEqual(out[start + 18], M.JUMP)  # 점프로 블록 끝에 잇는다
        self.assertEqual(out[: start], blk[:start])  # 코드(포인터)는 한 바이트도 안 바뀐다

    def test_종료없는_조각이_자리보다_짧으면_점프를_붙인다(self):
        blk, start, end = block_with_ref(3)
        msgs = M.parse(blk)
        out = M.splice(blk, [(msgs[0], b"\xf0\x24")])
        self.assertEqual(out[start : start + 2], b"\xf0\x24")
        self.assertEqual(out[start + 2], M.JUMP)
        self.assertEqual(out[start + 3] | out[start + 4] << 8, M.BASE + start + 6)


class TableTail(unittest.TestCase):
    def test_오름차순_주소_표_끝_워드가_글자로_딸려오지_않는다(self):
        # 표(주소 4워드, 마지막은 우연히 「藤」 93 A1) 뒤에 대본 — 본문은 `抵抗…` 만
        text = SJ("抵抗してもムダだ。") + b"\x06"
        s0 = 0x40
        tbl_at = s0 + 2  # 표가 놓일 자리
        words = [0xA000 + 0x120, 0xA000 + 0x140, 0xA000 + 0x160, 0xA193]
        blk = bytearray(b"\x00" * 0x200)
        blk[0:3] = b"\x4c\x03\xa0"
        for i, w in enumerate(words):
            blk[tbl_at + 2 * i : tbl_at + 2 * i + 2] = w.to_bytes(2, "little")
        start = tbl_at + 2 * 3  # 마지막 워드(93 A1)부터가 「메시지」로 읽히는 자리
        blk[start + 2 : start + 2 + len(text)] = text
        # 표가 가리키는 자리에 메시지 머리 후보가 있어야 한다(끝 워드 = $A193 → 오프셋 0x193)
        blk[0x193 : 0x193 + 6] = SJ("あいう")
        msgs = M.parse(bytes(blk))
        first = [m for m in msgs if m.start < 0x100]
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].start, start + 2)
        self.assertEqual(first[0].jp, "抵抗してもムダだ。")


if __name__ == "__main__":
    unittest.main()
