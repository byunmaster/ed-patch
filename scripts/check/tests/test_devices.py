#!/usr/bin/env python3
"""공용 안전장치 자체의 회귀 — **장치가 도는 곳과 사고가 나는 곳이 어긋나지 않는가**.

게임별 회귀는 `games/<게임>/tools/tests/` 에 있다. 여기는 `scripts/` 의 공용 장치만 본다
(`main` 에서 고치는 코드는 `main` 에서 검산된다).
"""

import os
import sys

# scripts/check/tests/ 아래라 네 번 올라가야 레포 루트다
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# 검사 장치는 `scripts/check/` 에 산다(`scripts/` 는 입구만 둔다 — 저장소 맵 참조)
sys.path.insert(0, os.path.join(ROOT, "scripts", "check"))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_fingerprint_canon_is_visible_from_main():
    """🔴 조판 지문 정본이 `main` 에서 안 보이면 장치가 아니다.

    값은 **게임 아래**(`games/<게임>/typeset_fingerprint.json`)에 둔다 — 게임이 갱신할 때마다
    공용 파일을 건드리지 않게. 그런데 **공용(`shared/`)을 고치는 자리는 `main`** 이고,
    main 의 작업 트리엔 그 파일이 없다. 실측: main 에서 `⏭ 정본 없음` 만 뜨고 조용히
    넘어갔다 — 정작 위험한 자리에서만 안 도는 장치였다. 그래서 게임 브랜치에서 읽어 온다.
    """
    import typeset_fingerprint as T

    canon, src = T.load_canon("ps1-ed1+2")
    assert src, "ps1-ed1+2 조판 정본을 어디서도 못 읽었다 — main 에서 공용을 고치면 눈이 먼다"
    assert canon.get("ps1-ed1+2"), f"정본({src})이 비어 있다"


def test_fingerprint_freeze_does_not_copy_another_branch():
    """⚠ `--freeze` 가 남의 브랜치 값을 자기 작업 트리로 베끼면 안 된다.

    폴백은 **읽기 전용**이다 — 베끼면 그 게임을 빌드해 보지도 않고 정본을 세우게 된다.
    """
    src = _read("scripts", "check", "typeset_fingerprint.py")
    body = src[src.index("if a.freeze:") :]
    assert '!= "작업 트리"' in body[:400], "freeze 경로에 남의 브랜치 값 차단이 없다"


def test_fingerprint_prefers_the_games_own_typesetter():
    """게임마다 조판법이 다르니 **지문기는 게임이 든다** — 공용은 대조·동결만 안다.

    PS1 은 우리가 개행을 다 넣고(krwrap 14슬롯) 새턴은 **엔진이 글자 단위로 접는다**.
    이 지식을 공용 표에 박으면 새 게임이 늘 때마다 공용을 고치게 되고, 그게 바로
    루트 `CLAUDE.md` 가 막는 「게임 얘기가 공용으로 새는」 자리다.
    """
    src = _read("scripts", "check", "typeset_fingerprint.py")
    body = src[src.index("def fingerprint(") :]
    assert "typeset_fp.py" in body[: body.index("GAMES[game]")], (
        "게임 몫 지문기(`games/<게임>/tools/typeset_fp.py`)를 안 찾는다 — 표에 박게 된다"
    )


def test_shared_scope_watches_worktree_not_only_commits():
    """⚠ 커밋 *전에* 도는 검사가 커밋된 것만 보면 한 발 늦는다 — 작업 트리도 봐야 한다."""
    src = _read("scripts", "check", "check_shared_scope.py")
    assert "status" in src and "--porcelain" in src, "작업 트리를 안 본다"


def test_shared_scope_covers_every_shared_path():
    """공용으로 선언한 자리가 실제 디렉터리와 어긋나면 구멍이 난다.

    ⚠ 2026-08-24 에 바구니를 **둘로 갈랐다**(코드 = main 에서만 / 글 = 브랜치 OK).
    가르고 나면 실패 모드가 하나 는다 — **어느 바구니에도 없는 공용 경로**는 아무도 안 본다.
    그래서 ① 둘 다 실재하는가 ② 위험한 둘이 **코드 쪽**인가 ③ 겹치지 않는가 를 다 본다.
    특히 ②는 `shared/` 를 글 바구니로 옮기는 실수를 막는다 — 그러면 ⚠ 가 안 떠서
    **다른 게임이 조용히 바뀌는 걸 아무도 모른다.**
    """
    import check_shared_scope as C

    for p in C.CODE + C.PROSE:
        assert os.path.exists(os.path.join(ROOT, p.rstrip("/"))), f"공용 경로 없음: {p}"
    for d in ("shared/", "scripts/"):
        assert d in C.CODE, f"{d} 는 바이트를 만든다 — 코드 바구니여야 한다"
        assert not any(s.startswith(d) for s in C.PROSE), f"{d} 가 글 바구니에 있다"
    for d in ("docs/", "CLAUDE.md", ".claude/"):
        assert d in C.PROSE, f"{d} 가 글 목록에 없다"
    assert not set(C.CODE) & set(C.PROSE), "두 바구니가 겹친다"


def test_worktree_links_only_declared_originals():
    """⚠ 그 게임이 **선언한 원본만** 건다(유저 요청 2026-08-18).

    지역을 통째로 걸면 딴 게임 원본이 그 트리에서 보이는데, 도구가 엉뚱한 걸 읽어도
    **빌드는 통과한다** — 조용히 틀리는 쪽이다. 그리고 `originals/` 자체를 걸면
    `originals/originals` 가 된다(`README.md` 가 추적돼 디렉터리가 이미 있다).
    """
    src = _read("scripts", "worktree.sh")
    assert "originals.txt" in src, "선언 목록을 안 읽는다"
    assert 'ln -sfn "$ROOT/originals" ' not in src, "originals 를 통째로 건다"
    assert "for r in kr jp us eu" not in src, "지역을 통째로 건다"


def test_every_game_declares_its_originals():
    """목록이 없으면 워크트리에 원본이 하나도 안 걸린다 — 게임마다 있어야 한다.

    ⚠ **디렉터리 목록이 아니라 추적되는 파일로 센다**(2026-08-24). `games/<게임>/work/` 는
    gitignore 라 그 트리에서 한 번 빌드하면 **껍데기 디렉터리가 남는다.** 목록으로 세면
    그게 게임으로 잡혀 `originals.txt` 를 내놓으라고 하는데, 그 브랜치에 안 딸려온 게
    정상이다 — 실측으로 `main` 의 게이트가 `games/ss-ed3/work/` 하나 때문에 늘 빨간불이었다.
    """
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files", "games/"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.split("\n")
    names = sorted({f.split("/")[1] for f in tracked if f.startswith("games/") and "/" in f[6:]})
    games = os.path.join(ROOT, "games")
    for g in names:
        man = os.path.join(games, g, "originals.txt")
        assert os.path.exists(man), f"games/{g}/originals.txt 가 없다"
        items = [ln.split("#")[0].strip() for ln in _read("games", g, "originals.txt").split("\n")]
        items = [i for i in items if i]
        assert items, f"games/{g}/originals.txt 가 비었다"
        for i in items:
            # `<지역>/<타이틀>` 또는 지역만(`kr/`). 절대경로·상위 참조는 링크를 엉뚱한 데 건다
            assert not i.startswith("/") and ".." not in i, f"{g}: 수상한 항목 {i!r}"


def test_worktree_carries_derived_because_build_reads_it():
    """🔴 `work/derived/` 는 **빌드가 읽는 입력**이다 — 없으면 새 트리에서 빌드가 죽는다.

    그중 의미정렬 제안(`align/*.json`)은 **비결정적**이라 그 자리에서 다시 만들면 안 된다
    (머신이 다르면 다른 배정이 나온다 — 제1 원칙). 실측: 새 워크트리에서
    `derived/align/ED2_SCN2.json` 없음으로 빌드가 죽었다. 링크가 아니라 **복사**다 —
    빌드가 여기에 쓰면 두 트리가 섞이기 때문이다.
    """
    src = _read("scripts", "worktree.sh")
    assert "SRC_DERIVED" in src, "derived 를 안 챙긴다"
    assert "cp -an" in src, "복사가 아니거나 있는 것을 덮어쓴다"


def test_gitignore_covers_symlink_forms():
    """⚠ 워크트리에서 `vendor`·`.emucap`·`.venv` 는 **심볼릭 링크**다.

    `vendor/` 패턴은 디렉터리만 잡는다 — git 은 링크를 디렉터리로 보지 않아 **링크가 커밋에
    딸려 들어간다**(2026-08-18 실측: `vendor` 링크가 커밋됐다). `originals/originals` ·
    `derived/derived` 와 같은 계열의 함정이라, 슬래시 없는 줄도 함께 둔다.
    """
    ig = _read(".gitignore").split("\n")
    for name in ("vendor", ".emucap", ".venv"):
        assert name in ig, f".gitignore 에 `{name}` (슬래시 없는 줄)이 없다 — 링크가 새어 든다"


def test_checklist_sections_are_indexed_by_the_skill():
    """스킬의 목록은 **색인**이지 정본이 아니다 — 체크리스트 절과 어긋나면 안 된다."""
    import re

    cl = _read("docs", "patcher-checklist.md")
    sk = open(
        os.path.join(ROOT, ".claude", "skills", "patcher-safety", "SKILL.md"), encoding="utf-8"
    ).read()
    nums = [m.group(1) for m in re.finditer(r"^## ([\d\-A-B]+)\.", cl, re.MULTILINE)]
    assert nums, "체크리스트에서 절 번호를 못 읽었다"
    for n in nums:
        assert re.search(rf"^\s*{re.escape(n)}\.", sk, re.MULTILINE), (
            f"스킬 색인에 절 {n} 이 빠졌다"
        )


# ⚠ 새 테스트는 **이 줄 위에** 둔다 — 아래에 쓰면 수집이 안 된다.
if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for f in fns:
        try:
            f()
        except Exception as e:
            bad += 1
            print(f"  FAIL {f.__name__}: {e}")
    print(f"{len(fns) - bad}/{len(fns)} passed")
    sys.exit(1 if bad else 0)
