#!/bin/sh
# 낡은 빌드 칸을 치운다 — 로컬에서도, dev 에서도 **이 스크립트 하나로**.
#
#   sh scripts/clean-build.sh            # 목록에서 고른다 (space 토글, Enter 확정)
#   sh scripts/clean-build.sh ss         # 걸러서 (게임·꼬리표 어느 쪽에 걸려도 된다)
#   sh scripts/clean-build.sh --stale    # 안 굴리는 갈래를 **묻지 않고** 전부 (자동화용)
#   sh scripts/clean-build.sh --failed   # 실패 산출물(*.failed)만 — 정상 이미지는 안 건드린다
#   sh scripts/clean-build.sh --remote   # dev 에서 같은 걸 돌린다 (인자는 그대로 넘어간다)
#
# ── 왜 필요한가
# 빌드 칸은 **꼬리표(=브랜치)별로 갈린다**(`shared/build_tag.py`). 갈래를 옮겨 다니면 칸이
# 계속 늘어나는데 이미지 하나가 240~770MB 다 — 실측 2026-08-25 에 dev 에 **2.9GB** 가
# 쌓여 있었고 그중 1.5GB 는 워크트리로 옮기기 전 메인 트리에 남은 것이었다.
#
# ── 무엇을 지우나 (그리고 무엇을 절대 안 지우나)
# 🔴 **`work/build/<꼬리표>/` 만** 건드린다. 같은 `work/` 라도 나머지는 성격이 다르다 —
#      `derived/`  원본에서 파생 — ⚠ **빌드가 읽는 입력**이다. 지우면 빌드가 아예 안 돈다
#                  (2026-07-30 레포 이관 때 실제로 겪었다)
#      `review/`   검토표·페이로드 — 원문 포함. 다시 만드는 데 오래 걸린다
#      `dist/`     배포 차분
#    빌드 칸만 「순수 출력, 2분이면 재생성」이다(루트 `CLAUDE.md`).
# 🔴 **고르는 게 기본이다.** 이 레포는 「내가 만든 게 확실하지 않으면 안 지운다」로 한 번
#    크게 물렸다(유저 소장물 삭제, 복구 불가). 그래서 전부 지우기가 아니라 **목록에서
#    고르기**이고, 고른 뒤에도 한 번 더 묻는다. 목록엔 지워도 되는 이유를 같이 찍는다:
#      `현재`   그 트리의 **지금 브랜치**에서 나올 꼬리표 — 지우면 다시 빌드해야 한다.
#               판정은 **정본에 물어본다**(`shared/build_tag.py`) — 셸로 다시 구현하지 않는다.
#               ⚠ 시간이 아니라 **브랜치**로 본다 — 한 시간째 QA 중이라 아무도 안 건드린
#                 이미지가 「낡았다」로 떨어지면 안 된다
#      `미상`   꼬리표를 못 읽었다 — **안 굴린다고 단정하지 않고 그냥 안 건드린다**
#      `작업중` 최근 $FRESH 분 안에 건드려진 칸 — **다른 세션이 지금 굴리는 중일 수 있다**.
#               ⚠ 이게 있는 이유는 **`실패` 를 이기기 위해서**다. 빌드 도중엔 `*.failed` 가
#                 잠깐 떠 있는데, 그것만 보면 「무효 산출물」로 지워 버린다.
#               🔴 이 레포는 워크트리를 여럿 띄워 병행한다(루트 `CLAUDE.md`). 실측 2026-08-25:
#               정리하려던 그 순간 `ss-ed3` 세션이 빌드 중이었고 `*.failed` 까지 떠 있었다 —
#               「실패했으니 지운다」로 갔으면 남의 작업을 날렸다.
#      `실패`   `*.failed` 다 — 실패한 빌드는 산출물을 무효화한다(레포 빌드 규율)
#      (표시 없음) 안 굴리는 갈래
# 🔴 **성공·실패가 한 칸에 섞여 있으면 줄을 가른다**(유저 지적 2026-08-26). 예전엔 칸 하나가
#    한 줄이고 `*.failed` 가 **하나라도** 있으면 그 줄에 `실패` 딱지가 붙었는데, 지우는 건
#    `rm -rf` 로 **칸 통째**였다 — 「실패 산출물이니 지워도 되겠지」로 고른 순간 옆에 있던
#    정상 이미지까지 같이 날아간다. 실패분만도 240~770MB 라 그것만 걷어내고 싶은 것도 당연한
#    요구다. 그래서 섞인 칸은 두 줄로 낸다:
#      `(*.failed 만)`    그 칸의 `*.failed` 만 지운다 — 정상 이미지는 남는다
#      `(실패분 빼고)`    나머지만 지운다
#    둘 다 고르면 칸이 통째로 비고, 빈 칸은 마지막에 `rmdir` 로 걷는다.
#    ⚠ **`작업중` 칸은 안 가른다** — 빌드 도중엔 `*.failed` 가 잠깐 떠 있어서, 가르면
#      「실패분만 지운다」가 남의 빌드 중간 산출물을 지우는 짓이 된다.
# ⚠ 커서는 **안 굴리는 갈래의 첫 칸**에서 시작한다 — 아무것도 안 고르고 Enter 를 쳐도
#   「현재」 칸이 날아가지 않게. (`select_multi` 는 무선택 Enter 를 커서 하나로 친다)
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
. "$ROOT/scripts/lib/select.sh"      # 화살표 키 선택 UI
TAB=$(printf '\t')
HOST=${DEV_HOST:-dev}
REMOTE_REPO=${DEV_REPO:-work/eiyuu-densetsu-patch}

FRESH=${CLEAN_FRESH_MIN:-10}   # 이 분 안에 건드려진 칸은 「작업중」으로 본다
YES=0
STALE=0
FAILED=0
FILTER=""
REMOTE=0
for a in "$@"; do
  case "$a" in
    --yes|-y) YES=1 ;;
    --stale)  STALE=1 ;;
    --failed) FAILED=1 ;;
    --remote) REMOTE=1 ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "모르는 인자: $a" >&2; exit 2 ;;
    *)  FILTER=$a ;;
  esac
done

# ── 원격은 **같은 스크립트를 저쪽에서** 돌린다 (규칙을 두 벌 안 든다)
if [ "$REMOTE" = 1 ]; then
  args=""
  for a in "$@"; do [ "$a" = "--remote" ] || args="$args $a"; done
  echo "── $HOST:$REMOTE_REPO"
  # shellcheck disable=SC2029
  exec ssh -t "$HOST" "cd $REMOTE_REPO && sh scripts/clean-build.sh$args"
fi

# 그 트리가 **지금 굴리는 꼬리표** — 🔴 **정본에 물어본다**(`shared/build_tag.py`).
# 셸로 다시 구현하면(브랜치 끝마디 + 글자 치환) 지금은 맞아도 규칙이 갈리는 날 **쓰고 있는
# 이미지를 지운다.** 이 판정은 조용히 틀리면 손해가 되돌릴 수 없는 자리다 — 정본이 하나여야 한다.
# ⚠ `ED_BUILD_TAG` 는 **떼고** 부른다. 그게 켜져 있으면 트리마다 다른 답이 나와야 하는데
#   전부 같은 값이 돌아온다.
# ⚠ 못 읽으면 빈 문자열이다 — 부르는 쪽이 「모른다」로 받아 **아무것도 안 지운다**(아래).
live_tag() {
  env -u ED_BUILD_TAG python3 -c 'import sys
sys.path.insert(0, sys.argv[1] + "/shared")
from build_tag import build_tag
print(build_tag())' "$1" 2>/dev/null || true
}

origin_of() {
  case "$1" in
    */.claude/worktrees/*) _o=${1#*/.claude/worktrees/}; printf '워크트리 %s' "${_o%%/*}" ;;
    *) printf 'main' ;;
  esac
}

# 빌드 칸 전부 — `게임<탭>꼬리표<탭>MB<탭>표시<탭>경로`. 큰 것부터.
#
# 🔴 **심볼릭 링크를 풀고 같은 자리를 하나로 묶는다**(실측 2026-08-25). 메인 트리의
#    `games/<게임>/work/build` 가 **워크트리로 가는 심볼릭 링크**로 걸려 있었다 —
#    링크를 안 풀면 같은 칸이 「main」과 「워크트리」로 **두 줄**로 보이고, 「main 것」을
#    지우면 **지금 굴리는 워크트리 이미지가 날아간다.** 여기서 안 풀면 조용히 틀린다.
# ⚠ 그래서 출처(`[main]`·`[워크트리 …]`)도 **푼 경로**로 판정한다 — 보이는 대로가 아니라
#   실제로 그 바이트가 어디 있는지로.
slots() {
  for d in "$ROOT"/games/*/work/build/*/ \
           "$ROOT"/.claude/worktrees/*/games/*/work/build/*/; do
    [ -d "$d" ] || continue
    (cd -P "$d" 2>/dev/null && pwd) || true
  done | sort -u | while IFS= read -r d; do
    [ -n "$d" ] && [ -d "$d" ] || continue
    # 링크를 푼 뒤에도 **모양이 빌드 칸**이어야 받는다(엉뚱한 데를 가리키는 링크는 버린다)
    case "$d" in
      "$ROOT"/games/*/work/build/*|"$ROOT"/.claude/worktrees/*/games/*/work/build/*) ;;
      *) continue ;;
    esac
    t=${d##*/}
    g=${d%/work/build/*}; g=${g##*/}
    case "$d" in
      "$ROOT"/.claude/worktrees/*) w=${d#"$ROOT"/.claude/worktrees/}; w="$ROOT/.claude/worktrees/${w%%/*}" ;;
      *) w=$ROOT ;;
    esac
    [ -z "$FILTER" ] || case "$g$t" in *"$FILTER"*) ;; *) continue ;; esac
    kb=$(du -sk "$d" 2>/dev/null | cut -f1) || kb=0
    lt=$(live_tag "$w")
    # 브랜치로 본 딱지 — 실패 여부와 **따로** 센다. 섞인 칸의 「실패분 빼고」 줄이 이걸 쓴다
    # (그 줄이야말로 「이 브랜치 것」인지가 중요한 자리다).
    if [ -z "$lt" ]; then bmark=미상   # 🔴 꼬리표를 못 읽었다 — 「안 굴린다」로 단정하지 않는다
    elif [ "$t" = "$lt" ]; then bmark=현재
    else bmark=-
    fi
    # 칸 안을 갈라 잰다 — `*.failed` 와 나머지. `-exec … +` 라 안 걸리면 아예 안 돌고
    # awk 가 0 을 찍는다.
    fkb=$(find "$d" -maxdepth 1 -mindepth 1 -name '*.failed' -exec du -sk {} + 2>/dev/null \
          | awk '{s += $1} END {printf "%d", s + 0}')
    rest=0
    find "$d" -maxdepth 1 -mindepth 1 ! -name '*.failed' -print -quit 2>/dev/null | grep -q . && rest=1
    # 맨 앞은 **정렬용 칸 크기**다(줄을 갈라도 두 줄이 붙어 있게) — 정렬 뒤 `cut` 으로 뗀다.
    if find "$d" -maxdepth 1 -newermt "-$FRESH min" -print -quit 2>/dev/null | grep -q .; then
      # 🔴 누가 지금 굴리고 있다 — **안 가른다**(위 주석). 통째로 하나만 낸다
      printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$kb" "$g" "$t" "$((kb / 1024))" 작업중 slot "$d"
    elif [ "$fkb" -gt 0 ] && [ "$rest" = 1 ]; then
      printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$kb" "$g" "$t" "$((fkb / 1024))" 실패 failed "$d"
      printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$kb" "$g" "$t" "$(((kb - fkb) / 1024))" "$bmark" rest "$d"
    elif [ "$fkb" -gt 0 ]; then
      printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$kb" "$g" "$t" "$((kb / 1024))" 실패 slot "$d"
    else
      printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$kb" "$g" "$t" "$((kb / 1024))" "$bmark" slot "$d"
    fi
  # 칸 크기 내림차순 → 같은 칸끼리 묶고(경로) → 그 안에서 failed 가 rest 보다 먼저.
  # ⚠ 종류를 ASCII(`failed`/`rest`/`slot`)로 두는 건 **이 정렬 때문**이다 — 한글이면
  #   순서가 로케일을 탄다.
  done | sort -t"$TAB" -k1,1nr -k7,7 -k6,6 | cut -f2-
}

# 줄에서 n 번째 칸을 꺼낸다 (1-based) — `게임 꼬리표 MB 표시 종류 경로`.
fld() {
  _fr=$2; _fn=$1
  while [ "$_fn" -gt 1 ]; do _fr=${_fr#*"$TAB"}; _fn=$((_fn - 1)); done
  printf '%s' "${_fr%%"$TAB"*}"
}

# 딱지 설명 — 색 있는 판(목록)과 맨 판(확인·비대화형).
# 🔴 **`case` 를 `$( )` 안에 직접 쓰지 않는다.** macOS `/bin/sh` 는 bash 3.2 인데 명령치환
#    안의 `case` 를 **파싱하지 못한다**(패턴의 `)` 를 닫는 괄호로 읽는다) — 실측 2026-08-26:
#    `syntax error near unexpected token` 를 뱉고 case 문 **원문이 그대로 화면에 찍혔다**.
#    하필 확인 화면의 「⚠ 이 브랜치 것」 경고 자리라, 마지막 안전판이 조용히 죽어 있었다.
#    함수로 빼면 치환 안엔 `$(mark_note …)` 만 남아 3.2 도 문제없이 판다.
mark_note() {
  case "$1" in
    현재)   printf ' \033[33m← 이 브랜치 것\033[0m' ;;
    실패)   printf ' \033[31m← 실패 산출물\033[0m' ;;
    미상)   printf ' \033[2m← 꼬리표 못 읽음\033[0m' ;;
    작업중) printf ' \033[35m← 방금 건드림\033[0m' ;;
  esac
  case "$2" in
    failed) printf ' \033[2m(*.failed 만)\033[0m' ;;
    rest)   printf ' \033[2m(실패분 빼고)\033[0m' ;;
  esac
}

mark_text() {
  case "$1" in
    현재)   printf '⚠ 이 브랜치 것' ;;
    실패)   printf '실패 산출물' ;;
    미상)   printf '⚠ 꼬리표 못 읽음' ;;
    작업중) printf '⚠ 방금 건드림' ;;
  esac
  case "$2" in
    failed) printf ' (*.failed 만)' ;;
    rest)   printf ' (실패분 빼고)' ;;
  esac
}

row_slot() {
  _g=$(fld 1 "$2"); _t=$(fld 2 "$2"); _mb=$(fld 3 "$2")
  _mk=$(fld 4 "$2"); _kd=$(fld 5 "$2"); _p=$(fld 6 "$2")
  _n=$(mark_note "$_mk" "$_kd")
  if [ "$3" = 1 ]; then printf "\033[36m❯ %-10s %-12s %5sMB [%s]\033[0m%s\n" "$_g" "$_t" "$_mb" "$(origin_of "$_p")" "$_n"
  else printf "  \033[2m%-10s\033[0m %-12s \033[2m%5sMB [%s]\033[0m%s\n" "$_g" "$_t" "$_mb" "$(origin_of "$_p")" "$_n"; fi
}

OLDIFS=$IFS; IFS='
'
# shellcheck disable=SC2046
set -- $(slots)
IFS=$OLDIFS
[ $# -gt 0 ] || { echo "빌드 칸이 없다."; exit 0; }

if [ "$STALE" = 1 ] || [ "$FAILED" = 1 ]; then
  # `--stale` 은 **갈래로**(안 굴리는 것 전부), `--failed` 는 **종류로**(실패 산출물만) 고른다.
  # ⚠ `--failed` 는 「현재」 칸 안의 실패분도 집는다 — 그건 갈래와 무관하게 **무효 산출물**이고,
  #   섞인 칸이면 정상 이미지는 다른 줄이라 안 건드린다. 「작업중」은 애초에 안 갈라 두었으니
  #   `실패` 딱지가 붙지 않아 저절로 빠진다.
  PICK=""
  for e in "$@"; do
    _mk=$(fld 4 "$e")
    if [ "$FAILED" = 1 ]; then
      [ "$_mk" = 실패 ] || continue
    else
      case "$_mk" in 현재|미상|작업중) continue ;; esac
    fi
    PICK="$PICK$e
"
  done
  [ -n "$PICK" ] || { echo "── 지울 것 없음"; exit 0; }
else
  # 커서는 **안 굴리는 갈래의 첫 칸**에 놓는다 — 무선택 Enter 가 「현재」를 지우지 않게.
  _i=0
  for e in "$@"; do
    _i=$((_i + 1))
    case "$(fld 4 "$e")" in 현재|미상|작업중) ;; *) SELECT_INDEX=$_i; break ;; esac
  done
  SELECT_RENDER=row_slot
  if PICK=$(select_multi "지울 빌드 칸" "$@"); then
    :
  else
    rc=$?
    if [ "$rc" = 2 ]; then
      echo "⛔ 고를 수가 없다(비대화형) — 필터로 좁히거나 \`--stale --yes\`(안 굴리는 갈래) ·" >&2
      echo "   \`--failed --yes\`(실패 산출물만) 를 쓴다:" >&2
      for e in "$@"; do
        printf '     %-10s %-12s %5sMB [%s] %s\n' \
          "$(fld 1 "$e")" "$(fld 2 "$e")" "$(fld 3 "$e")" \
          "$(origin_of "$(fld 6 "$e")")" "$(mark_text "$(fld 4 "$e")" "$(fld 5 "$e")")" >&2
      done
    fi
    exit 1
  fi
  SELECT_RENDER=; SELECT_INDEX=
fi

MB=$(printf '%s\n' "$PICK" | awk -F'\t' 'NF {s += $3} END {printf "%d", s + 0}')
NK=$(printf '%s\n' "$PICK" | grep -c . || true)
printf '── %s칸 · %sMB\n' "$NK" "$MB"
printf '%s\n' "$PICK" | while IFS="$TAB" read -r g t mb mk kd _p; do
  [ -n "${g:-}" ] || continue
  printf '   %-10s %-12s %5sMB %s\n' "$g" "$t" "$mb" "$(mark_text "$mk" "$kd")"
done

# ⚠ **`confirm_yes` 를 서브셸로 가둔다.** tty 가 없으면 `has_tty` 안의 `: </dev/tty` 가
#   실패하는데, `:` 는 **특수 빌트인**이라 POSIX 셸에선 리다이렉션 실패가 치명적이다 —
#   함수가 1 을 돌려주는 게 아니라 **부른 스크립트가 통째로 죽는다**(실측 rc=2, 아무 말도
#   안 남긴다). 라이브러리는 「열어 봐야 안다」까지만 적어 뒀고 이건 그 다음 함정이다.
if [ "$YES" != 1 ]; then
  ( confirm_yes "정말 지울까? [y/N] " ) || { echo "취소 — 대화형이 아니면 \`--yes\`."; exit 0; }
fi

printf '%s\n' "$PICK" | while IFS="$TAB" read -r _g _t _mb _mk kd p; do
  [ -n "${p:-}" ] || continue
  # 🔴 마지막 안전판 — 경로 모양이 빌드 칸이 아니면 손대지 않는다.
  case "$p" in
    "$ROOT"/games/*/work/build/*|"$ROOT"/.claude/worktrees/*/games/*/work/build/*) ;;
    *) echo "   ⚠ 모양이 빌드 칸이 아니다 — 건너뛴다: $p" >&2; continue ;;
  esac
  if [ "$kd" = slot ]; then
    rm -rf "$p"
    echo "   지움 $p"
  else
    # 칸 안에서 골라 지운다 — **한 단계 아래만**(`-maxdepth 1`). 칸 자체는 안 건드린다.
    if [ "$kd" = failed ]; then
      find "$p" -maxdepth 1 -mindepth 1 -name '*.failed' -exec rm -rf {} + 2>/dev/null || true
      echo "   지움 $p/*.failed"
    else
      find "$p" -maxdepth 1 -mindepth 1 ! -name '*.failed' -exec rm -rf {} + 2>/dev/null || true
      echo "   지움 $p (실패분 빼고)"
    fi
    rmdir "$p" 2>/dev/null || true   # 두 줄을 다 골랐으면 빈 칸이 남는다 — 그때만 걷힌다
  fi
done
echo "✅ ${NK}칸 정리 — ${MB}MB"
