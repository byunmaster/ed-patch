#!/bin/sh
# 이 게임의 커밋 전 게이트 — [kr] 새턴 『백의 마녀』.
#
#   sh games/ss-ed3/check.sh      (보통은 `sh scripts/check.sh` 가 부른다)
#
# ⚠ 아직 **이미지를 굽지 않는다**(정적 분석 단계). 그래서 「빌드가 되나」가 아니라
#   **「원본을 읽는 전제가 그대로인가」**가 1급 검사다. 재삽입이 서면 여기에 빌드가 붙는다.
#
# 🔴 이 게임의 뿌리 전제는 **2디스크 계약**이다 — 「양쪽에 있는 파일은 바이트 동일,
#    갈리는 건 매체뿐」. 이게 깨지면 「문안을 한 벌만 만든다」는 설계가 통째로 무너진다.
set -eu

G=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$G/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3

fail=0

# 원본이 없는 트리(다른 워크트리·CI)에서는 **건너뛴다.** 늘 빨간불인 게이트는 아무도 안 본다.
if [ ! -d "$ROOT/originals/jp/ss-ed3" ]; then
  echo "  ⏭ originals/jp/ss-ed3 가 없다 — 원본이 필요한 검사는 건너뛴다"
  exit 0
fi

echo "  ── 원본 지문 · 2디스크 계약"
"$PY" "$G/tools/common.py" 2>&1 | sed 's/^/   /' || fail=1

# 🔴 **덤프 라운드트립** — 경계가 한 칸이라도 밀리면 재삽입이 옆 바이트를 먹는다.
#    두 디스크 다 본다(같은 한 벌이라는 계약을 텍스트 층에서도 다시 확인하는 셈이다).
echo "  ── 번역이 그 블록의 것인가 (원문 지문)"
"$PY" "$G/tools/stamp_script.py" --check 2>&1 | sed 's/^/   /' || fail=1

echo "  ── 말투 (한 블록 안에서 높임과 반말이 섞였나)"
# ⚠ 경고지 실패가 아니다 — 한 블록 안에서 말 상대가 바뀌는 자리가 실제로 있다
"$PY" "$G/tools/check_speech.py" 2>&1 | tail -3 | sed 's/^/   /' || true

echo "  ── 원문에 있던 것이 사라지지 않았나 (숫자 · 고유명사)"
"$PY" "$G/tools/check_fidelity.py" 2>&1 | tail -3 | sed 's/^/   /' || true

echo "  ── 덤프 라운드트립 (대사 · 시스템 · 두 디스크)"
for n in 1 2; do
  "$PY" "$G/tools/dump_map.py" --disc "$n" --check 2>&1 | sed 's/^/   /' || fail=1
  "$PY" "$G/tools/dump_sys.py" --disc "$n" --check 2>&1 | sed 's/^/   /' || fail=1
done

if [ "$fail" -ne 0 ]; then
  echo "  ❌ [ss-ed3] 게이트 실패"
  exit 1
fi
echo "  ✅ [ss-ed3] 통과"
