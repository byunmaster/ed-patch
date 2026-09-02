#!/bin/sh
# 이 게임의 커밋 전 게이트 — [kr] PS1 영웅전설 III·IV.
#
#   sh games/ps1-ed3+4/check.sh      (보통은 `sh scripts/check.sh` 가 부른다)
#
# ⚠ 아직 **이미지를 굽지 않는다**(정적 분석 단계). 그래서 1급 검사는 「빌드가 되나」가
#   아니라 **「대본을 읽는 전제가 그대로인가」**다 — 원본 지문 · 아카이브 규격 · 코드표.
#
# 🔴 이 게임의 뿌리 전제는 **문자 코드표**다. 표가 한 칸이라도 밀리면 빌드도 검사도 다
#    통과하고 **화면에서만** 드러난다(2026-09-03: 주인공이 「ジヤラオ」로 읽혔다).
set -eu

G=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$G/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3

fail=0

# ⚠ 파이프는 종료 코드를 먹는다 — 출력을 먼저 받고 종료 코드를 따로 본다(ss-ed3 게이트와 같은 이유).
_run() {
  _gate=$1; _tail=$2; shift 2
  _out=$("$@" 2>&1) && _rc=0 || _rc=$?
  if [ "$_tail" -gt 0 ]; then printf '%s\n' "$_out" | tail -"$_tail" | sed 's/^/   /'
  else printf '%s\n' "$_out" | sed 's/^/   /'; fi
  [ "$_rc" -eq 0 ] || [ "$_gate" = warn ] || fail=1
}
run()  { _run gate "$@"; }
warn() { _run warn "$@"; }

# 원본이 없어도 도는 검사부터 — **여기가 늘 돌아야 하는 자리다.**
# (코드표·아카이브 규격의 회귀는 합성 입력으로 잡는다, 체크리스트 7)
echo "  ── 회귀 (원본 없이 돈다)"
run 0 "$PY" -m unittest discover -s "$G/tools/tests" -p "test_*.py"

if [ ! -d "$ROOT/originals/jp/ps1-ed3" ]; then
  echo "  ⏭ originals/jp/ps1-ed3 가 없다 — 원본이 필요한 검사는 건너뛴다"
  [ "$fail" -eq 0 ] && echo "  ✅ 통과(부분)" || echo "  🔴 실패"
  exit "$fail"
fi

echo "  ── 원본 지문 (오프셋이 결박된 그 덤프인가)"
run 0 "$PY" -c "
import sys; sys.path.insert(0, '$G/tools')
import common
for d in common.DISC_NAMES:
    common.verify_source(d)
    print(f'  {d}: 지문 ✓ · 파일 {len(common.iso_files(d)):,}')
"

echo "  ── 코드표가 대본을 얼마나 읽나"
# 🔴 게이트다 — 커버리지가 떨어졌다는 건 표가 밀렸거나 덤프 경계가 어긋났다는 뜻이다.
run 0 "$PY" "$G/tools/check_coverage.py" --disc ed3 --min 99.0

# ED4 는 아직 표가 없다 — 있으면 재고 없으면 알린다(늘 빨간불이 되지 않게)
warn 0 "$PY" "$G/tools/check_coverage.py" --disc ed4 --min 0

if [ "$fail" -eq 0 ]; then echo "  ✅ 통과"; else echo "  🔴 실패"; fi
exit "$fail"
