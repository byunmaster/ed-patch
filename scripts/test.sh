#!/bin/sh
# 단위·회귀 테스트를 전부 돌린다.
#
#   sh scripts/test.sh
#
# ⚠ **원본(`originals/`)이 없어도 돌아야 한다.** 소장본 없는 머신·CI 에서도 회귀를 잡는 게
#   목적이라, 이미지가 필요한 검사는 합성 섹터로 한다. 원본이 필요한 검증은 빌드 쪽
#   (`build.py` 의 무변경 구간 대조 · `check_determinism.py`)이 맡는다.
# ⚠ pytest 를 안 쓴다 — 이 머신 `.venv` 에 없고, 테스트 파일이 직접 실행되게 돼 있다.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3

fail=0
for t in \
  "$ROOT/scripts/tests/test_devices.py" \
  "$ROOT/shared/glossary/tests/test_glossary.py" \
  "$ROOT/shared/text/tests/test_krwrap.py" \
  "$ROOT/shared/text/tests/test_josa.py" \
  "$ROOT/games/ps1-ed1+2/tools/tests/test_pipeline.py"
do
  [ -f "$t" ] || continue
  printf '\n=== %s\n' "${t#"$ROOT"/}"
  "$PY" "$t" || fail=1
done

if [ "$fail" -ne 0 ]; then
  printf '\n❌ 실패한 테스트가 있다\n'
  exit 1
fi
printf '\n✅ 전부 통과\n'
