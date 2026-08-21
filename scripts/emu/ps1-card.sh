#!/bin/sh
# PS1 메모리카드를 DuckStation ↔ mednafen 사이에서 옮긴다.
#
#   sh scripts/emu/ps1-card.sh ps1-ed1+2            # DuckStation → mednafen (기본)
#   sh scripts/emu/ps1-card.sh ps1-ed1+2 export     # mednafen → DuckStation
#   sh scripts/emu/ps1-card.sh ps1-ed1+2 --dry      # 무엇을 할지만 보여준다
#
# `duckstation.sh` 를 지우면서(2026-08-21) DuckStation 쪽 카드 동기화도 같이 없어졌다.
# 2차 의견이 필요할 때 세이브를 넘기는 길이 이 스크립트다.
#
# ── 변환이랄 게 없다 ─────────────────────────────────────────────────────────
# 둘 다 **생 128KB 카드 이미지**다(실측: 131,072바이트, 첫 두 바이트 `4d43` = "MC").
# 다른 건 **파일명뿐**이라 이 스크립트가 하는 일도 복사와 이름 짓기다:
#
#   DuckStation  <타이틀>_1.mcd            _1 · _2
#   mednafen     <이미지 이름>.<MD5>.0.mcr  .0 · .1
#
# ⚠ **MD5 는 우리가 못 만든다** — mednafen 이 디스크에서 뽑는 값이라, 이미 있는 `.mcr` 에서
#   배운다. 그 게임을 mednafen 으로 한 번도 안 돌렸으면 배울 데가 없으니 그때는 멈추고
#   알려 준다(한 번 돌려 게임 안에서 저장하면 생긴다).
#
# ⚠ **원본과 빌드는 이름이 다르니 카드도 따로다**(`Legend of Heroes...(Japan)` vs
#   `Eiyuu Densetsu (KR)`). 그래서 import 는 **알고 있는 이름 전부에** 넣는다 — 어느 이미지로
#   켜든 같은 세이브가 보이는 게 QA 에서 맞다. 128KB짜리라 몇 벌 더 둬도 부담이 없다.
#   (MD5 는 원본과 빌드가 같다 — 실측 `eb5fce…`. 디스크 내용 해시가 아닌 모양이다.)
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)   # scripts/emu → 레포 루트
MEDBASE=${MEDNAFEN_HOME:-$HOME/.mednafen}
DUCK=${DUCKSTATION_SUPPORT:-$HOME/Library/Application Support/DuckStation}/memcards

GAME=${1:-}
[ -n "$GAME" ] || { echo "사용법: $0 <게임> [export] [--dry]" >&2; exit 2; }
shift
DIR=import; DRY=0
for a in "$@"; do
  case "$a" in
    import|export) DIR=$a ;;
    --dry|-n) DRY=1 ;;
    *) echo "모르는 인자: $a" >&2; exit 2 ;;
  esac
done
case "$GAME" in ps1-*) ;; *) echo "⛔ PS1 게임만 된다: $GAME" >&2; exit 2 ;; esac

SAV="$MEDBASE/sav/$GAME"
mkdir -p "$SAV"

# 이 게임의 이미지 이름들(확장자 뺀 것) — 원본 + 모든 빌드 칸
names() {
  for r in jp kr us; do
    for f in "$REPO/originals/$r/$GAME"/*.cue; do [ -f "$f" ] && basename "$f" .cue; done
  done
  for d in "$REPO/games/$GAME/work/build"/*/; do
    [ -d "$d" ] || continue
    for f in "$d"*.cue; do [ -f "$f" ] && basename "$f" .cue; done
  done
}

# 이미 있는 카드에서 MD5 를 배운다. 평평한 옛 자리(`sav/`)도 같이 본다.
learn_md5() {
  for d in "$SAV" "$MEDBASE/sav"; do
    for f in "$d"/*.mcr; do
      [ -f "$f" ] || continue
      b=$(basename "$f")
      b=${b%.mcr}; b=${b%.*}          # 슬롯 떼기
      printf '%s\n' "${b##*.}"        # 남은 꼬리가 MD5
    done
  done | sort -u | head -1
}

MD5=$(learn_md5)
[ -n "$MD5" ] || {
  echo "⛔ MD5 를 배울 카드가 없다 — $GAME 을 mednafen 으로 한 번 돌려 게임 안에서 저장한다." >&2
  echo "   sh scripts/emu.sh $GAME" >&2
  exit 1
}
echo "MD5: $MD5"

cp_v() {   # $1=원본 $2=대상
  if [ "$DRY" = 1 ]; then echo "  [dry] $(basename "$1") → $(basename "$2")"; return 0; fi
  # ⚠ 덮어쓰기 전에 한 세대를 남긴다 — 세이브는 재생성이 안 된다.
  [ -f "$2" ] && cp -p "$2" "$2.bak"
  cp -p "$1" "$2"
  echo "  $(basename "$1") → $(basename "$2")"
}

n=0
if [ "$DIR" = import ]; then
  echo "DuckStation → mednafen  ($SAV)"
  for slot in 1 2; do
    # ⚠ 글로브는 **여기서 리터럴로** 편다 — 변수에 담아 펴면 그 자리에서 공백에 쪼개져
    #   `Legend of Heroes I & II, The - ...` 가 산산조각 난다(sync-saves.sh 헤더와 같은 함정).
    for s in "$DUCK"/*_"$slot".mcd; do
      [ -f "$s" ] || continue
      case "$(basename "$s")" in
        *"Eiyuu Densetsu"*|*"Legend of Heroes"*) ;;
        *) continue ;;                    # ⚠ 남의 게임 카드가 같은 폴더에 산다
      esac
      # ⚠ 이름에 공백·`&` 가 있다 — IFS 를 개행으로 두지 않으면 단어마다 카드가 하나씩 생긴다.
      OLDIFS=$IFS; IFS='
'
      for nm in $(names | sort -u); do
        IFS=$OLDIFS
        cp_v "$s" "$SAV/$nm.$MD5.$((slot - 1)).mcr"; n=$((n + 1))
        IFS='
'
      done
      IFS=$OLDIFS
    done
  done
else
  echo "mednafen → DuckStation  ($DUCK)"
  mkdir -p "$DUCK"
  # ⚠ 되돌릴 때는 **하나만** 고른다 — 이름이 여럿이라 아무거나 쓰면 옛 진행분을 올릴 수 있다.
  for slot in 0 1; do
    newest=$(ls -t "$SAV"/*".$MD5.$slot.mcr" 2>/dev/null | head -1)
    [ -n "$newest" ] || continue
    cp_v "$newest" "$DUCK/Legend of Heroes I & II, The - Eiyuu Densetsu (Japan)_$((slot + 1)).mcd"
    n=$((n + 1))
  done
fi
[ "$n" -gt 0 ] || echo "⚠ 옮길 카드가 없었다"
