#!/bin/sh
# 작업 머신의 빌드 산출물을 이 맥으로 당긴다 — 인게임 QA 는 로컬이 빠르다.
#
#   sh scripts/pull-build.sh              # **현재 브랜치**와 같은 꼬리표 (기본)
#   sh scripts/pull-build.sh ed1-qa       # 꼬리표(브랜치)를 골라서
#   sh scripts/pull-build.sh --all        # 원격의 모든 꼬리표
#   sh scripts/pull-build.sh ed1-qa BattleJP   # + 변종(파일명 괄호 안 표기)
#
# ⚠ **기본이 하나인 이유는 전송량이 아니라 디스크와 목록**이다. 칸끼리 실제로 다른 바이트는
#   241MB 중 49KB(0.02%)뿐이라 rsync 델타로 거의 공짜다 — 새 칸의 첫 내려받기도
#   `--copy-dest` 로 밑절미를 주니 마찬가지다. 대신 칸마다 241MB 가 맥에 쌓이고,
#   DuckStation 목록이 **같은 이름으로** 뒤덮여 어느 게 뭔지 구분이 안 된다.
#
# ⚠ 꼬리표가 원격에 없으면 **받지 않고 멈춘다.** 조용히 다른 칸을 받으면 「엉뚱한 이미지를
#   받고도 받은 줄 아는」 상태가 되는데, 칸을 나눈 이유가 바로 그걸 막으려던 것이다.
#
# ⚠ 전송만 하면 안 된다. 이 레포의 1급 사고가 **낡거나 엉뚱한 이미지를 정상으로 오해하는 것**이라
#   (루트 CLAUDE.md 「빌드 규율」) 두 가지를 같이 본다:
#     · `*.failed` 는 받지 않는다 — 실패한 빌드는 산출물을 무효화한다
#     · 받은 뒤 sha1 을 찍는다 — `BATTLE_JP=1` 빌드가 **같은 이름으로** 나오기 때문이다
set -eu

HOST=${DEV_HOST:-dev}
REMOTE_REPO=${DEV_REPO:-work/eiyuu-densetsu-patch}
# ⚠ 빌드는 **꼬리표(브랜치)별로 갈린다** — `work/build/<꼬리표>/`. 꼬리표를 안 주면
# **현재 브랜치**와 같은 이름의 칸을 받는다.
ALL=0
ARGS=""
for a in "$@"; do
  case "$a" in
    --all) ALL=1 ;;
    *) ARGS="$ARGS $a" ;;
  esac
done
# shellcheck disable=SC2086
set -- $ARGS

REMOTE_BUILDS="$REMOTE_REPO/games/ps1-ed1+2/work/build"
ROOT=$(cd "$(dirname "$0")/.." && pwd)
LOCAL_BUILDS="$ROOT/games/ps1-ed1+2/work/build"

TAGS=$(ssh "$HOST" "ls -t '$REMOTE_BUILDS' 2>/dev/null")
[ -n "$TAGS" ] || { echo "원격에 빌드가 없다" >&2; exit 1; }

TAG=${1:-${ED_BUILD_TAG:-}}
if [ "$ALL" = 1 ]; then
  WANT=$TAGS
elif [ -n "$TAG" ]; then
  WANT=$TAG
else
  # 기본은 **내가 지금 있는 브랜치**다(유저 확정 2026-08-15) — 이미지 둘을 동시에 보는
  # 일이 없으니 그게 가장 단순하다. 원격 빌드 꼬리표도 브랜치라 이름이 그대로 맞는다.
  WANT=$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null | sed 's#.*/##; s#[^A-Za-z0-9._-]#-#g')
  [ -n "$WANT" ] || { echo "브랜치를 못 읽었다 — 꼬리표를 직접 줘라" >&2; exit 1; }
  echo "꼬리표: $WANT (현재 브랜치)"
fi

# ⚠ **없으면 여기서 멈춘다.** 조용히 다른 칸으로 넘어가면 「엉뚱한 이미지를 받고도 받은 줄
# 아는」 상태가 된다 — 칸을 나눈 이유가 바로 그걸 막으려던 것이다.
for t in $WANT; do
  printf '%s\n' "$TAGS" | grep -qx "$t" || {
    echo "⛔ 원격에 꼬리표 '$t' 가 없다.  있는 것: $(printf '%s ' $TAGS)" >&2
    echo "   (dev 에서 그 브랜치로 빌드했는지 확인하거나, 꼬리표를 직접 줘라)" >&2
    exit 1
  }
done

VARIANT=${2:-}
if [ -n "$VARIANT" ]; then
  BASE="Eiyuu Densetsu (KR $VARIANT)"
else
  BASE="Eiyuu Densetsu (KR)"
fi

# 실패 표식이 있으면 거기서 멈춘다 — 옆에 남은 낡은 이미지를 받아 가면 조사가 통째로 헛돈다.
for TAG in $WANT; do
REMOTE_BUILD="$REMOTE_BUILDS/$TAG"
LOCAL_BUILD="$LOCAL_BUILDS/$TAG"
mkdir -p "$LOCAL_BUILD"
echo "── [$TAG]"

if ssh "$HOST" "ls '$REMOTE_BUILD/$BASE.bin.failed'" >/dev/null 2>&1; then
  echo "⛔ 원격 빌드가 실패 상태다 ($BASE.bin.failed) — 먼저 빌드를 고쳐라." >&2
  exit 1
fi
if ! ssh "$HOST" "ls '$REMOTE_BUILD/$BASE.bin'" >/dev/null 2>&1; then
  echo "⛔ 원격에 '$BASE.bin' 이 없다." >&2
  exit 1
fi

REMOTE_SHA=$(ssh "$HOST" "sha1sum '$REMOTE_BUILD/$BASE.bin'" | cut -d' ' -f1)

mkdir -p "$LOCAL_BUILD"
# ⚠ 파일명이 `Eiyuu Densetsu (KR).bin` 이라 공백·괄호가 들어간다. 원격 경로를 어떻게 넘길지가
#   **rsync 구현에 따라 정반대**다(버전 고저가 아니다) — 맥 한 대 안에도 둘이 깔려 있어
#   PATH 순서로 갈린다. 그래서 골라 쓰는 게 아니라 **감지해서** 쓴다.
#     · 스톡 macOS(구 GNU 2.6.9 · 15+ 는 Apple openrsync): 원격 경로가 **원격 셸을 그대로 통과**한다.
#       감싸지 않으면 bash 가 `syntax error near unexpected token '('` 로 죽는다 → 작은따옴표 필요.
#     · 3.2.4+ (Homebrew): "modern arg-protection" 이 기본이라 셸을 안 태운다. 여기에 따옴표를 씌우면
#       그 따옴표가 **파일명의 일부**가 되어 `/root/'work/...` 를 찾다 죽는다(실측 2026-08-10).
#   `--secluded-args`(구 `--protect-args`) 유무가 그 경계다. 옵션이 있으면 보호가 기본이라 맨 경로.
#   `--info=progress2` 는 3.1+ 전용이라 안 쓴다 — 큰 파일 하나뿐이라 `--progress` 로 표시가 거의 같다.
if rsync --help 2>&1 | grep -q -- '--secluded-args'; then
  Q=''
else
  Q="'"
fi
# ⚠ 파일당 한 번씩 부른다. `host:a host:b` 로 **원격 소스를 둘 이상** 주는 건 GNU rsync 3.0+ 문법이라
#   스톡 macOS 의 GNU 2.6.9 에서는 usage error 로 죽는다(실측). 받는 게 두 개뿐이라 나눠도 손해가 없다.
# ⚠ **새 칸의 첫 내려받기도 델타로 만든다.** rsync 는 받는 쪽에 같은 이름의 파일이 있어야
#   차분을 뜨는데, 꼬리표가 새로 생기면 그 자리가 비어 있어 241MB 를 통째로 받는다.
#   칸끼리 실제로 다른 바이트는 **49KB(0.02%)** 뿐이라, 이미 받아 둔 다른 칸을 밑절미
#   (`--copy-dest`)로 주면 첫 내려받기도 거의 공짜가 된다.
#   ⚠ Apple openrsync 엔 이 옵션이 없다 — **있을 때만** 쓴다(없으면 그냥 전체 전송).
BASIS=""
if rsync --help 2>&1 | grep -q -- '--copy-dest' && [ ! -f "$LOCAL_BUILD/$BASE.bin" ]; then
  for c in "$LOCAL_BUILDS"/*/; do
    [ -f "$c$BASE.bin" ] || continue
    BASIS="--copy-dest=$c"; echo "   밑절미: $(basename "$c")"; break
  done
fi
for f in "$BASE.bin" "$BASE.cue"; do
  # shellcheck disable=SC2086
  rsync -a --progress $BASIS "$HOST:$Q$REMOTE_BUILD/$f$Q" "$LOCAL_BUILD/"
done

LOCAL_SHA=$(shasum -a 1 "$LOCAL_BUILD/$BASE.bin" | cut -d' ' -f1)

echo
echo "원격 sha1: $REMOTE_SHA"
echo "로컬 sha1: $LOCAL_SHA"
[ "$REMOTE_SHA" = "$LOCAL_SHA" ] || { echo "⛔ 전송 중 손상 — 다시 받아라." >&2; exit 1; }
echo "✅ $LOCAL_BUILD/$BASE.cue"
done
