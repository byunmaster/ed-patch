#!/bin/sh
# 「지금 어느 게임인가」를 정하는 **정본**. 게임 이름을 한 줄에 하나씩 낸다.
#
#   sh scripts/which_game.sh              # 브랜치(game/<타이틀>)에서 유도, main 이면 전부
#   sh scripts/which_game.sh --all        # 전부
#   sh scripts/which_game.sh ps1-ed1+2    # 골라서 (여럿 가능)
#
# ⚠ **새 규약을 만들지 않는다** — `common.BUILD_TAG` 가 이미 쓰는 방식 그대로다.
# ⚠ 소비자가 둘(`check.sh` · `test.sh`)이라 뽑았다. 각자 유도하게 두면 **둘이 다른 답을
#   낼 수 있고**, 그러면 「게이트는 이 게임을 봤는데 테스트는 저 게임을 봤다」가 된다.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)

case "${1:-}" in
  --all) ls "$ROOT/games" ;;
  "")
    br=$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
    case "$br" in
      game/*) echo "${br#game/}" ;;
      *) ls "$ROOT/games" ;;
    esac
    ;;
  *) for g in "$@"; do echo "$g"; done ;;
esac
