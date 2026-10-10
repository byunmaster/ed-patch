#!/bin/sh
# 정발(DOS) 영웅전설 1~4를 DOSBox-X로 실행한다 — 정발 대조·패치 검증용.
#
#   scripts/emu/dosbox.sh ed1|ed2|ed3|ed4 [옵션...] [dosbox 추가인자...]
#
#     --app      앱 번들(open -a)로 실행 — macOS에서 키 입력이 안 먹을 때(아래 참조)
#     --scancodes  usescancodes=true 로 실행. **방향키가 안 먹을 때** 시도한다(수정자키는
#                되는데 방향키만 죽는 게 전형적 증상). ⚠ 저수준 키보드 경로라 입력 모니터링
#                권한이 필요하므로 **--app 과 같이** 써야 의미가 있다
#     --mapper   매퍼 편집기로 시작(-startmapper). 단축키를 바꿔 저장하면 **전체** 매퍼
#                파일이 .local/cache/dosbox/mapper.map 로 생성된다(부분 매퍼는 키보드를 죽인다)
#     --debug    DOSBox-X 디버거(-break-start). ⚠ 디버거 UI는 **실행한 터미널**에 뜨므로
#                --app 과 같이 못 쓰고, -log-con 도 같은 터미널을 두고 부딪혀 뺀다
#     --refresh  사본을 버리고 원본에서 다시 만든다(세이브·설정·패치 전부 초기화)
#     --setup    게임 대신 SETUP.EXE 실행 — 사운드/음악 장치 재설정(GAME.INI에 기록)
#     --cd P     P를 CD-ROM 드라이브 D:로 마운트(디렉터리면 `mount -t cdrom`, 이미지면
#                `imgmount`). 미지정이면 배포본 동봉 이미지를 **자동으로 찾는다**
#                (`originals/kr/<G>/CD/` 와 `originals/kr/<G>/DosBox/CD/` 둘 다 본다).
#     --no-sync  세이브 동기화를 끈다(아래 참조). 기본은 켜짐.
#     --engine E DOSBox 구현을 고른다: x(기본) · staging. `DOSBOX_ENGINE` 로도 준다.
#     --core C   CPU 코어: normal(기본, 인터프리터) · dynamic(재컴파일 — **훨씬 빠르다**).
#                ⚠ 기본이 normal 인 건 호환성 때문이다. dynamic 은 같은 사이클을 몇 배 싸게
#                  돌려 빨리감기 천장을 올려 주지만, 자기수정 코드·타이밍 트릭을 쓰는 게임에서
#                  드물게 깨진다. **정발 DOS 판에서 확인되면 그때 기본값으로 올린다.**
#     --cycles N 에뮬 CPU 성능(기본 20000 ≈ 486). **DOSBox 의 속도는 배수가 아니라 이것**이다 —
#                터보는 그 위에서 프레임 제한을 풀 뿐이라, 게임이 CPU 를 다 쓰면 별로 안 빨라진다.
#                ⚠ 「fps 가 낮다」의 원인을 가르는 손잡이이기도 하다: 올려서 fps 가 오르면
#                  에뮬 한계, 안 오르면 **게임 자체가 그 속도**다(DOS RPG 는 원래 느리다).
#
# ── 엔진 둘 (유저 요청 2026-08-21) ───────────────────────────────────────────
# 기본은 **DOSBox Staging** 이고 X 도 그대로 산다. 「어차피 둘 다 앱 번들 아니냐」가 맞다 —
# **formula 는 둘 다 있고**(dosbox-x · dosbox-staging) 지금 이 맥엔 **둘 다 앱 번들**로 깔려
# 있다. 그러니 「formula 라 OS 천장에 안 걸린다」는 둘을 가르는 근거가 못 된다(2026-08-22 정정).
# 실제로 갈리는 건 이것들이다:
#   staging  ✅ SDL2 — **한글 입력 소스에서도 키가 먹는다**(X 는 SDL1 이라 방향키가 죽는다)
#            ✅ 활발한 유지보수 · 셰이더        ❌ 디버거 없음 · DOS 콘솔 로그 없음 · turbo 홀드 전용
#   X        ✅ `-break-start` 디버거 · `-log-con`(게임이 찍는 DOS 메시지 — ED4 진단에 실제로 썼다)
#            ✅ turbo 가 토글                   ❌ SDL1 한글 IME 함정 · 상류가 최신 macOS API 를 부르면 막힌다
# 🔴 그런데 **ED4 가 staging 에서 안 뜬다**(2026-08-22 실측 · X 에서는 뜬다). 타깃 넷 중 하나가
#   안 도는 엔진을 기본으로 둘 이유가 없어 **기본을 X 로 되돌렸다**(유저 확정). staging 은
#   `--engine staging` 으로 남는다 — 한글 입력 소스에서 X 의 방향키가 죽을 때 쓰는 길이고,
#   나중에 X 가 macOS 새 버전에서 막히면 그때 다시 뒤집으면 된다.
# 빨리감기(X) — **매퍼 이벤트 둘의 정체를 실측으로 확정했다**(2026-08-22, 문서엔 없다):
#   hand_speedlock   = **버스트(누르는 동안)**  → Tab   (SDL1 키심 9)
#   hand_speedlock2  = **토글**                 → `     (SDL1 키심 96)
#   mednafen 과 손가락이 같아진다(` 토글 · Tab 홀드). 한 번 뒤집어 봤다가 되돌린 결과다 —
#   이름만 보고 speedlock 을 토글로 짐작하면 정확히 반대다.
# ⚠ 이 배치는 `.local/cache/dosbox/mapper.map`(머신 전용)에 있다. 그 파일이 날아가면 `--mapper` 로
#   매퍼 UI 를 열어 다시 잡는다(부분 매퍼는 금물 — 전체 파일이라야 한다).
# ⚠ X 를 쓰면 **`-log-con` 이 살아난다** — 게임이 찍는 DOS 메시지가 로그에 남는다(ED4 를
#   그걸로 진단했다). 진단 능력만 보면 X 가 낫다.
# ⚠ **`--debug` 는 DOSBox-X 만 된다** — `-break-start` 디버거가 X 에만 있고, fix 트랙의
#   역공학이 거기 걸려 있다. `--debug` 를 주면 말없이 X 로 돌린다(알린다).
# ⚠ `--app`·`--scancodes` 도 X 전용이다(앱 번들 채널 + SDL1 저수준 키보드).
#
# ── 사본 방식 ────────────────────────────────────────────────────────────────
# 원본 `originals/kr/dos-ed{1,2,3,4}`(gitignore, 소장본)는 **읽기만 한다.** 게임 본체를
# `.local/cache/dosbox/<game>/` 로 복사해 그 사본을 실행하므로, 세이브·설정은 물론 **DOS 쪽
# 패치 파일을 덮어써 가며 검증**할 수 있다(ed2-mantra-restore와 같은 방식).
#
# ⚠ **CD 이미지는 복사하지 않는다** — 용량의 95%가 CD인데(ED3: 482M 중 471M) 읽기
# 전용이라 사본이 필요 없다. 원본에서 직접 마운트한다. 덕분에 4개 전부 떠도 사본은
# ~69MB(ED1 15M + ED2 33M + ED3 11M + ED4 10M)로 끝난다.
#
# 로그: .local/cache/dosbox/<game>.log (매 실행 초기화) · 스크린샷: .local/cache/dosbox/capture
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
# **기전·정본 자리·안전장치는 `scripts/emu/sync-saves.sh` 가 정본이다**(기종 무관 공용 —
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
. "$HERE/winsize.sh"   # 창 크기 단계 넷 — 실행기 셋이 같은 눈금
REPO=$(cd "$HERE/../.." && pwd)   # scripts/emu → 레포 루트
# 캡처는 세 실행기 모두 **메인 트리 `.local/work/capture/<게임>/`** 로 모은다(마스터 10-06 「저장 경로 일원화」).
#   워크트리에서 띄워도 메인 트리로 간다(.local 은 워크트리에 안 따라온다 — git-common-dir 로 찾는다).
#   `.local/cache` 가 아니라 바로 아래라 **지우는 칸이 아니다** — 찍은 것은 사람이 모은 자료다.
capture_dir() {   # $1 = 게임 칸 이름 → 만들어서 절대경로를 찍는다
  _cd=$(git -C "$REPO" rev-parse --git-common-dir 2>/dev/null || true)
  case "$_cd" in "") _root=$REPO ;; /*) _root=$(cd "$_cd/.." && pwd) ;; *) _root=$(cd "$REPO/$_cd/.." && pwd) ;; esac
  mkdir -p "$_root/.local/work/capture/$1" && printf '%s' "$_root/.local/work/capture/$1"
  return 0
}
# ⚠ **CLI 바이너리를 먼저 찾는다 — 앱 번들은 폴백이다**(유저 요청 2026-08-21). brew formula
# (`brew install dosbox-x`)는 **이 맥에서 소스로 빌드**돼 OS 천장에 안 걸리는 반면, 받아 쓰는
# 앱 번들은 상류가 최신 macOS API 를 부르는 순간 그냥 못 뜬다 — Geargrafx 가 SDL3 의
# macOS 14 API 때문에 Ventura 인 이 맥에서 실행 자체가 안 됐다(같은 날 실측). 같은 함정을
# DOS 쪽에도 두지 않는다.
# ⚠ `|| true` 가 없으면 **`set -e` 아래에서 여기서 죽는다** — 바이너리가 PATH 에 없을 때
#   command -v 가 1 을 반환하고, 그게 대입문의 종료코드가 된다(2026-08-21 실측: 이 한 줄로
#   DOS 실행이 통째로 막혔다).
# ⚠ 둘 다 **`return 0` 으로 닫는다** — 못 찾았을 때 non-zero 로 끝나면 `DOSBOX=$(staging_bin)`
#   이 그걸 물려받아 set -e 가 조용히 스크립트를 죽인다(위 command -v 주석과 같은 함정).
staging_bin() {
  b=$(command -v dosbox-staging 2>/dev/null || true); if [ -n "$b" ]; then printf '%s' "$b"; return 0; fi
  b=$(command -v dosbox 2>/dev/null || true);         if [ -n "$b" ]; then printf '%s' "$b"; return 0; fi
  b="/Applications/DOSBox Staging.app/Contents/MacOS/dosbox"
  [ -x "$b" ] && printf '%s' "$b"
  return 0
}
x_bin() {
  b=$(command -v dosbox-x 2>/dev/null || true); if [ -n "$b" ]; then printf '%s' "$b"; return 0; fi
  b=/Applications/dosbox-x.app/Contents/MacOS/dosbox-x
  [ -x "$b" ] && printf '%s' "$b"
  return 0
}
ENGINE=${DOSBOX_ENGINE:-auto}
APPDIR=${DOSBOX_APP:-/Applications/dosbox-x.app}

# 어느 구현으로 뜰지 정한다. `--which` 로 밖에서도 물어볼 수 있다 — **`emu.sh` 목록의
# 라벨이 이 답을 쓴다.** 값을 두 벌로 들면 엔진을 바꿨을 때 목록만 옛말을 한다
# (실제로 그랬다: staging 으로 돌리는데 목록엔 dosbox-x 라고 떴다 — 유저 지적 2026-08-21).
resolve_engine() {
  case "$ENGINE" in
    auto)    DOSBOX=$(x_bin); if [ -n "$DOSBOX" ]; then ENGINE=x; else DOSBOX=$(staging_bin); ENGINE=staging; fi ;;
    staging) DOSBOX=$(staging_bin) ;;
    x)       DOSBOX=$(x_bin) ;;
    *) echo "모르는 엔진: $ENGINE (staging|x)" >&2; exit 2 ;;
  esac
  DOSBOX=${DOSBOX_BIN:-$DOSBOX}
}

if [ "${1:-}" = --which ]; then
  resolve_engine
  printf 'dosbox-%s\n' "$ENGINE"
  exit 0
fi

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
CYCLES=${DOSBOX_CYCLES:-20000}
CORE=${DOSBOX_CORE:-normal}
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
    # 창 크기 단계 — DOSBox-X 는 conf 가 정하므로 **띄우기 전에** 박는다.
    # ⚠ 실행 중에는 ⌥-/⌥+ 로도 바뀐다(우리 매퍼가 문다 — X 본디 F12+↑↓ 도 산다).
    #   ⌥1~4(단계를 바로)는 mednafen·np2kai 만이다 — X 엔 그런 이벤트가 없다.
    --size) shift; WIN_SIZE=$1 ;;
    --size=*) WIN_SIZE=${1#*=} ;;
    --cycles) shift; CYCLES=$1; [ -n "$CYCLES" ] || { echo "--cycles N" >&2; exit 2; } ;;
    --core) shift; CORE=$1; [ -n "$CORE" ] || { echo "--core normal|dynamic" >&2; exit 2; } ;;
    --engine) shift; ENGINE=$1; [ -n "$ENGINE" ] || { echo "--engine staging|x" >&2; exit 2; } ;;
    --cd) shift; CD=$1; [ -n "$CD" ] || { echo "--cd 경로 필요" >&2; exit 2; } ;;
    *) ARGS="$ARGS $1" ;;
  esac
  shift
done
[ "$SETUP" = 1 ] && CMD="setup.exe"
[ "$APP" = 1 ] && [ "$DEBUG" = 1 ] && {
  echo "--app 과 --debug 는 같이 못 쓴다(디버거 UI는 터미널에 뜬다)" >&2; exit 2; }

# X 전용 기능이 걸려 있으면 엔진을 되돌린다. 조용히 다른 걸 띄우지 않고 이유를 말한다.
for need_x in "$DEBUG:--debug(디버거는 X 전용)" "$APP:--app(앱 번들 채널은 X 전용)" \
              "$SCAN:--scancodes(SDL1 저수준 키보드는 X 전용)"; do
  # ⚠ `[ … ] && echo` 로 쓰면 조건이 거짓일 때 **set -e 가 여기서 죽인다**(같은 함정을
  #   오늘 이미 한 번 밟았다 — 위 command -v 주석 참조). if 로 쓴다.
  case "$need_x" in
    1:*)
      if [ "$ENGINE" = staging ]; then echo "⚠ ${need_x#1:} — DOSBox-X 로 돌린다" >&2; fi
      ENGINE=x
      ;;
  esac
done
resolve_engine
# 매퍼는 엔진마다 형식이 달라 파일을 가른다(template 헤더 참조).
if [ "$ENGINE" = staging ]; then MAPPERFILE=mapper-staging.map; else MAPPERFILE=mapper.map; fi

ORIG="$REPO/originals/kr/$SRC"
[ -d "$ORIG" ] || { echo "원본 없음: originals/kr/$SRC (소장본 필요 — originals/README.md)" >&2; exit 1; }

BOX="$REPO/.local/cache/dosbox"
COPY="$BOX/$GAME"          # 쓰기 가능 사본 (세이브·설정·DOS 패치)
mkdir -p "$BOX/capture"

[ "$REFRESH" = 1 ] && rm -rf "$COPY"

# ── 사본 만들기 (CD·런처 폴더 제외) ─────────────────────────────────────────
if [ ! -f "$COPY/$MARKER" ]; then
  echo "사본 생성: originals/kr/$SRC → .local/cache/dosbox/$GAME (CD 제외)"
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
# .local/cache/dosbox 기준 **상대경로**로 적어 생성 conf에 절대경로가 안 남게 한다.
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
        MOUNTCD="imgmount D \"../../../originals/kr/$SRC/$sub/$(basename "$img")\" -t iso"
        break 3
      done
    done
  done
  [ -n "$MOUNTCD" ] || echo "⚠ CD 이미지 없음: originals/kr/$SRC/{CD,DosBox/CD}/*.{cue,iso} — BGM 초기화 실패 가능" >&2
fi

# ── conf 생성 (템플릿 → .local/cache/dosbox/<game>.conf, 생성물은 gitignore) ────────
sed -e "s|@GAME@|$GAME|g" -e "s|@DRIVE@|$DRIVE|g" -e "s|@CMD@|$CMD|g" \
    -e "s|@MOUNTCD@|$MOUNTCD|g" -e "s|@SBTYPE@|$SBTYPE|g" -e "s|@SBIRQ@|$SBIRQ|g" \
    -e "s|@MAPPERFILE@|$MAPPERFILE|g" -e "s|@CYCLES@|$CYCLES|g" -e "s|@CORE@|$CORE|g" \
    -e "s|@WINRES@|$(winsize_wh "${WIN_SIZE:-2}")|g" \
    -e "s|^captures=capture\$|captures=$(capture_dir "dos-$GAME")|" \
    "$HERE/dosbox/game.conf.tmpl" > "$BOX/$GAME.conf"
# 템플릿은 DOSBox-X 기준이다. staging 은 여섯 키를 거부하는데(실측) 전부 경고로 넘어가긴
# 하지만, 로그가 지저분하면 진짜 경고를 놓친다 — 여기서 갈아 준다.
#   usescancodes·autolock·stop turbo on key  없는 설정  → 뺀다
#   priority=highest,highest                 형식이 다르다 → 뺀다(기본값이면 충분)
#   [log] logfile=                           X 전용     → 뺀다(대신 stdout 을 파일로 받는다)
#   captures= / cycles=fixed N               이름·형식이 바뀜 → [capture] capture_dir /
#                                            cpu_cycles=N (⚠ `fixed` 를 남기면 파싱에 실패해
#                                            **3000 사이클로 떨어진다** — 게임이 기어간다)
# ⚠ `glshader=none` 을 박는다 — staging 은 기본으로 CRT 셰이더를 자동 적용하는데(실측
#   `crt/vga-1080p`), **문안 QA 에서 글자가 흐려지면 우리 조판 탓인지 셰이더 탓인지 못 가른다.**
# ── staging 매퍼 만들기 ─────────────────────────────────────────────────────
# 빨리감기를 **Tab** 에 둔다 — mednafen 쪽 「Tab = 홀드」와 같은 키다(유저 확정 2026-08-22).
# staging 의 speedlock 은 **누르는 동안만**이고 토글 설정이 없어서, 토글이 필요하면 mednafen 의
# ` 쪽을 쓴다(거기선 `fast_forward` 가 토글, `slow_forward` 를 전용해 Tab 이 홀드다).
# staging 기본값은 Alt+F12 다.
# ⚠ Tab 은 DOS 키이기도 하다(`key_tab`). 영웅전설 1~4 는 Tab 을 안 쓰지만, 쓰는 게임을
#   붙일 땐 여기를 옮긴다.
#
# ⚠ **한 줄만 적은 매퍼는 못 쓴다** — 파일이 있으면 기본 바인딩을 통째로 대체해서 나머지
#   키가 전부 죽는다(오늘 ED3 에서 실제로 겪었다). 그래서 **전체 파일**을 만들어야 하는데,
#   보통은 게임 안 매퍼 UI 에서 저장해야 나온다.
# 그런데 staging 이 번들한 매퍼 186개를 대조해 보니 **스틱 바인딩만 빼면 185개가 완전히
# 동일**했다 — 그게 곧 기본 세트다. 그걸 밑절미로 스틱을 걷어내고 speedlock 만 바꾼다.
# 없으면 그냥 안 만든다(기본 바인딩으로 돈다 — 빨리감기만 Alt+F12 로 남는다).
# ── DOSBox-X 매퍼 — 없으면 레포 템플릿을 깐다 (유저 제공 2026-09-07) ─────────────
# 🔴 **X 는 밑절미가 없었다.** Staging 은 번들 매퍼를 고쳐 쓰는데(아래) X 는 그런 게 없어,
#   지금까지 유저가 `--mapper` UI 로 직접 잡은 것이 `.local/`(머신 전용)에만 살았다.
#   머신을 옮기면 사라지고, 그러면 빨리감기도 창 크기도 조용히 기본값으로 돌아간다.
#   ⇒ 유저 머신의 것을 레포 템플릿으로 올려 **없을 때만** 깐다. conf 를 템플릿으로 두는
#     것과 같은 방식이다. 이미 있으면 **안 건드린다** — 사람이 손댄 배치일 수 있다.
# ⚠ **전체 파일이라야 한다** — 부분 매퍼는 기본 바인딩을 통째로 대체해 키보드를 죽인다
#   (2026-07-31 실측). 그래서 한 줄만 고치는 게 아니라 226줄을 통째로 둔다.
# 담긴 손가락: ` 토글 · Tab 홀드(빨리감기) · ⌥-/⌥+ 와 F12+↑↓(창 크기) · F12+R 재시작.
#   🔑 **X 에도 창 크기 이벤트가 본디 있다**(`hand_incsize`·`hand_decsize`, 기본 F12+↑↓).
#     없는 줄 알고 「X 는 conf 뿐」이라고 적었던 것은 틀렸다 — 매퍼 파일을 보고 알았다.
#     ⌥ 조합을 **덧붙이기만** 한다(`mod2` = Alt). 기본 F12+↑↓ 도 그대로 살려 둔다 —
#     뺏을 이유가 없고, 뺏으면 옛 손가락을 아는 사람이 헤맨다.
if [ "$ENGINE" = x ] && [ ! -f "$BOX/$MAPPERFILE" ] && [ -f "$HERE/dosbox/mapper-x.map" ]; then
  mkdir -p "$BOX" && cp "$HERE/dosbox/mapper-x.map" "$BOX/$MAPPERFILE"
  echo "매퍼 생성: $MAPPERFILE (빨리감기 \` 토글·Tab 홀드 · 창 크기 ⌥-/⌥+ · 재시작 F12+R)"
fi

if [ "$ENGINE" = staging ] && [ ! -f "$BOX/$MAPPERFILE" ]; then
  for _m in "/Applications/DOSBox Staging.app/Contents/Resources/mapperfiles/xbox/d.map" \
            "$(brew --prefix 2>/dev/null)/share/dosbox-staging/mapperfiles/xbox/d.map"; do
    [ -f "$_m" ] || continue
    # 스틱 제거 → speedlock 을 ` (SDL 스캔코드 53) 로
    # 공통 단축키(유저 요청 2026-09-07): F10 = 재시작(mednafen 기본·np2kai 와 같다). Staging 매퍼엔
    # ⌘ 수식키도 세이브스테이트도 없어 ⌘R·F5/F7 은 여기선 못 준다 — 그건 mednafen·np2kai 에서.
    sed -e 's/"stick[^"]*"//g' -e 's/ *$//' \
        -e 's|^hand_speedlock .*|hand_speedlock "key 43"|' \
        -e 's|^hand_restart .*|hand_restart "key 67"|' "$_m" > "$BOX/$MAPPERFILE"
    echo "매퍼 생성: $MAPPERFILE (빨리감기 홀드 = Tab · 재시작 = F10 — mednafen 과 같은 키)"
    break
  done
fi

if [ "$ENGINE" = staging ]; then
  sed -e '/^usescancodes=/d' -e '/^autolock=/d' -e '/^stop turbo on key=/d' \
      -e '/^priority=/d' \
      -e '/^\[log\]/d' -e '/^logfile=/d' \
      -e '/^captures=/d' \
      -e 's/^cycles=fixed /cpu_cycles=/' \
      "$BOX/$GAME.conf" > "$BOX/$GAME.conf.tmp"
  {
    echo ""
    echo "[render]"
    echo "glshader=none"
    echo ""
    echo "[capture]"
    echo "capture_dir=$(capture_dir "dos-$GAME")"
  } >> "$BOX/$GAME.conf.tmp"
  mv "$BOX/$GAME.conf.tmp" "$BOX/$GAME.conf"
fi
# ⚠ 매퍼 파일은 기본 바인딩을 **덮는 게 아니라 통째로 대체**한다 — 한 줄짜리를 깔면
# 나머지 키가 전부 언바인드돼 **키보드가 죽는다**(2026-07-31 실측). 게임 안 매퍼 UI
# (Ctrl+F1)로 저장한 **전체 파일**만 유효하다. 손으로 만든 부분 매퍼는 치운다.
if [ -f "$BOX/$MAPPERFILE" ] && [ "$(wc -l < "$BOX/$MAPPERFILE")" -lt 20 ]; then
  echo "⚠ 부분 매퍼 감지 — 키보드가 죽으므로 제거한다: .local/cache/dosbox/$MAPPERFILE" >&2
  rm -f "$BOX/$MAPPERFILE"
fi
rm -f "$BOX/$GAME.log"

# ── 한글 입력기 경고 ────────────────────────────────────────────────────────
# ⚠ macOS 입력 소스가 **한글이면 방향키가 DOSBox 에 안 들어온다**(IME 가 먹는다).
# 조용히 방향키만 죽고 Shift·메뉴는 멀쩡해서 DOSBox 설정 문제로 오해하기 쉽다
# (2026-07-31 유저가 규명 — usescancodes 도 --app 도 원인이 아니었다).
. "$HERE/ime.sh"
warn_ime

# ── 세이브 동기화 ───────────────────────────────────────────────────────────
# 기전은 `scripts/emu/sync-saves.sh` 에 있다(기종 무관 공용 — PS1 메모리카드도 같은 걸 쓴다).
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
# ⚠ staging 은 `-fastlaunch` 가 없고, **자기 기본 설정 파일을 먼저 읽는다** — 그대로 두면
#   이 맥의 개인 설정이 섞여 결과가 환경을 탄다(레포 제1 원칙). `--noprimaryconf` 로 끊는다.
if [ "$ENGINE" = staging ]; then
  COMMON="-conf $GAME.conf --noprimaryconf"
else
  COMMON="-conf $GAME.conf -fastlaunch"
fi
[ "$SCAN" = 1 ]   && COMMON="$COMMON -set \"sdl usescancodes=true\""
[ "$MAPPER" = 1 ] && COMMON="$COMMON -startmapper"

have_dosbox() {
  [ -n "$DOSBOX" ] && [ -x "$DOSBOX" ] && return 0
  if [ "$ENGINE" = staging ]; then
    echo "DOSBox Staging 없음 — brew install dosbox-staging (또는 --engine x)" >&2
  else
    echo "dosbox-x 없음 — brew install dosbox-x" >&2
  fi
  exit 1
}
# staging 은 `-log-con` 이 없다. 로그는 stdout 으로 나오니 그걸 파일로 받는다 —
# 그래픽 모드라 화면에 안 보이는 엔진 진단 메시지를 잡는 게 이 로그의 목적이다.
run_engine() {                      # $@ = 추가 인자
  if [ "$ENGINE" = staging ]; then
    "$DOSBOX" $COMMON "$@" $ARGS >>"$BOX/$GAME.log" 2>&1
  else
    "$DOSBOX" $COMMON -log-con "$@" $ARGS
  fi
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
    have_dosbox; run_engine
  fi
}

# 동기화가 꺼져 있으면 예전 그대로 exec 로 넘긴다 — 프로세스를 하나 아끼고 신호도 그대로 간다.
if [ "$SYNC" != 1 ]; then
  if [ "$DEBUG" = 1 ]; then have_dosbox; exec "$DOSBOX" $COMMON -break-start $ARGS; fi
  if [ "$APP" = 1 ]; then
    exec open -a "$APPDIR" --args -conf "$BOX/$GAME.conf" -defaultdir "$BOX" \
         -fastlaunch -log-con $APPOPT $ARGS
  fi
  have_dosbox; run_engine; exit $?
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
