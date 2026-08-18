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
for t in check_tail_cut check_terms check_spellings check_forbidden check_proper_nouns check_battle_wrap check_jp_leak; do
  out=$("$PY" "$G/$t.py" 2>&1) || fail=1
  echo "$out" | tail -3 | sed 's/^/  /'
done
# ED2 는 아직 재삽입 체인 밖이라 빌드가 문안을 안 본다 — 예행으로 대신 본다.
# ⚠ **게이트로 안 세운다**(exit 코드를 안 본다) — 제어런 재현 불가처럼 「지금 못 고치는」
# 자리가 섞여 있다. 수치가 나빠지면 사람이 본다.
"$PY" "$G/check_ed2_reinsert.py" -q 2>&1 | tail -1 | sed 's/^/  /'
# ⚠ **블록 경계는 인게임 QA 를 마친 층에만 게이트로 건다.** ED2 를 체인에 올리자 붙음이
#   463곳 나왔는데(ED1 은 71곳을 다 고쳤다), 그건 「실패」가 아니라 「할 일」이다 —
#   늘 빨간불이면 아무도 안 본다(루트 CLAUDE.md). ED2 는 아래에서 수치만 본다.
ED1SCN=$(ls "$ROOT/games/ps1-ed1+2/script/" 2>/dev/null | sed -n 's/\(ED1SCN[0-9]*\)\.json/\1/p' | tr '\n' ' ')
out=$("$PY" "$G/check_block_join.py" $ED1SCN 2>&1) || fail=1
echo "$out" | tail -1 | sed 's/^/  /'
"$PY" "$G/check_block_join.py" $(for i in $(seq 1 13); do echo -n "ED2SCN$i "; done) 2>&1 | tail -1 | sed 's/^/  [ED2] /'
# ⚠ 탈락 없이도 원문이 남는 길이 있다 — 색 구간(`%c…%c`)을 못 채우면 그 구간이 원문
#   그대로 나간다(ED2 49블록 실측). 구조 게이트는 전부 초록이라 여기서만 잡힌다.
"$PY" "$G/check_jp_leak.py" --ed2 2>&1 | tail -1 | sed 's/^/  /'
# 조사 받침 일치 + 변수 뒤 병기 — **정발 원문 전량**을 본다. 배정된 문안만 보면 늦다:
#   오타는 아직 화면에 안 나온 엔트리에 있다가 배정이 진행되며 하나씩 올라온다
#   (실측 2026-08-17: 화면 코퍼스 0건인데 원문 전량엔 3건). 그래서 상주 게이트다.
out=$("$PY" "$G/check_josa_agreement.py" 2>&1) || fail=1
echo "$out" | grep -E '✅|❌' | sed 's/^/  /'
# 같은 화자·같은 JP 인데 문안이 갈리는 자리 — ⚠ **게이트로 안 세운다**(404블록이라 늘
#   빨간불이 된다). 블록마다는 멀쩡하고 **블록 사이**만 깨지는 부류라 다른 게이트가 못 본다.
"$PY" "$G/check_same_jp.py" 2>&1 | grep -E '⚠|✅|ℹ' | sed 's/^/  /'
# 조판 지문 — ⚠ **락도 관측 대장도 조판을 안 본다**(화자 + 창 본문만 해시). 줄바꿈 규칙을
# 건드리면 이미지는 바뀌는데 아무 알림도 안 뜬다. 플랫폼을 병행하면 그 구멍이 사고가 된다 —
# 다른 게임 작업 중 `shared/text/krwrap.py` 한 줄이 이 게임의 조판을 조용히 바꾼다.
# 게이트가 아니다(문안을 바꾸면 당연히 바뀐다) — **안 바꿨는데 뜨면 `shared/` 를 의심한다.**
"$PY" "$ROOT/scripts/typeset_fingerprint.py" 2>&1 | tail -3 | sed 's/^/  /'
# 게임 브랜치가 공용을 건드렸나 — 게이트가 아니다(급하면 어길 수 있어야 한다).
# 공용은 `main` 에서 고치고 받아 온다 — 여기서 고치면 다른 게임이 조용히 바뀐다.
"$PY" "$ROOT/scripts/check_shared_scope.py" 2>&1 | tail -4 | sed 's/^/  /'
# 어투 혼용(존대↔해라체) — 게이트가 아니다(한 창에 두 상대가 섞이는 정당한 자리가 있다).
"$PY" "$G/check_speech_level.py" 2>&1 | head -2 | sed 's/^/  /'

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
