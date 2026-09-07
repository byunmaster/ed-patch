"""빈 섹터 지도 — **한글 폰트를 어디에 싣나**의 근거.

한글 2,350자 × 32B = **75,200B**. 후보의 성질이 둘로 갈린다:

- **빈 섹터**(0xFF 로 채워진 정상 섹터) — 크고 연속이다. ⚠ 지금 로더가 안 읽는다,
  읽는 코드를 우리가 넣어야 한다.
- **꼬리 빈칸**(시나리오·전투 섹터 끝의 0x00 패딩) — **로더가 이미 읽는 자리**지만
  시나리오마다 흩어져 있어 폰트처럼 **연속이 필요한 것**엔 못 쓴다(문안 확장용이다).

🔴 **「0 런이니 비었겠지」로 판단하지 않는다** — 이 레포는 그 판단으로 사운드 뱅크를
깨뜨린 적이 있다(`docs/reference/our-findings.md` 「빈 공간의 VAB 함정」).
여기서 「비었다」는 **섹터 전체가 한 값으로 채워졌다**는 뜻이고, 그래도 **로더가 그 섹터를
읽지 않는다는 증명은 아니다.** 쓰기 전에 실기/에뮬로 확인한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import scn

HANGUL_BYTES = 2350 * 32  # 완성형 2,350자 × 16×16 1bpp


def free_sectors(secs: list[dict], fill: bytes = b"\xff") -> list[int]:
    blank = fill * common.SECTOR_SIZE
    return [s["index"] for s in secs if s["data"] == blank]


def runs_of(indices: list[int]) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for i in indices:
        if out and i == out[-1][1] + 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return [(a, b) for a, b in out]


def main() -> int:
    common.check_originals()
    print(f"한글 폰트에 필요한 크기 {HANGUL_BYTES:,}B (2,350자 × 32B)\n")
    for key in common.DISKS:
        secs = common.read_sectors(common.disk_path(key))
        assert len(secs) == common.SECTOR_COUNT
        ff = free_sectors(secs, b"\xff")
        zz = free_sectors(secs, b"\x00")
        rs = sorted(runs_of(ff), key=lambda r: -(r[1] - r[0]))
        total = len(ff) * common.SECTOR_SIZE
        print(f"{key:9s} 빈 섹터 {len(ff):4d} = {total:9,}B  (전부 0x00 인 섹터 {len(zz)})")
        for a, b in rs[:4]:
            size = (b - a + 1) * common.SECTOR_SIZE
            fits = " ← 폰트가 들어간다" if size >= HANGUL_BYTES else ""
            print(f"            섹터 {a:4d}~{b:4d}  {size:9,}B{fits}")

    scenario, combat = scn.load()
    tail = sum(v["tail_free"] for v in scenario.values()) + sum(
        v["tail_free"] for v in combat.values()
    )
    print(f"\n꼬리 빈칸 합 {tail:,}B — **로더가 이미 읽는 자리**지만 흩어져 있다(문안 확장용).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
