#!/usr/bin/env python3
"""배포 페이지 그림(카드 표지·게임 화면)을 릴리스 `site-covers` 와 맞추고, 바뀌면 페이지를 다시 띄운다.

    python3 scripts/publish/sync_site_art.py            # 바뀐 것만 올리고 pages 워크플로를 돌린다
    python3 scripts/publish/sync_site_art.py --dry-run  # 무엇을 올리고 지울지만 찍는다

마스터 10-25: 「따로 배포 안하더라도 내가 스크린샷 파일 추가하면 적용되게」 — 그림 원본은 HDD 소장 폴더
(`/mnt/originals/_cover` · `_screenshot`, docs/machine-setup.md)라 GitHub 이 못 본다. 그래서 이 머신이
`build_site.py` 로 굽힌 `covers/*.png` 를 릴리스에 올리고 워크플로를 부른다(워크플로는 그 릴리스에서 받는다).
🔴 10-28 부터 릴리스엔 **상자 그림(카드 표지)만** 올린다 — 게임 화면 캡처는 저장소 `patcher/site/shots/` 에 커밋한다
(마스터 「스크린샷을 git에 넣어도 상관없지 않나」 · 「커버아트는 고민이네. 우선 캡쳐만 넣어보자」).
**배포 때 한 번** 돌린다(main 푸시 뒤) — 바뀐 게 없으면 아무것도 안 한다. 크론·폴더 감시는 마스터가 접었다(10-26
「동적처리를 위해 얻는것보다 드는 품이 더 큰것 같아」).

- 무엇이 바뀌었나는 릴리스에 같이 올리는 `site-covers.sha1.json`(이름 → sha1)으로 가린다.
- 🔴 원격 main 의 사이트 빌드가 `_cover`/`_screenshot` 을 아는 판(`SHOT_DIR`)이 아니면 **아무것도 안 올린다** —
  옛 빌드는 `<게임>.png` 를 타이틀 캡처로 알고 4:3 으로 펴서, 상자 그림이 찌그러진 채 나간다(마스터 「배포는 다음 배포때」).
"""

import glob
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REL = "site-covers"
MANIFEST = "site-covers.sha1.json"


def run(*cmd, check=True):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=check)


def remote_ready():
    """원격 main 의 build_site.py 가 HDD 그림 자리를 아는가."""
    run("git", "fetch", "-q", "origin", "main", check=False)
    r = run("git", "show", "origin/main:patcher/site/build_site.py", check=False)
    return r.returncode == 0 and "SHOT_DIR" in r.stdout


def local_art(out):
    run(sys.executable, os.path.join(ROOT, "patcher/site/build_site.py"), "--out", out)
    have = {}
    with open(os.path.join(ROOT, "patcher/site/site.json"), encoding="utf-8") as f:
        arts = {g["id"] for g in json.load(f)["games"] if g.get("art")}
    for p in sorted(glob.glob(os.path.join(out, "covers", "*.png"))):
        if os.path.basename(p)[:-4] not in arts:
            continue  # 게임 화면 캡처는 저장소(patcher/site/shots)에 있다 — 릴리스엔 상자 그림만
        with open(p, "rb") as f:
            have[os.path.basename(p)] = (hashlib.sha1(f.read()).hexdigest(), p)
    return have


def remote_art():
    names = run(
        "gh", "release", "view", REL, "--json", "assets", "--jq", ".assets[].name"
    ).stdout.split()
    sums = {}
    if MANIFEST in names:
        r = run("gh", "release", "download", REL, "-p", MANIFEST, "-O", "-", check=False)
        if r.returncode == 0:
            sums = json.loads(r.stdout)
    return {n for n in names if n.endswith(".png")}, sums


def main(argv):
    dry = "--dry-run" in argv
    if not remote_ready():
        print("⏭ 원격 main 의 사이트 빌드가 아직 옛 판이다 — 다음 배포(main 푸시) 뒤부터 돈다")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        have = local_art(tmp)
        if not have:
            print("🔴 구운 그림이 0 이다 — HDD 그림 자리를 못 읽었나(빈 채로 올리면 전부 지워진다)")
            return 1
        names, sums = remote_art()
        up = [n for n, (h, _) in have.items() if sums.get(n) != h or n not in names]
        gone = sorted(names - set(have))
        print(f"그림 {len(have)} · 올릴 것 {len(up)} · 지울 것 {len(gone)}")
        for n in up:
            print("  ↑", n)
        for n in gone:
            print("  ✗", n)
        if dry or not (up or gone):
            return 0
        if up:
            run("gh", "release", "upload", REL, "--clobber", *[have[n][1] for n in up])
        for n in gone:
            run("gh", "release", "delete-asset", REL, n, "-y")
        mf = os.path.join(tmp, MANIFEST)
        with open(mf, "w") as f:
            json.dump(
                {n: h for n, (h, _) in have.items()},
                f,
                ensure_ascii=False,
                indent=1,
                sort_keys=True,
            )
        run("gh", "release", "upload", REL, "--clobber", mf)
        run("gh", "workflow", "run", "pages.yml", "--ref", "main")
        print("✅ 올리고 pages 워크플로를 돌렸다")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
