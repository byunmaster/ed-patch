#!/bin/sh
# PS1 메모리카드를 DuckStation ↔ mednafen 사이에서 옮긴다.
#
#   sh scripts/emu/ps1-card.sh                      # 게임·방향을 목록에서 고른다 (↑↓ · Enter)
#   sh scripts/emu/ps1-card.sh ps1-ed1+2 import     # DuckStation → mednafen
#   sh scripts/emu/ps1-card.sh ps1-ed1+2 export     # mednafen → DuckStation
#   sh scripts/emu/ps1-card.sh --dry                # 무엇을 할지만 보여준다
#
# `duckstation.sh` 를 지우면서(2026-08-21) DuckStation 쪽 카드 동기화도 같이 없어졌다.
# 2차 의견이 필요할 때 세이브를 넘기는 길이 이 스크립트다.
#
# ── 왜 게임을 지정하나 — 카드는 「PS1 공통」이 아니다 ─────────────────────────
# 실물 카드는 한 장에 여러 게임이 들어가지만, **두 에뮬 다 이미지 이름으로 카드 파일을
# 가른다**(실측 2026-08-28) — DuckStation 은 게임별 카드가 기본이고 mednafen 은 파일명에
# 이미지 이름을 박는다. 그래서 「어느 게임」이 곧 「어느 파일」이다. 소장 PS1 원본도 셋이라
# (ed1+2 · ed3 · ed4) 고를 것이 실제로 있다. 다만 **칠 필요는 없다** — 안 주면 목록에서 고른다.
#
# ⚠ **방향은 기본값을 안 둔다**(2026-08-28). 종전엔 인자가 없으면 조용히 import 였는데,
#   두 방향 다 남의 세이브를 덮어쓰는 쓰기라 「무심코 반대로」가 곧 사고다. tty 가 없으면
#   (파이프·CI) 묻는 대신 시끄럽게 실패한다 — 자동 실행에서 프롬프트가 멈춰 서거나 방향을
#   추측하는 것보다 낫다.
#
# ── 변환이랄 게 없다 ─────────────────────────────────────────────────────────
# 둘 다 **생 128KB 카드 이미지**다(실측: 131,072바이트, 첫 두 바이트 `4d43` = "MC").
# 다른 건 **파일명뿐**이라 이 스크립트가 하는 일도 복사와 이름 짓기다:
#
#   DuckStation  <이미지 이름>_1.mcd            _1 · _2
#   mednafen     <이미지 이름>.<MD5>.0.mcr      .0 · .1
#
# ⚠ **MD5 는 우리가 못 만든다** — mednafen 이 디스크에서 뽑는 값이라, 이미 있는 `.mcr` 에서
#   배운다. 그 게임을 mednafen 으로 한 번도 안 돌렸으면 배울 데가 없으니 그때는 멈추고
#   알려 준다(한 번 돌려 게임 안에서 저장하면 생긴다).
#
# ⚠ **원본과 빌드는 이름이 다르니 카드도 따로다**(`Legend of Heroes...(Japan)` vs
#   `Eiyuu Densetsu (KR)`). 그래서 import 는 **알고 있는 이름 전부에** 넣는다 — 어느 이미지로
#   켜든 같은 세이브가 보이는 게 QA 에서 맞다. 128KB짜리라 몇 벌 더 둬도 부담이 없다.
#   (MD5 는 원본과 빌드가 같다 — 실측 `eb5fce…`. 디스크 내용 해시가 아닌 모양이다.)
#
# ⚠ **이름을 하드코딩하지 않는다**(2026-08-28). 종전엔 DuckStation 쪽 필터와 export 목적지가
#   ed1+2 문자열로 박혀 있었다. 게임이 인자로 굳어 있을 땐 안 틀렸지만 **고를 수 있게 되는
#   순간 조용히 틀린다** — ed3 를 골라도 ed1+2 카드를 읽고 ed1+2 카드를 덮어쓴다. 둘 다
#   `names()`(그 게임의 원본·빌드 이미지 이름)에서 유도한다.
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)   # scripts/emu → 레포 루트
MEDBASE=${MEDNAFEN_HOME:-$HOME/.mednafen}
DUCK=${DUCKSTATION_SUPPORT:-$HOME/Library/Application Support/DuckStation}/memcards
. "$HERE/../lib/select.sh"        # 화살표 키 선택 UI (emu.sh 와 같은 것)

usage() {
  echo "사용법: $0 [<ps1 게임>] [import|export] [--dry]" >&2
  echo "        인자를 빼면 목록에서 고른다" >&2
}

# ── 인자 ────────────────────────────────────────────────────────────────────
# 순서를 안 따진다 — 게임은 `ps1-` 접두사로, 방향은 이름으로 저절로 갈린다.
GAME=; DIR=; DRY=0
for a in "$@"; do
  case "$a" in
    -h|--help) usage; exit 0 ;;
    import|export) DIR=$a ;;
    --dry|-n) DRY=1 ;;
    ps1-*) GAME=$a ;;
    [a-z0-9]*-*) echo "⛔ PS1 게임만 된다: $a" >&2; exit 2 ;;
    *) echo "모르는 인자: $a" >&2; usage; exit 2 ;;
  esac
done

# 소장 원본이 있는 PS1 게임만 든다 — 없는 걸 고르게 하면 고른 뒤에 실패한다(emu.sh 와 같은 규칙).
ps1_games() {
  for _d in "$REPO"/originals/*/ps1-*/; do [ -d "$_d" ] && basename "$_d"; done | sort -u
}

# ── 게임 고르기 ─────────────────────────────────────────────────────────────
# 세이브 칸이 있는지를 같이 보여 준다 — mednafen 으로 한 번도 안 돌린 게임은 MD5 를 배울 데가
# 없어 어차피 멈추는데, 고르기 전에 보이면 헛걸음이 없다.
row_game() {
  if [ -d "$MEDBASE/sav/$2" ]; then _st="mednafen 세이브 있음"; else _st="mednafen 세이브 없음"; fi
  if [ "$3" = 1 ]; then printf '\033[36m❯ %-11s %s\033[0m\n' "$2" "$_st"
  else                  printf '  %-11s \033[2m%s\033[0m\n' "$2" "$_st"; fi
}

if [ -n "$GAME" ]; then
  ps1_games | grep -qx "$GAME" || {
    echo "⛔ 소장 원본이 없다: $GAME" >&2
    echo "   있는 것: $(ps1_games | tr '\n' ' ')" >&2
    exit 2
  }
else
  if ! has_tty; then
    echo "⛔ 게임을 고를 수가 없다(비대화형) — 인자로 지정한다: $(ps1_games | tr '\n' ' ')" >&2
    exit 2
  fi
  SELECT_RENDER=row_game
  # shellcheck disable=SC2046
  GAME=$(select_option "게임" $(ps1_games)) || exit 1
  SELECT_RENDER=
fi

# ── 방향 고르기 ─────────────────────────────────────────────────────────────
# 값은 `import`/`export` 인데 화면에 그것만 띄우면 어느 쪽이 어디로 가는지가 안 보인다.
# 「값<탭>설명」줄로 들고 라벨은 렌더에서만 쓴다 — emu.sh 의 이미지 목록과 같은 수법이다.
TAB=$(printf '\t')
row_dir() {
  _va=${2%%"$TAB"*}; _de=${2#*"$TAB"}
  if [ "$3" = 1 ]; then printf '\033[36m❯ %-7s %s\033[0m\n' "$_va" "$_de"
  else                  printf '  %-7s \033[2m%s\033[0m\n' "$_va" "$_de"; fi
}

if [ -z "$DIR" ]; then
  if ! has_tty; then
    echo "⛔ 방향을 고를 수가 없다(비대화형) — 인자로 지정한다:" >&2
    echo "     $0 $GAME import    # DuckStation → mednafen" >&2
    echo "     $0 $GAME export    # mednafen → DuckStation" >&2
    exit 2
  fi
  SELECT_RENDER=row_dir
  # ⚠ Esc(rc=3)도 취소로 친다 — 뒤로 갈 자리가 게임 목록인데, 게임을 인자로 준 경우엔 그 칸이
  #   없다. 갈래를 둘로 두는 값보다 「Esc = 그만둔다」가 한결같은 편이 낫다.
  PICK=$(select_option "전송 방향" \
    "import${TAB}DuckStation → mednafen" \
    "export${TAB}mednafen → DuckStation") || exit 1
  SELECT_RENDER=
  DIR=${PICK%%"$TAB"*}
fi

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

# ⚠ 한 번만 편다 — 이름 목록은 실행 중에 안 바뀌는데 글로브가 여러 폴더를 돈다.
NAMES=$(names | sort -u)
# 「이 이름이 우리 것인가」를 case 로 물어보려고 구분자로 감싼다(이름에 `|` 는 없다).
NAMES_BAR="|$(printf '%s' "$NAMES" | tr '\n' '|')|"

# 이 게임의 원본 이미지 이름 — export 목적지의 마지막 보루다.
# ⚠ **끝을 `return 0` 으로 닫는다**(set -e · 루트 CLAUDE.md 「코드 스타일」).
orig_name() {
  for r in jp kr us; do
    for f in "$REPO/originals/$r/$GAME"/*.cue; do
      [ -f "$f" ] && { basename "$f" .cue; return 0; }
    done
  done
  printf '%s\n' "$NAMES" | head -1
  return 0
}

# 이미 있는 카드에서 MD5 를 배운다. 평평한 옛 자리(`sav/`)도 같이 본다.
# ⚠ 평평한 자리엔 **다른 게임 카드도 산다**(실측: SMD·PS1 이 섞여 있다). 게임 칸(`$SAV`)은
#   이미 갈려 있으니 그대로 믿고, 평평한 자리만 **이 게임 이미지 이름으로 거른다** — 안 그러면
#   남의 게임 MD5 를 배워 읽히지도 않는 이름으로 카드를 만든다.
learn_md5() {
  for f in "$SAV"/*.mcr; do
    [ -f "$f" ] || continue
    b=$(basename "$f"); b=${b%.mcr}; b=${b%.*}
    printf '%s\n' "${b##*.}"
  done
  for f in "$MEDBASE/sav"/*.mcr; do
    [ -f "$f" ] || continue
    b=$(basename "$f"); b=${b%.mcr}; b=${b%.*}   # 슬롯 떼기 → "<이름>.<MD5>"
    case "$NAMES_BAR" in *"|${b%.*}|"*) ;; *) continue ;; esac
    printf '%s\n' "${b##*.}"
  done
}

MD5=$(learn_md5 | sort -u | head -1)
[ -n "$MD5" ] || {
  echo "⛔ MD5 를 배울 카드가 없다 — $GAME 을 mednafen 으로 한 번 돌려 게임 안에서 저장한다." >&2
  echo "   sh scripts/emu.sh $GAME" >&2
  exit 1
}
echo "$GAME  ·  MD5: $MD5"

cp_v() {   # $1=원본 $2=대상
  if [ "$DRY" = 1 ]; then echo "  [dry] $(basename "$1") → $(basename "$2")"; return 0; fi
  # ⚠ 덮어쓰기 전에 한 세대를 남긴다 — 세이브는 재생성이 안 된다.
  [ -f "$2" ] && cp -p "$2" "$2.bak"
  # ⚠ **`-p` 를 쓰지 않는다** — 원본 mtime 을 물려주면 `emu.sh` 의 pull(`rsync -u`)이
  #   「로컬이 더 낡았다」고 보고 **방금 넣은 카드를 dev 의 옛 카드로 되돌린다.**
  #   2026-08-25 실측: 슬롯2(mtime 08-18)를 넣었더니 다음 실행에서 dev 의 08-21 판이 덮었고
  #   그게 그대로 다시 올라갔다. 옮긴 시각이 곧 이 카드의 나이다.
  cp "$1" "$2"
  echo "  $(basename "$1") → $(basename "$2")"
  return 0
}

n=0
if [ "$DIR" = import ]; then
  echo "DuckStation → mednafen  ($SAV)"
  for slot in 1 2; do
    # ⚠ 글로브는 **여기서 리터럴로** 편다 — 변수에 담아 펴면 그 자리에서 공백에 쪼개져
    #   `Legend of Heroes I & II, The - ...` 가 산산조각 난다(sync-saves.sh 헤더와 같은 함정).
    for s in "$DUCK"/*_"$slot".mcd; do
      [ -f "$s" ] || continue
      # ⚠ **남의 게임 카드가 같은 폴더에 산다.** 「이 게임 것인가」는 카드 이름에서 `_N.mcd` 를
      #   떼고 우리가 아는 이미지 이름과 대조해 판정한다 — DuckStation 카드 이름이 곧 이미지
      #   이름이라 성립한다(실측 2026-08-28).
      b=$(basename "$s"); b=${b%"_$slot.mcd"}
      case "$NAMES_BAR" in *"|$b|"*) ;; *) continue ;; esac
      # ⚠ 이름에 공백·`&` 가 있다 — IFS 를 개행으로 두지 않으면 단어마다 카드가 하나씩 생긴다.
      OLDIFS=$IFS; IFS='
'
      for nm in $NAMES; do
        IFS=$OLDIFS
        cp_v "$s" "$SAV/$nm.$MD5.$((slot - 1)).mcr"; n=$((n + 1))
        IFS='
'
      done
      IFS=$OLDIFS
    done
  done
  [ "$n" -gt 0 ] || {
    echo "⚠ DuckStation 에서 이 게임 카드를 못 찾았다 — 이름이 이미지와 달라졌을 수 있다." >&2
    echo "   아는 이름: $(printf '%s' "$NAMES" | tr '\n' '·')" >&2
    ls -1 "$DUCK" 2>/dev/null | sed 's/^/   있는 카드: /' >&2 || true
  }
else
  echo "mednafen → DuckStation  ($DUCK)"
  mkdir -p "$DUCK"
  # ⚠ 되돌릴 때 **소스는 하나만** 고른다 — 이름이 여럿이라 아무거나 쓰면 옛 진행분을 올릴 수 있다.
  for slot in 0 1; do
    newest=$(ls -t "$SAV"/*".$MD5.$slot.mcr" 2>/dev/null | head -1)
    [ -n "$newest" ] || continue
    # 목적지는 **DuckStation 에 이미 있는 그 게임 카드**다(원본으로 보고 있으면 원본 카드,
    # 빌드로 보고 있으면 빌드 카드). 하나도 없으면 원본 이름으로 새로 만든다 — 안 쓰는 이름의
    # 카드를 함부로 늘리지 않으려는 것이다.
    m=0
    OLDIFS=$IFS; IFS='
'
    for nm in $NAMES; do
      IFS=$OLDIFS
      if [ -f "$DUCK/${nm}_$((slot + 1)).mcd" ]; then
        cp_v "$newest" "$DUCK/${nm}_$((slot + 1)).mcd"; n=$((n + 1)); m=$((m + 1))
      fi
      IFS='
'
    done
    IFS=$OLDIFS
    if [ "$m" = 0 ]; then
      cp_v "$newest" "$DUCK/$(orig_name)_$((slot + 1)).mcd"; n=$((n + 1))
    fi
  done
  [ "$n" -gt 0 ] || echo "⚠ 옮길 카드가 없었다 — $SAV 에 이 MD5 카드가 없다" >&2
fi
