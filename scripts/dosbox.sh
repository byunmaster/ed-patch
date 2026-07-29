#!/bin/sh
# 정발(DOS) 영웅전설 1~4를 DOSBox-X로 실행한다 — 정발 대조·패치 검증용.
#
#   scripts/dosbox.sh ed1|ed2|ed3|ed4 [옵션...] [dosbox 추가인자...]
#
#     --app      앱 번들(open -a)로 실행 — macOS에서 키 입력이 안 먹을 때(아래 참조)
#     --debug    DOSBox-X 디버거(-break-start). ⚠ 디버거 UI는 **실행한 터미널**에 뜨므로
#                --app 과 같이 못 쓰고, -log-con 도 같은 터미널을 두고 부딪혀 뺀다
#     --refresh  사본을 버리고 원본에서 다시 만든다(세이브·설정·패치 전부 초기화)
#     --setup    게임 대신 SETUP.EXE 실행 — 사운드/음악 장치 재설정(GAME.INI에 기록)
#     --cd P     P를 CD-ROM 드라이브 D:로 마운트(디렉터리면 `mount -t cdrom`, 이미지면
#                `imgmount`). 미지정이면 배포본 동봉 이미지를 **자동으로 찾는다**
#                (`originals/kr/<G>/CD/` 와 `originals/kr/<G>/DosBox/CD/` 둘 다 본다).
#
# ── 사본 방식 ────────────────────────────────────────────────────────────────
# 원본 `originals/kr/ED{1,2,3,4}`(gitignore, 소장본)는 **읽기만 한다.** 게임 본체를
# `work/dosbox/<game>/` 로 복사해 그 사본을 실행하므로, 세이브·설정은 물론 **DOS 쪽
# 패치 파일을 덮어써 가며 검증**할 수 있다(ed2-mantra-restore와 같은 방식).
#
# ⚠ **CD 이미지는 복사하지 않는다** — 용량의 95%가 CD인데(ED3: 482M 중 471M) 읽기
# 전용이라 사본이 필요 없다. 원본에서 직접 마운트한다. 덕분에 4개 전부 떠도 사본은
# ~69MB(ED1 15M + ED2 33M + ED3 11M + ED4 10M)로 끝난다.
#
# 로그: work/dosbox/<game>.log (매 실행 초기화) · 스크린샷: work/dosbox/capture
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
case "$GAME" in
  ed1) SRC=ED1; DRIVE=C; CMD="main.exe"; MARKER=MAIN.EXE;    SBTYPE=sbpro2; SBIRQ=7; WANT_CD= ;;
  ed2) SRC=ED2; DRIVE=F; CMD="game.bat"; MARKER=ED2MAIN.EXE; SBTYPE=sbpro2; SBIRQ=7; WANT_CD=1 ;;
  ed3) SRC=ED3; DRIVE=E; CMD="play.bat"; MARKER=ED3.EXE;     SBTYPE=sbpro2; SBIRQ=5; WANT_CD=1 ;;
  ed4) SRC=ED4; DRIVE=F; CMD="game.bat"; MARKER=ED4.EXE;     SBTYPE=sb16;   SBIRQ=5; WANT_CD=1 ;;
  *) usage ;;
esac

APP=0; DEBUG=0; REFRESH=0; SETUP=0; CD=""; ARGS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --app) APP=1 ;;
    --debug) DEBUG=1 ;;
    --refresh) REFRESH=1 ;;
    --setup) SETUP=1 ;;
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

BOX="$REPO/work/dosbox"
COPY="$BOX/$GAME"          # 쓰기 가능 사본 (세이브·설정·DOS 패치)
mkdir -p "$BOX/capture"

[ "$REFRESH" = 1 ] && rm -rf "$COPY"

# ── 사본 만들기 (CD·런처 폴더 제외) ─────────────────────────────────────────
if [ ! -f "$COPY/$MARKER" ]; then
  echo "사본 생성: originals/kr/$SRC → work/dosbox/$GAME (CD 제외)"
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
# work/dosbox 기준 **상대경로**로 적어 생성 conf에 절대경로가 안 남게 한다.
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

# ── conf 생성 (템플릿 → work/dosbox/<game>.conf, 생성물은 gitignore) ────────
sed -e "s|@GAME@|$GAME|g" -e "s|@DRIVE@|$DRIVE|g" -e "s|@CMD@|$CMD|g" \
    -e "s|@MOUNTCD@|$MOUNTCD|g" -e "s|@SBTYPE@|$SBTYPE|g" -e "s|@SBIRQ@|$SBIRQ|g" \
    "$REPO/dosbox/game.conf.tmpl" > "$BOX/$GAME.conf"
rm -f "$BOX/$GAME.log"

# 상대경로(logfile·captures·mapperfile·mount)가 해석되도록 기준 디렉터리로 이동한다.
cd "$BOX"
COMMON="-conf $GAME.conf -fastlaunch"

if [ "$DEBUG" = 1 ]; then
  # -log-con 은 뺀다 — 디버거 커서스 UI와 같은 터미널을 두고 부딪힌다.
  [ -x "$DOSBOX" ] || { echo "dosbox-x 없음: $DOSBOX (brew install --cask dosbox-x)" >&2; exit 1; }
  exec "$DOSBOX" $COMMON -break-start $ARGS
fi
# -log-con: DOS 콘솔 출력을 로그로 남긴다. 그래픽 모드라 화면에선 안 보이는 엔진 진단
# 메시지("Where : %s" / "What : %s" 등)를 잡기 위한 것.
if [ "$APP" = 1 ]; then
  exec open -a "$APPDIR" --args $COMMON -log-con $ARGS
fi
[ -x "$DOSBOX" ] || { echo "dosbox-x 없음: $DOSBOX (brew install --cask dosbox-x)" >&2; exit 1; }
exec "$DOSBOX" $COMMON -log-con $ARGS
