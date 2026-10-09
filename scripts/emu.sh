#!/bin/sh
# 게임 하나를 **알맞은 실행기로** 띄운다 — 세이브 동기화까지. 이게 유일한 실행 입구다.
#
#   sh scripts/emu.sh                     # 목록에서 골라 실행
#   sh scripts/emu.sh ps1                 # 그 플랫폼만 추려서 고른다
#   sh scripts/emu.sh ss-ed1+2            # 바로 실행 (mednafen ss)
#   sh scripts/emu.sh pce-ed1 --orig      # 빌드는 빼고 원본만 (문안 대조)
#   sh scripts/emu.sh dos-ed2             # DOSBox-X 로 위임
#   sh scripts/emu.sh pc98-ed1            # np2kai 로 위임 (--dosbox 면 DOSBox-X PC-98 모드)
#                                         #   원본·빌드는 pc98.sh 가 목록으로 묻는다
#   sh scripts/emu.sh <게임> <파일>       # 이미지를 직접 지정
#   sh scripts/emu.sh --list              # 목록만 (비대화형)
#
#     --orig     빌드가 있어도 **원본**을 띄운다 (원문·정발 대조용)
#     --no-sync  세이브 동기화를 끈다
#     --no-keys  키 배치 맞추기를 건너뛴다(기본은 맞춘다 — mednafen_keys.py)
#     --no-video 영상 규격 맞추기를 건너뛴다(기본은 맞춘다 — mednafen_video.py).
#     --size N   창 크기 1 매우 작음 · 2 작음(기본) · 3 보통 · 4 큼
#                mednafen 은 설정으로, np2kai 는 `NP2KAI_WIN_SIZE` 로 받는다.
#                ⚠ 실행 중에는 **⌥- / ⌥+**(한 단계씩) · **⌥1~4**(바로 지정).
#                   실행기 셋이 같은 손가락이다(X 는 우리 매퍼가 문다).
#                   ⌥1~4(단계를 바로)는 mednafen·np2kai 만 — X 엔 그 이벤트가 없다
#                ⌘1~4 로 **실행 중에도** 바꾸려면 `sh scripts/emu/mednafen-build.sh` 를 한 번 돌린다
#                ⚠ 화면을 끄는 게 아니라 **cfg 되돌리기**를 끈다
#     그 밖의 인자는 실행기에 그대로 넘어간다 (`-video.fs 1` 처럼)
#
# ── 왜 실행기가 하나인가 (유저 확정 2026-08-21) ───────────────────────────────
# 「에뮬레이터를 하나로 통일하면 일관성이 생기지 않나」에서 출발했는데, 세어 보니 소장
# 원본 30벌 중 mednafen 이 덮는 건 **10벌**이다. 나머지(DOS·PC88·PC98·X68000·FM-TOWNS·
# MSX·PSP·Win)는 구조적으로 다른 실행기가 필요하고, 그중 PC88 ED2·PC98 ED1 은
# `docs/ports-survey.md` 판정이 「⭐ED2 의 문」·「유망」이라 **로드맵 상위가 이미 밖에 있다.**
# 그래서 통일하는 축을 **에뮬레이터가 아니라 실행기 인터페이스**로 잡았다 — 무엇으로 뜨든
# 치는 명령과 세이브가 사는 곳은 하나다.
#
# **게임→시스템 매핑은 새 규칙이 아니다.** `originals/<지역>/<플랫폼>-ed<N>` 규약에서
# 플랫폼 접두사를 그대로 읽는다(`ss-ed1+2` → `ss`). 목록을 손으로 드는 자리가 없다.
#
# ⚠ **PS1 정본은 mednafen 이다**(유저 확정 2026-08-21, 종전 DuckStation 결정을 뒤집는다).
#   근거는 UI 가 아니라 셋이다 — ⑴ 세이브 파일명 규약이 OS 무관 동일해 dev 와 그대로 맞고
#   ⑵ emucap 어댑터가 **같은 바이너리**라 에이전트가 dev 에서 잡은 버그가 맥에서 1:1 로
#   재현되며 ⑶ brew 가 이 맥에서 소스로 빌드하니 OS 천장에 안 걸린다(Geargrafx 는 SDL3 가
#   macOS 14 API 를 불러 Ventura 인 이 맥에서 실행 자체가 안 됐다 — 2026-08-21 실측).
#   **`scripts/duckstation.sh` 는 지웠다**(유저 확정 2026-08-21) — 정본이 아닌 실행기를 위해
#   빌드 고르기·카드 동기화를 한 벌 더 유지할 값이 없다. DuckStation 앱 자체는 남겨 둔다:
#   화면이 이상할 때 다른 에뮬에서 보면 「우리 패치 탓」과 「에뮬 탓」이 갈리는데, 그때는
#   `sh scripts/emu/ps1-card.sh ps1-ed1+2 export` 로 카드를 넘기고 앱에서 이미지를 직접 연다.
#
# ⚠ **세이브를 게임별 칸으로 가른다** — `~/.mednafen/sav/<게임>/`. mednafen 은 원래 모든
#   기종의 세이브를 `sav/` 한 곳에 쌓는데, 그러면 「이 게임 것만 올린다」를 파일명 접두사로
#   추측해야 한다(DuckStation 쪽에서 실제로 그러고 있다). 칸을 가르면 그 추측이 없어지고
#   `sync-saves.sh` 의 leaf 와 1:1 이 된다. `-filesys.path_sav` 로 실행마다 지정한다.
# ⚠ **처음 켜기 전에 dev 쪽 세이브를 leaf 자리로 한 번 옮긴다.** dev 의 mednafen 세이브는
#   아직 `~/.mednafen/sav/` 에 평평하게 쌓여 있는데(칸 나누기는 이 스크립트가 도입한 것이다)
#   동기화 정본 자리는 `~/save/<게임>/` 이다. 안 옮기고 켜면 **빈 세이브가 새로 생기고 그게
#   더 최신이라 dev 로 올라가** 진행분을 덮는다(`sync-saves.sh` 의 `-u` 는 로컬이 새로우면
#   안 당긴다). 게임마다 한 번이면 끝난다 —
#     ssh dev 'mkdir -p ~/save/ss-ed1+2 && cp -n ~/.mednafen/sav/The_Legend*I\&II.* ~/save/ss-ed1+2/'
#
# ⚠ leaf 하나에 **카드 두 규약이 산다** — PS1 은 DuckStation 시절 `.mcd` 가 이미 올라가 있고
#   mednafen 은 `.mcr` 을 쓴다. 서로 안 읽지만 부딪히지도 않으니 그대로 둔다(2차 의견용
#   DuckStation 이 살아 있는 한 양쪽이 다 필요하다).
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
# 캡처는 세 실행기 모두 **메인 트리 `.local/work/capture/<게임>/`** 로 모은다(마스터 10-06 「저장 경로 일원화」).
#   워크트리에서 띄워도 메인 트리로 간다(.local 은 워크트리에 안 따라온다 — git-common-dir 로 찾는다).
#   `.local/cache` 가 아니라 바로 아래라 **지우는 칸이 아니다** — 찍은 것은 사람이 모은 자료다.
capture_dir() {   # $1 = 게임 칸 이름 → 만들어서 절대경로를 찍는다
  _cd=$(git -C "$REPO" rev-parse --git-common-dir 2>/dev/null || true)
  case "$_cd" in "") _root=$REPO ;; /*) _root=$(cd "$_cd/.." && pwd) ;; *) _root=$(cd "$REPO/$_cd/.." && pwd) ;; esac
  mkdir -p "$_root/.local/work/capture/$1" && printf '%s' "$_root/.local/work/capture/$1"
  return 0
}
HELPERS="$HERE/emu"                   # 실행기 본체·기전은 여기 모여 있다
SYNCSH="$HELPERS/sync-saves.sh"
PY_BIN="$REPO/.venv/bin/python"       # ⚠ 여기서 실패할 수 있는 명령을 쓰지 않는다(set -e)
[ -x "$PY_BIN" ] || PY_BIN=python3
. "$HERE/lib/select.sh"        # 화살표 키 선택 UI
. "$HERE/emu/ime.sh"           # 한글 입력 소스 함정 (기종 무관)

MEDBASE=${MEDNAFEN_HOME:-$HOME/.mednafen}

# ⚠ **한 번만 물어본다.** `runner_of` 는 목록의 줄마다 불리는데(30줄), 거기서 매번
#   서브프로세스를 띄우면 목록이 느려진다. 답은 실행 중에 안 바뀐다.
DOSENGINE=$(sh "$HELPERS/dosbox.sh" --which 2>/dev/null || echo dosbox)

usage() {
  echo "사용법: $0 [<게임>|<플랫폼>] [--orig] [--no-sync] [--no-keys] [--no-video] [--size 1-4] [파일] [실행기 인자...]" >&2
  echo "        $0 --list          목록만" >&2
}

# 플랫폼 접두사 → 실행기. 「없다」도 값이다 — 조용히 아무거나 띄우지 않는다.
runner_of() {
  case "$1" in
    ps1) echo "mednafen psx" ;;
    ss)  echo "mednafen ss" ;;
    pce) echo "mednafen pce" ;;
    sfc) echo "mednafen snes" ;;
    md)  echo "mednafen md" ;;
    dos)  echo "${DOSENGINE:-dosbox}" ;;
    pc98) echo "${PC98_EMU:-np2kai} (--dosbox 로 DOSBox-X)" ;;
    psp) echo "ppsspp" ;;
    *)   echo "— 미정 ($(blocked_by "$1"))" ;;
  esac
}

# 「왜 아직 못 붙였나」를 붙여 둔다 — 목록에서 고르면 튕겨 나오는데, 이유를 안 적으면
# 스크립트가 덜 된 건지 원래 안 되는 건지 사람이 알 수가 없다(유저 지적 2026-08-21).
# ⚠ 아래 셋은 **스크립트로 못 여는 게 아니라 머신 ROM(BIOS)이 있어야** 열린다. 우리가
#   배포할 수 없는 물건이라 소장본에서 손으로 놓기 전에는 붙여도 안 뜬다.
# 🔴 **pc98 은 여기 있다가 나갔다**(2026-08-30) — 「MAME 머신 ROM 필요」가 맞는 말이었지만
#   **그 길만 있는 게 아니었다.** DOSBox-X 의 `machine=pc98` 은 롬셋 없이 뜬다(실측: 영웅전설
#   PC-98 오프닝). 「ROM 이 필요하다」는 **그 에뮬레이터의 사정**이지 기종의 사정이 아니다 —
#   나머지 넷도 다시 볼 값이 있다.
# ✅ **그 「다시 보기」를 했다 — DOSBox-X 로는 넷 다 안 된다**(2026-09-03, dosbox-x 2026.08.02).
#   ⑴ `-machine` 이 아는 기종에 **pc88·msx·x68k 는 아예 없다.** 전부 PC/AT 계열 + pc98 이다
#      (amstrad · hercules · mcga · pcjr · tandy · vgaonly · svga_* · pc98/pc9801/pc9821 · fm_towns).
#   ⑵ `fm_towns` 는 이름만 있다 — 바이너리가 스스로 이렇게 말한다:
#      "FM Towns emulation not yet implemented. It's currently just a stub for future development."
#   ⇒ pc98 이 롬 없이 뜬 건 **DOSBox-X 가 PC-98 BIOS 를 합성해 주기 때문**이지 일반화되는
#     성질이 아니었다. 넷은 여전히 아래 에뮬 + 그 기종 ROM 이 있어야 한다.
# ⚠ fmt 는 ROM 말고 **덤프 형식**도 걸린다 — 소장본이 `*.mfm`(HxC) · KryoFlux `*.raw` 라
#   플럭스 덤프다. 어느 에뮬도 그대로는 안 읽고 먼저 이미지로 변환해야 한다.
blocked_by() {
  case "$1" in
    msx)  echo "openMSX — MSX2 BIOS 필요(번들 C-BIOS 는 디스크 부팅 불가) · 디스크 5장" ;;
    pc88) echo "quasi88 · MAME — PC-8801 ROM 필요" ;;
    x68k) echo "MAME x68000 — IPL/폰트 ROM 필요" ;;
    fmt)  echo "Tsugaru · MAME — FM TOWNS BIOS 필요 · 소장본이 플럭스 덤프(mfm/raw)라 변환도 든다" ;;
    win)  echo "Wine — brew cask 가 2026-09-01 비활성 예정, UTM VM 검토" ;;
    *)    echo "실행기 미정" ;;
  esac
}

# 실행기 바이너리 — 없으면 `need_tool` 이 묻고 깐다.
# ⚠ **끝을 `return 0` 으로 닫는다.** `[ -x … ] && printf` 로 끝내면 못 찾았을 때 함수가
#   non-zero 를 반환하고, `BIN=$(ppsspp_bin)` 이 그 값을 물려받아 **set -e 가 거기서
#   스크립트를 죽인다** — 아무 메시지도 없이. 오늘 세 번 밟았다(2026-08-21).
ppsspp_bin() {
  for b in PPSSPPSDL ppsspp PPSSPPQt; do
    p=$(command -v "$b" 2>/dev/null || true)
    if [ -n "$p" ]; then printf '%s' "$p"; return 0; fi
  done
  b="/Applications/PPSSPPSDL.app/Contents/MacOS/PPSSPPSDL"
  [ -x "$b" ] && printf '%s' "$b"
  return 0
}

# 플랫폼별로 **띄울 수 있는 파일**만 후보로 든다. CD 기종에서 `.bin` 을 후보에 넣으면 트랙
# 파일이 목록을 뒤덮고(ss-ed3 은 디스크 둘에 트랙이 다섯이다), 롬 기종에서 빼면 아무것도
# 안 잡힌다 — md-ed1/2·sfc-ed1/2 는 **zip 째로** 들어 있다(mednafen 이 zip 을 직접 읽는다).
exts_of() {
  case "$1" in
    ps1|ss|pce) echo "m3u cue ccd toc" ;;
    sfc|md)     echo "zip sfc smc smd md gen bin" ;;
    psp)        echo "iso cso chd" ;;
    *)          echo "m3u cue zip iso bin" ;;
  esac
}

# mednafen 이 요구하는 펌웨어. 없으면 부팅 도중에 죽는데, 그때 메시지가 불친절하다.
firmware_of() {
  case "$1" in
    psx) echo "scph5500.bin scph5501.bin scph5502.bin" ;;
    ss)  echo "sega_101.bin mpr-17933.bin" ;;
    pce) echo "syscard3.pce" ;;
    *)   echo "" ;;
  esac
}

# 소장 원본이 있는 게임만 목록에 든다 — 없는 걸 고르게 하면 고른 뒤에 실패한다.
# ⚠ **지역이 달라도 게임은 하나다** — `jp/pce-ed1` 과 `us/pce-ed1` 이 둘 다 있으면 목록에
#   `pce-ed1` 이 두 번 떴다(마스터 2026-09-27). 이미지는 게임을 고른 **다음**에 고르므로
#   여기선 이름만 모은다(`sort -u`).
games() {
  for d in "$REPO"/originals/*/*/; do
    [ -d "$d" ] && basename "$d"
  done | sort -u
}

# ── 고르기 ──────────────────────────────────────────────────────────────────
# 인자 없이 부르는 게 제일 흔한 쓰임이라(유저 요청 2026-08-21) 목록에서 골라 들어간다.
# 조작은 `scripts/lib/select.sh` — ↑↓ 이동, Enter 선택.
# ⚠ 하나뿐이면 묻지 않는다. ⚠ 파이프·CI 처럼 tty 가 없으면 묻는 대신 시끄럽게 실패한다 —
#   대화형 프롬프트가 자동 실행에서 멈춰 서는 게 제일 나쁜 실패다.
row_game() {
  _r=$(runner_of "${2%%-*}")
  if [ "$3" = 1 ]; then printf '\033[36m❯ %-12s %s\033[0m\n' "$2" "$_r"
  else                  printf '  %-12s \033[2m%s\033[0m\n' "$2" "$_r"; fi
}
row_file() {
  if [ "$3" = 1 ]; then printf '\033[36m❯ %s\033[0m\n' "$(basename "$2")"
  else                  printf '  %s\n' "$(basename "$2")"; fi
}

choose() {                      # $1=제목 $2=줄 렌더 함수 · 나머지=항목 → 고른 값은 stdout
  _title=$1; _render=$2; shift 2
  [ $# -eq 0 ] && return 1
  [ $# -eq 1 ] && { printf '%s' "$1"; return 0; }
  if ! has_tty; then
    echo "⛔ 후보가 여럿인데 고를 수가 없다(비대화형) — 인자로 지정한다:" >&2
    # 라벨은 화면용이니 떼고 **그대로 붙여 넣을 수 있는 값**만 보여 준다.
    for _it in "$@"; do echo "     ${_it#*"$TAB"}" >&2; done
    return 2
  fi
  SELECT_RENDER=$_render
  select_option "$_title" "$@"
  _rc=$?
  SELECT_RENDER=
  return $_rc
}

# ⚠ **없는 도구를 말없이 깔지 않는다 — 묻고 깐다**(유저 문의 2026-08-21). 자동 설치를 안 하는
#   이유는 안전이 아니라 **흐름**이다: 「게임 켜자」로 시작한 명령이 갑자기 몇 분짜리 빌드로
#   변하면 그게 더 나쁘다(mame 는 특히 무겁다). 그렇다고 안내만 하고 끝내면 명령을 다시 쳐야
#   하니, 물어보고 그 자리에서 깐다. 비대화형이면 명령만 알려주고 멈춘다.
#   ⚠ 설치 목록을 따로 두지 않는 이유는 DRY 다 — 「게임→실행기→패키지」가 두 벌이 되면 어긋난다.
need_tool() {                   # $1=바이너리 $2=brew 패키지
  command -v "$1" >/dev/null 2>&1 && return 0
  echo "⛔ $1 이 없다." >&2
  if has_tty && command -v brew >/dev/null 2>&1; then
    confirm_yes "   brew install $2 — 지금 깔까? (y/n) " || exit 1
    brew install "$2" || exit 1
  else
    echo "   brew install $2" >&2
    exit 1
  fi
}

# ── 이미지 고르기 ───────────────────────────────────────────────────────────
# **원본과 빌드 칸 전부를 한 목록에 올린다**(유저 요청 2026-08-21). 종전에는 「현재 브랜치
# 빌드가 있으면 그것, 없으면 원본」이라 **다른 브랜치 빌드는 고를 길이 아예 없었다** —
# 빌드는 꼬리표(브랜치)별로 갈려 있는데(`work/build/<꼬리표>/`) 정작 그걸 못 쓴 셈이다.
#
#   원본     Legend of Heroes I & II, The - Eiyuu Densetsu (Japan).cue
#   빌드 ed1-qa  Eiyuu Densetsu (KR).cue
#   빌드 ed2-wip Eiyuu Densetsu (KR).cue
#
# ⚠ 커서는 **현재 브랜치 빌드**에 놓고 시작한다 — 목록 순서는 원본이 먼저지만 QA 대상은
#   대개 지금 굴리는 빌드다. 눈에 보이는 자리라 잘못 눌러도 바로 안다.
TAB=$(printf '\t')

# 「라벨<탭>경로」줄을 뱉는다. 라벨은 화면용이고 경로가 값이다.
images_in() {
  _label=$1; _dir=$2
  # ⚠ 호출자가 결과를 줄 단위로 받으려고 IFS 를 개행으로 바꿔 둔다 — 그대로 두면 확장자
  #   목록이 안 쪼개져 `*.zip sfc smc ...` 라는 글로브 하나가 된다(실측). 여기서 되돌린다.
  # 🔴 **바꾼 IFS 를 반드시 되돌린다**(마스터 실측 2026-09-17, md·sfc). 종전 주석은
  #   「`$(...)` 안이라 서브셸이고 바꿔도 호출자에 안 샌다」였는데 **틀렸다** — 서브셸 밖으로는
  #   안 새도 **같은 서브셸 안의 `candidates()` 로는 샌다.** 그러면 그 뒤의
  #   `for _d in $(build_dirs)` 가 **개행이 아니라 공백으로만** 쪼개서, 빌드 칸이 **둘 이상이면
  #   전부 한 덩어리**가 되고 **하나도 안 잡힌다.** 칸이 하나일 땐 멀쩡히 돌아 눈치채기 어렵다
  #   — md 는 칸이 셋(빌드+글꼴비교 둘), sfc 는 둘이 되면서 **원본만 뜨기 시작했다.**
  _oifs=$IFS
  IFS=' '
  for _e in $(exts_of "$PLAT"); do
    for _f in "$_dir"/*."$_e"; do
      [ -f "$_f" ] || continue
      # ⚠ 실패한 빌드는 후보에서 뺀다 — 그 잔재를 정상으로 오해하는 게 이 레포의 1급
      #   사고다(루트 CLAUDE.md 「빌드 규율」). 조용히 빼지 않고 왜 없는지 알린다.
      if [ -f "$_f.failed" ] || [ -f "${_f%.*}.bin.failed" ]; then
        echo "⚠ 실패 표식이 있어 목록에서 뺐다: $_label / $(basename "$_f")" >&2
        continue
      fi
      printf '%s\t%s\n' "$_label" "$_f"
    done
  done
  IFS=$_oifs            # 🔴 되돌린다 — 위 주석 참조. 안 되돌리면 빌드 칸 둘 이상이 통째로 뭉개진다
}

candidates() {
  for _r in jp kr us; do
    [ -d "$REPO/originals/$_r/$GAME" ] && images_in "원본" "$REPO/originals/$_r/$GAME"
  done
  [ "$ORIG" = 1 ] && return 0
  for _d in $(build_dirs); do
    images_in "빌드 $(basename "$_d")" "$_d"
  done
}

# 🔴 **빌드는 메인 트리에만 있지 않다.** 세션마다 워크트리에서 굽고 산출물을 거기 그대로 둔다
#   (루트 `CLAUDE.md` 「빌드 산출물은 워크트리 안에 그대로 둔다」) — `pull-build.sh` 가 같은
#   이유로 양쪽을 훑는다. 여기만 메인 트리를 보고 있어서 **빌드를 받아 놓고도 원본이 떴다**
#   (마스터 실측 2026-09-15, ps1-ed3). 후보가 0개면 조용히 원본만 남아 자동 선택되므로
#   에러도 안 난다 — 이 레포의 1급 사고(낡은/엉뚱한 이미지를 정상으로 오해)와 같은 부류다.
#   ⚠ 메인 트리 칸이 워크트리로 가는 **심볼릭 링크**인 경우가 있어(실측: 둘) 같은 칸이 두 줄로
#   보인다 ⇒ **실경로로 중복을 접는다.**
build_dirs() {
  _seen=
  for _d in "$REPO/games/$GAME_DIR/work/build"/*/ \
            "$REPO/.claude/worktrees"/*/"games/$GAME_DIR/work/build"/*/; do
    [ -d "$_d" ] || continue
    _rp=$(cd "$_d" && pwd -P) || continue
    case "$_seen" in *"|$_rp|"*) continue ;; esac
    _seen="$_seen|$_rp|"
    printf '%s\n' "${_d%/}"
  done
}

# ⚠ 라벨을 `%-14s` 로 줄맞춤하지 않는다 — printf 의 폭은 **바이트**라 한글이 섞이면 어긋난다
#   (「원본」은 6바이트인데 화면에선 4칸이다). 꼬리표 길이도 제각각이라 어차피 못 맞춘다.
# 🔴 **빌드 지문(sha1 앞 12자)을 목록과 실행 줄에 보인다**(마스터 2026-09-28) — pull-build 표·
#   파일서버·웹 실행기와 **같은 규칙**이다: 이미지 파일의 sha1(`.cue` 면 그것이 가리키는 첫 파일).
#   「어느 빌드를 보고 있나」가 이 레포에서 하루를 태우는 축이라 고르는 자리에서 보여야 한다.
#   ⚠ CD 이미지는 수백 MB 라 한 번 재는 데 한두 초 — (경로·크기·시각)으로 캐시한다
#     (`.local/cache/emu-sha1.tsv`). 목록은 다시 그릴 때마다 줄을 부르므로 **캐시만 읽는다.**
SHA_CACHE="$REPO/.local/cache/emu-sha1.tsv"
_img_file() {
  _f=$1
  case "$_f" in
    *.cue|*.CUE)
      _b=$(sed -n 's/^ *FILE *"\(.*\)".*/\1/p' "$_f" | head -1)
      [ -n "$_b" ] && _f="$(dirname "$_f")/$_b" ;;
  esac
  printf '%s' "$_f"
  return 0
}
_sha_key() { printf '%s\t%s\t%s' "$1" "$(wc -c < "$1" | tr -d ' ')" "$(date -r "$1" +%s 2>/dev/null)"; }
sha_cached() {   # 캐시에 있으면 찍고, 없으면 아무것도 안 찍는다
  _f=$(_img_file "$1"); [ -f "$_f" ] || return 0
  _k=$(_sha_key "$_f")
  [ -f "$SHA_CACHE" ] && awk -F'\t' -v k="$_k" '($1"\t"$2"\t"$3)==k{print $4; exit}' "$SHA_CACHE"
  return 0
}
img_sha() {      # 캐시에 없으면 재서 넣는다
  _v=$(sha_cached "$1"); [ -n "$_v" ] && { printf '%s' "$_v"; return 0; }
  _f=$(_img_file "$1"); [ -f "$_f" ] || return 0
  _v=$(shasum -a 1 "$_f" 2>/dev/null | cut -c1-12)
  [ -n "$_v" ] || return 0
  mkdir -p "$(dirname "$SHA_CACHE")"
  printf '%s\t%s\n' "$(_sha_key "$_f")" "$_v" >> "$SHA_CACHE"
  printf '%s' "$_v"
  return 0
}

row_image() {
  _lb=${2%%"$TAB"*}; _pa=${2#*"$TAB"}
  _sh=; case "$_lb" in "빌드 "*) _sh=$(sha_cached "$_pa") ;; esac
  [ -n "$_sh" ] && _sh="  sha1 $_sh"
  if [ "$3" = 1 ]; then printf '\033[36m❯ %s · %s\033[0m\033[2m%s\033[0m\n' "$_lb" "$(basename "$_pa")" "$_sh"
  else                  printf '  \033[2m%s ·\033[0m %s\033[2m%s\033[0m\n' "$_lb" "$(basename "$_pa")" "$_sh"; fi
}

# ── 인자 ────────────────────────────────────────────────────────────────────
GAME=
case "${1:-}" in
  --list|-l) for g in $(games); do printf '  %-12s %s\n' "$g" "$(runner_of "${g%%-*}")"; done; exit 0 ;;
  -h|--help) usage; exit 0 ;;
  -*) ;;                                   # 게임 없이 옵션만 — 목록에서 고른다
  '') ;;
  *) GAME=$1; shift ;;
esac

ORIG=0; SYNC=1; KEYS=1; VIDEO=1; IMAGE=; EXTRA=""
for a in "$@"; do
  case "$a" in
    --orig) ORIG=1 ;;
    --no-sync) SYNC=0 ;;
    --no-keys) KEYS=0 ;;
    --no-video) VIDEO=0 ;;
    --size) shift; VIDEO_SIZE="${1:-2}" ;;
    --size=*) VIDEO_SIZE="${1#*=}" ;;
    *.cue|*.ccd|*.toc|*.m3u|*.zip|*.bin|*.iso|*.sfc|*.smc|*.smd|*.md|*.gen|*.pce)
      IMAGE=$a ;;
    *) EXTRA="$EXTRA $a" ;;                # 실행기 설정 덮어쓰기 등
  esac
done

# ── 게임 → 이미지 (Esc 로 되돌아온다) ────────────────────────────────────────
# 두 목록을 **고리로 묶는다**(유저 요청 2026-08-21). 한 번 고르면 못 돌아오면 잘못 들어갔을
# 때 명령을 처음부터 다시 쳐야 한다. 되돌아갈 자리가 있는 건 **목록에서 고른 경우**뿐이다 —
# 명령줄로 게임을 지정했으면 뒤가 셸이라 Esc 는 취소와 같아진다.
BACK=0                                # 게임을 목록에서 골랐나 = 되돌아갈 자리가 있나
[ -n "$GAME" ] || BACK=1

while :; do
  # 게임 이름이면 그대로, 플랫폼 이름이면 그 플랫폼만 추려서, 없으면 전부 놓고 고른다.
  if [ -z "$GAME" ]; then
    # shellcheck disable=SC2046
    GAME=$(choose "게임" row_game $(games)) || exit 1
  elif ! games | grep -qx "$GAME"; then
    CAND=$(games | grep "^$GAME-" || true)
    [ -n "$CAND" ] || { echo "⛔ 그런 게임도 플랫폼도 없다: $GAME  ($0 --list)" >&2; exit 1; }
    # shellcheck disable=SC2086
    GAME=$(choose "게임($GAME)" row_game $CAND) || exit 1
    BACK=0                            # 명령줄 필터라 여기가 첫 칸이다
  fi
  PLAT=${GAME%%-*}

  # ── 띄울 때마다 단축키를 찍는다 (마스터 요청 2026-09-17) ───────────────────
  # 기종마다 에뮬레이터가 다르고 **되는 것도 다르다.** 어디에 무엇이 있는지 외우고 있을 수가
  # 없으니 실행할 때마다 보여 준다.
  # 🔴 **여기 적힌 것은 전부 실제로 도는 것만이다.** 없는 기능을 「있다」고 찍으면 안 찍느니만
  #   못하다 — 이 레포에서 **글이 값을 대신한 자리**로 하루에 다섯 번 물렸다(2026-09-17).
  #   되감기는 mednafen 계열에만 있다. DOSBox-X·np2kai 엔 그 기능 자체가 없다.
  # ⚠ **정본은 여기가 아니다** — mednafen 은 `emu/mednafen_keys.py`, DOSBox-X 는
  #   `emu/dosbox/mapper-x.map`, PC-98 은 `emu/np2kai-keys.patch` 다. 여기는 그걸 사람이
  #   읽는 꼴로 보여 줄 뿐이라 **두 곳에 있는 지식**이다. 정본을 고치면 여기도 같이 고친다.
  # 🔴 **셋 다 ⌥ 조합이다**(마스터 2026-09-17). 창 크기 ⌥-/⌥+ · ⌥1~4 · 소리 ⌥M 이 이미 ⌥ 고,
  #   무엇보다 **DOS·PC-98 은 게임이 F 키를 쓴다** — 단독 F 키로 잡으면 게스트가 그 키를 못 받는다.
  #   ⚠ np2kai 는 기존 패치가 F5·F7·F10 을 이미 단독으로 가져다 쓰고 있다. 거기 더 얹지 않는다.
  keyhelp() {
    echo "── 단축키 ─────────────────────────────────────────────" >&2
    case "$1" in
      mednafen)
        echo "   Space 일시정지(⌥P 도 됨)    F9 캡처    ⌥B 되감기 ⚠ ⌥⇧B 로 먼저 켠다" >&2
        echo "   F5 저장        F7 불러오기    \` 빨리감기    Tab 누르는 동안 빨리감기" >&2
        echo "   ⌥F 뗀 뒤 3초 안에 패드 키 = 그 버튼 자동 연타(같이 누르지 않는다)    ⌥F 또는 아무 패드 키 = 끄기" >&2
        echo "   ⌘R 재시작    ⌥-/⌥+ 창 크기    ⌥1~4 크기 단계    ⌥M 소리" >&2
        ;;
      dos)
        echo "   ⌥P 일시정지    ⌥C 캡처    (되감기 없음 — DOSBox-X 에 그 기능이 없다)" >&2
        echo "   ⚠ 여긴 Space 가 안 된다 — 게임이 그 키를 쓴다" >&2
        echo "   Host+S 저장    Host+L 불러오기    Tab 빨리감기" >&2
        ;;
      pc98)
        echo "   ⌥P 일시정지    ⌥C 캡처    (되감기 없음 — np2kai 에 그 기능이 없다)" >&2
        echo "   ⚠ 여긴 Space 가 안 된다 — 게임이 그 키를 쓴다" >&2
        echo "   \` 빨리감기 토글    Tab 누르는 동안    \\ 디스크 교체    F5 저장    F7 불러오기" >&2
        ;;
      *) echo "   (이 기종은 아직 정리된 단축키가 없다)" >&2 ;;
    esac
    echo "───────────────────────────────────────────────────────" >&2
  }

  # ── PC-98 도 통째로 위임한다 ───────────────────────────────────────────────
  # 디스크가 3장이고 **파일 시스템이 없어**(`-fs none` · 드라이브 번호) 마운트 규약이
  # mednafen 계열과 아예 다르다. 사본·헤드리스·스크린샷까지 pc98.sh 가 안다.
  if [ "$PLAT" = pc98 ]; then
    # ⚠ `--orig` 를 **넘겨야 한다** — 위 인자 고리가 그걸 ORIG 로 먹어 EXTRA 에 안 남긴다.
    #   그래서 종전엔 `emu.sh pc98-ed1 --orig` 이 조용히 아무 일도 안 했다(2026-08-31).
    # ⚠ 「실행:」 줄은 pc98.sh 가 무엇을 띄우는지까지 알고 찍는다 — 여기서 또 찍지 않는다.
    set -- "$GAME"
    [ "$ORIG" = 1 ] && set -- "$@" --orig
    # ⚠ `--size` 도 위 고리가 먹으므로 되넘긴다 — np2kai·DOSBox-X 도 창 크기 단계를 받는다.
    [ -n "$VIDEO_SIZE" ] && set -- "$@" --size "$VIDEO_SIZE"
    keyhelp pc98
    # shellcheck disable=SC2086
    exec sh "$HELPERS/pc98.sh" "$@" $EXTRA
  fi

  # ── DOS 는 통째로 위임한다 ─────────────────────────────────────────────────
  # 사본 방식·CD 마운트·CNF 재작성까지 dosbox.sh 가 이미 다 한다. 흉내 내면 두 벌이 된다.
  if [ "$PLAT" = dos ]; then
    echo "실행: $GAME  [dosbox-x]"
    keyhelp dos
    # shellcheck disable=SC2086
    # ⚠ `--size` 는 위 고리가 먹으므로 되넘긴다 (DOSBox-X 는 conf 로 받는다).
    [ -n "$VIDEO_SIZE" ] && EXTRA="$EXTRA --size $VIDEO_SIZE"
    exec sh "$HELPERS/dosbox.sh" "${GAME#dos-}" $EXTRA
  fi

  MOD=$(runner_of "$PLAT" | sed -n 's/^mednafen //p')
  RUNNER=mednafen
  [ -n "$MOD" ] || case "$PLAT" in psp) RUNNER=ppsspp ;; *) RUNNER= ;; esac
  if [ -z "$RUNNER" ]; then
    echo "⚠ '$GAME' 은 아직 못 띄운다 — $(blocked_by "$PLAT")" >&2
    echo "   ROM·BIOS 를 originals 옆에 놓고 나서 runner_of() 에 붙인다." >&2
    [ "$BACK" = 1 ] && { GAME=; continue; }        # 목록으로 돌려보낸다
    exit 1
  fi

  # 🔴 **`originals` 의 이름과 `games/` 의 이름이 늘 같지는 않다**(실측 2026-09-15).
  #   합본은 `games/` 쪽만 합쳐져 있다 — 예전 `games/ps1-ed3+4` 가 그랬다(`originals/jp/ps1-ed3` · `ps1-ed4`).
  #   10-09 롬 단위로 `games/ps1-ed3` 로 갈랐지만 `ps1-ed1+2`(한 디스크 합본)처럼 `+` 이름은 남을 수 있다.
  #   게임 목록은 **originals 에서 뽑으므로**(위 `games()`) `ps1-ed3` 이 그대로 GAME 이 되고,
  #   그러면 `games/ps1-ed3/work/build` 라는 **없는 칸**을 보게 된다 ⇒ 후보에 원본만 남고
  #   **빌드를 받아 놓고도 원본이 뜬다.** 조용히 틀리는 쪽이라 한참 못 알아챈다.
  #   ⇒ 합본 이름을 펼쳐 주인을 찾는다. 새 규약이 아니라 **이미 있는 이름 규칙**을 읽는 것이다.
  game_dir_for() {
    if [ -d "$REPO/games/$1" ]; then printf '%s' "$1"; return 0; fi
    for _g in "$REPO"/games/*/; do
      _n=${_g%/}; _n=${_n##*/}
      case "$_n" in *+*) ;; *) continue ;; esac
      _head=${_n%%+*}          # ps1-ed1+2 → ps1-ed1
      _pre=${_head%-*}         # ps1-ed1   → ps1
      if [ "$1" = "$_head" ]; then printf '%s' "$_n"; return 0; fi
      for _x in $(printf '%s' "${_n#*+}" | tr '+' ' '); do
        if [ "$1" = "$_pre-ed$_x" ]; then printf '%s' "$_n"; return 0; fi
      done
    done
    printf '%s' "$1"; return 0            # 못 찾으면 원래 이름 — 아래가 「빌드 없음」으로 알린다
  }
  GAME_DIR=$(game_dir_for "$GAME")
  [ "$GAME_DIR" = "$GAME" ] || echo "   빌드 칸: games/$GAME_DIR (합본)"
  # (빌드 칸은 `build_dirs()` 가 메인 트리 + 워크트리를 함께 훑는다)
  [ -n "$IMAGE" ] && break                         # 파일을 직접 줬으면 고를 것이 없다

  TAG=$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null | sed 's#.*/##; s#[^A-Za-z0-9._-]#-#g')
  OLDIFS=$IFS; IFS='
'
  # shellcheck disable=SC2046
  set -- $(candidates)
  IFS=$OLDIFS
  if [ $# -eq 0 ]; then
    echo "⚠ 실행할 이미지가 없다 — originals/*/$GAME 도 빌드도 없다" >&2
    [ "$BACK" = 1 ] && { GAME=; continue; }
    exit 1
  fi

  # 🔴 **빌드가 하나도 없으면 원본이 조용히 자동 선택된다** — 후보가 원본 하나뿐이면 고를 게
  #   없어 그대로 뜨고, 에러도 경고도 안 난다. 마스터가 실측으로 두 번 물렸다
  #   (2026-09-15 ps1-ed3 · 2026-09-17 md-ed1). 둘 다 「받았는데 원본이 뜬다」였는데 원인이
  #   달랐다 — 앞은 **워크트리를 안 훑어서**(`build_dirs()` 가 고쳤다), 뒤는 **그 머신에 빌드가
  #   아예 없어서**다. `git pull` 은 소스만 가져온다. 빌드 산출물은 gitignore 라 안 따라오고
  #   `pull-build.sh` 로 따로 받아야 한다.
  # ⚠ 막지는 않는다 — 원본을 띄우는 건 정당한 용도다(대조군). 대신 **조용하지 않게** 한다.
  if [ "$ORIG" != 1 ]; then
    _has_build=0
    for _c in "$@"; do
      case ${_c%%"$TAB"*} in "빌드 "*) _has_build=1; break ;; esac
    done
    if [ "$_has_build" = 0 ]; then
      echo "⚠ 빌드가 없다 — 지금 뜨는 건 **원본**이다 (games/$GAME_DIR/work/build 가 비었다)" >&2
      echo "   이 머신에서 구웠다면: 워크트리 안까지 보는지 확인" >&2
      echo "   다른 머신에서 구웠다면: sh scripts/pull-build.sh ${GAME%%-*}" >&2
    fi
  fi

  # 현재 브랜치 빌드가 목록에 있으면 커서를 거기에 놓고 시작한다.
  # 🔴 **커서 기본값은 원본이 아니라 빌드여야 한다**(마스터 실측 2026-09-17, md-ed1).
  #   종전엔 「현재 브랜치와 같은 꼬리표의 빌드」만 찾았다. 그런데 **QA 머신은 늘 `main` 에
  #   서 있다** — 소스만 pull 받고 빌드는 `pull-build.sh` 로 받으니 브랜치를 갈 이유가 없다.
  #   그러면 `빌드 main` 은 없고 커서가 1번(=원본)에 남아, **Enter 만 치면 원본이 뜬다.**
  #   「받았는데 안 된다」의 정체가 이것이다 — 목록엔 빌드가 멀쩡히 있었다.
  # ⇒ 세 단계로 고른다: ① 현재 브랜치 꼬리표 ② 그 게임 이름 꼬리표 ③ 아무 빌드.
  #   ⚠ 꼬리표는 브랜치명을 **살균한** 꼴이라(`ps1-ed1+2` → `ps1-ed1-2`) 게임 이름도 같은
  #   규칙으로 살균해서 맞춘다. 셋 다 없을 때만 원본에 남는다(그땐 위에서 경고가 나간다).
  _gsan=$(printf '%s' "$GAME_DIR" | sed 's#[^A-Za-z0-9._-]#-#g')
  _n=0; _hit_tag=; _hit_game=; _hit_any=
  for _c in "$@"; do
    _n=$((_n + 1))
    case ${_c%%"$TAB"*} in
      "빌드 $TAG")   [ -n "$_hit_tag" ]  || _hit_tag=$_n ;;
      "빌드 $_gsan") [ -n "$_hit_game" ] || _hit_game=$_n ;;
      "빌드 "*)      [ -n "$_hit_any" ]  || _hit_any=$_n ;;
    esac
  done
  SELECT_INDEX=${_hit_tag:-${_hit_game:-$_hit_any}}
  # 빌드 지문을 미리 잰다(처음 한 번만 느리다 — 그다음은 캐시)
  for _c in "$@"; do
    case ${_c%%"$TAB"*} in "빌드 "*)
      [ -n "$(sha_cached "${_c#*"$TAB"}")" ] || { printf '   sha1 재는 중 — %s\r' "$(basename "${_c#*"$TAB"}")"; img_sha "${_c#*"$TAB"}" >/dev/null; printf '\033[2K'; } ;;
    esac
  done
  if PICK=$(choose "이미지" row_image "$@"); then
    SELECT_INDEX=; IMAGE=${PICK#*"$TAB"}; break
  fi
  _rc=$?
  SELECT_INDEX=
  [ "$_rc" = 3 ] && [ "$BACK" = 1 ] && { GAME=; continue; }   # Esc = 게임 목록으로
  exit 1
done

[ -f "$IMAGE" ] || { echo "⛔ 이미지 없음: $IMAGE" >&2; exit 1; }
# ⚠ 실패한 빌드의 잔재를 정상으로 오해하는 게 이 레포의 1급 사고다(루트 CLAUDE.md 「빌드 규율」).
if [ -f "$IMAGE.failed" ] || [ -f "${IMAGE%.*}.bin.failed" ]; then
  echo "⛔ 실패 표식이 옆에 있다 — 이 이미지로 QA 하면 안 된다" >&2
  exit 1
fi

# ── PSP 는 mednafen 밖이다 ──────────────────────────────────────────────────
# ⚠ 세이브 동기화는 아직 안 건다 — PPSSPP 는 세이브가 자기 memstick 트리에 들어가서
#   자리 규약이 다르다. 먼저 「뜨는가」부터 확인하고, 쓸 일이 생기면 그때 붙인다(YAGNI).
if [ "$RUNNER" = ppsspp ]; then
  BIN=$(ppsspp_bin)
  [ -n "$BIN" ] || { need_tool PPSSPPSDL ppsspp; BIN=$(ppsspp_bin); }
  echo "실행: $(basename "$IMAGE")  [ppsspp]"
  # shellcheck disable=SC2086
  exec "$BIN" $EXTRA "$IMAGE"
fi

# ── 펌웨어 ──────────────────────────────────────────────────────────────────
FW=$(firmware_of "$MOD")
if [ -n "$FW" ]; then
  have=0
  for f in $FW; do [ -f "$MEDBASE/firmware/$f" ] && have=1; done
  [ "$have" = 1 ] || {
    echo "⚠ 펌웨어가 없다 — $MEDBASE/firmware/ 에 다음 중 하나가 있어야 한다: $FW" >&2
    echo "  (BIOS 는 커밋 금지다 — 소장본에서 손으로 둔다)" >&2
  }
fi

need_tool mednafen mednafen
# 🔴 한글 입력기는 mednafen 에서도 글자 키를 먹는다 — 경고가 아니라 바꿔 준다(ime.sh).
ensure_ascii_input

# ⚠ **키 배치를 실행 직전에 맞춘다**(유저 요청 2026-08-21). mednafen 은 종료할 때 cfg 를 다시
#   쓰고 게임 안 입력설정이 그 기종 배치를 통째로 덮는데, 여기서 맞춰 두면 **다음 실행에
#   저절로 되돌아온다.** 지금은 안 도는 게 확실한 자리다(아직 안 띄웠다) — 켜 둔 채 고치면
#   종료할 때 옛 값으로 덮인다. 바꾼 게 있을 때만 말한다.
if [ "$KEYS" = 1 ] && command -v python3 >/dev/null 2>&1; then
  python3 "$HELPERS/mednafen_keys.py" --quiet || true
fi

# ⚠ **영상도 같은 자리에서 되돌린다**(유저 요청 2026-09-02). 화면비·오버스캔·지역은 실기
#   규격이 정해 놓은 값인데 cfg 는 그걸 안 지켜 준다 — mednafen 이 종료할 때 다시 쓰고,
#   게임 안 설정으로도 덮인다. 실측으로 **SFC 는 8:7 로 홀쭉했고**(correct_aspect 0)
#   **PCE 는 좌우가 잘려 있었다**(h_overscan 0). 무엇을 실기로 보는지는 mednafen_video.py.
if [ "$VIDEO" = 1 ] && command -v python3 >/dev/null 2>&1; then
  python3 "$HELPERS/mednafen_video.py" --quiet --size "${VIDEO_SIZE:-2}" "$MOD" || true
fi

# ⚠ **`sound 0` 이면 알려준다.** 조용히 켜 주지 않는 이유는, 이 값이 **일부러 꺼 둔 것일 수
#   있어서**다(에이전트가 헤드리스로 돌릴 때가 그렇다). 소리가 안 나는데 이유를 모르는 게
#   제일 나쁘니 말은 해 준다 — 실제로 2026-08-21 에 「mednafen 은 원래 소리가 안 나나」로
#   한 번 물렸다. ⚠ mednafen 은 **종료할 때 cfg 를 다시 쓴다** — 켜 놓고 고쳐도 날아간다.
if [ "$(sed -n 's/^sound \([01]\)$/\1/p' "$MEDBASE/mednafen.cfg" 2>/dev/null)" = 0 ]; then
  echo "⚠ 설정에 소리가 꺼져 있다(sound 0) — 켜려면 mednafen 을 끈 상태에서" >&2
  echo "  sed -i '' 's/^sound 0\$/sound 1/' \"$MEDBASE/mednafen.cfg\"" >&2
fi

# ── 세이브 당기기 ───────────────────────────────────────────────────────────
# 칸을 게임별로 갈라 두었으니 leaf 와 디렉터리가 1:1 이다 — 접두사 추측이 없다.
SAVEREL="sav/$GAME"
SAVEDIR="$MEDBASE/$SAVEREL"
mkdir -p "$SAVEDIR"
if [ "$SYNC" = 1 ]; then
  if sh "$SYNCSH" probe; then
    sh "$SYNCSH" pull "$GAME" "$SAVEDIR"
  else
    echo "⚠ dev 에 못 붙는다 — 로컬 세이브로 진행한다(종료 후에도 안 올라간다)" >&2
    SYNC=0
  fi
fi

# 🔴 **새턴은 세이브 이름에 이미지 해시가 박힌다** — 그래서 **빌드를 갈면 세이브가 조용히
#   안 읽힌다**(타이틀에 `Continue` 가 안 뜨고 그냥 New Game 이 시작된다). 원판으로 모은
#   세이브를 한글패치 빌드에서 못 쓰는 것도 같은 이유다.
#   `ss_gameid.py` 가 세이브를 **해시가 안 붙은 이름**(`<이미지이름>.bkr`)으로 모아 둔다.
#   mednafen 은 그 이름을 **먼저** 찾아보고 있으면 그걸 쓰므로(`%M` 규칙), 그 뒤로는 빌드를
#   아무리 갈아도 세이브가 따라온다.
#   ⚠ **해시를 쫓지 않는다**(2026-08-29 전환). 종전엔 해시를 계산해 그 이름으로 사본을 떴는데,
#     계산이 한 자만 어긋나도 조용히 New Game 이 됐다 — 실제로 어긋나 있었다(트랙이 여럿인
#     이미지의 TOC 를 안 읽었다). 자세한 경위는 `ss_gameid.py` 머리말.
#   ⚠ **반드시 실행 전에** 한다. mednafen 은 저장할 때마다 이름을 다시 정하므로, 켜 둔 채
#     만들면 그 파일을 **지금 켜져 있는 쪽의 백업 RAM 이 덮는다**(스크립트가 막는다).
#   🔴 **다른 기종도 같다**(마스터 2026-09-27 — md 가 롬을 갈 때마다 세이브가 안 보였다).
#     md·pce·sfc·ps1 은 `save_unhash.py` 가 같은 규칙으로 **해시 없는 한 벌**로 모은다.
#     세션이 새 md5 이름으로 사본을 떠 두면(종전 관례) 그것도 후보로 집어 온다.
if [ "$MOD" = ss ]; then
  "$PY_BIN" "$HELPERS/ss_gameid.py" --fit "$SAVEDIR" "$IMAGE" || true
else
  "$PY_BIN" "$HELPERS/save_unhash.py" --fit "$SAVEDIR" "$IMAGE" || true
fi

# ── 실행 ────────────────────────────────────────────────────────────────────
# `-force_module` 을 박는 이유는 자동 판별이 못 미더워서가 아니라, **엉뚱한 이미지를 줬을 때
# 조용히 다른 기종으로 뜨는 걸 막으려는** 것이다. 여기선 시끄럽게 죽는 쪽이 옳다.
# 🔴 **어느 바이너리를 띄우나는 갈래보다 먼저 정한다**(유저 실측 2026-09-07).
#   창 크기 단축키가 든 우리 빌드를 먼저 찾고 없으면 시스템 것으로 간다 —
#   ⚠ 종전엔 이 판단이 **`SYNC != 1` 갈래 안에만** 있어서, 세이브를 쓰는 **평소 실행에서는
#     한 번도 안 쓰였다.** 유저가 굽고도 「창 크기가 안 된다」고 한 게 이것이다. 증상이
#     조용했던 이유는 시스템 mednafen 이 그 명령 이름을 **모를 뿐 멀쩡히 뜨기** 때문이다
#     (`mednafen_cfg.py` 가 「설정이 없다: command.scale_*」로 여섯 줄을 찍고 있었는데
#      그게 유일한 신호였다).
#   💡 그래서 **값을 한 곳에서 정하고 두 갈래가 같이 쓴다.** 갈래마다 다시 고르면 또 갈린다.
#   ⚠ 시스템 것에는 그 명령이 아예 없어 `--size` 인자만 듣는다(띄우기 전에 크기를 정한다).
#     만들려면 `sh scripts/emu/mednafen-build.sh` — 상태는 `--check`.
#   🔴 **그 빌드에 이 기종 모듈이 있는지 먼저 본다**(실측 2026-09-15). mednafen 의 configure 는
#     의존물이 없으면 **그 모듈만 조용히 끄고 빌드는 성공**한다 — 맥의 우리 빌드에 `ss` 가
#     그렇게 빠져 있었다. 그 상태로 `-force_module ss` 를 주면 에뮬레이터가
#     **「Unrecognized system "ss"!」**로 죽어서, 원인이 우리 빌드가 아니라 **에뮬레이터 쪽으로**
#     보인다. 두 기종(ss-ed3 · ss-ed1+2)에서 같은 증상을 겪고서야 갈렸다.
#     ⇒ 없으면 **시끄럽게 알리고 시스템 것으로 떨어진다**(창 크기 단축키는 잃지만 뜨긴 뜬다).
_has_mod() {  # $1=바이너리 · $2=모듈 — 있으면 0
  "$1" --help 2>&1 | sed -n 's/.*Emulation modules: *//p' | head -1 |
    tr ' ' '\n' | grep -qx "$2" && return 0
  return 1
}
SNAPDIR=$(capture_dir "$GAME")   # F9 캡처 자리 — 명령줄로만 준다(emucap 과 같이 쓰는 cfg 는 안 건드린다)
echo "  📷 F9 캡처 → $SNAPDIR"
MEDNAFEN_BIN="$REPO/.local/cache/mednafen/bin/mednafen"
[ -x "$MEDNAFEN_BIN" ] || MEDNAFEN_BIN=mednafen
case "$MEDNAFEN_BIN" in
  /*) if _has_mod "$MEDNAFEN_BIN" "$MOD"; then
        echo "실행: $(basename "$IMAGE")  [$MOD]  (우리 빌드 — 창 크기 ⌥-/⌥+ · ⌥1~4)"
      else
        echo "⚠ 우리 빌드에 [$MOD] 모듈이 없다 — 시스템 mednafen 으로 간다(창 크기 단축키 없음)."
        echo "  다시 지으려면: sh scripts/emu/mednafen-build.sh   (상태: --check)"
        MEDNAFEN_BIN=mednafen
        echo "실행: $(basename "$IMAGE")  [$MOD]"
      fi ;;
  *)  echo "실행: $(basename "$IMAGE")  [$MOD]  (시스템 mednafen — 창 크기 단축키 없음)" ;;
esac
_isha=$(img_sha "$IMAGE" || true)
[ -n "$_isha" ] && echo "      sha1 $_isha"
keyhelp mednafen
if ! _has_mod "$MEDNAFEN_BIN" "$MOD"; then
  echo "🔴 이 mednafen 에는 [$MOD] 모듈이 없다 — 이미지가 아니라 **에뮬레이터** 문제다." >&2
  echo "   확인: $MEDNAFEN_BIN --help | grep 'Emulation modules'" >&2
  echo "   고치기: sh scripts/emu/mednafen-build.sh" >&2
  exit 1
fi
if [ "$SYNC" != 1 ]; then
  # shellcheck disable=SC2086
  exec "$MEDNAFEN_BIN" -force_module "$MOD" -filesys.path_sav "$SAVEREL" -filesys.path_snap "$SNAPDIR" $EXTRA "$IMAGE"
fi

# 🔴 **이번 실행에서 만든 스테이트도 dev 로 보낸다**(마스터 2026-09-27) — 세이브가 안 되는 자리
#   (전투 등)에서 재현한 순간을 세션에 넘기려는 것이다. dev emucap 도 mednafen 1.32.1 이라 md·ps1·
#   ss·pce 는 세션이 그대로 불러올 수 있다(⚠ sfc 는 dev 가 Mesen2 라 못 부른다 — 풀어 읽기만).
#   `~/save/<게임>/state/` 에 `<mednafen 이름>.<시각>.mednafen` 으로 쌓는다(슬롯을 덮지 않게 시각을 붙인다).
#   웹 실행기의 「상태」 버튼과 같은 칸이다(`scripts/publish/serve.py`).
STATE_MARK=$(mktemp)
push_states() {
  _stem=$(basename "${IMAGE%.*}")
  _tmp=$(mktemp -d)
  _ts=$(date +%Y%m%d-%H%M%S)
  find "$MEDBASE/mcs" -maxdepth 1 -type f -name "$_stem.*" -name '*.mc[0-9]' -newer "$STATE_MARK" \
    2>/dev/null | while IFS= read -r f; do cp -p "$f" "$_tmp/$(basename "$f").$_ts.mednafen"; done
  if [ -n "$(ls "$_tmp")" ]; then
    ( cd "$_tmp" && set -- * && sh "$SYNCSH" push "$GAME/state" "$_tmp" "$@" ) || true
  fi
  rm -rf "$_tmp" "$STATE_MARK"
  return 0
}

# ⚠ Ctrl+C 로 끊어도 세이브는 올려야 한다 — 진행분을 잃는 게 제일 나쁜 결과다.
PUSHED=0
finish() {
  [ "$PUSHED" = 1 ] && return 0
  PUSHED=1
  # 글로브는 **여기서 리터럴로** 편다(전개 결과는 단어분리를 안 타 파일명의 공백·`&` 가 산다
  # — `sync-saves.sh` 헤더 참조).
  ( cd "$SAVEDIR" && set -- * && sh "$SYNCSH" push "$GAME" "$SAVEDIR" "$@" ) || true
  push_states
}
trap 'finish; exit 130' INT
trap 'finish; exit 143' TERM

RC=0
# shellcheck disable=SC2086
"$MEDNAFEN_BIN" -force_module "$MOD" -filesys.path_sav "$SAVEREL" -filesys.path_snap "$SNAPDIR" $EXTRA "$IMAGE" || RC=$?
finish
exit $RC
