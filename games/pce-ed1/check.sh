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

# 4-a2. 정본 이름 뒤 조사 받침 — 명사 목록 기반 전수(우리 문안 전체 × 정본 이름 × 이/가·은/는·과/와·을/를, 10-18)
"$PY" "$T/check_josa_names.py"
"$PY" "$T/check_pua.py"

# 4-b. 사전 대조 — 원문의 정본 이름이 우리 줄에 정본 표기로 있나(라운드⑥ 닫힘 조건 「다른 표기 잔존 0」)
"$PY" "$T/check_glossary.py"

# 4-c. 화면 일본어 0 — 대사 외 자리(메뉴·시스템·전투·HUD·배너)에 가나·한자가 남지 않았나
"$PY" "$T/check_jp_left.py"

# 4-c2. 씬 번역 전체 재검증 — 일본어 잔존 · 글리프 · 조판 여섯 규칙(고아 부호 · 첫 칸 공백 · 빈 줄 · 낱말 가운데 끊김). 장 끝 카드는 verbatim 이라 ④ 를 안 댄다
"$PY" "$T/scene_check.py"

# 4-c3. 포인터 목표 — 씬 블록 안 포인터(모든 16비트 값 후보)가 가리키는 글이 번역 단위 목록 밖이면 실패(10-18). 점프 피연산자와 붙은 런을 통째로 버리던 파서 구멍(대사 68개)이 이걸로 드러났다
"$PY" "$T/check_ptr_targets.py"

# 4-d. 나레이션 싱크 — 음성 토막마다 자막 시간이 음성 길이 ±1.5초 안(늘린 뒤). 미해결은 OPEN_RUNS 에 사유와 함께
"$PY" "$T/voice_sync.py" --check

# 4-d2. 부호 규칙 — 공통 번역 규칙 2-11(… 뒤 공백)·1-7(～ 뒤 마침표 금지)
"$PY" "$T/typeset_check.py" --punct

# 4-e. 자기 표 0 — 게임 폴더에 일본어 열쇠→한글 값 표가 새로 생기지 않았나(사전·정본에서 읽는다, 마스터 10-08)
"$PY" "$T/check_own_tables.py"

# 5. 글리프 정본 — 코드가 세이브(BRAM)에 남으므로 순서를 못 흔든다. 새 글자는 덧붙이기만
"$PY" "$T/freeze_glyphs.py" --check

# 6. 빌드 — 코드 패치 사전조건 · 시스템 문구 자리 · 컨테이너 재조립 · 무변경 대조 · 되읽기
"$PY" "$T/build.py"

# 6-b. 롬 전체 잔존 일본어 — 디스크를 직접 훑어 빌드가 안 바꾼 일본어 런(4자 이상)이 기준선(`script/coverage_baseline.json`) 밖에 생기면 실패(10-18).
#      기준선의 부류별 수는 `coverage_scan.py` 출력 — 「화면 문장 후보 — 미판정」 15런은 번역 대상일 수 있다
"$PY" "$T/coverage_scan.py" --check

# 7. 조판 지문 — 공용(shared/text)이 이 게임의 줄바꿈을 흔들면 운다. 문안을 의도적으로 바꿨을 때만 --freeze
echo "-- 조판 지문 --"
"$PY" "$ROOT/scripts/check/typeset_fingerprint.py" --game pce-ed1
