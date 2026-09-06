#!/bin/sh
# sfc-ed1 커밋 전 게이트 — scripts/check.sh 가 부른다.
#
# ⚠ 아직 빌드가 없다(쓰기 경로를 안 만들었다 — patcher-checklist 2). 지금 지킬 수 있는 건
#   **입력 지문 · 포인터 표/사전 스캔의 재현 · 문자표 불변식**이라 그 셋을 본다.
#   게이트는 **지금 고칠 수 있는 것**만 실패로 친다(루트 CLAUDE.md).
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3
T="$ROOT/games/sfc-ed1/tools"

echo "== sfc-ed1 =="

# 1. 원본 지문 + 내부 헤더 — 소장본이 바뀌거나 손댄 롬이면 여기서 죽는다
"$PY" "$T/common.py"

# 2. 대본 — 포인터 표 4벌(3339·433·343·19) · 사전 6벌 · main 글자 177,108B. 스캐너가 흔들리면 운다
"$PY" "$T/text.py" --check

# 3. 스크립트 라벨 모델 — 본체 153KB 를 라벨로 풀어 오프셋을 다시 계산해 되쓰면 바이트가 같아야 한다
"$PY" "$T/script.py" --roundtrip

# 4. 배치기 — 확장 뱅크로 옮겨 쓴 롬을 되읽어 원본 디코드와 대조 + 무변경 구간 byte 대조(파일은 안 남긴다)
"$PY" "$T/build.py" --check

# 5. 번역 정본 — textmap 의 번역문이 조각의 토큰(사전·제어)을 전부 같은 순서로 품는가(원문 덤프를 먼저 낸다)
"$PY" "$T/units.py" --dump >/dev/null
"$PY" "$T/textmap.py" --check
