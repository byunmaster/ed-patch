"""test_battle — 전투 일괄 시험 롬 후크: 기계어가 끝까지 디코드되고, 시험 꼬리표가 아니면 거부한다(원본 불필요한 부분만)."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_battle


class HookCode(unittest.TestCase):
    def test_hook_decodes_and_labels(self):
        old = bytes.fromhex("48e7ff1c0c80")  # 렌더러 입구 원본 바이트(movem + cmpi 앞 2B)
        code, rngf, exit_off, tick_off = test_battle.hook_code(old)
        self.assertGreater(len(code), 100)
        self.assertTrue(0 < rngf < exit_off < tick_off < len(code))
        test_battle.verify(code)  # 연속 디코드 — 끝이 어긋나면 SystemExit

    def test_refuses_product_tag(self):
        tool = Path(test_battle.__file__)
        env = dict(os.environ, ED_BUILD_TAG="md-ed2")
        p = subprocess.run(
            [sys.executable, str(tool)], env=env, capture_output=True, text=True, check=False
        )
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("test-battle", p.stderr + p.stdout)


if __name__ == "__main__":
    unittest.main()
