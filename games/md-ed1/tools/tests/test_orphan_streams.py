"""연속 스트림 — 가리키는 참조 없이 앞 스트림(00 종결) 끝에서 이어 읽히는 스트림이 재조립 뒤에도 바로 뒤에 붙어 있는가.

물린 사고(2026-10-11): 블록 85 등 10곳의 일본어 덩이 56런이 번역된 앞 스트림 바로 뒤에 숨어 있었다. `a1` 을 복원하지
않는 문안 호출이 이어 읽는 자리라 lea 가 없고, 재조립이 앞 스트림만 모듈 끝으로 옮기면 이어 읽기가 엉뚱한 스트림으로 샌다.
원본 없이 도는 합성 모듈이다 — 같은 ORPHANS 표에 합성 모듈의 sha1 을 올려 쓴다.
"""

import hashlib
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scene

sj = lambda s: s.encode("cp932")


def module() -> tuple[bytes, list[int]]:
    code = bytearray(0x20)
    # lea A(pc),a1 ; movea.w #$85E2,a5 — 뿌리는 A 하나, 나머지는 참조가 없다
    code[0x1E:0x20] = b"\x4e\x75"
    streams = [
        sj("前の文だぞ。") + b"\x00",  # A: 뿌리 (00 종결)
        b"\x00",  # 연속 1: 글자 없는 끝
        sj("つづきの文だ。") + b"\x06",  # 연속 2 (FLOW)
        sj("さらにつづく。") + b"\x00",  # 연속 3
    ]
    heads, pos = [], 0x20
    for s in streams:
        heads.append(pos)
        pos += len(s)
    code[0:2] = b"\x43\xfa"
    code[2:4] = struct.pack(">h", heads[0] - 2)
    code[4:8] = b"\x3a\x7c\x85\xe2"
    return bytes(code) + b"".join(streams), heads


class Orphans(unittest.TestCase):
    def setUp(self):
        self.raw, self.heads = module()
        self.saved = dict(scene.ORPHANS)
        scene.ORPHANS[hashlib.sha1(self.raw).hexdigest()] = self.heads[1:]

    def tearDown(self):
        scene.ORPHANS.clear()
        scene.ORPHANS.update(self.saved)

    def test_found(self):
        mod = scene.parse_module(self.raw)
        self.assertEqual(sorted(mod.streams), self.heads)
        self.assertEqual(mod.orphans, self.heads[1:])

    def test_stay_adjacent_after_longer_translation(self):
        orig = scene.parse_module(self.raw)
        a = orig.streams[self.heads[0]]
        longer = [
            scene.Token(
                t.off, t.raw + sj("追加テキスト") if t.kind == "text" else t.raw, t.kind, t.code
            )
            for t in a.tokens
        ]
        new_bytes = scene.reassemble(orig, {self.heads[0]: longer})
        scene.verify_reassembly(orig, new_bytes, {self.heads[0]: longer})
        new = scene.parse_module(new_bytes, orig)
        self.assertEqual(len(new.streams), len(orig.streams))
        # 뿌리 스트림 바로 뒤에 연속 스트림 셋이 순서대로 이어진다
        q = next(iter(new.roots.values()))
        got = []
        for _ in range(4):
            st = new.streams[q]
            got.append(st.text())
            q = st.end
        want = [orig.streams[h].text() for h in self.heads]
        self.assertEqual(got[1:], want[1:])
        self.assertIn("追加テキスト", got[0])


if __name__ == "__main__":
    unittest.main()
