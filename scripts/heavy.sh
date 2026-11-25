#!/bin/sh
# 무거운 일은 **머신 전체에서 두 칸만** — 줄 세우기(마스터 2026-10-08 한 칸 → 11-06 두 칸).
#
#   sh scripts/heavy.sh python3 games/ss-ed3/tools/transcribe.py …     # 받아쓰기(음성 인식)
#   sh scripts/heavy.sh --status                                       # 지금 누가 쥐고 있나
#
# 왜: 받아쓰기(음성 인식 모델)는 메모리·CPU 를 크게 먹는다. ss-ed3 와 pce-ed1 이 밤사이 동시에 돌리다
#   pce 세션이 메모리 부족으로 죽었다(10-08, 16G·스왑 꽉 참). 워크트리가 여럿이어도 머신은 하나라
#   **잠금은 메인 트리 .local/cache/heavy.<칸>.lock** 이다(워크트리 안 .local 금지 규칙과 같은 자리).
# 칸이 다 차 있으면 5초마다 다시 두드린다(먼저 온 순서는 보장하지 않는다). 기다리는 동안 누가 쥐었는지 한 줄 찍는다.
set -eu

COMMON=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
[ -n "$COMMON" ] || { echo "heavy.sh: git 저장소 안에서 돌려야 한다" >&2; exit 2; }
DIR="$(dirname "$COMMON")/.local/cache"
mkdir -p "$DIR"
SLOTS="${HEAVY_SLOTS:-2}"   # 동시에 돌 수 있는 수 — 마스터 11-06 「2칸」(종전 1칸). 메모리 24G 에 받아쓰기 둘까지
WHO="$DIR/heavy.owner"

if [ "${1:-}" = "--status" ]; then
  i=0
  while [ "$i" -lt "$SLOTS" ]; do
    if flock -n "$DIR/heavy.$i.lock" true 2>/dev/null; then echo "칸 $i: 비어 있음"; else echo "칸 $i: 사용 중 — $(cat "$WHO.$i" 2>/dev/null || echo '?')"; fi
    i=$((i + 1))
  done
  exit 0
fi
[ $# -gt 0 ] || { sed -n '2,5p' "$0"; exit 2; }

me="$(basename "$(git rev-parse --show-toplevel)") · $(date +%H:%M) · $*"
# 칸을 차례로 두드려 빈 칸을 잡는다. flock -n 의 「못 잡음」은 75 로 받아 명령 자신의 종료 코드와 가른다.
# 잠금을 쥔 채로 명령을 돌린다 — 끝나거나 죽으면 커널이 풀어 준다(남는 잠금 파일 걱정 없음)
# 줄 선 시각(me 안)과 따로 **잡은 시각**을 적는다 — 줄 선 시각만 보이면 오래 기다린 묶음이 오래 쥔 것처럼 보였다(10-19)
said=0
while :; do
  i=0
  while [ "$i" -lt "$SLOTS" ]; do
    set +e
    flock -n -E 75 "$DIR/heavy.$i.lock" sh -c 'printf "%s · 잡음 %s\n" "$1" "$(date +%H:%M)" > "$2"; shift 2; exec "$@"' _ "$me" "$WHO.$i" "$@"
    rc=$?
    set -e
    [ "$rc" -ne 75 ] && exit "$rc"
    i=$((i + 1))
  done
  if [ "$said" -eq 0 ]; then
    echo "⏳ 무거운 일 대기 — 칸 $SLOTS 개 모두 사용 중:" >&2
    j=0; while [ "$j" -lt "$SLOTS" ]; do echo "   칸 $j: $(cat "$WHO.$j" 2>/dev/null || echo '?')" >&2; j=$((j + 1)); done
    said=1
  fi
  sleep 5
done
