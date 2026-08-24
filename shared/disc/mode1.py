"""MODE1/2352 섹터 쓰기 — EDC·ECC 재계산의 정본.

**둘째 소비자가 실재해서 올렸다** — 새턴 ED1+2 와 새턴 ED3 가 같은 MODE1/2352 다.

⚠ **PS1(MODE2 Form1) 것을 그대로 못 쓴다.** 두 군데가 다르다:
  · EDC 범위 — MODE1 은 섹터 **0~2063**, MODE2 Form1 은 16~2071
  · ECC 계산 시 헤더 — MODE1 은 **그대로** 두고, MODE2 는 헤더 12~15 를 0 으로 둔다
P/Q 패리티 자리(0x81C·0x8C8)와 GF 다항식(0x11D)은 같다.

🔴 **EDC 만 고치고 ECC 를 두면 안 된다.** 에뮬레이터는 무시하지만 실기 CD 컨트롤러는
하드웨어 정정을 수행해서, 낡은 패리티가 멀쩡한 유저 데이터를 「정정」해 오히려 깨뜨린다.

구현이 맞는지는 `selftest()` 가 본다 — **손 안 댄 원본 섹터를 다시 계산해** 원본 바이트와
맞댄다. 틀린 EDC/ECC 는 화면에 안 보이고 실기에서만 터지므로 이 자기검증이 없으면
「빌드는 되는데 실기에서만 깨지는」 부류가 된다.
"""

from .iso9660 import SECTOR, USER_SIZE

USER_OFF = 16  # MODE1 유저 데이터 시작 (sync 12 + header 4)

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
    """MODE1 섹터(2352B `bytearray`)의 EDC·ECC 를 제자리 재계산."""
    assert len(sec) == SECTOR, len(sec)
    assert sec[15] == 0x01, f"MODE1 이 아니다 (mode={sec[15]})"
    sec[2064:2068] = edc_compute(sec[0:2064]).to_bytes(4, "little")
    sec[2068:2076] = b"\x00" * 8  # intermediate
    src = memoryview(sec)[12:]  # ⚠ MODE1 은 헤더를 0 으로 두지 않는다
    _ecc_block(src, 86, 24, 2, 86, sec, 0x81C)  # P
    _ecc_block(src, 52, 43, 86, 88, sec, 0x8C8)  # Q


def selftest(path_or_mm, lbas=(16, 237, 4268, 12287)):
    """손 안 댄 섹터를 재계산해 원본과 맞댄다 — 어긋난 `[(lba, 다른 바이트 수)]`."""
    if isinstance(path_or_mm, (str, bytes)) or hasattr(path_or_mm, "__fspath__"):
        with open(path_or_mm, "rb") as f:
            return _selftest_reader(f.read, f.seek, lbas)
    mm = path_or_mm
    return _selftest_reader(lambda n: mm.read(n), lambda o: mm.seek(o), lbas)


def _selftest_reader(read, seek, lbas):
    bad = []
    for lba in lbas:
        seek(lba * SECTOR)
        orig = read(SECTOR)
        if len(orig) < SECTOR or orig[15] != 0x01:
            continue  # MODE1 이 아닌 섹터는 건너뛴다
        sec = bytearray(orig)
        sector_fix(sec)
        if bytes(sec) != orig:
            bad.append((lba, sum(1 for i in range(SECTOR) if sec[i] != orig[i])))
    return bad


def write_user_data(f, lba, data, *, label, expect=None):
    """열린 `r+b` 핸들의 `lba` 부터 유저 데이터를 쓰고 EDC·ECC 를 고친다.

    `label` — 무엇을 쓰는지(필수). 사고가 났을 때 **범인을 바로 알려면** 있어야 한다.
    `expect` — 쓰기 **사전 조건**. `bytes` 면 그 범위의 현재 바이트가 정확히 그것이어야 한다.
        ⚠ 이게 없으면 「배치가 밀렸는데 그 자리에 그냥 쓰는」 사고를 못 막는다
        (`docs/patcher-checklist.md` 2).

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
    last = (n - 1) // USER_SIZE
    for i in range(last + 1):
        f.seek((lba + i) * SECTOR)
        sec = bytearray(f.read(SECTOR))
        chunk = data[i * USER_SIZE : (i + 1) * USER_SIZE]
        sec[USER_OFF : USER_OFF + len(chunk)] = chunk
        sector_fix(sec)
        f.seek((lba + i) * SECTOR)
        f.write(sec)
    return last + 1


def write_at(f, lba, size, offset, data, *, label, expect=None):
    """ISO 파일 안의 `offset` 위치에 `data` 를 덮어쓴다(파일 크기 불변).

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
