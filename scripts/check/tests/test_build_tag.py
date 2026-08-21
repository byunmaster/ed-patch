"""꼬리표 — **워크트리에서만 안 도는** 함정을 박아 둔다.

`shared/build_tag.py` 의 값은 파일 경로에 들어가므로, 틀려도 빌드는 성공하고 이미지만
엉뚱한 칸에 떨어진다. 그래서 조용하다 — 테스트로 잡는다.
"""

import os
import sys
import unittest
from tempfile import TemporaryDirectory

# ⚠ 상대 단수를 박지 않는다 — `scripts/tests/` 가 `scripts/check/tests/` 로 내려가자
#   `../../shared` 가 어긋나 **테스트가 임포트조차 못 했다**(2026-08-22). 찾아 올라간다.
_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_d, "shared")):
    _d, _prev = os.path.dirname(_d), _d
    assert _d != _prev, "shared/ 를 못 찾겠다"
sys.path.insert(0, os.path.join(_d, "shared"))
import build_tag as B


class T(unittest.TestCase):
    def test_env_overrides_and_is_path_safe(self):
        os.environ["ED_TAG_TEST"] = "game/ps1-ed1+2"
        # `/` 를 그대로 두면 디렉터리가 한 겹 더 생긴다.
        self.assertEqual(B.build_tag("ED_TAG_TEST"), "game-ps1-ed1-2")

    def test_empty_env_falls_back(self):
        os.environ["ED_TAG_TEST2"] = ""
        self.assertNotEqual(B.build_tag("ED_TAG_TEST2"), "")

    def test_worktree_gitdir_file_is_followed(self):
        """⚠ 워크트리의 `.git` 은 **파일**이다 — 이걸 안 따라가면 전부 `local` 이 된다."""
        with TemporaryDirectory() as d:
            real = os.path.join(d, "realgit")
            os.makedirs(real)
            with open(os.path.join(real, "HEAD"), "w", encoding="utf-8") as f:
                f.write("ref: refs/heads/game/ss-ed1+2\n")
            fake_shared = os.path.join(d, "repo", "shared")
            os.makedirs(fake_shared)
            with open(os.path.join(d, "repo", ".git"), "w", encoding="utf-8") as f:
                f.write(f"gitdir: {real}\n")
            with open(B.__file__, encoding="utf-8") as f:
                src = f.read()
            with open(os.path.join(fake_shared, "bt_probe.py"), "w", encoding="utf-8") as f:
                f.write(src)
            sys.path.insert(0, fake_shared)
            try:
                import bt_probe

                os.environ.pop("ED_BUILD_TAG", None)
                self.assertEqual(bt_probe.build_tag(), "ss-ed1-2")
            finally:
                sys.path.remove(fake_shared)
                sys.modules.pop("bt_probe", None)


if __name__ == "__main__":
    unittest.main()
