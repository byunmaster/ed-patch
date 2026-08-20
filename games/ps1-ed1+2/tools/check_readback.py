#!/usr/bin/env python3
"""**최종 이미지를 되읽어 의도와 대조한다** — 쓴 것이 그대로 들어갔는가.

**왜.** 여태 검증한 건 「무엇을 쓰려 했는가」였다 — 재삽입 예행도 창·줄 게이트도 전부
**후보 바이트**를 본다. 후보에서 디스크까지 사이엔 층이 더 있다: 재배치(DUMMY 이동) ·
섹터 사용자 데이터 쓰기 · **EDC/ECC 재계산**. 거기서 틀리면 게이트는 전부 초록인데 이미지만
깨진다. `build.IMMUTABLE` 은 **안 바꾼 자리**만 원본과 맞대므로 **바꾼 자리는 무방비**였다.
공용 QA 규약(kr-patch-qa) §8.9 의 `RC_READBACK_QA` 가 정확히 이 구멍이다.

⚠ **의도를 재현하려 들면 안 된다.** 처음엔 `build_scene` 을 다시 돌려 맞대 봤는데 19씬이
전부 어긋났다 — 원인은 손상이 아니라 **빌드가 그 뒤에 고아 문자열·폰트를 더 쓴다**는
것이었다(116,288B 중 243B 차이). 한 층만 재현해 전체와 맞대면 검사기가 거짓말한다.

그래서 **쓰기 시점에 지문을 남긴다**(`common.write_user_data` → `write_manifest.json`).
여기서는 그 표를 읽어 최종 이미지에서 같은 자리를 뽑아 sha1 을 맞댈 뿐이다 — 재현이 없다.

⚠ 지문은 **섹터 단위**다. 쓰기 단위로 잡았더니 같은 파일을 뒤에서 조금만 덧칠한 것 때문에
앞의 큰 쓰기가 통째로 검증 밖으로 밀려 **커버리지가 38%** 였고, 하필 **대사 씬 열아홉이
전부** 그 밖이었다. 섹터로 잡으면 마지막 쓴 사람이 자연히 이겨서 **쓴 자리를 다 본다.**

  python3 tools/check_readback.py        # 빌드 뒤에 돈다
  python3 tools/check_readback.py -v     # 통과 항목까지 전량
"""

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import BUILD_DIR, OUT_DIR, SECTOR, USER_OFF, USER_SIZE

FINAL = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")
MANIFEST = os.path.join(OUT_DIR, "write_manifest.json")


def scan(verbose=False):
    if not os.path.exists(FINAL):
        print("  ℹ 최종 이미지가 없다 — 빌드 뒤에 본다")
        return 0
    if not os.path.exists(MANIFEST):
        print("  ⚠ 쓰기 지문표가 없다 — `python3 tools/build.py` 를 한 번 돌린다")
        return 1
    with open(MANIFEST, encoding="utf-8") as f:
        man = json.load(f)
    sectors = {int(k): v for k, v in man["sectors"].items()}

    bad = []
    with open(FINAL, "rb") as f:
        for lba in sorted(sectors):
            want, label = sectors[lba]
            f.seek(lba * SECTOR + USER_OFF)
            have = hashlib.sha1(f.read(USER_SIZE)).hexdigest()
            if have != want:
                bad.append((lba, label, want, have))
    for lba, label, want, have in bad[:20]:
        print(f"    ❌ LBA {lba} · {label} — sha1 {want[:12]} ≠ {have[:12]}")
    if len(bad) > 20:
        print(f"    … 그 밖 {len(bad) - 20}섹터")
    if verbose:
        import collections

        c = collections.Counter(v[1] for v in sectors.values())
        for label, n in c.most_common():
            print(f"    ✅ {n:>6}섹터  {label}")
    print(
        f"  {'✅' if not bad else '❌'} 되읽기가 의도와 같다: 섹터 {len(sectors):,} "
        f"({len(sectors) * USER_SIZE / 1e6:.1f}MB) · 어긋남 {len(bad)}"
        + ("" if not bad else "  ← 섹터 쓰기·EDC/ECC 층을 의심한다")
    )
    return len(bad)


if __name__ == "__main__":
    sys.exit(1 if scan("-v" in sys.argv) else 0)
