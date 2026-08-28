#!/usr/bin/env python3
"""게임 브랜치가 **공용 영역을 건드렸는가** — 플랫폼 병행의 안전장치.

## 왜

게임 트리(`games/<타이틀>/`)끼리는 안 겹친다 — 디스크 이미지가 다르니 물리적으로 독립이다.
겹치는 건 **공용**뿐인데, 공용이 다 같은 무게는 아니다:

    shared/          조판(krwrap) · 조사 · SJIS · ISO9660   ← 🔴 바이트를 만든다
    scripts/         진입점                                  ← 🔴 바이트를 만든다
    shared/glossary/ 고유명사 정본                           ← ⚠ 데이터 (바이트는 만든다)
    docs/            체크리스트 · reference                  ← 글
    CLAUDE.md        작업 규칙                               ← 글
    .claude/skills/  절차                                    ← 글

앞의 둘을 게임 브랜치에서 고치면 **다른 게임이 조용히 바뀐다.** 조판 지문이 잡긴 하지만
그건 **사후**다 — 다른 게임 세션이 자기 지문이 깨진 걸 보고서야 안다.

뒤의 셋은 **바이트를 안 만든다.** 틀리면 사람이 읽고 반박하고, 충돌이 나도 산문 충돌이라
잘못 풀어도 이미지가 안 깨진다. **조용히 틀리지 않는 것**이 기준이다.

가운데 하나는 어느 쪽도 아니다 — **정본은 데이터지 코드가 아니다.** 이름을 어떻게 쓰는지는
각 게임의 패처가 정하고, 표기가 틀리면 **그 게임의 게이트와 인게임에서 드러난다.** 그래서
브랜치에서 고쳐도 된다(2026-08-29). ⚠ 그래도 **바이트는 만든다** — 이름이 길어지면 칸을
넘고, 표기를 바꾸면 문안에 글자로 박힌 자리가 따라와야 한다. 그건 세어서 보여 준다.

## 규칙 (유저 확정 2026-08-18 · 문서 분리 2026-08-24)

**`shared/`·`scripts/` 는 `main` 에서만 고친다.** 게임 브랜치에서 필요하면 main 에 먼저
넣고 받아 온다. **`docs/`·`CLAUDE.md`·`.claude/` 는 게임 브랜치에서 고쳐도 된다** —
머지로 올라오면 `--first-parent main` 에서 한 줄이 되므로 main 이 오히려 읽기 좋아진다.

**`shared/glossary/` 도 브랜치에서 고친다**(유저 확정 2026-08-29). 정본 손질을 main 의
심부름 커밋으로 만들지 않으려는 것이다 — 실측으로 한 세션의 정본 작업이 main 에 독립
커밋 셋을 만들었다. ⚠ 대신 **뒤처리를 같은 브랜치가 진다**: 문안에 박힌 표기 · 다른 게임과
갈리는 자리(PS1 은 아직 자기 표를 든다)를 같이 커밋하거나, 못 맞추면 커밋 메시지에 적는다.

⚠ **게이트가 아니다** — 급할 땐 어길 수 있어야 한다(그리고 어긴 걸 알아야 한다).
수치만 보고하고, 어겼으면 무엇을 왜 고쳤는지 커밋 메시지에 남긴다.

  python3 scripts/check/check_shared_scope.py            # 현재 브랜치가 main 대비 무엇을 건드렸나
  python3 scripts/check/check_shared_scope.py --base X   # 기준을 바꾼다
"""

import argparse
import os
import subprocess
import sys

# scripts/check/ 아래라 세 번 올라가야 레포 루트다
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 🔴 게임 브랜치에서 고치면 **조용히** 다른 게임의 바이트가 바뀐다 — main 에서만
CODE = ("shared/", "scripts/")
# ⚠ 그 안에서 **정본만 예외**다(2026-08-29) — 데이터라 브랜치에서 고친다. 다만 바이트를
#   만드니 「고쳐도 된다」로 끝내지 않고 **뒤처리를 상기시킨다**(문안 · 다른 게임 갈림).
DATA = ("shared/glossary/",)
# 글 — 게임 브랜치에서 고쳐도 된다(2026-08-24). 세어서 보여만 주고 ⚠ 는 안 띄운다.
PROSE = ("docs/", "CLAUDE.md", ".claude/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="main")
    a = ap.parse_args()
    br = subprocess.run(
        ["git", "branch", "--show-current"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    if not br.startswith("game/"):
        print(f"  ⏭ 게임 브랜치가 아니다({br or 'detached'}) — 건너뜀")
        return 0
    r = subprocess.run(
        ["git", "diff", "--name-only", f"{a.base}...HEAD"], cwd=REPO, capture_output=True, text=True
    )
    if r.returncode:
        print(f"  ⏭ 기준 `{a.base}` 을 못 찾음 — 건너뜀")
        return 0
    files = [f for f in r.stdout.split("\n") if f.strip()]
    # ⚠ **작업 트리도 본다** — `check.sh` 는 커밋 *전에* 도는 게이트다. 커밋된 것만 보면
    # 「지금 고치고 있는 공용 파일」을 못 잡아 알림이 한 발 늦는다.
    w = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True
    ).stdout
    for ln in w.split("\n"):
        if len(ln) > 3:
            f = ln[3:].split(" -> ")[-1].strip()
            if f and f not in files:
                files.append(f)
    data = [f for f in files if f.startswith(DATA)]
    hit = [f for f in files if f.startswith(CODE) and not f.startswith(DATA)]
    prose = [f for f in files if f.startswith(PROSE)]
    game = [f for f in files if f.startswith("games/")]
    own = f"games/{br[len('game/') :]}/"
    other = [f for f in game if not f.startswith(own)]
    print(f"  브랜치 {br} — 바뀐 파일 {len(files)} (자기 게임 {len(game) - len(other)})")
    if hit:
        print(
            f"  ⚠ **공용 코드 {len(hit)}건** — `shared/`·`scripts/` 는 main 에서 고치고 받아 온다"
        )
        for f in hit[:8]:
            print(f"      {f}")
    if data:
        print(f"  ⚠ 공용 정본 {len(data)}건 — 브랜치에서 고쳐도 된다(2026-08-29).")
        print("      다만 **바이트를 만든다** — 문안에 박힌 표기와 다른 게임 갈림을 같이 커밋한다")
    if prose:
        print(f"  ℹ 공용 문서 {len(prose)}건 — 브랜치에서 고쳐도 된다(머지로 올라간다)")
    if other:
        print(f"  🔴 **남의 게임 {len(other)}건** — 이건 거의 사고다")
        for f in other[:5]:
            print(f"      {f}")
    if not hit and not other:
        print("  ✅ 공용 코드는 안 건드렸다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
