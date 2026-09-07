"""새턴 영웅전설 1&2 — 경로·원본 지문·ISO 읽기의 정본.

⚠ 원본은 읽기 전용이다. 쓰기 계열 헬퍼는 재삽입 설계가 서기 전까지 두지 않는다
(patcher-checklist 2 — 사전조건 없는 쓰기 경로를 미리 만들지 않는다).
"""

import hashlib
import mmap
import os
import sys

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(GAME_DIR))
ORIG_DIR = os.path.join(ROOT, "originals", "jp", "ss-ed1+2")
ORIG_BIN = os.path.join(ORIG_DIR, "The_Legend_of_Heroes_I&II.bin")
ORIG_CUE = os.path.join(ORIG_DIR, "The_Legend_of_Heroes_I&II.cue")

WORK_DIR = os.path.join(GAME_DIR, "work")
OUT_DIR = os.path.join(WORK_DIR, "derived")  # 원본에서 파생 — 빌드가 읽는 입력
REVIEW_DIR = os.path.join(WORK_DIR, "review")  # 검토표·시트 — ⚠ 원문 포함, 커밋 금지

# 테스트 이미지 — ⚠ **꼬리표별로 갈린다**(`shared/build_tag.py`). ps1 과 같은 모양이라야
# 루트에서 산출물을 훑는 쪽이 게임마다 다른 규칙을 안 들고 있어도 된다.
sys.path.insert(0, os.path.join(ROOT, "shared"))
from build_tag import build_tag

BUILD_TAG = build_tag()
BUILD_DIR = os.path.join(WORK_DIR, "build", BUILD_TAG)

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


def dst_files(dst=None, mm=None):
    """**쓰기 대상**의 `{경로: (LBA, 크기)}` — 빌드 이미지가 정본이고, 없으면 원본 것.

    🔴 **원본으로 읽고 빌드로 쓴다.** 「원본이 어땠는가」는 원본에서 묻지만(비멱등 방지),
       **쓰는 자리**는 빌드 이미지가 정한다. `relocate_files` 가 파일을 뒤로 밀면 둘의
       LBA 가 갈리고, 원본 LBA 로 빌드에 쓰면 **엉뚱한 섹터를 밟는다** — 실측 2026-08-31
       에 `patch_scn` 이 이걸로 터졌다(`ED1SCN03 이주 0x77BC: 되읽기가 다르다`).
       크기도 같다 — `expand_files` 가 꼬리를 늘리면 빌드 쪽이 크다.
    ⚠ 그래서 **재배치 대상이 아닌 파일도 여기로 묻는다.** 「지금은 안 옮기니까 괜찮다」는
      다음에 옮길 때 조용히 틀리는 자리가 된다.
    """
    dst = dst or os.path.join(BUILD_DIR, os.path.basename(ORIG_BIN))
    if os.path.exists(dst):
        f2, mm2 = open_image(dst)
        try:
            return {p: (lba, size) for p, lba, size in iso_files(mm2)}
        finally:
            mm2.close()
            f2.close()
    close = mm is None
    if close:
        f, mm = open_image()
    try:
        return {p: (lba, size) for p, lba, size in iso_files(mm)}
    finally:
        if close:
            mm.close()
            f.close()


# ── MODE1/2352 쓰기 (2026-08-21) ──────────────────────────────────────────────
# ⚠ **PS1 것을 그대로 못 쓴다.** 저 쪽은 MODE2 Form1 이고 여기는 **MODE1** 이라 두 군데가
# 다르다: EDC 범위(여기는 섹터 **0~2063**, 저기는 16~2071)와 **ECC 계산 시 헤더 처리**
# (MODE2 는 헤더 12~15 를 0 으로 두고 계산, MODE1 은 **그대로** 둔다).
# P/Q 패리티 자리(0x81C·0x8C8)와 GF 다항식(0x11D)은 같다.
#
# 🔴 **EDC 만 고치고 ECC 를 두면 안 된다.** 에뮬은 무시하지만 실기 CD 컨트롤러는 하드웨어
# 정정을 수행해서, 낡은 패리티가 멀쩡한 유저 데이터를 「정정」해 오히려 깨뜨린다.
#
# 구현이 맞는지는 `selftest_ecc()` 가 본다 — **손 안 댄 원본 섹터를 다시 계산해** 원본
# 바이트와 맞댄다. 틀린 EDC/ECC 는 화면에 안 보이고 실기에서만 터지므로 이 자기검증이 없으면
# 「빌드는 되는데 실기에서만 깨지는」 부류가 된다.

_ECC_F = bytearray(256)  # i → i*2 (GF(2^8), 0x11D)
_ECC_B = bytearray(256)  # (i ^ i*2) → i
for _i in range(256):
    _j = ((_i << 1) ^ (0x11D if _i & 0x80 else 0)) & 0xFF
    _ECC_F[_i] = _j
    _ECC_B[_i ^ _j] = _i


def edc_compute(data):
    """CD-ROM EDC (CRC-32/0xD8018001, LE 저장)."""
    edc = 0
    for b in data:
        edc ^= b
        for _ in range(8):
            edc = (edc >> 1) ^ (0xD8018001 if edc & 1 else 0)
    return edc


def _ecc_block(src, major_count, minor_count, major_mult, minor_inc, dst, dst_off):
    size = major_count * minor_count
    for major in range(major_count):
        idx = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minor_count):
            t = src[idx]
            idx += minor_inc
            if idx >= size:
                idx -= size
            a ^= t
            b ^= t
            a = _ECC_F[a]
        a = _ECC_B[_ECC_F[a] ^ b]
        dst[dst_off + major] = a
        dst[dst_off + major + major_count] = a ^ b


def sector_fix(sec):
    """MODE1 섹터(2352B bytearray)의 EDC·ECC 를 제자리 재계산."""
    assert len(sec) == SECTOR, len(sec)
    assert sec[15] == 0x01, f"MODE1 이 아니다 (mode={sec[15]})"
    sec[2064:2068] = edc_compute(sec[0:2064]).to_bytes(4, "little")
    sec[2068:2076] = b"\x00" * 8  # intermediate
    src = memoryview(sec)[12:]  # ⚠ MODE1 은 헤더를 0 으로 두지 않는다
    _ecc_block(src, 86, 24, 2, 86, sec, 0x81C)  # P
    _ecc_block(src, 52, 43, 86, 88, sec, 0x8C8)  # Q


def selftest_ecc(mm, lbas=(16, 237, 4268, 12287)):
    """손 안 댄 섹터를 재계산해 원본과 맞댄다 — 구현이 맞는지 확인."""
    bad = []
    for lba in lbas:
        mm.seek(lba * SECTOR)
        orig = mm.read(SECTOR)
        sec = bytearray(orig)
        sector_fix(sec)
        if bytes(sec) != orig:
            d = [i for i in range(SECTOR) if sec[i] != orig[i]]
            bad.append((lba, len(d), d[:6]))
    return bad


def write_user_data(f, lba, data, *, label, expect=None):
    """열린 `r+b` 핸들의 `lba` 부터 유저 데이터를 쓰고 EDC·ECC 를 고친다.

    `label` — 무엇을 쓰는지(필수). 사고가 났을 때 **범인을 바로 알려면** 있어야 한다.
    `expect` — 쓰기 **사전 조건**. `bytes` 면 그 범위의 현재 바이트가 정확히 그것이어야 한다.
        ⚠ 이게 없으면 「배치가 밀렸는데 그 자리에 그냥 쓰는」 사고를 못 막는다.

    ⚠ **길이가 섹터 경계를 넘어도 된다** — 걸치는 섹터를 전부 고친다.
    """
    n = len(data)
    if expect is not None:
        cur = bytearray()
        for i in range((n + USER_SIZE - 1) // USER_SIZE + 1):
            f.seek((lba + i) * SECTOR + USER_OFF)
            cur += f.read(USER_SIZE)
        if bytes(cur[:n]) != expect:
            raise AssertionError(f"쓰기 사전조건 불일치 — `{label}` @LBA {lba}")
    first, last = 0, (n - 1) // USER_SIZE
    for i in range(first, last + 1):
        f.seek((lba + i) * SECTOR)
        sec = bytearray(f.read(SECTOR))
        lo = i * USER_SIZE
        chunk = data[lo : lo + USER_SIZE]
        sec[USER_OFF : USER_OFF + len(chunk)] = chunk
        sector_fix(sec)
        f.seek((lba + i) * SECTOR)
        f.write(sec)
    return last - first + 1


def write_at(f, lba, size, offset, data, *, label, expect=None):
    """ISO 파일 안의 `offset` 위치에 `data` 를 덮어쓴다(파일 크기 불변).

    파일이 `lba` 에서 시작해 `size` 바이트일 때, **파일 내부 오프셋**으로 쓴다.
    ⚠ 섹터 경계를 걸치면 앞뒤 유저 데이터를 보존한 채 그 섹터만 고쳐 쓴다.
    """
    assert offset >= 0 and offset + len(data) <= size, f"파일 밖을 쓴다 — `{label}`"
    s_lba = lba + offset // USER_SIZE
    head = offset % USER_SIZE
    nsec = (head + len(data) + USER_SIZE - 1) // USER_SIZE
    buf = bytearray()
    for i in range(nsec):
        f.seek((s_lba + i) * SECTOR + USER_OFF)
        buf += f.read(USER_SIZE)
    if expect is not None and bytes(buf[head : head + len(data)]) != expect:
        raise AssertionError(f"쓰기 사전조건 불일치 — `{label}` @0x{offset:X}")
    buf[head : head + len(data)] = data
    return write_user_data(f, s_lba, bytes(buf), label=label)
