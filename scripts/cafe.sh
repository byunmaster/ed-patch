#!/bin/sh
# 네이버 카페 레퍼런스 수집 — 입구 하나.
#
#   sh scripts/cafe.sh chrome                 CDP 크롬을 띄운다(이미 떠 있으면 확인만)
#   sh scripts/cafe.sh list                   카페 좌표·수집 현황
#   sh scripts/cafe.sh fetch <카페> [menuid…] 게시판 목록 **증분** 수집(생략 시 전 게시판)
#       --full                                증분이 아니라 전량 재수집
#   sh scripts/cafe.sh body <카페> <menuid> <글id…>   본문·댓글 받기
#   sh scripts/cafe.sh probe <주소|clubid> [--save <슬러그> --name "이름"]
#                                             새 카페의 clubid·menuid 를 캔다
#   공통: --cdp host:port (기본 localhost:9222) · -v (원시 키 표시)
#
# 카페는 로그인 세션이 있어야 읽힌다. 인증은 **크롬 프로필**이 들고(쿠키),
# 이 스크립트가 아는 건 CDP 포트뿐이다 — 자격증명은 레포 어디에도 두지 않는다.
# 🔴 쿠키를 파일로 떨구지 않는다(세션 탈취 토큰 · 이 레포는 공개 전제).
#
# ⚠ 네이버는 캡차·2단계·기기등록이 걸려 아이디/비번을 넣어도 자동 로그인이 안 된다.
#   전용 프로필에 **사람이 한 번** 로그인해 두는 지금 방식이 유일하게 도는 길이다.
# ⚠ 수집물(`docs/reference/_inventory/`)은 gitignore — 타인 게시글이라 커밋 금지.
#   커밋되는 건 우리 말로 재구성한 요약 + 원문 링크다(docs/reference/README.md).
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PROFILE="$HOME/.cache/chrome-cdp-profile"
PORT=9222

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=$(command -v python3) || true
[ -n "${PY:-}" ] || { echo "✗ python3 이 없다" >&2; exit 1; }

# ── chrome: CDP 모드 크롬 ─────────────────────────────────────────────────────
# Chrome 136+ 는 **기본 프로필에서 원격 디버깅을 막는다** → 전용 프로필이 필수다.
if [ "${1:-}" = "chrome" ]; then
  shift
  [ "${1:-}" = "--restart" ] && {
    pkill -9 -f "user-data-dir=$PROFILE" 2>/dev/null || true
    sleep 1
  }
  if curl -s --max-time 2 "http://localhost:$PORT/json/version" >/dev/null 2>&1; then
    echo "✓ CDP 크롬이 이미 떠 있다 (localhost:$PORT)"
    curl -s "http://localhost:$PORT/json/version" | sed 's/,/,\n /g' | head -4
    exit 0
  fi
  echo "→ CDP 크롬을 띄운다 (프로필 $PROFILE)"
  open -na "Google Chrome" --args \
    --remote-debugging-port="$PORT" \
    --user-data-dir="$PROFILE" \
    --remote-allow-origins="http://localhost:$PORT" \
    --no-first-run --no-default-browser-check
  i=0
  while [ "$i" -lt 30 ]; do
    curl -s --max-time 2 "http://localhost:$PORT/json/version" >/dev/null 2>&1 && break
    i=$((i + 1))
    sleep 1
  done
  if curl -s --max-time 2 "http://localhost:$PORT/json/version" >/dev/null 2>&1; then
    echo "✓ 떴다. 이 창에서 **네이버 로그인**이 돼 있는지 한 번 본다(한 번 하면 유지된다)."
  else
    echo "✗ 안 떴다. 옛 인스턴스가 살아 있으면 플래그가 무시된다 →" >&2
    echo "    sh scripts/cafe.sh chrome --restart" >&2
    exit 1
  fi
  exit 0
fi

exec "$PY" "$ROOT/scripts/cafe/fetch.py" "$@"
