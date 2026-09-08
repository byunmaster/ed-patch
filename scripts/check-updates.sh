#!/bin/sh
# 외부 의존물의 새 버전을 확인한다 — 세션 시작 때 한 번 돌린다.
#
#   sh scripts/check-updates.sh            # 확인만
#   sh scripts/check-updates.sh --update   # emucap·템플릿을 당기고 emucap 은 빌드까지
#
# ⚠ 스킬(create-kr-patch)은 Claude Code 플러그인이라 설치는 `/plugin` 으로 해야 한다.
#   여기서는 마켓플레이스 클론만 최신화하고 새 버전이 있는지 알려준다.
# ⚠ emucap 을 새로 빌드하면 MCP 도구 스키마가 바뀔 수 있다 — **Claude Code 재시작** 필요.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
UPDATE=0
[ "${1:-}" = "--update" ] && UPDATE=1

behind() { # <dir> — origin 기준 뒤처진 커밋 수(없으면 빈 문자열)
  git -C "$1" fetch --quiet origin 2>/dev/null || return 1
  b=$(git -C "$1" symbolic-ref --short HEAD 2>/dev/null || echo main)
  git -C "$1" rev-list --count "HEAD..origin/$b" 2>/dev/null
}

echo "== 외부 의존물 업데이트 확인 =="

# ── emucap (MCP 서버 · 어댑터) ────────────────────────────────────────
EMU="$ROOT/vendor/emucap"
if [ -d "$EMU/.git" ]; then
  n=$(behind "$EMU" || echo "?")
  if [ "$n" = "0" ]; then
    echo "  emucap        최신 ($(git -C "$EMU" describe --tags --always 2>/dev/null))"
  else
    echo "  emucap        ⬆ $n 커밋 뒤처짐"
    git -C "$EMU" log --oneline -3 HEAD..origin/main 2>/dev/null | sed 's/^/                  /'
    if [ "$UPDATE" = "1" ]; then
      git -C "$EMU" pull --quiet --ff-only origin main
      echo "                  빌드 중…"
      (cd "$EMU" && "$HOME/.cargo/bin/cargo" build --release >/dev/null 2>&1) &&
        echo "                  ✅ 빌드 완료 — ⚠ Claude Code 재시작 필요" ||
        echo "                  ❌ 빌드 실패 — 직접 확인하라"
    fi
  fi
else
  echo "  emucap        없음 (vendor/emucap)"
fi

# ── 한글패치 스킬 (Claude Code 플러그인) ──────────────────────────────
SKILL="$HOME/.claude/plugins/marketplaces/kr-patch"
if [ -d "$SKILL/.git" ]; then
  n=$(behind "$SKILL" || echo "?")
  cur=$(python3 -c "
import json,os
p=os.path.expanduser('~/.claude/plugins/installed_plugins.json')
d=json.load(open(p)).get('plugins',{})
for k,v in d.items():
    if 'create-kr-patch' in k and v: print(v[0].get('version','?'))
" 2>/dev/null || echo "?")
  latest=$(git -C "$SKILL" log --oneline -1 --grep '^release:' origin/main 2>/dev/null | sed 's/.*release: //')
  if [ "$n" = "0" ] && [ "$cur" = "$latest" ]; then
    echo "  create-kr-patch 최신 ($cur)"
  else
    [ "$UPDATE" = "1" ] && git -C "$SKILL" pull --quiet --ff-only origin main 2>/dev/null
    echo "  create-kr-patch 설치본 $cur / 최신 ${latest:-?} — ⚠ 갱신은 \`/plugin\`"
  fi
fi

# ── QA 규약 스킬 (Claude Code 플러그인) ───────────────────────────────
# ⚠ `create-kr-patch`(제작 방법론)와 **다른 스킬**이다 — 이쪽은 정적 우선 QA 규약이다.
QA="$HOME/.claude/plugins/marketplaces/kr-patch-qa"
if [ -d "$QA/.git" ]; then
  n=$(behind "$QA" || echo "?")
  if [ "$n" = "0" ]; then
    echo "  kr-patch-qa   최신"
  else
    [ "$UPDATE" = "1" ] && git -C "$QA" pull --quiet --ff-only origin main 2>/dev/null
    echo "  kr-patch-qa   ${n}커밋 뒤짐 — ⚠ 갱신은 \`/plugin\`"
  fi
else
  echo "  kr-patch-qa   미설치 — \`/plugin\` 에서 kr-patch-qa 마켓플레이스를 켠다"
fi

# ── 패치 템플릿 (참고용 클론) ─────────────────────────────────────────
TPL="$ROOT/.local/cache/ref/kr-patch-template"
TPL_URL=https://github.com/mcpads/create-kr-patch-template
if [ -d "$TPL/.git" ]; then
  local_sha=$(git -C "$TPL" rev-parse HEAD)
  remote_sha=$(git ls-remote "$TPL_URL" HEAD 2>/dev/null | cut -f1)
  if [ "$local_sha" = "$remote_sha" ]; then
    echo "  patch-template 최신"
  else
    echo "  patch-template ⬆ 새 커밋 있음"
    if [ "$UPDATE" = "1" ]; then
      rm -rf "$TPL" && git clone --quiet --depth 1 "$TPL_URL" "$TPL" &&
        echo "                  ✅ 갱신 — 규칙 변경이 있는지 AGENTS.md 확인"
    fi
  fi
else
  echo "  patch-template 없음 — \`git clone --depth 1 $TPL_URL .local/cache/ref/kr-patch-template\`"
fi

[ "$UPDATE" = "0" ] && echo "\n(당기려면 --update. 스킬은 /plugin, emucap 갱신 후엔 재시작)"
exit 0
