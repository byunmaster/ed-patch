#!/bin/sh
# 웹 패처 — 빌드 / 로컬 확인 / 배포.
#
#   scripts/patcher.sh [serve] [옵션]    빌드해서 127.0.0.1 로 띄운다 (기본 동작)
#       --port N        포트 지정 (기본 8731)
#       --no-open       브라우저를 자동으로 열지 않는다
#   scripts/patcher.sh build             .local/cache/patcher/index.html 로 빌드만 한다
#   scripts/patcher.sh deploy [옵션]     공개 리포(ed-patch)에 올린다
#       --amend         마지막 커밋을 덮어쓴다(기본). 산출물 리포라 히스토리가
#                       의미 없어 안정화 전까지는 이쪽을 쓴다
#       --new           새 커밋을 쌓는다
#       --dry-run       빌드만 하고 커밋·push 하지 않는다
#       --msg "..."     커밋 메시지(생략 시 기본 문구)
#       --repo-dir DIR  공개 리포 클론 위치(기본 .local/cache/ed-patch, gitignore 안이라 안전)
#
# 세 갈래가 모두 아래 build() 하나를 거친다. serve 로 본 것이 곧 deploy 되는 것이며,
# 빌드 인자가 갈래마다 어긋날 수 없다 — 미리보기가 거짓말을 하지 않는다.
#
# 이 리포지토리에는 소스가, ed-patch(공개)에는 산출물만 올라간다.
#   patcher/index.html.tmpl + games/*/patches/*.json  --patcher/build.py-->  index.html
# 게임이 늘면 그 게임의 kind=="fix" 패치가 같은 페이지에 자동으로 실린다.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)

# 폰트 서브셋(fontTools)이 필요하다. venv가 있으면 그걸, 없으면 시스템 python3.
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=$(command -v python3)

# 페이지 푸터에 걸 소스 링크. 비우면 푸터가 통째로 숨는다.
# 작업 레포 공개 여부가 아직 미결이라 비워 둔다 — 공개하면 여기 한 줄만 채우면
# serve 와 deploy 에 동시에 반영된다. 공개 전 점검은 docs/publishing.md.
SRC_URL=""

# 배포 버전. 디스켓 라벨에 v1.0.0 으로 찍힌다. 비우면 라벨에 버전이 안 나온다.
# 릴리스할 때 여기를 올리고, 같은 값으로 git 태그를 단다.
VERSION=1.0.0

# 복원 결과를 녹화한 유튜브 영상 ID. 말풍선의 "미리보기" 버튼이 이걸 튼다.
# 비우면 버튼이 사라진다. 페이지를 열 때는 요청이 안 나가고, 버튼을 누른
# 순간에만 유튜브를 부른다 — 그전까지 이 페이지의 외부 요청은 0이다.
VIDEO=rRsJ_RGPIMY

DEPLOY_URL=https://github.com/byunmaster/ed-patch.git

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
    MODE=amend
    MSG=""
    REPO_DIR="$ROOT/.local/cache/ed-patch"
    while [ $# -gt 0 ]; do
        case "$1" in
            --amend)    MODE=amend ;;
            --new)      MODE=new ;;
            --dry-run)  MODE=dry ;;
            --msg)      MSG="$2"; shift ;;
            --repo-dir) REPO_DIR="$2"; shift ;;
            *) echo "deploy: 모르는 인자: $1" >&2; exit 1 ;;
        esac
        shift
    done

    [ -d "$REPO_DIR/.git" ] || {
        echo "== 공개 리포 클론: $REPO_DIR"
        git clone -q "$DEPLOY_URL" "$REPO_DIR"
    }

    echo "== 빌드"
    build "$REPO_DIR/index.html"
    # 갈무리 폰트를 페이지에 임베드해 배포하므로 OFL 전문도 같이 나가야 한다
    cp "$ROOT/patcher/LICENSE-Galmuri.txt" "$REPO_DIR/LICENSE-Galmuri.txt"

    if [ "$MODE" = dry ]; then
        echo "== --dry-run: 커밋·push 하지 않음"
        git -C "$REPO_DIR" --no-pager diff --stat
        exit 0
    fi

    cd "$REPO_DIR"
    if git diff --quiet && git diff --cached --quiet; then
        echo "== 바뀐 내용 없음"
        exit 0
    fi

    git add -A
    if [ "$MODE" = amend ]; then
        # 산출물 리포는 커밋 하나로 유지한다 — 메시지는 그대로 두고 내용만 갈아끼운다
        git commit -q --amend --no-edit ${MSG:+-m "$MSG"}
        echo "== amend 후 force push"
        git push -q --force-with-lease origin main
    else
        git commit -q -m "${MSG:-패처 갱신}"
        echo "== push"
        git push -q origin main
    fi

    echo "== 완료: https://byunmaster.github.io/ed-patch/  (Pages 재빌드에 1~2분)"
    git --no-pager log --oneline -1
    ;;

*)
    echo "모르는 명령: $CMD" >&2
    echo >&2
    usage >&2
    exit 1
    ;;
esac
