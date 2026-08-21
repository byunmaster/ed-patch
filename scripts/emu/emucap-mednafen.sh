#!/bin/sh
# emucap 이 띄우는 mednafen 을 감싼다 — **세이브를 게임별 칸에 넣고 dev 에서 당겨온다.**
#
#   MEDNAFEN_BIN=<이 파일>            emucap MCP 환경에 넣으면 launch.sh 가 이걸 실행한다
#   sh scripts/emu/emucap-mednafen.sh push <게임>   세션을 닫은 뒤 세이브를 올린다
#
# ── 왜 필요한가 ──────────────────────────────────────────────────────────────
# emucap 은 **맥에서 로컬로** 돈다(stdio MCP). 그래서 에이전트가 만든 세이브가 맥에 고립되고,
# 사람이 `emu.sh` 로 이어서 볼 수가 없다. 둘을 한 자리로 모은다 —
#
#   에이전트(emucap) ┐
#                    ├→ ~/.mednafen/sav/<게임>/ ←→ dev:~/save/<게임>/
#   사람(emu.sh)     ┘
#
# emucap 의 `launch.sh` 는 `-filesys.path_sav` 를 안 주므로 세이브가 평평한 `sav/` 에 쌓이는데,
# 그러면 「이 게임 것만 올린다」를 파일명으로 추측해야 한다. 여기서 인자를 하나 끼워 넣는다.
#
# ⚠ **반드시 exec 한다.** `launch.sh` 는 성공을 「그 PID 가 EMUCAP_PORT 에 ESTABLISHED」로
#   판정한다 — 래퍼가 부모로 남으면 소켓을 자식이 쥐고 있어 **연결 확인에 실패**한다.
#   그래서 종료 훅을 여기 못 단다. 올리기는 세션을 닫은 뒤 `push` 로 따로 한다.
# ⚠ **emucap 은 자기 포크를 쓴다** — 시스템 mednafen 이 아니다(계측 훅이 그 안에 있다).
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)   # scripts/emu → 레포 루트
SYNCSH="$HERE/sync-saves.sh"
MEDBASE=${MEDNAFEN_HOME:-$HOME/.mednafen}
FORK=${EMUCAP_MEDNAFEN_BIN:-$REPO/vendor/emucap/adapters/mednafen/work/mednafen/src/mednafen}

# 콘텐츠 경로에서 게임(leaf)을 읽는다 — `originals/<지역>/<leaf>/` 과
# `games/<leaf>/work/build/<꼬리표>/` 둘 다 규약이 이미 정해져 있어 새로 정할 게 없다.
leaf_of() {
  case "$1" in
    */originals/*/*/*) _t=${1#*/originals/}; _t=${_t#*/}; printf '%s' "${_t%%/*}" ;;
    */games/*/work/build/*) _t=${1#*/games/}; printf '%s' "${_t%%/*}" ;;
    *) printf '' ;;
  esac
}

if [ "${1:-}" = push ]; then
  GAME=${2:-}
  [ -n "$GAME" ] || { echo "사용법: $0 push <게임>" >&2; exit 2; }
  DIR="$MEDBASE/sav/$GAME"
  [ -d "$DIR" ] || { echo "올릴 세이브 칸이 없다: $DIR" >&2; exit 1; }
  # 글로브는 여기서 리터럴로 편다(파일명의 공백·`&` 가 살아야 한다 — sync-saves.sh 헤더).
  ( cd "$DIR" && set -- * && sh "$SYNCSH" push "$GAME" "$DIR" "$@" )
  exit $?
fi

[ -x "$FORK" ] || {
  echo "ERROR: emucap 용 mednafen 포크가 없다: $FORK" >&2
  echo "  vendor/emucap/adapters/mednafen/build.sh 로 빌드한다(macOS 는 flock 필요)." >&2
  exit 1
}

# 마지막 인자가 콘텐츠다(launch.sh 규약: ARGS+=("$CONTENT")).
CONTENT=
for a in "$@"; do CONTENT=$a; done
GAME=$(leaf_of "$CONTENT")

if [ -z "$GAME" ]; then
  # 규약 밖의 경로면 아무것도 손대지 않는다 — 조용히 엉뚱한 칸에 넣는 것보다 낫다.
  exec "$FORK" "$@"
fi

SAVEREL="sav/$GAME"
mkdir -p "$MEDBASE/$SAVEREL"
# ⚠ dev 에 못 붙어도 **띄우는 건 계속한다** — launch.sh 가 20초 안에 연결을 확인하므로
#   여기서 오래 붙들면 기동 자체가 실패한다. probe 는 ConnectTimeout=5 다.
if sh "$SYNCSH" probe 2>/dev/null; then
  sh "$SYNCSH" pull "$GAME" "$MEDBASE/$SAVEREL" >&2 || true
fi

exec "$FORK" -filesys.path_sav "$SAVEREL" "$@"
