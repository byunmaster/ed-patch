"""QA 빌드 전용 — ED3.EXE 를 이미지 끝으로 옮기고 적재 크기를 늘려 **EXE 뒤에 코드를 붙인다**(11-18, `ED_QA_WARP=1`).

왜: 원판 EXE(LBA 23~372) 바로 뒤가 M01.DAT(373)라 제자리에서 늘릴 수 없고, 「죽은 SDK 함수」 자리는 부팅 때 데이터로 읽혀 못 쓴다(status.md 11-18 2차).
무엇: ① 완성된 이미지의 ED3.EXE 를 읽는다 ② 헤더 t_size 를 `EXTRA` 만큼 늘리고 뒤에 코드+0 을 붙인다 ③ 이미지 끝에 새 섹터로 쓴다(EDC·ECC 포함)
④ ISO 디렉터리 레코드의 LBA·크기와 PVD 볼륨 크기를 고친다. 옛 섹터(23~372)는 그대로 남는다(낡은 사본 — 아무도 안 읽는다).
🔴 제품 빌드·시험 빌드는 이 파일을 안 부른다. 제품 롬 바이트 불변.
"""

import struct

import common

SECTOR, USER_OFF, USER_SIZE = common.SECTOR, common.USER_OFF, common.USER_SIZE
SYNC = bytes([0]) + bytes([0xFF]) * 10 + bytes([0])


def _bcd(v):
    return ((v // 10) << 4) | (v % 10)


def _new_sector(lba, template, data):
    """template = 같은 파일의 기존 섹터(서브헤더 복사). data = 2048B."""
    sec = bytearray(SECTOR)
    sec[0:12] = SYNC
    f = lba + 150
    sec[12:16] = bytes([_bcd(f // 4500), _bcd(f // 75 % 60), _bcd(f % 75), 2])
    sec[16:24] = template[16:24]
    sec[USER_OFF : USER_OFF + USER_SIZE] = data
    sec[2072:2076] = common.edc_compute(bytes(sec[16:2072])).to_bytes(4, "little")
    common.ecc_update(sec)
    return bytes(sec)


def relocate(img, disc, code, extra):
    tree, pos = common.iso_tree(img)
    old_lba, old_size = tree["/ED3.EXE"]
    dir_lba, at = pos["/ED3.EXE"]
    with open(img, "r+b") as f:
        f.seek(0, 2)
        total = f.tell() // SECTOR
        exe = bytearray()
        for i in range((old_size + USER_SIZE - 1) // USER_SIZE):
            f.seek((old_lba + i) * SECTOR + USER_OFF)
            exe += f.read(USER_SIZE)
        exe = exe[:old_size]
        assert exe[:8] == b"PS-X EXE" and old_size % USER_SIZE == 0
        assert len(code) <= extra and extra % USER_SIZE == 0
        t_size = struct.unpack_from("<I", exe, 0x1C)[0]
        assert t_size + 0x800 == old_size, "적재 크기와 파일 크기가 안 맞는다 — 가정이 깨졌다"
        struct.pack_into("<I", exe, 0x1C, t_size + extra)
        new = bytes(exe) + code.ljust(extra, b"\x00")
        f.seek(old_lba * SECTOR)
        template = f.read(SECTOR)
        new_lba = total
        f.seek(0, 2)
        for i in range(len(new) // USER_SIZE):
            f.write(_new_sector(new_lba + i, template, new[i * USER_SIZE : (i + 1) * USER_SIZE]))
        new_total = new_lba + len(new) // USER_SIZE
        # 디렉터리 레코드 — LBA(LE@2·BE@6) · 크기(LE@10·BE@14)
        f.seek(dir_lba * SECTOR + USER_OFF)
        sec = bytearray(f.read(USER_SIZE))
        assert sec[at + 2 : at + 6] == struct.pack("<I", old_lba)
        sec[at + 2 : at + 6] = struct.pack("<I", new_lba)
        sec[at + 6 : at + 10] = struct.pack(">I", new_lba)
        sec[at + 10 : at + 14] = struct.pack("<I", len(new))
        sec[at + 14 : at + 18] = struct.pack(">I", len(new))
        common.write_user_data(f, disc, dir_lba, bytes(sec), label="QA 재배치 — ED3.EXE 디렉터리 레코드")
        # PVD 볼륨 크기(80 LE · 84 BE)
        f.seek(16 * SECTOR + USER_OFF)
        pvd = bytearray(f.read(USER_SIZE))
        pvd[80:84] = struct.pack("<I", new_total)
        pvd[84:88] = struct.pack(">I", new_total)
        common.write_user_data(f, disc, 16, bytes(pvd), label="QA 재배치 — PVD 볼륨 크기")
    return new_lba, len(new), new_total
