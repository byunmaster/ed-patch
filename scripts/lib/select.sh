#!/bin/sh
# 화살표 키 선택 UI — POSIX sh.
#
#   . "$HERE/lib/select.sh"
#   pick=$(select_option "게임" a b c) || echo "취소"
#
#   ↑↓ / k j 이동 · Enter 선택 · **Esc 뒤로(rc=3)** · q·Ctrl+C 취소(rc=1)
#   고른 항목은 **stdout**, 화면에 그리는 건 전부 **/dev/tty** 다 — 그래야 호출자가
#   `$(...)` 로 결과만 받는다.
#
#   줄 모양을 바꾸려면 부르기 전에 SELECT_RENDER 에 함수 이름을 넣는다:
#     SELECT_RENDER=my_row   # my_row <번호> <항목> <선택됨?0|1>
#   커서를 처음부터 특정 줄에 놓으려면 SELECT_INDEX (1-based).
#
# ── 왜 zsh 판을 그대로 안 쓰나 ───────────────────────────────────────────────
# 원본은 `sellernote-infra/scripts/lib/select.sh`(zsh) 이고 연출은 그걸 따랐다 — ❯ 마커,
# 커서 숨김, 다 고르면 목록을 지우고 **한 줄 요약으로 압축**하는 것까지. 옮긴 이유는 둘이다:
#   · 이 레포 스크립트는 전부 `#!/bin/sh` 다. 하나만 zsh 면 그 하나가 어디서 도는지를
#     따로 기억해야 한다.
#   · **dev(Debian LXC)에 zsh 가 없다.** 실행기는 GUI 라 맥에서 돌지만, 목록·선택은
#     원격에서도 쓸 수 있어야 한다(`--list` 처럼).
# 레포가 다르니 공유가 아니라 **이식**이 맞다 — 고칠 일이 생기면 양쪽이 따로 산다.

# 키를 한 바이트 읽어 **16진수로** 돌려준다. 문자로 비교하면 Enter(\r)·Esc 가 셸에서
# 사라지거나 이스케이프로 먹혀 안 잡힌다 — 16진수면 그 함정이 통째로 없다.
# ⚠ **`[ -r /dev/tty ]` 로는 못 가린다** — 파일은 늘 거기 있어서 테스트는 통과하는데
# 실제로 열면 "Device not configured" 로 죽는다(에이전트·CI 처럼 제어 터미널이 없을 때 —
# 2026-08-21 실측). 열어 봐야 안다.
has_tty() { { : </dev/tty; } 2>/dev/null && { : >/dev/tty; } 2>/dev/null; }

_sel_key() { dd bs=1 count=1 2>/dev/null | od -An -tx1 | tr -d ' \n'; }

_sel_default_row() {
  if [ "$3" = 1 ]; then printf '\033[36m❯ %s\033[0m\n' "$2"
  else                  printf '  %s\n' "$2"; fi
}

# 화면이 목록보다 짧으면 커서 셈이 깨진다(스크롤이 일어나 「N줄 위」가 다른 줄을 가리킨다).
# 그럴 땐 번호로 받는다 — 화면을 못 믿는 자리에서 화면을 그리는 것보다 낫다.
_sel_numbered() {
  _sp=$1; _srender=${SELECT_RENDER:-_sel_default_row}; shift
  _i=0
  for _it in "$@"; do
    _i=$((_i + 1))
    printf '%2d)' "$_i" >/dev/tty
    "$_srender" "$_i" "$_it" 0 >/dev/tty
  done
  printf '%s [1-%d, b=뒤로, q=취소]: ' "$_sp" "$_i" >/dev/tty
  read -r _sel </dev/tty || return 1
  case "$_sel" in
    b|B) return 3 ;;
    ''|q|Q) return 1 ;;
    *[!0-9]*) return 1 ;;
  esac
  [ "$_sel" -ge 1 ] && [ "$_sel" -le $# ] || return 1
  _i=0
  for _it in "$@"; do
    _i=$((_i + 1))
    [ "$_i" = "$_sel" ] && { printf '%s' "$_it"; return 0; }
  done
  return 1
}

select_option() {
  _sp=$1; shift
  [ $# -eq 0 ] && return 1
  [ $# -eq 1 ] && { printf '%s' "$1"; return 0; }
  has_tty || return 2
  # ⚠ `tput lines` 는 **stdout 이 터미널일 때만** 진짜 크기를 준다. 이 함수는 결과를
  #   `$(...)` 로 넘기느라 stdout 이 파이프라 terminfo 기본값(24)이 나온다 — 그러면
  #   화면이 넉넉해도 번호 입력으로 떨어진다(실측). tty 를 직접 물어본다.
  _rows=$(stty size </dev/tty 2>/dev/null | cut -d' ' -f1)
  [ -n "$_rows" ] || _rows=24
  [ $(($# + 2)) -gt "${_rows:-24}" ] && { _sel_numbered "$_sp" "$@"; return $?; }

  _srender=${SELECT_RENDER:-_sel_default_row}
  _stotal=$#
  _ssel=${SELECT_INDEX:-1}
  { [ "$_ssel" -ge 1 ] && [ "$_ssel" -le $# ]; } 2>/dev/null || _ssel=1

  # $1=1 이면 이전에 그린 만큼 커서를 올려 제자리에 다시 그린다(지웠다 그리면 깜빡인다).
  _sel_draw() {
    _rd=$1; shift
    [ "$_rd" = 1 ] && printf '\033[%dA' "$_stotal" >/dev/tty
    _i=0
    for _it in "$@"; do
      _i=$((_i + 1))
      printf '\033[2K' >/dev/tty
      if [ "$_i" = "$_ssel" ]; then "$_srender" "$_i" "$_it" 1 >/dev/tty
      else                          "$_srender" "$_i" "$_it" 0 >/dev/tty; fi
    done
  }

  _sel_restore() {
    tput cnorm >/dev/tty 2>/dev/null || true
    [ -n "$_sold" ] && stty "$_sold" </dev/tty 2>/dev/null || true
    trap - INT TERM
  }

  printf '%s \033[2m(↑↓ 이동, Enter 선택, Esc 뒤로, q 취소)\033[0m\n' "$_sp" >/dev/tty

  _sold=$(stty -g </dev/tty 2>/dev/null) || _sold=
  # ⚠ `isig` 를 남긴다 — raw 로 다 끄면 **Ctrl+C 로 못 빠져나온다.** 커서도 되돌려야 하므로
  #   트랩으로 원상복구를 건다(안 그러면 터미널이 에코 없는 채로 남는다).
  stty -echo -icanon isig min 1 time 0 </dev/tty 2>/dev/null || true
  tput civis >/dev/tty 2>/dev/null || true
  trap '_sel_restore; exit 130' INT TERM

  _sel_draw 0 "$@"
  _src=1
  while :; do
    _k=$(_sel_key </dev/tty)
    case "$_k" in
      1b)                                   # Esc — 화살표의 머리이기도 하다
         _k2=$(_sel_key </dev/tty)
         if [ "$_k2" = 5b ] || [ "$_k2" = 4f ]; then
           _k3=$(_sel_key </dev/tty)
           case "$_k3" in
             41) [ "$_ssel" -gt 1 ] && _ssel=$((_ssel - 1)) ;;          # ↑
             42) [ "$_ssel" -lt "$_stotal" ] && _ssel=$((_ssel + 1)) ;; # ↓
           esac
           _sel_draw 1 "$@"
         else
           # 맨 Esc = **뒤로**. 취소(q)와 가르는 이유는 목록이 겹겹이라서다 — 이미지 목록에서
           # 잘못 들어왔을 때 되돌아갈 자리가 게임 목록이지 셸이 아니다(유저 요청 2026-08-21).
           _srft=3; break
         fi ;;
      6b) [ "$_ssel" -gt 1 ] && _ssel=$((_ssel - 1)); _sel_draw 1 "$@" ;;            # k
      6a) [ "$_ssel" -lt "$_stotal" ] && _ssel=$((_ssel + 1)); _sel_draw 1 "$@" ;;   # j
      0d|0a) _srft=0; break ;;               # Enter
      71|51|03|'') _srft=1; break ;;         # q · Q · Ctrl+C · EOF
    esac
  done
  _sel_restore

  # 목록을 지우고 **한 줄 요약**만 남긴다 — 고르고 나면 후보는 소음이다(zsh 판과 같은 연출).
  printf '\r\033[%dA\033[J' "$((_stotal + 1))" >/dev/tty
  if [ "${_srft:-1}" != 0 ]; then
    [ "$_srft" = 3 ] && printf '%s: \033[2m← 뒤로\033[0m\n' "$_sp" >/dev/tty \
                     || printf '%s: \033[2m취소\033[0m\n' "$_sp" >/dev/tty
    return "$_srft"
  fi
  _i=0
  for _it in "$@"; do
    _i=$((_i + 1))
    if [ "$_i" = "$_ssel" ]; then
      printf '%s: \033[36m%s\033[0m\n' "$_sp" "$_it" >/dev/tty
      printf '%s' "$_it"
      return 0
    fi
  done
  return 1
}

# y/n — 제대로 답할 때까지 다시 묻는다. 한글 자판 상태의 ㅛ/ㅜ 도 같은 키라 같은 답으로 받는다
# (원본 zsh 판의 판단을 그대로 가져왔다 — 오타 한 번에 작업이 취소되면 안 된다).
confirm_yes() {
  has_tty || return 1
  while :; do
    printf '%s' "$1" >/dev/tty
    read -r _a </dev/tty || { printf '\n' >/dev/tty; return 1; }
    case "$(printf '%s' "$_a" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')" in
      y|yes|ㅛ) return 0 ;;
      n|no|ㅜ)  return 1 ;;
      *) printf '  \033[2m(y 또는 n)\033[0m\n' >/dev/tty ;;
    esac
  done
}
