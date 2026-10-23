"""check_real_build — 산출물 판정(굽기 자체는 안 돈다)과, 칸 초과 이름이 실제 빌드를 죽이는지."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_real_build as C


def _good(d: Path) -> None:
    b = b"rom"
    (d / C.KR_NAME).write_bytes(b)
    (d / "manifest.json").write_text(json.dumps({"output_sha1": hashlib.sha1(b).hexdigest()}))


class Verify(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_ok(self):
        _good(self.d)
        self.assertIsNone(C.verify(self.d, 0))

    def test_rc(self):
        _good(self.d)
        self.assertIn("종료 코드", C.verify(self.d, 1))  # 낡은 롬이 남아 있어도 rc 가 막는다

    def test_no_output(self):
        self.assertIn("기대와 다르다", C.verify(self.d, 0))

    def test_failed_artifact(self):
        _good(self.d)
        (self.d / (C.KR_NAME + ".failed")).write_bytes(b"x")
        self.assertIn("실패 산출물", C.verify(self.d, 0))

    def test_hash_mismatch(self):
        _good(self.d)
        (self.d / C.KR_NAME).write_bytes(b"other")
        self.assertIn("해시", C.verify(self.d, 0))

    def test_clean_removes_stale(self):
        _good(self.d)
        (self.d / (C.KR_NAME + ".failed")).write_bytes(b"x")
        self.assertEqual(C.clean(self.d), 3)
        self.assertEqual(list(self.d.iterdir()), [])


class Main(unittest.TestCase):
    """굽기(`build.py --kr`)를 흉내 내서 main() 의 종합 판정을 본다 — 칸 초과 이름이 쓰기 경로를 죽이는 상황."""

    def _run(self, fake_build):
        import common

        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        out = d / common.BUILD_TAG
        out.mkdir()
        _good(out)  # 낡은 롬이 남아 있다
        saved = (common.BUILD_DIR, C.subprocess.run)
        common.BUILD_DIR = d
        C.subprocess.run = lambda *a, **k: fake_build(out)
        try:
            return C.main(), out
        finally:
            common.BUILD_DIR, C.subprocess.run = saved

    def test_build_dies_with_stale_rom_left_is_failure(self):
        # 정본 이름이 칸을 넘어 빌드가 죽었다 — 옛 롬이 있어도 초록이면 안 된다
        rc, out = self._run(lambda o: subprocess.CompletedProcess([], 1))
        self.assertEqual(rc, 1)
        self.assertFalse((out / C.KR_NAME).exists())  # 낡은 롬은 먼저 지웠다

    def test_build_ok_writes_image(self):
        def ok(o):
            _good(o)
            return subprocess.CompletedProcess([], 0)

        rc, _ = self._run(ok)
        self.assertEqual(rc, 0)

    def test_rc0_but_no_output_is_failure(self):
        rc, _ = self._run(lambda o: subprocess.CompletedProcess([], 0))
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
