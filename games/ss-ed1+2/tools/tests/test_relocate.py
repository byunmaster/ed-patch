"""재배치 회귀 — **함정마다 하나**. 원본 없이 도는 것만 여기 둔다.

🔴 이 도구는 **남의 파일 주소를 바꾼다.** 다른 도구가 「원본 LBA 로 빌드에 쓴다」는
   전제를 깔고 있으면 조용히 엉뚱한 섹터를 고친다 — 실제로 그렇게 물렸다(2026-08-31).
"""

import json
import os
import re
import sys
import unittest


def _read(path):
    with open(path) as f:
        return f.read()


TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import relocate_files as R


class Canon(unittest.TestCase):
    def test_targets_are_scene_files_only(self):
        """🔴 본체는 대상이 아니다 — 부팅 경로이고, 다른 패처가 그 전제에 얹혀 있다."""
        for p in R.targets():
            self.assertTrue(p.startswith("/BIN/") and "SCN" in p, f"{p}: 씬 파일이 아니다")
            self.assertNotIn(p, ("/ED.BIN", "/ED2.BIN"))

    def test_writers_take_their_extent_from_the_build(self):
        """🔴 **쓰기 자리는 빌드 이미지가 정한다** — 규칙은 `common.dst_files` 가 정본이다.

        ⚠ `patch_mon_names` 가 실제로 이 함정에 빠졌다 — ED2MON 이 밀리는데 옛 LBA 로 써서
          화면의 일본어가 22 → 255줄이 됐다(2026-08-31).
        ⚠ 그래서 **재배치 대상이 아닌 파일을 쓰는 도구도** 여기로 묻는다(2026-09-03).
          「지금은 안 옮기니까 맞다」는 다음에 옮길 때 조용히 틀리는 자리였다 — 본체 둘이
          정확히 그 상태였다.
        """
        for name in ("patch_crit_copy", "patch_josa_hook", "patch_mon_names"):
            src = _read(os.path.join(TOOLS, f"{name}.py"))
            self.assertIn("common.dst_files(", src, f"{name}: `common.dst_files` 를 안 쓴다")
            bad = re.search(r"files\s*=\s*\{[^}]*common\.iso_files\(mm\)", src)
            self.assertIsNone(
                bad, f"{name} 이 **원본** 목록으로 쓰기 자리를 정한다 — `common.dst_files` 를 쓴다"
            )

    def test_pregap_is_kept(self):
        """트랙 끝에 여유를 남긴다 — 오디오 트랙 바로 앞까지 데이터를 붙이지 않는다."""
        self.assertGreaterEqual(R.PREGAP_KEEP, 50)
        self.assertLess(R.PREGAP_KEEP, 150)

    def test_canon_is_sorted_and_unique(self):
        """정본은 정렬·중복 없음 — 순서가 흔들리면 배치가 달라진다(결정성)."""
        with open(R.CANON) as f:
            files = json.load(f)["files"]
        self.assertEqual(files, sorted(set(files)))

    def test_chain_runs_relocate_before_scenes(self):
        """⚠ 순서가 계약이다 — 재배치가 **씬 대사보다 먼저** 돌아야 그 자리를 쓴다."""
        sh = _read(os.path.join(os.path.dirname(TOOLS), "check.sh"))
        a = sh.index("relocate_files.py")
        b = sh.index("patch_scn.py")
        self.assertLess(a, b, "재배치가 씬 대사 뒤에 있다 — 늘린 자리를 아무도 안 쓴다")
        # 그리고 몬스터 이름은 재배치 **뒤**라 빌드 LBA 를 써야 한다 —
        # 그건 위 `test_writers_take_their_extent_from_the_build` 가 본다.


if __name__ == "__main__":
    unittest.main(verbosity=2)
