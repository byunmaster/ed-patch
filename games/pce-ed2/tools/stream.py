"""씬 대본 스트림 — 위치·앵커 검증. 첫 마을(エルアスタ) 씬 패키지(rel 386 ×78, 뱅크 0x73~)의 대본.

대본 = LZ 한 줄기(`lz.py`) — **시작 rel 396 +593**(게임이 `$575A` 에 A=`$92` X=`$51`, MPR4=0x75 로 넘기는 `$9251`)에서
푼 첫 줄이 지역명(「…の町」)이고, 줄은 `00` 으로 끝난다. 게임은 목표 줄까지 **처음부터 다시 풀며 센다**(초기화 `$5796`).
패키지 → 뱅크: rel 386 이 뱅크 0x73 첫 섹터, 섹터 4개 = 뱅크 하나(0x73 = 386~389 … 0x75 = 394~397 · 0x76 = 398~401).

⚠ 이 모듈은 **디스크 좌표와 디코더 상태의 일치**를 못 박는다 — 대본 의미(제어코드)는 아직 다 모른다.
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import lz

PKG_REL, PKG_SECTORS = 386, 78
TEXT_START = (396, 593)  # (rel, 섹터 안 오프셋)

# 에뮬 체크포인트(대사창을 넘기며 `$5796` 초기화 직전에 캡처): (입력 끝 rel, 오프셋, 쓰기 인덱스, 링 sha1)
# — 디코더가 이 위치에서 이 상태여야 한다. 한 곳이 아니라 다섯이다(링 256B 가 통째로 일치).
ANCHORS = [
    (397, 549, 7, "02c47f5bb34b0b5392c2a129918ff59de77c9aa4"),
    (397, 650, 128, "91134c4ec2b55981446dd138f28db7f080bd628e"),
    (397, 761, 246, "6794c3a824dbdc51f09750f4f3c4d33cb1aa8835"),
    (397, 791, 24, "85b3f4b707bb56a8c43ffbfdd928cd206e941405"),
    (397, 824, 70, "6f44dec6584208a4a6adbf370feeee00ea4209f1"),
]


def package() -> bytes:
    return bytes(common.track_data(PKG_REL, PKG_SECTORS))


def verify() -> None:
    pkg = package()
    start = (TEXT_START[0] - PKG_REL) * common.USER + TEXT_START[1]
    want = {((r - PKG_REL) * common.USER + o, w): h for r, o, w, h in ANCHORS}
    seen = set()
    for _b, pos, w, ring in lz.walk(pkg, start):
        key = (pos, w)
        if key in want and key not in seen and hashlib.sha1(ring).hexdigest() == want[key]:
            seen.add(key)
        if len(seen) == len(want) or pos > (398 - PKG_REL) * common.USER:
            break
    assert len(seen) == len(want), (
        f"스트림 앵커 불일치: {len(seen)}/{len(want)} — 디코더나 좌표가 틀렸다"
    )
    print(
        f"대본 스트림 앵커 {len(seen)}/{len(want)} 일치 (rel {TEXT_START[0]} +{TEXT_START[1]} 시작)"
    )


if __name__ == "__main__":
    common.verify_originals()
    verify()
