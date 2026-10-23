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

# 5b. 🔴 **실제 빌드를 돌린다** — `--check` 는 쓰기 직전에 return 해서 전투 이름 칸·sysmsg 칸·읽기 게이트(롬 전체 잔존)를 안 본다.
#     정본이 칸보다 길어져 빌드가 멈추는데도 check.sh 가 rc 0 이던 구멍(10-18 「붉은 슬러그Ｂ″」 16B>15B). 낡은 롬이 정상으로 읽히지 않게 지우고 시작하고,
#     빌드가 실패하면 set -e 로 여기서 멈추며, 끝나고 롬이 없으면(실패 산출물은 *.failed) 실패시킨다.
BUILD_TAG_DIR=$("$PY" -c "import sys;sys.path.insert(0,'$T');import common as C;print(C.BUILD_DIR/C.BUILD_TAG)")
rm -f "$BUILD_TAG_DIR"/*.bin "$BUILD_TAG_DIR"/*.failed
"$PY" "$T/build.py"
ls "$BUILD_TAG_DIR"/*.bin >/dev/null 2>&1 || { echo "❌ 빌드 산출물이 없다 — 빌드가 실패했다"; exit 1; }

# 5c. 🔴 구운 글리프 중복 — 롬에서 읽은 비트맵이 서로 같은 코드(특히 `,`·`.` · `、`·`。`)가 있으면 실패. 원본 글꼴 파일이 아니라 **구운 롬**을 본다
#     (ss-ed1+2 가 행 맞춤으로 쉼표 꼬리가 잘려 쉼표 3,983곳이 마침표로 그려졌다, 10-20). 원판이 이미 같게 그린 묶음·설계상 같은 묶음만 허용 목록에 있다.
"$PY" "$T/glyph_dupes.py" "$BUILD_TAG_DIR"/*.bin

# 5d. 🔴 런타임 제어 바이트 토글 — 원판 코드가 `lea d(pc),aN` 로 글 스트림 안 바이트를 덮는 자리(전투 블록·씬 모듈)가 한글 롬에서도 같은 바이트를 가리키는지.
#     md-ed1 에서 「하이 길도」 빈 글리프·문장 누락으로 나왔다(10-20). 쓰기 자리 n · 어긋남 m, 어긋남이 있으면 실패. 허용·중화는 ctl_toggle_scan.py 의 표(사유 포함).
"$PY" "$T/ctl_toggle_scan.py" "$BUILD_TAG_DIR"/*.bin

# 5e. 🔴 구조 대조 — 원판과 구운 롬의 모든 대사 블록(씬 모듈 356 · 전투 99)을 「제어 코드 열」(글자·쪽·줄 배치를 뺀 goto·call·조건·종결·인자)로 블록마다 맞댄다.
#     ss-ed3 10-21: 재조판 때 끝에 넣은 채움 바이트가 다음 블록 호출을 막아 첫 장면 대사가 빠졌다(하네스·한 블록씩 보기로는 안 보인다). 허용 목록은 struct_check.py(사유 + 엔진 근거).
#     재배치 장부(games/md-ed2/relocations.tsv)가 빌드와 다르면(= 장부에 없는 재배치) 같이 실패한다. 갱신: struct_check.py --update-ledger
"$PY" "$T/struct_check.py" "$BUILD_TAG_DIR"/ed2-kr.bin

# 6. 코드 영역 문안 census — 참조로 잡히는 스트림 178 · 스트림 밖 일본어 808런(캡션·이름 표·메뉴 라벨 등 — 번역 때 분류)
"$PY" "$T/sysmsg.py"

# 7. 타이틀 시작 메뉴 셀 폰트 — ED1(0x19ACD0)과 바이트 동일한 롬 0xEB3A0(셀 0~69, 지문 고정) · 커서 Y 명령(0x16202)이 원본인지
"$PY" "$T/gfxtext.py" --check

# 8. 한글 코드 배정 — 커밋본과 대조(세이브 호환: 이미 있던 글자는 코드가 안 밀린다) · 글꼴 구역 지문
"$PY" "$T/hangul.py" --check

# 9. 이름·라벨 표 — 정본·사전에서 읽은 표 집계(아이템 139 · 주문 33 · 지명 5 · 메뉴 라벨 …). 정본에 없는 라벨은 건수만 알린다(관리자 후보 대기)
"$PY" "$T/dict_names.py"

# 10. 후킹 — 조사 훅(EB·EC) · 어절 줄넘김 · 반각 부호 줄 끝 · 「의␣」: 자리가 원본 그대로인가 · 기계어 크기
"$PY" "$T/josa.py" --check
"$PY" "$T/wordwrap.py" --check
"$PY" "$T/punctwrap.py" --check
"$PY" "$T/halfspace.py" --check

# 11. 장 카드·HUD 장 제목 — 정본 장 제목 범주에서 만든 문안이 원본 스트림 자리와 맞는지(HUD 30B 계약) · 카드 스트림 제목 일치
"$PY" "$T/chapters.py" >/dev/null

# 12. 오프닝·엔딩 자막 — 표 넷 · 스트림 25 분모, 줄 폭·줄 수 (되읽기는 build.py)
"$PY" "$T/captions.py"
"$PY" "$T/places.py"
"$PY" "$T/field_hud.py"
"$PY" "$T/spell_digit.py"
"$PY" "$T/hud_status.py"
"$PY" "$T/banners.py"

# 13. 번역 규칙 2-11 — 「…」 뒤 공백
"$PY" "$T/check_ellipsis.py"

# 14. 코드 영역 문안(sysmsg) 커버리지 — 화면에 나가는데 번역이 빈 스트림·번역 속 가나(기준선 래칫, 엔딩 대사 19스트림이 빈 채 초록이던 구멍 10-13)
"$PY" "$T/check_sysmsg_gaps.py"


# 15. 명사 목록 × 조사 받침 — 정본 고유명사 뒤 이/가·은/는·을/를·과/와·으로/로 가 받침에 맞는가(이름을 바꾸며 조사를 안 고친 꼴 — 「슬러그이」 8곳, 10-18)
"$PY" "$T/check_josa_nouns.py"
