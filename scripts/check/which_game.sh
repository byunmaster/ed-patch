#!/bin/sh
# 「지금 어느 게임인가」를 정하는 **정본**. 게임 이름을 한 줄에 하나씩 낸다.
#
#   sh scripts/check/which_game.sh              # 브랜치(game/<타이틀>)에서 유도, main 이면 전부
#   sh scripts/check/which_game.sh --all        # 전부
#   sh scripts/check/which_game.sh ps1-ed1+2    # 골라서 (여럿 가능)
#   sh scripts/check/which_game.sh --why …      # **어떻게** 정했나 — explicit|branch|fallback
#
# ⚠ `--why` 가 있는 이유: 「전부」가 나오는 경로가 둘인데 **뜻이 다르다.** `--all` 은
#   「진짜 전부 보고 싶다」이고, main 에서 인자 없이 부른 것(`fallback`)은 **그냥 지금
#   게임을 모르는 것**이다. 부르는 쪽이 둘을 못 가르면, 공용 한 줄 고치고 main 에서
#   커밋하려다 **남의 게임 빌드가 실패해서 막힌다**(2026-08-24 실측: ps1 의 파생물이 그
#   트리에 없어 main 게이트가 늘 빨간불이었다).
#
# ⚠ **새 규약을 만들지 않는다** — `common.BUILD_TAG` 가 이미 쓰는 방식 그대로다.
# ⚠ 소비자가 둘(`check.sh` · `test.sh`)이라 뽑았다. 각자 유도하게 두면 **둘이 다른 답을
#   낼 수 있고**, 그러면 「게이트는 이 게임을 봤는데 테스트는 저 게임을 봤다」가 된다.
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)   # scripts/check → 레포 루트

WHY=0
if [ "${1:-}" = "--why" ]; then WHY=1; shift; fi

say() { [ "$WHY" -eq 1 ] && echo "$1" || cat; }

case "${1:-}" in
  --all) ls "$ROOT/games" | say explicit ;;
  "")
    br=$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
    case "$br" in
      game/*)
        # ⚠ **워크트리 꼬리표를 벗긴다.** 한 게임을 두 세션이 나눠 맡으면 브랜치가
        #   `game/<타이틀>-re` 처럼 꼬리를 단다(`worktree.sh --as`). 그대로 쓰면
        #   `games/<타이틀>-re` 를 찾다 못 찾고 **「게이트 없음」으로 넘어가며 ✅ 를 찍는다**
        #   — 초록이 「깨끗하다」가 아니라 **「아무도 안 돌렸다」**가 된다(2026-09-14 실측).
        g="${br#game/}"
        while [ ! -d "$ROOT/games/$g" ]; do
          case "$g" in
            *-*) g="${g%-*}" ;;                # 꼬리를 한 칸씩 벗긴다
            *)   g="${br#game/}"; break ;;     # 못 찾으면 원래 이름으로 — 아래가 경고한다
          esac
        done
        echo "$g" | say branch
        ;;
      *) ls "$ROOT/games" | say fallback ;;
    esac
    ;;
  *) for g in "$@"; do echo "$g"; done | say explicit ;;
esac
