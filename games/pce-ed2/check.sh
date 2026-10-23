#!/bin/sh
# pce-ed2 커밋 전 게이트 — scripts/check.sh 가 부른다.
#
# 지금(뼈대 단계)은 **입력 지문 · IPL · 디스크 구조 계약**만 본다. 빌드·조판 지문은 파이프라인이 서면 더한다.
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3
T="$ROOT/games/pce-ed2/tools"

echo "== pce-ed2 =="

# 1. 원본 지문 + IPL + 트랙 구조(데이터 트랙 길이 · 뒤쪽 복제 구간) — 소장본이나 섹터 모델이 바뀌면 여기서 죽는다
"$PY" "$T/common.py"

# 2. 대본 스트림 앵커 — 디코더·좌표가 에뮬 체크포인트(링 256B · 쓰기 인덱스)와 바이트까지 맞아야 한다
"$PY" "$T/stream.py"

# 3. 씬 패키지 — 머리표 4번 메시지 포인터 표가 가리키는 대본 덩이가 각자 다음 시작에 정확히 닿아야 한다
"$PY" "$T/package.py" --check

# 4. 빌드(트랙 1~2 만, 편집 없음 = 후킹 루틴 + 글리프 풀 0자) — 쓰기 사전조건(0xFF 패딩) · 무변경 대조 · 되읽기 · EDC/ECC 자기검증
"$PY" "$T/build.py" --trim

# 5. 배포 칸의 이미지가 전 트랙인가(오디오 포함) — 잘린 에뮬용이 거기 있으면 BGM 이 안 난다
"$PY" "$T/check_build_layout.py"

# 5-2. 제어 낀 줄 틀(`data/ctrl_lines.tsv`) — 모든 틀이 원본 줄에 맞고(낡은 틀 0) 제어 번호·구조 제어 검증을 통과해야 한다
"$PY" "$T/ctrllines.py" --verify

# 6. 번역 규칙 부호(2-11 문장 맨 앞 … 뒤 붙임 · 2-12 …가 ?!보다 앞) — 우리 문안 전체
"$PY" "$T/check_punct.py"
