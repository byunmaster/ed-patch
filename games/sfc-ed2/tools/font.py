"""sfc-ed2 글꼴 — 롬 안의 12×12 가나·한자 글리프표 추출·시트 출력(조사용, 읽기 전용).

🔎 출처(2026-10-12 에뮬 읽기 중단점 + 정적 디스어셈블로 확정)
  - 전각: `$C0:9F56` 가 `$D6:81D1 + 색인×18` 에서 **18바이트(12×12, 두 줄=3바이트 big-endian 12비트×2)** 를 `mvn` 으로
    $1328 로 복사한다. 색인 = 2바이트 코드 − $8000 (상위 $80~ 쪽 번호, 하위 쪽 내 번호). 곱셈은 `$C1:1F0B`(하드웨어 곱셈).
    복사한 뒤 `$9F9F~$A0AC` 가 비트를 섞어 **그림자(2번 색)** 를 만든다 — 롬엔 외곽선이 없다.
  - 반각: `$C0:90E8` 이 `$D6:DC19 + (코드−$20)×16` 에서 16바이트(8×16)를 복사한다(코드 $20~$7F).
⚠ 소비자(`mvn` 뱅크 $D6·기준 $81D1/$DC19)는 코드에 박힌 상수다 — 글꼴을 옮기려면 그 상수를 같이 고친다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

FULL_BASE = common.snes2off(0xD681D1)  # 0x1681D1
FULL_STRIDE = 18
HALF_BASE = common.snes2off(0xD6DC19)  # 0x16DC19
HALF_STRIDE = 16


def full_glyph(index: int) -> list[int]:
    """전각 글리프 → 12행 × 12비트(왼쪽이 최상위)."""
    d = common.rom_bytes()
    a = FULL_BASE + index * FULL_STRIDE
    rows = []
    for k in range(0, FULL_STRIDE, 3):
        v = int.from_bytes(d[a + k : a + k + 3], "big")
        rows += [(v >> 12) & 0xFFF, v & 0xFFF]
    return rows


def half_glyph(code: int) -> list[int]:
    """반각($20~$7F) 글리프 → 16행 × 8비트."""
    d = common.rom_bytes()
    a = HALF_BASE + (code - 0x20) * HALF_STRIDE
    return list(d[a : a + HALF_STRIDE])


def render(index: int) -> str:
    return "\n".join("".join("#" if (r >> (11 - x)) & 1 else "." for x in range(12)) for r in full_glyph(index))


if __name__ == "__main__":
    common.verify_originals()
    for i in [int(a, 0) for a in sys.argv[1:]] or [0x9C]:
        print(f"-- 색인 {i} (코드 $80{i:02X} 형)" if i < 256 else f"-- 색인 {i}")
        print(render(i))
