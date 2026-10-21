#!/bin/sh
# 촬영 칸 — 에뮬레이터 촬영(대사 보기·전투 일괄 등)은 **머신 전체 4칸**을 줄 서서 쓴다(마스터 2026-10-19).
#
#   sh scripts/capture.sh python3 games/sfc-ed1/tools/msg_viewer.py …   # 칸이 날 때까지 기다렸다가 돈다
#   sh scripts/capture.sh --status                                      # 지금 칸마다 누가 쓰나
#   sh scripts/capture.sh --fix python3 …                               # 고친 쪽 재촬영 전용 칸(짧은 일만, 10분 제한)
#
# 왜: 게임마다 촬영 차례를 통째로 묶어 두니(차례표) 고치는 동안 칸이 놀았다 — 코어 8개 중 에뮬레이터 하나만 돌던 때가
#   있었다(10-19 16시 load 1.3). 촬영과 고침을 가른다: 촬영 칸 4개를 줄 서서 쓰고, 다 찍은 게임은 칸을 놓고 고친 뒤
#   다시 줄 선다. 빌드·받아쓰기 같은 무거운 일은 그대로 `heavy.sh`(한 칸)다 — 이 칸과 따로다.
# 칸은 메인 트리 .local/cache/capture.N.lock(N=0..3). 끝나거나 죽으면 커널이 풀어 준다.
# 고친 쪽 재촬영은 긴 전수 묶음 뒤에 줄 서면 몇 분짜리가 한 시간을 기다린다 — `--fix` 전용 칸 하나를 따로 둔다
#   (마스터 10-19 「고친애들 전용 슬롯 하나 파면 좋을것 같은데」). 이 칸은 600초 안에 끝나는 일만 — 넘기면 끊는다.
set -eu

SLOTS=${CAPTURE_SLOTS:-4}
COMMON=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
[ -n "$COMMON" ] || { echo "capture.sh: git 저장소 안에서 돌려야 한다" >&2; exit 2; }
DIR="$(dirname "$COMMON")/.local/cache"
mkdir -p "$DIR"

FIX=0
if [ "${1:-}" = "--fix" ]; then FIX=1; shift; fi

if [ "${1:-}" = "--status" ]; then
  if flock -n "$DIR/capture.fix.lock" true 2>/dev/null; then echo "고침 칸: 비어 있음"; else echo "고침 칸: $(cat "$DIR/capture.fix.owner" 2>/dev/null || echo '?')"; fi
  i=0
  while [ "$i" -lt "$SLOTS" ]; do
    if flock -n "$DIR/capture.$i.lock" true 2>/dev/null; then
      echo "칸 $i: 비어 있음"
    else
      echo "칸 $i: $(cat "$DIR/capture.$i.owner" 2>/dev/null || echo '?')"
    fi
    i=$((i + 1))
  done
  exit 0
fi
[ $# -gt 0 ] || { sed -n '2,5p' "$0"; exit 2; }

me="$(basename "$(git rev-parse --show-toplevel)") · $(date +%H:%M) · $*"
if [ "$FIX" -eq 1 ]; then
  [ -n "$(flock -n "$DIR/capture.fix.lock" true 2>&1 || echo busy)" ] && echo "⏳ 고침 칸 대기" >&2
  exec flock "$DIR/capture.fix.lock" sh -c 'printf "%s · 잡음 %s\n" "$1" "$(date +%H:%M)" > "$2"; shift 2; exec timeout 600 "$@"' _ "$me" "$DIR/capture.fix.owner" "$@"
fi
waited=0
while :; do
  i=0
  while [ "$i" -lt "$SLOTS" ]; do
    lock="$DIR/capture.$i.lock"
    # 칸을 못 잡으면 flock 이 75 로 끝난다(-E) — 명령 자체의 실패 코드와 가르려고
    rc=0
    flock -n -E 75 "$lock" sh -c 'printf "%s · 잡음 %s\n" "$1" "$(date +%H:%M)" > "$2"; shift 2; exec "$@"' _ "$me" "$DIR/capture.$i.owner" "$@" || rc=$?
    [ "$rc" -eq 75 ] || exit "$rc"
    i=$((i + 1))
  done
  [ "$waited" -eq 1 ] || { echo "⏳ 촬영 칸 대기 — 칸 $SLOTS 개가 다 찼다(sh scripts/capture.sh --status)" >&2; waited=1; }
  sleep 20
done
