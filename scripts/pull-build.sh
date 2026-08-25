#!/bin/sh
# 작업 머신(dev)의 빌드 산출물을 이 맥으로 당긴다 — 인게임 QA 는 로컬이 빠르다.
#
#   sh scripts/pull-build.sh          # 원격 빌드를 목록에서 고른다(space 로 여러 개)
#   sh scripts/pull-build.sh ps1      # 걸러서 (게임·꼬리표 어느 쪽에 걸려도 된다)
#   sh scripts/pull-build.sh --all    # 원격에 있는 것 전부
#   sh scripts/pull-build.sh --all -j1  # 하나씩 (기본은 넷씩 동시에)
#
# ── 목록이 한 겹인 이유 (유저 확정 2026-08-21) ────────────────────────────────
# `emu.sh` 는 게임 → 이미지로 두 겹인데 여기는 **처음부터 빌드 목록**이다. 원격에 빌드가
# 많이 쌓이는 일이 없어서(대개 지금 굴리는 갈래 하나뿐이다) 겹을 나누면 Enter 만 두 번 치게
# 된다. 대신 걸러 쓸 수 있게 인자를 **꼬리표가 아니라 필터**로 받는다 — `ps1` 처럼.
#
# ⚠ **게임 고정을 풀었다.** 종전엔 `games/ps1-ed1+2` 가 박혀 있어 새턴 빌드는 받을 길이
#   없었다. 이제 원격의 `games/*/work/build/*` 를 통째로 훑는다.
#
# ⚠ **여러 개를 한 번에 받을 수 있다**(space 토글). 기본은 무선택이고 그냥 Enter 를 치면
#   커서에 있는 하나만 받는다 — 스페이스를 안 써도 예전과 똑같이 동작한다.
#
# ⚠ **워크트리 안까지 본다**(유저 확정 2026-08-22). 게임 작업은 워크트리에서 굴리므로 빌드가
#   `.claude/worktrees/<게임>/games/<게임>/work/build/<꼬리표>/` 에 나온다 — 메인 트리만 보면
#   **정작 지금 굴리는 빌드가 안 보인다**. 산출물을 루트 한 곳으로 모으는 안(publish-build.sh)도
#   있었지만 접었다: 워크트리끼리 간섭이 없는 게 낫고, **보는 쪽만 넓히면 되는 문제**였다.
#   사본을 만들면 「사본이 낡은 채로 정상으로 오해되는」 이 레포의 단골 사고가 하나 더 는다.
#
# ⚠ **꼬리표가 겹치면 워크트리가 이긴다**(유저 확정 2026-08-22). 꼬리표 기본값이 브랜치라
#   보통은 안 겹친다 — 메인 트리는 `main`, 워크트리는 `ps1-ed1-2` 처럼 갈린다. 그런데 dev 엔
#   양쪽에 `ps1-ed1-2` 가 있었다(메인 트리에서 그 브랜치로 빌드한 흔적, 실측). 그때 **지금
#   굴리는 쪽은 워크트리**이므로 그걸 남기고 메인 트리 것은 목록에서 뺀다.
#   목록엔 출처를 같이 찍고 받을 때 원격 경로를 헤더에 남긴다 — 어디서 온 건지 늘 보이게.
#   받는 자리는 `games/<게임>/work/build/<꼬리표>/` 하나다(맥은 QA 전용이라 워크트리를 안 판다).
#
# ⚠ **칸을 통째로 맞춘다.** 그 빌드 칸의 파일을 전부 받는다(변종이 있으면 같이 온다).
#   종전처럼 파일 이름을 인자로 받지 않는 이유는, 게임마다 이미지 이름이 다르기 때문이다.
#
# ⚠ 전송만 하면 안 된다. 이 레포의 1급 사고가 **낡거나 엉뚱한 이미지를 정상으로 오해하는 것**이라
#   (루트 CLAUDE.md 「빌드 규율」) 두 가지를 같이 본다:
#     · `*.failed` 가 있으면 **그 칸은 통째로 거부한다** — 실패한 빌드는 산출물을 무효화한다
#     · 받은 뒤 `.bin` 마다 sha1 을 대조한다
#
# ⚠ **하나가 실패해도 나머지는 계속 받는다**(유저 확정 2026-08-25). 종전엔 칸 하나가 실패하면
#   `exit 1` 로 그 자리에서 죽어, 여럿을 골라 놓고 자리를 비운 사이 **뒤엣것이 통째로 안 받아진
#   채** 돌아오는 일이 났다. 이제 칸마다 서브셸에서 돌리고 실패는 모아 뒀다 **끝에 요약**한다
#   (하나라도 실패하면 종료 코드는 1 이다 — CI 에서 조용히 성공으로 보이면 안 된다).
#   ⚠ 실패를 **덮지는 않는다** — 실패한 칸의 로컬 산출물은 「받다 만 것」이라 믿으면 안 된다.
#     요약이 그 칸을 이름으로 찍는다.
#
# ⚠ **기본이 병렬이다** — `-j4`(유저 확정 2026-08-25). `-j1` 이면 예전처럼 하나씩,
#   `--jobs 8` 로 올릴 수도 있다(숫자를 빼면 4).
#     · 병목은 대개 대역폭이라 2~4 면 충분하다. ssh 세션도 칸마다 셋(ls·rsync·sha1sum)이라
#       크게 올리면 원격 `MaxSessions`(기본 10)에 걸린다.
#     · **진행률은 칸마다 한 줄씩 동시에 보인다**(상태판). rsync 출력을 그냥 섞으면 `\r` 이
#       엉켜 못 읽으므로, 칸마다 **마지막 진행률 줄만** 파일에 흘려 두고 부모가 그 줄들을
#       0.3초마다 덮어 그린다. 자세한 로그(밑절미·sha1·오류)는 **칸이 끝난 뒤 순서대로** 뱉는다.
#     · 비대화형(파이프·CI)이면 상태판을 안 그린다 — 이스케이프가 로그에 남으면 못 읽는다.
set -eu

HOST=${DEV_HOST:-dev}
REMOTE_REPO=${DEV_REPO:-work/eiyuu-densetsu-patch}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
. "$ROOT/scripts/lib/select.sh"      # 화살표 키 선택 UI
TAB=$(printf '\t')

ALL=0
FILTER=""
JOBS=4
while [ $# -gt 0 ]; do
  case "$1" in
    --all) ALL=1 ;;
    # ⚠ `-j` 는 숫자가 붙어도(-j4) 떨어져도(-j 4) 되고, 아예 없으면 4 다.
    -j|--jobs) case "${2:-}" in ([0-9]*) JOBS=$2; shift ;; (*) JOBS=4 ;; esac ;;
    -j[0-9]*) JOBS=${1#-j} ;;
    --jobs=*) JOBS=${1#--jobs=} ;;
    -*) echo "모르는 옵션: $1" >&2; exit 2 ;;
    *) FILTER=$1 ;;
  esac
  shift
done
[ "$JOBS" -ge 1 ] 2>/dev/null || { echo "⛔ -j 는 1 이상의 수: $JOBS" >&2; exit 2; }

# 원격 빌드 칸 전부 — 최신순. `게임<탭>꼬리표<탭>원격경로` 로 뱉는다.
# ⚠ 글로브는 **원격 셸**이 편다(그래서 따옴표로 감싸지 않는다).
builds() {
  ssh "$HOST" "ls -dt $REMOTE_REPO/games/*/work/build/*/ \
                     $REMOTE_REPO/.claude/worktrees/*/games/*/work/build/*/ 2>/dev/null" 2>/dev/null \
  | while read -r d; do
    d=${d%/}
    t=${d##*/}
    g=${d%/work/build/*}; g=${g##*/}      # …/games/<게임>/work/build/<꼬리표> → <게임>
    printf '%s\t%s\t%s\n' "$g" "$t" "$d"
  done | awk -F'\t' '
    # 같은 게임·꼬리표면 워크트리 것을 남긴다. 처음 본 순서(=최신순)는 그대로 지킨다.
    { key = $1 FS $2; isw = (index($3, "/.claude/worktrees/") > 0)
      if (!(key in idx)) { idx[key] = ++n; line[n] = $0; wt[key] = isw }
      else if (isw && !wt[key]) { line[idx[key]] = $0; wt[key] = 1 } }
    END { for (i = 1; i <= n; i++) print line[i] }'
}

# 출처 — 워크트리면 그 이름, 아니면 main. 같은 게임·꼬리표가 둘일 때 이것으로 가른다.
origin_of() {
  case "$1" in
    */.claude/worktrees/*) _o=${1#*/.claude/worktrees/}; printf '워크트리 %s' "${_o%%/*}" ;;
    *) printf 'main' ;;
  esac
}

OLDIFS=$IFS; IFS='
'
# shellcheck disable=SC2046
set -- $(builds)
IFS=$OLDIFS
[ $# -gt 0 ] || { echo "원격에 빌드가 없다" >&2; exit 1; }

if [ -n "$FILTER" ]; then
  OLDIFS=$IFS; IFS='
'
  # ⚠ 패턴을 **여는 괄호로 연다** — `$( … )` 안에서 case 패턴의 `)` 를 셸이 명령치환의
  #   끝으로 읽어 `syntax error near unexpected token ';;'` 로 죽는다(실측).
  # shellcheck disable=SC2046
  set -- $(for e in "$@"; do case "$e" in (*"$FILTER"*) printf '%s\n' "$e" ;; esac; done)
  IFS=$OLDIFS
  [ $# -gt 0 ] || { echo "⛔ '$FILTER' 에 걸리는 빌드가 없다" >&2; exit 1; }
fi

row_build() {
  _g=${2%%"$TAB"*}; _r=${2#*"$TAB"}; _t=${_r%%"$TAB"*}; _p=${_r#*"$TAB"}
  _m=" [$(origin_of "$_p")]"
  if [ "$_t" = "${BR:-}" ]; then _m="$_m (현재 브랜치)"; fi
  if [ "$3" = 1 ]; then printf '\033[36m❯ %s · %s%s\033[0m\n' "$_g" "$_t" "$_m"
  else                  printf '  \033[2m%s ·\033[0m %s\033[2m%s\033[0m\n' "$_g" "$_t" "$_m"; fi
}

BR=$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null | sed 's#.*/##; s#[^A-Za-z0-9._-]#-#g' || true)

if [ "$ALL" = 1 ]; then
  # ⚠ 항목 안에 **탭**이 있으니 문자열로 이어 붙였다 다시 쪼개면 게임/꼬리표가 갈라진다.
  #   줄바꿈으로 잇고 IFS 를 개행으로 두고만 편다.
  ENTRIES=$(printf '%s\n' "$@")
else
  # 커서는 **현재 브랜치와 같은 꼬리표**에 놓고 시작한다(유저 확정 2026-08-15의 기본값을
  # 버리지 않고 커서로 옮긴 것이다 — Enter 만 치면 예전과 같다).
  _i=0
  for e in "$@"; do
    _i=$((_i + 1))
    _r=${e#*"$TAB"}
    if [ "${_r%%"$TAB"*}" = "$BR" ]; then SELECT_INDEX=$_i; fi
  done
  SELECT_RENDER=row_build
  # ⚠ 비대화형(파이프·CI)이면 **조용히 끝내지 않는다** — 후보를 찍고 어떻게 좁히는지 알린다.
  if PICK=$(select_multi "빌드" "$@"); then
    :
  else
    if [ $? = 2 ]; then
      echo "⛔ 후보가 여럿인데 고를 수가 없다(비대화형) — 필터로 좁힌다:" >&2
      for e in "$@"; do
        _g=${e%%"$TAB"*}; _r=${e#*"$TAB"}
        echo "     $_g · ${_r%%"$TAB"*} [$(origin_of "${_r#*"$TAB"}")]" >&2
      done
    fi
    exit 1
  fi
  SELECT_RENDER=; SELECT_INDEX=
  ENTRIES=$PICK
fi

# ⚠ rsync 인자 규약이 **구현에 따라 정반대**다(버전 고저가 아니다) — 맥 한 대 안에도 둘이
#   깔려 있어 PATH 순서로 갈린다. 그래서 골라 쓰는 게 아니라 **감지해서** 쓴다.
#     · 스톡 macOS(구 GNU 2.6.9 · 15+ 는 Apple openrsync): 원격 경로가 **원격 셸을 그대로 통과**한다.
#       감싸지 않으면 bash 가 `syntax error near unexpected token '('` 로 죽는다 → 작은따옴표 필요.
#     · 3.2.4+ (Homebrew): "modern arg-protection" 이 기본이라 셸을 안 태운다. 여기에 따옴표를 씌우면
#       그 따옴표가 **파일명의 일부**가 되어 `/root/'work/...` 를 찾다 죽는다(실측 2026-08-10).
#   `--secluded-args`(구 `--protect-args`) 유무가 그 경계다.
if rsync --help 2>&1 | grep -q -- '--secluded-args'; then Q=''; else Q="'"; fi
HAVE_COPY_DEST=0
rsync --help 2>&1 | grep -q -- '--copy-dest' && HAVE_COPY_DEST=1

NL='
'
OLDIFS=$IFS; IFS=$NL
# shellcheck disable=SC2046
set -- $ENTRIES
IFS=$OLDIFS

# 칸마다 로그(`<i>.log`)·진행률 한 줄(`<i>.stat`)·rsync 종료 상태(`<i>.rc`)를 여기 둔다.
TMPD=$(mktemp -d "${TMPDIR:-/tmp}/pull-build.XXXXXX")
trap 'rm -rf "$TMPD"' EXIT HUP INT TERM
BOARD=0; [ -t 1 ] && BOARD=1   # 비대화형이면 상태판을 안 그린다
COLS=$(tput cols 2>/dev/null || echo 80)

# ── 칸 하나 받기 ────────────────────────────────────────────────────────────
# **백그라운드 서브셸**에서 돈다. 안의 `exit 1` 은 이 칸만 끝내고, 부모가 `wait` 로 그 상태를
# 받아 실패 목록에 적는다.
# ⚠ `if pull_one …` 로 부르면 안 된다 — 조건 자리에서는 `set -e` 가 **함수 안까지 통째로**
#   꺼져서 rsync 가 죽어도 뒤의 sha1 대조까지 마저 돌아 「성공」으로 보인다(POSIX).
stat_set() { printf '%s\n' "$1" > "$STATF"; }

# rsync 를 돌리되 **진행률은 상태판으로, 나머지는 로그로** 가른다.
# ⚠ 파이프의 종료 상태는 마지막 명령의 것이라 rsync 의 실패가 묻힌다. `pipefail` 은 dash 에
#   없으므로 상태를 파일로 넘긴다. `set +e` 는 **파이프 성분 서브셸 안**이라 부모의 errexit 을
#   안 건드린다 — 안 끄면 rsync 가 죽는 순간 그 서브셸이 상태를 못 적는다.
# ⚠ 가르는 일을 `tr | while read` 로 하면 **상태판이 뭉텅이로 늦는다** — tr 은 출력이 터미널이
#   아니면 블록 버퍼라 진행률이 몇 초씩 고여 있다가 한꺼번에 나온다(macOS 엔 `stdbuf` 도 없다).
#   awk 하나로 갈라 매 판마다 `fflush`·`close` 한다. RS 는 한 글자만 되는 awk(맥 기본)가 있어
#   `\r` 로 끊고 그 안의 줄은 손으로 쪼갠다.
run_rsync() {
  { set +e; rsync -a --progress "$@" 2>&1; echo $? > "$RCF"; } \
  | awk -v f="$STATF" 'BEGIN { RS = "\r" }
      { n = split($0, a, "\n"); last = ""
        for (i = 1; i <= n; i++) if (a[i] ~ /[^ \t]/) last = a[i]
        if (last == "") next
        print last > f; close(f)                       # 상태판 — 늘 마지막 한 줄만
        for (i = 1; i <= n; i++)                       # 로그 — 진행률 아닌 줄만
          if (a[i] ~ /[^ \t]/ && a[i] !~ /%/) print a[i]
        fflush() }'
  read -r _s < "$RCF"
  [ "$_s" = 0 ] || { echo "⛔ rsync 실패(종료 $_s)" >&2; exit 1; }
}

pull_one() {
  GAME=$1; TAG=$2; REMOTE_BUILD=$3
  STATF="$TMPD/$4.stat"; RCF="$TMPD/$4.rc"
  LOCAL_BUILDS="$ROOT/games/$GAME/work/build"
  LOCAL_BUILD="$LOCAL_BUILDS/$TAG"
  echo "── $GAME · $TAG [$(origin_of "$REMOTE_BUILD")]"
  echo "   원격: $REMOTE_BUILD"

  stat_set "원격 칸을 훑는다"
  _old=$IFS; IFS=$NL
  # shellcheck disable=SC2046
  set -- $(ssh "$HOST" "ls '$REMOTE_BUILD'" 2>/dev/null)
  IFS=$_old
  [ $# -gt 0 ] || { echo "⛔ 원격 칸이 비었다: $REMOTE_BUILD" >&2; exit 1; }
  for f in "$@"; do
    case "$f" in
      *.failed) echo "⛔ 실패 표식이 있다($f) — 이 칸은 받지 않는다. 먼저 빌드를 고쳐라." >&2; exit 1 ;;
    esac
  done

  mkdir -p "$LOCAL_BUILD"
  for f in "$@"; do
    # ⚠ **새 칸의 첫 내려받기도 델타로 만든다.** rsync 는 받는 쪽에 같은 이름의 파일이 있어야
    #   차분을 뜨는데, 꼬리표가 새로 생기면 그 자리가 비어 있어 241MB 를 통째로 받는다.
    #   칸끼리 실제로 다른 바이트는 **49KB(0.02%)** 뿐이라, 이미 받아 둔 다른 칸을 밑절미
    #   (`--copy-dest`)로 주면 첫 내려받기도 거의 공짜가 된다.
    #   ⚠ Apple openrsync 엔 이 옵션이 없다 — 있을 때만 쓴다.
    BASIS=""
    if [ "$HAVE_COPY_DEST" = 1 ] && [ ! -f "$LOCAL_BUILD/$f" ]; then
      for c in "$LOCAL_BUILDS"/*/; do
        [ -f "$c$f" ] || continue
        BASIS="--copy-dest=$c"; echo "   밑절미: $(basename "$c")"; break
      done
    fi
    # ⚠ 파일당 한 번씩 부른다. `host:a host:b` 로 원격 소스를 둘 이상 주는 건 GNU rsync 3.0+
    #   문법이라 스톡 macOS 의 2.6.9 에서 usage error 로 죽는다(실측).
    stat_set "$f 받는 중"
    # shellcheck disable=SC2086
    run_rsync $BASIS "$HOST:$Q$REMOTE_BUILD/$f$Q" "$LOCAL_BUILD/"
  done

  # ⚠ 받은 뒤 sha1 을 찍는다 — 같은 이름으로 다른 빌드가 나올 수 있다(`BATTLE_JP=1`).
  for f in "$@"; do
    case "$f" in *.bin) ;; *) continue ;; esac
    stat_set "$f sha1 대조"
    R=$(ssh "$HOST" "sha1sum '$REMOTE_BUILD/$f'" | cut -d' ' -f1)
    L=$(shasum -a 1 "$LOCAL_BUILD/$f" | cut -d' ' -f1)
    if [ "$R" != "$L" ]; then
      echo "⛔ 전송 중 손상: $f" >&2
      echo "   원격 $R" >&2
      echo "   로컬 $L" >&2
      exit 1
    fi
    echo "   sha1 ✅ $f"
  done
  stat_set "끝"
  echo "✅ $LOCAL_BUILD"
}

# ── 상태판 ──────────────────────────────────────────────────────────────────
# 배치가 도는 동안 **따로 띄운 프로세스**가 그린다. 부모는 그동안 `wait` 만 하므로 둘이
# 같은 화면에 겹쳐 쓸 일이 없고, 종료 상태는 `wait` 에서 그대로 받는다(`.done` 파일 같은
# 우회가 필요 없다 — 그 우회는 서브셸의 errexit 을 다시 꺼 놓게 된다).
# ⚠ 줄이 넘치면 되감기 계산이 깨진다 — 폭을 잘라 그린다(한글은 두 칸이라 넉넉히 뺀다).
board_run() {
  _drawn=0
  while [ ! -f "$TMPD/stop" ]; do
    board_draw
    sleep 0.3
  done
  board_draw                                   # 마지막 상태를 한 번 더
  [ "$_drawn" = 0 ] || {                       # 지운다 — 자세한 로그는 부모가 뱉는다
    printf '\033[%dA' "$_drawn"
    _i=0; while [ "$_i" -lt "$_drawn" ]; do printf '\033[2K\n'; _i=$((_i + 1)); done
    printf '\033[%dA' "$_drawn"
  }
}
board_draw() {
  [ "$_drawn" = 0 ] || printf '\033[%dA' "$_drawn"
  _drawn=0
  _o=$IFS; IFS=$NL
  for _j in $BATCH; do
    IFS=$_o
    _r=${_j#* }; _ji=${_r%% *}; _lab=${_r#* }
    _s=…
    [ ! -f "$TMPD/$_ji.stat" ] || _s=$(cat "$TMPD/$_ji.stat" 2>/dev/null || echo …)
    printf '\033[2K   \033[2m%s\033[0m\n' "$(printf '%s  %s' "$_lab" "$_s" | cut -c1-$((COLS - 12)))"
    _drawn=$((_drawn + 1))
    IFS=$NL
  done
  IFS=$_o
}

# 띄워 둔 배치를 기다린다. 로그는 **띄운 순서대로** 뱉는다(끝난 순서가 아니다 — 목록 순서와
# 어긋나면 어느 칸 얘긴지 못 읽는다).
flush_batch() {
  [ -n "$BATCH" ] || return 0
  BPID=
  if [ "$BOARD" = 1 ]; then rm -f "$TMPD/stop"; board_run & BPID=$!; fi
  _o=$IFS; IFS=$NL
  for _j in $BATCH; do
    IFS=$_o
    _pid=${_j%% *}; _r=${_j#* }; _ji=${_r%% *}; _lab=${_r#* }
    if wait "$_pid"; then _st=0; else _st=1; fi
    eval "ST_$_ji=$_st"
    IFS=$NL
  done
  IFS=$_o
  if [ -n "$BPID" ]; then : > "$TMPD/stop"; wait "$BPID" 2>/dev/null || true; fi
  _o=$IFS; IFS=$NL
  for _j in $BATCH; do
    IFS=$_o
    _r=${_j#* }; _ji=${_r%% *}; _lab=${_r#* }
    eval "_st=\$ST_$_ji"
    cat "$TMPD/$_ji.log"
    if [ "$_st" = 0 ]; then
      OKN=$((OKN + 1))
    else
      FAILN=$((FAILN + 1)); FAILED="$FAILED  · $_lab$NL"
      echo "⛔ 실패: $_lab — 넘어간다" >&2
    fi
    IFS=$NL
  done
  IFS=$_o
  BATCH=""; NJOB=0
}

BATCH=""    # "<pid> <idx> <라벨>" 줄들
NJOB=0; IDX=0; OKN=0; FAILN=0; FAILED=""

for e in "$@"; do
  GAME=${e%%"$TAB"*}; _r=${e#*"$TAB"}; TAG=${_r%%"$TAB"*}
  REMOTE_BUILD=${_r#*"$TAB"}                 # 원격 경로는 목록이 준 것을 그대로 쓴다
  IDX=$((IDX + 1))
  pull_one "$GAME" "$TAG" "$REMOTE_BUILD" "$IDX" >"$TMPD/$IDX.log" 2>&1 &
  BATCH="$BATCH$! $IDX $GAME · $TAG$NL"
  NJOB=$((NJOB + 1))
  [ "$NJOB" -lt "$JOBS" ] || flush_batch
done
flush_batch

if [ -n "$FAILED" ]; then
  printf '\n⛔ 실패 %d 칸 · 성공 %d 칸\n%s' "$FAILN" "$OKN" "$FAILED" >&2
  echo "   ⚠ 실패한 칸은 **받다 만 것**일 수 있다 — 다시 받기 전엔 쓰지 않는다." >&2
  exit 1
fi
[ "$OKN" -le 1 ] || echo "✅ $OKN 칸 전부 받았다"
