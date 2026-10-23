#!/usr/bin/env python3
"""재배치 장부 게이트 — 방금 구운 빌드의 장부(`work/build/<꼬리표>/relocations.tsv`, build.py 가 `structure.py` 로 뽑는다)를 커밋된 장부
(`games/pce-ed1/relocations.tsv`)와 비교한다. **장부에 없던 (블록, 종류) 가 새로 생기면 실패**(마스터 10-22 — 재배치를 한 곳은 전부 장부로 남긴다).
구조 대조 위반은 build.py 안에서 이미 빌드를 실패시킨다(대조 블록 수·위반 수 출력).

    python3 tools/check_relocations.py            # 비교(게이트)
    python3 tools/check_relocations.py --freeze   # 새 장부를 커밋 대상으로 복사(재배치를 의도적으로 바꿨을 때만)
수·좌표는 문안이 바뀌면 흔들리므로 **비교는 (블록 키, 종류) 집합**이다 — 숫자 변화는 알림만.
"""

import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common

COMMITTED = HERE.parent / "relocations.tsv"


def load(p: Path) -> dict[tuple[str, str], int]:
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        f = line.split("\t")
        out[(f[0], f[1])] = int(f[2])
    return out


def main() -> int:
    built = common.BUILD_DIR / common.BUILD_TAG / "relocations.tsv"
    if not built.exists():
        print(f"✘ {built} 가 없다 — 빌드가 장부를 못 냈다(build.py 가 먼저 돌아야 한다)")
        return 1
    if "--freeze" in sys.argv:
        COMMITTED.write_text(built.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  재배치 장부 갱신: {COMMITTED}")
        return 0
    if not COMMITTED.exists():
        print("✘ 커밋된 재배치 장부(games/pce-ed1/relocations.tsv)가 없다 — `check_relocations.py --freeze` 로 만든다")
        return 1
    new, old = load(built), load(COMMITTED)
    added = sorted(set(new) - set(old))
    gone = sorted(set(old) - set(new))
    kinds = Counter(k for _b, k in new)
    print("재배치 장부 — 행 %d(종류별: %s) · 커밋 장부 %d행" % (len(new), " ".join(f"{k} {v}" for k, v in sorted(kinds.items())), len(old)))
    if gone:
        print(f"  ⓘ 장부에만 있고 이번 빌드엔 없는 (블록, 종류) {len(gone)}건 — 재배치가 줄었다(`--freeze` 로 정리): {gone[:5]}")
    if added:
        print(f"✘ 장부에 없는 재배치 {len(added)}건 — 의도한 변경이면 `check_relocations.py --freeze` 로 장부를 갱신하고 사유를 devlog 에 남긴다:")
        for b, k in added[:30]:
            print(f"    {b}\t{k}")
        return 1
    print("  ✅ 장부에 없는 재배치 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
