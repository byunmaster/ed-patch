"""배포용 빌드 칸(work/build/<꼬리표>/)의 이미지가 **전 트랙**인지 본다 — 원본과 같은 크기 · cue 24트랙.
없으면 「안 쟀다」(통과가 아니다). 잘라 낸 에뮬용 빌드는 `-trim` 칸으로 나가므로 여기 안 온다."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build
import common


def main() -> int:
    d = common.BUILD_DIR / common.BUILD_TAG
    iso, cue = d / "ed2.iso", d / "ed2.cue"
    if not iso.exists():
        print(f"  빌드 칸 레이아웃: 안 쟀다({d.name} 에 이미지 없음 — 전체 빌드 때 build.py 가 검사한다)")
        return 0
    try:
        build.check_full_layout(iso, cue)
    except build.BuildError as e:
        print(f"  ❌ 빌드 칸 레이아웃: {e} — 잘린 이미지가 배포 칸에 있다")
        return 1
    print("  빌드 칸 레이아웃 OK — 원본과 같은 크기 · 24트랙")
    return 0


if __name__ == "__main__":
    sys.exit(main())
