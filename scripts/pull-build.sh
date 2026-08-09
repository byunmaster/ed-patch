#!/bin/sh
# 작업 머신의 빌드 산출물을 이 맥으로 당긴다 — 인게임 QA 는 로컬이 빠르다.
#
#   sh scripts/pull-build.sh              # KR 이미지 하나
#   sh scripts/pull-build.sh BattleJP     # 다른 변종(파일명 괄호 안 표기)
#
# ⚠ 전송만 하면 안 된다. 이 레포의 1급 사고가 **낡거나 엉뚱한 이미지를 정상으로 오해하는 것**이라
#   (루트 CLAUDE.md 「빌드 규율」) 두 가지를 같이 본다:
#     · `*.failed` 는 받지 않는다 — 실패한 빌드는 산출물을 무효화한다
#     · 받은 뒤 sha1 을 찍는다 — `BATTLE_JP=1` 빌드가 **같은 이름으로** 나오기 때문이다
set -eu

HOST=${DEV_HOST:-dev}
REMOTE_REPO=${DEV_REPO:-work/eiyuu-densetsu-patch}
REMOTE_BUILD="$REMOTE_REPO/games/ps1-ed1+2/work/build"

ROOT=$(cd "$(dirname "$0")/.." && pwd)
LOCAL_BUILD="$ROOT/games/ps1-ed1+2/work/build"

VARIANT=${1:-}
if [ -n "$VARIANT" ]; then
  BASE="Eiyuu Densetsu (KR $VARIANT)"
else
  BASE="Eiyuu Densetsu (KR)"
fi

# 실패 표식이 있으면 거기서 멈춘다 — 옆에 남은 낡은 이미지를 받아 가면 조사가 통째로 헛돈다.
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
for f in "$BASE.bin" "$BASE.cue"; do
  rsync -a --progress "$HOST:$Q$REMOTE_BUILD/$f$Q" "$LOCAL_BUILD/"
done

LOCAL_SHA=$(shasum -a 1 "$LOCAL_BUILD/$BASE.bin" | cut -d' ' -f1)

echo
echo "원격 sha1: $REMOTE_SHA"
echo "로컬 sha1: $LOCAL_SHA"
[ "$REMOTE_SHA" = "$LOCAL_SHA" ] || { echo "⛔ 전송 중 손상 — 다시 받아라." >&2; exit 1; }
echo "✅ $LOCAL_BUILD/$BASE.cue"
