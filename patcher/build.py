#!/usr/bin/env python3
"""패치 스펙(JSON)을 `patcher/index.html.tmpl` 에 박아 자립형 웹 패처를 만든다.

결과물은 외부 요청이 전혀 없는 HTML 하나다. GitHub Pages 용 **공개** 리포지토리에
이 파일만 올리면 된다. 패치 데이터가 페이지 안에 인라인되므로 xdelta 같은 별도
포맷도, 디코더도 필요 없다 — 대신 스펙에 원본 바이트를 담지 않는다(패치 스키마 v2).

CLI 패처(`apply_patch.py`)와 **같은 JSON** 을 읽으므로 둘이 어긋날 일이 없다.

usage:
  patcher/build.py --out <index.html> [--spec patches/x.json ...] [--repo URL]
                   [--version 1.0.0] [--video YOUTUBE_ID]

`--spec` 을 주지 않으면 `games/*/patches/` 의 `kind == "fix"` 스펙을 경로 순으로 모두
넣는다(진단용 `diag-*` 는 자동으로 빠진다). 게임이 늘면 그 게임의 패치가 같은 페이지에
자동으로 실린다 — 패처는 시리즈 전체의 배포 창구다.
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))  # patcher/ — 템플릿·폰트가 같이 산다
ROOT = os.path.dirname(HERE)


def main():
    argv = sys.argv[1:]
    if "--out" not in argv:
        sys.exit(__doc__)
    out = argv[argv.index("--out") + 1]
    repo = argv[argv.index("--repo") + 1] if "--repo" in argv else ""
    version = argv[argv.index("--version") + 1] if "--version" in argv else ""
    video = argv[argv.index("--video") + 1] if "--video" in argv else ""
    specs_arg = [argv[i + 1] for i, v in enumerate(argv) if v == "--spec"]

    paths = specs_arg or sorted(glob.glob(os.path.join(ROOT, "games", "*", "patches", "*.json")))
    specs = []
    for p in paths:
        s = json.load(open(p, encoding="utf-8"))
        if not specs_arg and s.get("kind") != "fix":
            continue
        if "files" not in s:
            sys.exit(f"{p}: 'files' 가 없다 — gen_patch.py 로 만든 스펙이어야 한다")
        specs.append(s)
        print(f"# 포함: {os.path.relpath(p, ROOT)}  ({s['name']})")
    if not specs:
        sys.exit("포함할 스펙이 없다")

    tmpl = open(os.path.join(HERE, "index.html.tmpl"), encoding="utf-8").read()

    # 서브셋한 갈무리 폰트(@font-face + base64). patcher/subset_font.py 가 만든다.
    fonts_path = os.path.join(HERE, "fonts.css")
    if not os.path.exists(fonts_path):
        sys.exit(f"{fonts_path} 가 없다 — python3 patcher/subset_font.py 를 먼저 돌려라")
    fonts = open(fonts_path, encoding="utf-8").read()

    # </script> 가 스펙 문자열에 섞여도 HTML 파싱이 깨지지 않게 이스케이프한다
    blob = json.dumps(specs, ensure_ascii=False).replace("</", "<\\/")
    html = (
        tmpl.replace("@FONTS@", fonts)
        .replace("@PATCHES@", blob)
        .replace("@REPO@", repo)
        .replace("@VERSION@", version)
        .replace("@VIDEO@", video)
    )
    for token in ("@FONTS@", "@PATCHES@", "@REPO@", "@VERSION@", "@VIDEO@"):
        if token in html:
            sys.exit(f"템플릿 치환 실패: {token}")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, "w", encoding="utf-8").write(html)
    n = sum(len(s["files"]) for s in specs)
    ver = f"v{version} / " if version else ""
    print(f"# 기록: {out}  ({ver}{len(html):,}B, 스펙 {len(specs)}개 / 대상 파일 {n}개)")


if __name__ == "__main__":
    main()
