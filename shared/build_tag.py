"""빌드 산출물을 가르는 **꼬리표** — 기본은 현재 git 브랜치.

한 게임 안에서도 갈래를 동시에 굴린다(ED1 QA 를 도는 사이 ED2 빌드가 덮어썼다 —
유저 요청 2026-08-15). 그래서 이미지를 `work/build/<꼬리표>/` 로 나눈다. 도구는
`BUILD_DIR` 만 쓰므로 **하나도 안 고쳐도 따라온다.**

⚠ **여기 있는 이유는 둘째 소비자가 실재해서다**(YAGNI — 루트 `CLAUDE.md`). PS1 이 쓰던
것을 새턴이 그대로 필요로 했고, 아래 워크트리 함정이 **양쪽에 똑같이** 있다.
"""

import os


def build_tag(env="ED_BUILD_TAG"):
    """`<브랜치>` · 환경변수로 덮어씀 · 못 읽으면 `local`.

    ⚠ **워크트리에서는 `.git` 이 디렉터리가 아니라 파일**이다(`gitdir: …` 한 줄). 그대로
    `.git/HEAD` 를 열면 실패해 전부 `local` 로 떨어지는데, 갈래를 가르려고 만든 장치가
    **정작 갈래를 굴리는 자리에서만 안 도는** 꼴이 된다(2026-08-18 실측). 따라간다.

    ⚠ 파일명에 들어가므로 `/` 같은 글자는 `-` 로 바꾼다 — `game/ps1-ed1+2` 를 그대로 쓰면
    디렉터리가 한 겹 더 생긴다.
    """
    tag = os.environ.get(env)
    if not tag:
        # 이 파일은 `<레포>/shared/` 에 있다 — 레포 루트는 한 단계 위다.
        git = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".git")
        try:
            if os.path.isfile(git):  # 워크트리 — `gitdir: <실제 경로>`
                with open(git, encoding="utf-8") as f:
                    git = f.read().strip().split(":", 1)[1].strip()
            with open(os.path.join(git, "HEAD"), encoding="utf-8") as f:
                ref = f.read().strip()
            tag = ref.rsplit("/", 1)[-1] if ref.startswith("ref:") else ref[:7]
        except (OSError, IndexError):
            tag = "local"
    return "".join(c if (c.isalnum() or c in "-_.") else "-" for c in tag) or "local"
