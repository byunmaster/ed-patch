#!/bin/sh
# 웹 패처 — 빌드 / 로컬 확인 / 배포.
#
#   scripts/patcher.sh [serve] [옵션]    빌드해서 127.0.0.1 로 띄운다 (기본 동작)
#       --port N        포트 지정 (기본 8731)
#       --no-open       브라우저를 자동으로 열지 않는다
#   scripts/patcher.sh build             .local/cache/patcher/index.html 로 빌드만 한다
#
# 두 갈래가 모두 아래 build() 하나를 거친다 — 빌드 인자가 갈래마다 어긋날 수 없다.
#   patcher/index.html.tmpl + games/*/patches/*.json  --patcher/build.py-->  index.html
# 게임이 늘면 그 게임의 kind=="fix" 패치가 같은 페이지에 자동으로 실린다.
# ⚠ 배포(deploy)는 걷었다(2026-10-07) — 이 레포가 ed-patch 이름을 이어받았고, 배포 사이트
#   (patcher/site)는 Pages 워크플로가 굽는다. 아래 deploy 갈래는 안내만 하고 멈춘다.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)

# 폰트 서브셋(fontTools)이 필요하다. venv가 있으면 그걸, 없으면 시스템 python3.
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=$(command -v python3)

# 페이지 푸터에 걸 소스 링크. 비우면 푸터가 통째로 숨는다.
# 레포는 2026-10-07 에 공개됐다(이름 ed-patch).
SRC_URL="https://github.com/byunmaster/ed-patch"

# 배포 버전. 디스켓 라벨에 v1.0.0 으로 찍힌다. 비우면 라벨에 버전이 안 나온다.
# 릴리스할 때 여기를 올리고, 같은 값으로 git 태그를 단다.
VERSION=1.0.0

# 복원 결과를 녹화한 유튜브 영상 ID. 말풍선의 "미리보기" 버튼이 이걸 튼다.
# 비우면 버튼이 사라진다. 페이지를 열 때는 요청이 안 나가고, 버튼을 누른
# 순간에만 유튜브를 부른다 — 그전까지 이 페이지의 외부 요청은 0이다.
VIDEO=rRsJ_RGPIMY

# build <출력경로> — 유일한 빌드 경로. 갈래별로 다른 인자를 주지 않는다.
build() {
    "$PY" "$ROOT/patcher/build.py" \
        --out "$1" ${SRC_URL:+--repo "$SRC_URL"} ${VERSION:+--version "$VERSION"} \
        ${VIDEO:+--video "$VIDEO"}
}

usage() { sed -n '2,21p' "$0" | sed 's/^#\{1,\} \{0,1\}//'; }

# 하위 명령을 생략하면 serve — 제일 자주 쓰는 갈래이고, 아무것도 망가뜨리지 않는다.
# 옵션만 준 경우(`patcher.sh --port 9000`)도 serve 로 보고 인자를 그대로 넘긴다.
CMD=serve
case "${1:-}" in
    -h|--help|help) usage; exit 0 ;;
    ""|-*)          ;;
    *)              CMD=$1; shift ;;
esac

case "$CMD" in
build)
    [ $# -eq 0 ] || { echo "build 는 인자를 받지 않는다: $*" >&2; exit 1; }
    echo "== 빌드"
    build "$ROOT/.local/cache/patcher/index.html"
    ;;

serve)
    PORT=8731
    OPEN=yes
    while [ $# -gt 0 ]; do
        case "$1" in
            --port)    PORT="$2"; shift ;;
            --no-open) OPEN=no ;;
            *) echo "serve: 모르는 인자: $1" >&2; exit 1 ;;
        esac
        shift
    done

    OUT="$ROOT/.local/cache/patcher"
    echo "== 빌드"
    build "$OUT/index.html"

    URL="http://127.0.0.1:$PORT/"
    echo "== 서빙: $URL   (Ctrl+C 로 중단)"
    # file:// 로 열면 안 된다. showDirectoryPicker 가 보안 컨텍스트를 요구하는데
    # file:// 은 그 대상이 아니라 디스켓을 눌러도 아무 일도 일어나지 않는다.
    # 127.0.0.1 은 보안 컨텍스트로 쳐주므로 여기서는 실제와 똑같이 동작한다.
    [ "$OPEN" = yes ] && (sleep 1; open "$URL") &

    # 서버를 포그라운드로 둔다 — Ctrl+C 한 번에 같이 끝나게
    exec "$PY" -m http.server "$PORT" --bind 127.0.0.1 --directory "$OUT"
    ;;

deploy)
    # 🔴 **옛 배포 갈래는 걷었다**(2026-10-07). 예전엔 산출물 전용 공개 리포 ed-patch 를 받아 index.html
    #   하나로 main 을 강제 덮어썼다 — 그런데 이 작업 레포가 **ed-patch 라는 이름을 이어받았다.** 남겨 두면
    #   한 번의 실행으로 이 레포 main 이 패처 파일 하나로 덮인다. 배포는 이제 Pages 워크플로다.
    echo "deploy 는 없어졌다 — 배포 사이트는 main 에 머지하면 .github/workflows/pages.yml 이 굽는다." >&2
    echo "  패처 미리보기는 serve, 사이트 미리보기는 python3 patcher/site/build_site.py --out <dir>" >&2
    exit 1
    ;;

*)
    echo "모르는 명령: $CMD" >&2
    echo >&2
    usage >&2
    exit 1
    ;;
esac
