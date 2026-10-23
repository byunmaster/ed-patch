"""check.sh 가 실제 빌드를 돌려 칸 초과를 잡는가 — `build.py --check` 만으로는 전투 이름 칸·sysmsg 칸이 안 보였다(10-18)."""

import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE / "tools"))
sys.path.insert(0, str(HERE.parents[1]))


class CheckRunsRealBuild(unittest.TestCase):
    def test_check_sh_builds_and_clears_stale_rom(self):
        s = (HERE / "check.sh").read_text(encoding="utf-8")
        self.assertRegex(s, r'"\$PY" "\$T/build\.py"\n')  # --check 없는 줄
        self.assertIn('rm -f "$BUILD_TAG_DIR"/*.bin', s)  # 낡은 롬을 먼저 지운다
        self.assertLess(s.index("rm -f"), s.index('"$PY" "$T/build.py"\n'))
        self.assertIsNone(re.search(r"build\.py\"[^\n]*\|\|\s*true", s))  # 실패를 삼키지 않는다

    def test_name_longer_than_slot_stops_build(self):
        import battle

        orig = battle.blocks.__globals__["common"].rom() if hasattr(battle, "common") else None
        if orig is None:
            self.skipTest("원본 없음")
        blocks = [b for _s, b, _e in battle.blocks(orig)]
        mons = battle.monsters(orig)
        key = next(k for k in mons if k.startswith("赤スラッグ"))
        mons = dict(mons)
        mons[key] = {"ours": "아주 새빨간 슬러그 군군군"}
        with self.assertRaises(SystemExit):
            for n, b in enumerate(blocks):
                battle.plan_block(b, n, {}, mons, lambda s: s.encode("cp932", "replace"))


class NoStrayPua(unittest.TestCase):
    def test_script_has_no_ps1_placeholder_pua(self):
        """PS1 문안의 자리표시 PUA(U+E003)가 정본에 섞이면 MD 에선 HUD 「입구」 글리프(구)로 굽힌다 — 공백이어야 한다(10-18 상점 「약초구말이군」)."""
        import glob
        import json

        bad = []
        for f in glob.glob(str(HERE / "script" / "*.json")):
            for k, v in json.load(open(f, encoding="utf-8"))["streams"].items():
                if "\ue003" in v.get("ours", ""):
                    bad.append((f, k))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
