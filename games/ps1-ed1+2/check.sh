#!/bin/sh
# 이 게임의 커밋 전 게이트 — 빌드 + 화면에 나가는 것들.
#
#   sh games/ps1-ed1+2/check.sh      (보통은 `sh scripts/check.sh` 가 부른다)
#
# ⚠ **빌드만으로는 절반이다.** 빌드는 구조(무변경 구간·창 수·인자·확정 락)를 보고,
#   조판·이름창·표기는 못 본다. 둘을 갈라 두면 한쪽만 돌리게 되므로 여기서 묶는다.
# ⚠ 빌드가 실패하면 산출물이 `*.failed` 로 무효화되고 여기서 멈춘다 — 뒤 검사는
#   낡은 이미지를 보게 되므로 이어서 돌리지 않는다.
# ⚠ 게이트는 **지금 고칠 수 있는 것**만 실패로 친다. 「할 일」을 실패로 세우면 늘 빨간불이
#   되고, 늘 빨간불이면 아무도 안 본다(루트 CLAUDE.md).
#
# ⚠ 단위·회귀 테스트(`scripts/test.sh`)와 브랜치 범위 검사는 **여기 없다** — 레포 전역이라
#   `scripts/check.sh` 가 맡는다.
set -eu

G=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$G/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3
T="$G/tools"

echo "  ── 빌드 (구조 계약 · 무변경 구간 · 일본어 잔존 · 인자 센티널)"
"$PY" "$T/build.py" >/dev/null || { echo "  ❌ 빌드 실패 — python3 games/ps1-ed1+2/tools/build.py"; exit 1; }
echo "     ✅ 통과"

# ⚠ **이름창·블록 경계는 정본으로 옮긴 씬만 본다.** 안 옮긴 씬은 아직 정발 배정이라 후보가
#   잔뜩 뜨는데, 그건 「실패」가 아니라 「할 일」이다.
SCN=$(ls "$G/script/" 2>/dev/null | sed -n 's/\(ED1SCN[0-9]*\)\.json/\1/p' | tr '\n' ' ')

fail=0
for t in check_tail_cut check_terms check_spellings check_forbidden check_proper_nouns check_battle_wrap check_punct check_name_echo check_onomatopoeia check_pointer_tables check_iso_layout check_readback check_movie_coverage check_card_centering check_window_nl check_log_register; do
  out=$("$PY" "$T/$t.py" 2>&1) || fail=1
  echo "$out" | tail -3 | sed 's/^/     /'
done

# 일본어 잔존 — ⚠ 탈락 없이도 원문이 남는 길이 **둘** 있다. ① 색 구간(`%c…%c`)을 못 채우면
# 그 구간이 원문 그대로 나간다(ED2 49블록 실측). ② **정본에 항목조차 없는 블록** — 순회가
# 번역표를 돌아 아예 안 보였다(8블록 실측 2026-08-19). 둘 다 구조 게이트는 초록이라 여기서만
# 잡힌다. ⚠ 요약은 검사기가 **맨 끝 한 줄**로 합쳐 낸다(중간에 진행 출력이 끼어든다).
out=$("$PY" "$T/check_jp_leak.py" 2>&1) || fail=1
echo "$out" | tail -1 | sed 's/^/     /'
"$PY" "$T/check_jp_leak.py" --ed2 2>&1 | tail -1 | sed 's/^/     [ED2] /'

# ED2 는 아직 재삽입 체인 밖이라 빌드가 문안을 안 본다 — 예행으로 대신 본다.
# ⚠ **게이트로 안 세운다**(exit 코드를 안 본다) — 제어런 재현 불가처럼 「지금 못 고치는」
# 자리가 섞여 있다. 수치가 나빠지면 사람이 본다. ED2 를 체인에 올리면 이 줄은 지운다.
"$PY" "$T/check_ed2_reinsert.py" -q 2>&1 | tail -1 | sed 's/^/     /'

# 블록 경계 — ⚠ **인게임 QA 를 마친 층에만 게이트로 건다.** ED2 를 체인에 올리자 붙음이
# 463곳 나왔는데(ED1 은 71곳을 다 고쳤다), 그건 「실패」가 아니라 「할 일」이다.
# shellcheck disable=SC2086
out=$("$PY" "$T/check_block_join.py" $SCN 2>&1) || fail=1
echo "$out" | tail -1 | sed 's/^/     /'
"$PY" "$T/check_block_join.py" $(for i in $(seq 1 13); do echo -n "ED2SCN$i "; done) 2>&1 | tail -1 | sed 's/^/     [ED2] /'

# 조사 받침 일치 + 변수 뒤 병기. ⚠ **상주 게이트다** — 오타는 아직 화면에 안 나온 자리에
# 있다가 배정이 진행되며 하나씩 올라온다(실측 2026-08-17: 화면 코퍼스 0건인데 전량엔 3건).
out=$("$PY" "$T/check_josa_agreement.py" 2>&1) || fail=1
echo "$out" | grep -E '✅|❌' | sed 's/^/     /'

# 같은 화자·같은 JP 인데 문안이 갈리는 자리 — ⚠ **게이트로 안 세운다**(늘 빨간불이 된다).
# 블록마다는 멀쩡하고 **블록 사이**만 깨지는 부류라 다른 게이트가 못 본다.
"$PY" "$T/check_same_jp.py" 2>&1 | grep -E '⚠|✅|ℹ' | sed 's/^/     /'

# 조판 지문 — ⚠ **락도 관측 대장도 조판을 안 본다**(화자 + 창 본문만 해시). 줄바꿈 규칙을
# 건드리면 이미지는 바뀌는데 아무 알림도 안 뜬다. 플랫폼을 병행하면 그 구멍이 사고가 된다 —
# 다른 게임 작업 중 `shared/text/krwrap.py` 한 줄이 이 게임의 조판을 조용히 바꾼다.
# 게이트가 아니다(문안을 바꾸면 당연히 바뀐다) — **안 바꿨는데 뜨면 `shared/` 를 의심한다.**
"$PY" "$ROOT/scripts/check/typeset_fingerprint.py" 2>&1 | tail -3 | sed 's/^/     /'

# 어투 혼용(존대↔해라체) — 게이트가 아니다(한 창에 두 상대가 섞이는 정당한 자리가 있다).
"$PY" "$T/check_speech_level.py" 2>&1 | head -2 | sed 's/^/     /'

if [ -n "$SCN" ]; then
  # shellcheck disable=SC2086
  out=$("$PY" "$T/check_speakers.py" $SCN 2>&1) || fail=1
  echo "$out" | tail -1 | sed 's/^/     /'
  echo "     (이름창은 정본 씬만: $SCN)"
fi

echo
"$PY" "$T/status.py"
exit "$fail"
