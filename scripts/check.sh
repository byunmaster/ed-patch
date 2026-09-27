#!/bin/sh
# ⭐ **커밋 전에 이것 하나만** — 레포 전역 검사 + 지금 게임의 게이트.
#
#   sh scripts/check.sh                # 지금 브랜치가 가리키는 게임
#   sh scripts/check.sh ps1-ed1+2      # 게임을 골라서
#   sh scripts/check.sh --all          # 게이트가 있는 게임 전부
#
# ⚠ **main 에서는 게임 게이트를 안 돌린다**(유저 지적 2026-08-24). main 은 공용을 고치는
#   자리이고 그 트리엔 **원본도 파생물도 없는 게 정상**이다 — 남의 게임 빌드를 돌리면
#   늘 빨간불이 된다(실측: ps1 의 `derived/align/*` 이 없어 main 커밋이 매번 막혔다).
#   공용이 게임을 깨뜨리는지는 **조판 지문**과 각 게임 브랜치의 게이트가 잡는다.
#   정말 전부 보고 싶으면 `--all` 로 **명시**한다 — 그때만 돈다.
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
# 그 목록을 **어떻게** 정했나 — `--all`·이름 지정(explicit) / 게임 브랜치(branch) /
# main 에서 그냥 모르는 것(fallback). 셋을 못 가르면 위 ⚠ 의 사고가 난다.
WHY=$(sh "$ROOT/scripts/check/which_game.sh" --why "$@")

# ⚠ 테스트도 **자기 게임 것만** 본다(유저 확정 2026-08-21). 게이트는 갈라 놓고 테스트만
#   전역이면, 원본을 안 링크한 워크트리에서 남의 게임 때문에 늘 빨간불이 된다(실측:
#   새턴 트리에서 ps1 의 정발 DOS 의존으로 실패). 늘 빨간불인 게이트는 아무도 안 본다.
echo "── 단위·회귀 테스트 (공용 + $(echo "$GAMES" | tr '\n' ' '))"
# 성공이면 조용히, 실패면 **무엇이** 틀렸는지 꼬리를 보인다 — 「❌ 테스트 실패」 한 줄로는
#   다시 돌려 봐야 원인을 안다(pce 제보 2026-09-27).
tout=$(sh "$ROOT/scripts/test.sh" $GAMES 2>&1) || {
  echo "❌ 테스트 실패 — sh scripts/test.sh $(echo "$GAMES" | tr '\n' ' ')"
  echo "$tout" | tail -20 | sed 's/^/     /'
  exit 1
}
echo "  ✅ 통과"

fail=0
if [ "$WHY" = "fallback" ]; then
  echo "── 게임 게이트"
  echo "  ⏭ main 이다 — 게임 게이트는 건너뛴다(원본·파생물이 없는 게 정상이다)"
  echo "     전부 보려면: sh scripts/check.sh --all   ·  하나만: sh scripts/check.sh <게임>"
  GAMES=""
fi
for g in $GAMES; do
  gate="$ROOT/games/$g/check.sh"
  if [ ! -f "$gate" ]; then
    # 🔴 **실패로 친다.** 종전엔 줄만 찍고 `continue` 했는데, 그러면 맨 끝에서
    #   **✅ 커밋해도 되는 상태** 가 찍힌다 — 초록이 「깨끗하다」가 아니라 **「아무도 안
    #   돌렸다」**가 되는 자리다(2026-09-14 실측: `game/ps1-ed1+2-re` 워크트리에서 무인자로
    #   돌리면 `games/ps1-ed1+2-re` 를 찾다 못 찾고 그대로 ✅ 였다).
    #   ⚠ 게이트 없는 게임을 조용히 「통과」로 보이게 한 것이 dos-ed2 가 여태 무방비였던 이유다.
    if [ ! -d "$ROOT/games/$g" ]; then
      echo "── [$g]  ❌ 그런 게임이 없다 — 이름을 확인해라 (sh scripts/check/which_game.sh --why)"
    else
      echo "── [$g]  ❌ 게이트 없음 (games/$g/check.sh 를 만들어라)"
    fi
    fail=1
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
