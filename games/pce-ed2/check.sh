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

# 5-1. 구조 대조(마스터 10-22 「재배치사고 막는 정적검사」) — 원본과 새 이미지의 모든 대사 덩이·줄에서 글자 바이트를 뺀 제어 열을 맞댄다(표·별칭 · 덩이 이음 · 줄 수 · 구조 제어 · FF 채움).
#      허용(쪽 넘김 증감 · 틀 · 상수 이름)은 규칙으로 검출해 개수를 센다 — 그 밖의 어긋남은 실패. 재배치 장부(`relocations.tsv`)는 빌드가 한 재배치에서 자동으로 뽑고 커밋된 것과 다르면 실패.
"$PY" "$T/structcheck.py" --gate --iso "$ROOT/games/pce-ed2/work/build/test-pce-ed2-trim/ed2.iso"
"$PY" "$T/relocations.py" --gate --iso "$ROOT/games/pce-ed2/work/build/test-pce-ed2-trim/ed2.iso"

# 5-1b. 글자색 제어 대조(마스터 10-29 「대사 색상코드 누락 점검」) — 원판과 구운 바이트의 `14`·`15 nn`·`17`·`18` 열이 같아야 한다(대사 덩이 · 본 프로그램 문자열 · 표 · 장면 코드 문자열 · 章間). `06`/`04` 는 색이 아니라 글자 방식이라 대상 밖.
"$PY" "$T/check_colors.py" --gate --iso "$ROOT/games/pce-ed2/work/build/test-pce-ed2-trim/ed2.iso"

# 5-1d. 이음 대조(마스터 10-30 「보물상자처럼 띄어쓰기 개행 제대로 안 된 게 꽤 있을 것 같은데」) — 변수 자리 바로 앞이 한글(공백 없음) · 원판이 개행으로 끝나는데 한글은 아님 · 대사 쪽이 창(4줄)을 넘김.
"$PY" "$T/check_joints.py" --gate --iso "$ROOT/games/pce-ed2/work/build/test-pce-ed2-trim/ed2.iso"

# 5-1e. 조판 전수(구운 바이트, 마스터 10-31 「조판검사할 때 첫칸공백·고아부호·빈줄개행·여러 창 균등 분배」 + 4-6 색 제어) — 대사·전투·시스템 문안을 이미지에서 직접 훑어
#       첫 칸 공백 · 고아 부호 · 빈 줄 · 부호 뒤 공백 · 마지막 쪽 한 어절 · 쪽 끝 한 어절 · 넘침 · 색 제어 누락·번짐을 센다(원판도 같은 꼴이면 「원판 동일」로 따로 센다). 기준선(layout_baseline.json) 래칫.
"$PY" "$T/check_layout.py" --gate --iso "$ROOT/games/pce-ed2/work/build/test-pce-ed2-trim/ed2.iso"

# 5-1f. 연출 멈춤 개수(11-07, 관리자 지시) — 원판 줄마다 `11 nn nn` 개수가 제품 줄과 같은가(빌드 산출물 대조). 번역·조판이 원판 멈춤을 조용히 지우면 운다. 기준선(data/pause_count_baseline.tsv) 래칫.
"$PY" "$T/check_pauses.py" "$ROOT/games/pce-ed2/work/build/test-pce-ed2-trim/ed2.iso"

# 5-1h. 원판 사본 잔존(11-17, 마스터 「이런 케이스가 다른 기종·게임에도?」 — pce-ed1 에서 원판에 대사 블록 사본이 고친 자리 밖에 따로 있어 정상 진행이 그 사본을 읽었다)
#        고친 덩어리(평문·압축 모두)의 원판 바이트를 **이미지 전체**에서 찾아, 제품에 원판 그대로 남은 사본이 알려진 목록(`data/orig_copies_known.tsv`) 밖에 있으면 실패.
"$PY" "$T/check_orig_copies.py" "$ROOT/games/pce-ed2/work/build/test-pce-ed2-trim/ed2.iso" --gate

# 5-1i. 항목 토큰이 그리는 원문 가나 잔존(11-17 — 상점 판매 줄 「천 옷は은」): 번역한 줄의 `1D xx`(항목 이름 + 조사 가나)가 빈 칸(`60`)이 아니면 실패.
#        잔존 게이트(5-1 · residual)는 가나 4자↑ 연속·원문 글리프 줄을 보므로 제어 토큰이 그리는 가나 한 글자는 못 본다.
"$PY" "$T/check_item_kana.py" "$ROOT/games/pce-ed2/work/build/test-pce-ed2-trim/ed2.iso" --gate

# 5-1g. 패턴 치환 자리 전수(11-07 관리자 공지 — SFC II 프리징: 패턴 검색→치환이 우연히 같은 바이트의 자료까지 고침) — 리터럴·표 즉치·장면 패키지 호출이 전부 실제 명령 경계인가(기준선 래칫).
#        짝으로 빌드가 「쓴 섹터 안 바뀐 바이트 전수 = 쓰기 장부 안」(`build.verify_declared_bytes`)을 본다.
"$PY" "$T/pattern_audit.py"

# 5-1c. 마스터 판정 문안(`master_rulings.json`, 10-30) — 마스터가 정한 꼴(금지·필수)이 구운 한글 문안에 지켜지나. 검수·재조판이 판정을 되돌리면 운다. 공용 판정기 + 게임 말뭉치 어댑터(`tools/rulings_corpus.py`).
"$PY" "$ROOT/scripts/check/master_rulings.py" --game pce-ed2

# 5-2. 제어 낀 줄 틀(`data/ctrl_lines.tsv`) — 모든 틀이 원본 줄에 맞고(낡은 틀 0) 제어 번호·구조 제어 검증을 통과해야 한다
"$PY" "$T/ctrllines.py" --verify

# 6. 번역 규칙 부호(2-11 문장 맨 앞 … 뒤 붙임 · 2-12 …가 ?!보다 앞) — 우리 문안 전체
"$PY" "$T/check_punct.py"

# 6-0a. 화자 이름 반복(11-18, pce-ed1 부류) — 화자 머리 바로 뒤 본문이 같은 이름으로 시작하는데 원판은 아닌 줄(「카자즘 크하하하」 1282:67:1 — 원문은 웃음소리뿐).
"$PY" "$T/check_name_repeat.py" --iso "$ROOT/games/pce-ed2/work/build/test-pce-ed2-trim/ed2.iso"

# 6-0b. 막간(章間) 자막 줄 폭·줄 수·줄 경계(이름+직함 · 숫자+단위 · 「이름 N세」 를 가르면 실패 — 마스터 11-22 「막간도 줄바꿈 검수」)
"$PY" -c "import sys; sys.path.insert(0, '$T'); sys.path.insert(0, '$ROOT/shared'); import kanma; e = kanma.check_ko(); print('  막간 자막 [pce-ed2] — 줄 폭·줄 수·붙임 쌍 어긋남', len(e)); [print('   ', x) for x in e]; sys.exit(1 if e else 0)"

# 6-0. 말투 경보(11-13) — 대사 「그대」 금지(4-16) · 원문 대비 길이 급감 · 반말 줄 「-시-」 혼입(참고). 음성 자막은 안 본다.
"$PY" "$T/check_speech.py"

# 6-1. 줄·쪽 나눔 지표 래칫(번역 규칙 2-16, 마스터 10-26) — 쪽 끝 고아 · 낱말 쪽 · 문장 중간 손 개행 · 절째 내리면 들어가는 쪽갬 줄을 조판 결과로 센다. 기준선보다 늘면 실패.
"$PY" "$T/check_linebreak.py"

# 6-1b. 조판 지문(공용 krwrap 이 이 게임 줄바꿈을 조용히 바꾸면 운다) — 구역별 해시(대사 패키지 · 틀 · 오프닝/엔딩 자막). 문안을 의도적으로 바꿨을 때만 `--freeze`(값은 games/pce-ed2/typeset_fingerprint.json).
"$PY" "$ROOT/scripts/check/typeset_fingerprint.py" --game pce-ed2

# 6-2. 조사 전수(정본 고유명사 × 뒤 조사 받침 대조) — 이름을 바꾸고 조사를 안 고친 줄(「슬러그이」 류)
"$PY" "$T/check_josa.py"

# 6-3. 짝 경계(`data/align_map.json` — PCE 줄 ↔ PS1 블록 구간) — 이웃 블록 덧붙음 · 변형 대사 중복 · 구간 모자람(누락)을 PCE 원문 줄에 맞대어 전수 본다(10-20 style 검수 — 「레스의 책을 받았습니다」가 시녀 대사 앞에 붙은 부류).
#     PS1 일문 덤프(`games/ps1-ed1+2/work/derived/scn_jp`)가 없으면 못 잰다 — 통과가 아니라 실패로 친다.
"$PY" "$T/align_check.py" --gate
