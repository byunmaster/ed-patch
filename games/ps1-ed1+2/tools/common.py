"""공용: 경로, 섹터 상수, 추출/EDC 헬퍼. 모든 도구가 여기서 가져다 쓴다."""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # games/ps1-ed1+2
ORIG_DIR = os.path.join(ROOT, "..", "..", "originals", "ps1-ed1+2")  # 원본 이미지 (gitignore)
WORK_DIR = os.path.join(ROOT, "work")  # 테스트/패치 빌드 (gitignore)
OUT_DIR = os.path.join(ROOT, "out")  # 분석 산출물 (gitignore)

ORIG_BIN = os.path.join(ORIG_DIR, "Legend of Heroes I & II, The - Eiyuu Densetsu (Japan).bin")
ORIG_CUE = os.path.join(ORIG_DIR, "Legend of Heroes I & II, The - Eiyuu Densetsu (Japan).cue")

SECTOR = 2352  # raw MODE2/2352
USER_OFF = 24  # sync(12)+header(4)+subheader(8) → Mode2 Form1 유저 데이터
USER_SIZE = 2048

# ED1SCN1.BIN (iso_files.txt) — 자주 쓰는 대상
ED1SCN1_LBA, ED1SCN1_SIZE = 1183, 206260
ED1SCN1_RAM_BASE = 0x8016A000  # 오버레이 로드 주소 (no$psx로 검증)


def extract(lba, size, path=ORIG_BIN):
    """ISO 파일의 유저 데이터(2048/섹터)를 이어붙여 추출."""
    out = bytearray()
    with open(path, "rb") as f:
        for i in range((size + USER_SIZE - 1) // USER_SIZE):
            f.seek((lba + i) * SECTOR + USER_OFF)
            out += f.read(USER_SIZE)
    return bytes(out[:size])


# ── MIPS 절대주소 참조 스캐너 (lui+addiu/ori/lw 쌍) ──────────────────────────
# lui rt,hi 뒤 6워드 내에 rt를 rs로 쓰는 load/addiu가 오면 hi<<16 + lo로 주소 조립.
# addiu(0x09)·lw(0x23)는 lo 부호확장, ori(0x0D)는 안 함.
MIPS_LUI, MIPS_ADDIU, MIPS_ORI, MIPS_LW = 0x0F, 0x09, 0x0D, 0x23


MIPS_MEM_LOADS = frozenset((0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26))  # lb/lh/lwl/lw/lbu/lhu/lwr


def iter_lui_pairs(data, load_ops):
    """lui + (load_ops 중 하나) 쌍을 (imm_off, lui_off, op, addr)로 순회.

    메모리 로드가 레지스터를 덮어쓰면(예: `lw t0,..(t0)` 뒤 `addiu x,t0,imm`) 그
    레지스터의 lui 상위값이 무효가 되므로 페어링에서 제외 — 스테일 레지스터가
    우연한 텍스트 주소를 만들어 잘못 패치되는 것을 막는다. R-type 산술
    (`addu at,at,idx` 인덱싱)은 상위값을 보존하므로 무효화하지 않는다(점프 테이블 패턴).
    jal은 $ra만 덮으므로 베이스 레지스터에 무해."""
    words = [int.from_bytes(data[i : i + 4], "little") for i in range(0, len(data) - 3, 4)]
    recent_lui = {}
    for idx, w in enumerate(words):
        op = w >> 26
        if op == MIPS_LUI:
            recent_lui[(w >> 16) & 0x1F] = (idx, w & 0xFFFF)
            continue
        if op in load_ops:
            rs = (w >> 21) & 0x1F
            if rs in recent_lui:
                lui_idx, hi = recent_lui[rs]
                if idx - lui_idx <= 6:
                    lo = w & 0xFFFF
                    addr = (hi << 16) + (lo - 0x10000 if lo >= 0x8000 and op != MIPS_ORI else lo)
                    yield idx * 4, lui_idx * 4, op, addr
        if op in MIPS_MEM_LOADS:  # rt를 메모리값으로 재정의 → 상위값 소실
            recent_lui.pop((w >> 16) & 0x1F, None)


def edc_compute(data):
    """Mode2 Form1 EDC (subheader+data = 섹터 16~2071 대상, 2072에 LE 저장)."""
    edc = 0
    for b in data:
        edc ^= b
        for _ in range(8):
            edc = (edc >> 1) ^ (0xD8018001 if edc & 1 else 0)
    return edc


# ── Mode2 Form1 ECC (P/Q Reed-Solomon 패리티) ────────────────────────────────
# EDC만 고치고 ECC를 두면 에뮬은 넘어가지만(무시) **실기 CD 컨트롤러는 하드웨어 정정을
# 수행**해서, 스테일 패리티가 멀쩡한 유저 데이터를 "정정"해 오히려 깨뜨릴 수 있다.
# GF(2^8) 생성다항식 0x11D — ecm/cdrdao 표준 알고리즘.
_ECC_F = bytearray(256)  # i → i*2 (GF)
_ECC_B = bytearray(256)  # (i ^ i*2) → i (역룩업)
for _i in range(256):
    _j = ((_i << 1) ^ (0x11D if _i & 0x80 else 0)) & 0xFF
    _ECC_F[_i] = _j
    _ECC_B[_i ^ _j] = _i


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


def ecc_update(sec):
    """섹터(2352B bytearray)의 P(0x81C~)·Q(0x8C8~) 패리티를 제자리 재계산.

    Mode2는 헤더(12~15)를 0으로 두고 계산한다(ecc 대상 = 12~2075의 2064B)."""
    hdr = bytes(sec[12:16])
    sec[12:16] = b"\x00\x00\x00\x00"
    src = memoryview(sec)[12:]
    _ecc_block(src, 86, 24, 2, 86, sec, 0x81C)  # P
    _ecc_block(src, 52, 43, 86, 88, sec, 0x8C8)  # Q
    sec[12:16] = hdr


def write_user_data(f, lba, data, nsec=None):
    """열린 r+b 파일 핸들의 lba부터 유저 데이터를 기록하고 EDC·ECC 재계산.
    반환: 실제로 바뀐 섹터 수."""
    if nsec is None:
        nsec = (len(data) + USER_SIZE - 1) // USER_SIZE
    changed = 0
    for i in range(nsec):
        chunk = bytes(data[i * USER_SIZE : (i + 1) * USER_SIZE]).ljust(USER_SIZE, b"\x00")
        sec_base = (lba + i) * SECTOR
        f.seek(sec_base)
        sec = bytearray(f.read(SECTOR))
        if sec[USER_OFF : USER_OFF + USER_SIZE] == chunk:
            continue
        assert not (sec[18] & 0x20), f"섹터 {lba + i}는 Form2 — 대상 아님"
        sec[USER_OFF : USER_OFF + USER_SIZE] = chunk
        sec[2072:2076] = edc_compute(bytes(sec[16:2072])).to_bytes(4, "little")
        ecc_update(sec)
        f.seek(sec_base)
        f.write(sec)
        changed += 1
    return changed


def write_cue(cue_path, bin_name):
    with open(cue_path, "w", encoding="ascii") as f:
        f.write(f'FILE "{bin_name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
