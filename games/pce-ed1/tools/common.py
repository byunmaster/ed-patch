"""pce-ed1 공용 — 원본 지문 · 데이터 트랙 섹터 모델 · 경로 상수.

⚠ **읽기 전용이다.** 쓰기 헬퍼는 재삽입 설계가 서기 전까지 두지 않는다
(`docs/patcher-checklist.md` 2 — 쓰기 사전조건이 없는 쓰기 경로를 만들지 않는다).

🔴 **좌표는 「데이터 트랙 상대 섹터(rel)」다.** 이 디스크는 ISO9660 이 아니고(`CD001` 없음)
게임이 **트랙 2 시작을 0 으로 세는 섹터 번호**로 직접 읽는다(IPL 의 load record 가 그 좌표다).
파일 오프셋도 절대 LBA 도 아니다 — `rel` 이 안 붙은 섹터 상수는 못 믿는다.
    file_sector = T2_SECTOR + rel        (2352B raw 섹터, 유저 데이터는 +16 부터 2048B)
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from build_tag import build_tag

GAME = "pce-ed1"
ROOT = Path(__file__).resolve().parents[3]
GAME_DIR = ROOT / "games" / GAME
ORIG_DIR = ROOT / "originals" / "jp" / GAME

WORK = GAME_DIR / "work"
OUT_DIR = WORK / "derived"
REVIEW_DIR = WORK / "review"
BUILD_TAG = build_tag()
BUILD_DIR = WORK / "build"
DIST_DIR = WORK / "dist"
# 에뮬 실행용 cue 사본 자리 — 원본 cue 가 ISO 파일명을 대문자로 적어 리눅스에서 못 찾는다.
# `DRAGON_...ISO` 는 원본의 **하드링크**라 여기에 쓰면 원본이 망가진다. 읽기만 한다.
EMU_DIR = WORK / "emu"

# redump 덤프(.cue + .iso, 2352B raw). 같은 폴더의 .ccd/.img/.sub 세트는 같은 디스크의 중복
# 덤프라 도구가 안 읽는다(originals/README.md 규약상 정리 대상).
ORIG_ISO = ORIG_DIR / "Dragon_Slayer_-_Eiyuu_Densetsu_(NTSC-J)_[HCD1020].iso"
ORIG_CUE = ORIG_DIR / "Dragon_Slayer_-_Eiyuu_Densetsu_(NTSC-J)_[HCD1020].cue"
ORIG_SHA1 = {
    ORIG_ISO.name: "8a7ee4ca1b05410490c86c749b7fd80672ee1e6f",
    ORIG_CUE.name: "fdf5c303452e53b6af15a1eaf8af91606e7fe76d",
}
ORIG_ISO_SIZE = 658_369_488  # = 279,919 섹터 × 2352

RAW = 2352
USER = 2048
USER_OFF = 16  # sync 12 + header 4 (MODE1)

# 트랙 배치(cue 기준, 파일 섹터). 트랙 1 은 오디오(0~3364), 트랙 2 가 데이터, 3~21 CD-DA,
# 트랙 22 가 데이터 — 트랙 2 머리 1,733 섹터의 **복제**다(1,730/1,733 동일. 부팅 보호용 관행).
T2_SECTOR = 3365  # 00:44:65
T2_LEN = 10072  # 트랙 3(02:59:12) 직전까지 — 유저 데이터 20.6MB
T22_SECTOR = 278186  # 61:49:11
T22_LEN = 1733

# IPL 블록은 rel 1 에 있다(rel 0 은 저작권 문구). 시그니처 오프셋 0x20.
IPL_REL = 1
IPL_SIG = b"PC Engine CD-ROM SYSTEM"


def sha1_of(path: Path, bufsize: int = 1 << 20) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while chunk := f.read(bufsize):
            h.update(chunk)
    return h.hexdigest()


def verify_originals() -> None:
    """지문이 어긋나면 그 자리에서 죽는다 — 패치된 사본을 원본으로 오해하지 않기 위해."""
    for p in (ORIG_ISO, ORIG_CUE):
        if not p.exists():
            raise SystemExit(f"원본 없음: {p}")
        got = sha1_of(p)
        if got != ORIG_SHA1[p.name]:
            raise SystemExit(f"지문 불일치: {p.name}\n  기대 {ORIG_SHA1[p.name]}\n  실제 {got}")


_iso_cache: bytes | None = None


def iso_bytes() -> bytes:
    """원본 이미지 전체(628MB)를 메모리에 한 번만 올린다."""
    global _iso_cache
    if _iso_cache is None:
        _iso_cache = ORIG_ISO.read_bytes()
    return _iso_cache


def user_sector(rel: int) -> bytes:
    """데이터 트랙 상대 섹터 rel 의 유저 데이터 2048B."""
    off = (T2_SECTOR + rel) * RAW + USER_OFF
    return iso_bytes()[off : off + USER]


def track_data(rel_start: int = 0, count: int | None = None) -> bytes:
    """rel_start 부터 count 섹터의 유저 데이터를 이어 붙인다(기본: 트랙 2 전부)."""
    if count is None:
        count = T2_LEN - rel_start
    return b"".join(user_sector(rel_start + i) for i in range(count))


def ipl() -> dict:
    u = user_sector(IPL_REL)
    assert u[0x20 : 0x20 + len(IPL_SIG)] == IPL_SIG, "IPL 시그니처가 rel 1 에 없다"
    return {
        "load_rel": int.from_bytes(u[0:3], "big"),  # 게임 좌표(rel) — 실측 2 = HuC6280 코드
        "load_sectors": u[3],
        "load_addr": int.from_bytes(u[4:6], "little"),
        "exec_addr": int.from_bytes(u[6:8], "little"),
        "mpr2_6": list(u[8:13]),
        "mode": u[13],
        "title": u[0x6A:0x80].split(b"\0")[0].decode("ascii", "replace"),
    }


if __name__ == "__main__":
    verify_originals()
    print(f"원본 OK: {ORIG_ISO.name}  ({ORIG_ISO.stat().st_size:,}B)")
    info = ipl()
    print(
        f"IPL rel {IPL_REL}: load rel {info['load_rel']} ×{info['load_sectors']} → "
        f"${info['load_addr']:04X} exec ${info['exec_addr']:04X} "
        f"mpr {info['mpr2_6']} mode {info['mode']:#04x}  「{info['title']}」"
    )
    # 트랙 22 = 트랙 2 머리의 복제 — 규격이 바뀌면 여기서 운다
    head = track_data(0, T22_LEN)
    dup = iso_bytes()[T22_SECTOR * RAW : (T22_SECTOR + T22_LEN) * RAW]
    same = sum(
        1
        for i in range(T22_LEN)
        if dup[i * RAW + USER_OFF : i * RAW + USER_OFF + USER] == head[i * USER : (i + 1) * USER]
    )
    print(f"트랙 22 = 트랙 2 머리 복제: {same}/{T22_LEN} 섹터 동일")
    assert same >= 1700
