#!/bin/sh
# 영전2 만트라 DOS판을 DOSBox-X로 실행한다 (패치 검증·크래시 재현용).
#
#   scripts/dosbox.sh              평범하게 실행  ※ 실제로는 --app 을 권장
#   scripts/dosbox.sh --app        앱 번들로 실행 — macOS에서 키보드가 안정적이다
#   scripts/dosbox.sh --debug      DOSBox-X 디버거 (-break-start). docs/03-debugger.md 참조
#
# 처음 실행하면 originals/ED2 를 work/dosbox/ed2/ed2 로 복사한다(쓰기 가능 사본).
# originals/ 는 절대 건드리지 않는다.
#
# 로그: work/dosbox/ed2.log  (DOS 콘솔 출력 포함 — 엔진 진단 메시지가 여기 남는다)
#
# [키보드가 안 먹을 때]
#   macOS SDL1에서 usescancodes=true면 저수준 키보드 경로를 타는데 입력 모니터링
#   권한이 필요하다. 셸에서 앱 번들 내부 바이너리를 직접 띄우면 그 권한이 안 붙어
#   키보드만 죽는다(마우스는 멀쩡). 템플릿에서 껐고, 그래도 안 되면 --app 을 쓴다.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DOSBOX=/Applications/dosbox-x.app/Contents/MacOS/dosbox-x
WORK="$ROOT/work/dosbox"
GAME="$WORK/ed2/ed2"

[ -x "$DOSBOX" ] || { echo "DOSBox-X 없음: $DOSBOX  (brew install --cask dosbox-x)" >&2; exit 1; }

# 게임 사본 준비
if [ ! -f "$GAME/ED2MAIN.EXE" ]; then
    [ -d "$ROOT/originals/ED2" ] || {
        echo "originals/ED2 가 없다. 소장본을 그 경로에 두거나 심볼릭 링크하라." >&2; exit 1; }
    echo "originals/ED2 -> $GAME 복사 중..."
    mkdir -p "$WORK/ed2"
    rm -rf "$GAME"
    cp -R "$ROOT/originals/ED2" "$GAME"
    find "$GAME" -name '.DS_Store' -delete
    rm -f "$GAME/ED2.SWP"
fi

mkdir -p "$WORK/capture"
sed "s|@ROOT@|$ROOT|g" "$ROOT/dosbox/ed2.conf.tmpl" > "$WORK/ed2.conf"
rm -f "$WORK/ed2.log"

# -log-con: DOS 콘솔 출력을 로그로 남긴다. 게임이 그래픽 모드라 화면에선 안 보이는
# 엔진 진단("Where : %s" / "What  : %s")을 잡기 위한 것이다.
# (-log-fileio 는 이 빌드에서 아무것도 찍지 않는다 — 로드 추적은 tools/atime_probe.py)
COMMON="-conf $WORK/ed2.conf -fastlaunch"

case "$1" in
    --app)
        shift
        exec open -a /Applications/dosbox-x.app --args $COMMON -log-con "$@" ;;
    --debug)
        shift
        # 디버거 UI는 "실행한 터미널"에 뜨므로 앱 번들로는 못 쓴다.
        # -log-con 은 뺀다 — 커서스 UI와 같은 터미널을 두고 부딪힌다.
        exec "$DOSBOX" $COMMON -break-start "$@" ;;
    *)
        exec "$DOSBOX" $COMMON -log-con "$@" ;;
esac
