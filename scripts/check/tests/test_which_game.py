"""「지금 어느 게임인가」 정본의 회귀 — 목록과 **그 목록을 정한 근거**가 같이 맞아야 한다.

🔴 지키는 것: `--all`(진짜 전부 보고 싶다)과 main 의 무인자 폴백(그냥 지금 게임을 모른다)이
   **같은 목록을 내면서 뜻이 다르다.** 부르는 쪽이 둘을 못 가르면 공용 한 줄 고치고
   main 에서 커밋하려다 남의 게임 빌드에 막힌다(2026-08-24 실측).
"""

import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))  # scripts/check/tests → 루트
SH = os.path.join(ROOT, "scripts", "check", "which_game.sh")


def run(*args):
    out = subprocess.run(
        ["sh", SH, *args], capture_output=True, text=True, check=True, cwd=ROOT
    ).stdout
    return [x for x in out.split("\n") if x]


def branch():
    return subprocess.run(
        ["git", "-C", ROOT, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,  # git 이 없거나 레포가 아닐 수도 있다 — 그 경우도 fallback 이 맞다
    ).stdout.strip()


class TestWhichGame(unittest.TestCase):
    def test_all_은_games_아래_전부(self):
        self.assertEqual(run("--all"), sorted(os.listdir(os.path.join(ROOT, "games"))))

    def test_이름을_주면_그대로(self):
        self.assertEqual(run("ss-ed3"), ["ss-ed3"])
        self.assertEqual(run("dos-ed2", "ss-ed3"), ["dos-ed2", "ss-ed3"])

    def test_why_는_근거를_낸다(self):
        self.assertEqual(run("--why", "--all"), ["explicit"])
        self.assertEqual(run("--why", "ss-ed3"), ["explicit"])

    def test_why_가_지금_브랜치와_맞는다(self):
        """게임 브랜치면 `branch`, 그 밖(main·detached)이면 `fallback`."""
        want = "branch" if branch().startswith("game/") else "fallback"
        self.assertEqual(run("--why"), [want])

    def test_why_와_목록이_같은_판단을_쓴다(self):
        """🔴 둘이 어긋나면 「게이트는 이 게임을 봤는데 근거는 저 게임」이 된다."""
        games, why = run(), run("--why")[0]
        if why == "branch":
            self.assertEqual(games, [branch()[len("game/") :]])
        else:
            self.assertEqual(games, sorted(os.listdir(os.path.join(ROOT, "games"))))

    def test_why_는_목록을_안_섞는다(self):
        """`--why` 는 근거 한 줄만 낸다 — 게임 이름이 같이 나오면 부르는 쪽이 오해한다."""
        for args in (["--why"], ["--why", "--all"], ["--why", "dos-ed2", "ss-ed3"]):
            self.assertEqual(len(run(*args)), 1, args)


if __name__ == "__main__":
    unittest.main()
