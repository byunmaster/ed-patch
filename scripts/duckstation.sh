#!/bin/sh
# 빌드한 KR 이미지를 DuckStation 으로 띄우고, **메모리카드를 dev 와 동기화**한다.
#
#   sh scripts/duckstation.sh              # work/build 의 KR 이미지
#   sh scripts/duckstation.sh --pull       # dev 에서 최신 빌드를 먼저 당겨온다
#   sh scripts/duckstation.sh <파일.cue>   # 이미지를 직접 지정
#   sh scripts/duckstation.sh --no-sync    # 메모리카드 동기화 없이 그냥 실행
#
# ── 왜 필요한가 ──────────────────────────────────────────────────────────────
# 빌드는 dev 에서 하는데 **인게임 QA 는 맥의 DuckStation** 이다(`docs/machine-setup.md` ⑤).
# 그러면 유저 세이브가 맥에만 쌓여 머신을 오갈 때 끊긴다. 세이브 정본을 늘 켜져 있는 dev 에
# 두고 실행 전후로 맞춘다 — 기전은 `scripts/sync-saves.sh` 가 정본이다(DOS 와 같은 걸 쓴다).
#
# ⚠ **세이브스테이트가 아니라 메모리카드다.** 문안 변경 검증에 스테이트를 쓰면 안 된다
#   (루트 CLAUDE.md — 텍스트가 오버레이로 RAM 에 올라와 **스테이트가 곧 옛 빌드**다.
#   다섯 번을 헛돌고 확정한 규칙이다). 그래서 동기화 대상도 메모리카드로 한정한다.
#
# ⚠ **동기화 범위를 이 게임 카드로 좁힌다.** `memcards/` 에는 다른 게임 카드도 같이 사는데,
#   통째로 올리면 남의 게임 세이브가 `ps1-ed1+2` 정본에 섞인다. 그래서 타이틀 접두사로 건다.
#
# ⚠ mednafen(dev)과는 **카드를 공유하지 않는다.** 내용은 둘 다 raw 128KB 라 호환되지만
#   파일명 규약이 다르다 — DuckStation 은 타이틀, mednafen 은 이름+MD5 다. 섞으면 양쪽에
#   이름만 쌓이고 서로의 카드를 못 본다. dev 의 mednafen 은 에이전트 검증용이라 공유할
#   이유가 없어 **DuckStation 만 정본**으로 둔다(유저 결정, 2026-08-10).
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
SYNCSH="$HERE/sync-saves.sh"

APPDIR=${DUCKSTATION_APP:-/Applications/DuckStation.app}
SUPPORT=${DUCKSTATION_SUPPORT:-$HOME/Library/Application Support/DuckStation}
MEMCARDS="$SUPPORT/memcards"

LEAF=ps1-ed1+2                                        # originals/jp/ps1-ed1+2 와 같은 이름
CARD_PREFIX="Legend of Heroes I & II, The - Eiyuu Densetsu (Japan)"
BUILD="$REPO/games/ps1-ed1+2/work/build"
IMAGE="$BUILD/Eiyuu Densetsu (KR).cue"

SYNC=1; PULL=0
for a in "$@"; do
  case "$a" in
    --no-sync) SYNC=0 ;;
    --pull) PULL=1 ;;
    -*) echo "모르는 옵션: $a" >&2; exit 2 ;;
    *) IMAGE=$a ;;
  esac
done

# ── 빌드 당겨오기(선택) ─────────────────────────────────────────────────────
[ "$PULL" = 1 ] && sh "$HERE/pull-build.sh"

[ -f "$IMAGE" ] || {
  echo "이미지 없음: $IMAGE" >&2
  echo "  dev 에서 빌드한 뒤 --pull 로 당기거나, 파일을 직접 지정한다." >&2
  exit 1
}
# ⚠ 실패한 빌드의 잔재를 정상으로 오해하는 게 이 레포의 1급 사고다(루트 CLAUDE.md 「빌드 규율」).
if [ -f "$IMAGE.failed" ] || [ -f "${IMAGE%.cue}.bin.failed" ]; then
  echo "⛔ 실패 표식이 옆에 있다 — 이 이미지로 QA 하면 안 된다" >&2
  exit 1
fi

# ⚠ 자동 설치는 하지 않는다. DuckStation 은 **Homebrew cask 가 없어**(2026-08-10 확인) 받으려면
#   릴리스 아카이브를 직접 내려 /Applications 에 풀어야 하는데, 스크립트가 말없이 할 일이
#   아니다 — 서명·Gatekeeper 격리 속성까지 걸린다. `dosbox.sh` 도 같은 이유로 힌트만 준다.
if [ ! -d "$APPDIR" ]; then
  echo "DuckStation 없음: $APPDIR" >&2
  echo "  https://www.duckstation.org 에서 받아 /Applications 에 둔다" >&2
  echo "  (다른 자리에 뒀으면 DUCKSTATION_APP 로 지정)" >&2
  exit 1
fi

# ── 메모리카드 당기기 ───────────────────────────────────────────────────────
if [ "$SYNC" = 1 ]; then
  if sh "$SYNCSH" probe; then
    mkdir -p "$MEMCARDS"
    sh "$SYNCSH" pull "$LEAF" "$MEMCARDS"
  else
    echo "⚠ dev 에 못 붙는다 — 로컬 메모리카드로 진행한다(종료 후에도 안 올라간다)" >&2
    SYNC=0
  fi
fi

# ── 실행 ────────────────────────────────────────────────────────────────────
echo "실행: $(basename "$IMAGE")"
if [ "$SYNC" != 1 ]; then
  exec open -a "$APPDIR" "$IMAGE"
fi

# ⚠ `-W` 가 있어야 앱이 끝날 때까지 블록해 종료 훅이 산다(`open` 은 원래 바로 반환한다).
# ⚠ Ctrl+C 로 끊어도 카드는 올려야 한다 — 진행분을 잃는 게 제일 나쁜 결과다.
PUSHED=0
finish() {
  [ "$PUSHED" = 1 ] && return 0
  PUSHED=1
  # 글로브는 **여기서 리터럴로** 편다. 전개 결과는 단어분리를 안 타서 파일명의 공백·`&` 가
  # 살아 있다(패턴을 변수에 담아 펴면 그 자리에서 깨진다 — sync-saves.sh 헤더 참조).
  ( cd "$MEMCARDS" && set -- "$CARD_PREFIX"*.mcd \
      && sh "$SYNCSH" push "$LEAF" "$MEMCARDS" "$@" ) || true
}
trap 'finish; exit 130' INT
trap 'finish; exit 143' TERM

RC=0
open -W -a "$APPDIR" "$IMAGE" || RC=$?
finish
exit $RC
