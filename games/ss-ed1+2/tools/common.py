"""새턴 영웅전설 1&2 — 경로·원본 지문·ISO 읽기의 정본.

⚠ 원본은 읽기 전용이다. 쓰기 계열 헬퍼는 재삽입 설계가 서기 전까지 두지 않는다
(patcher-checklist 2 — 사전조건 없는 쓰기 경로를 미리 만들지 않는다).
"""

import hashlib
import mmap
import os

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(GAME_DIR))
ORIG_DIR = os.path.join(ROOT, "originals", "jp", "ss-ed1+2")
ORIG_BIN = os.path.join(ORIG_DIR, "The_Legend_of_Heroes_I&II.bin")
ORIG_CUE = os.path.join(ORIG_DIR, "The_Legend_of_Heroes_I&II.cue")

WORK_DIR = os.path.join(GAME_DIR, "work")
OUT_DIR = os.path.join(WORK_DIR, "derived")  # 원본에서 파생 — 빌드가 읽는 입력

# 트랙1 = MODE1/2352 (PS1 합본은 MODE2/2352 · USER_OFF 24 — 여기와 다르다)
SECTOR = 2352
USER_OFF = 16  # sync(12)+header(4) → Mode1 유저 데이터
USER_SIZE = 2048

# 입력 지문 — 2026-08-18 실측 (patcher-checklist 1)
SRC_SIZE = 484_403_808
SRC_SHA1 = "ad6daf4a03fd5a6b054faea80202d67b7555bcab"


def digests(path):
    """{size, sha1} — 배포 표기·원본 확인에 같이 쓴다."""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 22):
            h.update(chunk)
    return {"size": os.path.getsize(path), "sha1": h.hexdigest()}


def verify_source(path=ORIG_BIN, strict=None):
    """원본이 그 덤프인지 확인. 크기가 다르면 즉시, 같으면 sha1 로 확정한다.

    strict=False 로 명시하면 경고만 한다(다른 덤프로 조사할 때의 명시적 탈출구).
    """
    size = os.path.getsize(path)
    if size != SRC_SIZE:
        bad = f"크기 {size:,} (기대 {SRC_SIZE:,})"
    else:
        got = digests(path)["sha1"]
        bad = None if got == SRC_SHA1 else f"sha1 {got} (기대 {SRC_SHA1})"
    if bad:
        msg = f"⚠ 원본 불일치: {path}\n  {bad}"
        if strict is False:
            print(msg + "\n  (strict=False — 계속한다)")
        else:
            raise SystemExit(msg)


def open_image(path=ORIG_BIN):
    f = open(path, "rb")
    return f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)


def sector_user(mm, lba):
    off = lba * SECTOR + USER_OFF
    return mm[off : off + USER_SIZE]


def read_extent(mm, lba, size):
    out = bytearray()
    for i in range((size + USER_SIZE - 1) // USER_SIZE):
        out += sector_user(mm, lba + i)
    return bytes(out[:size])


def iso_files(mm):
    """ISO9660 전체 파일 목록 [(경로, LBA, 크기)] — LBA 순."""
    pvd = sector_user(mm, 16)
    assert pvd[0] == 1 and pvd[1:6] == b"CD001", "PVD 시그니처 불일치"
    root = pvd[156 : 156 + 34]
    files = []
    _walk(
        mm, int.from_bytes(root[2:6], "little"), int.from_bytes(root[10:14], "little"), "", files, 0
    )
    files.sort(key=lambda x: x[1])
    return files


def _walk(mm, lba, size, path, files, depth):
    if depth > 8:
        return
    data = read_extent(mm, lba, size)
    pos = 0
    while pos < len(data):
        rec_len = data[pos]
        if rec_len == 0:  # 레코드는 섹터 경계를 넘지 않는다 → 다음 섹터로
            pos = (pos // USER_SIZE + 1) * USER_SIZE
            continue
        rec = data[pos : pos + rec_len]
        ext_lba = int.from_bytes(rec[2:6], "little")
        ext_size = int.from_bytes(rec[10:14], "little")
        flags = rec[25]
        name = rec[33 : 33 + rec[32]]
        pos += rec_len
        if name in (b"\x00", b"\x01"):
            continue
        full = f"{path}/{name.decode('ascii', 'replace').split(';')[0]}"
        if flags & 0x02:
            _walk(mm, ext_lba, ext_size, full, files, depth + 1)
        else:
            files.append((full, ext_lba, ext_size))


def extract(path_in_iso, mm=None):
    """ISO 안 경로 하나를 bytes 로. 분석용 — 대량이면 iso_files 로 직접 돈다."""
    close = mm is None
    if close:
        f, mm = open_image()
    try:
        for name, lba, size in iso_files(mm):
            if name == path_in_iso:
                return read_extent(mm, lba, size)
        raise KeyError(path_in_iso)
    finally:
        if close:
            mm.close()
            f.close()
