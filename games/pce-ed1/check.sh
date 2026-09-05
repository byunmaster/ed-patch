#!/bin/sh
# pce-ed1 커밋 전 게이트 — scripts/check.sh 가 부른다.
#
# ⚠ 아직 빌드가 없다(쓰기 경로를 안 만들었다 — patcher-checklist 2). 지금 지킬 수 있는 건
#   **입력 지문 · 컨테이너 스캔의 재현 · 코덱 왕복**이라 그 셋을 본다.
#   게이트는 **지금 고칠 수 있는 것**만 실패로 친다(루트 CLAUDE.md).
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3
T="$ROOT/games/pce-ed1/tools"

echo "== pce-ed1 =="

# 1. 원본 지문 + IPL + 트랙 22 복제 — 소장본이나 섹터 모델이 바뀌면 여기서 죽는다
"$PY" "$T/common.py"

# 2. 시나리오 컨테이너 — 23개 · 318블록 · 고유 214 · 12.8만 자. 스캐너·디코더가 흔들리면 운다
"$PY" "$T/containers.py" --check
