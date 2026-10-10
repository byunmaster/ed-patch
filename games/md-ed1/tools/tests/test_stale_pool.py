"""낡은 변위(블록 161 꼴) — 문안 풀이 10B 뒤로 밀린 모듈에서 lea 가 풀 머리·토막 머리로 고쳐지고 재조립이 따라가는가.

원본 없이 도는 합성 모듈이다. 실제 블록은 sha1 로 가리키고, 여기선 같은 sha1 표에 합성 모듈을 올려 쓴다.
물린 사고(2026-10-11): 블록 161 의 문안 lea 19곳이 전부 문장 한복판을 가리켜 스트림이 토막(`ﾌ勝ちだ。`)으로 읽혔다.
"""

import hashlib
import re
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scene

SHIFT = 10


def module() -> bytes:
    sj = lambda s: s.encode("cp932")  # noqa: E731
    pool = [
        sj("ルールは簡単だぜ。") + b"\x01" + sj("よく聞けよ。") + b"\x05" + sj("次の話だ。") + b"\x07",
        sj("会心") + b"\x0f\xff\xfc",  # goto 가 글자 한복판(낡음) — +10 이면 아래 「の 一撃」 머리
        sj("痛恨の 一撃 !!") + b"\x07",
        sj("遊びたくなったら いつでも来なよ。") + b"\x00",
    ]
    code_len = 0x40
    base = code_len + 12  # 풀 시작(앞에 rts)
    heads, pos = [], base
    for s in pool:
        heads.append(pos)
        pos += len(s)
    # 코드: lea 4개 — 풀 머리 0 · 1 · 2, 그리고 스트림 0 안 「次の話だ。」(쪽 넘김 뒤 토막 머리)
    inner = heads[0] + len(sj("ルールは簡単だぜ。") + b"\x01" + sj("よく聞けよ。") + b"\x05")
    code = bytearray(code_len)
    targets = [heads[0], heads[1], heads[2], inner]
    for i, t in enumerate(targets):
        ins = 4 + i * 8
        code[ins : ins + 2] = b"\x43\xfa"
        code[ins + 2 : ins + 4] = struct.pack(">h", t - SHIFT - (ins + 2))  # 낡은 변위: 10B 앞
        code[ins + 4 : ins + 8] = b"\x3a\x7c\x85\xe2"
    code[code_len - 2 : code_len] = b"\x4e\x75"
    # goto 의 낡은 변위: 「会心」 뒤 0F 의 인자 = 풀 스트림 2 안 「の」 앞으로 가야 하는 값 − SHIFT
    b = bytearray(bytes(code) + bytes(10) + b"\x4e\x75" + b"".join(pool))
    g = b.index(b"\x0f\xff\xfc")
    want = heads[2] + len(sj("痛恨"))
    b[g + 1 : g + 3] = struct.pack(">h", want - SHIFT - (g + 1))
    return bytes(b)


class StalePool(unittest.TestCase):
    def setUp(self):
        self.raw = module()
        self.saved = dict(scene.STALE_SHIFT)
        scene.STALE_SHIFT[hashlib.sha1(self.raw).hexdigest()] = SHIFT

    def tearDown(self):
        scene.STALE_SHIFT.clear()
        scene.STALE_SHIFT.update(self.saved)

    def test_pool_found(self):
        mod = scene.parse_module(self.raw)
        texts = sorted(st.text() for st in mod.streams.values())
        # 풀 스트림 4 + goto 대상(「の 一撃 !!」) + 한복판 토막(「次の話だ。」)
        self.assertEqual(len(mod.streams), 6)
        self.assertEqual(len(mod.roots), 4)
        self.assertTrue(any(t.startswith("次の話だ。") for t in texts))
        self.assertTrue(any(t.startswith("の 一撃 !!") for t in texts))

    def test_reassemble_keeps_links(self):
        orig = scene.parse_module(self.raw)
        new_bytes = scene.reassemble(orig)
        scene.verify_reassembly(orig, new_bytes)
        new = scene.parse_module(new_bytes, orig)
        strip = lambda m: sorted(re.sub(r"<0f\w+→goto:0x\w+>", "<goto>", st.text()) for st in m.streams.values())  # noqa: E731
        self.assertEqual(strip(new), strip(orig))
        # goto 는 새 자리의 「の 一撃 !!」 로 닿는다
        g = next(t for st in new.streams.values() for t in st.tokens if t.ref == scene.GOTO)
        self.assertEqual(new.streams[g.target].text(), "の 一撃 !!<07|끝>")
        for ins, t in new.roots.items():
            self.assertGreater(t, max(orig.streams))  # 고쳐진 lea 가 새 자리를 가리킨다


if __name__ == "__main__":
    unittest.main()
