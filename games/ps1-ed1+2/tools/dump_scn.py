"""
.bin에서 특정 ISO 파일의 유저 데이터(2048바이트/섹터)를 이어붙여 추출하고,
지정 구간을 SJIS 주석付き 헥스로 덤프한다. 제어 코드 분석용.

사용: python dump_scn.py <LBA> <size> <start> <length> [out.txt]
예:   python dump_scn.py 1183 206260 0 768   (ED1SCN1.BIN 앞 768바이트)
"""

import sys

from common import extract


def is_sjis_lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF


def annotated_dump(data, base, out):
    """16바이트 헥스 + 오른쪽에 SJIS 해석 (제어 바이트는 <xx>로 표기)"""
    i = 0
    while i < len(data):
        row = data[i : i + 16]
        hx = " ".join(f"{b:02X}" for b in row)
        # SJIS 해석: 행 단위가 아니라 흐름 단위로 하면 복잡하므로 행마다 시도
        txt = []
        j = 0
        while j < len(row):
            b = row[j]
            if is_sjis_lead(b) and j + 1 < len(row):
                try:
                    txt.append(row[j : j + 2].decode("cp932"))
                    j += 2
                    continue
                except UnicodeDecodeError:
                    pass
            if 0x20 <= b < 0x7F:
                txt.append(chr(b))
            else:
                txt.append(f"<{b:02X}>")
            j += 1
        out.write(f"{base + i:06X}  {hx:<48} {''.join(txt)}\n")
        i += 16


def main():
    lba, size, start, length = (int(x, 0) for x in sys.argv[1:5])
    out_path = sys.argv[5] if len(sys.argv) > 5 else None
    data = extract(lba, size)
    dst = open(out_path, "w", encoding="utf-8") if out_path else sys.stdout
    annotated_dump(data[start : start + length], start, dst)
    if out_path:
        dst.close()
        print(f"saved: {out_path}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
