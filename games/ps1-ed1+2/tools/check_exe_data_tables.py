#!/usr/bin/env python3
"""EXE 안의 **문자열이 아닌 표**가 원판과 같은가 — 문자열 구획 재packing 이 표를 조용히 지우는 사고를 막는다.

**왜.** ED2.EXE 이름 구획(0x800~0xF44) 한복판에 u16×7 숫자표(100·250·500·1000·2500·5000·10000, 0xE6C~0xE7A)가 있는데,
`patch_ed2_sys.repack_names` 가 첫 바이트 `0x64`(`d`)를 이름으로 오인해 옮기고 나머지를 0 으로 지웠다(정적 확인 11-07,
PCE II 퀵메뉴 사고와 같은 부류: 원판 문자열 칸 안쪽에 코드가 읽는 표 바이트가 겹쳐 있었다). 읽는 코드(0x80020cf0 이벤트 등록 함수)는 그
14B 를 스택 지역 배열로 복사만 하고 다시 읽지 않아(정적 전수) 화면 증상은 없지만, 같은 부류가 다른 자리에서 터지지 않게 바이트로 잠근다.

- **핫픽스 이미지**(`ED_HOTFIX=1` 빌드, 꼬리표 `test-hotfix`) → 표가 원판과 다르면 **실패**.
- **제품 이미지**(v1.2.0 과 같은 롬) → 아는 결함이라 **알림만**(v1.2.1 핫픽스에서 고친다). 고친 뒤 제품에도 올리면 `KNOWN_OPEN` 을 비운다.

  python3 tools/check_exe_data_tables.py            # 제품 이미지
  python3 tools/check_exe_data_tables.py --hotfix   # test-hotfix 이미지(없으면 건너뜀)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import common
from common import ORIG_BIN, extract

EXES = {"ED.EXE": (257, 1021952), "ED2.EXE": (756, 872448)}
# (실행파일, 시작, 끝, 설명, 제품 롬에서 아는 결함인가)
TABLES = (("ED2.EXE", 0xE6C, 0xE7A, "이름 구획 안 u16×7 숫자표(100…10000)", True),)


def check(img, strict):
    bad = known = 0
    for name, a, b, label, open_in_product in TABLES:
        lba, size = EXES[name]
        o = bytes(extract(lba, size, path=ORIG_BIN))[a:b]
        n = bytes(extract(lba, size, path=img))[a:b]
        if o == n:
            print(f"  {name} 0x{a:X}~0x{b:X} {label}: 원판과 같다")
        elif strict or not open_in_product:
            bad += 1
            print(f"  ❌ {name} 0x{a:X}~0x{b:X} {label}: 원판과 다르다 (원판 {o.hex()} · 지금 {n.hex()})")
        else:
            known += 1
            print(f"  ⚠ {name} 0x{a:X}~0x{b:X} {label}: 원판과 다르다 — 제품 롬의 아는 결함(v1.2.1 핫픽스에서 고침)")
    return bad, known


def main():
    hot = "--hotfix" in sys.argv
    tag = "test-hotfix" if hot else None
    img = os.path.join(common.BUILD_DIR if not tag else os.path.join(os.path.dirname(common.BUILD_DIR), tag), "Eiyuu Densetsu (KR).bin")
    if not os.path.exists(img):
        print(f"  EXE 표 보존: 이미지 없음({img}) — 건너뜀")
        return 0
    bad, known = check(img, strict=hot)
    print(f"EXE 비문자열 표 [{'핫픽스' if hot else '제품'}] — 표 {len(TABLES)} · 어긋남 {bad} · 아는 결함 {known}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
