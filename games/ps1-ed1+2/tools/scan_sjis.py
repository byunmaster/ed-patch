"""
영웅전설 1+2 (PS1) .bin 정적 분석 1차 패스
 1. 파일 크기 / 섹터 구조 확인 (MODE2/2352)
 2. 앞부분 헥스 덤프 + PVD 확인
 3. ISO9660 파일 목록 추출 (LBA, 크기)
 4. 전체 .bin에서 연속 SJIS 일본어 문자열 스캔 → 오프셋 + 소속 파일 매핑
결과: OUT_DIR(work/derived) 에 sjis_strings.txt, iso_files.txt
"""

import mmap
import os
import re
import sys
from bisect import bisect_right

from common import ORIG_BIN as BIN
from common import OUT_DIR, SECTOR, USER_OFF, USER_SIZE


def hexdump(data, base=0, width=16):
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        hx = " ".join(f"{b:02X}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{base + i:08X}  {hx:<{width * 3}} {asc}")
    return "\n".join(lines)


def sector_user(mm, lba):
    off = lba * SECTOR + USER_OFF
    return mm[off : off + USER_SIZE]


def read_extent(mm, lba, size):
    out = bytearray()
    n = (size + USER_SIZE - 1) // USER_SIZE
    for i in range(n):
        out += sector_user(mm, lba + i)
    return bytes(out[:size])


def parse_dir(mm, lba, size, path, files, depth=0):
    if depth > 8:
        return
    data = read_extent(mm, lba, size)
    pos = 0
    while pos < len(data):
        rec_len = data[pos]
        if rec_len == 0:
            # 레코드는 섹터 경계를 넘지 않음 → 다음 섹터로
            pos = (pos // USER_SIZE + 1) * USER_SIZE
            continue
        rec = data[pos : pos + rec_len]
        ext_lba = int.from_bytes(rec[2:6], "little")
        ext_size = int.from_bytes(rec[10:14], "little")
        flags = rec[25]
        name_len = rec[32]
        name = rec[33 : 33 + name_len]
        pos += rec_len
        if name in (b"\x00", b"\x01"):
            continue
        name_s = name.decode("ascii", "replace").split(";")[0]
        full = f"{path}/{name_s}"
        if flags & 0x02:
            parse_dir(mm, ext_lba, ext_size, full, files, depth + 1)
        else:
            files.append((full, ext_lba, ext_size))


# ---- SJIS 스캔 ----
# 2바이트 SJIS 문자 4연속 이상
SJIS_RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]){4,}")


def is_kana(ch):
    return "぀" <= ch <= "ヿ"


def is_kanji(ch):
    return "一" <= ch <= "鿿"


def is_japanese(s):
    kana = sum(1 for c in s if is_kana(c))
    kanji = sum(1 for c in s if is_kanji(c))
    good = kana + kanji
    # 가나가 1자 이상 있거나, 전부 한자여도 6자 이상이면 인정
    return (kana >= 1 and good >= len(s) * 0.5) or (kanji >= 6 and good >= len(s) * 0.8)


def main():
    size = os.path.getsize(BIN)
    print(f"파일 크기: {size:,} bytes")
    print(f"2352로 나눈 몫: {size / SECTOR}  (정수면 raw 2352 이미지)")
    print()

    f = open(BIN, "rb")
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

    print("=== 섹터 0 앞 64바이트 (sync + header 확인) ===")
    print(hexdump(mm[:64]))
    print()

    pvd_off = 16 * SECTOR
    pvd = sector_user(mm, 16)
    print(f"=== 섹터 16 (PVD) @ 0x{pvd_off:X}, user data 첫 64바이트 ===")
    print(hexdump(pvd[:64], base=pvd_off + USER_OFF))
    print()
    assert pvd[0] == 1 and pvd[1:6] == b"CD001", "PVD 시그니처 불일치"
    vol_id = pvd[40:72].decode("ascii", "replace").strip()
    print(f"볼륨 ID: {vol_id}")

    root = pvd[156 : 156 + 34]
    root_lba = int.from_bytes(root[2:6], "little")
    root_size = int.from_bytes(root[10:14], "little")
    files = []
    parse_dir(mm, root_lba, root_size, "", files)
    files.sort(key=lambda x: x[1])
    with open(os.path.join(OUT_DIR, "iso_files.txt"), "w", encoding="utf-8") as fo:
        fo.write(f"{'LBA':>8} {'raw offset':>12} {'size':>12}  path\n")
        for name, lba, sz in files:
            fo.write(f"{lba:>8} {lba * SECTOR:>12} {sz:>12,}  {name}\n")
    print(f"\nISO 파일 수: {len(files)} → iso_files.txt 저장")

    # 오프셋 → 파일 매핑용
    file_lbas = [lba for _, lba, _ in files]

    def owner(raw_off):
        lba = raw_off // SECTOR
        i = bisect_right(file_lbas, lba) - 1
        if i >= 0:
            name, flba, fsz = files[i]
            nsec = (fsz + USER_SIZE - 1) // USER_SIZE
            if lba < flba + nsec:
                return name
        return "(파일 외 영역)"

    print("\nSJIS 스캔 중...")
    hits = []
    for m in SJIS_RUN.finditer(mm):
        try:
            s = m.group().decode("cp932")
        except UnicodeDecodeError:
            continue
        if is_japanese(s):
            hits.append((m.start(), s))
    print(f"유효 일본어 문자열: {len(hits)}개")

    # 클러스터: 64KB 이상 벌어지면 새 구간
    clusters = []
    for off, s in hits:
        if clusters and off - clusters[-1][-1][0] < 65536:
            clusters[-1].append((off, s))
        else:
            clusters.append([(off, s)])

    out_path = os.path.join(OUT_DIR, "sjis_strings.txt")
    with open(out_path, "w", encoding="utf-8") as fo:
        for cl in clusters:
            start, end = cl[0][0], cl[-1][0]
            fo.write(
                f"\n===== 클러스터 0x{start:X} ~ 0x{end:X} ({len(cl)}개, {owner(start)}) =====\n"
            )
            for off, s in cl:
                fo.write(f"0x{off:09X}  {s}\n")
    print(f"→ {out_path} 저장")

    print("\n=== 클러스터 요약 (문자열 20개 이상) ===")
    for cl in clusters:
        if len(cl) < 20:
            continue
        start, end = cl[0][0], cl[-1][0]
        total_chars = sum(len(s) for _, s in cl)
        samples = " | ".join(s[:20] for _, s in cl[len(cl) // 2 : len(cl) // 2 + 3])
        print(f"0x{start:09X}~0x{end:09X}  {len(cl):>5}개 {total_chars:>7}자  {owner(start)}")
        print(f"    예: {samples}")

    mm.close()
    f.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
