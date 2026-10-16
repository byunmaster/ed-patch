"""`0x16`(파티 리더별 분기) — 변위 다섯이 재배치를 따라가는가. 원본 없이 도는 합성 모듈.

물린 사고(2026-10-11): 변위 다섯을 참조로 안 잡아 재조립이 스트림을 옮겨도 착지가 그대로였다
(정본 3블록에서 45개 중 40개가 원본과 달랐다). 변위는 **각자 자기 자리 기준**이다.
"""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scene


def module() -> bytes:
    sj = lambda s: s.encode("cp932")  # noqa: E731
    head = bytes.fromhex("43fa") + b"\0\0" + bytes.fromhex("3a7c85e3")  # lea x(pc),a1; movea.w #MSG,a5
    a_at = len(head)
    b_at, c_at = a_at + 64, a_at + 80
    b = bytearray(head)
    b[2:4] = struct.pack(">h", a_at - 2)
    a = sj("あいう") + b"\x16"
    base = a_at + len(sj("あいう")) + 1
    targets = [b_at, c_at, b_at, c_at, b_at]
    a += b"".join(struct.pack(">h", t - (base + 2 * k)) for k, t in enumerate(targets)) + b"\x00"
    b += a.ljust(64, b"\x00")
    b += (sj("かきく") + b"\x00").ljust(16, b"\x00")
    b += sj("さしす") + b"\x00"
    return bytes(b)


class Rel16(unittest.TestCase):
    def test_targets_follow_relocation(self):
        mod = scene.parse_module(module())
        (tok,) = [t for st in mod.streams.values() for t in st.tokens if t.code == 0x16]
        self.assertEqual(tok.ref, scene.MULTI)
        self.assertEqual(len(set(tok.targets)), 2)
        self.assertTrue(all(t in mod.streams for t in tok.targets))
        new = scene.parse_module(scene.reassemble(mod))
        (nt,) = [t for st in new.streams.values() for t in st.tokens if t.code == 0x16]
        # 착지가 옮겨졌고(원본 자리 그대로가 아니다), 같은 스트림 내용을 가리킨다
        self.assertNotEqual(nt.targets, tok.targets)
        old = [mod.streams[t].text() for t in tok.targets]
        self.assertEqual([new.streams[t].text() for t in nt.targets], old)


if __name__ == "__main__":
    unittest.main()
