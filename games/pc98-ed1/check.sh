#!/bin/sh
# pc98-ed1 커밋 전 게이트 — scripts/check.sh 가 부른다.
#
# ⚠ 아직 빌드가 없다(쓰기 경로를 안 만들었다 — patcher-checklist 2). 지금 지킬 수 있는 건
#   **입력 지문 · 판정의 재현 · 덤프의 무손실**이라 그 셋을 본다.
#   게이트는 **지금 고칠 수 있는 것**만 실패로 친다(루트 CLAUDE.md).
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3
T="$ROOT/games/pc98-ed1/tools"
OUT=$(mktemp)
trap 'rm -f "$OUT"' EXIT

# 🔴 **`cmd | sed` 는 실패를 삼킨다** — 파이프의 종료 코드는 마지막 명령(`sed`) 것이다.
#    실측 2026-09-06: 빌드가 SJIS 불가 문자로 죽었는데 게이트가 ✅ 를 찍었다.
#    `sh` 는 `pipefail` 이 없으므로(dash) **파일로 받아** 종료 코드를 직접 본다.
run() {
  if "$@" > "$OUT" 2>&1; then
    sed 's/^/    /' "$OUT"
  else
    sed 's/^/    /' "$OUT"
    echo "❌ 실패: $*"
    exit 1
  fi
}

echo "== pc98-ed1 =="

# 1. 원본 지문 + 섹터 모델 — 소장본이나 d88 리더가 바뀌면 여기서 죽는다
"$PY" "$T/common.py"

# 2. 폰트 소재 판정 — 「게임이 CGROM 을 직접 읽는다」가 뒤집히면 설계 전제가 무너진다
"$PY" "$T/probe_font.py" >/dev/null
echo "폰트 소재 판정 재현 OK (CG 루틴 9곳)"

# 3. 시나리오 디렉터리 — 224건이 553섹터를 정확히 채우나
"$PY" "$T/scn.py"

# 4. 대본 덤프 라운드트립 — 🔴 이게 깨지면 저본을 못 믿는다
run "$PY" "$T/dump_scn.py"
run "$PY" "$T/dump_sys.py"

# 5. 한글 글리프 표 — 결정성 + 얼린 지문
run "$PY" "$T/font.py" --check

# 6. 메모리 판독의 서명 — 폰트를 올릴 자리(세그먼트 0x4000)의 전제가 살아 있나
"$PY" "$T/memmap.py" >/dev/null
echo "메모리 지도 판독 재현 OK (뱅크 검사 3곳)"

# 7. 번역 정본 — 열쇠가 원문에 붙나(사전 규칙이 바뀌면 여기서 덮인 비율이 떨어진다)
run "$PY" "$T/translate.py" stat

# 7b. 고유명사 — 한 낱말이 우리 문안 안에서 두 표기로 나오나(`rpg-translate` §5)
#     ⚠ 공용 정본과 다른 것은 **보고만** 한다 — 정본이 판정 규칙(`docs/naming.md`)보다
#     낡은 자리가 있다(지명 접미 13종, 2026-09-06 실측).
run "$PY" "$T/check_glossary.py"

# 7c. 표기 꼴 — 전각/반각 숫자·따옴표·일본식 부호가 문안 안에서 섞였나
run "$PY" "$T/check_style.py"

# 7d. 🔴 **안 옮긴 문안이 화면에서 깨지나** — 우리 한글은 원본 한자 구를 **빼앗아** 앉으므로
#     (JIS ku 0x40~0x58) 안 옮긴 자리는 「일본어로 남는」 게 아니라 **엉뚱한 한글로 깨진다.**
#     실측 2026-09-06: 원판 세이브의 `第１章…` 이 슬롯 목록에서 `L 1 ▨▨▨` 로 떴다.
#     ⚠ **계측이지 게이트가 아니다** — 전량을 옮기기 전엔 0 이 될 수 없다.
run "$PY" "$T/check_hijacked.py"

# 8. 🔴 **빌드** — 쓰기 경로가 섰으니 게이트가 이걸 본다(루트 CLAUDE.md 「게임 게이트」).
#    사전조건 다섯(무변경 대조 · 섹터 ID · 빈자리 · 겹침 · 실패 무효화)이 여기서 돈다.
#    ⚠ `work/derived/pierce.json` 이 있으면 2초, 없으면 처음 한 번만 오래 걸린다.
run "$PY" "$T/build.py"

# 9. 🔴 **왕복** — 구운 이미지를 되읽어 정본과 **글자로** 대조한다.
#    `shared/text/sjis.py` 가 못 박은 자리다: 슬롯 계산이 틀리면 화면에만 엉뚱한 글자가
#    나오고 **빌드도 단위 테스트도 통과한다.** 그래서 넣은 것을 되읽는다.
run "$PY" "$T/patch_scn.py" --verify
#    시스템 문안(메뉴·표·전투 메시지)은 **제자리 교체**라 길이가 곧 계약이다.
run "$PY" "$T/patch_sys.py" --verify
