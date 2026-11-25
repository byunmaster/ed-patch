#!/usr/bin/env python3
"""씬 컨테이너 조각의 뱅크 수 ≤ 한글판 캐시 상한 안에서 — **원판이 15칸을 요구하는 씬은 3뱅크(12섹터) 이하 조각에만 둔다**(11-22 마스터 「바람의 탑 입장 안 됨 · 바즈눈 검은 화면」).

원판은 보스 그림(rec 274, 3뱅크)을 입구에서 올려 캐시 15칸을 쓰는 씬이 있다(devlog 11-06 「전 씬 캐시 피크」: 120·123·126·130·131·144~154·156·166·168 — 원판 17씬).
한글판은 글리프 뱅크가 칸 14·15 를 써 상한이 14 라, 그 씬이 든 조각이 **4뱅크(13~16섹터)** 면 적재가 조용히 실패한다(씬 열기 탐색 루프가 짝 적재 실패 뒤 멈춤 · 화면은 검은 채 음악만).
이 게이트는 구운 이미지의 컨테이너(참조표·짝 항목의 섹터 수)를 읽어 그 씬이 든 **모든 조각**이 3뱅크 이하인지 본다.

🔴 **장별 한도**(11-23 — 마스터 「1,2,3,4,5,종장 모두 캐시위험이 없도록」 · 관리자 「조각이 닿을 수 있는 모든 장의 묶음 기준」):
  정상 상태 점유 = 상주 6뱅크(그룹 0 = 3 · NPC 그림 캐시 셋) + **그 장의 지역 묶음 A + B** + 씬 컨테이너 조각 ≤ 14.
  묶음은 장마다 다르고(뱅크 0x77 의 표 — 장 1~종장 2·4·3·5·4·4뱅크) 컨테이너 조각은 **지금 장의 참조표**에서만 올라온다(`$6BAE` — `$C1B6`·`$C010` 로 색인.
  4장에서 워프로 가는 론도는 4장 표의 항목이다). 그래서 「장 × 그 장 참조표가 가리키는 조각과 그 짝 고리 전부」의 뱅크 수 ≤ 14 − 6 − 묶음 을 잰다.
  ⚠ 이 식이 서는 조건은 「올라와 있는 컨테이너 = 지금 장의 것」이다 — 원판은 장이 바뀌는 필드행에서 옛 장 컨테이너를 남긴다. `earlyfree` 가 그 길을 막는다.
  15칸 씬 검사는 이 식의 4장 몫(묶음 5 → 조각 3뱅크)과 같은 말이다 — 원판 측정에서 나온 독립 근거라 같이 둔다.
  속은 것(11-23): 「1444 는 이미 3뱅크」 — 참조표가 가리키는 풀 쪽만 3뱅크였고 **짝으로만 올라오는 제자리 쪽**이 14섹터였다(4장 씬 114 검은 화면). 표만 보면 짝이 빠진다.

    python3 games/pce-ed1/tools/check_cache_pieces.py [이미지]    # 구운 이미지 필요(인자 없으면 지금 꼬리표 칸)
"""

import mmap
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import containers

PEAK15 = {120, 123, 126, 130, 131, *range(144, 155), 156, 166, 168}  # 원판 캐시 15칸 요구 씬(11-06 측정)
MAX_BANKS = 3
CACHE_SLOTS = 14  # 16칸 − 글리프 뱅크 둘(슬롯 14·15)
RESIDENT = 6  # 그룹 0(3뱅크) + NPC 그림 캐시 셋 — 어느 장이든 늘 올라와 있다
BUNDLE_REL = 34 + (0x77 - 0x68) * 4  # 장별 지역 묶음 표가 든 뱅크 0x77
BUNDLE_A_SECTORS = 0x5FD  # 장마다 1B(묶음 A 섹터 수) — rec 는 +0x5F1
BUNDLE_B_SECTORS = 0x60F  # 〃 묶음 B — rec 는 +0x603
BUNDLE_BANKS = (2, 4, 3, 5, 4, 4)  # 원판 값 — 표를 엉뚱한 데서 읽으면 한도가 조용히 틀린다(뱅크 0x76 으로 읽어 한 번 속았다)
CHAPTERS = 6


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


def _banks(sectors: int) -> int:
    return -(-sectors // 4)


def bundle_banks(track: bytes) -> list[int]:
    b = track[BUNDLE_REL * common.USER : (BUNDLE_REL + 4) * common.USER]
    return [_banks(b[BUNDLE_A_SECTORS + ch]) + _banks(b[BUNDLE_B_SECTORS + ch]) for ch in range(CHAPTERS)]


def chapter_entries(track: bytes) -> list[list[tuple[int, int]]]:
    """장 → 참조표 항목 (rel, 섹터 수) — 엔진(`$6BAE`)이 읽는 그대로: 장별 시작 주소 표(6) + 3B 항목."""
    base = containers.REF_BANK_REL * common.USER
    starts = [track[base + containers.REF_BASES_OFF + 2 * ch] | track[base + containers.REF_BASES_OFF + 2 * ch + 1] << 8 for ch in range(CHAPTERS)]
    idx = [(a - 0x6000 - containers.REF_TABLE_OFF) // 3 for a in starts] + [containers.REF_ENTRIES]
    ent = []
    for i in range(containers.REF_ENTRIES):
        e = track[base + containers.REF_TABLE_OFF + 3 * i : base + containers.REF_TABLE_OFF + 3 * i + 3]
        ent.append(((e[0] | e[1] << 8) + containers.REC_BASE, e[2]))
    return [ent[idx[ch] : idx[ch + 1]] for ch in range(CHAPTERS)]


def partners(track: bytes, rel: int) -> list[tuple[int, int]]:
    """그 조각의 디렉터리가 가리키는 짝 (rel, 섹터 수) — 씬을 못 찾으면 엔진이 이 조각을 내리고 짝을 올린다(`splitload`)."""
    U = common.USER
    d = track[rel * U : rel * U + 330]
    r = containers.parse_dir(d)
    out = []
    for k, e in enumerate(r[0] if r else ()):
        if e[0] == containers.PARTNER_ID:
            at = k * containers.ENTRY
            out.append(((d[at + 1] | d[at + 2] << 8) + containers.REC_BASE, d[at + 3]))
    return out


def scan_chapters(track: bytes | None = None) -> tuple[list[str], int]:
    """장 × 그 장에서 올라올 수 있는 조각 — 상주 + 묶음 + 조각 ≤ 14 인가. (위반, 잰 조각 수)"""
    track = track if track is not None else built_track(common.BUILD_DIR / common.BUILD_TAG / "ed1.iso")
    bundle = bundle_banks(track)
    if tuple(bundle) != BUNDLE_BANKS:
        return [f"장별 묶음 표가 원판 값 {BUNDLE_BANKS} 이 아니다: {bundle} — 표 자리(rel {BUNDLE_REL})를 다시 확인"], 0
    bad: list[str] = []
    n = 0
    for ch, ents in enumerate(chapter_entries(track)):
        limit = CACHE_SLOTS - RESIDENT - bundle[ch]
        seen: dict[int, int] = {}
        todo = [(rel, ns, f"참조표 지역 {area}") for area, (rel, ns) in enumerate(ents)]
        while todo:
            rel, ns, via = todo.pop()
            if seen.get(rel, -1) >= ns:
                continue
            seen[rel] = ns
            n += 1
            if _banks(ns) > limit:
                bad.append(
                    f"장 {ch + 1}: 조각 rel {rel} = {ns}섹터({_banks(ns)}뱅크, {via}) > {limit}뱅크 — 상주 {RESIDENT} + 묶음 {bundle[ch]} + 조각 {_banks(ns)} > {CACHE_SLOTS}칸"
                )
            todo += [(prel, pn, f"rel {rel} 의 짝") for prel, pn in partners(track, rel)]
    return bad, n


def main() -> int:
    iso = Path(sys.argv[1]) if len(sys.argv) > 1 else common.BUILD_DIR / common.BUILD_TAG / "ed1.iso"
    if not iso.exists():
        print(f"❌ 구운 이미지가 없다 — 빌드 먼저({iso})")
        return 1
    track = built_track(iso)
    bad, n = scan(track)
    print(f"캐시 15칸 씬 조각 뱅크 수 — 씬×조각 {n}개 확인")
    for b in bad:
        print("  ✘", b)
    print("✅ 15칸 씬은 전부 3뱅크 이하 조각" if not bad else f"❌ {len(bad)}건")
    bad2, n2 = scan_chapters(track)
    print(f"장별 캐시 한도(상주 {RESIDENT} + 묶음 + 조각 ≤ {CACHE_SLOTS}) — 장×조각 {n2}개 확인 · 조각 한도 {[CACHE_SLOTS - RESIDENT - b for b in BUNDLE_BANKS]}뱅크")
    for b in bad2:
        print("  ✘", b)
    print("✅ 어느 장에서도 올라올 수 있는 조각이 한도 안" if not bad2 else f"❌ {len(bad2)}건")
    return 1 if bad or bad2 else 0


if __name__ == "__main__":
    sys.exit(main())
