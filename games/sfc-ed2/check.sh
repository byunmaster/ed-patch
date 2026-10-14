#!/bin/sh
# sfc-ed2 커밋 전 게이트 — scripts/check.sh 가 부른다.
#
# ⚠ 아직 빌드·번역이 없다(기계 작업 라운드 — 조사 단계). 지킬 수 있는 것만 본다:
#   원본 지문·내부 헤더 · 글꼴 표 추출 · 대본 후보 스캐너 재현. 게이트는 지금 고칠 수 있는 것만 실패로 친다.
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3
T="$ROOT/games/sfc-ed2/tools"

echo "== sfc-ed2 =="

# 1. 원본 지문 + 내부 헤더(HiROM) + 체크섬 합
"$PY" "$T/common.py"

# 2. 글꼴 — 12×12 전각 글리프 색인 $9C 가 읽히는가(좌표·배열이 틀리면 형태가 깨진다)
"$PY" "$T/font.py" 0x9c >/dev/null

# 3. 대본 후보 스캐너 — 덩이 수가 흔들리면(코드 규칙·상한 변경) 운다
"$PY" "$T/scan_text.py" | head -1 | grep -q "덩이 2335개 · 글자 137,975"

# 4. 대사 문법 — 메시지 단위 수·글자 수가 흔들리면(토큰 규칙 변경) 운다. 문법 밖에서 끊긴 덩이는 17(UI·코드 섞인 자리)
"$PY" "$T/script.py" | grep -q "메시지 단위 2,621개 · 전각 글자 118,386 · 문법 밖에서 끊긴 덩이 17"
"$PY" "$T/segs.py" | grep -q "글자 구간 3,510개"

# 5. 빌드 — textmap 번역을 얹은 2MB 롬: 코드 패치 단언 · 무변경 구간 대조 · 헤더 체크섬 · 결정성(두 번 빌드 sha1 대조). 일본어 잔량은 정보(--strict 는 번역 뒤)
"$PY" "$T/build.py" --twice | grep -q "sha1="

# 6. 글리프표 — 1,284자 길이 불변식(한 글자라도 빠지면 이후 색인이 전부 밀린다)
"$PY" "$T/glyphmap.py" | grep -q "글리프표 1284자"

