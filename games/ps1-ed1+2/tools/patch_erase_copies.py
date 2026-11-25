#!/usr/bin/env python3
"""원판 대사 사본 지우기 — 핫픽스 경로(`ED_HOTFIX=1`) 전용(마스터 11-17, PCE I 사본 사고).

우리가 번역해 바꾼 자리 밖에 원판 일본어(SJIS 10자↑)가 그대로 남은 사본을 `check_orig_copies` 와 **같은 탐색**으로 찾아
0 으로 지운다 — ① 번역하며 새 LBA 로 옮긴 씬 파일의 옛 자리 ② 동영상 EXE 넷(OPEN1·2·END1·2)이 **한 벌씩 다 들고 있는** 남의 몫
내레이션(각자 자기 몫만 튼다 — 읽기 BP 실측) ③ 옮긴 파일 안 상자·상점 안내 원문. 전부 읽히지 않음을 시험 롬(사본을 지운 이미지)의
실화면으로 확인했다(ED1·ED2 오프닝·첫 장면 픽셀 차 0).

⚠ 지운 자리는 「원판과 다른 자리」가 되므로 그 자체가 새 바늘이 된다 — 같은 덩이의 다른 사본이 나오지 않을 때까지 되풀이한다.
⚠ 쓰기 가드: OPEN1 「ED2 오프닝 내레이션」 무변경 선언은 핫픽스에선 `common.IMMUTABLE` 에서 빠진다(지우는 게 목적인 구간이라).
제품 롬(v1.2.0)은 `ED_HOTFIX` 끔이면 안 건드린다.
"""

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common as C
import check_orig_copies as K
from patch_hangul_glyph_table import IMG

MAX_ROUNDS = 5


def apply():
    if os.environ.get("ED_HOTFIX") != "1":
        return 0
    total = 0
    for rnd in range(MAX_ROUNDS):
        _, _, hits, _ = K.scan(IMG)
        if not hits:
            break
        by = collections.defaultdict(list)
        for off, nd in hits:
            for i in range(len(nd)):
                by[(off + i) // C.USER_SIZE].append((off + i) % C.USER_SIZE)
        with open(IMG, "r+b") as f:
            for lba, offs in sorted(by.items()):
                d = bytearray(C.extract(lba, C.USER_SIZE, path=IMG))
                for x in offs:
                    d[x] = 0
                C.write_user_data(f, lba, bytes(d), label=f"원판 사본 지움(라운드 {rnd + 1})")
        total += len(hits)
        print(f"  원판 사본 지움 라운드 {rnd + 1}: {len(hits)}건 · 섹터 {len(by)}")
    else:
        raise SystemExit("  ❌ 원판 사본 지움이 수렴하지 않는다")
    return total


if __name__ == "__main__":
    sys.exit(0 if apply() is not None else 1)
