"""이벤트 멤버 구조 — 포인터 재계산의 회귀. 원본 없이 돈다.

🔴 밟은 함정: **런 길이를 못 바꾼다고 결론 냈었다.** 총량을 유지한 채 경계만 옮겼더니
   둘째 줄이 「첫 줄의 21번째 코드부터」로 나왔기 때문이다(인게임 실측 2026-09-03).
   실제로는 `0x90 <u16>` 포인터가 있었고, 그걸 다시 계산하니 자유로워졌다.
   ⇒ 「포인터가 안 보인다」는 **없다는 뜻이 아니다.** 스캔의 정렬·구간을 먼저 의심한다.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scriptmap


def member(base, script, segs):
    """합성 멤버 — 헤더(u16 TEXT_BASE) + 스크립트 + 0xFFFF 로 갈린 풀."""
    pool = bytearray()
    starts = []
    for codes in segs:
        starts.append(base + len(pool))
        pool += struct.pack(f"<{len(codes)}H", *codes)
        pool += struct.pack("<H", scriptmap.TERM)
    body = bytearray(struct.pack("<H", base))
    body += script
    if len(body) > base:
        raise AssertionError("스크립트가 TEXT_BASE 를 넘는다")
    body += b"\x00" * (base - len(body))
    return bytes(body) + bytes(pool), starts


def ptr(V):
    """0x90 이스케이프 — 다음 자리를 짝수로 올리므로 여기서는 0x90 뒤에 패딩 한 칸."""
    return bytes([0x90, 0x00]) + struct.pack("<H", V)


class TestScriptMap(unittest.TestCase):
    def setUp(self):
        self.segs = [[0x42, 0x43], [0x50, 0x51, 0x52], [0x60]]
        # 포인터 셋 — 각 조각을 가리킨다 (V = 조각 시작 − TEXT_BASE)
        script = ptr(0) + ptr(6) + ptr(14)
        self.mem, self.starts = member(32, script, self.segs)

    def test_parse(self):
        info = scriptmap.parse(self.mem)
        self.assertEqual(info["base"], 32)
        self.assertEqual(len(info["pointers"]), 3)
        self.assertEqual(info["resolved"], 3)
        self.assertEqual([s for s, _ in info["segments"]], self.starts)

    def test_identity_rebuild_is_byte_equal(self):
        info = scriptmap.parse(self.mem)
        out, unres = scriptmap.rebuild(self.mem, [c for _, c in info["segments"]])
        self.assertEqual(out, self.mem)
        self.assertEqual(unres, 0)

    def test_lengths_may_change_and_pointers_follow(self):
        """🔴 이게 이 모듈의 존재 이유다 — 길이를 바꿔도 포인터가 따라간다."""
        new = [[0x42, 0x43, 0x44, 0x45], [0x50], [0x60, 0x61]]
        out, unres = scriptmap.rebuild(self.mem, new)
        self.assertEqual(unres, 0)
        info = scriptmap.parse(out)
        self.assertEqual([c for _, c in info["segments"]], new)
        self.assertEqual(info["resolved"], 3)
        # 포인터가 실제로 새 조각 시작을 가리키나
        starts = [s for s, _ in info["segments"]]
        self.assertEqual(sorted(t for _, t, _ in info["targets"]), sorted(starts))

    def test_segment_count_must_match(self):
        with self.assertRaises(scriptmap.ScriptError):
            scriptmap.rebuild(self.mem, [[1], [2]])

    def test_odd_bit_is_preserved(self):
        """V 의 최하위 비트는 주소에 안 쓰인다(`V & ~1`) — 그대로 보존한다."""
        script = ptr(0 | 1) + ptr(6) + ptr(14)
        mem, _ = member(32, script, self.segs)
        info = scriptmap.parse(mem)
        self.assertEqual(info["resolved"], 3)
        out, _ = scriptmap.rebuild(mem, [c for _, c in info["segments"]])
        self.assertEqual(scriptmap.pointer_sites(out)[0][1] & 1, 1)


if __name__ == "__main__":
    unittest.main()
