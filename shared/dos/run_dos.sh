#!/bin/sh
# 정발(DOS) 영웅전설 1~4를 DOSBox-X로 실행한다 — 한글화 작업의 **정발 대조용**.
#
#   shared/dos/run_dos.sh ed1|ed2|ed3|ed4 [--app] [--refresh] [--setup]
#                                          [--cd <경로|cue>] [dosbox 추가인자...]
#
#     --app      앱 번들(open -a)로 실행 — 키 입력이 안 먹을 때(아래 주석 참조)
#     --refresh  오버레이 초기화 — 세이브·수정 CNF를 버리고 원본 상태로 되돌린다
#     --setup    게임 대신 SETUP.EXE 실행 — 사운드/음악 장치 재설정(GAME.INI에 기록)
#     --cd P     P를 CD-ROM 드라이브 D:로 마운트(디렉터리면 `mount -t cdrom`, 이미지면
#                `imgmount`). 미지정이면 배포본에 동봉된 이미지를 **자동으로 찾는다** —
#                `originals/kr/<G>/CD/` 와 `originals/kr/<G>/DosBox/CD/` 둘 다 본다
#                (두기 런처 폴더를 지우고 CD만 남겨도 동작하게).
#
# 원본은 `originals/kr/ED{1,2,3,4}`(gitignore, 소장본). **원본은 읽기만 한다** —
# DOSBox-X의 **overlay 마운트**로 원본 위에 `work/dosbox/<game>-ovl/`를 얹어, 게임이 쓰는
# 것(세이브·설정)은 전부 오버레이로 간다. 예전엔 통째 복사했는데 ED2~4가 258/482/433MB라
# 1.2GB가 중복됐다 — overlay는 복사가 0이고 원본 보호는 더 확실하다.
# 로그: work/dosbox/<game>.log · 스크린샷: work/dosbox/capture
#
# 게임별 실행 명령·CD 필요 여부는 **두기게임 배포본의 `DosBox/Settings.conf`**(UTF-16LE의
# `Autoexec=` / `CD=`)와 각 게임 배치 파일에서 확인한 값이다:
#   ed1  main.exe   CD 없음(CD=0, CD 폴더 비어 있음)   DataDir 설정 없음
#   ed2  game.bat   CD/ED2.cue                        DataDir = F:\ed2\ed2 → F: 루트로 재작성
#                   (= gkey.exe -s opening.exe → ed2main.exe. **오프닝은 CD에서 재생**되므로
#                    ed2main만 직접 부르면 오프닝이 통째로 빠진다 — 유저 지적 07-29)
#   ed3  play.bat   CD/MANTRAINC_YJ3.ISO              DataDir = E:
#   ed4  GAME.BAT   CD/ED4.iso                        DataDir = F:
# ⚠ ed3/ed4는 **반드시 배치 파일**을 타야 한다. `driver.exe ed?.exe`(=NOSOUND.BAT)만 돌리면
#   "No driver loaded / Sound Driver Installation Failed"로 죽는다 — 배치가 먼저 올리는
#   사운드 TSR `soundrv.com`이 없으면 드라이버 설치 자체가 실패한다(유저 실측 07-29).
#   그리고 **BGM이 CD 오디오**라 CD를 안 물리면 "Music System Installation Failed"로 또 죽는다.
#   사운드 카드는 각 게임 CNF가 지정한다(ed3=SOUND_BLASTER_PRO, ed4=SOUND_BLASTER_16 —
#   conf의 sbtype=sb16이 둘 다 커버).
# DataDir은 **사본의 CNF에서** 마운트 루트로 재작성한다(원본 경로를 재현하는 것보다 단순).
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
DOSBOX=${DOSBOX:-/Applications/dosbox-x.app/Contents/MacOS/dosbox-x}  # 환경변수로 교체 가능

usage() { echo "사용법: $0 ed1|ed2|ed3|ed4 [--app] [--refresh] [dosbox 인자...]" >&2; exit 2; }

GAME=$1
[ -n "$GAME" ] || usage
shift

case "$GAME" in
  # SBTYPE/SBIRQ: 게임 CNF(ed1·ed2)와 동봉 드라이버(ed3=sbpro.com, ed4=SB16.COM) 기준.
  # ⚠ ed1/ed2는 CNF가 **IRQ 7**을 쓴다 — 5로 두면 소리가 안 난다.
  ed1) SRC=ED1; DRIVE=C; CMD="main.exe"; SBTYPE=sbpro2; SBIRQ=7 ;;
  ed2) SRC=ED2; DRIVE=F; CMD="game.bat"; SBTYPE=sbpro2; SBIRQ=7 ;;
  ed3) SRC=ED3; DRIVE=E; CMD="play.bat"; SBTYPE=sbpro2; SBIRQ=5 ;;
  ed4) SRC=ED4; DRIVE=F; CMD="game.bat"; SBTYPE=sb16;   SBIRQ=5 ;;
  *) usage ;;
esac

APP=0; REFRESH=0; SETUP=0; CD=""; WANT_CD=""; ARGS=""
case "$GAME" in ed2|ed3|ed4) WANT_CD=1 ;; esac  # BGM이 CD 오디오(ed1만 CD 없음)
while [ $# -gt 0 ]; do
  case "$1" in
    --app) APP=1 ;;
    --refresh) REFRESH=1 ;;
    --setup) SETUP=1 ;;
    --cd) shift; CD=$1; [ -n "$CD" ] || { echo "--cd 경로 필요" >&2; exit 2; } ;;
    *) ARGS="$ARGS $1" ;;
  esac
  shift
done
[ "$SETUP" = 1 ] && CMD="setup.exe"

ORIG="$REPO/originals/kr/$SRC"
[ -d "$ORIG" ] || { echo "원본 없음: originals/kr/$SRC (소장본 필요 — originals/README.md)" >&2; exit 1; }

BOX="$REPO/work/dosbox"
OVL="$BOX/$GAME-ovl"      # 쓰기 전용 오버레이 (세이브·수정 CNF)
mkdir -p "$BOX/capture"

[ "$REFRESH" = 1 ] && rm -rf "$OVL"
mkdir -p "$OVL"

# 원본 CNF의 DataDir은 설치 시점 경로(F:\ed2\ed2 등)라 이 환경에 없다. 마운트 루트로
# 고친 사본을 **오버레이에** 둔다 — 오버레이 파일이 원본을 가리므로 원본은 안 바뀐다.
for cnf in "$ORIG"/*.CNF "$ORIG"/*.cnf; do
  [ -f "$cnf" ] || continue
  base=$(basename "$cnf")
  if grep -qi '^ *DataDir' "$cnf" && [ ! -f "$OVL/$base" ]; then
    sed -E "s|^ *DataDir.*|DataDir = ${DRIVE}:|I" "$cnf" > "$OVL/$base"
    echo "  오버레이 $base: DataDir → ${DRIVE}:"
  fi
done

# CD 마운트 줄 조립 — ed3/ed4는 BGM이 CD 오디오라 드라이브가 없으면 음악 초기화가 실패한다.
MOUNTCD=""
if [ -n "$CD" ]; then
  case "$CD" in
    *.cue|*.CUE|*.iso|*.ISO|*.chd|*.CHD) MOUNTCD="imgmount D \"$CD\" -t iso" ;;
    *) MOUNTCD="mount D \"$CD\" -t cdrom" ;;
  esac
elif [ -n "$WANT_CD" ]; then
  # 배포본에 동봉된 CD 이미지를 자동으로 찾아 D:로 물린다(.cue 우선 — 오디오 트랙 포함).
  # work/dosbox 기준 상대경로로 적어 conf에 절대경로가 안 남게 한다.
  for sub in CD DosBox/CD; do
    for ext in cue CUE iso ISO; do
      for img in "$ORIG/$sub"/*."$ext"; do
        [ -f "$img" ] || continue
        MOUNTCD="imgmount D \"../../originals/kr/$SRC/$sub/$(basename "$img")\" -t iso"
        break 3
      done
    done
  done
  if [ -z "$MOUNTCD" ]; then
    echo "⚠ CD 이미지 없음: originals/kr/$SRC/{CD,DosBox/CD}/*.{cue,iso} — BGM 초기화 실패 가능" >&2
  fi
fi

# 템플릿 → 실제 conf (생성물은 work/ 이하라 gitignore. 커밋되는 건 템플릿뿐)
sed -e "s|@GAME@|$GAME|g" -e "s|@DRIVE@|$DRIVE|g" -e "s|@CMD@|$CMD|g" \
    -e "s|@MOUNTCD@|$MOUNTCD|g" -e "s|@ORIG@|../../originals/kr/$SRC|g" \
    -e "s|@SBTYPE@|$SBTYPE|g" -e "s|@SBIRQ@|$SBIRQ|g" \
    "$HERE/dosbox.conf.in" > "$BOX/$GAME.conf"

# 상대경로(logfile·captures·mapperfile·mount)가 해석되도록 기준 디렉터리로 이동한다.
cd "$BOX"
COMMON="-conf $GAME.conf -fastlaunch -log-con"

if [ "$APP" = 1 ]; then
  exec open -a /Applications/dosbox-x.app --args $COMMON $ARGS
fi
[ -x "$DOSBOX" ] || { echo "dosbox-x 없음: $DOSBOX (brew install --cask dosbox-x)" >&2; exit 1; }
exec "$DOSBOX" $COMMON $ARGS
