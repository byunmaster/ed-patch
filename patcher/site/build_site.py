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

글꼴(프리텐다드)은 페이지에 쓰이는 글자만 남겨 base64 로 박는다(`patcher/subset_font.py` 의 서브셋 함수를
그대로 쓴다 — 프리텐다드 원본은 `vendor/pretendard/`, `scripts/fetch_galmuri.sh` 가 받는다).
"""

import base64
import glob
import io
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


def main_root():
    """메인 트리 루트 — 워크트리에서 돌려도 git common dir 로 거슬러 찾는다."""
    try:
        common = subprocess.run(
            ["git", "-C", ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return os.path.dirname(common)
    except (OSError, subprocess.CalledProcessError):
        return ROOT


# 마스터 소장 그림 — 카드 표지(상자 그림 `_cover`)·상세 페이지 게임 화면(`_screenshot`, `<게임>--NN.png`).
#   HDD 소장 폴더가 정본이다(docs/machine-setup.md, 마스터 10-25). 없는 머신(배포 워크플로 포함)에선 예전 칸
#   (`SITE_COVERS` · `.local/ship/site-covers`)으로 물러난다 — 거기엔 릴리스 `site-covers` 에 올린 같은 그림이 있다.
ART_DIR = os.environ.get("SITE_ART") or "/mnt/originals/_cover"
SHOT_DIR = os.environ.get("SITE_SHOTS") or "/mnt/originals/_screenshot"
# 게임 화면 캡처는 저장소에 커밋한다(마스터 10-28 「스크린샷을 git에 넣어도 상관없지 않나」 — 한글이 보이는
#   것만 골라 넣었다). `shots/<게임>--NN.png` 는 상세 페이지 넘김, `shots/<게임>.png` 는 상자 그림이 없는 게임의
#   카드 표지. 상자 그림(`_cover`)은 원저작물이라 저장소에 넣지 않고 예전처럼 릴리스 `site-covers` 로 받는다.
SHOTS = os.path.join(HERE, "shots")


def local_dir(name):
    """`.local/<name>` — 워크트리엔 `.local/` 이 안 따라오므로 메인 트리 것을 거슬러 찾는다(루트 CLAUDE.md)."""
    for base in (ROOT, main_root()):
        p = os.path.join(base, ".local", name)
        if os.path.isdir(p):
            return p
    return os.path.join(ROOT, ".local", name)


def read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


# 🔴 **예약 글꼴 이름(RFN)** — 프리텐다드는 OFL 에 RFN 이 붙어 있어, 고친 판(서브셋도 고친
#    판이다)은 원래 이름을 쓸 수 없다. 그래서 서브셋한 뒤 글꼴 안의 이름 표(name)를 우리 이름으로
#    바꾸고 CSS 에서도 그 이름으로 부른다.
# 글꼴은 프리텐다드 하나다(마스터 10-06 「배포페이지는 프리텐다드로 통일」). 갈무리는 웹 패처 몫이다.
PRETENDARD = os.path.join(ROOT, "vendor", "pretendard")
RFN_FACES = [
    # (CSS·글꼴 안 이름, 원본, font-weight, 원래 이름 — 고지용)
    ("EDText", os.path.join(PRETENDARD, "Pretendard-Regular.woff2"), 400, "Pretendard"),
    ("EDText", os.path.join(PRETENDARD, "Pretendard-Bold.woff2"), 700, "Pretendard"),
]


def _renamed(woff2, family, weight):
    """서브셋 바이트의 이름 표를 family 로 바꿔 다시 woff2 로."""
    from fontTools.ttLib import TTFont

    font = TTFont(io.BytesIO(woff2))
    style = "Bold" if weight >= 700 else "Regular"
    names = {
        1: family,
        2: style,
        3: f"{family}-{style}-subset",
        4: f"{family} {style}",
        6: f"{family}-{style}",
        16: family,
        17: style,
    }
    tbl = font["name"]
    for rec in list(tbl.names):
        if rec.nameID in names:
            rec.string = names[rec.nameID]
        elif rec.nameID in (21, 22, 25):  # WWS·변형 이름에도 원래 이름이 남는다
            tbl.removeNames(nameID=rec.nameID)
    buf = io.BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    return buf.getvalue()


def fonts_css(text):
    chars = (subset_font.ALWAYS | set(text)) - {c for c in text if not c.isprintable()}
    rules = []
    for family, path, weight, _orig in RFN_FACES:
        if not os.path.exists(path):
            sys.exit(f"글꼴 원본이 없다: {path}\n  sh scripts/fetch_galmuri.sh 를 먼저 돌린다")
        data = _renamed(subset_font.subset_face(path, chars), family, weight)
        b64 = base64.b64encode(data).decode("ascii")
        disp = "swap"  # 글자가 늦게 와도 기본 글꼴로 먼저 보이게
        rules.append(
            f"@font-face{{font-family:'{family}';font-weight:{weight};font-display:{disp};"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}"
        )
    return (
        "/* 프리텐다드 (Pretendard → EDText) —\n"
        "   SIL OFL 1.1, 쓰이는 글자만 남긴 서브셋. 예약 글꼴 이름이 있어 이름을 바꿨다.\n"
        "   전문은 배포물의 LICENSE-Pretendard.txt */\n" + "\n".join(rules)
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
    covers_dir = os.environ.get("SITE_COVERS") or local_dir("ship/site-covers")
    shot_dir = SHOTS
    src_of = {}
    crop_of = {}  # 카드 표지를 테두리 잘라 구울 칸 → (자를 상자, 구울 크기)  # 굽는 칸 이름 → 원본 경로(site.json 엔 안 싣는다 — 머신 경로라)
    for g in site["games"]:
        # 카드 표지는 인게임 캡처(마스터 10-28 「인게임 캡쳐를 카드로 쓰는게 낫겠다」) — 그 게임의 첫 화면
        #   `shots/<게임>--00.png`(마스터 「타이틀이미지들을 파일명 00으로」). `shots/<게임>.png` 가 있으면 그게 이긴다.
        #   상자 그림은 캡처가 하나도 없을 때만.
        cover_png = os.path.join(SHOTS, f"{g['id']}.png")
        firsts = sorted(glob.glob(os.path.join(SHOTS, f"{glob.escape(g['id'])}--*.png")))
        if not os.path.exists(cover_png) and firsts:
            cover_png = firsts[0]
        art = os.path.join(ART_DIR, g["art"]) if g.get("art") else None
        if art and not os.path.exists(art):
            art = os.path.join(covers_dir, f"{g['id']}.png")  # 배포 워크플로 — 릴리스에서 받은 상자 그림
        if not os.path.exists(cover_png) and art and os.path.exists(art):
            cover_png = art  # 상자 그림이 있으면 그걸 카드에(같은 이름 covers/<게임>.png 로 굽는다)
        if os.path.exists(cover_png):
            g["cover"] = f"covers/{g['id']}.png"
            src_of[g["cover"]] = cover_png
            if cover_png == art:
                g["cover_art"] = True  # 상자 그림 — 화면 캡처처럼 4:3 으로 펴지 않고 비율을 지킨다
            else:
                # 기종 화면(내부 해상도 그대로의 캡처)은 TV 처럼 4:3 으로 편다. 녹화본처럼 이미 16:9 로
                # 늘어난 그림은 펴면 찌그러지니 비율을 지켜 검은 바탕에 앉힌다(카드에서 `wide`).
                # ⚠ 「가로가 길다」로 가르면 안 된다 — PS1 고해상도 모드는 560×240(2.33)인데도 4:3 화면이다.
                #   16:9 에 딱 맞는 것만 녹화본으로 본다.
                from PIL import Image

                with Image.open(cover_png) as im:
                    if abs(im.width / im.height - 16 / 9) < 0.02:
                        g["cover_wide"] = True
                    else:
                        # 타이틀이 검은 테두리 안에 작게 앉은 캡처(PS1 IV 등)는 카드에선 테두리를 잘라 칸을
                        #   채운다(마스터 10-28 「이건 왜 카드화면에 꽉 안차?」). 4:3 으로 편 화면 기준의 비율을
                        #   지켜 굽고 카드에선 object-fit: cover. 상세 페이지 넘김 그림은 그대로 둔다.
                        bb = im.convert("L").point(lambda v: 255 if v > 12 else 0).getbbox()
                        if bb and (bb[2] - bb[0] < im.width * 0.9 or bb[3] - bb[1] < im.height * 0.9):
                            cw, ch = bb[2] - bb[0], bb[3] - bb[1]
                            disp = (cw / im.width * 4) / (ch / im.height * 3)
                            crop_of[g["cover"]] = (bb, (round(ch * disp), ch))
                            g["cover_trim"] = True
        # 상세 페이지 넘김용 게임 화면 — 같은 칸의 `<게임>--NN.png`(이름순)
        shots = sorted(glob.glob(os.path.join(shot_dir, f"{glob.escape(g['id'])}--*.png")))
        if shots:
            g["shots"] = [f"covers/{os.path.basename(x)}" for x in shots]
            src_of.update({f"covers/{os.path.basename(x)}": x for x in shots})
    css, bps, slider, theme = read("site.css"), read("bps.js"), read("slider.js"), read("theme.js")
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
    idx = fill(index_t, FONTS=fonts, THEMEJS=theme, CSS=css, DATA=data)
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
            THEMEJS=theme,
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
            THEMEJS=theme,
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
    #   이 머신에선 `.local/ship/site-covers/<게임>.png` 에서, 배포 땐 워크플로가 릴리스 `site-covers` 에서 받아 온다.
    #   site.json 의 cover 는 그림이 실제로 있을 때만 채운다(없으면 카드가 「준비 중/진행 예정」 글자를 쓴다).
    #   배포 전엔 굽힌 `covers/*.png` 를 그대로 릴리스 `site-covers` 에 올린다(상자 그림도 `<게임>.png` 이름으로 들어 있다).
    for rel, src in src_of.items():
        os.makedirs(os.path.join(out, "covers"), exist_ok=True)
        if rel in crop_of:
            from PIL import Image

            box, size = crop_of[rel]
            with Image.open(src) as im:
                im.crop(box).resize(size, Image.NEAREST).save(os.path.join(out, rel))
            continue
        shutil.copy(src, os.path.join(out, rel))

    # 이 머신에서 미리 볼 때 — 패치 파일을 게임 빌드 칸(work/dist, 워크트리가 이긴다)에서 옆에 둔다.
    #   배포 때는 워크플로가 릴리스에서 받아 같은 자리에 둔다(그래서 여기서는 없으면 조용히 넘어간다).
    for g in site["games"]:
        r = g.get("release") or {}
        # 업그레이드 사슬 칸(chain[].bps·xdelta)도 같은 자리에 둔다 — 웹 패치가 칸을 차례로 받는다
        names = [r.get("bps"), r.get("xdelta")]
        names += [c.get(k) for c in r.get("chain") or [] for k in ("bps", "xdelta")]
        for name in names:
            if not name:
                continue
            main = main_root()
            for base in (os.path.join(main, ".claude", "worktrees", g["id"]), main):
                src = os.path.join(base, "games", g["id"], "work", "dist", name)
                if os.path.exists(src):
                    shutil.copy(src, os.path.join(out, g["id"], name))
                    break

    shutil.copy(
        os.path.join(PRETENDARD, "LICENSE.txt"), os.path.join(out, "LICENSE-Pretendard.txt")
    )


if __name__ == "__main__":
    main()
