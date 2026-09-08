#!/bin/sh
# macOS 입력 소스 함정 — 에뮬레이터 공용.
#
#   . "$HERE/emu/ime.sh"
#   ensure_ascii_input     # ⭐ 실행 직전에 ASCII 자판을 **강제**한다 (못 하면 경고로 떨어진다)
#   warn_ime               #    경고만 (강제 없이)
#
# ── 🔴 이건 취향 문제가 아니라 크래시다 (2026-08-31 확정) ────────────────────
# 종전엔 「한글이면 방향키가 죽는다」고 **경고만** 했다. 경고는 안 통했다 — 크래시 리포트
# 셋(`~/Library/Logs/DiagnosticReports/dosbox-x-*.ips`)이 전부 같은 자리였다:
#
#   -[SDLTranslatorResponder insertText:replacementRange:]
#     → __strncpy_chk → SIGSEGV (KERN_INVALID_ADDRESS at 0x0)
#   호출자는 IMKInputSession_Modern insertText: — **입력기(IME)** 다.
#
# IME 가 조합을 확정하며 넘기는 문자열을 SDL1 이 ASCII C 문자열로 바꾸는데, 한글은 ASCII 로
# 못 바꿔 **NULL** 이 나오고 그걸 그대로 strncpy 한다. 즉 **비ASCII 확정 = 즉사**다.
# 고칠 자리는 DOSBox-X 가 안고 있는 SDL1 안이라 우리 쪽에서 못 고친다.
#
# 🔴 **증상이 둘인데 원인은 하나다.**
#   · 「키가 안 먹는다」 — 조합 중인 키는 IME 가 물고 있어 게임까지 오지 않는다
#   · 「한글 치면 뻗는다」 — 위의 SIGSEGV
#   그래서 입력 소스를 **바꿔 주는 것**이 유일한 대책이다. 경고로는 못 막는다.
#   ⚠ 실제로 이 레포가 세 번 헛다리를 짚었다 — 「앱 번들 채널이라 그렇다」·「usescancodes
#     탓이다」·「PC-98 키보드 절이 빠졌다」. 셋 다 아니었고 크래시 로그 한 줄이 답이었다.
#     **키 문제를 만나면 설정을 만지기 전에 DiagnosticReports 를 먼저 본다.**
#
# 기종별 실측 (2026-08-21 갱신):
#   · DOSBox-X (SDL1)      🔴 방향키가 죽고, 한글 확정이 들어오면 **프로세스가 죽는다**
#   · DOSBox Staging (SDL2) ✅ 한글 상태에서도 먹는다 (ED3 로 확인)
#   · mednafen              🔴 **글자 키(a·s·d·w…)가 죽는다. 방향키는 산다**(2026-08-22).
#                             하필 우리 배치가 버튼을 전부 글자 키에 뒀으니(mednafen_keys.py)
#                             한글 모드면 **이동만 되고 확인·취소가 안 먹는** 상태가 된다.
#
# 끄려면 `EMU_NO_IME_SWITCH=1`. 바꿀 자판은 `IME_ASCII`(기본 com.apple.keylayout.ABC).

IME_ASCII=${IME_ASCII:-com.apple.keylayout.ABC}

# ⚠ 소스된 파일은 제 경로를 못 안다(POSIX sh) — 레포 뿌리는 git 에 묻는다. 워크트리에서도
#   `--git-common-dir` 이 본 트리를 가리키므로 빌드 사본이 한 벌로 모인다(pc98.sh 와 같은 규약).
_ime_main() {
  _g=$(git rev-parse --git-common-dir 2>/dev/null || true)
  [ -n "$_g" ] || return 0
  (cd "$_g/.." && pwd)
}

# 전환기를 **필요할 때 짓는다**(2초). 산출물은 머신 전용이라 `.local/` 이다.
# ⚠ 소스가 더 새로우면 다시 짓는다 — 안 그러면 고쳐 놓고 옛 바이너리가 도는 이 레포 단골 사고다.
_ime_tis() {
  _m=$(_ime_main); [ -n "$_m" ] || return 0
  _src="$_m/scripts/emu/tis_select.swift"
  _bin="$_m/.local/cache/bin/tis-select"
  [ -f "$_src" ] || return 0
  if [ ! -x "$_bin" ] || [ "$_src" -nt "$_bin" ]; then
    command -v swiftc >/dev/null 2>&1 || return 0
    mkdir -p "$(dirname "$_bin")"
    swiftc -O -o "$_bin" "$_src" >/dev/null 2>&1 || return 0
  fi
  printf '%s' "$_bin"
}

# 지금 입력 소스가 **입력기**인가 — `com.apple.keylayout.*` 은 그냥 자판이라 안전하다.
# 그 밖(`com.apple.inputmethod.Korean.*` 등)은 조합을 거치므로 위험하다.
_ime_is_ime() {
  case "$1" in
    com.apple.keylayout.*) return 1 ;;
    '') return 1 ;;
    *) return 0 ;;
  esac
}

# ⭐ 실행 직전에 부른다. 바꿨으면 말하고, 못 바꿨으면 경고로 떨어진다.
ensure_ascii_input() {
  [ "$(uname -s)" = Darwin ] || return 0
  [ "${EMU_NO_IME_SWITCH:-0}" = 1 ] && { warn_ime; return 0; }
  _t=$(_ime_tis)
  [ -n "$_t" ] || { warn_ime; return 0; }        # swiftc 가 없다 — 종전대로 경고만
  _cur=$("$_t" 2>/dev/null || true)
  _ime_is_ime "$_cur" || return 0                # 이미 안전한 자판이다 — 조용히 지나간다
  if "$_t" "$IME_ASCII" 2>/dev/null; then
    echo "  ⓘ 입력 소스를 $IME_ASCII 로 바꿨다 (한글이면 DOSBox-X 가 뻗는다: SDL1 insertText SIGSEGV)"
    echo "     되돌리려면: $_t $_cur"
    _ime_hint_percontext
  else
    warn_ime
  fi
}

# 앱별 기억을 켜 두면 이 문제 자체가 없어진다 — 켜져 있으면 두 번 말하지 않는다.
# ⚠ 우리가 켜지는 않는다. 전역 사용자 설정이고 **재로그인이 필요**해서 실행 명령이 조용히
#   건드릴 물건이 아니다. 알려만 준다.
_ime_hint_percontext() {
  [ -n "$(defaults read com.apple.HIToolbox AppleGlobalTextInputProperties 2>/dev/null)" ] && return 0
  echo "     한 번에 끝내려면(앱별 입력 소스 기억, 재로그인 필요):"
  echo "       defaults write com.apple.HIToolbox AppleGlobalTextInputProperties \\"
  echo "         -dict TextInputGlobalPropertyPerContextInput -int 1"
}

# ⚠ **단정하지 않는다.** 늘 뜨는 경고는 아무도 안 본다(이 레포가 게이트에 대해 못 박은
#   것과 같은 이유다). 「한글이니 안 된다」가 아니라 「안 먹으면 여기부터 보라」로 적는다.
warn_ime() {
  [ "$(uname -s)" = Darwin ] || return 0
  defaults read ~/Library/Preferences/com.apple.HIToolbox.plist AppleSelectedInputSources 2>/dev/null \
    | grep -qi 'inputmethod\.Korean' || return 0
  echo "ⓘ 입력 소스가 한글이다 — 영문(ABC)으로 바꿀 것." >&2
  echo "  · mednafen  : 글자 키(a·s·d·w)가 안 먹는다" >&2
  echo "  · DOSBox-X  : 방향키가 죽고, **한글 확정이 들어오면 프로세스가 죽는다**(SIGSEGV)" >&2
  _ime_hint_percontext >&2
}

# ── 🔴 실행 직전 한 번으로는 모자란다 ────────────────────────────────────────
# `ensure_ascii_input` 은 **띄우는 순간**만 맞춘다. 그런데 맥의 입력 소스는 **전역**이라,
# 게임을 켜 두고 터미널·채팅에서 한글을 한 번 치면 그대로 한글로 돌아온다. 그 상태로 에뮬
# 창을 클릭하면 **방향키만 죽는다** — Enter·ESC·Shift 는 멀쩡해서 「에뮬이 이상하다」로
# 오해하기 딱 좋다(2026-09-01 유저 실측: 정확히 이 증상이었다. 2026-07-31 에 한 번 규명해
# 놓고도 같은 자리에 다시 빠졌다).
#
# 그래서 **에뮬 창이 앞에 있는 동안만** ASCII 로 되돌린다. 앞에 없을 때는 손대지 않으므로
# 터미널에서 한글 쓰는 건 그대로다.
#   ⚠ 최전면 앱은 `lsappinfo` 로 읽는다 — osascript/System Events 와 달리 **손쉬움 권한이
#     필요 없다**(실측: 이 터미널엔 그 권한이 없어 keystroke 는 막혔지만 lsappinfo 는 된다).
#   ⚠ 감시기는 에뮬이 죽으면 같이 끝난다. 백그라운드로 돌고 아무것도 안 찍는다.
guard_ascii_input() {                 # $1 = 에뮬 프로세스를 찾을 pgrep 패턴
  [ "$(uname -s)" = Darwin ] || return 0
  [ "${EMU_NO_IME_SWITCH:-0}" = 1 ] && return 0
  command -v lsappinfo >/dev/null 2>&1 || return 0
  _t=$(_ime_tis); [ -n "$_t" ] || return 0
  _pat=$1
  (
    # 뜨기를 기다린다 — `open -n`·직접 실행 둘 다 곧바로는 안 뜬다.
    _i=0
    while [ $_i -lt 30 ]; do pgrep -f "$_pat" >/dev/null 2>&1 && break; sleep 1; _i=$((_i + 1)); done
    while pgrep -f "$_pat" >/dev/null 2>&1; do
      _front=$(lsappinfo info -only name "$(lsappinfo front 2>/dev/null)" 2>/dev/null || true)
      case "$_front" in
        *dosbox*|*DOSBox*|*mednafen*)
          _cur=$("$_t" 2>/dev/null || true)
          _ime_is_ime "$_cur" && "$_t" "$IME_ASCII" >/dev/null 2>&1 || true ;;
      esac
      sleep 1
    done
  ) >/dev/null 2>&1 &
}
