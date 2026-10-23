"""구조 대조 검사(`check_ctrl_flow.lockstep`)가 **일부러 망가뜨린 사본에서 실제로 우는가** — 가짜 바이트로(원본 데이터를 옮기지 않는다).

원판 쪽: 조각 A(글 · 색 · 호출 · 점프) → B(글 · 효과음 · 종결) · C(글 · 복귀). 구운 쪽: 같은 흐름을 다른 자리·다른 글 길이로 옮겼다.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import text  # noqa: F401, I001  (shared/text 보다 먼저)
import check_ctrl_flow as C
import script

LEADS = frozenset({0x74})
A, B, CC = 0x00, 0x30, 0x40  # 원문 조각 자리(뱅크 0, 파일 오프셋 = 주소 − 0x8000)
A2, B2, C2, S2 = 0x100, 0x130, 0x140, 0x150  # 구운 자리


def snes(off: int) -> bytes:
    return (0x8000 + off).to_bytes(3, "little")


def rel(frm: int, to: int) -> bytes:
    return ((to - frm) & 0xFFFF).to_bytes(2, "little")


def make_orig() -> bytes:
    img = bytearray(0x60)
    a = bytes([0x11, 0x12, 0xE3, 0x13, 0xCF, 0x14, 0xF9]) + snes(B)
    fc_at = A + len(a)
    a += bytes([0xFC]) + rel(fc_at, CC) + bytes([0xE0, 0xE4])
    img[A : A + len(a)] = a
    img[B : B + 6] = bytes([0x15, 0xE5, 0x07, 0x16, 0xE0, 0xE4])
    img[CC : CC + 2] = bytes([0x17, 0xFE])
    return bytes(img)


def make_built(stub: bool = False) -> bytearray:
    img = bytearray(0x200)
    a = bytes([0x74, 0x21, 0xE3, 0x31, 0xF9]) + snes(B2)
    fc_at = A2 + len(a)
    tgt = S2 if stub else C2
    a += bytes([0xFC]) + rel(fc_at, tgt) + bytes([0xE0, 0xE4])
    img[A2 : A2 + len(a)] = a
    img[B2 : B2 + 9] = bytes([0x74, 0x22, 0x30, 0xE5, 0x07, 0x74, 0x23, 0xE0, 0xE4])
    img[C2 : C2 + 3] = bytes([0x74, 0x24, 0xFE])
    if stub:
        img[S2 : S2 + 8] = bytes([0xFC, 3, 0, 0xF9]) + snes(C2) + b"\xfe"
    return img


def walk(orig: bytes, built: bytes) -> C.Result:
    items = script.parse_region(orig, 0, 0x48, {B, CC})
    return C.lockstep(orig, items, bytes(built), [(A, A2, "A")], frozenset(), LEADS)


class Lockstep(unittest.TestCase):
    def test_정상은_조용하다(self):
        r = walk(make_orig(), make_built())
        self.assertEqual(r.errors, [])
        self.assertGreaterEqual(r.ctrl, 6)

    def test_FC_중계_조각은_목표로_풀린다(self):
        r = walk(make_orig(), make_built(stub=True))
        self.assertEqual(r.errors, [])
        self.assertEqual(r.fc_stubs, {(CC, S2)})

    def test_제어_인자_한_바이트가_달라지면_운다(self):
        b = make_built()
        b[B2 + 4] = 0x08  # 효과음 인자 07 → 08
        self.assertTrue(walk(make_orig(), b).errors)

    def test_종결을_쪽_대기로_바꾸면_운다(self):
        b = make_built()
        b[B2 + 7] = 0xFF  # E0 → FF
        self.assertTrue(walk(make_orig(), b).errors)

    def test_종결_앞_채움_바이트가_끼면_운다(self):
        """ss-ed3 10-21 사고의 꼴 — 대사 끝에 FF FF 를 넣으면 제어 열이 달라진다."""
        b = make_built()
        b[B2 + 7 : B2 + 9] = bytes([0xFF, 0xFF])
        self.assertTrue(walk(make_orig(), b).errors)

    def test_호출_목표가_엉뚱한_블록이면_운다(self):
        b = make_built()
        b[A2 + 5 : A2 + 8] = snes(C2)  # F9 가 B 대신 C 를 부른다
        self.assertTrue(walk(make_orig(), b).errors)

    def test_글이_통째로_사라지면_운다(self):
        b = make_built()
        b[B2 : B2 + 3] = bytes([0xE5, 0x07, 0x00])[:3]  # 앞 글 덩이 자리에 제어가 먼저 온다
        self.assertTrue(walk(make_orig(), b).errors)

    def test_글_길이만_달라지는_번역은_통과한다(self):
        b = make_built()
        b[A2 : A2 + 2] = bytes([0x40, 0x41])  # 같은 길이의 다른 글자
        self.assertEqual(walk(make_orig(), b).errors, [])


def targets(orig: bytes, built: bytes) -> list:
    items = script.parse_region(orig, 0, 0x48, {B, CC})
    r = C.lockstep(orig, items, bytes(built), [(A, A2, "A")], frozenset(), LEADS)
    return C.target_bytes(orig, items, bytes(built), r.moved, {}, [A], LEADS)


class TargetBytes(unittest.TestCase):
    """pce-ed1 10-22 의 꼴 — 한 메시지의 점프 스텁이 제자리 종료 바이트를 덮었는데 다른 메시지의 점프가 그 바이트로 들어온다."""

    def test_정상은_조용하다(self):
        bad, st = targets(make_orig(), make_built())
        self.assertEqual(bad, [])
        self.assertGreaterEqual(st["맞음"], 3)

    def test_글_목표_자리를_종료로_덮으면_운다(self):
        b = make_built()
        b[B2] = 0xE0  # F9 가 부르는 조각 머리가 종료 바이트가 됐다
        bad, _ = targets(make_orig(), b)
        self.assertTrue(bad)

    def test_제어_목표_자리가_다른_코드로_덮이면_운다(self):
        o = make_orig()
        b = make_built()
        # 원판 C 조각 머리를 제어(FE)로 두고, 구운 쪽은 FC 스텁이 덮었다
        o = bytearray(o)
        o[CC : CC + 2] = bytes([0xFE, 0xFE])
        b[C2 : C2 + 3] = bytes([0xFC, 0x03, 0x00])
        bad, _ = targets(bytes(o), b)
        self.assertTrue(bad)


if __name__ == "__main__":
    unittest.main()
