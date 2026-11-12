"""전투 AI 가 이름 버퍼에 쓰는 자리 — 이름 끝 위치가 **우리 이름 길이**와 맞는지 본다(10-24 붉은 슬라임 글줄 겹침).
AI 스크립트는 원문 이름 길이(가나 2B)를 박아 두고 접미를 떼거나(`06`) 붙인다. 우리 이름이 길어지거나 짧아지면 끝 토큰이 글자 코드 가운데 박힌다.
정본 이름이 바뀌어 길이가 달라지면 이 시험이 울린다 — `patches.py` 의 해당 자리(`$D4:3179` · `$D4:2F12` · `$D4:54F5` · `$D4:5501`) 오프셋을 같이 고친다. 구운 롬이 없으면 건너뛴다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import common
import monsters

KR_ROM = common.BUILD_DIR / common.BUILD_TAG / "Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"
BASES = (0x063B, 0x067B, 0x06BB, 0x06FB)


@unittest.skipUnless(KR_ROM.exists(), "구운 롬 없음")
class NameAiSites(unittest.TestCase):
    def setUp(self):
        self.groups = monsters.groups(KR_ROM.read_bytes())

    def base_len(self, g, slot, suf=2):
        name = self.groups[g][1][slot]
        return len(name) - suf  # 접미: 전각 2B(`80 1A~1D`, 원판 꼴) — 원판 접미가 ASCII 인 군(9 칸1 · 40)은 suf=1

    def test_group2_slime(self):  # 붉은 슬라임: 접미 뗀 이름 끝 `$0646` · 접미 `A` 자리 `$0646` · 끝 `$0647`
        self.assertEqual(self.base_len(2, 0), 0x0646 - BASES[0])

    def test_group24(self):  # 木人(칸 0) 끝 `$0643` · ビルタラ(칸 2) 끝 `$06C1`
        self.assertEqual(self.base_len(24, 0), 0x0643 - BASES[0])
        self.assertEqual(self.base_len(24, 2), 0x06C1 - BASES[2])

    def test_other_groups(self):  # 군 → 스크립트 표로 찾은 자리(10-24): 군9 슬롯1 +8 · 군36 슬롯1 +6 · 군62 슬롯0 +6 · 군71 슬롯0 +6
        self.assertEqual(self.base_len(9, 1, 1), 0x0683 - BASES[1])  # 군9 칸1 은 원판 접미가 ASCII(반각)
        self.assertEqual(self.base_len(36, 1), 0x0681 - BASES[1])
        self.assertEqual(len(self.groups[62][1][0]), 0x0641 - BASES[0])  # 접미 없는 원문 이름 — 접미 `80 1A` 는 스크립트가 이어 붙인다
        self.assertEqual(self.base_len(71, 0), 0x0641 - BASES[0])

    def test_summon_counters(self):  # 소환 군의 「다음 글자」 자리 = 4번째 칸(슬롯3) 이름의 접미 ASCII 자리
        self.assertEqual(self.base_len(52, 3), 0x06FF - BASES[3])
        for g in (35, 47):
            self.assertEqual(self.base_len(g, 3), 0x0703 - BASES[3], g)
        self.assertEqual(self.base_len(40, 3, 1), 0x0703 - BASES[3])  # 군40 은 원판 접미가 ASCII(반각 1B)

    def test_sites_patched(self):  # 전각 접미 꼴 — 원판 코드 꼴에 operand 만 우리 이름 길이(Lk−Lj)만큼 옮긴 것(patches.apply_fullsuf)
        rom = KR_ROM.read_bytes()
        for a, want in (
            (0xD42F12, "A2801A8E4606"), (0xD42F1A, "8D4806"), (0xD43179, "8D4606"),  # 군2 칸0: 접미 · 끝 · 이름 끝
            (0xD42FEC, "A9809D4805A90E9D4905A9069D4A05"), (0xD43011, "A9809D8805A90F9D8905A9069D8A05"),  # 군2 분열 표지(본문+접미 13B 뒤)
            (0xD454F5, "8D4306"), (0xD45501, "8DC106"), (0xD46E66, "8D8106"), (0xD4B6CD, "8D4106"), (0xD43C17, "8D8306"),
            (0xD4A617, "A9808D4106A91A8D4206A9068D4306"), (0xD4A637, "8D8206"),  # 군62
            (0xD48CAE, "AD0007"), (0xD48D0D, "AD0007"), (0xD48D16, "EE0007"), (0xD48D4A, "A91D8D0007"),  # 소환 군52(원판 코드 + 접미 둘째 바이트 `$0700`)
            (0xD46C10, "AD0407"), (0xD46C98, "AD0407"), (0xD46CA1, "EE0407"), (0xD46CD5, "A91D8D0407"),  # 군35
            (0xD481C1, "AD0407"), (0xD4822A, "AD0407"), (0xD48233, "EE0407"), (0xD484EC, "A91C8D0407"),  # 군47
            (0xD47602, "AD0307"), (0xD4760C, "8D0307"), (0xD476C3, "8D0307"),  # 군40(원판 접미 ASCII — 반각 패치 그대로)
        ):
            o = common.snes2off(a)
            self.assertEqual(rom[o : o + len(want) // 2].hex().upper(), want, hex(a))


if __name__ == "__main__":
    unittest.main()
