#!/usr/bin/env python3
"""패치 스펙(JSON)을 `web/index.html.tmpl` 에 박아 자립형 웹 패처를 만든다.

결과물은 외부 요청이 전혀 없는 HTML 하나다. GitHub Pages 용 **공개** 리포지토리에
이 파일만 올리면 되므로, 분석 노트가 들어 있는 이 리포지토리는 비공개로 둘 수 있다.
패치 데이터가 페이지 안에 인라인되므로 xdelta 같은 별도 포맷도, 디코더도 필요 없다.

CLI 패처(`apply_patch.py`)와 **같은 JSON** 을 읽으므로 둘이 어긋날 일이 없다.

usage:
  build_patcher.py --out <index.html> [--spec patches/x.json ...] [--repo URL]
                   [--version 1.0.0] [--video YOUTUBE_ID]

`--spec` 을 주지 않으면 `patches/` 의 `kind == "fix"` 스펙을 파일명 순으로 모두 넣는다
(진단용 `diag-*` 는 자동으로 빠진다).
"""

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    argv = sys.argv[1:]
    if "--out" not in argv:
        sys.exit(__doc__)
    out = argv[argv.index("--out") + 1]
    repo = argv[argv.index("--repo") + 1] if "--repo" in argv else ""
    version = argv[argv.index("--version") + 1] if "--version" in argv else ""
    video = argv[argv.index("--video") + 1] if "--video" in argv else ""
    specs_arg = [argv[i + 1] for i, v in enumerate(argv) if v == "--spec"]

    paths = specs_arg or sorted(glob.glob(os.path.join(ROOT, "patches", "*.json")))
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

    tmpl = open(os.path.join(ROOT, "web", "index.html.tmpl"), encoding="utf-8").read()

    # 서브셋한 갈무리 폰트(@font-face + base64). tools/subset_font.py 가 만든다.
    fonts_path = os.path.join(ROOT, "web", "fonts.css")
    if not os.path.exists(fonts_path):
        sys.exit(f"{fonts_path} 가 없다 — .venv/bin/python tools/subset_font.py 를 먼저 돌려라")
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
