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
"$PY" "$T/battle.py" --check

# 4. 조사 일치 — 주입 토큰(이름·아이템) 뒤에 고정 조사를 쓴 자리(P2 를 닫는 게이트)
"$PY" "$T/check_josa.py"

# 4-b. 사전 대조 — 원문의 정본 이름이 우리 줄에 정본 표기로 있나(라운드⑥ 닫힘 조건 「다른 표기 잔존 0」)
"$PY" "$T/check_glossary.py"

# 4-c. 화면 일본어 0 — 대사 외 자리(메뉴·시스템·전투·HUD·배너)에 가나·한자가 남지 않았나
"$PY" "$T/check_jp_left.py"

# 4-d. 나레이션 싱크 — 음성 토막마다 자막 시간이 음성 길이 ±1.5초 안(늘린 뒤). 미해결은 OPEN_RUNS 에 사유와 함께
"$PY" "$T/voice_sync.py" --check

# 5. 글리프 정본 — 코드가 세이브(BRAM)에 남으므로 순서를 못 흔든다. 새 글자는 덧붙이기만
"$PY" "$T/freeze_glyphs.py" --check

# 6. 빌드 — 코드 패치 사전조건 · 시스템 문구 자리 · 컨테이너 재조립 · 무변경 대조 · 되읽기
"$PY" "$T/build.py"

# 7. 조판 지문 — 공용(shared/text)이 이 게임의 줄바꿈을 흔들면 운다. 문안을 의도적으로 바꿨을 때만 --freeze
echo "-- 조판 지문 --"
"$PY" "$ROOT/scripts/check/typeset_fingerprint.py" --game pce-ed1
