#!/bin/sh
# 이 게임의 커밋 전 게이트 — [fix] 트랙(만트라 DOS 영웅전설 II 복원).
#
#   sh games/dos-ed2/check.sh      (보통은 `sh scripts/check.sh` 가 부른다)
#
# ⚠ 2026-08-19 까지 **이 트랙엔 게이트가 아예 없었다.** `scripts/check.sh` 가 사실상
#   ps1-ed1+2 전용이었기 때문인데, 트랙이 둘인데 하나만 지켜지는 상태였다.
#
# ⚠ 여기가 kr 트랙보다 얇은 건 성격 차이다 — [fix] 는 이미지를 굽지 않고 **패치 스펙**을
#   낸다. 그래서 「빌드가 되나」가 아니라 **「배포돼도 되는 모양인가」**가 1급 검사다.
set -eu

G=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$G/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3

fail=0

# 🔴 **패치 스펙에 원본 바이트가 없나.** 이 JSON 은 웹 패처 HTML 에 통째로 인라인돼
#    공개 배포된다 — 한 번 새면 원저작물 조각을 배포하는 셈이다(루트 CLAUDE.md 「저작권」).
echo "  ── 패치 스펙 (원본 바이트 · 스키마 · 결과 지문)"
"$PY" "$G/tools/check_patches.py" 2>&1 | sed 's/^/   /' || fail=1

# 웹 패처가 실제로 빌드되나 — 스펙이 유효해도 인라인 단계에서 깨지는 자리가 있다.
echo "  ── 웹 패처 빌드"
if [ -f "$ROOT/patcher/build.py" ]; then
  # 산출물은 버린다 — **빌드가 되나만 본다.** 배포본은 `scripts/patcher.sh` 가 만든다.
  out="$ROOT/.local/patcher-check.html"
  mkdir -p "$ROOT/.local"
  if "$PY" "$ROOT/patcher/build.py" --out "$out" >/dev/null 2>&1; then
    echo "     ✅ 통과 ($(wc -c <"$out" | tr -d ' ')B)"
    rm -f "$out"
  else
    echo "     ❌ 실패 — python3 patcher/build.py --out $out"
    fail=1
  fi
else
  echo "     – patcher/build.py 가 없다"
fi

exit "$fail"
