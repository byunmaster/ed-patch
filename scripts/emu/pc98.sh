#!/bin/sh
# PC-98 게임을 띄운다 — `emu.sh pc98-ed1` 이 여기로 위임한다. **기본 실행기는 np2kai** 다
# (유저 확정 2026-09-06 — DOSBox-X 의 PC-98 모드는 **전투 둘째 라운드에서 뻗는다**, 원본으로도).
# `--dosbox` 로 DOSBox-X 갈래를 그대로 쓸 수 있다(매퍼·kbtest·shot 은 그쪽 전용).
#
#   sh scripts/emu/pc98.sh pc98-ed1 [옵션...] [실행기 추가인자...]
#
#     --np2kai    (기본) np2kai 로 띄운다. 없으면 묻고 소스 빌드(.local/cache/np2kai/). 우리 패치가 붙는다:
#                 ` 빨리감기 토글 · Tab 빨리감기 홀드 · \ 디스크 교체 · 방향키=텐키 · ⌘R 재시작 ·
#                 ⌘L 마우스 잠금 토글(시작은 안 잡음, NP2KAI_MOUSE_LOCK=1 이면 예전처럼 잡는다 — ⌘M 은 macOS 최소화).
#                 실행파일은 `NP2KAI_BIN` 또는 PATH 의 sdlnp21kai·sdlnp2kai·
#                 xnp21kai·xnp2kai·np21kai·np2kai, 또는 /Applications 의 *np2*kai*.app.
#                 FDD1 = 부팅 디스크(event/program) · **FDD2 = scenario(세이브 매체)**.
#                 ⚠ 디스크 교체는 np2kai 메뉴에서(FDD1 → program.d88). 설정·ROM 은
#                 `~/.config/<실행파일 이름>/`(font.rom 이 없으면 본체 폰트 자리가 빈다 —
#                 이 게임은 제 폰트를 RAM 에 올리므로 부팅 경고 셋 정도만 영향).
#     --dosbox    DOSBox-X 의 PC-98 모드(옛 기본값). `PC98_EMU=dosbox` 로도 된다.
#
#     (옵션 없이)   ⑴ 원본·빌드 칸을 **목록으로 고르고**(하나뿐이면 안 묻는다),
#                   ⑵ 세이브가 있으면 **어느 디스크로 뜰지**도 고른다(이어하기 / 오프닝부터)
#     --orig      묻지 않고 **원본**을 띄운다 (원문 대조용)
#     --build T   묻지 않고 **빌드 꼬리표 T** 를 띄운다 (`work/build/T`)
#     --event     묻지 않고 Event 디스크로 부팅 — 오프닝부터다(**오프닝 한글화 확인**·새 게임).
#                 ⚠ 오프닝은 5분 넘게 돌고 그동안 **키를 하나도 안 받는다**(리눅스 실측:
#                 60초간 Enter 를 계속 보낸 화면과 안 보낸 화면이 같았다). 모르고 열면
#                 「키보드가 안 먹는다」로 보인다 — ` 로 빨리감기 하면 40초다
#     --program   묻지 않고 Program 디스크로 부팅 — 오프닝을 건너뛰고 **바로 LOAD 메뉴**.
#                 ⚠ **이어하기 전용**이다: 세이브가 없으면 LOAD·サクサク 둘 다 안 먹고
#                 화면만 한 번 깜빡인다(실측 — 키보드로도 마우스 클릭으로도 그렇다).
#                 새 게임은 반드시 --event 쪽 흐름을 거쳐야 한다
#     --refresh   실행 사본을 버리고 원본에서 다시 만든다 (세이브·설정 초기화)
#     --shot P    뜬 화면을 P 로 저장하고 끝낸다 (헤드리스 검증용, ImageMagick 필요)
#     --wait N    `--shot` 전에 기다릴 초 (기본 25)
#     --headless  화면이 없어도 Xvfb 로 띄운다 (없으면 자동 판단)
#     --no-app    맥에서 **앱 번들 대신 실행파일**로 띄운다 (기본은 앱 번들)
#     --scancodes `usescancodes=true` — **방향키만 안 먹을 때** 시도한다
#     --sdl1      옛 SDL1 앱 번들로 띄운다 (비교용)
#     --jis       일본어(JIS) 배열 키보드를 쓸 때
#     --kbtest    🔧 **키가 들어오나만 잰다** — 게임 대신 DOS 프롬프트를 띄워 타이핑을
#                 호스트 파일로 받아 본다. 「안 먹는다」를 추측 대신 계측으로 가른다
#     --mapper    🎮 **키 배치를 한 번 만든다** — 매퍼 편집기를 띄우고, 네가 Save 를 누르면
#                 그 파일에 우리 배치(방향키=텐키 · Tab=빨리감기 · \`=토글 · \\=디스크 교체)를
#                 얹는다. 한 번만 하면 되고 `--refresh` 로도 안 날아간다
#     --no-sync   dev 로 세이브를 안 보낸다 (기본은 보낸다 · `PC98_SYNC=0` 으로도 끈다)
#
# 💾 **세이브는 Scenario 디스크 「안」에 쓰인다** — 이 기종만 그렇다. 그래서 실행 사본을
#    매번 새로 뜨는 이 스크립트가 **세이브를 매번 지우고 있었다**(2026-09-03 발견).
#    지금은 종료할 때 세이브 매체를 `.local/cache/pc98/saves/<게임>/<출처>-<해시>.d88` 로 떼어
#    두고 dev 에 올린다. 자세한 건 아래 「💾 세이브」 절.
#
# ── 🔴 키가 안 먹을 때 ──────────────────────────────────────────────────────
# ⓿ **오프닝 데모부터 의심한다.** `--event` 로 켜면 4분 넘는 비대화형 데모가 돈다 —
#    화면은 멀쩡히 도는데 키를 하나도 안 받으니 「키보드 고장」과 구분이 안 된다.
#    기본값(Program)으로 켜면 LOAD 메뉴가 뜨고 거기선 먹는다. **이게 제일 흔한 오진이다.**
# 🔧 그다음 **`--kbtest` 로 잰다.** 「키가 에뮬까지 오나」와 「게임이 그 키를 안 받나」는
#    화면만 봐서는 안 갈리는데, 고치는 자리가 아예 다르다. 재고 나서 아래로 간다.
# ⑴ **창을 한 번 클릭한다.** 터미널에서 띄우면 포커스가 터미널에 남아 키가 그쪽으로 간다 —
#    제일 흔하고 제일 먼저 볼 것이다(에뮬 화면은 멀쩡히 도니까 「안 먹는다」로만 보인다).
# ⑵ **dosbox-x 가 이미 떠 있으면 그 창이 앞으로 나올 뿐이다.** macOS `open -a` 는 **이미
#    도는 앱에는 `--args` 를 안 준다**(실측 2026-08-31: 두 번째 호출이 프로세스를 안 늘리고
#    첫 인자 그대로였다). 그래서 디스크를 바꿔 다시 띄워도 **옛 창이 그대로 살아 있고**,
#    거기서 치는 키는 당연히 「엉뚱하게」 논다. 아래에서 `open -n` 을 쓰고 같은 사본을 쥔
#    옛 인스턴스를 먼저 닫는 이유가 이것이다.
# 그다음은 아래 순서. 근거는 `scripts/emu/ime.sh` · `scripts/emu/dosbox.sh` 의 실측이다:
#   ⑶ **입력 소스가 한글이면 DOSBox-X(SDL1)는 방향키가 죽는다.** 수정자키·메뉴는 멀쩡해서
#      설정 문제로 오해하기 쉽다. 영문(ABC)으로 바꾼다 — 아래 `warn_ime` 가 알려 준다.
#   ⑷ **앱 번들로 띄워야 키가 간다** — 맥에선 이게 기본이다(`--no-app` 로 끈다).
#      ⚠ `open -a` 는 **cwd 를 안 물려준다** → conf 는 절대경로, `-defaultdir` 로 맞춘다.
#      (그걸 안 하면 상대경로 `event.d88` 을 못 찾아 마운트가 통째로 빈다 — DOS 쪽 실측.)
#   ⑸ 🔴 **방향키만 안 먹는 건 에뮬 탓이 아니다** — 이 게임은 이동을 **텐키(숫자패드)로만**
#      받는다(인게임 실측: 텐키 18,526px / 방향키·윗줄숫자·HJKL 427px = 무반응).
#      맥북엔 텐키가 없어 그대로면 못 움직인다. `--mapper` 로 방향키를 텐키에 물린다.
#      ⚠ 방향키가 **에뮬까지는 잘 온다**는 증거가 있다 — ⌃⌥+→ 로 Turbo 가 걸린다.
#      그러니 `--scancodes`·입력소스·SDL 을 뒤지기 전에 여기부터 본다(그 셋을 한나절 팠다).
#   ⑹ 그래도 이상하면 `--scancodes`(저수준 경로 — 입력 모니터링 권한이 든다).
#
# ── 왜 MAME 가 아니라 DOSBox-X 인가 (2026-08-30 실측) ────────────────────────
# `emu.sh` 의 `blocked_by` 는 오래 「pc98 = MAME 머신 ROM 필요」라고 적고 있었다. 맞는 말이나
# **그 길만 있는 게 아니었다** — DOSBox-X 의 `machine=pc98` 은 **머신 ROM 없이 뜬다.**
# 실측: Debian trixie 의 `dosbox-x 2025.02.01` 로 영웅전설 PC-98 오프닝이 그대로 나왔다.
#   · emucap 의 `mame-pc98` 어댑터는 MAME 를 소스에서 빌드하고 **pc9801rs 롬셋 전량**을
#     요구한다(어댑터 README). 계측이 필요해지면 그때 그 길로 간다.
#   · 지금 필요한 건 「뜨나 · 화면이 맞나」이고 그건 이쪽이 훨씬 싸다.
#
# 🔴 **함정 넷** (전부 실측으로 물린 것이다)
#   ⑴ 이 게임 디스크엔 **파일 시스템이 없다**(FAT 도 디렉터리도 없다). `imgmount` 에
#      **`-fs none` 이 없으면** DOSBox-X 가 FAT 로 읽으려다 실패한다
#      (`drive_fat.cpp: Illegal BPB value`).
#   ⑵ `-fs none` 이면 드라이브를 **글자가 아니라 번호**로 준다(`0`=fda `1`=fdb).
#      `imgmount A ...` 는 "Must specify drive number" 로 튕긴다.
#   ⑵' 🔴 **파일 이름이 DOS 8.3 을 지켜야 한다** — 확장자 앞이 8자를 넘으면 `imgmount` 가
#      **같은 내용인데도** 못 연다(실측: `old_event.d88` 실패 · 그 사본 `oldev.d88` 성공).
#      그래서 사본 이름을 `event`·`program`·`scenario` 로 고정한다.
#   ⑶ **시나리오 디스크는 게임이 세이브를 쓰는 매체다.** originals 는 읽기 전용이라
#      반드시 `.local/` 사본을 띄운다 — 원본에 직접 물리면 소장본이 더러워진다.
#   ⑷ 🔴 **conf 를 쓰는 히어독은 반드시 따옴표로 닫는다**(`<<'EOF'`). 안 그러면 주석 속
#      백틱이 **셸 명령으로 실행되고** 그 자리가 빈칸이 된다 — 실제로 그랬다(2026-08-31:
#      `auto: command not found` · `dosbox/game.conf.tmpl: No such file` · `pc-98: command
#      not found` 셋이 뜨고 생성된 conf 의 주석 세 줄이 잘려 나갔다).
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/winsize.sh"   # 창 크기 단계 넷 — 실행기 셋이 같은 눈금
REPO=$(cd "$HERE/../.." && pwd)
. "$HERE/../lib/select.sh"     # 화살표 키 선택 UI

GAME=${1:-pc98-ed1}
case "$GAME" in -*) GAME=pc98-ed1 ;; *) [ $# -gt 0 ] && shift ;; esac

# 🔴 **시작 디스크는 세이브가 있으면 물어서 고른다**(유저 요청 2026-09-03 · 아래 💿 절).
#   여기 `BOOT=event` 는 **세이브가 없을 때의 값**이다 — 그때는 Program 이 빈 LOAD 화면이라
#   고를 게 없다(슬롯 10칸이 전부 비어 있다 · 실측).
#   ⚠ Event 는 **오프닝 데모 디스크**라 5분 넘게 비대화형으로 돌고 그동안 키를 하나도 안
#   받는다 — 모르고 QA 로 열면 화면은 멀쩡히 도는데 아무 키도 안 먹어 **「에뮬 키보드가
#   고장났다」로 오진하게 된다.** 실제로 그 오진에 한나절을 썼다(호스트 입력·SDL·PC-98
#   키보드 절·앱 번들 채널을 차례로 의심했는데 전부 멀쩡했다).
EMU=${PC98_EMU:-np2kai}   # np2kai | dosbox
REBUILD_NP2=${NP2KAI_REBUILD:-0}
ORIG=0; BUILDPICK=; BOOT=event; REFRESH=0; SHOT=; WAIT=25; HEADLESS=auto
APP=auto; SCAN=0; JIS=0; KBTEST=0; SDL1=0; GENMAP=0
BOOTSET=0
SYNC=${PC98_SYNC:-1}   # dev 세이브 동기화 (PC98_SYNC=0 으로 기본 끄기)
PRISTINE=
EXTRA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --orig)     ORIG=1 ;;
    --build)    BUILDPICK=$2; shift ;;
    --program)  BOOT=program; BOOTSET=1 ;;          # 기본값이라 사실상 무해한 별칭이다
    --event|--opening) BOOT=event; BOOTSET=1 ;;      # 오프닝 데모를 일부러 볼 때
    --refresh)  REFRESH=1 ;;
    --shot)     SHOT=$2; shift ;;
    --wait)     WAIT=$2; shift ;;
    --headless) HEADLESS=1 ;;
    --no-app)   APP=0 ;;
    --app)      APP=1 ;;
    --scancodes) SCAN=1 ;;
    --sdl1)     SDL1=1 ;;   # 옛 SDL1 앱 번들로 비교해 볼 때
    --jis)      JIS=1 ;;
    --kbtest)   KBTEST=1 ;;
    --mapper)   GENMAP=1 ;;   # 매퍼 편집기를 띄워 배치를 만든다
    --no-sync)  SYNC=0 ;;   # dev 세이브 동기화를 끈다
    --np2kai)   EMU=np2kai ;;
    --dosbox)   EMU=dosbox ;;
    --rebuild-np2kai) REBUILD_NP2=1 ;;   # 소스 빌드를 다시 한다(패치·상류 갱신)
    # 창 크기 단계 — np2kai 는 환경변수로 받는다(패치가 첫 창을 그때 정한다).
    # ⚠ 실행 중에는 ⌥- / ⌥+ 로 바꾼다. DOSBox-X 는 conf 가 정하므로 여기서 안 쓴다.
    --size)     WIN_SIZE=$2; shift ;;
    --size=*)   WIN_SIZE=${1#*=} ;;
    *)          EXTRA="$EXTRA $1" ;;
  esac
  shift
done

# ⚠ **맥에선 PATH 에 `dosbox-x` 가 없다** — `brew install --cask` 는 **앱 번들**로 깐다.
#   `scripts/emu/dosbox.sh` 가 DOS 쪽에서 쓰는 것과 같은 해석기를 여기서도 쓴다.
# ⚠ **값을 정하는 자리에서 실패할 수 있는 명령을 쓰지 않는다**(루트 CLAUDE.md 셸 절) —
#   `command -v` 는 못 찾으면 non-zero 라 `set -e` 가 그 줄에서 조용히 죽는다.
#   그래서 `|| true` 를 붙이고 함수는 `return 0` 으로 닫는다.
# 뒤지는 자리를 **한 곳에 적어 두고** 못 찾으면 그 목록을 그대로 보여 준다 —
# 「설치했는데 안 된다」를 물었을 때 되물을 필요가 없게.
# 🔴 **SDL2 빌드를 먼저 찾는다**(2026-08-31). 순서가 바뀐 이유는 취향이 아니다 —
#   ⑴ **SDL1 에선 부팅된 게임이 키를 못 받는다.** 에뮬 자체 DOS 프롬프트는 멀쩡히 먹어서
#      더 헷갈린다(경로가 다르다 — 셸은 BIOS 로 읽고 게임은 PC-98 키보드 하드웨어를 직접
#      읽는다). 같은 게임이 dev 의 SDL2 판에서는 LOAD 메뉴 키가 먹었다.
#   ⑵ SDL1 은 **한글 입력 확정에서 통째로 죽는다**(insertText SIGSEGV — ime.sh 머리말).
#   ⑶ 맥의 **cask(SDL1)는 2026-09-01 비활성 예정**이다(Gatekeeper 미통과). 남는 길이 없다.
#   맥에서 SDL2 를 얻는 길은 **formula** 다: `brew install dosbox-x` (cask 가 아니다).
dosbox_x_places() {
  [ -n "${DOSBOX_BIN:-}" ] && printf '%s\n' "$DOSBOX_BIN"
  printf '%s\n' \
    /opt/homebrew/bin/dosbox-x \
    /usr/local/bin/dosbox-x \
    /usr/bin/dosbox-x \
    "${DOSBOX_APP:-/Applications/dosbox-x.app}/Contents/MacOS/dosbox-x" \
    "$HOME/Applications/dosbox-x.app/Contents/MacOS/dosbox-x" \
    /Applications/DOSBox-X.app/Contents/MacOS/DOSBox-X
}
dosbox_x_bin() {
  # ⚠ `--sdl1` 이면 번들만 본다 — 비교용이라 조용히 SDL2 로 새면 비교가 안 된다.
  if [ "${SDL1:-0}" = 1 ]; then
    for b in "${DOSBOX_APP:-/Applications/dosbox-x.app}/Contents/MacOS/dosbox-x" \
             "$HOME/Applications/dosbox-x.app/Contents/MacOS/dosbox-x"; do
      [ -x "$b" ] && { printf '%s' "$b"; return 0; }
    done
    return 0
  fi
  dosbox_x_places | while IFS= read -r b; do
    [ -x "$b" ] && { printf '%s' "$b"; break; }
  done
  return 0
}
# 백엔드는 **물어본다** — 경로로 추측하면 틀린다(formula 가 어디 깔릴지 모른다).
engine_of() {
  "$1" -version 2>&1 | grep -o "SDL[12]" | head -1 || true
  return 0
}
# np2kai 실행파일 — 값을 정하는 자리라 실패해도 non-zero 로 안 끝난다(루트 CLAUDE.md 셸 절).
np2kai_bin() {
  [ -n "${NP2KAI_BIN:-}" ] && { printf '%s\n' "$NP2KAI_BIN"; return 0; }
  for n in sdlnp21kai_sdl2 sdlnp21kai sdlnp2kai_sdl2 sdlnp2kai; do
    [ -x "$NP2_HOME/bin/$n" ] && { printf '%s\n' "$NP2_HOME/bin/$n"; return 0; }
  done
  for n in sdlnp21kai_sdl2 sdlnp21kai sdlnp2kai_sdl2 sdlnp2kai xnp21kai xnp2kai np21kai np2kai; do
    _b=$(command -v "$n" 2>/dev/null || true)
    [ -n "$_b" ] && { printf '%s\n' "$_b"; return 0; }
  done
  for a in /Applications/*np2*kai*.app "$HOME"/Applications/*np2*kai*.app /Applications/*NP2*.app; do
    [ -d "$a" ] || continue
    _b=$(ls "$a"/Contents/MacOS/* 2>/dev/null | head -1 || true)
    [ -n "$_b" ] && { printf '%s\n' "$_b"; return 0; }
  done
  return 0
}
# ── np2kai 가 없으면 **묻고 빌드한다**(유저 요청 2026-09-06 — 다른 실행기는 `need_tool` 이
#    brew 로 묻고 깐다. np2kai 는 brew 포뮬러가 없어 소스 빌드다). 자리는 머신 전용 `.local/cache/np2kai/`:
#      src/    git clone --depth 1 AZO234/NP2kai
#      build/  cmake -G Ninja -D BUILD_SDL=ON -D USE_SDL=2 …  →  타깃 sdlnp21kai_sdl2(IA-32 판)
#      bin/    결과 실행파일 사본 — `np2kai_bin` 이 PATH 보다 먼저 여기를 본다
#    ⚠ 몇 분 걸린다. 「게임 켜자」가 빌드로 변하는 게 싫으면 n 을 치면 된다(비대화형이면 안내만).
#    ⚠ ROM 은 못 깔아 준다 — 설정 폴더(`~/.config/sdlnp21kai/`)에 font.rom 등을 유저가 둔다.
patch_sha1() { { sha1sum "$1" 2>/dev/null || shasum -a 1 "$1"; } | cut -c1-40; }
NP2_HOME="${NP2KAI_HOME:-$(cd "$(git -C "$REPO" rev-parse --git-common-dir 2>/dev/null || echo "$REPO/.git")/.." && pwd)/.local/cache/np2kai}"
np2kai_install() {
  if [ "$(uname -s)" = Darwin ]; then
    command -v brew >/dev/null 2>&1 || { echo "⛔ brew 가 없다 — https://brew.sh 부터" >&2; return 1; }
    echo "  ① 의존물: brew install cmake ninja sdl2 sdl2_mixer sdl2_ttf libusb"
    brew install cmake ninja sdl2 sdl2_mixer sdl2_ttf libusb || return 1
  else
    for t in cmake ninja git; do command -v "$t" >/dev/null 2>&1 || {
      echo "⛔ $t 가 없다 — apt-get install cmake ninja-build git libsdl2-dev libsdl2-mixer-dev libsdl2-ttf-dev libusb-1.0-0-dev" >&2; return 1; }; done
  fi
  mkdir -p "$NP2_HOME"
  if [ ! -d "$NP2_HOME/src/.git" ]; then
    echo "  ② 소스: git clone --depth 1 https://github.com/AZO234/NP2kai"
    rm -rf "$NP2_HOME/src"
    git clone -q --depth 1 https://github.com/AZO234/NP2kai "$NP2_HOME/src" || return 1
  fi
  # 🎮 **키 패치** — np2kai 는 손에 익은 키가 거의 없다(NOWAIT 도 메뉴 항목뿐이다). 실행기 셋을
  #   같은 손가락으로 쓰려고 `sdl/` 에 붙인다 — 레포의 `np2kai-keys.patch`.
  #     ` 토글 · Tab 홀드(빨리감기, 유저 요청 2026-09-06 — PC-98 판은 오프닝 스킵이 없어 5분을
  #     그냥 봐야 한다) · \ 디스크 교체 · 방향키=텐키 · F5/F7 세이브 · F10·⌘R 재시작 · ⌘L 마우스 ·
  #     **⌥- / ⌥+ · ⌥1~4 창 크기**(유저 요청 2026-09-07 — mednafen 과 같은 손가락, 단계 넷).
  #     🔴 ⌘가 아닌 건 mednafen 이 정했다 — 거기선 ⌘가 수정자로 안 세어져 세이브 슬롯과 겹친다.
  #   ⚠ 창 크기는 **에뮬 해상도가 아니라 창만** 바꾼다. `NP2KAI_WIN_SIZE`(1~4, 기본 2)로 처음 크기를
  #     정한다 — `emu.sh --size N` 이 그 환경변수를 준다.
  #   빌드마다 소스를 상류로 되돌리고 새로 붙인다. 상류가 바뀌어 안 붙으면 **키 없이** 빌드하고 알린다.
  _pt="$HERE/np2kai-keys.patch"
  # 🔴 **먼저 소스를 상류 그대로 되돌린다.** 옛 패치가 붙은 소스에 새 패치를 대면 적용도 역적용도
  #   안 맞아 「안 붙는다 — 키 없이 빌드」로 빠지고, 지문은 새 걸로 찍혀 다음엔 묻지도 않는다
  #   (유저 실측 2026-09-06: 재빌드했는데 ⌘L 도 마우스 기본값도 옛날 그대로였다). src 는 우리 클론이라
  #   지켜야 할 로컬 변경이 없다.
  git -C "$NP2_HOME/src" checkout -q -- . 2>/dev/null || true
  git -C "$NP2_HOME/src" clean -qfd 2>/dev/null || true
  PATCHED=0
  if git -C "$NP2_HOME/src" apply --check "$_pt" >/dev/null 2>&1 && git -C "$NP2_HOME/src" apply "$_pt"; then
    PATCHED=1
    echo "  ② 키 패치: 붙였다 (\` 토글 · Tab 홀드 · \\ 디스크 교체 · 방향키=텐키 · ⌘R · ⌘L · ⌥-/⌥+ · ⌥1~4 창 크기 · ⌥M 소리)"
  else
    echo "  ⚠ 키 패치가 상류 소스에 안 붙는다 — 키 없이 빌드한다(메뉴 F11 로 대신). 상류가 바뀐 것이니 알려 달라" >&2
  fi
  # ⚠ 상류가 SDL3 를 기본으로 바꿨다(2026-09 실측: `USE_SDL` 기본 3, README 는 아직 SDL2).
  # ⚠ **C++ 표준을 박는다** — 상류 CMake 가 표준을 안 정해 컴파일러 기본을 탄다. 리눅스 gcc 는
  #   C++17 이라 넘어가는데 인텔 맥 AppleClang 15 는 C++98 로 잡아 `constexpr` 에서 20개 오류로
  #   죽었다(유저 실측 2026-09-06, sound/mamebsd/ymfm.h). `CMAKE_CXX_STANDARD` 만 주면 CMake 가
  #   「기본이 충족하면 생략」하므로 `-std=gnu++17` 을 플래그로도 준다.
  #   SDL2 로 고정하면 타깃 이름에 `_sdl2` 가 붙는다 — `sdlnp21kai_sdl2`(IA-32 판).
  echo "  ③ 빌드: cmake … -D BUILD_SDL=ON -D USE_SDL=2 → sdlnp21kai_sdl2 (몇 분)"
  cmake -S "$NP2_HOME/src" -B "$NP2_HOME/build" -G Ninja -D CMAKE_BUILD_TYPE=Release \
        -D BUILD_SDL=ON -D BUILD_X=OFF -D BUILD_WX=OFF -D BUILD_HAXM=OFF -D USE_SDL=2 -D USE_USB=OFF \
        -D CMAKE_CXX_STANDARD=17 -D CMAKE_CXX_STANDARD_REQUIRED=ON -D CMAKE_C_STANDARD=11 \
        -D CMAKE_CXX_FLAGS=-std=gnu++17 \
        > "$NP2_HOME/cmake.log" 2>&1 || { echo "⛔ cmake 실패 — $NP2_HOME/cmake.log" >&2; return 1; }
  cmake --build "$NP2_HOME/build" --target sdlnp21kai_sdl2 -j "$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)" \
        > "$NP2_HOME/build.log" 2>&1 || { echo "⛔ 빌드 실패 — $NP2_HOME/build.log" >&2; return 1; }
  _out=$(find "$NP2_HOME/build" -type f -name 'sdlnp21kai_sdl2' -perm -u+x 2>/dev/null | head -1 || true)
  [ -n "$_out" ] || { echo "⛔ 빌드는 끝났는데 sdlnp21kai_sdl2 가 안 보인다 — $NP2_HOME/build" >&2; return 1; }
  mkdir -p "$NP2_HOME/bin" && cp "$_out" "$NP2_HOME/bin/sdlnp21kai_sdl2" || return 1
  # 🔑 **어느 패치로 구웠는지 지문을 남긴다** — 레포의 패치가 바뀌면 실행파일이 있어도 다시 굽는다.
  #   실측 2026-09-06: 첫 빌드 뒤 패치를 추가했는데 실행파일이 있어 설치기가 안 돌았고, 유저는
  #   `rm -rf build` 까지 했는데도 빨리감기 키가 없는 채로 떴다.
  # ⚠ 패치가 안 붙었으면 지문을 **안 찍는다** — 다음 실행이 다시 묻게.
  if [ "$PATCHED" = 1 ]; then patch_sha1 "$_pt" > "$NP2_HOME/bin/.patch.sha1"; else rm -f "$NP2_HOME/bin/.patch.sha1"; fi
  echo "  ✅ $NP2_HOME/bin/sdlnp21kai_sdl2"
  return 0
}
NP2=
if [ "$EMU" = np2kai ]; then
  NP2=$(np2kai_bin)
  # 우리가 구운 실행파일이면 **패치 지문**을 맞춰 본다 — 다르면 다시 굽는다(묻고).
  case "$NP2" in
    "$NP2_HOME"/bin/*)
      _want=$(patch_sha1 "$HERE/np2kai-keys.patch"); _have=$(cat "$NP2_HOME/bin/.patch.sha1" 2>/dev/null || true)
      if [ "$REBUILD_NP2" = 1 ] || [ "$_want" != "$_have" ]; then
        [ "$REBUILD_NP2" = 1 ] && echo "ⓘ --rebuild-np2kai — np2kai 를 다시 굽는다" \
          || echo "ⓘ 키 패치가 바뀌었다(구운 것: ${_have:-없음}) — np2kai 를 다시 굽는다"
        if has_tty && confirm_yes "   지금 다시 빌드할까? 몇 분 걸린다 (y/n) "; then
          rm -rf "$NP2_HOME/build"
          np2kai_install || exit 1
          NP2=$(np2kai_bin)
        else
          echo "   그냥 띄운다 — 키 패치 없이(나중에: sh scripts/emu.sh pc98-ed1 --rebuild-np2kai)" >&2
        fi
      fi ;;
  esac
  if [ -z "$NP2" ]; then
    echo "⛔ np2kai 가 없다 (뒤진 곳: NP2KAI_BIN · $NP2_HOME/bin · PATH 의 sdlnp21kai·sdlnp2kai·xnp21kai·xnp2kai · /Applications/*np2*kai*.app)" >&2
    if has_tty && confirm_yes "   소스에서 빌드해 $NP2_HOME 에 둘까? 몇 분 걸린다 (y/n) "; then
      np2kai_install || exit 1
      NP2=$(np2kai_bin)
    else
      echo "   나중에 하려면 그냥 다시 실행하고 y — 또는 직접:" >&2
      echo "     brew install cmake ninja sdl2 sdl2_mixer sdl2_ttf libusb" >&2
      echo "     git clone --depth 1 https://github.com/AZO234/NP2kai $NP2_HOME/src" >&2
      echo "     cmake -S $NP2_HOME/src -B $NP2_HOME/build -G Ninja -D BUILD_SDL=ON -D BUILD_X=OFF -D BUILD_WX=OFF -D USE_SDL=2 && cmake --build $NP2_HOME/build --target sdlnp21kai_sdl2" >&2
      echo "   깔린 게 있으면:  NP2KAI_BIN=/경로/sdlnp21kai  sh scripts/emu.sh pc98-ed1" >&2
      echo "   DOSBox-X 로 그냥 띄우려면:  --dosbox" >&2
      exit 1
    fi
  fi
  [ -n "$NP2" ] || { echo "⛔ 빌드 뒤에도 np2kai 를 못 찾는다" >&2; exit 1; }
  # DOSBox-X 전용 옵션은 여기서 막는다 — 조용히 무시하면 「찍었는데 파일이 없다」가 된다.
  _bad=
  [ -z "$SHOT" ]      || _bad="$_bad --shot"
  [ "$KBTEST" = 0 ]   || _bad="$_bad --kbtest"
  [ "$GENMAP" = 0 ]   || _bad="$_bad --mapper"
  [ "$SCAN" = 0 ]     || _bad="$_bad --scancodes"
  [ "$SDL1" = 0 ]     || _bad="$_bad --sdl1"
  [ -z "$_bad" ] || { echo "⛔$_bad 는 DOSBox-X 전용이다 — --dosbox 와 함께 쓴다" >&2; exit 1; }
fi
DOSBOX=
[ "$EMU" = dosbox ] && DOSBOX=$(dosbox_x_bin)
[ "$EMU" != dosbox ] || [ -n "$DOSBOX" ] || {
  echo "⛔ dosbox-x 를 못 찾았다. 이 자리들을 뒤졌다:" >&2
  echo "     PATH 의 dosbox-x" >&2
  dosbox_x_places | sed 's/^/     /' >&2
  echo "   macOS 는 brew install --cask dosbox-x 가 **앱 번들**로 깔아 PATH 에 안 붙는다." >&2
  echo "   깔린 자리를 직접 알려 주면 된다 — 둘 중 하나:" >&2
  echo "     DOSBOX_BIN=/경로/dosbox-x  sh scripts/emu.sh pc98-ed1" >&2
  echo "     DOSBOX_APP=/Applications/…app  sh scripts/emu.sh pc98-ed1" >&2
  echo "   어디 있는지 모르면: ls -d /Applications/*osbox* ; command -v dosbox-x" >&2
  exit 1
}

# 백엔드는 conf 를 쓰기 전에 알아야 한다 — **매퍼 파일이 엔진마다 형식이 다르기 때문**이다.
ENGINE=
[ -z "$DOSBOX" ] || ENGINE=$(engine_of "$DOSBOX")
[ -n "$ENGINE" ] || ENGINE=SDL2

SRC="$REPO/originals/jp/$GAME"
[ -d "$SRC" ] || { echo "⛔ 원본이 없다: originals/jp/$GAME" >&2; exit 1; }

# 실행 사본 — 머신 전용이라 `.local/` 이다(루트 CLAUDE.md 「work vs .local」).
# 🔴 **본 트리 한 곳에 둔다**(워크트리 안이 아니라). 워크트리 경로에서는 DOSBox-X 가
#   디스크를 못 열었다 — 같은 이름·같은 바이트인데 본 트리에서는 뜨고 거기서는 안 떴다
#   (2026-08-30, 재현됨. 경로 길이·점 디렉터리·깊이·파일 속성 전부 아니었고 **원인을 못
#   밝혔다**). 실행 사본은 머신 전용이라 트리마다 나눌 이유도 없다 — 한 벌이면 된다.
#   ⚠ 그래서 **한 게임을 두 트리에서 동시에 띄우면 사본이 부딪힌다.** 아래에서 그 게임의
#   옛 인스턴스를 먼저 죽이는 이유가 이것이기도 하다.
MAIN=$(cd "$(git -C "$REPO" rev-parse --git-common-dir 2>/dev/null || echo "$REPO/.git")/.." && pwd)
RUN="${PC98_RUN_DIR:-$MAIN/.local/cache/pc98}/$GAME"
[ "$REFRESH" = 1 ] && rm -rf "$RUN"
mkdir -p "$RUN"

# 🔴 **같은 사본을 쥔 옛 인스턴스를 먼저 닫는다.** 이유가 둘인데 둘 다 「조용히 틀린다」다:
#   ⑴ 아래에서 그 디스크 파일을 지우고 다시 만든다 — 열어 둔 채로 갈면 무슨 일이 나는지
#      아무도 모른다(시나리오 디스크는 게임이 **쓰는** 매체다).
#   ⑵ macOS `open -a`/`open -n` 은 **이미 도는 앱을 앞으로 낼 뿐** 새 인자를 안 준다.
#      옛 창이 살아 있으면 「빌드로 바꿔 띄웠는데 원본이 그대로」가 된다.
OLDPIDS=$(pgrep -f "(dosbox-x|np2.*kai).*$RUN" 2>/dev/null || true)
if [ -n "$OLDPIDS" ]; then
  echo "  ⓘ 같은 사본을 쓰던 실행기를 닫는다 (PID: $(echo "$OLDPIDS" | tr '\n' ' '))"
  # ⚠ TERM 을 씹는 경우가 있다(실측: 몇 분째 살아남아 다음 실행과 사본을 다퉜다).
  #   확인하고 안 죽었으면 KILL 로 올린다 — 안 그러면 감시기도 같이 안 끝난다.
  # shellcheck disable=SC2086
  kill $OLDPIDS 2>/dev/null || true
  sleep 2
  STILL=$(pgrep -f "(dosbox-x|np2.*kai).*$RUN" 2>/dev/null || true)
  if [ -n "$STILL" ]; then
    # shellcheck disable=SC2086
    kill -9 $STILL 2>/dev/null || true
    sleep 1
  fi
fi

# ── 무엇을 띄울까 — 원본이냐 빌드냐 ─────────────────────────────────────────
# **원본과 빌드 칸 전부를 한 목록에 올린다** — `emu.sh` 의 이미지 목록과 같은 규약이다.
# 종전에는 「빌드가 있으면 무조건 빌드」라 **다른 꼬리표 빌드를 고를 길이 없었고**, 지금
# 무엇이 떴는지도 한 줄 로그로만 알 수 있었다.
# ⚠ 커서는 **현재 브랜치 꼬리표**에 놓는다. ⚠ tty 가 없으면 묻지 않고 옛 규칙으로 간다.
BUILDS="$REPO/games/$GAME/work/build"
SYNCSH="$HERE/sync-saves.sh"
SAVEDIR="$(dirname "$RUN")/saves/$GAME"
# ⚠ 해시 도구는 맥(shasum)과 리눅스(sha1sum)가 다르다. **값을 정하는 자리에서 실패할 수 있는
#   명령을 쓰지 않는다**(루트 CLAUDE.md 셸 절) — 실패해도 빈 값으로 끝나게 감싼다.
sha8() {
  _h=$( { shasum -a 1 "$1" 2>/dev/null || sha1sum "$1" 2>/dev/null; } | cut -c1-8 ) || true
  printf '%s' "$_h"
}
# 그 칸(원본이면 빈 인자)의 **세이브 매체 원본** 자리 — 세이브 키의 재료다.
pristine_of() {
  if [ -n "$1" ] && [ -f "$1/scenario.d88" ]; then printf '%s' "$1/scenario.d88"; return 0; fi
  if [ -n "$1" ] && [ -f "$1/disk.hdi" ];     then printf '%s' "$1/disk.hdi";     return 0; fi
  ls "$SRC"/*Scenario*.d88 2>/dev/null | head -1 && return 0
  ls "$SRC"/*.hdi 2>/dev/null | head -1
  return 0
}
save_of() {   # $1 = 칸 경로(빈 값=원본) → 그 칸의 세이브 파일 (없으면 빈 값)
  _pr=$(pristine_of "$1"); [ -n "$_pr" ] || return 0
  if [ -n "$1" ]; then _tg=$(basename "$1"); else _tg=orig; fi
  _f="$SAVEDIR/$_tg-$(sha8 "$_pr").${_pr##*.}"
  [ -f "$_f" ] && printf '%s' "$_f"
  return 0
}
TAG=$(git -C "$REPO" branch --show-current 2>/dev/null | sed 's|.*/||; s|[^A-Za-z0-9._-]|-|g' || true)
TAB=$(printf '\t')

# 「라벨<탭>경로」— 경로가 비면 원본 그대로다.
# 🔴 **세이브가 있는 칸을 목록에 표시한다**(2026-09-03 사고 뒤). 세이브는 **칸마다 따로**다 —
#   세이브가 디스크 이미지 안에 있으니 원본 세이브를 빌드에 얹으면 그건 원본 디스크로
#   노는 것이다. 그런데 화면에 그게 안 보여서, **원본으로 새로 저장하고 빌드로 이어하기**를
#   눌러 「예전 세이브가 나온다」로 겪었다(유저 보고). 잃은 건 없었지만 보이지 않는 게 문제다.
sources() {
  _sv=$(save_of ""); [ -n "$_sv" ] && _m=" 💾" || _m=""
  printf '원본%s\t\n' "$_m"
  for _d in "$BUILDS"/*/; do
    [ -d "$_d" ] || continue
    _d=${_d%/}
    _n=$(ls "$_d"/*.d88 "$_d"/*.hdi 2>/dev/null | wc -l | tr -d ' ')
    [ "$_n" -gt 0 ] || continue
    _sv=$(save_of "$_d"); [ -n "$_sv" ] && _m=" 💾" || _m=""
    printf '빌드 %s (%s장)%s\t%s\n' "$(basename "$_d")" "$_n" "$_m" "$_d"
  done
}
row_src() {
  _lb=${2%%"$TAB"*}
  if [ "$3" = 1 ]; then printf '\033[36m❯ %s\033[0m\n' "$_lb"
  else                  printf '  %s\n' "$_lb"; fi
}

OVER=                                  # 원본 위에 덮을 빌드 칸 (빈 값 = 원본만)
SIDEPICK=                              # 목록에서 같이 고른 시작 디스크 (빈 값 = 안 골랐다)
NL='
'                                      # ⚠ `$(printf '\n')` 은 뒤 개행을 먹어서 못 쓴다
# ⚠ `--kbtest` 는 게임을 아예 안 띄운다(DOS 프롬프트다) — 무엇을 띄울지 물을 이유가 없다.
if [ "$ORIG" = 1 ] || [ "$KBTEST" = 1 ]; then
  :
elif [ -n "$BUILDPICK" ]; then
  OVER="$BUILDS/$BUILDPICK"
  [ -d "$OVER" ] || { echo "⛔ 그런 빌드 칸이 없다: $OVER" >&2; exit 1; }
else
  OLDIFS=$IFS; IFS='
'
  # shellcheck disable=SC2046
  set -- $(sources)
  IFS=$OLDIFS
  # 커서 자리 — ⑴ **세이브가 제일 최근인 칸**, 없으면 ⑵ 현재 브랜치 꼬리표의 빌드.
  # 🔴 ⑴ 이 먼저인 이유: 세이브는 칸마다 따로라, 커서가 엉뚱한 칸에 있으면 그대로 Enter 를
  #   눌러 **「예전 세이브가 나온다」**가 된다(2026-09-03 실제로 겪었다). 이어서 놀 칸이
  #   기본이어야 한다.
  _i=0; _best=; _bestt=0
  for _c in "$@"; do
    _i=$((_i + 1))
    _sv=$(save_of "${_c#*"$TAB"}")
    if [ -n "$_sv" ]; then
      _t=$(stat -f %m "$_sv" 2>/dev/null || stat -c %Y "$_sv" 2>/dev/null) || _t=0
      [ -n "$_t" ] || _t=0
      if [ "$_t" -gt "$_bestt" ]; then _bestt=$_t; _best=$_i; fi
    fi
  done
  if [ -n "$_best" ]; then
    SELECT_INDEX=$_best
  else
    _i=0
    for _c in "$@"; do
      _i=$((_i + 1))
      case "${_c%%"$TAB"*}" in "빌드 $TAG "*) SELECT_INDEX=$_i; break ;; esac
    done
  fi
  SELECT_RENDER=row_src
  # 💿 **시작 디스크를 같은 화면에서 ←→ 로 고른다**(유저 요청 2026-09-03). 화면을 두 번
  #   띄우면 「또 물어보네」가 되고, 무엇보다 **지금 어느 디스켓인지가 안 보인다.**
  #   ⚠ 세이브가 있는지는 **출처를 고른 뒤에야** 안다(키에 그 출처의 해시가 들어간다).
  #     그래서 여기서는 늘 둘 다 내주고, 세이브가 없는데 이어하기를 골랐으면 아래 💾 절에서
  #     되돌린다 — 고르는 자리에서 못 거르니 **고른 뒤에 시끄럽게** 알린다.
  if [ "$BOOTSET" = 0 ]; then
    SELECT_SIDE_LABEL="시작 디스크"
    SELECT_SIDE="이어하기 (Program)
오프닝부터 (Event)"
    SELECT_SIDE_INDEX=1
  fi
  PICK=$(select_option "띄울 것" "$@") && _rc=0 || _rc=$?
  SELECT_RENDER=; SELECT_INDEX=; SELECT_SIDE=; SELECT_SIDE_LABEL=; SELECT_SIDE_INDEX=
  case "$_rc" in
    0) # 가로축을 줬으면 결과가 **두 줄**이다(select.sh 머리말).
       _row=${PICK%%"$NL"*}
       if [ "$_row" != "$PICK" ]; then
         case "${PICK#*"$NL"}" in
           오프닝*)  SIDEPICK=event ;;
           이어하기*) SIDEPICK=program ;;
         esac
       fi
       OVER=${_row#*"$TAB"} ;;
    2) # tty 가 없다 — 옛 규칙(현재 꼬리표 빌드가 있으면 그것)으로 간다
       [ -d "$BUILDS/$TAG" ] && OVER="$BUILDS/$TAG"
       if [ -n "$OVER" ]; then _w="빌드 ${OVER##*/}"; else _w=원본; fi
       echo "  ⓘ 비대화형이라 안 묻는다 — $_w 으로 간다" >&2 ;;
    *) exit 1 ;;
  esac
fi

# ⚠ 소장본이 **플로피 3장(.d88)** 일 수도 **설치된 하드(.hdi)** 일 수도 있다 —
#   `pc98-ed1` 은 전자, `pc98-ed2` 는 후자다(`docs/ports-survey.md`). 마운트가 다르다.
# 🔴 **매번 새로 복사한다.** 이유가 둘이다.
#   ⑴ 원본과 빌드를 오가는데 사본을 재활용하면 **어느 쪽을 띄웠는지 알 수 없다**
#      (「낡은 사본을 정상으로 오해」는 이 레포의 1급 사고다).
#   ⑵ 🔴 **덮어쓴 파일은 DOSBox-X 가 못 연다**(2026-08-30, 재현됨). `cp -f` 로 제자리에
#      다시 쓴 이미지는 마운트에 실패하고, **같은 바이트를 새 파일로** 만들면 뜬다.
#      inode·권한·ext4 속성·크기·내용 어디에도 차이가 없어 **원인은 못 밝혔다.**
#      그래서 **지우고 새로 만든다**(`rm -f` 뒤 `cp`). 1.2MB 짜리 셋이라 비용이 없다.
MEDIA=fd
if ls "$SRC"/*.d88 >/dev/null 2>&1; then
  for role in Event Program Scenario; do
    low=$(echo "$role" | tr 'A-Z' 'a-z')
    f=$(ls "$SRC"/*"$role"*.d88 2>/dev/null | head -1) || true
    [ -n "$f" ] || { echo "⛔ $role 디스크를 못 찾았다: $SRC" >&2; exit 1; }
    rm -f "$RUN/$low.d88"
    cp "$f" "$RUN/$low.d88"
    # 세이브 매체(Scenario)의 **원본 자리**를 기억한다 — 「손 안 댄 상태」의 기준이다.
    if [ "$role" = Scenario ]; then PRISTINE=$f; fi
  done
elif ls "$SRC"/*.hdi >/dev/null 2>&1; then
  MEDIA=hd
  f=$(ls "$SRC"/*.hdi | head -1)
  rm -f "$RUN/disk.hdi"
  cp "$f" "$RUN/disk.hdi"
  PRISTINE=$f
else
  echo "⛔ .d88 도 .hdi 도 없다: $SRC" >&2
  exit 1
fi

# 고른 빌드 칸을 **원본 위에 덮는다.** 빌드가 세 장 다 없어도 되게(대개 event 한 장부터
# 시작한다) 있는 것만 갈아 끼우고, **몇 장이 원본 그대로인지 반드시 말한다** — 안 그러면
# 「빌드로 띄웠다」고 믿는데 실은 원본인 디스크가 섞여 있게 된다.
WHAT="원본"
if [ -n "$OVER" ]; then
  n=0
  if [ "$MEDIA" = fd ]; then
    for low in event program scenario; do
      [ -f "$OVER/$low.d88" ] || continue
      rm -f "$RUN/$low.d88"              # ⚠ 덮어쓰면 안 열린다(머리말 함정 ⑵)
      cp "$OVER/$low.d88" "$RUN/$low.d88"
      if [ "$low" = scenario ]; then PRISTINE=$OVER/scenario.d88; fi
      n=$((n + 1))
    done
    # ⚠ `$n장` 은 셸이 한글까지 이름으로 먹는다(macOS /bin/sh 실측: `(��,` 가 찍혔다) — 중괄호.
      WHAT="빌드 $(basename "$OVER") (${n}장, 나머지 $((3 - n))장은 원본)"
  elif [ -f "$OVER/disk.hdi" ]; then
    rm -f "$RUN/disk.hdi"; cp "$OVER/disk.hdi" "$RUN/disk.hdi"; n=1
    PRISTINE=$OVER/disk.hdi
    WHAT="빌드 $(basename "$OVER")"
  fi
  [ "$n" -gt 0 ] || { echo "⛔ 그 칸엔 쓸 디스크가 없다: $OVER" >&2; exit 1; }
fi

# ── 💾 세이브 ───────────────────────────────────────────────────────────────
# 🔴 **PC-98 은 세이브가 디스크 이미지 「안」에 쓰인다.** 다른 기종처럼 따로 뽑히는 세이브
#    파일이 없다 — 게임이 드라이브 2 의 **Scenario 디스크에 직접 쓴다**(실측 2026-09-03:
#    실행 사본이 빌드본과 0x0002C2~0x0012EF 구간 975바이트만 달랐다).
# 🔴 그래서 위의 「**매번 새로 복사한다**」가 **세이브를 매번 지우고 있었다.** 구조가
#    옳아서(어느 쪽을 띄웠는지 알아야 한다) 복사는 남기고, **세이브만 따로 떼어 둔다.**
#
# 🔑 **떼어 둘 때 이름에 「출처 + 그 출처의 해시」를 박는다.** 이게 이 기종의 핵심이다 —
#    세이브 디스크는 곧 **그때 그 빌드의 게임 데이터**이기도 하니까:
#      · 같은 빌드로 다시 켜면  → 키가 같다 → 세이브가 산다
#      · 빌드를 다시 만들면      → 키가 다르다 → **새 문안의 깨끗한 디스크**로 뜬다
#                                  (옛 세이브는 옛 키로 그대로 남는다 — 아무것도 안 잃는다)
#      · 원본↔빌드를 오가면      → 각자 제 디스크를 쓴다
#    「낡은 사본을 정상으로 오해」가 이 레포의 1급 사고인데, 해시를 키에 넣으면 그 자리가
#    **구조적으로 없어진다**(경고에 기대지 않는다).
# ⚠ 정본 자리와 안전장치는 `sync-saves.sh` 가 정본이다 — 여기서는 무엇을 어디로만 정한다.
#   leaf 는 originals 규약대로 `$GAME`(=pc98-ed1).
if [ "$MEDIA" = fd ]; then SAVEMED=scenario.d88; else SAVEMED=disk.hdi; fi
if [ -n "$OVER" ]; then SRCTAG=$(basename "$OVER"); else SRCTAG=orig; fi
SAVEKEY="$SRCTAG-$(sha8 "$PRISTINE").${SAVEMED##*.}"

# `--refresh` 는 「세이브·설정 초기화」다 — 세이브가 $RUN 밖으로 나왔으니 여기서도 지운다.
if [ "$REFRESH" = 1 ]; then rm -f "$SAVEDIR/$SAVEKEY"; fi

if [ "$SYNC" = 1 ] && [ "$KBTEST" != 1 ]; then
  if sh "$SYNCSH" probe; then
    sh "$SYNCSH" pull "$GAME" "$SAVEDIR"
  else
    echo "⚠ ${DEV_HOST:-dev} 에 못 붙는다 — 로컬 세이브로 진행한다(종료 후에도 안 올라간다)" >&2
    SYNC=0
  fi
fi

# 떼어 둔 세이브가 있으면 **그 디스크로 갈아 끼운다**(위 복사가 덮어쓴 자리를 되돌린다).
# ⚠ 여기서도 `rm -f` 뒤 `cp` 다 — 제자리 덮어쓴 이미지는 DOSBox-X 가 못 연다(위 함정 ⑵).
if [ "$KBTEST" != 1 ] && [ -f "$SAVEDIR/$SAVEKEY" ]; then
  rm -f "$RUN/$SAVEMED"
  cp "$SAVEDIR/$SAVEKEY" "$RUN/$SAVEMED"
  echo "  💾 세이브를 얹었다 — **$WHAT** 의 것이다 ($SAVEKEY)"
fi

# ── 💾 다른 칸의 세이브를 가져온다 (유저 실측 2026-09-06 「이어하기를 골랐는데 오프닝이 떴다」) ──
# 세이브 칸은 빌드 해시로 갈리므로(위) **빌드를 새로 받을 때마다 처음부터**가 된다. 그런데 이 게임의
# 세이브는 시나리오 디스크의 **논리 섹터 0~127 한 덩이**(0 = 슬롯 목록 · 1~127 = 슬롯 데이터, 슬롯당
# 섹터 둘)뿐이라 어느 빌드에나 이식할 수 있다. 실린더 0~7 이라 d88 에서 **연속**이다 — 헤더 0x2B0
# 직후 128섹터 × (16B 헤더 + 1,024B) = 133,120B. 인터리브는 실린더 안에서만 일어나므로 파싱이 필요 없다.
# ⚠ 처음엔 「논리 0·1·2 세 섹터」로 알았다(pc98-ed1 이 두 번 정정했다 — 그 세이브가 슬롯 1 만 써서
#   diff 에 그것만 보였다). 셋만 옮기면 **슬롯 1 말고는 다 잃는다.** 관리자 독립 검증(09-06): 유저 세이브
#   넷의 세이브 차이가 전부 이 구간 안이고, 우리 빌드의 패치(논리 1008~)는 이 구간을 한 바이트도 안 건드린다.
# ⚠ 사전조건: 두 파일 크기가 같다(1,281,968B). 다르면 다른 디스크(event·program)를 잘못 고른 것.
# 가져오면 **이 칸의 세이브로 저장**되므로 다음부터는 그냥 뜬다. 원본은 안 건드린다(사본을 만든다).
import_save() {  # $1=옛 세이브 파일 → $RUN/$SAVEMED 에 섹터 셋을 얹고 $SAVEDIR/$SAVEKEY 로 남긴다
  # ⚠ 원본·빌드의 program.d88 을 같이 넘긴다 — 세이브에 박힌 글자를 바꿀 밑절미다(아래).
  _po=$(ls "$SRC"/*Program*.d88 2>/dev/null | head -1 || true)
  _pb="$RUN/program.d88"
  python3 - "$1" "$RUN/$SAVEMED" "${_po:-/nonexistent}" "$_pb" <<'PY' || return 1
import sys, pathlib
LO, HI = 0x0002B0, 0x00020AB0            # scenario.d88 논리 섹터 0~127 (헤더 직후 128섹터, 133,120B)
old, new = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
src, dst = old.read_bytes(), bytearray(new.read_bytes())
if len(src) != len(dst) or len(src) != 1281968:
    sys.exit(f"⛔ 크기가 다르다 — 다른 디스크다: {old.name} {len(src):,}B vs {new.name} {len(dst):,}B")
dst[LO:HI] = src[LO:HI]

# 🔴 **세이브에 글자가 박혀 있다** — 장 이름 바와 파티 이름 넷은 게임이 실행 파일에서 세이브로
#    복사한다(pc98-ed1 실측 2026-09-07). 그래서 원판·옛 빌드 세이브를 새 빌드로 열면 그 자리만
#    일본어·깨진 글자로 뜬다(유저가 본 「HUD 빈칸」의 한 갈래). 여기서 우리 문안으로 바꿔 준다.
# 자리는 **원본 program.d88 과 같은 오프셋**이다(게임이 통째로 복사한다 — 실측으로 일치).
#    그래서 하드코딩한 문안이 필요 없다: 세이브에서 읽은 값을 **원본 program 에서 찾아**,
#    **빌드 program 의 같은 자리** 값으로 바꾼다. 빌드가 바뀌면 저절로 따라오고, 이미 우리
#    문안이면 원본에서 못 찾아 조용히 넘어간다.
# ⚠ 길이가 다르면 **안 바꾼다** — 세이브 레코드는 stride 0x40 고정이라 늘리면 다음 칸을 먹는다.
#    (우리 빌드는 짧은 이름을 공백으로 채워 길이가 같다.)
CHAP = (0x001083, 30)                                    # 장 이름 바(앞뒤 공백 5칸 포함)
PARTY = (0x001220, 0x001260, 0x0012a0, 0x0012e0)         # 파티 넷, 종결자 0x06 까지
prog_o, prog_b = pathlib.Path(sys.argv[3]), pathlib.Path(sys.argv[4])
if prog_o.exists() and prog_b.exists():
    po, pb = prog_o.read_bytes(), prog_b.read_bytes()
    n = 0
    if len(po) == len(pb):
        off, ln = CHAP
        cur = bytes(dst[off:off + ln])
        i = po.find(cur)
        if i >= 0 and pb[i:i + ln] != cur:
            dst[off:off + ln] = pb[i:i + ln]; n += 1
        for off in PARTY:
            end = dst.find(b"\x06", off, off + 0x40)
            if end < 0:
                continue
            cur = bytes(dst[off:end])
            i = po.find(cur + b"\x06")
            if i < 0:
                continue
            j = pb.find(b"\x06", i, i + 0x40)
            if j < 0 or j - i != end - off:      # 길이가 다르면 건드리지 않는다
                continue
            if pb[i:j] != cur:
                dst[off:end] = pb[i:j]; n += 1
    if n:
        print(f"  💾 세이브에 박힌 글자 {n}자리를 이 빌드 문안으로 바꿨다(장 이름·파티 이름)")
new.write_bytes(bytes(dst))
PY
  mkdir -p "$SAVEDIR" && cp "$RUN/$SAVEMED" "$SAVEDIR/$SAVEKEY"
}
if [ "$MEDIA" = fd ] && [ "$KBTEST" != 1 ] && [ ! -f "$SAVEDIR/$SAVEKEY" ]; then
  _cands=$(ls -t "$SAVEDIR"/*.d88 2>/dev/null | sed "/\/${SAVEKEY}\$/d" || true)
  if [ -n "$_cands" ]; then
    if has_tty; then
      echo "  💾 **$WHAT** 엔 세이브가 없는데 다른 칸엔 있다 — 세이브(논리 섹터 0~127)만 이 빌드로 가져올 수 있다"
      _o=$IFS; IFS='
'
      # shellcheck disable=SC2086
      set -- $_cands
      IFS=$_o
      _names=""
      for _c in "$@"; do _names="$_names$(basename "$_c" .d88) ($(date -r "$_c" +%m-%d\ %H:%M 2>/dev/null || stat -f %Sm -t %m-%d\ %H:%M "$_c"))
"; done
      # shellcheck disable=SC2086
      OLDIFS=$IFS; IFS='
'; set -- $_names "가져오지 않는다 (오프닝부터)"; IFS=$OLDIFS
      SELECT_QUIET=1
      if _pick=$(select_option "세이브" "$@"); then
        SELECT_QUIET=
        case "$_pick" in
          "가져오지 않는다"*) ;;
          *) _key=${_pick%% (*}
             if import_save "$SAVEDIR/$_key.d88"; then
               echo "  💾 가져왔다: $_key → $SAVEKEY (원본 칸은 그대로다)"
             else
               echo "  ⚠ 가져오기 실패 — 오프닝부터 뜬다" >&2
             fi ;;
        esac
      else
        SELECT_QUIET=
      fi
    else
      echo "  ⓘ 다른 칸에 세이브가 있다($(echo "$_cands" | wc -l | tr -d ' ')개) — 대화형에서 띄우면 가져올지 묻는다" >&2
    fi
  fi
fi

# ── 💿 어느 디스크로 뜨나 ────────────────────────────────────────────────────
#   · 이어하기(Program) = 게임 본편 QA. 오프닝도 디스크 교체도 안 만난다
#   · 오프닝부터(Event) = **오프닝 한글화 확인**(유저 요청 2026-09-03) · 새 게임
# 고르는 자리는 위 목록의 ←→ 다. 안 물은 경로(`--orig`·`--build`·비대화형)에서는
# **세이브가 있으면 이어하기**로 간다 — 그게 열에 아홉이다.
if [ "$BOOTSET" = 0 ] && [ "$KBTEST" != 1 ]; then
  if [ -n "$SIDEPICK" ]; then
    BOOT=$SIDEPICK
  elif [ -f "$SAVEDIR/$SAVEKEY" ]; then
    BOOT=program
    echo "  💿 세이브가 있어 이어하기로 뜬다(오프닝은 --event)"
  fi
  # 🔴 세이브가 없는데 이어하기면 **빈 LOAD 화면**이다 — 되돌리고 시끄럽게 알린다.
  #    (슬롯 10칸이 전부 비고 LOAD·サクサク 둘 다 안 먹는다 — 실측.)
  if [ "$BOOT" = program ] && [ ! -f "$SAVEDIR/$SAVEKEY" ]; then
    BOOT=event
    echo "  ⓘ **$WHAT** 엔 세이브가 없다 — 이어하기는 빈 화면이라 오프닝부터 뜬다"
    # 다른 칸에 있으면 알려 준다 — 이게 안 보여서 「예전 세이브가 나온다」로 겪었다.
    _other=$(ls "$SAVEDIR" 2>/dev/null | sed "/^${SRCTAG}-/d" | head -3 | tr '\n' ' ')
    [ -n "$_other" ] && echo "     └ 다른 칸엔 있다: $_other(세이브는 칸마다 따로다 — 디스크 안에 있어서)"
  fi
fi

# 종료할 때 부른다. **원본과 같으면 아무것도 안 한다** — 세이브를 안 한 실행(스크린샷·
# 매퍼 만들기·그냥 확인)이 빈 파일을 정본으로 올려 버리는 걸 막는다.
save_out() {
  [ -f "$RUN/$SAVEMED" ] || return 0
  [ -n "${PRISTINE:-}" ] || return 0
  if cmp -s "$PRISTINE" "$RUN/$SAVEMED"; then return 0; fi
  # ⚠ **안 바뀌었으면 올리지 않는다.** `sync-saves.sh` 의 push 는 매번 `<leaf>.bak` 을
  #   갈아 치우므로, 같은 세이브를 다시 올리면 **되돌릴 한 세대를 그냥 태운다** —
  #   세이브 없이 두 번 켜는 것만으로 직전 세대가 사라진다.
  if cmp -s "$SAVEDIR/$SAVEKEY" "$RUN/$SAVEMED" 2>/dev/null; then return 0; fi
  mkdir -p "$SAVEDIR"
  cp "$RUN/$SAVEMED" "$SAVEDIR/$SAVEKEY"
  echo "  💾 세이브를 떼어 뒀다: $SAVEDIR/$SAVEKEY"
  if [ "$SYNC" = 1 ]; then sh "$SYNCSH" push "$GAME" "$SAVEDIR" "$SAVEKEY" || true; fi
}

# ── np2kai 갈래 ─────────────────────────────────────────────────────────────
# 여기까지(원본/빌드 고르기 · 실행 사본 · 세이브 되살리기 · 부팅 디스크 · save_out)는 실행기와
# 무관하다. 아래부터는 DOSBox-X 전용(conf · 매퍼 · 앱 번들 · imgmount)이라 np2kai 는 여기서 뜬다.
#
# np2kai 의 규약(소스 sdl/np2.c 실측 2026-09-06):
#   · 위치 인자를 **확장자로** 가른다 — .d88/.fdi/… 는 FDD, 앞에서부터 FDD1·FDD2(둘까지).
#     .hdi/.nhd 는 IDE, .iso/.cue 는 CD.
#   · 설정·ROM 자리 = `$XDG_CONFIG_HOME/<실행파일이름>/` 또는 `~/.config/<실행파일이름>/`
#     (sdlnp2kai · sdlnp21kai · xnp2kai …). 파일은 `np2kai.cfg`, 절은 `[NekoProjectIIkai]`.
#   · `-c/--config <파일>` 로 다른 설정을 줄 수 있다. 우리는 유저 설정을 건드리지 않는다.
# 🔴 **FDD2 = scenario.d88** 이다. 이 게임은 시나리오 디스크에 세이브를 쓰고(드라이브 2 에서만
#    슬롯을 읽는다 — 드라이브 1 이면 전부 Read Error, pc98 세션 실측), 종료 뒤 `save_out` 이
#    그 파일을 떼어 둔다. np2kai 가 읽기전용으로 열면 세이브가 조용히 안 남는다 — 설정에
#    읽기전용 옵션을 켜 두지 않았는지 본다.
if [ "$EMU" = np2kai ]; then
  if [ "$MEDIA" = fd ]; then
    case "$BOOT" in program) FD1=program.d88 ;; *) FD1=event.d88 ;; esac
    set -- "$RUN/$FD1" "$RUN/scenario.d88"
    DRIVES="FDD1=$FD1 · FDD2=scenario.d88 (세이브 매체)"
  else
    set -- "$RUN/disk.hdi"
    DRIVES="IDE=disk.hdi"
  fi
  # 설정 폴더 이름은 파일 이름이 아니라 **컴파일 상수**다(sdl/np2.c `appname`: IA-32 판 = sdlnp21kai,
  # i286 판 = sdlnp2kai). cmake 타깃 `_sdl2` 꼬리는 파일 이름에만 붙으니 떼고 본다.
  NP2NAME=$(basename "$NP2")
  case "$NP2" in *.app/Contents/MacOS/*) NP2NAME=$(basename "${NP2%%.app/Contents/MacOS/*}") ;; esac
  NP2NAME=$(printf '%s' "$NP2NAME" | sed -E 's/_(sdl[123]|HAXM)+$//')
  CFGDIR="${XDG_CONFIG_HOME:-$HOME/.config}/$NP2NAME"
  # np2kai 는 이 폴더를 **읽기만 하고 만들지 않는다**(유저 실측 2026-09-06: 맥 ~/.config 에 없었다).
  # 유저가 font.rom 을 둘 자리이니 먼저 만들어 둔다 — 안 만들면 「어디에 두라는 거냐」가 된다.
  mkdir -p "$CFGDIR" 2>/dev/null || true
  echo "실행: $GAME  [np2kai]  $WHAT · 부팅=$BOOT · $NP2"
  echo "  $DRIVES"
  echo "  설정·ROM: $CFGDIR  (np21kai.cfg · font.rom · bios.rom …)"
  # 폰트 ROM 이 없으면 np2kai 는 **작업 폴더의 `default.ttf`** 로 본체 폰트를 그린다(실측:
  # `Couldn't load 12 points font from ./default.ttf`). 레포의 네오둥근모(새턴용, OFL)를 놓아 준다 —
  # 이 게임은 대사·메뉴를 제 폰트로 RAM 에 올리므로 본체 폰트가 닿는 건 부팅 경고·시스템 문구뿐이다.
  if [ ! -f "$CFGDIR/font.rom" ] && [ ! -f "$CFGDIR/font.bmp" ] && [ ! -f "$CFGDIR/FONT.ROM" ]; then
    if [ ! -f "$RUN/default.ttf" ] && [ -f "$REPO/shared/fonts/neodgm.ttf" ]; then
      cp "$REPO/shared/fonts/neodgm.ttf" "$RUN/default.ttf"
    fi
    echo "  ⓘ font.rom 이 없어 본체 폰트는 default.ttf(네오둥근모)로 그린다 — 진짜 ROM 은 $CFGDIR 에" >&2
  fi
  if [ "$BOOT" = event ]; then
    echo "  ┌ 새 게임 순서 ────────────────────────────────────────────────────"
    echo "  │ ⑴ 오프닝이 끝나면 「プログラムディスクをドライブ1に…」 안내가 뜬다"
    echo "  │ ⑵ **\\ 한 번**(백슬래시 · Return 위) — FDD1 이 event ↔ program 으로 바뀐다(우리 패치)"
    echo "  │    패치가 없으면 F11 메뉴 ▸ FDD ▸ FDD1 ▸ Open... ▸ program.d88 (같은 폴더가 열린다)"
    echo "  │ ⑶ RETURN → 第1章 이 시작된다"
    echo "  │ ⑷ 한 번 세이브해 두면 다음부터는 --program 으로 바로 LOAD 하면 된다"
    echo "  └──────────────────────────────────────────────────────────────"
  fi
  echo "  🎮 방향키 = 텐키 8/2/4/6(이동) · ⌘R/F10 = 재시작 · F5/F7 = 퀵세이브/로드 · ⌘L = 마우스 잠금 토글(시작은 안 잡음)"
  echo "  ⏩ 빨리감기: \` 토글 · Tab 누르는 동안 · \\ = 디스크 교체   (전부 우리 패치 — 없으면 F11 메뉴)"
  echo "  🖥  창 크기: ⌥- / ⌥+ · ⌥1~4 · 소리: ⌥M (단계 넷, 지금 ${WIN_SIZE:-2}단계)   ⚠ 에뮬 해상도가 아니라 창만 바뀐다"
  # 첫 창 크기는 환경변수로 넘긴다 — 패치가 창을 만든 직후 이걸 읽는다(`--size N` → 여기).
  export NP2KAI_WIN_SIZE="${WIN_SIZE:-2}"
  cd "$RUN"
  DONE=0
  finish() { [ "$DONE" = 1 ] && return 0; DONE=1; save_out; }
  trap 'finish; exit 130' INT
  trap 'finish; exit 143' TERM
  RC=0
  # shellcheck disable=SC2086
  "$NP2" "$@" $EXTRA > "$RUN/np2kai.log" 2>&1 || RC=$?
  finish
  [ "$RC" = 0 ] || echo "  ⚠ np2kai 가 $RC 로 끝났다 — 로그: $RUN/np2kai.log" >&2
  exit $RC
fi

# 🔴 SDL1 시절 매퍼가 실행 폴더에 남아 있으면 SDL2 가 그걸 집는다(기본 이름이 같다).
#    이름만 바꿔 비켜 둔다 — 지우지 않는 건 사람이 손댄 배치일 수도 있어서다.
if [ -f "$RUN/mapper-dosbox-x.map" ]; then
  head -1 "$RUN/mapper-dosbox-x.map" | grep -q "^\[SDL1\]" && [ "$ENGINE" = SDL2 ] && {
    mv "$RUN/mapper-dosbox-x.map" "$RUN/mapper-dosbox-x.map.sdl1-old"
    echo "  ⓘ SDL1 시절 매퍼를 비켜 뒀다(형식이 달라 SDL2 에서 키가 죽는다): mapper-dosbox-x.map.sdl1-old"
  }
fi

CONF="$RUN/pc98.conf"
# ⚠ conf 는 사본이라 손대도 된다. 다만 **템플릿이 바뀌면 다시 만든다** — 표식이 없으면
#   옛 conf 라 보고 갈아엎는다(안 그러면 새 키보드 설정이 옛 사용자에게 안 간다).
CONF_MARK="# tmpl:9"
if [ ! -f "$CONF" ] || ! grep -q "^$CONF_MARK\$" "$CONF" 2>/dev/null; then
  # 🔴 **따옴표 친 히어독**이라야 한다(머리말 함정 ⑷) — 주석의 백틱이 실행되면 안 된다.
  #   그래서 표식만 따로 찍고 본문은 통째로 리터럴이다.
  printf '%s\n' "$CONF_MARK" > "$CONF"
  cat >> "$CONF" <<'CONFEOF'
# PC-98 실행 설정 — 이 파일은 사본이라 마음대로 고쳐도 된다(--refresh 로 되돌린다).
# 🔴 **로그를 남긴다.** 여기 이게 없어서 오래 장님이었다 — 앱 번들(`open`)로 띄우면 stdout
#    이 아무 데도 안 가서 「디스크가 물렸나 · 부팅했나」를 볼 길이 자체가 없었다.
#    dosbox.sh 의 DOS 템플릿은 진작 logfile 을 두고 있었는데 여기만 빠져 있었다(2026-08-31).
[log]
logfile=pc98.log
[sdl]
autolock=false
# 🔴 **이 줄 하나가 맥의 키보드를 살린다.** DOSBox-X 기본값은 auto 이고, 맥에선 그게
#    저수준 스캔코드 경로로 붙는다 — 그 경로는 **입력 모니터링 권한**이 필요해서, 권한이
#    없으면 창은 멀쩡히 뜨고 **키보드만 죽는다**(dosbox/game.conf.tmpl 이 같은 이유로
#    이미 못 박아 뒀는데 여기만 빠져 있었다 — 2026-08-31).
#    ⚠ 리눅스에선 auto 여도 먹어서 **맥에서만 갈린다** — 실측: 같은 conf 로 리눅스는
#      키 입력 전후 화면이 170,901px 바뀌고(= 먹는다) 안 보내면 16px 다.
usescancodes=false
fullscreen=false
CONFEOF
  # ⚠ **창 크기 한 줄만 히어독 밖에서 쓴다** — 위 히어독은 따옴표로 닫혀 있어야 하고
  #   (주석 속 `$`·백틱이 터진다, 이 파일 머리의 ⑷) 그러면 `$(…)` 도 안 풀린다.
  #   그래서 값이 드는 이 줄만 갈라 낸다. **[sdl] 절 한복판이라 순서가 중요하다.**
  printf 'windowresolution=%s\n' "$(winsize_wh "${WIN_SIZE:-2}")" >> "$CONF"
  cat >> "$CONF" <<'CONFEOF'
# opengl 이라야 windowresolution 스케일링이 먹는다
output=opengl
priority=highest,highest
# 메뉴 바를 띄운다 — 디스크 교체(Drive ▸ A:)·매퍼 편집기가 여기 있다.
showmenu=true
# 🔴 **매퍼 파일은 엔진 사이에 호환되지 않는다**(루트 CLAUDE.md·dosbox.sh 가 이미 못 박았다).
#    SDL1 이 쓴 `[SDL1]` 파일을 SDL2 가 읽으면 바인딩을 못 찾아 **키가 죽는다.** 그래서
#    파일 이름에 엔진을 박는다. 실제로 이 게임 실행 폴더에 SDL1 시절 매퍼가 남아 있었다.
#    ⚠ 이 자리는 **게임 폴더 밖**이다 — `--refresh` 로 사본을 갈아도 키 배치는 살아야 한다.
mapperfile=@MAPPER@
[dosbox]
machine=pc98
memsize=14
# 🔴 **호스트 키를 Ctrl+Alt 로 못 박는다.** 기본값(`mapper`)은 맥/리눅스에서 **F12** 인데,
#    맥은 F12 가 시스템에 먹히거나 `fn` 을 같이 눌러야 해서 「단축키가 안 먹는다」가 된다.
#    이 게임은 오프닝 끝에 **디스크 교체가 필수**라(호스트키+O) 그 키가 확실해야 한다.
#    ⇒ 교체는 **Ctrl+Alt(⌃⌥)+O**.
hostkey=ctrlalt
[cpu]
core=normal
cputype=386
cycles=fixed 8000
# 오프닝이 5분이라 빨리 감기가 필요하다 — 그건 이제 ` 한 번이다(매퍼가 건다).
# 여기 turbo 는 **`--shot` 전용 초기값**이고, 실행마다 아래에서 다시 정한다.
turbo=false
# 🔴 **키를 눌러도 빨리감기가 안 풀린다**(유저 요청 2026-09-03 · DOS 와 같은 거동).
#   종전엔 `true` 였다 — 오프닝 빨리감기가 안내창에서 저절로 풀리라고 둔 것인데,
#   그 대가로 **` 토글이 첫 키 입력에 죽었다**(DOS 는 안 죽는다). 자동 해제는 포기하고
#   토글을 온전하게 둔다 — 오프닝이 끝나면 ` 를 한 번 눌러 제 속도로 돌아온다.
# ⚠ `stop turbo after second` 로 시간제한을 걸어 볼 수도 있는데, 그건 **수동 토글에도
#   똑같이 걸린다**(실측: 8초로 두니 손으로 켠 빨리감기도 8초 만에 꺼졌다). 그래서 0 이다.
stop turbo on key=false
stop turbo after second=0
[render]
aspect=false

# 🔴 **PC-98 은 키보드 컨트롤러가 PC/AT 와 다르다.** machine=pc98 이면 auto 도 이걸 고르지만
#    명시해 둔다 — 값이 화면에 보이면 「설정했나」를 다시 안 묻는다.
[keyboard]
controllertype=pc98
[pc98]
# ⚠ **여긴 강제하지 않는다.** 종전엔 force ibm=true 로 박아 뒀는데 그건 추측이었고, 키가
#    안 먹는 증상은 그대로였다(2026-08-31). DOSBox-X 기본값은 auto 이고, 실측 로그가
#    "Host keyboard layout is now us (US English)" 를 찍으니 auto 가 이미 US 배열을 고른다.
#    문서가 못 박아 둔 한계도 있다 — 「키보드를 BIOS 로 읽는 앱·게임에서만」 듣는다.
#    일본어(JIS) 자판을 쓸 때만 --jis 로 뒤집는다.
pc-98 force ibm keyboard layout=@IBM@
pc-98 force JIS keyboard layout=@JIS@

[autoexec]
CONFEOF
fi
# 자판 배열만 실행마다 맞춘다(--jis). conf 를 통째로 다시 안 만들려고 자리표시자를 친다.
# ⚠ `--scancodes` 를 `-set "sdl usescancodes=true"` 로 넘기지 않는다 — `open --args` 를
#   거치면 인자 경계가 흐려져 **먹었는지 아닌지도 알 수 없다**(종전엔 따옴표가 깨져 아예
#   안 먹었다). conf 에 박으면 파일을 열어 눈으로 확인할 수 있다.
if [ "$SCAN" = 1 ]; then _scan=true; else _scan=false; fi
sed_i() { sed -i '' "$@" 2>/dev/null || sed -i "$@"; }
MAPDIR=$(dirname "$RUN")
mkdir -p "$MAPDIR"
MAPPER="$MAPDIR/mapper-$(echo "$ENGINE" | tr 'A-Z' 'a-z').map"
sed_i -e "s|^mapperfile=.*|mapperfile=$MAPPER|" "$CONF"

# ── 🎮 키 배치(매퍼) ────────────────────────────────────────────────────────
# 🔴 **이 게임은 이동을 텐키(숫자패드)로만 받는다.** 실측(리눅스, 인게임): 텐키를 누르면
#    화면이 18,526px 바뀌고 **방향키·윗줄 숫자·HJKL 은 427px = 무반응**이다. PC-98 게임의
#    관례라 에뮬 잘못이 아닌데, 맥북엔 텐키가 없어 「키보드가 안 먹는다」로 보인다.
#    ⚠ 방향키가 **에뮬까지는 잘 온다** — 유저 실측: ⌃⌥+→ 로 Turbo 가 걸린다(=매퍼가 받았다).
#      그러니 고칠 자리는 호스트·SDL 이 아니라 **매퍼**다.
# 🔴 **부분 매퍼는 금지다**(2026-09-03 실측). 매퍼 파일이 있으면 DOSBox-X 는 기본 바인딩을
#    **통째로 지우고** 그 파일만 읽는다 — 한 줄짜리 파일을 물렸더니 `dir` 조차 안 찍혔다
#    (같은 조건에서 매퍼 없이 띄우면 찍힌다). 그래서 **DOSBox-X 자신이 저장한 완전한
#    파일**에 우리 줄만 덧쓴다. 그 파일을 만드는 게 `--mapper` 다.
# ⚠ 숫자는 **SDL 스캔코드**다(SDL1 의 키심이 아니다 — 그래서 두 엔진의 매퍼가 호환이 안 된다).
#      53=` 43=Tab 79=→ 80=← 81=↓ 82=↑ 92/94/96/90=텐키 4/6/8/2
# ⚠ ` · Tab · \ 는 **게스트 바인딩을 지운다** — 순수 단축키로 만든다. 게임에 새 나갈 일이
#   없어야 안심하고 아무 데서나 누른다(디스크 교체가 게임 중에 새면 그건 사고다).
# 🔴 **손가락은 레포 전체가 같아야 한다** — 정본은 `dosbox.sh` 머리말(2026-08-22 실측):
#      hand_speedlock  = **홀드**(누르는 동안) → **Tab**
#      hand_speedlock2 = **토글**             → **`**
#    mednafen 도 같다(` 토글 · Tab 홀드). 이름만 보고 speedlock 을 토글로 짐작하면 정확히
#    반대다 — DOS 쪽에서 한 번 뒤집어 봤다가 되돌린 자리다. 여기서도 한 번 거꾸로 걸었다.
#    (2026-09-03 실측으로 확정: ` 를 누르면 ON, 그 뒤 글자를 쳐도 ON 이 유지된다.)
# 💿 **디스크 교체(swapimg)를 맨 `\` 에도 건다**(기본 ⌃⌥O 는 그대로 남긴다).
#   🔴 **자동화는 길이 다 막혔다**(2026-09-03 전부 실측):
#      ⑴ 부팅 드라이브를 비켜 가기 — `imgmount 0 program` 뒤 `boot event.d88` 은
#         **"Floppy image(s) already mounted"** 로 거절한다. 부팅 이미지는 드라이브를 먹는다.
#      ⑵ Program 으로 새 게임 — 안 된다. Program 부팅 화면은 **LOAD·サクサク 뿐**이고
#         슬롯 10칸이 전부 비어 있다. 새 게임은 Event 를 거쳐야만 한다.
#      ⑶ 드라이브 배치를 바꾸기 — 3장·2드라이브라 어떻게 물려도 교체가 **정확히 한 번**
#         남는다. 게임이 화면으로 직접 요구하는 것도 그래서다.
#      ⑷ 설정으로 자동 교체 — dosbox-x 에 그런 설정이 없다(바이너리 문자열 전수 확인).
#      ⑸ 대신 눌러 주기 — 맥은 합성 키 입력에 손댈 권한이 없고, 「지금이 그 순간인가」는
#         화면을 봐야 아는데 그 화면도 못 읽는다.
#   ⇒ 그래서 **안 만나게** 하는 쪽으로 갔다 — 세이브가 있으면 Program 으로 띄운다(위 💾 절).
#      교체를 만나는 건 **새 게임을 시작하는 딱 한 번**이다.
#   ⇒ 그래서 **화음을 없애 한 키로** 만든다. `\` 는 맥북 Return 바로 위라 누르기 쉽고,
#      게스트 바인딩을 지워 두므로 게임엔 절대 안 샌다.
patch_mapper() {
  _m=$1
  awk '
    /^hand_speedlock /  { print "hand_speedlock \"key 43\" \"key 79 host\" "; next }
    /^hand_speedlock2/  { print "hand_speedlock2 \"key 53\" "; next }
    /^hand_swapimg/     { print "hand_swapimg \"key 49\" \"key 18 host\" "; next }
    /^key_grave /       { print "key_grave "; next }
    /^key_tab /         { print "key_tab "; next }
    /^key_backslash /   { print "key_backslash "; next }
    /^key_kp_8 /        { print "key_kp_8 \"key 96\" \"key 82\" "; next }
    /^key_kp_2 /        { print "key_kp_2 \"key 90\" \"key 81\" "; next }
    /^key_kp_4 /        { print "key_kp_4 \"key 92\" \"key 80\" "; next }
    /^key_kp_6 /        { print "key_kp_6 \"key 94\" \"key 79\" "; next }
    { print }
  ' "$_m" > "$_m.new" && mv "$_m.new" "$_m"
}
# 엔진이 다른 매퍼는 **키를 통째로 죽인다** — 비켜 둔다(지우지 않는 건 손댄 배치일 수 있어서).
if [ -f "$MAPPER" ] && ! head -1 "$MAPPER" | grep -q "^\[$ENGINE\]"; then
  mv "$MAPPER" "$MAPPER.other-engine"
  echo "  ⓘ 엔진이 다른 매퍼를 비켜 뒀다: $(basename "$MAPPER").other-engine"
fi
# 있으면 **매번** 우리 줄을 덧쓴다(멱등이다). 손으로 딴 키를 더해 둬도 그건 안 건드린다.
[ -f "$MAPPER" ] && patch_mapper "$MAPPER"
sed_i -e "s/^usescancodes=.*/usescancodes=$_scan/" "$CONF"
# ⚠ 오프닝은 **키로 못 건너뛴다**(ESC·Return·space 를 300초 내내 눌러 봤다 — 다른
#   기종판과 달리 이 Event 디스크는 안 넘어간다). 빨리감기가 유일한 수단인데, 그건 이제
#   **` 한 번**이다(토글 · 키를 쳐도 안 풀린다). 그래서 종전의 `--fast` 는 없앴다 —
#   손으로 켤 수 있는 걸 켜 주는 스위치는 손잡이만 는다(유저 지적 2026-09-03).
# 🔴 **딱 하나 예외가 `--shot` 이다** — 헤드리스라 누를 손이 없다. 거기서만 켜고 뜬다
#   (실측: 안내창까지 290초 → 40초. `--wait` 을 5분으로 늘리는 것보다 이쪽이 싸다).
if [ -n "$SHOT" ]; then _turbo=true; else _turbo=false; fi
sed_i -e "s/^turbo=.*/turbo=$_turbo/" "$CONF"
if [ "$JIS" = 1 ]; then _ibm=false; _jis=true; else _ibm=auto; _jis=false; fi
sed_i -e "s/^pc-98 force ibm keyboard layout=.*/pc-98 force ibm keyboard layout=$_ibm/" \
      -e "s/^pc-98 force JIS keyboard layout=.*/pc-98 force JIS keyboard layout=$_jis/" "$CONF"

# ── 디스크 셋 — 🔴 **3장인데 드라이브는 2개다** ─────────────────────────────
# 그래서 드라이브 1 에는 **여러 장을 교체 가능하게** 물린다(`imgmount 1 a.d88 b.d88`).
# 게임이 다음 디스크를 요구하면 **Ctrl+F4**(디스크 교체)로 넘긴다.
#   · `--event`  = 처음부터 — 오프닝이 끝나면 게임이 **Program** 을 찾는다. 그래서 드라이브1
#                  첫 장이 Program 이다. 종전엔 여기에 Scenario 만 물려 뒀는데, 그러면
#                  오프닝이 끝나도 다음으로 못 넘어간다(2026-08-31 유저 실측).
#   · 기본(program) = 이어하기 — 곧바로 LOAD 메뉴. 드라이브1 은 세이브 매체인 Scenario.
# ⚠ Scenario 는 게임이 **쓰는** 매체다 — 반드시 `.local/` 사본이어야 한다(머리말 함정 ⑶).
# 🔴 **디스크 교체가 필수다** — 게임이 오프닝 끝에 직접 요구한다(2026-08-31 화면으로 확인):
#      「プログラムディスクをドライブ1に · シナリオディスクをドライブ2に
#        セットして【RETURN】キーを押してください。」
#    PC-98 의 「드라이브1·2」는 DOSBox-X 의 **imgmount 0·1** 이다. 오프닝은 드라이브1에
#    Event 를 물고 도니까, 끝나면 그 자리를 **Program 으로 갈아야** RETURN 이 먹는다.
#    그래서 드라이브 0 에 event·program 을 **교체 가능한 세트**로 물린다.
#    ⚠ 이걸 모르면 「RETURN 을 눌러도 아무 일이 없다」로 보인다 — 실제로 그렇게 헤맸다.
case "$BOOT" in
  event)   D0="event.d88 program.d88"; D1="scenario.d88" ;;
  program) D0="program.d88";           D1="scenario.d88" ;;
esac

# 헤드리스 판단 — dev(LXC)엔 화면이 없다. Xvfb 로 띄우면 스크린샷까지 된다.
# 🔴 **맥은 `DISPLAY` 가 없어도 화면이 있다**(X 가 아니라 Quartz). 그걸 안 가르면 맥에서
#    늘 헤드리스로 가 「Xvfb 가 없다」로 죽는다 — 유저 지적 2026-08-31.
if [ "$HEADLESS" = auto ]; then
  case "$(uname -s)" in
    Darwin) HEADLESS=0 ;;
    *) [ -n "${DISPLAY:-}" ] && HEADLESS=0 || HEADLESS=1 ;;
  esac
fi
if [ "$HEADLESS" = 1 ]; then
  command -v Xvfb >/dev/null 2>&1 || {
    echo "⛔ 화면도 Xvfb 도 없다 — apt-get install xvfb" >&2; exit 1; }
  DISPLAY=${PC98_DISPLAY:-:99}
  export DISPLAY
  xdpyinfo >/dev/null 2>&1 || { Xvfb "$DISPLAY" -screen 0 1024x768x24 >/dev/null 2>&1 & sleep 2; }
  echo "  헤드리스: DISPLAY=$DISPLAY"
fi

# 🔴 맥은 **앱 번들 채널**로 띄운다 — 실행파일을 직접 부르면 키가 안 먹는다(유저 실측).
# ⚠ **실행파일이 PATH 에 있어도 번들을 따로 찾는다.** 처음엔 「우리가 찾은 실행파일이
#   번들 안이면」으로만 봤는데, brew **formula** 로 깔면 `dosbox-x` 가 PATH 에 있어
#   번들 감지가 아예 안 걸렸다 — 그래서 계속 실행파일을 직접 불렀다(2026-08-31).
find_bundle() {
  for d in "${DOSBOX_APP:-}" /Applications/dosbox-x.app "$HOME/Applications/dosbox-x.app" \
           /Applications/DOSBox-X.app "$HOME/Applications/DOSBox-X.app"; do
    [ -n "$d" ] || continue
    [ -d "$d" ] && { printf '%s' "$d"; return 0; }
  done
  return 0
}
case "$DOSBOX" in
  *.app/Contents/MacOS/*) BUNDLE=${DOSBOX%%.app/Contents/MacOS/*}.app ;;
  *) BUNDLE=$(find_bundle) ;;
esac
# 🔴 **앱 번들 채널은 SDL1 일 때만 쓴다.** 종전엔 「맥이면 무조건 번들」이라, formula(SDL2)가
#   깔려 있어도 굳이 번들(SDL1)을 찾아 띄웠다 — 그게 게임 키가 안 먹던 자리다.
#   SDL2 는 실행파일로 곧장 띄운다(번들 자체가 없다). cwd 를 우리가 정할 수 있으니
#   `-defaultdir` 곡예도 필요 없다.
if [ "$APP" = auto ]; then
  if [ "$(uname -s)" = Darwin ] && [ "$ENGINE" = SDL1 ] && [ -n "$BUNDLE" ]; then APP=1; else APP=0; fi
fi
# ⚠ `[ … ] && …` 로 쓰지 않는다 — 조건이 거짓이면 그 줄이 non-zero 라 `set -e` 가
#   **조용히 스크립트를 죽인다**(루트 CLAUDE.md 셸 절 · 이 레포가 하루에 셋을 밟았다).
if [ "$APP" = 1 ] && [ -z "$BUNDLE" ]; then
  echo "⛔ --app 인데 앱 번들을 못 찾았다 — DOSBOX_APP 으로 알려 준다." >&2
  exit 1
fi

# 🔴 입력 소스 함정 — **경고가 아니라 강제다.** 한글 입력기가 붙은 채로 뜨면 DOSBox-X 는
#    조합 확정에서 SIGSEGV 로 죽고(크래시 리포트 셋으로 확정), 그 전에도 조합 중인 키가
#    게임까지 안 온다. 근거와 되돌리는 법은 ime.sh 머리말.
. "$HERE/ime.sh"
ensure_ascii_input
# 🔴 그리고 **도는 내내** 지킨다 — 입력 소스는 전역이라 딴 데서 한글을 치면 돌아온다.
#    돌아온 채로 에뮬 창을 클릭하면 **방향키만 죽는다**(Enter·ESC·Shift 는 멀쩡하다).
guard_ascii_input "dosbox-x"

# 실행 채널을 한 자리로 모은다 — `--shot`·`--kbtest`·본 실행이 같은 길로 떠야 잰 값이 쓸모가
# 있다(다른 길로 재면 「테스트는 되는데 게임은 안 된다」가 나온다).
# 🔴 `open -n` 이다. `-n` 이 없으면 **이미 도는 dosbox-x 가 앞으로 나올 뿐 인자가 안 간다**
#    (실측 2026-08-31 — 위 머리말 ⑵).
launch() {                      # 인자 = dosbox-x 인자. 백그라운드로 띄우고 PID 를 잡지 않는다
  if [ "$APP" = 1 ]; then
    # ⚠ `open -a` 는 **cwd 를 안 물려준다** — conf 는 절대경로로 주고 상대경로(이미지 파일)는
    #   `-defaultdir` 로 맞춘다. 안 그러면 마운트가 통째로 빈다(DOS 쪽에서 실제로 겪었다).
    # ⚠ `-W` 는 앱이 끝날 때까지 **블록**한다 — 세이브를 떼어 두려면 종료를 봐야 한다.
    #   동기화가 꺼져 있으면 예전처럼 바로 반환해 터미널을 놓아 준다.
    open -n ${LAUNCH_WAIT:+-W} -a "$BUNDLE" --args -defaultdir "$RUN" "$@"
  else
    "$DOSBOX" "$@"
  fi
}

WAY="$ENGINE · 실행파일 $DOSBOX"
if [ "$APP" = 1 ]; then WAY="$ENGINE · 앱 번들 $BUNDLE"; fi
# ⚠ 맥에서 키가 안 먹는데 **실행파일**로 떴다면 번들이 없다는 뜻이다 — 그때 알려 준다.
# ⚠ 종전엔 「맥에서 실행파일로 뜨면 키가 안 먹을 수 있다」고 경고했는데, **SDL2 실행파일이
#   이제 권장 경로**라 그 경고는 거꾸로였다. 걱정할 자리는 SDL1 쪽이다.
if [ "$(uname -s)" = Darwin ] && [ "$ENGINE" = SDL1 ]; then
  echo "  ⚠ SDL1 로 떴다 — **부팅된 게임이 키를 못 받고**, 한글 입력이 들어오면 죽는다." >&2
  echo "     brew install dosbox-x   (cask 가 아니라 formula — SDL2 다)" >&2
fi

# ── 🔧 키보드 계측 ──────────────────────────────────────────────────────────
# 「키가 안 먹는다」는 화면만 봐서는 **에뮬까지 안 오는 것**과 **게임이 안 받는 것**이 안
# 갈린다. 고치는 자리가 아예 다른데도 그렇다. 그래서 게임 대신 PC-98 DOS 프롬프트를 띄우고
# `copy con` 으로 타이핑을 **호스트 파일**에 받는다 — 파일에 글자가 있으면 키는 들어온 것이다.
if [ "$KBTEST" = 1 ]; then
  KB="$RUN/kbtest"
  rm -rf "$KB"; mkdir -p "$KB"
  # ⚠ 게스트에서 **호스트 파일이 생기는 것**을 신호로 쓴다. `copy con` + Ctrl+Z 는 종결이
  #   까다로워서(F6 을 모르면 못 끝낸다) 그냥 `md ok` 한 줄로 바꿨다 — 글자키와 Enter 를
  #   동시에 본다. 신호가 오는 즉시 우리가 에뮬을 닫으므로 창을 손으로 닫을 일도 없다.
  cat > "$KB/kb.conf" <<KBEOF
[log]
logfile=$KB/kb.log
[sdl]
autolock=false
usescancodes=false
fullscreen=false
windowresolution=$(winsize_wh "${WIN_SIZE:-2}")
output=opengl
[dosbox]
machine=pc98
memsize=14
[keyboard]
controllertype=pc98
[autoexec]
mount c "$KB"
c:
cls
echo ================================================
echo   KEYBOARD TEST -- type:   md ok      then ENTER
echo ================================================
KBEOF
  echo "🔧 키보드 계측 ($WAY)"
  echo "   창이 뜨면 ⑴ 창을 한 번 클릭하고  ⑵  md ok  를 치고 Enter."
  echo "   (창은 알아서 닫는다. 90초 안에 신호가 없으면 실패로 친다.)"
  launch -conf "$KB/kb.conf" -defaultdir "$KB" &
  # 🔴 **뜨기를 먼저 기다린다.** `open -n` 은 곧바로 돌아오므로 여기서 바로 살아 있나를 물으면
  #    아직 시작 전이라 「사용자가 닫았다」로 오판하고 즉시 실패를 찍는다(내 리그가 그랬다).
  _i=0
  while [ $_i -lt 25 ]; do
    pgrep -f "dosbox-x.*kbtest" >/dev/null 2>&1 && break
    sleep 1; _i=$((_i + 1))
  done
  if ! pgrep -f "dosbox-x.*kbtest" >/dev/null 2>&1; then
    echo "⛔ dosbox-x 가 뜨지 않았다 — 로그: $KB/kb.log" >&2; exit 1
  fi
  _i=0; _hit=0
  while [ $_i -lt 90 ]; do
    if [ -d "$KB/OK" ] || [ -d "$KB/ok" ]; then _hit=1; break; fi
    pgrep -f "dosbox-x.*kbtest" >/dev/null 2>&1 || break   # 사용자가 먼저 닫았다
    sleep 1; _i=$((_i + 1))
  done
  pkill -f "dosbox-x.*kbtest" 2>/dev/null || true
  echo
  if [ "$_hit" = 1 ]; then
    echo "✅ 키가 에뮬까지 **들어온다**(글자키·Enter 둘 다)."
    echo "   ⇒ 호스트 쪽은 문제가 없다. 남은 건 게임 쪽이다 —"
    echo "     ⚠ 이 게임의 **오프닝 프롤로그는 자동으로 넘어가고 키를 안 받는다**"
    echo "       (리눅스에서 60초간 Enter 를 계속 보낸 화면과 안 보낸 화면이 같았다)."
    echo "       프롤로그가 끝나 타이틀이 뜬 뒤에 눌러 본다."
  else
    echo "🔴 키가 에뮬까지 **안 들어온다**($KB 에 ok 가 안 생겼다)."
    echo "   ⇒ 호스트 쪽이다. 이 순서로 하나씩 — 각각 이 명령을 다시 돌려 확인한다:"
    echo "     ⑴ 창을 클릭했나 (터미널에 포커스가 남아 있으면 키가 그리로 간다)"
    echo "     ⑵ sh scripts/emu/pc98.sh $GAME --kbtest --no-app       (실행파일 채널)"
    echo "     ⑶ sh scripts/emu/pc98.sh $GAME --kbtest --scancodes    (저수준 경로)"
    echo "        └ 시스템 설정 > 개인정보 보호 및 보안 > 입력 모니터링 에서 dosbox-x 허용"
    echo "   로그: $KB/kb.log"
  fi
  exit 0
fi

# ── 🎮 --mapper : 키 배치를 한 번 만든다 ────────────────────────────────────
# DOSBox-X 는 매퍼를 **편집기에서 Save 할 때만** 쓴다(명령줄에도 설정에도 저장 스위치가
# 없다 — 2026-09-03 확인: Main 메뉴엔 「Load mapper file…」뿐이고 Save 는 편집기 안에만
# 있다). 그래서 한 번은 사람 손이 든다. 대신 **네 빌드가 직접 쓴 완전한 파일**이라
# 판 차이로 조용히 어긋날 자리가 없다.
if [ "$GENMAP" = 1 ]; then
  echo "매퍼 만들기 — $ENGINE · $MAPPER"
  echo "  ┌ 순서 ─────────────────────────────────────────────────────────"
  echo "  │ ⑴ 곧 뜨는 키보드 그림 아래쪽의 \033[36mSave\033[0m 를 누른다"
  echo "  │ ⑵ 이어서 \033[36mExit\033[0m — 그러면 여기서 나머지를 자동으로 얹는다"
  echo "  └───────────────────────────────────────────────────────────────"
  cd "$RUN"
  launch -conf "$CONF" -startmapper
  _i=0
  while [ $_i -lt 300 ]; do
    [ -f "$MAPPER" ] && break
    _i=$((_i + 1)); sleep 1
  done
  if [ ! -f "$MAPPER" ]; then
    echo "⛔ Save 를 못 받았다(5분). 편집기에서 Save 를 눌렀는지 본다." >&2
    exit 1
  fi
  sleep 1
  patch_mapper "$MAPPER"
  echo "✅ 키 배치를 얹었다 — $MAPPER"
  echo "   · 방향키 ↑↓←→ → 텐키 8 2 4 6 (**이동**). 텐키도 그대로 산다"
  echo "   · Tab = 빨리감기(누르는 동안만) · \` = 빨리감기 토글 — DOS·mednafen 과 같은 손가락"
  echo "     ⚠ 토글은 **다음 키 입력에서도 풀린다**(PC-98 만 그렇다 — 오프닝 빨리감기 때문)"
  echo "   · \\ = 디스크 교체 (오프닝 끝의 그 자리 · ⌃⌥O 와 같다)"
  echo "   이제 그냥 실행하면 된다:  sh scripts/emu.sh $GAME"
  exit 0
fi

echo "실행: $GAME  [dosbox-x pc98]  $WHAT · 부팅=$BOOT · $WAY"
echo "  드라이브 0=$D0 · 1=$D1"
if [ "$BOOT" = event ]; then
  # ⚠ 한 번 겪으면 아는 절차지만 모르면 **막힌 걸로 보인다.** 실행할 때마다 적어 준다.
  echo "  ┌ 새 게임 순서 ────────────────────────────────────────────────────"
  echo "  │ ⑴ 오프닝이 끝나면 「プログラムディスクをドライブ1に…」 안내가 뜬다"
  echo "  │ ⑵ **디스크를 Program 으로 간다** — \033[36m\\\\\033[0m 한 번 (백슬래시 · Return 위)"
  echo "  │    ⌃⌥O 도 그대로 되고, 메뉴로도 된다: Drive ▸ A: ▸ \"Swap floppy drive\""
  echo "  │ ⑶ RETURN → 第1章 이 시작된다"
  echo "  │ ⑷ 한 번 세이브해 두면 다음부터는 --program 으로 바로 LOAD 하면 된다"
  echo "  │ 💡 오프닝은 제 속도로 약 5분이다. 창을 클릭하고 \033[36m\`\033[0m 를 한 번 누르면"
  echo "  │    빨리감기(토글)로 약 40초 — 키를 쳐도 안 풀리니 그대로 두면 된다."
  echo "  │ ⚠ ⑵ 를 건너뛰고 RETURN 만 누르면 **아무 일도 안 난다** — 리눅스도 같다"
  echo "  └──────────────────────────────────────────────────────────────"
fi
# 🔴 **이동은 텐키(숫자패드)다** — 방향키·윗줄 숫자·HJKL 은 전부 안 먹는다
#    (인게임 실측: 텐키 18,526px 변화 / 나머지 427px = 무반응). PC-98 게임의 관례다.
if [ -f "$MAPPER" ]; then
  echo "  🎮 방향키=텐키(이동) · Tab=빨리감기(홀드) · \` =빨리감기 토글"
  echo "     (토글은 다음 키 입력에서도 풀린다 — 오프닝 건너뛰기에 쓴다)"
else
  echo "  🔴 **이동은 텐키(숫자패드)뿐이다** — 맥북엔 텐키가 없어 방향키로는 못 움직인다."
  echo "     한 번만 만들어 두면 방향키·\`·Tab 이 다 붙는다(--refresh 로도 안 날아간다):"
  echo "       \033[36msh scripts/emu/pc98.sh $GAME --mapper\033[0m"
fi

# 🔴 `-fs none` 과 **드라이브 번호**가 둘 다 있어야 한다(머리말 함정 ⑴⑵).
if [ "$MEDIA" = fd ]; then
  # ⚠ `$D1` 은 **일부러 안 감싼다** — 여러 장을 공백으로 이어 한 `imgmount` 에 넘긴다.
  set -- -conf "$CONF" \
    -c "imgmount 0 $D0 -t floppy -fs none" \
    -c "imgmount 1 $D1 -t floppy -fs none" \
    -c "boot -l a"
else
  # 하드 이미지는 FAT 가 있다(설치본) — `-fs none` 을 쓰지 않는다.
  set -- -conf "$CONF" \
    -c "imgmount 2 disk.hdi -t hdd" \
    -c "boot -l c"
fi

cd "$RUN"
if [ -n "$SHOT" ]; then
  # ⚠ `--shot` 은 **X 도구 셋**에 기댄다(창을 지정해 찍어야 하므로). 맥엔 없다 —
  #   거기선 그냥 창을 보면 되니 조용히 흉내 내지 않고 시끄럽게 막는다.
  for t in import xdotool; do
    command -v "$t" >/dev/null 2>&1 || {
      echo "⛔ --shot 에는 $t 가 필요하다(X 환경 전용) — apt-get install imagemagick xdotool" >&2
      echo "   맥에선 --shot 없이 띄워 창을 직접 본다." >&2
      exit 1; }
  done
  # 🔴 **루트 창을 먼저 지운다.** Xvfb 의 루트는 지난 실행의 화면을 그대로 들고 있어서,
  #   새 창이 아직 안 그려졌으면 `import -window root` 가 **옛 화면을 찍는다**
  #   (실측 2026-08-30: 실패한 첫 실행의 콘솔 화면을 세 번 연속 찍었다).
  command -v xsetroot >/dev/null 2>&1 && xsetroot -solid black 2>/dev/null || true

  # shellcheck disable=SC2086
  "$DOSBOX" "$@" $EXTRA > "$RUN/boot.log" 2>&1 &
  DPID=$!
  sleep "$WAIT"

  # 창을 **우리가 띄운 프로세스의 것으로** 지정해 찍는다.
  # 🔴 이름으로 찾거나 루트를 찍으면 **남의 창·옛 화면**을 찍는다 — 세 번 속았다.
  #   그래서 못 찾으면 **찍지 않고 실패한다.** 조용히 엉뚱한 그림을 남기는 게 더 나쁘다.
  WID=
  i=0
  while [ $i -lt 20 ]; do
    WID=$(xdotool search --pid "$DPID" 2>/dev/null | tail -1 || true)
    [ -n "$WID" ] && break
    i=$((i + 1)); sleep 1
  done
  if [ -z "$WID" ]; then
    kill "$DPID" 2>/dev/null || true
    echo "⛔ 우리가 띄운 dosbox 창을 못 찾았다 — 화면을 안 찍는다(로그: $RUN/boot.log)" >&2
    exit 1
  fi
  import -window "$WID" "$SHOT"
  kill "$DPID" 2>/dev/null || true

  # 🔴 **마운트가 됐는지 확인한다.** 안 그러면 「디스크를 못 연 콘솔 화면」을 찍어 놓고
  #   성공한 줄 안다 — 실제로 세 번 그랬다. d88 을 읽으면 로그에 트랙 줄이 쏟아진다.
  if ! grep -q "^LOG: D88" "$RUN/boot.log" 2>/dev/null; then
    echo "⛔ 디스크가 마운트되지 않았다 — 화면은 콘솔이다. 로그: $RUN/boot.log" >&2
    exit 1
  fi
  echo "  화면: $SHOT  (로그: $RUN/boot.log)"
else
  # ⚠ 실행파일로 띄우면 DOSBox-X 가 초기 로그를 **stdout 으로** 쏟는다(conf 의 logfile 은
  #   그 뒤부터다). 터미널을 덮으니 파일로 보낸다 — 안 뜰 때 볼 자리는 여기다.
  if [ "$APP" != 1 ]; then echo "  로그: $RUN/pc98.log · $RUN/stdout.log"; fi
  # 💾 **Ctrl+C 로 끊거나 DOSBox 가 비정상 종료해도 세이브는 떼어 둔다** — 진행분을 잃는
  #    게 이 흐름에서 제일 나쁜 결과다(dosbox.sh 와 같은 모양).
  LAUNCH_WAIT=1
  DONE=0
  finish() { [ "$DONE" = 1 ] && return 0; DONE=1; save_out; }
  trap 'finish; exit 130' INT
  trap 'finish; exit 143' TERM
  RC=0
  # shellcheck disable=SC2086
  if [ "$APP" = 1 ]; then
    launch "$@" $EXTRA || RC=$?
  else
    launch "$@" $EXTRA >> "$RUN/stdout.log" 2>&1 || RC=$?
  fi
  finish
  exit $RC
fi
