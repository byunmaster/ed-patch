#!/bin/sh
# pce-ed1 커밋 전 게이트 — scripts/check.sh 가 부른다.
#
# 보는 것: **입력 지문 · 분모(씬 컨테이너 · 전투 컨테이너) · 빌드**.
# 빌드가 곧 절반이다 — 무변경 구간 대조 · 되읽기 · EDC/ECC 자기검증을 build.py 가 안에서 돌린다.
# 게이트는 **지금 고칠 수 있는 것**만 실패로 친다(루트 CLAUDE.md).
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3
T="$ROOT/games/pce-ed1/tools"

echo "== pce-ed1 =="

# 1. 원본 지문 + IPL + 트랙 22 복제 — 소장본이나 섹터 모델이 바뀌면 여기서 죽는다
"$PY" "$T/common.py"

# 2. 시나리오 컨테이너 — 24개 · 332블록 · 고유 220 · 13.3만 자 (+ 참조표 분모). 스캐너·디코더가 흔들리면 운다
"$PY" "$T/containers.py" --check

# 3. 전투 컨테이너 — 6개 · 100블록 · 레코드 259 · 이름 224. 이름칸 파서가 흔들리면 운다
"$PY" "$T/battle.py" >/dev/null

# 4. 빌드 — 코드 패치 사전조건 · 시스템 문구 자리 · 컨테이너 재조립 · 무변경 대조 · 되읽기
"$PY" "$T/build.py"
