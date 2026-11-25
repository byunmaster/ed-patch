"""조판 지문 입력은 커밋된 소스(+원판 롬)뿐이어야 한다 — untracked 파생물(`work/derived/`)을 읽으면 동결 값이 머신·시점을 탄다(10-24)."""

import re
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


class FingerprintInputs(unittest.TestCase):
    def test_조판기와_지문이_work_derived_를_안_읽는다(self):
        for name in ("typeset.py", "typeset_fp.py"):
            src = (TOOLS / name).read_text(encoding="utf-8")
            code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith(("#", '"""')))
            self.assertIsNone(re.search(r"OUT_DIR\s*/", code), f"{name} 이 OUT_DIR(work/derived) 를 읽는다")


if __name__ == "__main__":
    unittest.main()
