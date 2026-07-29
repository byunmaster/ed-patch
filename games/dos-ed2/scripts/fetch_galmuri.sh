#!/bin/sh
# 갈무리(Galmuri) 픽셀 폰트 원본을 vendor/galmuri/ 로 내려받는다.
#
# vendor/ 는 gitignore 라 이건 그냥 캐시다. 커밋되는 건 서브셋 결과(web/fonts.css)와
# 라이선스 전문(web/LICENSE-Galmuri.txt)뿐이다.
#
#   scripts/fetch_galmuri.sh          내려받기 (이미 있으면 건너뛴다)
#   scripts/fetch_galmuri.sh --force  다시 받기
#
# 폰트: 갈무리 — SIL Open Font License 1.1
#       Copyright (c) 2019-2025 Lee Minseo (quiple@quiple.dev)
#       https://github.com/quiple/galmuri
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
VER=2.40.3
BASE="https://cdn.jsdelivr.net/npm/galmuri@$VER/dist"
DEST="$ROOT/vendor/galmuri"

[ "$1" = --force ] && rm -rf "$DEST"
mkdir -p "$DEST"

# woff2 만 받는다. ttf 는 5MB 씩이라 필요 없다.
for f in Galmuri9.woff2 GalmuriMono9.woff2 Galmuri11.woff2 Galmuri11-Bold.woff2 GalmuriMono11.woff2 LICENSE.txt; do
    if [ -s "$DEST/$f" ]; then
        echo "  있음: $f"
    else
        echo "  받는 중: $f"
        curl -sSf --max-time 60 -o "$DEST/$f" "$BASE/$f"
    fi
done

# 라이선스 전문은 배포물에도 같이 나가야 한다(OFL 조건)
cp "$DEST/LICENSE.txt" "$ROOT/web/LICENSE-Galmuri.txt"

echo "== 완료: $DEST  (갈무리 $VER)"
echo "   이제 .venv/bin/python tools/subset_font.py 로 서브셋한다."
