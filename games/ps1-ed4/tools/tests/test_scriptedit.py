"""스크립트 편집(블록 옮기기·쪽 더하기) 회귀 — **원본 없이 돈다**. 작은 VM 해석기로 「원래 자리에서 시작해 점프를 따라가면 같은 메시지 + 새 쪽이 나오고 원래 다음 연산에 닿는다」를 본다.

🔴 지키는 것: ① JMP 가 정렬 규칙을 지킨다(연산 뒤 커서가 홀수면 패딩 1바이트) ② 메시지 언어의 `02` 는 점프가 아니라 쪽 넘김 ③ 앞 스크립트 오프셋은 안 변한다(덧붙이기만).
"""

import struct
import unittest

import _path  # noqa: F401
import scriptedit

from shared.ps1 import gmf_script as sm

MARK = 0x10  # 메시지 뒤에 오는 다른 VM 연산(복귀 확인용)


def member(strings, script_tail=b""):
    """표 규격 합성 멤버 — 스크립트: `0F`(VM) `0F`(메시지) <색인 0> 01 `0F` <색인 1> 00, 그 뒤 MARK 연산."""
    # 오프셋: 2:0F(VM) 3:0F 4-5:idx0 6:01 7:0F 8-9:idx1 10:00 11:MARK
    script = (
        bytes([0x0F, 0x0F])
        + struct.pack("<H", 0)
        + b"\x01"
        + b"\x0f"
        + struct.pack("<H", 1)
        + b"\x00"
        + bytes([MARK])
        + script_tail
    )
    if len(script) % 2:
        script += b"\x00"
    base = 2 + len(script)
    n = len(strings)
    tbl, pool = [], bytearray()
    for s in strings:
        tbl.append(n * 2 + len(pool))
        pool += struct.pack(f"<{len(s)}H", *s) + struct.pack("<H", 0xFFFF)
    return struct.pack("<H", base) + script + struct.pack(f"<{n}H", *tbl) + bytes(pool)


def run(mem, start):
    """(출력한 색인들, 끝난 주소) — VM `02`(JMP)를 따라가고, `0F` 로 시작한 메시지를 `00` 까지 읽고, MARK 연산에서 멈춘다."""
    pc, printed = start, []
    while True:
        op = mem[pc]
        pc += 1
        if op == scriptedit.JMP:
            if pc % 2:
                pc += 1
            pc = struct.unpack_from("<h", mem, pc)[0]
        elif op == scriptedit.TEXT:
            while True:  # 메시지 언어
                m = mem[pc]
                pc += 1
                if m == 0x0F:
                    if pc % 2:
                        pc += 1
                    printed.append(struct.unpack_from("<H", mem, pc)[0])
                    pc += 2
                elif m in (1, 2):
                    continue
                elif m == 0:
                    break
                else:
                    raise AssertionError(f"모르는 메시지 연산 {m:#x}")
        elif op == MARK:
            return printed, pc - 1
        else:
            raise AssertionError(f"모르는 VM 연산 {op:#x} @{pc - 1}")


class TestBlocks(unittest.TestCase):
    def test_블록_경계(self):
        m = member([[0x40], [0x41]])
        (b,) = scriptedit.blocks(m)
        self.assertEqual((b["p0"], b["e"]), (2, 11))
        self.assertEqual([v for _, v, _ in b["sites"]], [0, 1])

    def test_원본은_그대로_실행된다(self):
        m = member([[0x40], [0x41]])
        self.assertEqual(run(m, 2), ([0, 1], 11))


class TestRewrite(unittest.TestCase):
    def test_쪽을_더해도_원래_다음_연산에_닿는다(self):
        m = member([[0x40], [0x41]], script_tail=b"\x00\x00\x00")
        new = scriptedit.rewrite_message(m, 1, [[0x50, 0x51], [0x52]], [1, 2, 2, 0])
        printed, end = run(new, 2)
        self.assertEqual(printed, [0, 1, 2, 3])  # 원래 둘 + 새 둘(색인 2·3)
        self.assertEqual(end, 11)  # 원래 MARK 연산 위치 — 점프 복귀가 맞다
        segs = [list(c) for _, c in sm.parse(new)["segments"]]
        self.assertEqual(segs, [[0x40], [0x41], [0x50, 0x51], [0x52]])

    def test_앞_스크립트는_안_밀린다(self):
        m = member([[0x40], [0x41]])
        new = scriptedit.rewrite_message(m, 0, [[0x50]], [1, 2, 0])
        # MARK 연산과 그 앞(원래 블록 바깥) 바이트는 같은 자리에 같은 값
        self.assertEqual(new[11], MARK)
        self.assertEqual(new[:2], new[:2])
        # 스크립트 구간 길이만 늘었다(덧붙임)
        self.assertGreater(sm.text_base(new), sm.text_base(m))

    def test_모든_색인_u16_은_짝수_주소에_앉는다(self):
        m = member([[0x40], [0x41]])
        new = scriptedit.rewrite_message(m, 1, [[0x50]], [2, 2, 0])
        for q, _v in sm.parse(new)["pointers"]:
            self.assertEqual(q % 2, 0)

    def test_흐름_수가_틀리면_운다(self):
        m = member([[0x40], [0x41]])
        with self.assertRaises(scriptedit.EditError):
            scriptedit.rewrite_message(m, 1, [[0x50]], [2, 0])
        with self.assertRaises(scriptedit.EditError):
            scriptedit.rewrite_message(m, 1, [[0x50]], [2, 2, 1])  # 마지막이 00 이 아니다

    def test_없는_조각은_운다(self):
        m = member([[0x40], [0x41]])
        with self.assertRaises(scriptedit.EditError):
            scriptedit.rewrite_message(m, 9, [[0x50]], [0, 0, 0])

    def test_JMP_정렬(self):
        self.assertEqual(
            scriptedit.jmp_bytes(2, 0x1234), bytes([2, 0, 0x34, 0x12])
        )  # 짝수 주소 연산 → 패딩
        self.assertEqual(
            scriptedit.jmp_bytes(3, 0x1234), bytes([2, 0x34, 0x12])
        )  # 홀수 주소 연산 → 패딩 없음


if __name__ == "__main__":
    unittest.main()
