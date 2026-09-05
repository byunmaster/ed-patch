#!/usr/bin/env python3
"""빌드 결정성 검사 — **어디서 빌드하든 같은 바이트가 나와야 한다.**

이 레포의 기본 원칙이다(유저 확정 2026-08-04). 지켜지지 않으면 "집에서 되는데 회사에서 안 된다"가
되고, 그때부터는 **버그를 재현할 수 없어 조사 자체가 불가능**해진다. 실제로 그 사고를 겪었다 —
빌드 경로 한복판에 LaBSE 임베딩이 있어 회사 빌드와 집 빌드가 달랐다(좌표 117건·문안 24건,
2026-08-03). 그래서 비결정적 제안 생성과 결정적 빌드를 갈랐고(`align_map.json` 정본),
이 스크립트는 **그 분리가 유지되고 있는지**를 매번 되묻는다.

검사 방법: 정상 빌드 → 파생물 중 **비결정적 원천**(`work/derived/align`, LaBSE 산출물)을 치우고
재빌드 → sha1 대조. 같아야 통과. 다르면 빌드가 그 파생물을 읽고 있다는 뜻이다.

  python3 tools/check_determinism.py

⚠ 더 강한 검사는 `work/derived` 를 통째로 지우고 덤프 둘(`extract_scn`·`extract_dos_kr`)만
재생성해 돌리는 것이다 — 시간이 더 들지만 머신을 옮겼을 때의 실제 상황에 가깝다.
"""

import hashlib
import os
import shutil
import subprocess
import sys

from common import BUILD_DIR, OUT_DIR

TOOLS = os.path.dirname(os.path.abspath(__file__))
IMAGE = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")
NONDET = os.path.join(OUT_DIR, "align")  # LaBSE 산출물 — 빌드가 읽으면 안 된다


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build():
    subprocess.run(
        [sys.executable, os.path.join(TOOLS, "build.py")],
        check=True,
        cwd=TOOLS,
        stdout=subprocess.DEVNULL,
    )


def main():
    print("① 정상 빌드")
    build()
    a = sha1(IMAGE)
    print(f"   sha1 {a}")

    moved = NONDET + ".determinism-check"
    if os.path.exists(NONDET):
        shutil.move(NONDET, moved)
    try:
        print("② 비결정적 파생물(work/derived/align) 없이 재빌드")
        build()
        b = sha1(IMAGE)
        print(f"   sha1 {b}")
    finally:
        if os.path.exists(moved):
            if os.path.exists(NONDET):
                shutil.rmtree(NONDET)
            shutil.move(moved, NONDET)

    if a == b:
        print("\n✅ 통과 — 어디서 빌드해도 같은 이미지가 나온다")
        return 0
    print(
        "\n❌ 실패 — 빌드가 비결정적 파생물을 읽고 있다.\n"
        "   배정은 `align_map.json`(커밋)이 정본이어야 한다. `past_align_semantic` 은 제안 생성기다."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
