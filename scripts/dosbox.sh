#!/bin/sh
# 정발(DOS) 영웅전설 1~4를 DOSBox-X로 실행한다 — 정발 대조·패치 검증용.
#
#   scripts/dosbox.sh ed1|ed2|ed3|ed4 [옵션...] [dosbox 추가인자...]
#
#     --app      앱 번들(open -a)로 실행 — macOS에서 키 입력이 안 먹을 때(아래 참조)
#     --scancodes  usescancodes=true 로 실행. **방향키가 안 먹을 때** 시도한다(수정자키는
#                되는데 방향키만 죽는 게 전형적 증상). ⚠ 저수준 키보드 경로라 입력 모니터링
#                권한이 필요하므로 **--app 과 같이** 써야 의미가 있다
#     --mapper   매퍼 편집기로 시작(-startmapper). 단축키를 바꿔 저장하면 **전체** 매퍼
#                파일이 .local/dosbox/mapper.map 로 생성된다(부분 매퍼는 키보드를 죽인다)
#     --debug    DOSBox-X 디버거(-break-start). ⚠ 디버거 UI는 **실행한 터미널**에 뜨므로
#                --app 과 같이 못 쓰고, -log-con 도 같은 터미널을 두고 부딪혀 뺀다
#     --refresh  사본을 버리고 원본에서 다시 만든다(세이브·설정·패치 전부 초기화)
#     --setup    게임 대신 SETUP.EXE 실행 — 사운드/음악 장치 재설정(GAME.INI에 기록)
#     --cd P     P를 CD-ROM 드라이브 D:로 마운트(디렉터리면 `mount -t cdrom`, 이미지면
#                `imgmount`). 미지정이면 배포본 동봉 이미지를 **자동으로 찾는다**
#                (`originals/kr/<G>/CD/` 와 `originals/kr/<G>/DosBox/CD/` 둘 다 본다).
#     --no-sync  세이브 동기화를 끈다(아래 참조). 기본은 켜짐.
#
# ── 사본 방식 ────────────────────────────────────────────────────────────────
# 원본 `originals/kr/dos-ed{1,2,3,4}`(gitignore, 소장본)는 **읽기만 한다.** 게임 본체를
# `.local/dosbox/<game>/` 로 복사해 그 사본을 실행하므로, 세이브·설정은 물론 **DOS 쪽
# 패치 파일을 덮어써 가며 검증**할 수 있다(ed2-mantra-restore와 같은 방식).
#
# ⚠ **CD 이미지는 복사하지 않는다** — 용량의 95%가 CD인데(ED3: 482M 중 471M) 읽기
# 전용이라 사본이 필요 없다. 원본에서 직접 마운트한다. 덕분에 4개 전부 떠도 사본은
# ~69MB(ED1 15M + ED2 33M + ED3 11M + ED4 10M)로 끝난다.
#
# 로그: .local/dosbox/<game>.log (매 실행 초기화) · 스크린샷: .local/dosbox/capture
#
# ── 세이브 동기화 (기본 켜짐, --no-sync 로 끈다) ──────────────────────────────
# 작업 머신은 원격(dev)인데 **DOSBox 는 GUI 라 맥에서만 뜬다.** 그래서 세이브가 맥에
# 고립되는데, 정본을 늘 켜져 있는 dev 에 두려는 것이다. 방향은 이렇다 —
#
#   실행 전: dev 의 세이브를 사본으로 당긴다 (없으면 조용히 넘어간다)
#   DOSBox 실행 (로컬 디스크 속도)
#   종료 후: 사본의 세이브를 dev 로 올린다
#
# ⚠ **게임 파일까지 원격에 두면 안 된다.** 맥↔dev 는 Tailscale 릴레이 경유라 실측
# **RTT 73ms · 2.1MB/s** 다(2026-08-10). DOS 게임은 작은 동기 읽기를 수없이 하고 CD 는
# `imgmount` 랜덤 시크라, 마운트해서 돌리면 못 쓸 정도로 느려진다. 반면 **세이브는
# ed2 기준 324KB** — 이것만 옮기면 0.2초다. 그래서 무거운 쪽(게임)을 로컬에 두고
# 가벼운 쪽(세이브)만 오간다.
#
# **기전·정본 자리·안전장치는 `scripts/sync-saves.sh` 가 정본이다**(기종 무관 공용 —
# PS1 메모리카드도 같은 걸 쓴다). 여기서는 무엇을 어디로 보낼지만 정한다:
# leaf 는 `originals/` 규약을 그대로 쓴 `dos-ed1`~`dos-ed4`, 대상은 게임별 `$SAVES` 다.
#
# dev 에 못 붙으면 **경고만 하고 그냥 로컬로 실행한다** — 오프라인에서도 플레이는 된다.
# 환경변수: DEV_HOST · DEV_SAVES(sync-saves.sh 참조) · DOSBOX_SYNC=0 으로 기본 끄기
#
# ── 게임별 실행 명령 ─────────────────────────────────────────────────────────
# 두기게임 배포본의 `DosBox/Settings.conf`(UTF-16LE의 `Autoexec=`/`CD=`)와 각 배치 파일에서
# 확인한 값이다:
#   ed1  main.exe   CD 없음(CD=0)          DataDir 설정 없음
#   ed2  game.bat   CD/ED2.cue             DataDir = F:\ed2\ed2 → 마운트 루트로 재작성
#                   (= gkey.exe -s opening.exe → ed2main.exe. **오프닝이 CD에서 재생**되므로
#                    ed2main만 직접 부르면 오프닝이 통째로 빠진다 — 유저 지적 2026-07-29)
#   ed3  play.bat   CD/MANTRAINC_YJ3.ISO   DataDir = E:
#   ed4  game.bat   CD/ED4.iso             DataDir = F:
# ⚠ ed3/ed4는 **반드시 배치 파일**을 타야 한다. `driver.exe ed?.exe`(=NOSOUND.BAT)만 돌리면
#   "No driver loaded / Sound Driver Installation Failed"로 죽는다 — 배치가 먼저 올리는
#   사운드 TSR `soundrv.com`이 없으면 드라이버 설치 자체가 실패한다(유저 실측 2026-07-29).
#   그리고 **BGM이 CD 오디오**라 CD를 안 물리면 "Music System Installation Failed"로 또 죽는다.
#
# ── macOS 키보드 함정 ────────────────────────────────────────────────────────
# ⚠ **입력 소스가 한글이면 방향키가 안 먹는다**(IME 가 가로챈다). Shift·메뉴는 멀쩡해서
# DOSBox 설정 문제로 오해하기 쉽다 — 영문(ABC)으로 바꾸고 플레이한다. 실행 시 경고한다.
# SDL1에서 `usescancodes=true`면 저수준 키보드 경로를 타는데 입력 모니터링 권한이 필요하다.
# 셸에서 앱 번들 **내부 바이너리**를 직접 띄우면 그 권한이 안 붙어 키보드만 죽는다(마우스는
# 멀쩡). 템플릿에서 껐고, 그래도 안 되면 `--app`으로 앱 번들 채널을 쓴다.
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
DOSBOX=${DOSBOX:-/Applications/dosbox-x.app/Contents/MacOS/dosbox-x}  # 환경변수로 교체 가능
APPDIR=${DOSBOX_APP:-/Applications/dosbox-x.app}

usage() {
  echo "사용법: $0 ed1|ed2|ed3|ed4 [--app|--debug] [--refresh] [--setup] [--cd P] [dosbox 인자...]" >&2
  exit 2
}

GAME=$1
[ -n "$GAME" ] || usage
shift

# SRC=원본 폴더 · DRIVE=마운트 드라이브 · CMD=실행 명령 · MARKER=사본 완성 판정 파일
# SBTYPE/SBIRQ: 게임 CNF(ed1·ed2)와 동봉 드라이버(ed3=sbpro.com, ed4=SB16.COM) 기준.
# ⚠ ed1/ed2는 CNF가 **IRQ 7**을 쓴다 — 5로 두면 소리가 안 난다.
# SAVES=동기화할 세이브 경로(사본 기준 상대). 원본과 사본을 대조해 확인했다(2026-08-10) —
#   ed1 만 루트에 흩어져 있고(`SAVEDATA.000`~`.019` + `SAVEDATA.DAT`) 나머지는 `SAVE/` 다.
#   ⚠ 글로브라 따옴표 없이 전개해야 한다(`push_saves` 참조).
case "$GAME" in
  ed1) SRC=dos-ed1; DRIVE=C; CMD="main.exe"; MARKER=MAIN.EXE;    SBTYPE=sbpro2; SBIRQ=7; WANT_CD= ; SAVES="SAVEDATA.*" ;;
  ed2) SRC=dos-ed2; DRIVE=F; CMD="game.bat"; MARKER=ED2MAIN.EXE; SBTYPE=sbpro2; SBIRQ=7; WANT_CD=1; SAVES="SAVE" ;;
  ed3) SRC=dos-ed3; DRIVE=E; CMD="play.bat"; MARKER=ED3.EXE;     SBTYPE=sbpro2; SBIRQ=5; WANT_CD=1; SAVES="SAVE" ;;
  ed4) SRC=dos-ed4; DRIVE=F; CMD="game.bat"; MARKER=ED4.EXE;     SBTYPE=sb16;   SBIRQ=5; WANT_CD=1; SAVES="SAVE" ;;
  *) usage ;;
esac

APP=0; DEBUG=0; REFRESH=0; SETUP=0; SCAN=0; MAPPER=0; CD=""; ARGS=""
SYNC=${DOSBOX_SYNC:-1}
DEV_HOST=${DEV_HOST:-dev}                    # pull-build.sh 와 같은 관례
DEV_SAVES=${DEV_SAVES:-save}                 # dev 홈 기준 상대 — 레포 밖이다(헤더 참조)
while [ $# -gt 0 ]; do
  case "$1" in
    --app) APP=1 ;;
    --debug) DEBUG=1 ;;
    --refresh) REFRESH=1 ;;
    --setup) SETUP=1 ;;
    --scancodes) SCAN=1 ;;
    --mapper) MAPPER=1 ;;
    --no-sync) SYNC=0 ;;
    --cd) shift; CD=$1; [ -n "$CD" ] || { echo "--cd 경로 필요" >&2; exit 2; } ;;
    *) ARGS="$ARGS $1" ;;
  esac
  shift
done
[ "$SETUP" = 1 ] && CMD="setup.exe"
[ "$APP" = 1 ] && [ "$DEBUG" = 1 ] && {
  echo "--app 과 --debug 는 같이 못 쓴다(디버거 UI는 터미널에 뜬다)" >&2; exit 2; }

ORIG="$REPO/originals/kr/$SRC"
[ -d "$ORIG" ] || { echo "원본 없음: originals/kr/$SRC (소장본 필요 — originals/README.md)" >&2; exit 1; }

BOX="$REPO/.local/dosbox"
COPY="$BOX/$GAME"          # 쓰기 가능 사본 (세이브·설정·DOS 패치)
mkdir -p "$BOX/capture"

[ "$REFRESH" = 1 ] && rm -rf "$COPY"

# ── 사본 만들기 (CD·런처 폴더 제외) ─────────────────────────────────────────
if [ ! -f "$COPY/$MARKER" ]; then
  echo "사본 생성: originals/kr/$SRC → .local/dosbox/$GAME (CD 제외)"
  rm -rf "$COPY"; mkdir -p "$COPY"
  for item in "$ORIG"/*; do
    [ -e "$item" ] || continue
    case "$(basename "$item")" in
      CD|cd|DosBox|dosbox|DOSBOX) continue ;;   # CD 이미지·두기 런처는 원본에서 직접 쓴다
    esac
    cp -R "$item" "$COPY/"
  done
  find "$COPY" -name '.DS_Store' -delete
  find "$COPY" -iname '*.SWP' -delete     # ED2.SWP 등 스왑 잔재(원본 실행 흔적)
  chmod -R u+w "$COPY"                    # 원본이 읽기전용이면 세이브가 안 된다

  # 원본 CNF의 DataDir은 설치 시점 경로(F:\ed2\ed2 등)라 이 환경에 없다 — 마운트 루트로
  # 재작성한다(원본 디렉터리 구조를 재현하는 것보다 단순하고, 사본이라 맘껏 고쳐도 된다).
  for cnf in "$COPY"/*.CNF "$COPY"/*.cnf; do
    [ -f "$cnf" ] || continue
    grep -qi '^ *DataDir' "$cnf" || continue
    sed -E "s|^ *DataDir.*|DataDir = ${DRIVE}:|I" "$cnf" > "$cnf.new" && mv "$cnf.new" "$cnf"
    echo "  $(basename "$cnf"): DataDir → ${DRIVE}:"
  done
fi

# ── CD 마운트 줄 조립 ───────────────────────────────────────────────────────
# ed2~4는 BGM이 CD 오디오라 드라이브가 없으면 음악 초기화가 실패한다.
# .local/dosbox 기준 **상대경로**로 적어 생성 conf에 절대경로가 안 남게 한다.
MOUNTCD=""
if [ -n "$CD" ]; then
  case "$CD" in
    *.cue|*.CUE|*.iso|*.ISO|*.chd|*.CHD) MOUNTCD="imgmount D \"$CD\" -t iso" ;;
    *) MOUNTCD="mount D \"$CD\" -t cdrom" ;;
  esac
elif [ -n "$WANT_CD" ]; then
  for sub in CD DosBox/CD; do          # .cue 우선(오디오 트랙 포함)
    for ext in cue CUE iso ISO; do
      for img in "$ORIG/$sub"/*."$ext"; do
        [ -f "$img" ] || continue
        MOUNTCD="imgmount D \"../../originals/kr/$SRC/$sub/$(basename "$img")\" -t iso"
        break 3
      done
    done
  done
  [ -n "$MOUNTCD" ] || echo "⚠ CD 이미지 없음: originals/kr/$SRC/{CD,DosBox/CD}/*.{cue,iso} — BGM 초기화 실패 가능" >&2
fi

# ── conf 생성 (템플릿 → .local/dosbox/<game>.conf, 생성물은 gitignore) ────────
sed -e "s|@GAME@|$GAME|g" -e "s|@DRIVE@|$DRIVE|g" -e "s|@CMD@|$CMD|g" \
    -e "s|@MOUNTCD@|$MOUNTCD|g" -e "s|@SBTYPE@|$SBTYPE|g" -e "s|@SBIRQ@|$SBIRQ|g" \
    "$HERE/dosbox/game.conf.tmpl" > "$BOX/$GAME.conf"
# ⚠ 매퍼 파일은 기본 바인딩을 **덮는 게 아니라 통째로 대체**한다 — 한 줄짜리를 깔면
# 나머지 키가 전부 언바인드돼 **키보드가 죽는다**(2026-07-31 실측). 게임 안 매퍼 UI
# (Ctrl+F1)로 저장한 **전체 파일**만 유효하다. 손으로 만든 부분 매퍼는 치운다.
if [ -f "$BOX/mapper.map" ] && [ "$(wc -l < "$BOX/mapper.map")" -lt 20 ]; then
  echo "⚠ 부분 매퍼 감지 — 키보드가 죽으므로 제거한다: .local/dosbox/mapper.map" >&2
  rm -f "$BOX/mapper.map"
fi
rm -f "$BOX/$GAME.log"

# ── 한글 입력기 경고 ────────────────────────────────────────────────────────
# ⚠ macOS 입력 소스가 **한글이면 방향키가 DOSBox 에 안 들어온다**(IME 가 먹는다).
# 조용히 방향키만 죽고 Shift·메뉴는 멀쩡해서 DOSBox 설정 문제로 오해하기 쉽다
# (2026-07-31 유저가 규명 — usescancodes 도 --app 도 원인이 아니었다).
if defaults read ~/Library/Preferences/com.apple.HIToolbox.plist AppleSelectedInputSources 2>/dev/null \
   | grep -qi 'inputmethod\.Korean'; then
  echo "⚠ 입력 소스가 한글이다 — DOSBox 에서 방향키가 안 먹는다. 영문(ABC)으로 바꾸고 플레이할 것." >&2
fi

# ── 세이브 동기화 ───────────────────────────────────────────────────────────
# 기전은 `scripts/sync-saves.sh` 에 있다(기종 무관 공용 — PS1 메모리카드도 같은 걸 쓴다).
# 여기서는 **무엇을 어디로** 만 정한다. leaf 는 originals 규약대로 `$SRC`(=dos-ed2)다.
SYNCSH="$HERE/sync-saves.sh"

# ⚠ $SAVES 는 글로브(ed1 의 `SAVEDATA.*`)다. **사본 안에서 먼저 편 뒤** 실제 파일명으로
#   넘긴다 — sync-saves.sh 는 패턴이 아니라 전개된 이름을 받는 계약이다(그쪽 헤더 참조).
push_saves() { ( cd "$COPY" && set -- $SAVES && sh "$SYNCSH" push "$SRC" "$COPY" "$@" ) || true; }

if [ "$SYNC" = 1 ]; then
  if sh "$SYNCSH" probe; then
    sh "$SYNCSH" pull "$SRC" "$COPY"
  else
    echo "⚠ $DEV_HOST 에 못 붙는다 — 로컬 세이브로 진행한다(종료 후에도 안 올라간다)" >&2
    SYNC=0
  fi
fi

# 상대경로(logfile·captures·mapperfile·mount)가 해석되도록 기준 디렉터리로 이동한다.
cd "$BOX"
COMMON="-conf $GAME.conf -fastlaunch"
[ "$SCAN" = 1 ]   && COMMON="$COMMON -set \"sdl usescancodes=true\""
[ "$MAPPER" = 1 ] && COMMON="$COMMON -startmapper"

have_dosbox() {
  [ -x "$DOSBOX" ] || { echo "dosbox-x 없음: $DOSBOX (brew install --cask dosbox-x)" >&2; exit 1; }
}
# ⚠ `open -a` 는 **cwd 를 물려주지 않는다** — 위에서 cd 해도 앱은 제 작업디렉터리에서 뜬다.
# 그래서 상대경로 `-conf ed1.conf` 를 못 찾아 마운트 없이 맨 프롬프트만 나왔다(2026-07-31).
# conf 는 절대경로로 주고, conf 안의 상대경로(mount·logfile·captures)는 -defaultdir 로 맞춘다.
# (절대경로는 실행 시 계산한 값이라 커밋되는 파일엔 안 남는다.)
APPOPT=""
[ "$SCAN" = 1 ]   && APPOPT="$APPOPT -set \"sdl usescancodes=true\""
[ "$MAPPER" = 1 ] && APPOPT="$APPOPT -startmapper"

# -log-con: DOS 콘솔 출력을 로그로 남긴다. 그래픽 모드라 화면에선 안 보이는 엔진 진단
# 메시지("Where : %s" / "What : %s" 등)를 잡기 위한 것.
# ⚠ `--app` + 동기화일 때만 `open -W` 를 쓴다 — `-W` 는 앱이 끝날 때까지 **블록**하므로
#   종료 훅을 걸 수 있다. 동기화가 없으면 예전처럼 바로 반환시켜 터미널을 놓아 준다.
run_dosbox() {
  if [ "$DEBUG" = 1 ]; then
    # -log-con 은 뺀다 — 디버거 커서스 UI와 같은 터미널을 두고 부딪힌다.
    have_dosbox; "$DOSBOX" $COMMON -break-start $ARGS
  elif [ "$APP" = 1 ]; then
    open ${1:+-W} -a "$APPDIR" --args -conf "$BOX/$GAME.conf" -defaultdir "$BOX" \
         -fastlaunch -log-con $APPOPT $ARGS
  else
    have_dosbox; "$DOSBOX" $COMMON -log-con $ARGS
  fi
}

# 동기화가 꺼져 있으면 예전 그대로 exec 로 넘긴다 — 프로세스를 하나 아끼고 신호도 그대로 간다.
if [ "$SYNC" != 1 ]; then
  if [ "$DEBUG" = 1 ]; then have_dosbox; exec "$DOSBOX" $COMMON -break-start $ARGS; fi
  if [ "$APP" = 1 ]; then
    exec open -a "$APPDIR" --args -conf "$BOX/$GAME.conf" -defaultdir "$BOX" \
         -fastlaunch -log-con $APPOPT $ARGS
  fi
  have_dosbox; exec "$DOSBOX" $COMMON -log-con $ARGS
fi

# ⚠ Ctrl+C 로 끊거나 DOSBox 가 비정상 종료해도 세이브는 올려야 한다 — 진행분을 잃는 게
#   이 흐름에서 제일 나쁜 결과다. trap 으로 받고, 정상 종료 경로와 중복 실행되지 않게 건다.
PUSHED=0
finish() { [ "$PUSHED" = 1 ] && return 0; PUSHED=1; push_saves; }
trap 'finish; exit 130' INT
trap 'finish; exit 143' TERM

RC=0
run_dosbox wait || RC=$?     # ⚠ set -e 아래라 실패를 여기서 받아야 종료 훅이 산다
finish
exit $RC
