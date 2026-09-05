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
from common import MIPS_ADDIU, MIPS_ORI, extract, iter_lui_pairs

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

# B) MIPS lui + addiu/ori 조합 (공용 스캐너 재사용)
hits_b = [
    (imm_off, addr - BASE)
    for imm_off, _, _, addr in iter_lui_pairs(data, (MIPS_ADDIU, MIPS_ORI))
    if addr - BASE in starts
]
print(f"\n[B] lui+addiu/ori 조합 일치: {len(hits_b)}건")
for i, off in hits_b[:15]:
    print(f"    파일 0x{i:06X} (코드영역={i >= TEXT_END}) → 텍스트 0x{off:05X}")

# 참조된 블록 커버리지
covered = {off for _, off in hits_a} | {off for _, off in hits_b}
print(f"\n참조로 커버된 블록: {len(covered)}/{len(starts)}")
uncov = sorted(starts - covered)
print(f"미커버 블록 예시: {[hex(u) for u in uncov[:10]]}")

# lui 상위값 분포 (텍스트 주소 대역 0x8016/0x8017 확인용)
words = [int.from_bytes(data[i : i + 4], "little") for i in range(0, len(data) - 3, 4)]
his = Counter(w & 0xFFFF for w in words if (w >> 26) == 0x0F and (w & 0xFFFF) in (0x8016, 0x8017))
print(f"\nlui 0x8016/0x8017 등장: {dict(his)}")
