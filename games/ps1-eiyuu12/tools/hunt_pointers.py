"""
ED1SCN1.BIN(오버레이, RAM 0x8016A000 로드)에서 텍스트 블록을 가리키는
절대 주소 참조 탐색:
 A) u32 LE 값이 곧 RAM 주소인 데이터 테이블
 B) MIPS lui+addiu/ori 쌍으로 조립되는 주소 (코드 내 참조)
"""

import re
from collections import Counter

from common import ED1SCN1_LBA as LBA
from common import ED1SCN1_RAM_BASE as BASE
from common import ED1SCN1_SIZE as FSIZE
from common import extract

TEXT_END = 0x13208

data = extract(LBA, FSIZE)

# 텍스트 블록 시작 오프셋 ("00 뒤 %c" 또는 파일 시작 지명)
starts = set()
for m in re.finditer(rb"%c", data[:TEXT_END]):
    p = m.start()
    if p == 0 or data[p - 1] == 0x00:
        starts.add(p)
print(f"블록 시작 후보 {len(starts)}개, 오버레이 베이스 0x{BASE:X} 가정")

# A) 직접 u32 주소 테이블
hits_a = []
for i in range(0, len(data) - 4, 4):
    v = int.from_bytes(data[i : i + 4], "little")
    off = v - BASE
    if off in starts:
        hits_a.append((i, off))
print(f"\n[A] u32 절대주소(0x{BASE:X}+블록시작) 일치: {len(hits_a)}건")
for i, off in hits_a[:15]:
    print(f"    파일 0x{i:06X} → 텍스트 0x{off:05X}")

# B) MIPS lui + addiu/ori 조합
words = [int.from_bytes(data[i : i + 4], "little") for i in range(0, len(data) - 3, 4)]
hits_b = []
recent_lui = {}  # reg → (word_idx, imm)
for idx, w in enumerate(words):
    op = w >> 26
    if op == 0x0F:  # lui rt, imm
        recent_lui[(w >> 16) & 0x1F] = (idx, w & 0xFFFF)
    elif op in (0x09, 0x0D):  # addiu / ori
        rs = (w >> 21) & 0x1F
        if rs in recent_lui:
            lui_idx, hi = recent_lui[rs]
            if idx - lui_idx <= 6:
                lo = w & 0xFFFF
                if op == 0x09 and lo >= 0x8000:
                    addr = (hi << 16) + lo - 0x10000
                else:
                    addr = (hi << 16) + lo
                off = addr - BASE
                if off in starts:
                    hits_b.append((idx * 4, off))
print(f"\n[B] lui+addiu/ori 조합 일치: {len(hits_b)}건")
for i, off in hits_b[:15]:
    print(f"    파일 0x{i:06X} (코드영역={i >= TEXT_END}) → 텍스트 0x{off:05X}")

# 참조된 블록 커버리지
covered = {off for _, off in hits_a} | {off for _, off in hits_b}
print(f"\n참조로 커버된 블록: {len(covered)}/{len(starts)}")
uncov = sorted(starts - covered)
print(f"미커버 블록 예시: {[hex(u) for u in uncov[:10]]}")

# lui 상위값 분포 (텍스트 주소 대역 확인용)
lui_his = Counter((w >> 16) & 0xFFFF == 0 for w in words)  # placeholder
his = Counter(w & 0xFFFF for w in words if (w >> 26) == 0x0F and (w & 0xFFFF) in (0x8016, 0x8017))
print(f"\nlui 0x8016/0x8017 등장: {dict(his)}")
