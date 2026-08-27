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

step() {   # step <설명> <스크립트> [인자…]
  d=$1
  shift
  out=$("$PY" "$@" 2>&1) || {
    echo "  ❌ $d — $PY $*"
    echo "$out" | tail -12 | sed 's/^/     /'
    exit 1
  }
  echo "$out" | grep -E '✅|되읽기|훑기' | tail -3 | sed "s|^|     |"
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
echo "  ── 본편 대사 (저본 → 조판 → 칸 안에서 치환)"
step "씬 대사" "$T/patch_scn.py" --apply
echo "  ── ED2 몬스터 이름 (제자리 우선 · 넘치면 칸끼리 재배치)"
step "몬스터 이름" "$T/patch_mon_names.py" --apply
echo "  ── 회심/통한 복사 루프 (14B 고정 → NUL 종단)"
step "회심 복사" "$T/patch_crit_copy.py" --apply
echo "  ── 고정 길이 복사 전수 (칸에 맞나 · 빌드 이미지 기준)"
step "고정 복사" "$T/check_fixed_copy.py"
echo "  ── 동적 조사 훅 (SH-2 디스어셈블 검산 + 참조 되읽기)"
step "조사 훅" "$T/patch_josa_hook.py" --apply

echo "  ✅ 체인 통과 — work/build/<꼬리표>/ 에 이미지가 있다"
