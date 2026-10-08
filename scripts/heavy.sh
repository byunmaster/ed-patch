#!/bin/sh
# 무거운 일은 **한 번에 한 세션만** — 머신 전체 줄 세우기(마스터 2026-10-08).
#
#   sh scripts/heavy.sh python3 games/ss-ed3/tools/transcribe.py …     # 받아쓰기(음성 인식)
#   sh scripts/heavy.sh --status                                       # 지금 누가 쥐고 있나
#
# 왜: 받아쓰기(음성 인식 모델)는 메모리·CPU 를 크게 먹는다. ss-ed3 와 pce-ed1 이 밤사이 동시에 돌리다
#   pce 세션이 메모리 부족으로 죽었다(10-08, 16G·스왑 꽉 참). 워크트리가 여럿이어도 머신은 하나라
#   **잠금은 메인 트리 .local/cache/heavy.lock 하나**다(워크트리 안 .local 금지 규칙과 같은 자리).
# 다른 세션이 쥐고 있으면 기다렸다가 돈다(먼저 온 순서). 기다리는 동안 누가 쥐었는지 한 줄 찍는다.
set -eu

COMMON=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
[ -n "$COMMON" ] || { echo "heavy.sh: git 저장소 안에서 돌려야 한다" >&2; exit 2; }
DIR="$(dirname "$COMMON")/.local/cache"
mkdir -p "$DIR"
LOCK="$DIR/heavy.lock"
WHO="$DIR/heavy.owner"

if [ "${1:-}" = "--status" ]; then
  if flock -n "$LOCK" true 2>/dev/null; then echo "비어 있음"; else echo "사용 중: $(cat "$WHO" 2>/dev/null || echo '?')"; fi
  exit 0
fi
[ $# -gt 0 ] || { sed -n '2,5p' "$0"; exit 2; }

me="$(basename "$(git rev-parse --show-toplevel)") · $(date +%H:%M) · $*"
if ! flock -n "$LOCK" true 2>/dev/null; then
  echo "⏳ 무거운 일 대기 — 지금: $(cat "$WHO" 2>/dev/null || echo '?')" >&2
fi
# 잠금을 쥔 채로 명령을 돌린다 — 끝나거나 죽으면 커널이 풀어 준다(남는 잠금 파일 걱정 없음)
exec flock "$LOCK" sh -c 'printf "%s\n" "$1" > "$2"; shift 2; exec "$@"' _ "$me" "$WHO" "$@"
