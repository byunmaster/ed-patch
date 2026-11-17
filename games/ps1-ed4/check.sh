#!/bin/sh
# 이 게임의 커밋 전 게이트 — [kr] PS1 영웅전설 IV 『朱紅い雫』. `sh scripts/check.sh` 가 부른다.
#
# 지금은 **기반 단계**(번역 없음)다 — 이미지를 굽긴 하되 문안은 안 바꾼다. 그래서 1급 검사는
#   ① 원본 지문 ② 무변경 왕복(원본과 바이트 같음) ③ 결정성(같은 입력 두 번 = 같은 sha) ④ 쓰기 가드 ⑤ 재삽입 시험 ⑥ 화면 일본어 기준선이다.
# 🔴 시험 빌드는 꼬리표 `test-*` 칸에서 굽고 끝나면 지운다(마스터 목록에 안 나온다).
set -eu

G=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$G/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3

fail=0

# ⚠ 파이프는 종료 코드를 먹는다 — 출력을 먼저 받고 종료 코드를 따로 본다.
run() {
  _tail=$1; shift
  _out=$("$@" 2>&1) && _rc=0 || _rc=$?
  _n=$(printf '%s\n' "$_out" | wc -l)
  if [ "$_tail" -gt 0 ] && [ "$_n" -gt "$_tail" ]; then
    printf '%s\n' "$_out" | head -n $((_n - _tail)) | grep '🔴' | sed 's/^/   /' || true
    printf '%s\n' "$_out" | tail -"$_tail" | sed 's/^/   /'
  else printf '%s\n' "$_out" | sed 's/^/   /'; fi
  [ "$_rc" -eq 0 ] || fail=1
}

echo "  ── 회귀 (원본 없이 돈다)"
run 0 "$PY" -m unittest discover -s "$G/tools/tests" -p "test_*.py"

if [ ! -d "$ROOT/originals/jp/ps1-ed4" ]; then
  echo "  ⏭ originals/jp/ps1-ed4 가 없다 — 원본이 필요한 검사는 건너뛴다"
  [ "$fail" -eq 0 ] && echo "  ✅ 통과(부분)" || echo "  🔴 실패"
  exit "$fail"
fi

echo "  ── 원본 지문 (오프셋이 결박된 그 덤프인가)"
run 0 "$PY" -c "
import sys; sys.path.insert(0, '$G/tools')
import common
common.verify_source()
print(f'  지문 ✓ · 파일 {len(common.iso_files()):,}')
"

echo "  ── 덤프 (대본 481 · 실행파일 문자열 · 맵 표 — 라벨 없는 구역이 나오면 운다)"
run 4 "$PY" "$G/tools/dump.py"

echo "  ── 무변경 왕복 + 결정성 (원본과 바이트 같음 · 두 번 구워 sha 같음)"
run 0 "$PY" "$G/tools/check_determinism.py" --probe

echo "  ── 쓰기 가드 (무변경 구간·선언 안 된 파일·없는 조각은 막히고 *.failed 가 남는다)"
run 0 "$PY" "$G/tools/check_guard.py"

echo "  ── 재삽입 시험 (같은 크기 · 길이 변경 — 되읽기·안 건드린 조각·글리프)"
run 3 env ED_BUILD_TAG=test-gate-same "$PY" "$G/tools/probe.py" --mode same
run 3 env ED_BUILD_TAG=test-gate-resize "$PY" "$G/tools/probe.py" --mode resize
rm -rf "$G/work/build/test-gate-same" "$G/work/build/test-gate-resize"

echo "  ── 화면 일본어 잔존 (대본, 기준선 래칫)"
run 0 "$PY" "$G/tools/check_jp_left.py"

echo "  ── UI 문안 정본 (원문 지문 · 고정 길이)"
run 0 "$PY" "$G/tools/uitext.py" check
echo "  ── 대본 번역 정본 (원문 지문 · 쪽 한도)"
run 0 "$PY" "$G/tools/script_kr.py" check
echo "  ── 마스터 판정 문안 (금지·필수 꼴 — 검수·재조판이 판정을 되돌리지 못하게, 공용 판정기 + tools/rulings_corpus.py)"
run 0 "$PY" scripts/check/master_rulings.py --game ps1-ed4
echo "  ── 대본 조판 탈락 (정본 번역 조각 수 = 조판된 수 · 못 넣은 쪽 0 — 탈락한 쪽은 일본어가 그대로 나간다)"
run 0 "$PY" "$G/tools/script_kr.py" fit
echo "  ── 제어 코드 대조 (원판 대본의 색·이름 삽입·흐름 연산이 제품 바이트에 그대로 · 수 그리기는 부분열 · 양성 대조)"
run 0 "$PY" "$G/tools/check_ctrl_codes.py"
# 실행파일 쓰기 감사(11-08) — 원판 대비 바뀐 워드 전수가 선언한 자리(표·동굴·패치 목록·기준 상수 참조·글리프 배열·의뢰 표) 안인가 — 우연한 바이트 패턴 치환 부류
run 0 "$PY" "$G/tools/check_exe_writes.py"
echo "  ── 삽입 칸 앞 띄어쓰기 (이름·아이템·수가 끼는 자리 바로 앞 조각이 공백 없이 한글로 끝나면 「차서스톤」으로 나간다 · 양성 대조)"
run 0 "$PY" "$G/tools/check_spacing.py"
echo "  ── 조판 결과 전수 (첫 칸 공백 · 고아 부호 · 빈 줄 · 부호 앞뒤 공백 · …뒤 공백 · ?… 순서 · 낱말 속 접힘 · 넘침 · 한 줄 문장 갈림 2-10 · 쉼표 2-13 남김 래칫 · 양성 대조)"
run 0 "$PY" "$G/tools/check_typeset.py"
echo "  ── 전수 촬영 「빈 줄」 (한글에만 나온 본문 뒤 이름 줄 앞 빈 줄 · 촬영 폴더가 있으면 — 원판과 같은 곳은 기준선)"
run 0 "$PY" "$G/tools/check_sweep_blank.py"
echo "  ── 말투 게이트 (규칙 4-16 ③④ — 대사 「그대」 0 · 반말 줄 듣는 이 「-시-」 래칫 · 원문 대비 길이 급감 래칫 · 양성 대조)"
run 0 "$PY" "$G/tools/check_speech.py"
echo "  ── 문장부호 게이트 (규칙 1-1·1-3·1-7·2-12 — ... · ・・ · 띄운 … 반복 · 전각 ！？ · ~ · ～. · ?… 0 · 원문 점 n→… round(n/3) 래칫 · 양성 대조)"
run 0 "$PY" "$G/tools/check_punct.py"
echo "  ── 가운데 맞춤 (규칙 2-8 — 그림 글 줄 가운데 오차 · 아이템 메시지 창 좌우 여백, 줄 끝 부호는 폭에서 뺀다 · 양성 대조)"
run 0 "$PY" "$G/tools/check_center.py"
echo "  ── 게시판 의뢰문 줄 폭 (상세 창 192px — 줄이 넘으면 엔진이 글자 단위로 접어 보상 줄을 덮는다 · 판정 대기 목록 래칫)"
run 0 "$PY" "$G/tools/check_board_rows.py"

echo "  ── 줄·쪽 나눔 지표 (규칙 2-16 — 쪽 끝 고아 · 보조용언 쪽 끊기 · 절 쪼갬, 기준선 래칫)"
run 0 "$PY" "$G/tools/linemetrics.py" check

echo "  ── 조판 지문 (대본 조판 24474 조각을 멤버별 sha1 — 공용 krwrap 이 이 게임 줄바꿈을 조용히 바꾸면 실패한다, 마스터 10-29 N4)"
# 🔴 실패로 친다 — 문안을 의도적으로 바꿨으면 `typeset_fingerprint.py --game ps1-ed4 --freeze`, **안 바꿨는데 떴으면 `shared/` 를 의심한다.**
# ⚠ 파이프로 걸러 보면 종료 코드를 먹는다 — 출력을 먼저 받고 종료 코드를 따로 본다.
_fp=$("$PY" "$ROOT/scripts/check/typeset_fingerprint.py" --game ps1-ed4 2>&1) && _fprc=0 || _fprc=$?
printf '%s\n' "$_fp" | sed 's/^/   /'
if [ "$_fprc" -ne 0 ]; then
  echo "   🔴 조판 지문이 바뀌었다"
  fail=1
fi

echo "  ── 그림 글(오프닝·엔딩·스태프롤) — 줄이 그림 안 · 압축 뒤 크기가 원 멤버 한도 안"
run 0 "$PY" "$G/tools/narration.py" check "$G/work/review/narration"

echo "  ── 고유명사 정본 ↔ 원본 (정본에만 있는 항목 · 한 표기가 원문 둘)"
run 0 "$PY" "$G/tools/check_canon_nouns.py"

if [ "${ED_BOARD_4LINE:-}" != "0" ]; then
  echo "  ── 게시판 본문 4줄 안(기본 켬) — 구운 롬을 읽어 정본과 대조"
  run 0 "$PY" "$G/tools/board4.py" --verify
fi

echo "  ── 화자 호칭 정본(shared/canon/ed4.json speaker) ↔ 대본"
run 0 "$PY" "$G/tools/check_canon_speaker.py"

[ "$fail" -eq 0 ] && echo "  ✅ 통과" || echo "  🔴 실패"
exit "$fail"
