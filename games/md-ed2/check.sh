#!/bin/sh
# md-ed2 커밋 전 게이트 — scripts/check.sh 가 부른다.
#
# 지금은 **기계 작업 1단계**라 입력 지문 · 아카이브 분모 · 코덱 왕복 · 씬 모듈 분모만 본다.
# 빌드(build.py)·조판·이름 검사는 파이프라인이 서면 ED1(games/md-ed1/check.sh)을 따라 더한다.
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3
T="$ROOT/games/md-ed2/tools"

echo "== md-ed2 =="

# 1. 원본 지문 + 헤더 체크섬 + 꼬리 빈 공간 — 소장본이 바뀌면 여기서 죽는다
"$PY" "$T/common.py"

# 2. 아카이브 7 · 대본 90블록(씬 모듈 356) — 색인·디코더·분할 표가 흔들리면 운다
"$PY" "$T/archives.py"

# 3. 씬 모듈 — 스트림 3,468 · 화자 태그 2,028/2,028 도달(고아 52) · 항등 재조립 실패 0
"$PY" "$T/scene.py"

# 4. 엔진 대응표 — ED1 후킹 자리의 ED2 주소(바이트 지문)
"$PY" "$T/engine.py" --check

# 5. 빌드 게이트 — 원본 지문 · 대본 아카이브 재배치(여유 · 왕복) · 쓰기 구간. 번역 정본이 아직 없어 문안은 원본 그대로다
"$PY" "$T/build.py" --check

# 6. 코드 영역 문안 census — 참조로 잡히는 스트림 178 · 스트림 밖 일본어 808런(캡션·이름 표·메뉴 라벨 등 — 번역 때 분류)
"$PY" "$T/sysmsg.py"

# 7. 타이틀 시작 메뉴 셀 폰트 — ED1(0x19ACD0)과 바이트 동일한 롬 0xEB3A0(셀 0~69, 지문 고정) · 커서 Y 명령(0x16202)이 원본인지
"$PY" "$T/gfxtext.py" --check

# 8. 한글 코드 배정 — 커밋본과 대조(세이브 호환: 이미 있던 글자는 코드가 안 밀린다) · 글꼴 구역 지문
"$PY" "$T/hangul.py" --check
