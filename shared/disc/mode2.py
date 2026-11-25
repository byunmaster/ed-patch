"""MODE2/2352 **Form1** 섹터 쓰기 — PS1 의 EDC·ECC 재계산과 사전조건·무변경 가드가 걸린 쓰기 통로.

`mode1.py`(새턴)와 짝이다. 둘째 소비자가 실재한다 — ps1-ed1+2 · ps1-ed3 · ps1-ed4 가 같은 규격이고
지금은 각자 `common.py` 에 사본을 갖고 있다(EDC/ECC 사본 둘 이상 = 한쪽만 고쳐지는 자리).

MODE1 과 다른 둘(`mode1.py` 머리말): EDC 범위는 섹터 **16~2071**(저장 2072), ECC 계산 때 **헤더 12~15 를
0 으로** 둔다. P/Q 패리티 자리·GF 다항식은 같아서 `mode1` 의 블록 계산을 그대로 쓴다.

🔴 EDC 만 고치고 ECC 를 두면 안 된다(실기 컨트롤러가 멀쩡한 데이터를 「정정」해 깨뜨린다).
"""

import struct

from .guard import WriteGuard, check_expect
from .iso9660 import MODE2_FORM1_USER_OFF as USER_OFF
from .iso9660 import SECTOR, USER_SIZE
from .mode1 import _ecc_block, edc_compute

__all__ = [
    "SECTOR",
    "USER_OFF",
    "USER_SIZE",
    "WriteGuard",
    "ecc_update",
    "read_user_data",
    "sector_fix",
    "selftest",
    "set_file_size",
    "write_cue",
    "write_user_data",
]


def ecc_update(sec):
    """섹터(2352B bytearray)의 P(0x81C~)·Q(0x8C8~) 패리티를 제자리 재계산 — 헤더는 0 으로 두고 계산한 뒤 복원."""
    hdr = bytes(sec[12:16])
    sec[12:16] = b"\x00\x00\x00\x00"
    src = memoryview(sec)[12:]
    _ecc_block(src, 86, 24, 2, 86, sec, 0x81C)  # P
    _ecc_block(src, 52, 43, 86, 88, sec, 0x8C8)  # Q
    sec[12:16] = hdr


def sector_fix(sec):
    """Form1 섹터의 EDC·ECC 를 제자리 재계산. Form2 는 대상이 아니다(실패)."""
    assert len(sec) == SECTOR, len(sec)
    assert not (sec[18] & 0x20), "Form2 섹터 — 대상 아님"
    sec[2072:2076] = edc_compute(bytes(sec[16:2072])).to_bytes(4, "little")
    ecc_update(sec)


def read_user_data(f, lba, size):
    """열린 핸들의 `lba` 부터 유저 데이터 `size` 바이트(섹터 경계를 이어 붙인다)."""
    out = bytearray()
    for i in range((size + USER_SIZE - 1) // USER_SIZE):
        f.seek((lba + i) * SECTOR + USER_OFF)
        out += f.read(USER_SIZE)
    return bytes(out[:size])


def write_user_data(f, lba, data, nsec=None, *, label, expect=None, guard=None):
    """열린 `r+b` 핸들의 `lba` 부터 유저 데이터를 쓰고 EDC·ECC 를 다시 계산한다. 반환 = **실제로 바뀐 섹터 수**.

    `label` 필수 — 가드에 걸렸을 때 범인을 바로 알려면 있어야 한다.
    `expect` — 사전조건(`guard.check_expect`): bytes 면 현재 바이트가 정확히 그것, int 면 전 범위가 그 값.
    `guard` — `guard.Guard`(무변경 구간). 안 주면 가드 없이 쓴다(체크리스트 2: 통로를 하나로 좁히려면 부르는 쪽이 항상 준다).
    ⚠ 안 바뀐 섹터는 **건드리지 않는다**(바이트 동일 유지 — 결정성).
    """
    if nsec is None:
        nsec = (len(data) + USER_SIZE - 1) // USER_SIZE
    if expect is not None:
        cur = read_user_data(f, lba, nsec * USER_SIZE)
        check_expect(cur, expect, label, f"lba {lba}")
    changed = 0
    for i in range(nsec):
        chunk = bytes(data[i * USER_SIZE : (i + 1) * USER_SIZE]).ljust(USER_SIZE, b"\x00")
        base = (lba + i) * SECTOR
        f.seek(base)
        sec = bytearray(f.read(SECTOR))
        old = bytes(sec[USER_OFF : USER_OFF + USER_SIZE])
        if old == chunk:
            continue
        if guard is not None:
            guard.check((lba + i) * USER_SIZE, old, chunk, label)
        assert not (sec[18] & 0x20), f"섹터 {lba + i}는 Form2 — 대상 아님"
        sec[USER_OFF : USER_OFF + USER_SIZE] = chunk
        sector_fix(sec)
        f.seek(base)
        f.write(sec)
        changed += 1
    return changed


def set_file_size(f, dir_lba, at, new_size, *, label, guard=None):
    """ISO 디렉터리 레코드(`dir_lba` 섹터의 `at` 오프셋)의 파일 크기(LE·BE 둘 다)를 고친다. 섹터 수가 안 바뀔 때만 쓴다."""
    sec = bytearray(read_user_data(f, dir_lba, USER_SIZE))
    if sec[at] < 34:
        raise ValueError(f"{label}: 디렉터리 레코드가 아니다 (@{at})")
    sec[at + 10 : at + 14] = struct.pack("<I", new_size)
    sec[at + 14 : at + 18] = struct.pack(">I", new_size)
    return write_user_data(f, dir_lba, bytes(sec), label=label, guard=guard)


def selftest(path, lbas):
    """손 안 댄 Form1 섹터를 재계산해 원본과 맞댄다 — 어긋난 `[(lba, 다른 바이트 수)]`. 원본 파일이 있을 때만."""
    bad = []
    with open(path, "rb") as f:
        for lba in lbas:
            f.seek(lba * SECTOR)
            orig = f.read(SECTOR)
            if len(orig) < SECTOR or orig[15] != 0x02 or orig[18] & 0x20:
                continue
            sec = bytearray(orig)
            sector_fix(sec)
            if bytes(sec) != orig:
                bad.append((lba, sum(1 for i in range(SECTOR) if sec[i] != orig[i])))
    return bad


def write_cue(cue_path, bin_name):
    with open(cue_path, "w", encoding="ascii") as f:
        f.write(f'FILE "{bin_name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
