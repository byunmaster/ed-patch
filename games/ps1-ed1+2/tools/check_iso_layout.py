#!/usr/bin/env python3
"""**ISO 물리 배치가 원본과 같은가** — 파일 LBA·크기·겹침·이미지 밖 참조.

**왜.** 이 레포는 배치를 보는 눈이 없었다. 게임 `CLAUDE.md` 가 그걸 자백하고 있다 —
「🔴 재삽입 체인 등록은 ED1 인게임 QA 가 끝난 뒤에. 넣는 순간 ED1 씬 LBA 가 밀리는데
**락도 무변경 구간 검사도 그걸 못 잡는다**(둘 다 배치를 안 본다)」.

- `locked_lines`·`observed_lines` 는 **문안 해시**만 본다
- `build.IMMUTABLE` 은 **선언한 구간**의 바이트만 본다 — 파일이 통째로 밀리면 그 구간도
  같이 밀려서 「원본과 동일」이 나올 수 있다
- 재삽입 예행은 **블록**을 보지 파일 표를 안 본다

배치가 밀리면 증상이 오타가 아니라 **로드 실패·프리즈**다. 우리 전략은 「FST/LBA 고정,
내용만 교체」이므로 **차이가 0이어야 정상**이고, 하나라도 나오면 그건 사고다.

kr-patch-qa 공용 규약 §8.5(ISO/ROM 물리 배치)를 이 게임에 옮긴 것이다.

  python3 tools/check_iso_layout.py       # 원본 ↔ 최종 이미지
  python3 tools/check_iso_layout.py -v    # 파일 표 전량
"""

import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import BUILD_DIR, ORIG_BIN, SECTOR, extract

FINAL = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")
PVD_LBA = 16


def read_root(path):
    """루트 디렉터리 레코드 → `[(이름, LBA, 크기)]`.

    ⚠ 디렉터리 레코드는 **섹터를 넘지 않는다** — 길이 0 을 만나면 다음 섹터 머리로 건너뛴다.
    그걸 빼먹으면 파일 목록이 중간에서 끊긴다.
    """
    pvd = bytes(extract(PVD_LBA, 2048, path=path))
    root = pvd[156 : 156 + 34]
    lba = int.from_bytes(root[2:6], "little")
    size = int.from_bytes(root[10:14], "little")
    data = bytes(extract(lba, size, path=path))
    out, i = [], 0
    while i < len(data):
        ln = data[i]
        if ln == 0:
            i = (i // 2048 + 1) * 2048
            continue
        rec = data[i : i + ln]
        nlen = rec[32]
        name = rec[33 : 33 + nlen].decode("ascii", "replace")
        out.append((name, int.from_bytes(rec[2:6], "little"), int.from_bytes(rec[10:14], "little")))
        i += ln
    return out


def scan(verbose=False):
    if not os.path.exists(FINAL):
        print("  ℹ 최종 이미지가 없다 — 빌드 뒤에 본다")
        return 0
    src, dst = read_root(ORIG_BIN), read_root(FINAL)
    bad = []

    if len(src) != len(dst):
        bad.append(f"파일 수가 다르다 — 원본 {len(src)} · 최종 {len(dst)}")
    for a, b in zip(src, dst, strict=False):
        if a != b:
            bad.append(f"{a[0]}: LBA·크기가 밀렸다 {a[1]}/{a[2]} → {b[1]}/{b[2]}")
        elif verbose:
            print(f"    ✅ {a[0]:<14} LBA {a[1]:>7} · {a[2]:>9}B")

    # 겹침 — ⚠ `.`/`..` 은 같은 LBA 를 가리키는 게 정상이라 이름으로 뺀다
    segs = sorted(
        (lba, lba + -(-size // 2048), name)
        for name, lba, size in dst
        if size and name not in ("\x00", "\x01")
    )
    for (_l0, e0, n0), (l1, _e1, n1) in itertools.pairwise(segs):
        if e0 > l1:
            bad.append(f"겹친다 — {n0}(…{e0}) ↔ {n1}({l1}…)")

    total = os.path.getsize(FINAL) // SECTOR
    for name, lba, size in dst:
        if lba + -(-size // 2048) > total:
            bad.append(f"이미지 밖을 가리킨다 — {name} LBA {lba} + {size}B > {total}섹터")

    for m in bad:
        print(f"    ❌ {m}")
    print(
        f"  {'✅' if not bad else '❌'} ISO 배치가 원본과 같다: 파일 {len(dst)} · 어긋남 {len(bad)}"
        + ("" if not bad else "  ← 증상이 오타가 아니라 로드 실패·프리즈다")
    )
    return len(bad)


if __name__ == "__main__":
    sys.exit(1 if scan("-v" in sys.argv) else 0)
