#!/usr/bin/env python3
"""씬 컨테이너 조각의 뱅크 수 ≤ 한글판 캐시 상한 안에서 — **원판이 15칸을 요구하는 씬은 3뱅크(12섹터) 이하 조각에만 둔다**(11-22 마스터 「바람의 탑 입장 안 됨 · 바즈눈 검은 화면」).

원판은 보스 그림(rec 274, 3뱅크)을 입구에서 올려 캐시 15칸을 쓰는 씬이 있다(devlog 11-06 「전 씬 캐시 피크」: 120·123·126·130·131·144~154·156·166·168 — 원판 17씬).
한글판은 글리프 뱅크가 칸 14·15 를 써 상한이 14 라, 그 씬이 든 조각이 **4뱅크(13~16섹터)** 면 적재가 조용히 실패한다(씬 열기 탐색 루프가 짝 적재 실패 뒤 멈춤 · 화면은 검은 채 음악만).
이 게이트는 구운 이미지의 컨테이너(참조표·짝 항목의 섹터 수)를 읽어 그 씬이 든 **모든 조각**이 3뱅크 이하인지 본다.

    python3 games/pce-ed1/tools/check_cache_pieces.py     # 구운 이미지 필요
"""

import mmap
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import containers

PEAK15 = {120, 123, 126, 130, 131, *range(144, 155), 156, 166, 168}  # 원판 캐시 15칸 요구 씬(11-06 측정)
MAX_BANKS = 3


def built_track(iso: Path) -> bytes:
    with open(iso, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        return b"".join(
            mm[(common.T2_SECTOR + r) * common.RAW + common.USER_OFF : (common.T2_SECTOR + r) * common.RAW + common.USER_OFF + common.USER]
            for r in range(common.T2_LEN)
        )


def sectors_of(track: bytes) -> dict[int, int]:
    """rel → 섹터 수 — 참조표(44항목)와 짝 항목(디렉터리 끝 `FE`)이 말하는 값. 같은 rel 이 둘이면 큰 쪽(적재가 말하는 값)."""
    out: dict[int, int] = {}
    base = containers.REF_BANK_REL * common.USER + containers.REF_TABLE_OFF
    for i in range(44):
        b = track[base + 3 * i : base + 3 * i + 3]
        rel, n = (b[0] | b[1] << 8) + containers.REC_BASE, b[2]
        out[rel] = max(out.get(rel, 0), n)
    U = common.USER
    for rel in range(common.T2_LEN):
        d = track[rel * U : rel * U + 330]
        r = containers.parse_dir(d)
        if not r:
            continue
        ents, end = r
        for k, e in enumerate(ents):
            if e[0] == containers.PARTNER_ID:
                at = k * containers.ENTRY
                prel = (d[at + 1] | d[at + 2] << 8) + containers.REC_BASE
                out[prel] = max(out.get(prel, 0), d[at + 3])
    return out


def scan(track: bytes | None = None) -> tuple[list[str], int]:
    track = track if track is not None else built_track(common.BUILD_DIR / common.BUILD_TAG / "ed1.iso")
    sec = sectors_of(track)
    bad: list[str] = []
    n = 0
    for c in containers.scan(track):
        ids = {b["id"] for b in c["blocks"]}
        for sid in sorted(ids & PEAK15):
            n += 1
            ns = sec.get(c["rel"])
            if ns is None:
                bad.append(f"씬 {sid}: 조각 rel {c['rel']} 의 섹터 수를 참조표·짝 항목에서 못 찾는다")
            elif -(-ns // 4) > MAX_BANKS:
                bad.append(f"씬 {sid}: 조각 rel {c['rel']} = {ns}섹터({-(-ns // 4)}뱅크) > {MAX_BANKS}뱅크 — 원판 15칸 씬이 한글판 상한 14칸을 넘어 적재가 실패한다")
    return bad, n


def main() -> int:
    iso = common.BUILD_DIR / common.BUILD_TAG / "ed1.iso"
    if not iso.exists():
        print(f"❌ 구운 이미지가 없다 — 빌드 먼저({iso})")
        return 1
    bad, n = scan()
    print(f"캐시 15칸 씬 조각 뱅크 수 — 씬×조각 {n}개 확인")
    for b in bad:
        print("  ✘", b)
    print("✅ 15칸 씬은 전부 3뱅크 이하 조각" if not bad else f"❌ {len(bad)}건")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
