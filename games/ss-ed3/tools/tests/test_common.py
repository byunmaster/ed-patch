"""`common.py` — 바깥 서비스 열쇠 읽기. **원본도 망도 없이** 돈다.

🔴 열쇠는 `.local/secrets.env` 하나에 모은다 — 도구마다 읽는 법을 따로 쓰면 곧 갈린다.
⚠ 워크트리에는 `.local/` 이 안 따라오므로 **메인 트리까지 거슬러 올라가는지**가 핵심이다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common as C


class Secrets(unittest.TestCase):
    """`.local/secrets.env` 읽기 — 열쇠가 느는 자리가 이미 둘이라 한 곳으로 모았다."""

    def test_env_wins_and_file_parses(self):
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".local"))
            with open(os.path.join(d, ".local", "secrets.env"), "w", encoding="utf-8") as f:
                f.write("# 주석\nDEEPL_API_KEY=abc\nGEMINI_API_KEY='q u o'\n#DEAD_KEY=x\n")
            with mock.patch.object(C, "ROOT", d):
                self.assertEqual(C.secret("DEEPL_API_KEY"), "abc")
                self.assertEqual(C.secret("GEMINI_API_KEY"), "q u o")  # 따옴표는 벗긴다
                self.assertEqual(C.secret("DEAD_KEY"), "")  # 주석은 안 읽는다
                self.assertEqual(C.secret("NOPE"), "")
                with mock.patch.dict(os.environ, {"DEEPL_API_KEY": "env"}):
                    self.assertEqual(C.secret("DEEPL_API_KEY"), "env")  # 환경변수가 이긴다

    def test_walks_up_to_main_tree(self):
        """워크트리에는 `.local/` 이 없다 — 위로 올라가 메인 트리 것을 찾는다."""
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as d:
            main = os.path.join(d, "repo")
            wt = os.path.join(main, ".claude", "worktrees", "x")
            os.makedirs(os.path.join(main, ".local"))
            os.makedirs(wt)
            p = os.path.join(main, ".local", "secrets.env")
            with open(p, "w", encoding="utf-8") as f:
                f.write("DEEPL_API_KEY=up\n")
            with mock.patch.object(C, "ROOT", wt):
                self.assertEqual(C.secrets_path(), p)
                self.assertEqual(C.secret("DEEPL_API_KEY"), "up")


if __name__ == "__main__":
    unittest.main()
