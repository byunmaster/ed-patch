#!/bin/sh
# 스팀덱에 QA 앱을 깐다 — 데스크톱 모드 터미널(Konsole)에서 한 번.
#
#   sh scripts/deck/install.sh
#
# 하는 일 셋: pygame 설치(사용자 칸) · 바탕화면 실행 항목 · 스팀 「비 스팀 게임」에 넣을 명령 안내.
# ⚠ mednafen 과 BIOS 는 여기서 안 깐다 — 소장본 BIOS 는 레포에 없다(루트 CLAUDE.md). mednafen 이
#   PATH 에 없으면(flatpak 등) `~/.config/edqa/config.json` 의 "mednafen" 에 실행 명령을 적는다.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
# ⚠ SteamOS 의 python 은 pip 가 없고(「No module named pip」) 시스템 칸이 외부 관리라 사용자 칸 설치도
#   막힌다(「externally-managed-environment」, 마스터 실측 10-30). 그래서 **앱 전용 가상환경**을 만든다 —
#   pip 없이 만들고(--without-pip: ensurepip 가 빠진 판도 있다) get-pip.py 로 그 안에만 pip 를 넣는다.
VENV="$HOME/.local/share/edqa-venv"
PY="$VENV/bin/python"
[ -x "$PY" ] || python3 -m venv --without-pip "$VENV"
"$PY" -m pip --version >/dev/null 2>&1 || curl -fsSL https://bootstrap.pypa.io/get-pip.py | "$PY" -
# pygame 은 새 파이썬 판(SteamOS)용 바퀴가 늦어 소스 빌드로 가다 죽는다(「subprocess-exited-with-error」, 10-30) —
# 바퀴가 먼저 나오는 호환판 pygame-ce 를 쓴다(import pygame 그대로).
"$PY" -m pip install -q pygame-ce
APP="$HERE/edqa.py"
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/edqa.desktop" <<D
[Desktop Entry]
Type=Application
Name=영웅전설 QA
Exec="$PY" "$APP"
Terminal=false
Categories=Game;
D
command -v mednafen >/dev/null 2>&1 || flatpak info com.github.AmatCoder.mednaffe >/dev/null 2>&1 ||
  echo "⚠ mednafen 이 없다 — Discover 에서 Mednaffe 를 깐다(앱이 그 안의 mednafen 을 찾아 쓴다)"
echo "✅ 깔았다. 게임 모드에서 쓰려면 스팀 → 게임 → 「비 스팀 게임 추가」 → 영웅전설 QA."
echo "   캡처 키: 스팀 입력에서 뒤 버튼 하나를 키보드 F9 에 건다(mednafen 스크린샷)."
