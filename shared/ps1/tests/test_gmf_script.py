"""대본 컨테이너 파서 동치 — ps1-ed3 `scriptmap.py` 와 **같은 결과**를 내야 옮겨 탈 수 있다(원본 불필요, ED3 파일이 있을 때만).

합성 멤버 둘(표 규격·풀 규격)로 `parse`·`rebuild`·`layout`·`window_chains` 를 맞댄다. 실제 디스크 전량 대응은 `verify_on_disc.py`.
"""

import importlib.util
import os
import struct
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, ROOT)
from shared.ps1 import gmf_script as S

TERM = 0xFFFF


def table_member(strings):
    n = len(strings)
    pool, tbl = bytearray(), []
    for s in strings:
        tbl.append(n * 2 + len(pool))
        pool += struct.pack(f"<{len(s)}H", *s) + struct.pack("<H", TERM)
    return (
        struct.pack("<H", 8)
        + b"\x0f\x00\x00\x00\x00\x00"
        + struct.pack(f"<{n}H", *tbl)
        + bytes(pool)
    )


def pool_member(strings):
    pool = b"".join(struct.pack(f"<{len(s)}H", *s) + struct.pack("<H", TERM) for s in strings)
    return struct.pack("<H", 8) + b"\x0f\x90" + struct.pack("<H", 0) + b"\x00\x00" + pool


def ed3_ref():
    path = os.path.join(ROOT, "games", "ps1-ed3", "tools", "scriptmap.py")
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("ed3_scriptmap_ref", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TestStandalone(unittest.TestCase):
    def test_표_규격_항등과_길이_변경(self):
        mem = table_member([[0x40, 0x41], [0x42], [0x43, 0x44, 0x45]])
        self.assertEqual(S.layout(mem), S.LAYOUT_TABLE)
        segs = [list(c) for _, c in S.parse(mem)["segments"]]
        self.assertEqual(S.rebuild(mem, segs, event_data=True)[0], mem)
        segs[1] = [0x50] * 7
        out = S.rebuild(mem, segs, event_data=True)[0]
        self.assertEqual([list(c) for _, c in S.parse(out)["segments"]], segs)

    def test_풀_규격_항등과_길이_변경(self):
        mem = pool_member([[0x40, 0x41], [0x42]])
        self.assertEqual(S.layout(mem), S.LAYOUT_POOL)
        segs = [list(c) for _, c in S.parse(mem)["segments"]]
        self.assertEqual(S.rebuild(mem, segs, event_data=True)[0], mem)
        segs[0] = [1, 2, 3, 4, 5]
        out = S.rebuild(mem, segs, event_data=True)[0]
        self.assertEqual([list(c) for _, c in S.parse(out)["segments"]], segs)

    def test_조각_수가_다르면_멈춘다(self):
        for mem in (table_member([[1], [2]]), pool_member([[1], [2]])):
            with self.assertRaises(S.ScriptError):
                S.rebuild(mem, [[1]], event_data=True)


def table_member_with_body(body, strings):
    """스크립트 `body` 를 낀 표 규격 멤버(본문 길이는 짝수로 맞춘다)."""
    body = body + b"\x00" * (len(body) & 1)
    n = len(strings)
    pool, tbl = bytearray(), []
    for s_ in strings:
        tbl.append(n * 2 + len(pool))
        pool += struct.pack(f"<{len(s_)}H", *s_) + struct.pack("<H", TERM)
    return struct.pack("<H", 2 + len(body)) + body + struct.pack(f"<{n}H", *tbl) + bytes(pool)


class TestMessageStreams(unittest.TestCase):
    STR = ([0x40], [0x41], [0x42], [0x43])

    def test_VM_0F_가_홀수_오프셋이어도_진짜_색인을_읽는다(self):
        # `0F 0F pad idx 00` — VM 0F 가 홀수(3) 오프셋. 옛 스캔은 (0F,00)=15 를 읽었다.
        body = b"\x00" + b"\x0f\x0f\x00" + struct.pack("<H", 2) + b"\x00"
        mem = table_member_with_body(body, self.STR)
        self.assertEqual(S.layout(mem), S.LAYOUT_TABLE)
        self.assertEqual([v for _, v in S.table_sites(mem)], [2])

    def test_출력_사이_한_바이트_연산이_끼어도_이어진다(self):
        # 출력 뒤 02(쪽 넘김)·05(이름 삽입)·01(줄바꿈)·00(끝) — 모두 피연산자 없는 연산이다
        buf = bytearray(b"\x0f")  # VM 블록 시작(오프셋 2)

        def put_print(idx, op):
            buf.append(0x0F)
            if (2 + len(buf)) & 1:  # 출력 연산 뒤 포인터가 홀수면 패딩 1
                buf.append(0)
            buf.extend(struct.pack("<H", idx))
            buf.append(op)

        for idx, op in ((0, 2), (1, 5), (2, 1), (3, 0)):
            put_print(idx, op)
        mem = table_member_with_body(bytes(buf), self.STR)
        self.assertEqual([v for _, v in S.table_sites(mem)], [0, 1, 2, 3])

    def test_출력이_없거나_00_으로_안_닫히면_메시지가_아니다(self):
        mem = table_member_with_body(b"\x0f\x05\x05\x00", self.STR)
        self.assertEqual(S.table_sites(mem), [])


class TestEquivalenceWithEd3(unittest.TestCase):
    def test_같은_결과(self):
        ref = ed3_ref()
        if ref is None:
            self.skipTest("games/ps1-ed3 없음")
        for mem in (
            table_member([[0x40, 0x41], [0x42], [0x43]]),
            pool_member([[0x40, 0x41], [0x42]]),
        ):
            self.assertEqual(ref.layout(mem), S.layout(mem))
            a, b = ref.parse(mem), S.parse(mem)
            for k in ("layout", "base", "segments", "pointers", "targets", "resolved", "starts"):
                self.assertEqual(a[k], b[k], k)
            segs = [list(c) for _, c in a["segments"]]
            segs[0] = segs[0] + [9, 9]
            self.assertEqual(
                ref.rebuild(mem, segs, event_data=True), S.rebuild(mem, segs, event_data=True)
            )
            self.assertEqual(ref.window_chains(mem), S.window_chains(mem))


if __name__ == "__main__":
    unittest.main()
