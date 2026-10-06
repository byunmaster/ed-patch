#!/usr/bin/env python3
"""배포 사이트를 굽는다 — 인덱스(게임 카드 + 진행 칸) + 게임마다 패치 페이지.

    python3 patcher/site/build_site.py --out <디렉터리>
    python3 patcher/site/build_site.py --out <디렉터리> --fragment   # 인덱스를 머리 없는 조각으로(미리보기용)

산출물은 외부 요청이 없는 정적 파일이다(GitHub Pages 에 그대로 올린다):

    index.html          게임 카드 — 진행 칸은 열 때마다 site.json 을 읽는다(못 읽으면 구울 때 박은 사본)
    site.json           진행 상황 정본의 사본 — 이것만 바꿔 올려도 카드가 바뀐다
    <게임>/index.html    웹 패치 · 파일 받기 · 원본 지문 · 진행 단계 (`release` 가 있는 게임만)

🔴 **패치 파일(.bps/.xdelta)은 여기서 만들지 않는다.** 그건 각 게임의 빌드 산출물(`work/dist/`,
gitignore)이고, 배포할 때 그 칸에서 이 디렉터리 옆으로 복사한다 — 번역 문안을 git 에 넣지 않는
경계(docs/publishing.md)가 그대로다. site.json 의 `release.bps` · `xdelta` 가 그 파일 이름을 가리킨다.

글꼴은 갈무리를 페이지에 쓰이는 글자만 남겨 base64 로 박는다(`patcher/subset_font.py` 의 서브셋 함수를
그대로 쓴다 — 원본은 `vendor/galmuri/`, `scripts/fetch_galmuri.sh` 가 받는다).
"""

import base64
import glob
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))  # patcher/site/
sys.path.insert(0, os.path.dirname(HERE))  # patcher/ — subset_font
import subset_font

ROOT = os.path.dirname(os.path.dirname(HERE))
# 네오둥근모 — 제목용(16px 격자). 레포에 커밋된 ttf 를 서브셋해 woff2 로 박는다(OFL 1.1).
NEODGM = os.path.join(ROOT, "shared", "fonts", "neodgm.ttf")


def local_dir(name):
    """`.local/<name>` — 워크트리엔 `.local/` 이 안 따라오므로 메인 트리 것을 거슬러 찾는다(루트 CLAUDE.md)."""
    try:
        common = subprocess.run(
            ["git", "-C", ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        main = os.path.dirname(common)
    except (OSError, subprocess.CalledProcessError):
        main = ROOT
    for base in (ROOT, main):
        p = os.path.join(base, ".local", name)
        if os.path.isdir(p):
            return p
    return os.path.join(ROOT, ".local", name)


def read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


def fonts_css(text):
    chars = (subset_font.ALWAYS | set(text)) - {c for c in text if not c.isprintable()}
    rules = []
    for family, fname, weight in subset_font.FACES:
        path = os.path.join(subset_font.SRC, fname)
        if not os.path.exists(path):
            sys.exit(f"글꼴 원본이 없다: {path}\n  sh scripts/fetch_galmuri.sh 를 먼저 돌린다")
        b64 = base64.b64encode(subset_font.subset_face(path, chars)).decode("ascii")
        rules.append(
            f"@font-face{{font-family:'{family}';font-weight:{weight};font-display:block;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}"
        )
    b64 = base64.b64encode(subset_font.subset_face(NEODGM, chars)).decode("ascii")
    rules.append(
        "@font-face{font-family:'NeoDunggeunmo';font-weight:400;font-display:block;"
        f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}"
    )
    return (
        "/* 갈무리 (Galmuri) · 네오둥근모 (NeoDunggeunmo) — 둘 다 SIL OFL 1.1, 쓰이는 글자만 남긴 서브셋.\n"
        "   전문은 배포물의 LICENSE-Galmuri.txt · LICENSE-neodgm.txt */\n" + "\n".join(rules)
    )


def full_doc(frag):
    """조각(제목·style 다음 본문)을 완전한 문서로 감싼다. 머리 = 첫 </style> 까지."""
    cut = frag.index("</style>") + len("</style>")
    return (
        '<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        + frag[:cut]
        + "\n</head>\n<body>\n"
        + frag[cut:]
        + "\n</body>\n</html>\n"
    )


def main():
    argv = sys.argv[1:]
    if "--out" not in argv:
        sys.exit(__doc__)
    out = argv[argv.index("--out") + 1]
    fragment = "--fragment" in argv

    site = json.loads(read("site.json"))
    covers_dir = os.environ.get("SITE_COVERS") or local_dir("site-covers")
    for g in site["games"]:
        if os.path.exists(os.path.join(covers_dir, f"{g['id']}.png")):
            g["cover"] = f"covers/{g['id']}.png"
        # 상세 페이지 넘김용 게임 화면 — 같은 칸의 `<게임>--NN.png`(이름순)
        shots = sorted(glob.glob(os.path.join(covers_dir, f"{glob.escape(g['id'])}--*.png")))
        if shots:
            g["shots"] = [f"covers/{os.path.basename(x)}" for x in shots]
    css, bps, slider = read("site.css"), read("bps.js"), read("slider.js")
    index_t, game_t, fix_t = read("index.frag.html"), read("game.frag.html"), read("fix.frag.html")
    data = json.dumps(site, ensure_ascii=False).replace("</", "<\\/")

    # 글자는 템플릿 · 데이터 · 스크립트 전부에서 모은다(스크립트가 화면에 쓰는 문구가 거기 산다)
    fonts = fonts_css(
        index_t + game_t + fix_t + bps + slider + json.dumps(site, ensure_ascii=False)
    )

    def fill(t, **kw):
        for k, v in kw.items():
            t = t.replace(f"@{k}@", v)
        left = re.findall(r"@[A-Z]+@", t)
        if left:
            sys.exit(f"채우지 못한 자리: {left}")
        return t

    os.makedirs(out, exist_ok=True)
    shutil.rmtree(os.path.join(out, "covers"), ignore_errors=True)  # 지난 빌드의 그림이 남지 않게
    idx = fill(index_t, FONTS=fonts, CSS=css, DATA=data)
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(idx if fragment else full_doc(idx))
    with open(os.path.join(out, "site.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(site, ensure_ascii=False, indent=2) + "\n")
    print(f"# index.html  ({os.path.getsize(os.path.join(out, 'index.html')):,}B)")

    for g in site["games"]:
        if g.get("track") != "kr" or g.get("status") not in ("released", "preparing"):
            continue
        page = fill(
            game_t,
            FONTS=fonts,
            CSS=css,
            DATA=data,
            BPSJS=bps,
            SLIDERJS=slider,
            GAME=g["id"],
            TITLE=g["title"],
            PLATFORM=g["platform"],
        )
        d = os.path.join(out, g["id"])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
            f.write(full_doc(page))
        print(f"# {g['id']}/index.html")

    # [fix] 트랙 — 게임의 patches/*.json(kind == "fix", 스키마 v2: 우리가 쓴 바이트 + sha1 만)을
    #   페이지에 인라인한다. 판정·적용은 단독 패처(patcher/index.html.tmpl)와 같다.
    for g in site["games"]:
        if g.get("track") != "fix" or not g.get("href"):
            continue
        specs = []
        for p in sorted(glob.glob(os.path.join(ROOT, "games", g["id"], "patches", "*.json"))):
            with open(p, encoding="utf-8") as f:
                spec = json.load(f)
            if spec.get("kind") == "fix":
                specs.append(spec)
        if not specs:
            sys.exit(f"{g['id']}: 실을 fix 스펙이 없다")
        page = fill(
            fix_t,
            FONTS=fonts,
            CSS=css,
            DATA=data,
            SLIDERJS=slider,
            PATCHES=json.dumps(specs, ensure_ascii=False).replace("</", "<\\/"),
            GAME=g["id"],
            TITLE=g["title"],
            PLATFORM=g["platform"],
        )
        rel = g["href"] if g["href"].endswith(".html") else g["href"] + "index.html"
        os.makedirs(os.path.dirname(os.path.join(out, rel)), exist_ok=True)
        with open(os.path.join(out, rel), "w", encoding="utf-8") as f:
            f.write(full_doc(page))
        print(f"# {rel}  (fix 스펙 {len(specs)}개)")

    # 커버(타이틀 화면 캡처)는 git 에 넣지 않는다 — 게임 화면이라 패치 파일과 같은 취급이다.
    #   이 머신에선 `.local/site-covers/<게임>.png` 에서, 배포 땐 워크플로가 릴리스 `site-covers` 에서 받아 온다.
    #   site.json 의 cover 는 그림이 실제로 있을 때만 채운다(없으면 카드가 「준비 중/진행 예정」 글자를 쓴다).
    for g in site["games"]:
        src = os.path.join(covers_dir, f"{g['id']}.png")
        if g.get("cover"):
            os.makedirs(os.path.join(out, "covers"), exist_ok=True)
            shutil.copy(src, os.path.join(out, "covers", f"{g['id']}.png"))
        for x in g.get("shots", []):
            os.makedirs(os.path.join(out, "covers"), exist_ok=True)
            shutil.copy(os.path.join(covers_dir, os.path.basename(x)), os.path.join(out, x))

    for lic in ("LICENSE-Galmuri.txt", "LICENSE-neodgm.txt"):
        shutil.copy(os.path.join(ROOT, "shared", "fonts", lic), os.path.join(out, lic))


if __name__ == "__main__":
    main()
