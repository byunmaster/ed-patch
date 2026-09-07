"""pc98-ed1 공용 — 원본 지문 · d88 섹터 모델 · 경로 상수.

⚠ **읽기 전용이다.** 쓰기 헬퍼는 재삽입 설계가 서기 전까지 두지 않는다
(`docs/patcher-checklist.md` 2 — 쓰기 사전조건이 없는 쓰기 경로를 만들지 않는다).

🔴 **좌표는 「논리 순서」다.** 이 디스크는 섹터가 **3:1 인터리브로 물리 배치**돼 있어
(R = 20 23 26 21 24 27 22 25) d88 트랙표 순서 ≠ 게임이 읽는 순서다. 게임은 CHR 로
주소를 매기므로 우리도 **(C,H,R) 정렬**을 정본으로 삼는다. 물리 순서가 필요하면
`read_sectors(logical=False)`.
"""

import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from build_tag import build_tag

GAME = "pc98-ed1"
ROOT = Path(__file__).resolve().parents[3]
GAME_DIR = ROOT / "games" / GAME
ORIG_DIR = ROOT / "originals" / "jp" / GAME

WORK = GAME_DIR / "work"
OUT_DIR = WORK / "derived"
REVIEW_DIR = WORK / "review"
BUILD_TAG = build_tag()
BUILD_DIR = WORK / "build"
DIST_DIR = WORK / "dist"

# 원본 세 장 — sha1 은 **.d88 파일 자체**의 것이다(논리 이미지 지문은 FLAT_SHA1).
# ⚠ 시나리오 디스크는 세이브가 실려 쓰기가 일어나는 매체다. 영문 패치 레포도 같은 경고를
#   남겼다(docs/prior-art.md) — 소장본에 세이브가 있으면 지문이 갈릴 수 있다.
DISKS = {
    "event": (
        "Dragon_Slayer-Eiyuu_Densetsu_Event_Disk_JAP.d88",
        "b1428da7b41f8d2da87e8fc0e2d30fec84c0933e",
    ),
    "program": (
        "Dragon_Slayer-Eiyuu_Densetsu_Program_Disk_JAP.d88",
        "9f310412e8c2f31d59b119b1084a2a83e799461b",
    ),
    "scenario": (
        "Dragon_Slayer-Eiyuu_Densetsu_Scenario_Disk_JAP.d88",
        "02f78e7274f5f706a9c2fd7601d0adc0e57c0041",
    ),
}

# **논리 순서**(C,H,R 정렬) 평면 이미지의 지문 — 리더가 바뀌면 여기가 먼저 운다.
FLAT_SHA1 = {
    "event": "9f465988afdbfa784d76fb499d9a1f1140dc239a",
    "program": "be7f502b8072ca1e6201498b6a7e8a8a6eae22ef",
    "scenario": "7247ac7b1442acc813c7c2528af8023cccb2f3d7",
}

# 2HD 1232KB — 77실린더 × 2면 × 8섹터 × 1024B.
CYLINDERS = 77
HEADS = 2
SECTORS_PER_TRACK = 8
SECTOR_SIZE = 1024
SECTOR_COUNT = CYLINDERS * HEADS * SECTORS_PER_TRACK  # 1232
FLAT_SIZE = SECTOR_COUNT * SECTOR_SIZE  # 1,261,568

# 🔴 **섹터 ID 는 디스크마다 다르다** — 1 부터도 아니고 셋이 서로 다른 대역을 쓴다.
#    event 0x30~0x37 · program 0x10~0x17 · scenario 0x20~0x27, 그리고 **부트 섹터만 R=0x01**.
#    로더가 이걸로 「지금 꽂힌 게 어느 장인가」를 가리는 것으로 보인다(가설).
#    ⇒ **고정 base 상수를 두지 않는다.** 트랙 안에서 R 을 정렬해 그 순위를 논리 번호로 쓴다.
#    ⚠ 다시 쓰는 날에도 **섹터 ID 를 보존**해야 한다 — 정규화하면 디스크가 안 읽힐 수 있다.
SECTOR_ID_BASE = {"event": 0x30, "program": 0x10, "scenario": 0x20}


def disk_path(key: str) -> Path:
    return ORIG_DIR / DISKS[key][0]


def read_sectors(path: Path, logical: bool = True) -> list[dict]:
    """d88 → 섹터 목록. 각 항목 `{c,h,r,index,file_off,data}`.

    `logical=True` 면 (C,H,R) 로 정렬한다 — **게임이 읽는 순서**다.
    `False` 면 d88 트랙표에 적힌 **물리 순서**(인터리브된 그대로)를 준다.
    """
    raw = path.read_bytes()
    out = []
    for track_no, track_off in enumerate(struct.unpack_from("<164I", raw, 0x20)):
        if track_off == 0 or track_off >= len(raw):
            continue
        p = track_off
        n_sectors = struct.unpack_from("<H", raw, p + 4)[0]
        track = []
        for _ in range(n_sectors):
            if p + 16 > len(raw):
                break
            c, h, r = raw[p], raw[p + 1], raw[p + 2]
            data_len = struct.unpack_from("<H", raw, p + 14)[0]
            track.append(
                {
                    "c": c,
                    "h": h,
                    "r": r,
                    "track": track_no,
                    "file_off": p + 16,
                    "data": raw[p + 16 : p + 16 + data_len],
                }
            )
            p += 16 + data_len
        # 논리 번호 = 트랙 번호 × 8 + **그 트랙 안에서 R 을 정렬한 순위**.
        # base 를 상수로 안 두는 이유는 위 SECTOR_ID_BASE 주석에 있다.
        for rank, sec in enumerate(sorted(track, key=lambda s: s["r"])):
            sec["rank"] = rank
            sec["index"] = track_no * SECTORS_PER_TRACK + rank
        out += track
    if logical:
        out.sort(key=lambda s: s["index"])
    return out


def read_flat(path: Path, logical: bool = True) -> bytes:
    return b"".join(s["data"] for s in read_sectors(path, logical=logical))


def check_originals() -> dict[str, bytes]:
    """세 장의 지문을 확인하고 **논리 순서** 평면 이미지를 돌려준다. 틀리면 즉시 죽는다."""
    flats = {}
    for key, (_name, want) in DISKS.items():
        p = disk_path(key)
        if not p.exists():
            raise SystemExit(f"원본 없음: {p}\n  originals/jp/{GAME}/ 를 채우고 다시 돌린다.")
        got = hashlib.sha1(p.read_bytes()).hexdigest()
        if got != want:
            raise SystemExit(f"원본 지문 불일치 {key}\n  want {want}\n  got  {got}")
        secs = read_sectors(p)
        if len(secs) != SECTOR_COUNT:
            raise SystemExit(f"섹터 수 이상 {key}: {len(secs)} != {SECTOR_COUNT}")
        if [s["index"] for s in secs] != list(range(SECTOR_COUNT)):
            raise SystemExit(f"논리 섹터 번호에 구멍/중복 {key} — CHR 규약이 다른 덤프다")
        if any(len(s["data"]) != SECTOR_SIZE for s in secs):
            raise SystemExit(f"섹터 크기 이상 {key}")
        flat = b"".join(s["data"] for s in secs)
        if hashlib.sha1(flat).hexdigest() != FLAT_SHA1[key]:
            raise SystemExit(
                f"논리 이미지 지문 불일치 {key} — 리더가 바뀌었나\n"
                f"  want {FLAT_SHA1[key]}\n  got  {hashlib.sha1(flat).hexdigest()}"
            )
        flats[key] = flat
    return flats


if __name__ == "__main__":
    check_originals()  # ⚠ 먼저 검증한다 — 출력만 하고 통과시키면 게이트가 아니다
    for key in DISKS:
        p = disk_path(key)
        secs = read_sectors(p)
        phys = read_sectors(p, logical=False)
        flat = b"".join(s["data"] for s in secs)
        same = [s["index"] for s in phys] == list(range(SECTOR_COUNT))
        print(
            f"{key:9s} 섹터 {len(secs)}  {len(flat):>9,}B  sha1 {hashlib.sha1(flat).hexdigest()}"
            f"  (물리=논리? {'예' if same else '아니오 — 인터리브'})"
        )
    print("원본 셋 지문 확인.")
