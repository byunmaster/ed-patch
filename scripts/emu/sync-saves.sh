#!/bin/sh
# 세이브 정본을 작업 머신(dev)에 두고 실행 머신과 오간다 — 기종 무관 공용 기전.
#
#   sh scripts/emu/sync-saves.sh probe
#   sh scripts/emu/sync-saves.sh pull <leaf> <로컬디렉터리>
#   sh scripts/emu/sync-saves.sh push <leaf> <로컬디렉터리> <파일명>...
#
#     leaf      정본 폴더명. **`originals/` 규약(`<플랫폼>-ed<N>`)을 그대로 쓴다** —
#               `dos-ed2` · `ps1-ed1+2` · `win-ed3`. 세이브 폴더가 원본 폴더와 1:1 로 읽힌다.
#     로컬디렉터리  세이브가 들어 있는 자리. 레포 밖이어도 된다.
#     파일명     그 디렉터리 기준 상대경로. **글로브는 호출자가 미리 편다.**
#
# ⚠ 패턴이 아니라 **전개된 이름**을 받는 이유 — DuckStation 메모리카드는 파일명에 공백과
#   `&` 가 들어간다(`Legend of Heroes I & II, The - ...`). 패턴 문자열을 변수에 담아
#   `$pat` 로 펴면 셸이 **글로브보다 먼저 공백으로 쪼개** 이름이 산산조각 난다. 반면 호출자가
#   글로브를 리터럴로 쓰면 전개 결과는 단어분리를 안 타므로 공백이 그대로 살아 있다.
#   그래서 여기서는 `"$@"` 로만 받는다(`$*` 로 두면 같은 자리에서 깨진다).
#
# ── 왜 이런 모양인가 ─────────────────────────────────────────────────────────
# 에뮬레이터·DOSBox 는 **GUI 라 맥에서만** 뜨는데 작업 머신은 원격(dev)이다. 그래서 세이브가
# 실행한 머신에 고립된다. 게임 파일째 원격에 두고 마운트해 돌리는 건 실측으로 불가였다 —
# 맥↔dev 는 Tailscale 릴레이 경유라 **RTT 73ms · 2.1MB/s**(2026-08-10). 반면 세이브는
# **수백 KB** 다. 그래서 무거운 쪽(게임·롬)은 실행 머신 로컬에 두고 **가벼운 쪽만 오간다.**
#
# 정본 자리는 **레포 밖**(`DEV_SAVES`, 기본 `~/save/<leaf>`)이다. `.local/` 은 규약상
# "지웠다 다시 만들어도 되는 머신 전용물"이라 유일본을 두면 안 되고, `originals/` 는
# 읽기 전용이다. 세이브는 재생성이 불가능하고 커밋도 못 하니 어느 칸에도 안 맞는다.
#
# 안전장치 둘:
#   · pull 은 `rsync -u` — **로컬이 더 새로우면 건너뛴다**(안 올린 진행분을 원격 낡은 값이
#     덮는 걸 막는다). 지난 세션을 못 올린 채 다시 켰을 때가 그 상황이다.
#   · push 는 직전 세대를 `<leaf>.bak` 으로 남긴다(수백 KB 라 부담이 없다).
#
# ⚠ **이건 동기화지 병합이 아니다.** 두 머신에서 **각각 플레이**하면 나중에 올린 쪽이
#   이긴다(`.bak` 으로 한 세대만 되돌릴 수 있다). DOS 는 맥에서만 도니 안전하지만,
#   PS1 처럼 dev(mednafen/emucap)와 맥(DuckStation) **양쪽에서 도는 기종은 실제로 갈릴 수
#   있다** — 그런 기종을 붙일 땐 "지금 어느 쪽이 정본인가"를 사람이 정하는 절차가 필요하다.
#
# 환경변수: DEV_HOST(기본 dev · pull-build.sh 와 같은 관례) · DEV_SAVES(기본 save)
set -e

DEV_HOST=${DEV_HOST:-dev}
DEV_SAVES=${DEV_SAVES:-save}      # dev 홈 기준 상대 — 레포 밖이다
SSHOPT="-o ConnectTimeout=5 -o BatchMode=yes"

ACT=$1
[ -n "$ACT" ] || { echo "사용법: $0 probe|pull|push <leaf> <디렉터리> [패턴...]" >&2; exit 2; }
shift

# dev 에 붙는지만 본다. 못 붙어도 호출자가 **로컬로 계속 진행**할 수 있게 코드로만 알린다.
if [ "$ACT" = probe ]; then
  ssh $SSHOPT "$DEV_HOST" true 2>/dev/null || exit 1
  exit 0
fi

LEAF=$1; DIR=$2
[ -n "$LEAF" ] && [ -n "$DIR" ] || { echo "leaf 와 디렉터리가 필요하다" >&2; exit 2; }
shift 2
REMOTE="$DEV_SAVES/$LEAF"
SHORT=$(printf '%s' "$DIR" | sed "s|^$HOME|~|")   # 로그가 길어지지 않게 홈을 접는다

case "$ACT" in
  pull)
    mkdir -p "$DIR"
    # 원격에 아직 정본이 없으면 rsync 가 23 으로 죽는데 그건 **정상 상황**이라 삼킨다.
    if rsync -a -u -e "ssh $SSHOPT" "$DEV_HOST:$REMOTE/" "$DIR/" 2>/dev/null; then
      echo "세이브 당김: $DEV_HOST:$REMOTE → $SHORT"
    else
      echo "세이브 없음(원격) — 그냥 진행한다"
    fi
    ;;

  push)
    [ $# -gt 0 ] || { echo "push 에는 올릴 파일명이 필요하다" >&2; exit 2; }
    [ -d "$DIR" ] || { echo "⚠ 로컬 디렉터리 없음: $DIR" >&2; exit 1; }
    # 글로브가 아무것도 못 맞으면 셸이 **패턴 문자열을 그대로** 남긴다 — 그걸 올리려다
    # 실패하는 대신 여기서 조용히 끝낸다(세이브를 한 번도 안 만든 게임이 이 경우다).
    ( cd "$DIR" && for f in "$@"; do [ -e "$f" ] && exit 0; done; exit 1 ) \
      || { echo "올릴 세이브 없음 — 넘어간다"; exit 0; }
    # 덮어쓰기 전에 한 세대를 남긴다 — 되돌릴 길이 하나는 있어야 한다.
    ssh $SSHOPT "$DEV_HOST" \
      "mkdir -p '$REMOTE'; rm -rf '$REMOTE.bak'; cp -a '$REMOTE' '$REMOTE.bak' 2>/dev/null || true" \
      2>/dev/null || { echo "⚠ $DEV_HOST 에 못 붙어 세이브를 못 올렸다 — 로컬에는 남아 있다" >&2; exit 1; }
    ( cd "$DIR" && rsync -a -e "ssh $SSHOPT" "$@" "$DEV_HOST:$REMOTE/" 2>/dev/null ) \
      && echo "세이브 올림: $SHORT → $DEV_HOST:$REMOTE" \
      || { echo "⚠ 세이브 업로드 실패 — 로컬에는 남아 있다" >&2; exit 1; }
    ;;

  *) echo "모르는 동작: $ACT (probe|pull|push)" >&2; exit 2 ;;
esac
