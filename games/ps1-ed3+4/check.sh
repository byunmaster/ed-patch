#!/bin/sh
# 이 게임의 커밋 전 게이트 — [kr] PS1 영웅전설 III·IV.
#
#   sh games/ps1-ed3+4/check.sh      (보통은 `sh scripts/check.sh` 가 부른다)
#
# ⚠ 아직 **이미지를 굽지 않는다**(정적 분석 단계). 그래서 1급 검사는 「빌드가 되나」가
#   아니라 **「대본을 읽는 전제가 그대로인가」**다 — 원본 지문 · 아카이브 규격 · 코드표.
#
# 🔴 이 게임의 뿌리 전제는 **문자 코드표**다. 표가 한 칸이라도 밀리면 빌드도 검사도 다
#    통과하고 **화면에서만** 드러난다(2026-09-03: 주인공이 「ジヤラオ」로 읽혔다).
set -eu

G=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$G/../.." && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3

fail=0

# ⚠ 파이프는 종료 코드를 먹는다 — 출력을 먼저 받고 종료 코드를 따로 본다(ss-ed3 게이트와 같은 이유).
_run() {
  _gate=$1; _tail=$2; shift 2
  _out=$("$@" 2>&1) && _rc=0 || _rc=$?
  if [ "$_tail" -gt 0 ]; then
    # 🔴 `tail` 이 잘라 낸 앞부분의 🔴 줄은 **따로 올린다** — ss-ed1+2 에서 합계 줄이 가려져
    #    일본어가 남은 빌드가 초록으로 보였다(09-27 관리자 공통 점검).
    _n=$(printf '%s\n' "$_out" | wc -l)
    if [ "$_n" -gt "$_tail" ]; then
      printf '%s\n' "$_out" | head -n $((_n - _tail)) | grep '🔴' | sed 's/^/   /' || true
    fi
    printf '%s\n' "$_out" | tail -"$_tail" | sed 's/^/   /'
  else printf '%s\n' "$_out" | sed 's/^/   /'; fi
  [ "$_rc" -eq 0 ] || [ "$_gate" = warn ] || fail=1
}
run()  { _run gate "$@"; }
warn() { _run warn "$@"; }

# 원본이 없어도 도는 검사부터 — **여기가 늘 돌아야 하는 자리다.**
# (코드표·아카이브 규격의 회귀는 합성 입력으로 잡는다, 체크리스트 7)
echo "  ── 회귀 (원본 없이 돈다)"
run 0 "$PY" -m unittest discover -s "$G/tools/tests" -p "test_*.py"

if [ ! -d "$ROOT/originals/jp/ps1-ed3" ]; then
  echo "  ⏭ originals/jp/ps1-ed3 가 없다 — 원본이 필요한 검사는 건너뛴다"
  [ "$fail" -eq 0 ] && echo "  ✅ 통과(부분)" || echo "  🔴 실패"
  exit "$fail"
fi

echo "  ── 원본 지문 (오프셋이 결박된 그 덤프인가)"
run 0 "$PY" -c "
import sys; sys.path.insert(0, '$G/tools')
import common
for d in common.DISC_NAMES:
    common.verify_source(d)
    print(f'  {d}: 지문 ✓ · 파일 {len(common.iso_files(d)):,}')
"

echo "  ── 코드표가 대본을 얼마나 읽나"
# 🔴 게이트다 — 커버리지가 떨어졌다는 건 표가 밀렸거나 덤프 경계가 어긋났다는 뜻이다.
run 0 "$PY" "$G/tools/check_coverage.py" --disc ed3 --min 99.0

# ED4 는 활자 로제타로 표가 섰다(2026-09-03). ED3 보다 낮은 건 ED3 에 없는 한자 때문이다.
run 0 "$PY" "$G/tools/check_coverage.py" --disc ed4 --min 98.0

echo "  ── 폰트 레이아웃 (모양이 계산되는 글자로 검산)"
# 🔴 게이트다 — 저장 규약을 빠뜨리면 한자는 읽히는데 **한글이 무너진다**(실측).
#    ⚠ 규약이 **디스크마다 다르다**(`font.LAYOUT`) — 그래서 둘 다 잰다. ED3 규약으로 ED4 를
#      읽던 동안 「카나를 폰트 렌더로 확인했다」고 적혀 있었다(2026-09-03에 바로잡음).
run 0 "$PY" "$G/tools/check_font.py" --disc ed3
run 0 "$PY" "$G/tools/check_font.py" --disc ed4

echo "  ── 고유명사 정본이 원본과 맞나"
# 🔴 게이트다 — 「원본에 없는 항목」과 「한 표기가 원문 둘에」는 판단이 안 드는 사고다.
#    ⚠ 아직 안 옮긴 낱말은 **실패로 안 친다**(할 일이지 실패가 아니다).
run 0 "$PY" "$G/tools/check_glossary.py" --disc ed3
run 0 "$PY" "$G/tools/check_glossary.py" --disc ed4

echo "  ── 조사 일치(F8) · 일본어 잔존(F7)"
# 🔴 게이트다 — 이름 뒤 조사가 받침과 맞나·병기가 안 풀린 채 남았나 / 「옮겼다」고 올린 자리에 가나·한자가 섞였나.
#    ⚠ 미번역은 실패가 아니다(옮긴 자리만 본다 — 늘 빨간불이면 아무도 안 본다).
run 0 "$PY" "$G/tools/check_josa.py" --disc ed3
run 0 "$PY" "$G/tools/check_jp_left.py" --disc ed3

echo "  ── 자기 표 0 (게임 폴더에 JP→KR 이름·라벨 표가 남았나)"
# 🔴 게이트다 — 사전·정본이 유일한 출처다(마스터 10-08). 스태프롤만 예외(게임마다 제작진이 다르다).
run 0 "$PY" "$G/tools/check_own_tables.py"

echo "  ── 이름창≠본문 메아리(F4) · 조판 규칙(F3)"
# 🔴 게이트다 — 본문이 화자 이름으로 시작하면 화면에 이름이 두 번 나온다 / 줄바꿈 뒤 줄 머리 부호·어절 쪼갬·폭 초과.
run 0 "$PY" "$G/tools/check_name_echo.py" --disc ed3
run 0 "$PY" "$G/tools/check_typeset_rules.py" --disc ed3

echo "  ── 재삽입 구조 (포인터가 다 풀리고 항등 재구축이 바이트 동일한가)"
# 🔴 게이트다 — 항등 재구축이 깨지면 우리 파서가 구조를 잘못 읽는 것이고,
#    그 상태로 문안을 넣으면 **조용히** 깨진다.
run 4 "$PY" "$G/tools/check_script.py" --disc ed3
# ED4 는 규격이 다르다 — 오프셋 표를 낀다(`scriptmap.LAYOUT_TABLE`). 색인이 그대로라
# **표만 다시 계산**하면 되고, 그래서 규격 멤버 전부가 길이 자유다.
run 4 "$PY" "$G/tools/check_script.py" --disc ed4

echo "  ── 대사 VM opcode 표"
# 🔴 게이트다 — 표가 달라졌다는 건 원본이 그 덤프가 아니거나 트리 해독이 바뀌었다는 뜻이다.
#    ⚠ 이건 **메시지 VM** 이다. 스크립트 구간의 데이터를 가진 **이벤트 VM** 은 아직 미지다.
run 3 "$PY" "$G/tools/opcodes.py" --disc ed3 --check

echo "  ── 조판 상수가 원본을 담나"
# 🔴 게이트다 — 상한이 원본보다 좁으면 우리 문안도 창 밖으로 나간다.
run 0 "$PY" "$G/tools/typeset.py" --disc ed3 --check
run 0 "$PY" "$G/tools/typeset.py" --disc ed4 --check

echo "  ── 번역 정본 (원문 지문 · 조판)"
# 🔴 게이트다 — 색인이 밀리면 **번역이 남의 자리에 붙는다.** 원문 지문이 그걸 잡는다.
#    ⚠ 진행률은 실패로 안 친다(할 일이지 실패가 아니다).
run 6 "$PY" "$G/tools/script.py" --disc ed3 --check
run 6 "$PY" "$G/tools/script.py" --disc ed4 --check

echo "  ── 그림 자리표 (글자가 박힌 그림이 그 자리인가)"
# 🔴 게이트다 — 자리는 「멤버 안 몇 번째 TIM 인가」라 `gmfz`·`tim` 을 고치면 밀린다.
#    밀린 채로 그리면 **엉뚱한 그림에 한글이 박힌다.** 크기까지 대조한다.
run 3 "$PY" "$G/tools/dump_tim.py" --disc ed3 --catalog

echo "  ── UI 문안 (원문 지문 · 길이)"
# 🔴 게이트다 — 표가 없는 자리는 **길이 고정**이라, 넘치면 그 문안이 통째로 안 들어간다.
#    ⚠ 진행률은 실패로 안 친다.
run 6 "$PY" "$G/tools/uitext.py" --disc ed3 --check
run 6 "$PY" "$G/tools/uitext.py" --disc ed4 --check

echo "  ── 글리프 자리 정본이 원본과 부딪히나"
# 🔴 게이트다 — 배정한 자리를 원본도 쓰면 **그 글자가 화면에서 바뀐다.**
#    ⚠ 「지금 계산한 배정과 정본이 다르다」는 경고지 실패가 아니다 — 다시 박으려면
#      이미 넣은 문안을 다시 구워야 하므로 사람이 판단한다.
run 4 "$PY" "$G/tools/hangul_map.py" --disc ed3 --check
run 4 "$PY" "$G/tools/hangul_map.py" --disc ed4 --check

echo "  ── 실행파일 낱말 표 (항등 재구축이 바이트 동일한가)"
# 🔴 게이트다 — 이 표는 **이름·메뉴·아이템이 사는 자리**다. 파서가 구조를 잘못 읽으면
#    문안을 넣는 순간 조용히 깨진다. 빈틈(표가 안 가리키는 문자열)을 넘어 움직이지 않는지도
#    여기서 같이 본다.
run 6 "$PY" "$G/tools/exetext.py" --disc ed3 --check
run 6 "$PY" "$G/tools/exetext.py" --disc ed4 --check

echo "  ── 조판 지문 (공용이 우리 줄바꿈을 조용히 흔들지 않나)"
# ⚠ **락도 관측 대장도 조판을 안 본다**(화자 + 창 본문만 해시). `tools/typeset.py` 가
#    `shared/text/krwrap.py` 를 직접 쓰므로, 같은 PS1 플랫폼인 ps1-ed1+2 를 흔든 공용
#    변경이 우리도 흔들 수 있다(실측 확인 2026-09-15 — krwrap 을 되돌리면 ed3 대사 구역
#    지문이 실제로 갈린다). 게이트가 아니다(문안을 바꾸면 당연히 뜬다) —
#    **안 바꿨는데 뜨면 `shared/` 를 의심한다.**
# ⚠ 헤드라인이 `tail -N` 에 잘리는 사고를 ps1-ed1+2 가 겪었다(2026-09-15) — 첫 줄 + 마지막
#    줄만 남긴다(성공 시 한 줄이라 awk 가 중복 없이 처리한다).
"$PY" "$ROOT/scripts/check/typeset_fingerprint.py" --game ps1-ed3+4 2>&1 \
  | awk 'NR==1{first=$0} {last=$0; n=NR} END{print first; if (n>1) print last}' \
  | sed 's/^/   /'

if [ "$fail" -eq 0 ]; then echo "  ✅ 통과"; else echo "  🔴 실패"; fi
exit "$fail"
