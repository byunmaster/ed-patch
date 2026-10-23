#!/bin/sh
# 단위·회귀 테스트 — **공용 + 지금 게임**.
#
#   sh scripts/test.sh                # 브랜치가 가리키는 게임 (main 이면 전부)
#   sh scripts/test.sh ps1-ed1+2      # 게임을 골라서
#   sh scripts/test.sh --all          # 전 게임
#
# ⚠ **남의 게임 테스트를 돌리지 않는다**(유저 확정 2026-08-21). 게이트는 게임별로 갈라
#   놓고 테스트만 전역이었던 탓에, **새턴 워크트리에서 `check.sh` 가 ps1 테스트 때문에
#   빨간불**이었다 — ps1 의 `patch_opening_font` 가 임포트 시점에 정발 DOS 원본을 읽는데
#   그 트리는 `originals/jp/ss-ed1+2` 만 링크하기 때문이다. 자기 게임 것만 보면 안 겪는다.
#   ⚠ 늘 빨간불인 게이트는 아무도 안 본다 — 그게 이 분리의 진짜 이유다.
#
# ⚠ **원본(`originals/`)이 없어도 돌아야 한다.** 소장본 없는 머신·CI 에서도 회귀를 잡는 게
#   목적이라, 이미지가 필요한 검사는 합성 섹터로 한다. 원본이 필요한 검증은 빌드 쪽
#   (`build.py` 의 무변경 구간 대조 · `check_determinism.py`)이 맡는다.
# ⚠ pytest 를 안 쓴다 — 이 머신 `.venv` 에 없고, 테스트 파일이 직접 실행되게 돼 있다.
#
# 목록을 손으로 들지 않는다 — **자리로 찾는다**(새 게임·새 테스트가 저절로 딸려 온다):
#   공용   scripts/*/tests/test_*.py · shared/*/tests/test_*.py
#   게임   games/<게임>/tools/tests/test_*.py
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3

fail=0
ran=0

run() {
  [ -f "$1" ] || return 0   # 글롭이 안 맞으면 패턴 그대로 들어온다
  printf '\n=== %s\n' "${1#"$ROOT"/}"
  ran=$((ran + 1))
  if grep -q "__main__" "$1"; then
    "$PY" "$1" || fail=1
  else
    # 🔴 직접 실행 꼬리가 없는 파일은 그냥 돌리면 **정의만 하고 아무것도 안 돈 채 통과**한다
    #   (10-20 실측: unittest 클래스만 있고 꼬리가 없는 파일 다섯이 몇 주째 「통과」였다).
    #   꼬리에 기대지 않고 여기서 TestCase 와 맨 test_* 함수를 직접 모아 돌린다.
    "$PY" "$RUNNER" "$1" || fail=1
  fi
}

# `TEST_SHARED_ONLY=1` — 공용 테스트만(main 의 check.sh 가 쓴다: 게임 테스트는 따로 알림으로 돈다).
#   ⚠ 읽고 바로 지운다 — 남겨 두면 test.sh 를 부르는 테스트(없는 게임 검사 등)까지 물려받는다.
SHARED_ONLY=${TEST_SHARED_ONLY:-}
unset TEST_SHARED_ONLY
GAME_LIST=""
[ "$SHARED_ONLY" = 1 ] || GAME_LIST=$(sh "$ROOT/scripts/check/which_game.sh" "$@")

RUNNER=$(mktemp "${TMPDIR:-/tmp}/test-runner.XXXXXX.py")
trap 'rm -f "$RUNNER"' EXIT
cat > "$RUNNER" <<'EOF'
import os, runpy, sys, unittest
path = sys.argv[1]
sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
ns = runpy.run_path(path, run_name="__test__")
suite = unittest.TestSuite()
for v in ns.values():
    if isinstance(v, type) and issubclass(v, unittest.TestCase) and v.__module__ == "__test__":
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(v))
funcs = [v for k, v in ns.items() if k.startswith("test_") and callable(v) and not isinstance(v, type)]
for f in funcs:
    suite.addTest(unittest.FunctionTestCase(f))
if suite.countTestCases() == 0:
    print("❌ 테스트를 하나도 못 찾았다 — 이름이 test_* 인가?")
    sys.exit(1)
sys.exit(0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1)
EOF

# ⚠ 목록을 손으로 들지 않는다 — **자리로** 찾는다. `scripts/*/tests/` 까지 보는 이유는
#   테스트가 **검사 대상 옆**에 살기 때문이다(check/tests · 나중에 emu/tests …).
for t in "$ROOT"/scripts/*/tests/test_*.py "$ROOT"/shared/*/tests/test_*.py; do
  run "$t"
done

for g in $GAME_LIST; do
  # 🔴 **없는 게임이면 실패다.** 글롭이 안 맞으면 `run` 이 조용히 넘어가서, 이름을 잘못
  #   유도한 채로 **「✅ 전부 통과」** 가 찍힌다 — 초록이 「깨끗하다」가 아니라 「아무도 안
  #   돌렸다」가 되는 자리다(2026-09-14, `game/<게임>-re` 워크트리 실측).
  if [ ! -d "$ROOT/games/$g" ]; then
    printf '\n❌ 그런 게임이 없다: %s (sh scripts/check/which_game.sh --why)\n' "$g"
    fail=1
    continue
  fi
  for t in "$ROOT/games/$g"/tools/tests/test_*.py; do
    run "$t"
  done
done

if [ "$fail" -ne 0 ]; then
  printf '\n❌ 실패한 테스트가 있다\n'
  exit 1
fi
printf '\n✅ 전부 통과 (%s개 파일)\n' "$ran"
