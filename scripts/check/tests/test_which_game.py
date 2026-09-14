"""「지금 어느 게임인가」 정본의 회귀 — 목록과 **그 목록을 정한 근거**가 같이 맞아야 한다.

🔴 지키는 것: `--all`(진짜 전부 보고 싶다)과 main 의 무인자 폴백(그냥 지금 게임을 모른다)이
   **같은 목록을 내면서 뜻이 다르다.** 부르는 쪽이 둘을 못 가르면 공용 한 줄 고치고
   main 에서 커밋하려다 남의 게임 빌드에 막힌다(2026-08-24 실측).
"""

import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))  # scripts/check/tests → 루트
SH = os.path.join(ROOT, "scripts", "check", "which_game.sh")


def run(*args):
    out = subprocess.run(
        ["sh", SH, *args], capture_output=True, text=True, check=True, cwd=ROOT
    ).stdout
    return [x for x in out.split("\n") if x]


def game_dirs():
    """`games/` 아래 게임 목록 — **정본(`which_game.sh`)이 하는 것과 똑같이** 센다.

    정본은 `ls "$ROOT/games"` 라 **숨김 파일만** 빠진다. 여기서 그보다 엄격하게(예: 디렉터리만)
    세면 정본이 낼 답을 테스트가 틀렸다고 하게 된다 — 어긋나는 쪽이 어디든 결과는 같다.
    ⚠ 날 `os.listdir` 로 대면 Finder 가 떨군 `games/.DS_Store` 하나에 게이트가 빨간불이 된다
    (2026-08-26 실측). 늘 빨간불인 게이트는 아무도 안 본다.
    """
    d = os.path.join(ROOT, "games")
    return sorted(x for x in os.listdir(d) if not x.startswith("."))


def branch():
    return subprocess.run(
        ["git", "-C", ROOT, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,  # git 이 없거나 레포가 아닐 수도 있다 — 그 경우도 fallback 이 맞다
    ).stdout.strip()


def game_of(br):
    """브랜치 이름 → 게임 이름. **정본이 하는 것과 똑같이** 꼬리표를 벗긴다.

    🔴 여기서 「`game/` 만 떼면 게임 이름」이라고 다시 쓰면 **정본이 낸 맞는 답을 테스트가
    틀렸다고 한다** — `game/<게임>-re` 워크트리에서 실제로 그랬다(ps1-ed1+2-re 가 잡았다).
    같은 파일 안의 `game_dirs()` 가 이미 같은 규율을 목록 쪽에 적어 뒀는데, 브랜치 쪽엔
    안 따랐던 것이다. **4-D — 같은 지식이 두 곳에 있으면 갈린다.**
    """
    g = br[len("game/") :]
    while "-" in g and not os.path.isdir(os.path.join(ROOT, "games", g)):
        g = g.rsplit("-", 1)[0]
    return g if os.path.isdir(os.path.join(ROOT, "games", g)) else br[len("game/") :]


class TestWhichGame(unittest.TestCase):
    def test_all_은_games_아래_전부(self):
        self.assertEqual(run("--all"), game_dirs())

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
            self.assertEqual(games, [game_of(branch())])
        else:
            self.assertEqual(games, game_dirs())

    def test_무인자_결과는_늘_실재하는_게임이다(self):
        """🔴 이 한 줄이 함정의 피해면을 통째로 덮는다 — **어느 브랜치에 서 있든** 돈다.

        종전엔 `game/<게임>-re` 워크트리에서 정본이 `<게임>-re` 를 냈고, 부르는 쪽이 그걸
        조용히 통과시켜 **게이트가 하나도 안 돈 채 ✅** 가 찍혔다(2026-09-14 실측).
        ⚠ 이 검사는 **그 워크트리에 서 있을 때만** 그 사고를 본다 — 그래서 브랜치를 인자로
        줄 수 있는 `sandbox()` 갈래를 따로 둔다. 둘 다 있어야 덮인다.
        """
        for g in run():
            self.assertTrue(
                os.path.isdir(os.path.join(ROOT, "games", g)),
                f"정본이 실재하지 않는 게임을 냈다: {g} (브랜치 {branch()})",
            )

    def test_why_는_목록을_안_섞는다(self):
        """`--why` 는 근거 한 줄만 낸다 — 게임 이름이 같이 나오면 부르는 쪽이 오해한다."""
        for args in (["--why"], ["--why", "--all"], ["--why", "dos-ed2", "ss-ed3"]):
            self.assertEqual(len(run(*args)), 1, args)


def sandbox(tmp, branch, games):
    """정본 스크립트를 **가짜 레포**에 떠서 돌린다 — 브랜치 이름을 마음대로 줄 수 있다.

    `which_game.sh` 는 ROOT 를 **자기 경로**(scripts/check → ../..)에서 잡고 브랜치를
    `git -C $ROOT` 로 읽는다. 그래서 진짜 레포에서는 **지금 브랜치밖에 못 시험한다** —
    함정(`game/<게임>-re`)은 그 워크트리에 서 있을 때만 재현된다. 사본을 뜨면 둘 다 된다.
    """
    root = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(root, "scripts", "check"))
    for g in games:
        os.makedirs(os.path.join(root, "games", g))
    shutil.copy(SH, os.path.join(root, "scripts", "check", "which_game.sh"))

    def git(*a):
        subprocess.run(["git", "-C", root, *a], capture_output=True, check=True)

    git("init", "-q", "-b", branch)
    # ⚠ **커밋이 하나는 있어야 한다.** 갓 init 한 레포는 브랜치가 태어나기 전이라
    #   `rev-parse --abbrev-ref HEAD` 가 실패하고, 정본은 그걸 **fallback(전부)** 으로 읽는다
    #   — 꼬리표 시험이 조용히 「전부」를 보게 된다.
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "t")
    return root


def run_in(root, *args):
    out = subprocess.run(
        ["sh", os.path.join(root, "scripts", "check", "which_game.sh"), *args],
        capture_output=True,
        text=True,
        check=True,
        cwd=root,
    ).stdout
    return [x for x in out.split("\n") if x]


class TestWorktreeSuffix(unittest.TestCase):
    """🔴 한 게임을 두 세션이 나눠 맡으면 브랜치가 `game/<게임>-re` 처럼 꼬리를 단다.

    그대로 쓰면 `games/<게임>-re` 를 찾다 못 찾는데, 종전엔 `check.sh` 가 「게이트 없음」을
    찍고 **그대로 ✅ 커밋해도 되는 상태** 로 끝났다 — 초록이 「깨끗하다」가 아니라
    **「아무도 안 돌렸다」**였다(2026-09-14 실측).
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_꼬리표를_벗겨_실재하는_게임을_낸다(self):
        root = sandbox(self.tmp, "game/ps1-ed1+2-re", ["ps1-ed1+2", "ss-ed3"])
        self.assertEqual(run_in(root), ["ps1-ed1+2"])
        self.assertEqual(run_in(root, "--why"), ["branch"])

    def test_꼬리표가_여러_칸이어도_벗긴다(self):
        root = sandbox(self.tmp, "game/ps1-ed1+2-re-2", ["ps1-ed1+2"])
        self.assertEqual(run_in(root), ["ps1-ed1+2"])

    def test_꼬리표가_없으면_그대로(self):
        root = sandbox(self.tmp, "game/ss-ed3", ["ps1-ed1+2", "ss-ed3"])
        self.assertEqual(run_in(root), ["ss-ed3"])

    def test_이름이_하이픈을_품어도_안_깎는다(self):
        """⚠ 벗기기는 **실재할 때 멈춘다** — `ps1-ed1+2` 자체가 하이픈을 품는다."""
        root = sandbox(self.tmp, "game/pc98-ed1", ["pc98-ed1", "pc98"])
        self.assertEqual(run_in(root), ["pc98-ed1"])

    def test_꼬리표_브랜치에서도_why_와_목록이_맞는다(self):
        """⚠ 이 가지는 **꼬리표 붙은 브랜치에 서 있을 때만** 돈다 — main 에선 `fallback` 이라
        아예 안 지나간다. 진짜 레포의 같은 이름 검사는 그래서 이 자리를 못 본다."""
        root = sandbox(self.tmp, "game/ss-ed3-re", ["ss-ed3", "ps1-ed1+2"])
        self.assertEqual(run_in(root, "--why"), ["branch"])
        self.assertEqual(run_in(root), ["ss-ed3"])

    def test_끝내_못_찾으면_원래_이름을_낸다(self):
        """못 찾은 걸 **숨기지 않는다** — 부르는 쪽(`check.sh`·`test.sh`)이 실패로 친다."""
        root = sandbox(self.tmp, "game/없는게임", ["ps1-ed1+2"])
        self.assertEqual(run_in(root), ["없는게임"])


class TestNoGameIsSilent(unittest.TestCase):
    """🔴 없는 게임을 주면 **입구 둘 다 빨간불**이어야 한다 — 이게 함정의 실제 피해면이다.

    ⚠ `check.sh`·`test.sh` 는 **이 파일을 다시 돈다** — 아무 표식 없이 부르면 무한 재귀다
    (실제로 한 번 물렸다). 그래서 표식을 켜서 부르고, 표식이 있으면 이 검사만 건너뛴다.
    """

    GUARD = "ED_TEST_NO_RECURSE"

    @unittest.skipIf(os.environ.get("ED_TEST_NO_RECURSE"), "재귀 방지 — 바깥 회차가 이미 본다")
    def test_check_와_test_가_없는_게임에_실패한다(self):
        env = {**os.environ, self.GUARD: "1"}
        for entry in ("check.sh", "test.sh"):
            r = subprocess.run(
                ["sh", os.path.join(ROOT, "scripts", entry), "없는게임"],
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=env,
                timeout=600,
                check=False,  # 실패를 **기대**한다 — 여기서 던지면 검사 자체가 없어진다
            )
            self.assertNotEqual(r.returncode, 0, f"{entry} 가 없는 게임에 ✅ 를 찍었다")


if __name__ == "__main__":
    unittest.main()
