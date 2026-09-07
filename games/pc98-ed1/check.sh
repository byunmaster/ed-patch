#!/bin/sh
# pc98-ed1 커밋 전 게이트 — scripts/check.sh 가 부른다.
#
# ⚠ 아직 빌드가 없다(쓰기 경로를 안 만들었다 — patcher-checklist 2). 지금 지킬 수 있는 건
#   **입력 지문 · 판정의 재현 · 덤프의 무손실**이라 그 셋을 본다.
#   게이트는 **지금 고칠 수 있는 것**만 실패로 친다(루트 CLAUDE.md).
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3
T="$ROOT/games/pc98-ed1/tools"

echo "== pc98-ed1 =="

# 1. 원본 지문 + 섹터 모델 — 소장본이나 d88 리더가 바뀌면 여기서 죽는다
"$PY" "$T/common.py"

# 2. 폰트 소재 판정 — 「게임이 CGROM 을 직접 읽는다」가 뒤집히면 설계 전제가 무너진다
"$PY" "$T/probe_font.py" >/dev/null
echo "폰트 소재 판정 재현 OK (CG 루틴 9곳)"

# 3. 시나리오 디렉터리 — 224건이 553섹터를 정확히 채우나
"$PY" "$T/scn.py"

# 4. 대본 덤프 라운드트립 — 🔴 이게 깨지면 저본을 못 믿는다
"$PY" "$T/dump_scn.py" | sed 's/^/    /'
"$PY" "$T/dump_sys.py" | sed 's/^/    /'

# 5. 한글 글리프 표 — 결정성 + 얼린 지문
"$PY" "$T/font.py" --check | sed 's/^/    /'

# 6. 메모리 판독의 서명 — 폰트를 올릴 자리(세그먼트 0x4000)의 전제가 살아 있나
"$PY" "$T/memmap.py" >/dev/null
echo "메모리 지도 판독 재현 OK (뱅크 검사 3곳)"
