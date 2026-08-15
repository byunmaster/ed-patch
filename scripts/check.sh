#!/bin/sh
# 커밋 전에 이것 하나만 돌린다 — 빌드 + 화면에 나가는 것들.
#
#   sh scripts/check.sh
#
# ⚠ **빌드만으로는 절반이다.** 빌드는 구조(무변경 구간·창 수·인자·확정 락)를 보고,
#   조판·이름창·표기는 못 본다. 둘을 갈라 두면 한쪽만 돌리게 되므로 여기서 묶는다.
#
# ⚠ 빌드가 실패하면 산출물이 `*.failed` 로 무효화되고 여기서 멈춘다 — 뒤 검사는
#   낡은 이미지를 보게 되므로 이어서 돌리지 않는다.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3
G="$ROOT/games/ps1-ed1+2/tools"

echo "── 빌드 (구조 계약 · 무변경 구간 · 일본어 잔존 · 인자 센티널)"
"$PY" "$G/build.py" >/dev/null || { echo "❌ 빌드 실패 — 위 명령을 직접 돌려 사유를 본다"; exit 1; }
echo "  ✅ 통과"

echo "── 단위·회귀 테스트"
sh "$ROOT/scripts/test.sh" >/dev/null || { echo "❌ 테스트 실패 — sh scripts/test.sh"; exit 1; }
echo "  ✅ 통과"

# ⚠ **이름창은 정본으로 옮긴 씬만 본다.** 안 옮긴 씬은 아직 정발 배정이라 후보가 잔뜩
#   뜨는데, 그건 「실패」가 아니라 「할 일」이다. 게이트가 늘 빨간불이면 보지 않게 된다.
DONE=$(ls "$ROOT/games/ps1-ed1+2/script/" 2>/dev/null | sed -n 's/\(ED1SCN[0-9]*\)\.json/\1/p' | tr '\n' ' ')

fail=0
for t in check_tail_cut check_block_join check_terms check_spellings check_forbidden check_proper_nouns check_battle_wrap; do
  out=$("$PY" "$G/$t.py" 2>&1) || fail=1
  echo "$out" | tail -3 | sed 's/^/  /'
done
# ED2 는 아직 재삽입 체인 밖이라 빌드가 문안을 안 본다 — 예행으로 대신 본다.
# ⚠ **게이트로 안 세운다**(exit 코드를 안 본다) — 제어런 재현 불가처럼 「지금 못 고치는」
# 자리가 섞여 있다. 수치가 나빠지면 사람이 본다.
"$PY" "$G/check_ed2_reinsert.py" -q 2>&1 | tail -1 | sed 's/^/  /'

if [ -n "$DONE" ]; then
  # shellcheck disable=SC2086
  out=$("$PY" "$G/check_speakers.py" $DONE 2>&1) || fail=1
  echo "$out" | tail -2 | sed 's/^/  /'
  echo "  (이름창은 정본 씬만: $DONE)"
fi

echo
"$PY" "$G/status.py"
[ "$fail" -eq 0 ] || { echo "\n⚠ 검사 중 실패가 있다 — 위 출력을 본다"; exit 1; }
echo "\n✅ 커밋해도 되는 상태"
