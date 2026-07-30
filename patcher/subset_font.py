#!/usr/bin/env python3
"""갈무리 픽셀 폰트를 페이지에 실제로 쓰이는 글자만 남겨 서브셋하고, base64 data URI
로 박은 `patcher/fonts.css` 를 만든다.

한글은 완성형 11,172자라 원본 woff2 가 500KB 씩이다. 셋을 그대로 심으면 페이지가
1.4MB 가 되므로 쓰이는 글자(보통 300자 안팎)만 남긴다 — 셋 합쳐 수십 KB 로 준다.

글자 목록은 `patcher/index.html.tmpl` 과 `games/*/patches/*.json`(kind == "fix")에서 긁는다.
문구를 고치면 이 스크립트를 다시 돌려야 한다. 빠뜨린 글자는 두부(□)가 되는 게
아니라 CSS 폰트 스택의 다음 폰트로 떨어지므로, 잊어도 페이지가 깨지지는 않는다.

원본은 `vendor/galmuri/`(gitignore, 내려받기 캐시)에 두고 산출물만 커밋한다.
  scripts/fetch_galmuri.sh     원본 내려받기
  patcher/subset_font.py       서브셋 → patcher/fonts.css

usage:
  subset_font.py [--out patcher/fonts.css]
"""

import base64
import glob
import io
import json
import os
import sys

from fontTools import subset
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))  # patcher/
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "vendor", "galmuri")

# (CSS family, 원본 파일, font-weight)
#
# Galmuri9 = 본문(18px = 2×9). Galmuri11 = 제목(33px = 3×11)과 CRT(22px = 2×11).
# 픽셀 폰트라 각자 고유 격자의 정수배로만 써야 획이 안 뭉개지고, 그래서 크기 단계를
# 늘리려면 폰트를 갈아 끼우는 수밖에 없다(11px 격자는 11→22→33 뿐이다).
#
# Galmuri9 에는 볼드 원본이 없어(업스트림에 없음) 브라우저 합성 볼드를 쓴다.
FACES = [
    ("Galmuri9", "Galmuri9.woff2", 400),
    ("Galmuri11", "Galmuri11.woff2", 400),
    ("Galmuri11", "Galmuri11-Bold.woff2", 700),
    ("GalmuriMono9", "GalmuriMono9.woff2", 400),
    ("GalmuriMono11", "GalmuriMono11.woff2", 400),
]

# 본문에 안 보여도 런타임에 튀어나올 수 있는 글자들.
# ASCII 전체 — 파일명·숫자·브라우저 예외 메시지(대개 영문)가 여기서 나온다.
ALWAYS = set(chr(c) for c in range(0x20, 0x7F))
# 화면에 직접 쓰는 기호 (템플릿에 없더라도 넣어 둔다)
ALWAYS |= set("─│┌┐└┘├┤┬┴┼█▓▒░▶◀▲▼·—…※⋯「」『』©")


def used_chars():
    """페이지에 실릴 수 있는 글자를 전부 모은다."""
    chars = set(ALWAYS)

    with open(os.path.join(HERE, "index.html.tmpl"), encoding="utf-8") as f:
        chars |= set(f.read())

    # 스펙에서 화면에 나오는 값 — 라벨/이름/파일경로. description 은 안 쓰지만
    # 나중에 노출해도 안전하게 통째로 넣는다(글자 수가 얼마 안 된다).
    for p in sorted(glob.glob(os.path.join(ROOT, "games", "*", "patches", "*.json"))):
        with open(p, encoding="utf-8") as f:
            spec = json.load(f)
        if spec.get("kind") != "fix":
            continue
        chars |= set(json.dumps(spec, ensure_ascii=False))

    # 제어문자는 뺀다
    return {c for c in chars if c.isprintable()}


def subset_face(path, chars):
    """woff2 하나를 글자 집합으로 줄여 woff2 바이트로 돌려준다."""
    font = TTFont(path)
    opts = subset.Options()
    opts.flavor = "woff2"
    # 픽셀 폰트라 힌팅이 의미 없다. 이름/버전 기록은 남긴다(OFL 고지 추적용).
    opts.hinting = False
    opts.desubroutinize = False
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    subsetter = subset.Subsetter(options=opts)
    subsetter.populate(text="".join(sorted(chars)))
    subsetter.subset(font)
    buf = io.BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    font.close()
    return buf.getvalue()


def main():
    argv = sys.argv[1:]
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(HERE, "fonts.css")

    missing = [f for _, f, _ in FACES if not os.path.exists(os.path.join(SRC, f))]
    if missing:
        sys.exit(f"원본이 없다: {', '.join(missing)}\n  scripts/fetch_galmuri.sh 를 먼저 돌려라")

    chars = used_chars()
    hangul = sum(1 for c in chars if "가" <= c <= "힣")
    print(f"# 글자 {len(chars)}자 (한글 {hangul}자)")

    css = [
        "/* 갈무리 (Galmuri) — SIL Open Font License 1.1",
        "   Copyright (c) 2019-2025 Lee Minseo (quiple@quiple.dev)",
        "   https://github.com/quiple/galmuri  |  https://openfontlicense.org",
        "   이 페이지에 쓰이는 글자만 남긴 서브셋이다. 전체 라이선스 전문은 배포물의",
        "   LICENSE-Galmuri.txt 를 참조. 생성: patcher/subset_font.py */",
    ]
    total_src = total_sub = 0
    for family, fname, weight in FACES:
        path = os.path.join(SRC, fname)
        src_size = os.path.getsize(path)
        data = subset_face(path, chars)
        total_src += src_size
        total_sub += len(data)
        b64 = base64.b64encode(data).decode("ascii")
        css.append(
            f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};"
            f"font-display:block;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}"
        )
        print(f"#   {fname:24} {src_size:>8,}B -> {len(data):>7,}B  ({len(data) / src_size:.1%})")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    text = "\n".join(css) + "\n"
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"# 기록: {out}  (원본 {total_src:,}B -> 서브셋 {total_sub:,}B, css {len(text):,}B)")


if __name__ == "__main__":
    main()
