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

[ "$fail" -eq 0 ] && echo "  ✅ 통과" || echo "  🔴 실패"
exit "$fail"
