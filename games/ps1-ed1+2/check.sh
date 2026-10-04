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
# 🔴 2026-09-12 까지 아래 다섯이 **있는데 게이트에 안 물려 있었다**(마스터 QA 로 발각).
#   초록불이 「없다」가 아니라 「아무도 안 본다」였다 — check_jp_left·check_scn_jp_left 는
#   화면·EXE 일본어 잔존, check_shop_verbs 는 매매 동사 뒤집힘, check_variants·
#   check_leader_variants 는 정발 변형이 한 창에 쏟아지는 자리. 다섯 다 지금 0이라
#   게이트로 세운다(루트 CLAUDE.md — 0 이 된 축을 보고로만 두면 다시 늘어도 안 보인다).
# 🔴 2026-09-14: check_window_frame 추가(040) — 온점 매달기가 창의 마지막 줄을 14.5슬롯
#   까지 늘렸는데 그 창이 이미 줄 수 리밋을 꽉 채운 자리(엔진이 부호만 다음 줄로 꺾어
#   창 틀이 갉힌다). 계측을 스크래치로 날리면 다음 사람이 또 잰다 — 늘 도는 축으로 남긴다.
# 🔴 2026-09-27: check_typeset_rules(씬 조판 ①~④) · check_prewrap_rules(런타임 줄넘김 ①~④·⑦·⑧,
#   ~90초 — 빌드 EXE 의 prewrap 을 통째로 실행한다) 추가. 둘 다 만들어 놓고 게이트에 안 물려 있었다.
for t in check_tail_cut check_terms check_spellings check_forbidden check_proper_nouns check_battle_wrap check_battle_grid_wrap check_punct check_name_echo check_onomatopoeia check_pointer_tables check_iso_layout check_readback check_movie_coverage check_card_centering check_window_nl check_log_register check_register_vs_jp check_jp_left check_scn_jp_left check_shop_verbs check_variants check_leader_variants check_window_frame check_typeset_rules check_prewrap_rules; do
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

# 블록 경계 — 🔴 **ED2 도 게이트다**(2026-09-06). 예전엔 「ED2 를 체인에 올리자 붙음이
# 463곳 나왔고 그건 실패가 아니라 할 일」이라 보고만 했는데, **463곳은 08-17 에 다 닫혔고
# 지금 0이다.** 0 이 된 축을 보고로 두면 다시 늘어도 아무도 안 본다.
# shellcheck disable=SC2086
out=$("$PY" "$T/check_block_join.py" $SCN 2>&1) || fail=1
echo "$out" | tail -1 | sed 's/^/     /'
# shellcheck disable=SC2046
out=$("$PY" "$T/check_block_join.py" $(for i in $(seq 1 13); do echo -n "ED2SCN$i "; done) 2>&1) || fail=1
echo "$out" | tail -1 | sed 's/^/     [ED2] /'

# 조사 받침 일치 + 변수 뒤 병기. ⚠ **상주 게이트다** — 오타는 아직 화면에 안 나온 자리에
# 있다가 배정이 진행되며 하나씩 올라온다(실측 2026-08-17: 화면 코퍼스 0건인데 전량엔 3건).
out=$("$PY" "$T/check_josa_agreement.py" 2>&1) || fail=1
echo "$out" | grep -E '✅|❌' | sed 's/^/     /'

# 같은 화자·같은 JP 인데 문안이 갈리는 자리 — ⚠ **게이트로 안 세운다**(늘 빨간불이 된다).
# 블록마다는 멀쩡하고 **블록 사이**만 깨지는 부류라 다른 게이트가 못 본다.
# 🔴 **--games 기본값이 ED1 하나라 이제까지 ED2 는 한 번도 안 봤다**(오늘의 여섯째 사례,
# 2026-09-13). 여기서 명시로 둘 다 준다.
"$PY" "$T/check_same_jp.py" --games ED1,ED2 2>&1 | grep -E '⚠|✅|ℹ' | sed 's/^/     /'

# 조판 지문 — ⚠ **락도 관측 대장도 조판을 안 본다**(화자 + 창 본문만 해시). 줄바꿈 규칙을
# 건드리면 이미지는 바뀌는데 아무 알림도 안 뜬다. 플랫폼을 병행하면 그 구멍이 사고가 된다 —
# 다른 게임 작업 중 `shared/text/krwrap.py` 한 줄이 이 게임의 조판을 조용히 바꾼다.
# 게이트가 아니다(문안을 바꾸면 당연히 바뀐다) — **안 바꿨는데 뜨면 `shared/` 를 의심한다.**
# ⚠ **`tail -3` 로 헤드라인이 잘렸었다**(2026-09-15 관리자 지적) — 경보 첫 줄("⚠ 조판이
# 바뀐 씬 N")이 잘려 나가고 익명 해시 줄만 남아 "몇 씬이 바뀌었는지"가 안 보였다.
# 헤드라인 + 안내문(마지막 줄, 둘이 같은 줄이면 한 번만)만 남긴다 — `sed -n '1p;$p'` 는
# 성공 시(출력 1줄) 그 한 줄을 두 번 찍는다, awk 로 회피(중간 씬 목록은 직접 돌려서 본다).
"$PY" "$ROOT/scripts/check/typeset_fingerprint.py" 2>&1 \
  | awk 'NR==1{first=$0} {last=$0; n=NR} END{print first; if (n>1) print last}' \
  | sed 's/^/     /'

# 어투 혼용(존대↔해라체) — 게이트가 아니다(한 창에 두 상대가 섞이는 정당한 자리가 있다).
"$PY" "$T/check_speech_level.py" 2>&1 | head -2 | sed 's/^/     /'

# 인물표 대조(말투 등급) — ⚠ **게이트가 아니다**(도구 자신의 설계: 등급은 상대·상황에 따라
# 정당하게 오르내린다, 사람이 본다). 그래도 매 커밋 보이게 배선한다 — 손으로만 돌리면
# 돌린 회차에만 보이고, 09-06 회차 뒤로 아무도 안 돌려 09-12 QA 까지 안 걸렸다.
"$PY" "$T/check_speaker_register.py" 2>&1 | tail -2 | sed 's/^/     /'

# 줄 갈림 잔여 — ⚠ **게이트가 아니다**(조판기가 못 고친 나머지라 「할 일」이지 「실패」가
# 아니다 — 폭 초과는 문안을 줄여야 하고, 하드개행 보호 블록은 사람이 다시 놓아야 한다).
# 늘어나는지만 매 커밋 본다.
"$PY" "$T/check_line_breaks.py" 2>&1 | tail -1 | sed 's/^/     /'

if [ -n "$SCN" ]; then
  # shellcheck disable=SC2086
  out=$("$PY" "$T/check_speakers.py" $SCN 2>&1) || fail=1
  echo "$out" | tail -1 | sed 's/^/     /'
  echo "     (이름창은 정본 씬만: $SCN)"
fi

echo
"$PY" "$T/status.py"
exit "$fail"
