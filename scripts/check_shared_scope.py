#!/usr/bin/env python3
"""게임 브랜치가 **공용 영역을 건드렸는가** — 플랫폼 병행의 안전장치.

## 왜

게임 트리(`games/<타이틀>/`)끼리는 안 겹친다 — 디스크 이미지가 다르니 물리적으로 독립이다.
겹치는 건 **공용**뿐이다:

    shared/          조판(krwrap) · 조사 · SJIS · ISO9660
    scripts/         진입점
    .claude/skills/  절차
    docs/            체크리스트 · reference

여기를 게임 브랜치에서 고치면 **다른 게임이 조용히 바뀐다.** 조판 지문이 잡긴 하지만
그건 **사후**다 — 다른 게임 세션이 자기 지문이 깨진 걸 보고서야 안다.

## 규칙 (유저 확정 2026-08-18)

**공용은 `main` 에서만 고친다.** 게임 브랜치에서 필요하면 main 에 먼저 넣고 받아 온다.

⚠ **게이트가 아니다** — 급할 땐 어길 수 있어야 한다(그리고 어긴 걸 알아야 한다).
수치만 보고하고, 어겼으면 무엇을 왜 고쳤는지 커밋 메시지에 남긴다.

  python3 scripts/check_shared_scope.py            # 현재 브랜치가 main 대비 무엇을 건드렸나
  python3 scripts/check_shared_scope.py --base X   # 기준을 바꾼다
"""

import argparse
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = ("shared/", "scripts/", ".claude/", "docs/", "CLAUDE.md")


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
    hit = [f for f in files if f.startswith(SHARED)]
    game = [f for f in files if f.startswith("games/")]
    own = f"games/{br[len('game/') :]}/"
    other = [f for f in game if not f.startswith(own)]
    print(f"  브랜치 {br} — 바뀐 파일 {len(files)} (자기 게임 {len(game) - len(other)})")
    if hit:
        print(f"  ⚠ **공용 영역 {len(hit)}건** — 공용은 `main` 에서 고치고 받아 온다")
        for f in hit[:8]:
            print(f"      {f}")
    if other:
        print(f"  🔴 **남의 게임 {len(other)}건** — 이건 거의 사고다")
        for f in other[:5]:
            print(f"      {f}")
    if not hit and not other:
        print("  ✅ 자기 게임만 만졌다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
