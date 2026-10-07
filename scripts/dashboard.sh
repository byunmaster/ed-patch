#!/bin/sh
# 전 게임 트리의 상태를 한 화면으로 — 관리자(브릿지) 세션의 재료.
#
#   sh scripts/dashboard.sh              # 워크트리 전부
#   sh scripts/dashboard.sh pce ss       # 걸러서 (부분 일치, 여럿 가능)
#   sh scripts/dashboard.sh --brief      # 게임마다 한 줄(표)만
#
# ── 왜 스크립트인가 (유저 확정 2026-09-06) ─────────────────────────────────────
# 세션이 여덟을 넘어 사람이 탭을 넘나들며 상태를 모을 수 없게 됐다. 관리자 세션 하나가
# main 에 서서 **전 작업을 꿰뚫고 · 유저 지시를 전달하고 · main(공용·emucap·스킬 갱신)을
# 관리한다.** 워크트리는 만지지 않는다 — 만지면 아홉째 워커가 된다.
# 그 관리자가 사실을 매번 LLM 으로 새로 짜면 회차마다 다르게 나오므로, **사실 수집은
# 여기서 결정적으로** 뽑고 관리자는 그 위에서 해석·전달만 한다.
#
# ⚠ **「뒤 N」이 0 이 아니면 그 세션에 rebase 를 요청한다** — main 에 공용이 쌓였다는 뜻이다.
#   되머지가 아니라 `git rebase main`(루트 CLAUDE.md 「Git 정책」). 워킹트리가 더티면 그 세션이
#   먼저 커밋해야 하니, 「더티」 열을 같이 보고 보낸다.
#
# ⚠ **읽기만 한다.** 워크트리를 고치지 않고, 빌드도 안 돌린다. 워커 세션의 토큰도 안 쓴다 —
#   재료는 전부 이미 있는 것이다: git(브랜치·더티·마지막 커밋·main 대비) + 상태 문서
#   (`games/<게임>/docs/*status*.md`, 「세션 시작 시」 2번이 이미 그 문서를 강제한다).
#
# ⚠ 상태 문서의 절 이름은 게임마다 다르다(실측 2026-09-06: 「한 줄 요약」은 여섯, 「남은 일」·
#   「다음에 할 일」·「유저 손이 필요한 것」·「열려 있는 물음」이 섞여 있다). 정규식으로 느슨하게
#   잡고 **없으면 없다고 찍는다** — 조용히 빈칸으로 두면 「다 잘 되는구나」로 읽힌다.
#   앞으로 워커가 유저 판정을 기다릴 땐 **`## 유저 판정 대기`** 절에 적는다. 그 절만 정확히 잡는다.
#
# ⚠ 세션(busy/idle)은 셸에서 안 보인다 — 관리자가 ListAgents 로 겹쳐 본다. 세션 이름 =
#   워크트리 이름이 규약이라(유저 2026-09-06) 이름 하나로 짝이 맞는다.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WT_DIR="$ROOT/.claude/worktrees"
BRIEF=0
SUMMARY_LINES=${DASHBOARD_LINES:-12}     # 절 하나를 최대 몇 줄까지 보이나

FILTERS=""
for a in "$@"; do
  case "$a" in
    --brief) BRIEF=1 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) FILTERS="$FILTERS $a" ;;
  esac
done

# 필터: 인자가 없으면 전부, 있으면 부분 일치 하나라도 걸리면 통과.
want() {
  [ -z "$FILTERS" ] && return 0
  for f in $FILTERS; do
    case "$1" in *"$f"*) return 0 ;; esac
  done
  return 1
}

# 「N분 전」 — git 의 %cr 를 그대로 쓴다(사람이 읽는 값이라 정확도는 필요 없다).
# 절 뽑기: 제목이 정규식에 걸리는 절을 찾아 **그 절의 본문만**(다음 제목 전까지) 낸다.
# ⚠ 같은 깊이 이하의 제목이 나오면 끊는다 — `## 남은 일` 아래 `### 1.` 소절은 포함한다.
section() { # $1=file $2=제목 정규식(ERE)
  awk -v re="$2" -v max="$SUMMARY_LINES" '
    /^#{1,6} / {
      if (on) { exit }
      if ($0 ~ re) { on = 1; depth = length($1); print "  ▸ " substr($0, depth + 2); next }
    }
    on {
      if ($0 ~ /^#{1,6} / && length($1) <= depth) exit
      if (n < max) { if ($0 != "") print "    " $0; n++ }
      else if (n == max) { print "    …"; n++ }
    }' "$1"
}

# 단계: 상태 문서 첫 100줄에서 `단계: P2/7` 꼴을 찾는다(docs/ed1-phases.md). 없으면 `-`.
phase() { # $1=worktree $2=game
  for doc in "$1"/games/"$2"/docs/*status*.md; do
    [ -f "$doc" ] || continue
    v=$(head -100 "$doc" | grep -oE '단계: *P[0-9]+/[0-9]+' | head -1 | sed 's/단계: *//')
    [ -n "$v" ] && { echo "$v"; return; }
  done
  echo -
}

# 상황판 — 워커가 일을 잡을 때·커밋할 때·막힐 때 덮어쓰는 몇 줄(마스터 10-07 「관리자는 보고받기보다
# 늘 알고 있어야」). 커밋 전의 진행은 git·상태 문서에 아직 없으니 이게 그 틈을 메운다. 머신 전용이라 .local.
BOARD="$ROOT/.local/work/board"
board_age() { # $1=file → 「N분 전」
  now=$(date +%s); m=$(stat -c %Y "$1" 2>/dev/null || stat -f %m "$1")
  d=$(( (now - m) / 60 ))
  if [ "$d" -lt 60 ]; then echo "${d}분 전"; else echo "$((d / 60))시간 전"; fi
}
board_now() { # $1=game → 「지금:」 줄 한 줄
  f="$BOARD/$1.md"
  [ -f "$f" ] || { echo "(상황판 없음)"; return; }
  v=$(grep -m1 '^지금:' "$f" | sed 's/^지금: *//')
  echo "${v:-?} ($(board_age "$f"))"
}

[ "$BRIEF" -eq 1 ] && printf '%-12s %-16s %-5s %5s %5s %5s  %s\n' 게임 브랜치 단계 앞 뒤 더티 지금

for wt in "$WT_DIR"/*/; do
  g=$(basename "$wt")
  want "$g" || continue
  [ -d "$wt/.git" ] || [ -f "$wt/.git" ] || continue

  br=$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')
  ahead=$(git -C "$wt" rev-list --count main.."$br" 2>/dev/null || echo '?')
  behind=$(git -C "$wt" rev-list --count "$br"..main 2>/dev/null || echo '?')
  dirty=$(git -C "$wt" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  last=$(git -C "$wt" log -1 --format='%cr · %s' 2>/dev/null || echo '?')
  ph=$(phase "$wt" "$g")

  if [ "$BRIEF" -eq 1 ]; then
    printf '%-12s %-16s %-5s %5s %5s %5s  %s\n' "$g" "${br#game/}" "$ph" "$ahead" "$behind" "$dirty" "$(board_now "$g")"
    continue
  fi

  echo "━━ $g  [$br]  단계 $ph  main+$ahead  뒤 $behind  더티 $dirty"
  echo "  마지막 커밋: $last"
  if [ -f "$BOARD/$g.md" ]; then
    echo "  📌 상황판 ($(board_age "$BOARD/$g.md"))"
    sed 's/^/    /' "$BOARD/$g.md" | head -8
  else
    echo "  ⚠ 상황판 없음 (.local/work/board/$g.md)"
  fi
  # 뒤처짐·더티는 관리자가 짚을 징후라 줄을 따로 뺀다.
  [ "$behind" != "0" ] && [ "$behind" != "?" ] && echo "  ⚠ main 이 $behind 앞서 있다 — rebase 대상"
  [ "$dirty" != "0" ] && git -C "$wt" status --porcelain | sed 's/^/    /' | head -8

  found=0
  for doc in "$wt"/games/"$g"/docs/*status*.md; do
    [ -f "$doc" ] || continue
    found=1
    echo "  📄 ${doc#"$wt"/}"
    section "$doc" '^#+ (한 줄 요약|지금 어디까지|지금 상태)'
    section "$doc" '^#+ 유저 판정 대기'
    section "$doc" '^#+ (유저 손이 필요한 것|열려 있는 물음)'
    section "$doc" '^#+ (남은 일|다음에 할 일)'
  done
  [ "$found" -eq 0 ] && echo "  ⚠ 상태 문서 없음 (games/$g/docs/*status*.md)"
  echo
done
