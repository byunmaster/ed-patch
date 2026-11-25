"""임시 적재 빌리기(`transient_fallback`) — 손으로 짠 기계어는 디스어셈블로 검산한다(연속 디코드 + 분기·호출 목적지 + 사이트 바이트)."""

import contextlib
import io
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import band_fallback
import debug_item_list
import earlyfree
import huc6280_dis as D
import transient_fallback as T


def listing() -> list[str]:
    code = T.code()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        D.dis(code, T.ORG, 0, len(code) - 1)  # 끝 1B 는 표시 바이트(dirty)
    return [ln for ln in buf.getvalue().splitlines() if ln.strip()]


class TransientFallbackTest(unittest.TestCase):
    def test_decodes(self):
        ls = listing()
        self.assertFalse([ln for ln in ls if ".db" in ln], "디코드되지 않는 바이트")
        self.assertEqual(T.code()[-1], 0)  # 표시는 0 으로 시작한다
        self.assertEqual(T.labels()["dirty"], T.ORG + len(T.code()) - 1)

    def test_branch_and_call_targets(self):
        ls = listing()
        starts = {int(ln[:4], 16) for ln in ls}
        engine = {0x56D8, 0x578A, 0x570C, band_fallback.restore_at()}
        for ln in ls:
            m = re.search(r"\b(?:BCC|BCS|BNE|BEQ|BMI|BRA|JSR|JMP)\s+\$([0-9A-F]{4})", ln)
            if m:
                t = int(m.group(1), 16)
                self.assertTrue(t in starts or t in engine, ln)
        lab = T.labels()
        for name in ("load", "load1", "rid", "done", "scene", "leader"):
            self.assertIn(lab[name], starts, name)

    def test_borrow_only_after_loader_failure(self):
        """엔진 로더를 먼저 부르고, 캐리가 선 때만 슬롯 15 를 가리키게 한 뒤 엔진의 읽기 자리로 뛴다."""
        text = "\n".join(listing())
        i_load = text.index("JSR $56D8")
        i_bcc = text.index("BCC", i_load)
        i_grp = text.index("JSR $578A", i_bcc)
        i_slot = text.index("LDA #$0F", i_grp)
        i_jmp = text.index("JMP $570C", i_slot)
        self.assertLess(i_load, i_bcc)
        self.assertLess(i_slot, i_jmp)
        self.assertEqual(T.BORROW_SLOT, 15)
        self.assertEqual(text.count("JMP $%04X" % band_fallback.restore_at()), 1)

    def test_restore_label_is_the_band_restore_loop(self):
        """`band_fallback` 의 되돌리기 고리 머리 — `LDY #8` 로 시작하고 글리프 뱅크 1 앞 섹터(rel 118)를 0x87 로 읽는다."""
        code, _free = band_fallback.code()
        at = band_fallback.restore_at() - band_fallback.LOAD_ORG
        self.assertEqual(code[at : at + 2], b"\xa0\x08")
        tail = code[at:]
        self.assertIn(bytes([0xA9, band_fallback.GLYPH1_REL & 0xFF, 0x85, 0xFE]), tail)
        self.assertIn(bytes([0xA9, band_fallback.BORROW_BANK, 0x85, 0xFA]), tail)
        self.assertEqual(tail[-1], 0x60)

    def test_sites(self):
        got = {name: (off, old, new) for name, off, old, new in T.sites()}
        self.assertEqual(set(got), {"npc", "area", "scene", "leader"})
        lab = T.labels()
        far = lambda to: b"\x20\xd8\x4f\x08" + to.to_bytes(2, "little")  # noqa: E731
        self.assertEqual(got["npc"], (0x0A61, bytes.fromhex("a90120d85684f8"), far(lab["load"]) + b"\xea"))
        self.assertEqual(got["area"], (0x0CE1, bytes.fromhex("a90120d8565ab98d37"), far(lab["load"]) + b"\x5a\xea\xea"))
        self.assertEqual(got["scene"], (0x0617, bytes.fromhex("a9018562a902"), far(lab["scene"])))
        self.assertEqual(got["leader"], (0x028B, bytes.fromhex("a901186df13e"), far(lab["leader"])))
        for _name, (_off, old, new) in got.items():
            self.assertEqual(len(old), len(new))

    def test_replayed_instructions(self):
        """먼 호출이 지운 원판 명령을 스텁이 대신 한다 — 씬: LDA #1 / STA $62 / LDA #2 · 리더: LDA #1 / CLC / ADC $3EF1 · 적재: STY $F8 / LDA $378D,Y."""
        code, lab = T.code(), T.labels()
        at = lambda name: lab[name] - T.ORG  # noqa: E731
        self.assertEqual(code[at("load") + 3 : at("load") + 9], bytes.fromhex("84f8b98d3760"))
        self.assertEqual(code[at("scene") : at("leader")], bytes.fromhex("5a202b797aa9018562a90260".replace("2b79", lab["rid"].to_bytes(2, "little").hex())))
        self.assertEqual(code[at("leader") + 3 : at("dirty")], bytes.fromhex("a901186df13e60"))

    def test_room(self):
        self.assertLessEqual(len(T.code()), T.ROOM)
        self.assertEqual(T.ORG + T.ROOM, earlyfree.ORG)  # 뒤는 옛 컨테이너 먼저 내리기
        org, blob, _i, _w = debug_item_list.assemble()
        self.assertLessEqual(org + len(blob), T.ORG)  # 앞은 디버그 목록 코드


if __name__ == "__main__":
    unittest.main()
