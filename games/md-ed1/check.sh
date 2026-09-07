#!/bin/sh
# md-ed1 커밋 전 게이트 — scripts/check.sh 가 부른다.
#
# ⚠ 아직 빌드가 없다(쓰기 경로를 안 만들었다 — patcher-checklist 2). 지금 지킬 수 있는 건
#   **입력 지문 · 아카이브 분모의 재현 · 글꼴 형상 · 코덱 왕복**이라 그 넷을 본다.
#   게이트는 **지금 고칠 수 있는 것**만 실패로 친다(루트 CLAUDE.md).
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3
T="$ROOT/games/md-ed1/tools"

echo "== md-ed1 =="

# 1. 원본 지문 + 헤더 체크섬 + 꼬리 빈 공간 — 소장본이 바뀌면 여기서 죽는다
"$PY" "$T/common.py"

# 2. 아카이브 — 대본 225블록 663,896B · 전투 110블록. 색인·디코더가 흔들리면 운다
"$PY" "$T/archives.py" --check

# 3. 글꼴 — 리소스 6 · 14×14 두 면 · SJIS 1,459자
"$PY" "$T/font.py" --check

# 4. 씬 모듈 — 스트림 2,752 · 화자 태그 1,425/1,437 도달(나머지 12 는 참조 없는 죽은 문안) · 225블록 항등 재조립이 다시 파싱해 같다
"$PY" "$T/scene.py" --check
