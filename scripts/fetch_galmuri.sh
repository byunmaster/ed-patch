#!/bin/sh
# 갈무리(Galmuri) 픽셀 폰트 원본을 vendor/galmuri/ 로 내려받는다.
#
# vendor/ 는 gitignore 라 이건 그냥 캐시다. 커밋되는 건 서브셋 결과(patcher/fonts.css)와
# 라이선스 전문(patcher/LICENSE-Galmuri.txt)뿐이다.
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
cp "$DEST/LICENSE.txt" "$ROOT/patcher/LICENSE-Galmuri.txt"

# 프리텐다드(Pretendard) — 배포 사이트 본문 글꼴. SIL OFL 1.1(예약 글꼴 이름 있음 → 서브셋은
#   이름을 바꿔 쓴다, patcher/site/build_site.py 의 RFN_FACES).
#   Copyright (c) 2021 Kil Hyung-jin — https://github.com/orioncactus/pretendard
PVER=1.3.9
PBASE="https://cdn.jsdelivr.net/npm/pretendard@$PVER/dist"
PDEST="$ROOT/vendor/pretendard"
[ "$1" = --force ] && rm -rf "$PDEST"
mkdir -p "$PDEST"
for f in web/static/woff2/Pretendard-Regular.woff2 web/static/woff2/Pretendard-Bold.woff2 LICENSE.txt; do
    b=$(basename "$f")
    if [ -s "$PDEST/$b" ]; then
        echo "  있음: $b"
    else
        echo "  받는 중: $b"
        curl -sSf --max-time 60 -o "$PDEST/$b" "$PBASE/$f"
    fi
done

echo "== 완료: $DEST  (갈무리 $VER) · $PDEST  (프리텐다드 $PVER)"
echo "   이제 python3 patcher/subset_font.py 로 서브셋한다."
