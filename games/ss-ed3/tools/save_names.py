"""빌드 칸에 **해시 이름 세이브**를 이미지 옆에 놓는다 — 세이브 보관함은 해시 없는 정본만 둔다.

    (build.py 가 이미지를 다 구운 뒤 부른다)

🔴 새턴 세이브 이름은 `<이미지이름>.<GameID>.bkr` 이고 GameID 는 **앞 512 섹터**의 해시라 한글패치는 빌드마다 바뀐다
   (`scripts/emu/ss_gameid.py` 머리말). 예전엔 세이브 보관함(`~/save/ss-ed3/`)에 **빌드마다 해시 이름 사본**을 쌓아 옛 사본 수십 개가
   헷갈렸다(마스터 10-05). ⇒ 사본은 **그 빌드의 칸**에 둔다 — 이미지와 한 묶음으로 오가고, 빌드를 지우면 같이 사라진다.

   보관함(정본) = 해시 없는 `<이미지이름>.bkr/.bcr/.smpc`(mednafen 은 해시 없는 파일을 먼저 읽는다). 여기서 읽기만 한다.
⚠ 세이브 내용은 빌드 입력이 아니다 — 이미지 결정성에 안 걸린다(이미지 바이트는 그대로).
"""

import glob
import os
import re
import shutil

EXTS = ("bkr", "bcr", "smpc")
_HASHED = re.compile(r"\.[0-9a-f]{32}\.(?:bkr|bcr|smpc)$")


def default_src():
    return os.environ.get("ED_SAVE_DIR") or os.path.expanduser("~/save/ss-ed3")


def emit(src_dir, out_dir, images, game_id):
    """`images`(.cue·.m3u 경로들)마다 `<이름>.<해시>.<확장자>` 를 `out_dir` 에 놓는다. `[만든 파일]`.

    옛 해시 사본은 먼저 지운다(한 칸에 **한 빌드의 것만** — 낡은 사본이 정상으로 읽히지 않게).
    정본이 없는 확장자는 건너뛴다. 정본 폴더가 없으면 아무것도 안 한다.
    """
    for old in glob.glob(os.path.join(out_dir, "*")):
        if _HASHED.search(old):
            os.remove(old)
    if not os.path.isdir(src_dir):
        return []
    made = []
    for img in images:
        if not os.path.exists(img):
            continue
        name = os.path.splitext(os.path.basename(img))[0]
        gid = game_id(img)
        for ext in EXTS:
            src = os.path.join(src_dir, f"{name}.{ext}")
            if os.path.isfile(src):
                dst = os.path.join(out_dir, f"{name}.{gid}.{ext}")
                shutil.copyfile(src, dst)
                made.append(dst)
    return made
