"""옛 컨테이너 먼저 내리기(`earlyfree`) — 손으로 짠 기계어는 디스어셈블로 검산한다(연속 디코드 + 분기 목적지 + 호출 목적지)."""

import contextlib
import io
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import debug_item_list
import earlyfree as E
import huc6280_dis as D
import sprmask


def parts() -> list[tuple[int, bytes, bool]]:
    """(시작 주소, 바이트, 명령인가) — 먼 호출 둘(인라인 인자 3B 가 붙어 디스어셈블러가 못 읽는다)은 자료로 가른다."""
    code = E.code()
    i, j = code.index(E.SITE_OLD), code.index(E.RELOAD)
    cuts = [(0, i, True), (i, i + 6, False), (i + 6, j, True), (j, j + 6, False), (j + 6, len(code), True)]
    return [(E.ORG + lo, code[lo:hi], is_code) for lo, hi, is_code in cuts]


def listing() -> list[str]:
    out = []
    for org, body, is_code in parts():
        if not is_code:
            continue
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            D.dis(body, org, 0, len(body))
        out += [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    return out


class EarlyFreeTest(unittest.TestCase):
    def test_decodes_and_calls(self):
        ls = listing()
        self.assertFalse([ln for ln in ls if ".db" in ln], "디코드되지 않는 바이트")
        self.assertEqual(sum(1 for ln in ls if "JSR $5597" in ln), 1)  # 엔진의 그룹 내림을 그대로 부른다
        self.assertTrue(any("LDY $61" in ln for ln in ls))  # 씬 컨테이너 그룹
        self.assertEqual(sum(1 for ln in ls if "$378D,Y" in ln), 2)  # 올라와 있나 보기 + 번호를 슬롯 14 에 세워 두기
        self.assertTrue(ls[-1].rstrip().endswith("RTS"))
        self.assertEqual(sum(1 for ln in ls if "RTS" in ln), 1)

    def test_branch_targets_land_on_instruction_starts(self):
        ls = listing()
        starts = {int(ln[:4], 16) for ln in ls} | {org for org, _b, is_code in parts() if not is_code}  # 먼 호출 머리
        seen = 0
        for ln in ls:
            m = re.search(r"\b(?:BCC|BCS|BNE|BEQ|BMI|BRA)\s+\$([0-9A-F]{4})", ln)
            if m:
                seen += 1
                self.assertIn(int(m.group(1), 16), starts, ln)
        self.assertEqual(seen, 3)  # 안 올라와 있다 → 묶음 · 바꾸는 전환 둘 → 끝

    def test_far_calls(self):
        code = E.code()
        self.assertEqual(code.count(E.SITE_OLD), 1)  # 묶음 올리기(원판 6B 그대로)
        self.assertEqual(code.count(E.RELOAD), 1)  # 필드행 — 엔진의 컨테이너 바꾸기
        self.assertLess(code.index(E.SITE_OLD), code.index(E.RELOAD))  # 묶음 먼저(컨테이너를 내린 뒤)
        self.assertEqual(E.RELOAD, bytes.fromhex("20d84f02ab6b"))  # 뱅크 0x6A `$6BAB`
        self.assertEqual(code[-5:], bytes.fromhex("a9ff856c60"))  # 지역 기억을 못 쓰게 → 다음 마을에서 반드시 다시 올린다

    def test_frees_before_bundle_unconditionally(self):
        """11-23: 장이 바뀌는 전환이면 **필드행이어도** 옛 컨테이너를 묶음 앞에서 내린다(옛 판은 `$6B8C` 조건을 먼저 봐서 필드행을 건너뛰었다)."""
        code = E.code()
        self.assertEqual(code[:5], bytes.fromhex("a461b98d37"))  # LDY $61 / LDA $378D,Y — 조건 없이 시작
        self.assertLess(code.index(bytes.fromhex("209755")), code.index(E.SITE_OLD))

    def test_field_condition_mirrors_engine(self):
        """`$6B8C` 의 「컨테이너를 안 바꾼다」 조건 — `$C009 != 3` 이고 `$C00F + $C010 == 0`. 그때만 여기서 올린다."""
        code = E.code()
        at = code.index(E.SITE_OLD) + 6
        self.assertEqual(code[at : at + 16], bytes.fromhex("ad09c0c903f013ad0fc0186d10c0d00a"))
        self.assertEqual(at + 16, code.index(E.RELOAD))

    def test_parks_group_on_glyph_slot(self):
        self.assertEqual(E.PARK_SLOT, 14)  # 할당기·조각 모으기의 `CPX #$0E` 바깥 첫 칸 — 주인표가 늘 0
        self.assertIn(bytes([0xA9, E.PARK_SLOT, 0x99, 0x8D, 0x37]), E.code())

    def test_site_and_room(self):
        self.assertEqual(E.site_new(), bytes.fromhex("20d84f084f79"))
        self.assertEqual(len(E.site_new()), len(E.SITE_OLD))
        self.assertLessEqual(len(E.code()), E.ROOM)
        self.assertEqual(E.ORG + E.ROOM, sprmask.DEBUG_LIST_LIMIT)  # 뒤는 잘린 그림 사본 토막 a
        org, blob, _i, _w = debug_item_list.assemble()
        self.assertLessEqual(org + len(blob), E.ORG)  # 앞은 디버그 목록 코드


if __name__ == "__main__":
    unittest.main()
