#!/bin/sh
# ⭐ **커밋 전에 이것 하나만** — 레포 전역 검사 + 지금 게임의 게이트.
#
#   sh scripts/check.sh                # 지금 브랜치가 가리키는 게임
#   sh scripts/check.sh ps1-ed1+2      # 게임을 골라서
#   sh scripts/check.sh --all          # 게이트가 있는 게임 전부
#
# ⚠ **여기엔 게임 얘기를 쓰지 않는다.** 2026-08-19 까지 이 파일은 78줄이었는데 그중 3줄만
#   공용이고 나머지는 전부 ps1-ed1+2 전용 검사기였다 — 「공용 진입점」이 아니라 **한 게임의
#   게이트가 공용 자리를 점유한 것**이었다. 값을 두 번 치렀다: dos-ed2 는 커밋 전 게이트가
#   **아예 없었고**(트랙이 둘인데 하나만 지켜졌다), ps1 브랜치에서 자기 게임 검사기를
#   추가하려면 **공용을 고쳐야 해서** 못 했다(브랜치 규약 위반). 게임 게이트는
#   `games/<게임>/check.sh` 로 내렸다.
#
# ⚠ 게임 게이트가 실패하면 **여기서 멈춘다** — 뒤 검사는 낡은 산출물을 보게 된다.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3

# 어느 게임인가 — 정본은 `scripts/check/which_game.sh` 다(테스트도 같은 답을 써야 한다).
GAMES=$(sh "$ROOT/scripts/check/which_game.sh" "$@")

# ⚠ 테스트도 **자기 게임 것만** 본다(유저 확정 2026-08-21). 게이트는 갈라 놓고 테스트만
#   전역이면, 원본을 안 링크한 워크트리에서 남의 게임 때문에 늘 빨간불이 된다(실측:
#   새턴 트리에서 ps1 의 정발 DOS 의존으로 실패). 늘 빨간불인 게이트는 아무도 안 본다.
echo "── 단위·회귀 테스트 (공용 + $(echo "$GAMES" | tr '\n' ' '))"
sh "$ROOT/scripts/test.sh" $GAMES >/dev/null \
  || { echo "❌ 테스트 실패 — sh scripts/test.sh $(echo "$GAMES" | tr '\n' ' ')"; exit 1; }
echo "  ✅ 통과"

fail=0
for g in $GAMES; do
  gate="$ROOT/games/$g/check.sh"
  if [ ! -f "$gate" ]; then
    # ⚠ **조용히 넘어가지 않는다.** 게이트가 없는 게임을 「통과」로 보이게 하면 그게 곧
    #   dos-ed2 가 여태 무방비였던 이유다.
    echo "── [$g]  ⚠ 게이트 없음 (games/$g/check.sh 를 만들어라)"
    continue
  fi
  echo "── [$g]"
  sh "$gate" || fail=1
done

# 게임 브랜치가 공용·남의 게임을 건드렸나 — 게이트가 아니다(급하면 어길 수 있어야 한다).
# 공용은 `main` 에서 고치고 받아 온다 — 게임 브랜치에서 고치면 다른 게임이 조용히 바뀐다.
echo "── 브랜치 범위"
"$PY" "$ROOT/scripts/check/check_shared_scope.py" 2>&1 | tail -4 | sed 's/^/  /'

[ "$fail" -eq 0 ] || { printf '\n⚠ 검사 중 실패가 있다 — 위 출력을 본다\n'; exit 1; }
printf '\n✅ 커밋해도 되는 상태\n'
