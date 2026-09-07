"""시나리오·전투 디렉터리 — 「대본이 어느 섹터에 사나」의 정본.

디스크에 파일 시스템이 없다. 로더가 **섹터를 직접 읽으므로** 디렉터리라는 것도
「몇 번째 섹터부터 몇 장이 한 시나리오인가」라는 규약뿐이다.

규약(우리 이미지에서 재확인, 2026-08-30):

    시나리오 영역 = 논리 섹터 256 ~ 808
    각 시나리오 = 머리 섹터 1 + `머리[6]` 장
    머리 섹터 0x00 `e9 xx xx` = 진입점 0xe000, 0x03 `e9 xx xx` = 0xe003
    전투 영역   = 논리 섹터 896 ~ 1005, **한 장에 하나**

⚠ **예외 둘은 데이터가 거짓말을 한다** — `머리[6]` 이 그 자리에서 다른 뜻으로 쓰인다.
  선행 영문 패치도 같은 자리에 같은 예외를 박아 뒀다(docs/prior-art.md) — 서로 독립으로
  같은 값에 걸렸으니 데이터의 성질로 본다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

SCENARIO_RANGE = (256, 809)
COMBAT_RANGE = (896, 1006)

# 🔴 머리[6] 을 못 믿는 자리. 키는 (C,H,R).
CHUNK_COUNT_OVERRIDE = {
    (0x20, 0x00, 0x20): 2,
    (0x26, 0x01, 0x22): 3,
}


def key_of(sec: dict) -> tuple[int, int, int]:
    return (sec["c"], sec["h"], sec["r"])


def format_key(key: tuple[int, int, int]) -> str:
    return f"{key[0]:02x}.{key[1]:02x}.{key[2]:02x}"


def scenario_directory(sectors: list[dict]) -> dict[tuple, dict]:
    """{(C,H,R): {'index', 'sector_count', 'data', 'tail_free'}}"""
    out = {}
    i = SCENARIO_RANGE[0]
    while i < SCENARIO_RANGE[1]:
        head = sectors[i]
        key = key_of(head)
        count = CHUNK_COUNT_OVERRIDE.get(key, head["data"][6])
        if count > 10:
            raise SystemExit(f"chunk_count 이상 {format_key(key)} = {count} — 규약이 바뀌었다")
        members = sectors[i : i + 1 + count]
        data = b"".join(s["data"] for s in members)
        tail = len(data) - len(data.rstrip(b"\x00"))
        out[key] = {
            "index": i,
            "sector_count": len(members),
            "data": data,
            "tail_free": tail,
        }
        i += 1 + count
    if i != SCENARIO_RANGE[1] - 64:  # 마지막 시나리오가 영역을 넘어서 끝난다(정상)
        pass
    return out


def combat_directory(sectors: list[dict]) -> dict[tuple, dict]:
    out = {}
    for i in range(*COMBAT_RANGE):
        sec = sectors[i]
        data = sec["data"]
        out[key_of(sec)] = {
            "index": i,
            "sector_count": 1,
            "data": data,
            "tail_free": len(data) - len(data.rstrip(b"\x00")),
        }
    return out


def load() -> tuple[dict, dict]:
    sectors = common.read_sectors(common.disk_path("scenario"))
    return scenario_directory(sectors), combat_directory(sectors)


if __name__ == "__main__":
    scn, cbt = load()
    print(f"시나리오 {len(scn)}건 · 전투 {len(cbt)}건")
    tot = sum(v["sector_count"] for v in scn.values())
    print(
        f"  시나리오가 쓰는 섹터 {tot} · 꼬리 빈칸 합 {sum(v['tail_free'] for v in scn.values()):,}B"
    )
    print(f"  전투 꼬리 빈칸 합 {sum(v['tail_free'] for v in cbt.values()):,}B")
