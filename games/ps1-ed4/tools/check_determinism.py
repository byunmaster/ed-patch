"""결정성 검사 — **같은 입력을 두 번 구워 sha1 을 맞댄다**(제1 원칙: 같은 입력이면 같은 바이트).

    python3 tools/check_determinism.py [--probe]

① 무변경 왕복을 서로 다른 꼬리표 칸에 두 번 굽는다 → 둘이 같고 **원본과도 같아야** 한다.
② `--probe` 면 재삽입 시험(`probe.py` 의 가짜 한글 줄)도 두 번 굽는다 → 둘이 같아야 한다.
구움은 **별도 프로세스**로 한다(같은 프로세스면 캐시·전역이 같아 결정성을 못 잰다).
"""

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

HERE = os.path.dirname(os.path.abspath(__file__))


def sha(path):
    return common.sha1_of(path)


def bake(script, tag, *args):
    env = dict(os.environ, ED_BUILD_TAG=tag)
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, script), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode:
        raise SystemExit(
            f"🔴 {script} 이 실패했다(tag {tag}):\n{r.stdout[-800:]}\n{r.stderr[-800:]}"
        )
    bdir = os.path.join(common.WORK_DIR, "build", tag)
    bins = [f for f in os.listdir(bdir) if f.endswith(".bin")]
    if len(bins) != 1:
        raise SystemExit(f"🔴 {bdir} 에 이미지가 {len(bins)}개 — 한 칸에 하나여야 한다")
    return os.path.join(bdir, bins[0])


def main():
    probe = "--probe" in sys.argv
    runs = [("build.py", "identity")] + ([("probe.py", "probe")] if probe else [])
    bad = 0
    for script, name in runs:
        tags = [f"test-det-{name}-{i}" for i in (1, 2)]
        outs = [bake(script, t) for t in tags]
        h = [sha(o) for o in outs]
        ok = h[0] == h[1]
        extra = ""
        if name == "identity":
            ok = ok and h[0] == common.DISC["sha1"]
            extra = " · 원본과 " + ("같다" if h[0] == common.DISC["sha1"] else "다르다")
        print(f"{'✅' if ok else '🔴'} {name}: {h[0][:12]} / {h[1][:12]}{extra}")
        bad += not ok
        for t in tags:  # 시험 칸은 쓰고 나면 지운다(루트 CLAUDE.md — test-* 칸)
            shutil.rmtree(os.path.join(common.WORK_DIR, "build", t), ignore_errors=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
