"""
길이 변경 실험이 로딩 멈춤을 유발 → 오프셋 민감 구조 탐색.

1) Len Test 빌드 라운드트립 검증 (빌더 버그 배제)
2) ED1SCN1.BIN에서 대사 블록 시작(00 뒤 '%c') 오프셋 수집
3) 파일 전체에서 u16/u32 LE 배열이 블록 시작 오프셋들과 (상수 베이스 허용)
   연속 일치하는 구간 탐색 = 오프셋 테이블 후보
4) 텍스트 영역 꼬리(0x13180~)와 그 뒤 데이터 구조 덤프
"""

import os
import re

from common import ED1SCN1_LBA as LBA
from common import ED1SCN1_SIZE as FSIZE
from common import WORK_DIR, extract

LEN = os.path.join(WORK_DIR, "Eiyuu Densetsu (Len Test).bin")

orig = extract(LBA, FSIZE)
lent = extract(LBA, FSIZE, path=LEN)

# 1) 라운드트립 검증
DEL_AT, INS_AT = 0x21, 0x132B0
expect = orig[:DEL_AT] + orig[DEL_AT + 2 : INS_AT] + b"\x00\x00" + orig[INS_AT:]
print(
    f"[1] Len Test 빌드 검증: {'OK — 의도한 바이트열과 정확히 일치' if lent == expect else '불일치!! 빌더 버그'}"
)

# 2) 블록 시작 오프셋 수집
starts = []
for m in re.finditer(rb"%c", orig[:0x13300]):
    p = m.start()
    if p == 0 or orig[p - 1] == 0x00:
        starts.append(p)
print(f'[2] "00 뒤 %c" 블록 시작 후보: {len(starts)}개 (첫 5개: {[hex(s) for s in starts[:5]]})')
sset = set(starts)


# 3) 오프셋 테이블 탐색
def u16(b, i):
    return b[i] | (b[i + 1] << 8)


def u32(b, i):
    return u16(b, i) | (u16(b, i + 2) << 16)


def hunt(width, reader):
    found = []
    i = 0
    while i < len(orig) - width * 8:
        # 이 지점부터 연속 몇 개의 값이 (동일 베이스 보정으로) 블록 시작과 일치하나
        v0 = reader(orig, i)
        matched = 0
        for base_cand in {v0 - s for s in sset if abs(v0 - s) < 0x20000} or {None}:
            if base_cand is None:
                break
            run = 0
            j = i
            while j < len(orig) - width:
                v = reader(orig, j) - base_cand
                if v in sset:
                    run += 1
                    j += width
                else:
                    break
            if run > matched:
                matched, base = run, base_cand
        if matched >= 8:
            found.append((i, matched, base))
            i += matched * width
        else:
            i += 1 if width == 2 else 2
    return found


for width, reader, name in ((2, u16, "u16"), (4, u32, "u32")):
    hits = hunt(width, reader)
    print(f"[3] {name} 테이블 후보: {len(hits)}개")
    for off, run, base in hits[:10]:
        print(f"    파일 0x{off:X}: 연속 {run}개 일치, 베이스 0x{base:X}")


# 4) 텍스트 꼬리와 이후 구조
def dump(data, start, length, label):
    print(f"\n[4] {label} (0x{start:X}~)")
    for i in range(start, min(start + length, len(data)), 16):
        row = data[i : i + 16]
        hx = " ".join(f"{b:02X}" for b in row)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        print(f"{i:06X}  {hx:<48} {asc}")


dump(orig, 0x131F0, 0x60, "마지막 문자열 주변")
dump(orig, 0x132B0, 0x80, "00 보충 지점 이후")
dump(orig, 0x13400, 0x60, "텍스트 영역 뒤 데이터")

if __name__ == "__main__":
    pass
