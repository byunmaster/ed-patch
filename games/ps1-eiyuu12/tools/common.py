"""공용: 경로, 섹터 상수, 추출/EDC 헬퍼. 모든 도구가 여기서 가져다 쓴다."""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # games/ps1-eiyuu12
ORIG_DIR = os.path.join(ROOT, "..", "..", "originals", "ps1-eiyuu12")  # 원본 이미지 (gitignore)
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


def edc_compute(data):
    """Mode2 Form1 EDC (subheader+data = 섹터 16~2071 대상, 2072에 LE 저장)."""
    edc = 0
    for b in data:
        edc ^= b
        for _ in range(8):
            edc = (edc >> 1) ^ (0xD8018001 if edc & 1 else 0)
    return edc


def write_user_data(f, lba, data, nsec=None):
    """열린 r+b 파일 핸들의 lba부터 유저 데이터를 기록하고 EDC 재계산.
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
        f.seek(sec_base)
        f.write(sec)
        changed += 1
    return changed


def write_cue(cue_path, bin_name):
    with open(cue_path, "w", encoding="ascii") as f:
        f.write(f'FILE "{bin_name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
