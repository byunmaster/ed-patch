#!/bin/sh
# 이 게임의 커밋 전 게이트 — **재삽입 체인을 통째로 돌린다.**
#
#   sh games/ss-ed1+2/check.sh      (보통은 `sh scripts/check.sh` 가 부른다)
#
# ⚠ **여기선 「빌드」와 「검사」가 안 갈린다.** 새턴 쪽은 패처마다 자기 되읽기와 가드를
#   들고 있어(원문 대조 · 폭 검사 · 앞말 일본어 · 이중 주인 · 라벨 전량 훑기 · 디스어셈블
#   검산), 체인을 돌리는 것이 곧 검사다. 갈라 두면 한쪽만 돌리게 된다.
# ⚠ **순서가 계약이다** — `patch_title.py` 가 빌드 사본을 만들고, 나머지가 그 위에 얹는다.
#   `patch_ui.py` 는 글리프를 굽고 조사 훅은 그 슬롯 코드에서 표를 유도한다.
# ⚠ 실패하면 산출물이 `*.failed` 로 무효화되고 여기서 멈춘다 — 뒤 단계는 낡은 이미지를
#   보게 되므로 이어 돌리지 않는다(`set -e`).
# ⚠ 원본이 필요하다(`originals/jp/ss-ed1+2`). 워크트리는 `scripts/worktree.sh` 가 링크한다.
#
# ⚠ 단위·회귀 테스트(`scripts/test.sh`)와 브랜치 범위 검사는 **여기 없다** — 레포 전역이라
#   `scripts/check.sh` 가 맡는다.
set -eu

G=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$G/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3
T="$G/tools"

# 🔴 **실패한 빌드는 산출물을 무효화한다**(루트 CLAUDE.md 「빌드 규율」). 남은 낡은 이미지를
#    정상으로 오해하고 조사하면 엉뚱한 결론이 나온다 — 이 레포의 1급 사고다.
#    ⚠ 헤더엔 예전부터 그렇게 적혀 있었는데 **실제로는 안 하고 있었다**(2026-08-27 실측).
# ⚠ `set -e` 아래라 **값을 정하는 자리에서 실패할 수 있는 명령을 쓰지 않는다** — 못 구하면
#    빈 값으로 두고 아래에서 건너뛴다(루트 CLAUDE.md 「코드 스타일」 셸 절).
BUILD=$("$PY" -c "import sys;sys.path.insert(0,'$T');import common as C;print(C.BUILD_DIR)" 2>/dev/null) || BUILD=""

invalidate() {
  [ -n "$BUILD" ] && [ -d "$BUILD" ] || return 0
  n=0
  for p in "$BUILD"/*.bin "$BUILD"/*.cue "$BUILD"/*.m3u; do
    [ -f "$p" ] || continue
    mv "$p" "$p.failed"
    n=$((n + 1))
  done
  [ "$n" -gt 0 ] && echo "  ⚠ 산출물 ${n}개를 *.failed 로 무효화했다 ($BUILD)"
  return 0
}

# ⚠ **지난 표식은 시작할 때 지운다.** 「성공했을 때」가 아니다 — 체인이 중간에 죽으면
#    성공 시점을 못 밟아 표식이 또 남고, `scripts/pull-build.sh` 가 정상 이미지가 있는
#    칸까지 통째로 거부한다(유저 실측 2026-08-27). 시작에 지워야 「이 칸의 `.failed` 는
#    **직전 실행의 결과만** 뜻한다」가 선다.
[ -n "$BUILD" ] && rm -f "$BUILD"/*.failed

step() {   # step <설명> <스크립트> [인자…]
  d=$1
  shift
  out=$("$PY" "$@" 2>&1) || {
    echo "  ❌ $d — $PY $*"
    echo "$out" | tail -12 | sed 's/^/     /'
    invalidate
    exit 1
  }
  echo "$out" | grep -E '✅|되읽기|훑기|ℹ' | tail -4 | sed "s|^|     |"
}

echo "  ── 자막 (빌드 사본을 만든다)"
step "자막" "$T/patch_title.py" --apply
echo "  ── 파일 확장 (꼬리 섹터를 자리로 — LBA 불변)"
step "파일 확장" "$T/expand_files.py" --apply
echo "  ── 표·헤더·카드·고유명사·시스템 메시지 (되읽기 + 가드 넷)"
step "UI" "$T/patch_ui.py" --apply
echo "  ── 그림 (타이틀 · 메뉴 · 챕터 판 · HUD)"
step "타이틀 그림" "$T/patch_gfx_title.py" --apply
step "메뉴 그림" "$T/patch_gfx_menu.py" --apply
step "챕터 판" "$T/patch_gfx_cards.py" --apply
step "HUD" "$T/patch_gfx_hud.py" --apply
echo "  ── 파일 재배치 (모자란 씬 파일을 뒤로 밀어 1섹터씩 준다 — LBA 가 바뀐다)"
# ⚠ **`patch_scn` 이 남긴 부족 목록**(`work/derived/scn_shortfall.json`)을 읽는다. 그래서
#   첫 회차엔 목록이 없어 아무것도 안 하고, **다음 회차부터** 자리를 연다.
#   🔴 그러니 이 게이트는 **두 번 돌려야 수렴한다** — 아래 씬 대사가 그 자리를 쓴다.
step "파일 재배치" "$T/relocate_files.py" --apply
echo "  ── 본편 대사 (저본 → 조판 → 칸 안에서 치환)"
step "씬 대사" "$T/patch_scn.py" --apply
echo "  ── ED2 몬스터 이름 (제자리 우선 · 넘치면 칸끼리 재배치)"
step "몬스터 이름" "$T/patch_mon_names.py" --apply
echo "  ── 회심/통한 복사 루프 (14B 고정 → NUL 종단)"
step "회심 복사" "$T/patch_crit_copy.py" --apply
echo "  ── 고정 길이 복사 전수 (칸에 맞나 · 빌드 이미지 기준)"
step "고정 복사" "$T/check_fixed_copy.py"
echo "  ── 포인터 정렬 (두 바이트 고정으로 읽는 화면이 있다)"
step "포인터 정렬" "$T/check_ptr_align.py"
echo "  ── 정본 (같은 원문이 두 표기로 갈렸나)"
step "정본" "$T/check_glossary.py"
echo "  ── 문안 (조사·부호·정본 — 「한국어가 맞나」)"
step "문안" "$T/check_text.py"
echo "  ── 동적 조사 훅 (SH-2 디스어셈블 검산 + 참조 되읽기)"
step "조사 훅" "$T/patch_josa_hook.py" --apply

# 조판 지문 — ⚠ **게이트가 아니라 보고다**(문안을 바꾸면 당연히 바뀐다).
# 새턴이 `shared/` 에 닿는 면은 셋이다 — `glossary`(이름) · `text.line_key`(저본 열쇠) ·
# `text.josa`(조우 문구). 갈래 셋이 같은 파일을 미는 국면이라, 다른 게임 작업 중의 한 줄이
# 이 게임의 문안을 조용히 바꿀 수 있는데 **락도 관측 대장도 그걸 안 본다.**
# **안 바꿨는데 뜨면 `shared/` 를 의심한다.** 의도한 변화면 `--freeze` 로 다시 찍는다.
echo "  ── 조판 지문 (공용이 우리 문안을 흔들었나 — 보고)"
"$PY" "$ROOT/scripts/check/typeset_fingerprint.py" --game ss-ed1+2 2>&1 | tail -3 | sed 's/^/     /'

echo "  ✅ 체인 통과 — work/build/<꼬리표>/ 에 이미지가 있다"
