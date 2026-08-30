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
#   ── 가로축 하나 더 (SELECT_SIDE) ──────────────────────────────────────────
#   목록(↑↓) 과 **함께 고를 것**이 하나 더 있을 때 쓴다. 화면을 두 번 띄우는 대신
#   **목록 위** 한 줄로 붙고 **←→ 로 바꾼다**(유저 요청 2026-09-03 — pc98 의 시작 디스크).
#   안내 줄에도 `←→ <라벨>` 이 저절로 들어간다.
#     SELECT_SIDE='이어하기\n오프닝부터'   # 개행으로 나눈 항목들
#     SELECT_SIDE_LABEL='시작 디스크'      # 그 줄 앞에 붙일 이름 (없어도 된다)
#     SELECT_SIDE_INDEX=1                  # 1-based 초깃값
#   🔴 **결과는 stdout 에 두 줄로 나온다** — 첫 줄이 목록 항목, 둘째 줄이 가로축 값이다.
#      `$(...)` 는 subshell 이라 변수로는 못 돌려준다(전역에 써 봐야 호출자에 안 간다).
#      SELECT_SIDE 를 안 주면 예전처럼 **한 줄**이라 기존 호출자는 그대로다.
#   고르고 나서 남기는 **한 줄 요약**(`게임: ss-ed3`)이 필요 없으면 SELECT_QUIET=1.
#     ⚠ 요약이 기본인 이유는 목록을 지우고 나면 **뭘 골랐는지가 화면에서 사라지기** 때문이다.
#       부르는 쪽이 곧바로 같은 걸 다시 찍는다면(pull-build 의 결과 표) 그때만 끈다.
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

# ⚠ **파일 스코프에 둔다.** select_option 안에 두면 select_multi 에서 `command not found` 로
#   터미널이 에코 꺼진 채 남는다(2026-08-22 실측).
_sel_restore() {
  tput cnorm >/dev/tty 2>/dev/null || true
  [ -n "${_sold:-}" ] && stty "$_sold" </dev/tty 2>/dev/null || true
  trap - INT TERM
}

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
  _sside0=0; [ -n "${SELECT_SIDE:-}" ] && _sside0=1
  if [ $(($# + 2 + _sside0)) -gt "${_rows:-24}" ]; then
    # 번호 폴백에는 가로축을 못 그린다 — **기본값을 그대로 낸다**(호출자 파싱은 유지된다).
    _snum=$(_sel_numbered "$_sp" "$@") || return $?
    printf '%s' "$_snum"
    [ "$_sside0" = 1 ] && printf '\n%s' "$(printf '%s\n' "$SELECT_SIDE" | sed -n "${SELECT_SIDE_INDEX:-1}p")"
    return 0
  fi

  _srender=${SELECT_RENDER:-_sel_default_row}
  _stotal=$#
  _ssel=${SELECT_INDEX:-1}
  { [ "$_ssel" -ge 1 ] && [ "$_ssel" -le $# ]; } 2>/dev/null || _ssel=1

  # 가로축(선택) — 있으면 목록 아래 한 줄을 더 그린다.
  _sside=0; _ssidx=1; _ssn=0
  if [ -n "${SELECT_SIDE:-}" ]; then
    _sside=1
    _ssn=$(printf '%s\n' "$SELECT_SIDE" | wc -l | tr -d ' ')
    _ssidx=${SELECT_SIDE_INDEX:-1}
    { [ "$_ssidx" -ge 1 ] && [ "$_ssidx" -le "$_ssn" ]; } 2>/dev/null || _ssidx=1
  fi
  _sel_side_val() { printf '%s\n' "$SELECT_SIDE" | sed -n "${_ssidx}p"; }
  _sel_side_draw() {
    printf '\033[2K' >/dev/tty
    if [ "$_ssn" -gt 1 ]; then
      # ⚠ 여기에 `(←→)` 를 또 적지 않는다 — 안내 줄이 이미 말한다(중복은 눈에 걸린다).
      printf '  \033[2m%s\033[0m \033[2m‹\033[0m \033[36m%s\033[0m \033[2m›\033[0m\n' \
        "${SELECT_SIDE_LABEL:-}" "$(_sel_side_val)" >/dev/tty
    else
      printf '  \033[2m%s\033[0m \033[36m%s\033[0m\n' "${SELECT_SIDE_LABEL:-}" "$(_sel_side_val)" >/dev/tty
    fi
  }

  # $1=1 이면 이전에 그린 만큼 커서를 올려 제자리에 다시 그린다(지웠다 그리면 깜빡인다).
  # ⚠ 가로축은 **목록 위**에 그린다(유저 확정 2026-09-03). 줄 옆에 붙이면 ⑴ 「이 줄만의
  #   설정」으로 읽히고 ⑵ 줄 길이가 제각각이라 ‹ › 위치가 커서를 따라 춤춘다. 위에 두면
  #   **무엇을 고르든 함께 적용된다**는 게 모양으로 드러나고, 자리도 안 흔들린다.
  _sel_draw() {
    _rd=$1; shift
    [ "$_rd" = 1 ] && printf '\033[%dA' "$((_stotal + _sside))" >/dev/tty
    [ "$_sside" = 1 ] && _sel_side_draw
    _i=0
    for _it in "$@"; do
      _i=$((_i + 1))
      printf '\033[2K' >/dev/tty
      if [ "$_i" = "$_ssel" ]; then "$_srender" "$_i" "$_it" 1 >/dev/tty
      else                          "$_srender" "$_i" "$_it" 0 >/dev/tty; fi
    done
    return 0
  }


  _shelp='↑↓ 이동'
  [ "$_sside" = 1 ] && [ "$_ssn" -gt 1 ] && _shelp="$_shelp, ←→ ${SELECT_SIDE_LABEL:-바꾸기}"
  printf '%s \033[2m(%s, Enter 선택, Esc 뒤로, q 취소)\033[0m\n' "$_sp" "$_shelp" >/dev/tty

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
             43) [ "$_sside" = 1 ] && [ "$_ssidx" -lt "$_ssn" ] && _ssidx=$((_ssidx + 1)) ;; # →
             44) [ "$_sside" = 1 ] && [ "$_ssidx" -gt 1 ] && _ssidx=$((_ssidx - 1)) ;;       # ←
           esac
           _sel_draw 1 "$@"
         else
           # 맨 Esc = **뒤로**. 취소(q)와 가르는 이유는 목록이 겹겹이라서다 — 이미지 목록에서
           # 잘못 들어왔을 때 되돌아갈 자리가 게임 목록이지 셸이 아니다(유저 요청 2026-08-21).
           _srft=3; break
         fi ;;
      6b) [ "$_ssel" -gt 1 ] && _ssel=$((_ssel - 1)); _sel_draw 1 "$@" ;;            # k
      6a) [ "$_ssel" -lt "$_stotal" ] && _ssel=$((_ssel + 1)); _sel_draw 1 "$@" ;;   # j
      68) { [ "$_sside" = 1 ] && [ "$_ssidx" -gt 1 ]; } && _ssidx=$((_ssidx - 1)); _sel_draw 1 "$@" ;;     # h
      6c) { [ "$_sside" = 1 ] && [ "$_ssidx" -lt "$_ssn" ]; } && _ssidx=$((_ssidx + 1)); _sel_draw 1 "$@" ;; # l
      0d|0a) _srft=0; break ;;               # Enter
      71|51|03|'') _srft=1; break ;;         # q · Q · Ctrl+C · EOF
    esac
  done
  _sel_restore

  # 목록을 지우고 **한 줄 요약**만 남긴다 — 고르고 나면 후보는 소음이다(zsh 판과 같은 연출).
  printf '\r\033[%dA\033[J' "$((_stotal + _sside + 1))" >/dev/tty
  if [ "${_srft:-1}" != 0 ]; then
    [ "$_srft" = 3 ] && printf '%s: \033[2m← 뒤로\033[0m\n' "$_sp" >/dev/tty \
                     || printf '%s: \033[2m취소\033[0m\n' "$_sp" >/dev/tty
    return "$_srft"
  fi
  _i=0
  for _it in "$@"; do
    _i=$((_i + 1))
    if [ "$_i" = "$_ssel" ]; then
      # ⚠ 요약엔 **탭 앞부분만** 쓴다 — 항목이 `이름\t경로` 인 호출자가 여럿이라,
      #   그대로 찍으면 고른 뒤 화면에 절대경로가 남는다.
      _stab=$(printf '\t'); _slbl=${_it%%"$_stab"*}
      if [ "$_sside" = 1 ]; then _slbl="$_slbl · $(_sel_side_val)"; fi
      [ "${SELECT_QUIET:-0}" = 1 ] || printf '%s: \033[36m%s\033[0m\n' "$_sp" "$_slbl" >/dev/tty
      printf '%s' "$_it"
      [ "$_sside" = 1 ] && printf '\n%s' "$(_sel_side_val)"
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

# 체크박스 다중 선택 — space 토글 · ↑↓/kj 이동 · Enter 확정 · Esc 뒤로(3) · q 취소(1).
# 고른 항목을 **줄바꿈으로** stdout 에 뱉는다. 줄 모양은 SELECT_RENDER 를 그대로 쓴다
# (앞에 체크박스만 붙인다). 시작 커서는 SELECT_INDEX.
#
# ⚠ 원본(zsh 판 `select_multi`)은 **기본 전체 선택**인데 여기선 **기본 무선택**이다 —
#   저쪽은 터널 열기라 전부가 흔한 답이지만, 이쪽은 하나가 수백 MB 라 전부가 사고다.
# ⚠ 아무것도 안 고르고 Enter 를 치면 **커서 항목 하나**로 친다. 스페이스를 모르는 채로
#   써도 종전(단일 선택)과 똑같이 동작하게 하려는 것이다.
select_multi() {
  _sp=$1; shift
  [ $# -eq 0 ] && return 1
  # 하나뿐이면 묻지 않는다(select_option 과 같은 규칙) — 비대화형에서도 그대로 흐른다.
  [ $# -eq 1 ] && { printf '%s\n' "$1"; return 0; }
  has_tty || return 2
  _rows=$(stty size </dev/tty 2>/dev/null | cut -d' ' -f1)
  [ -n "$_rows" ] || _rows=24
  [ $(($# + 2)) -gt "${_rows:-24}" ] && { _sel_numbered_multi "$_sp" "$@"; return $?; }

  _srender=${SELECT_RENDER:-_sel_default_row}
  _stotal=$#
  _ssel=${SELECT_INDEX:-1}
  { [ "$_ssel" -ge 1 ] && [ "$_ssel" -le $# ]; } 2>/dev/null || _ssel=1
  _chk=" "                                  # 고른 번호를 " 1 3 " 처럼 담는다

  _sel_mdraw() {
    _rd=$1; shift
    [ "$_rd" = 1 ] && printf '\033[%dA' "$_stotal" >/dev/tty
    _i=0
    for _it in "$@"; do
      _i=$((_i + 1))
      printf '\033[2K' >/dev/tty
      case "$_chk" in *" $_i "*) printf '\033[32m[✓]\033[0m' >/dev/tty ;; *) printf '[ ]' >/dev/tty ;; esac
      if [ "$_i" = "$_ssel" ]; then "$_srender" "$_i" "$_it" 1 >/dev/tty
      else                          "$_srender" "$_i" "$_it" 0 >/dev/tty; fi
    done
  }

  printf '%s \033[2m(space 토글, ↑↓ 이동, Enter 확정, Esc 뒤로, q 취소)\033[0m\n' "$_sp" >/dev/tty
  _sold=$(stty -g </dev/tty 2>/dev/null) || _sold=
  stty -echo -icanon isig min 1 time 0 </dev/tty 2>/dev/null || true
  tput civis >/dev/tty 2>/dev/null || true
  trap '_sel_restore; exit 130' INT TERM
  _sel_mdraw 0 "$@"
  while :; do
    _k=$(_sel_key </dev/tty)
    case "$_k" in
      1b) _k2=$(_sel_key </dev/tty)
          if [ "$_k2" = 5b ] || [ "$_k2" = 4f ]; then
            _k3=$(_sel_key </dev/tty)
            case "$_k3" in
              41) [ "$_ssel" -gt 1 ] && _ssel=$((_ssel - 1)) ;;
              42) [ "$_ssel" -lt "$_stotal" ] && _ssel=$((_ssel + 1)) ;;
            esac
            _sel_mdraw 1 "$@"
          else _srft=3; break; fi ;;
      6b) [ "$_ssel" -gt 1 ] && _ssel=$((_ssel - 1)); _sel_mdraw 1 "$@" ;;
      6a) [ "$_ssel" -lt "$_stotal" ] && _ssel=$((_ssel + 1)); _sel_mdraw 1 "$@" ;;
      20) case "$_chk" in                       # space
            *" $_ssel "*) _chk=$(printf '%s' "$_chk" | sed "s/ $_ssel / /") ;;
            *) _chk="$_chk$_ssel " ;;
          esac
          _sel_mdraw 1 "$@" ;;
      0d|0a) _srft=0; break ;;
      71|51|03|'') _srft=1; break ;;
    esac
  done
  _sel_restore
  printf '\r\033[%dA\033[J' "$((_stotal + 1))" >/dev/tty
  if [ "${_srft:-1}" != 0 ]; then
    [ "$_srft" = 3 ] && printf '%s: \033[2m← 뒤로\033[0m\n' "$_sp" >/dev/tty \
                     || printf '%s: \033[2m취소\033[0m\n' "$_sp" >/dev/tty
    return "$_srft"
  fi
  [ "$_chk" = " " ] && _chk=" $_ssel "        # 아무것도 안 골랐으면 커서 항목
  _i=0; _n=0
  for _it in "$@"; do
    _i=$((_i + 1))
    case "$_chk" in *" $_i "*)
      printf '%s\n' "$_it"
      _n=$((_n + 1))
      [ "${SELECT_QUIET:-0}" = 1 ] || printf '%s: \033[36m%s\033[0m\n' "$_sp" "$_it" >/dev/tty ;;
    esac
  done
  [ "$_n" -gt 0 ] || return 1
  return 0
}

# 화면이 짧을 때 — 번호를 여러 개 받는다(`1 3` · `1,3`).
_sel_numbered_multi() {
  _sp=$1; _srender=${SELECT_RENDER:-_sel_default_row}; shift
  _i=0
  for _it in "$@"; do
    _i=$((_i + 1))
    printf '%2d)' "$_i" >/dev/tty
    "$_srender" "$_i" "$_it" 0 >/dev/tty
  done
  printf '%s [번호 여럿 가능: 1 3, b=뒤로, q=취소]: ' "$_sp" >/dev/tty
  read -r _sel </dev/tty || return 1
  case "$_sel" in b|B) return 3 ;; ''|q|Q) return 1 ;; esac
  _sel=$(printf '%s' "$_sel" | tr ',' ' ')
  _n=0
  for _s in $_sel; do
    case "$_s" in *[!0-9]*) continue ;; esac
    { [ "$_s" -ge 1 ] && [ "$_s" -le $# ]; } || continue
    _i=0
    for _it in "$@"; do
      _i=$((_i + 1))
      [ "$_i" = "$_s" ] && { printf '%s\n' "$_it"; _n=$((_n + 1)); }
    done
  done
  [ "$_n" -gt 0 ] || return 1
  return 0
}
