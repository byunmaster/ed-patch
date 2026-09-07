"""메모리 지도 — **한글 폰트를 RAM 어디에 올리나**의 근거.

폰트는 디스크가 아니라 **RAM 문제**다. 후킹한 CG 루틴이 글자마다 표를 읽으므로 표가
상주해야 하고, 그러려면 「이 게임이 RAM 을 어디까지 쓰나」를 알아야 한다.

실측(2026-08-30) — program 디스크 `0x5a48` 부터가 그 답이다:

    mov al,[0x501] / and ax,7 / dec ax      ; BIOS 워크 = 128KB 단위 메모리 크기
    mov cl,[0x40ac] / and cx,3              ; 유틸리티 메뉴의 설정(뱅크 수 0~3)
    → min(설정, 메모리) 만큼 뱅크를 본다

    mov ah,0x40 / mov al,0 / mov es,ax      ; 세그먼트 0x4000 = **선형 256KB**
    mov es:[0],0x96d8 / cmp                 ; 써 보고 되읽어 **RAM 이 있나** 검사
    mov es:[0],0x89ae / cmp                 ; 두 값으로 두 번 (부동 버스에 안 속는다)
    mov cx,0x10 / call 0x5b9b               ; 그 뱅크를 **8KB 페이지 16개**로 등록
    add ah,0x20 / loop                      ; 다음 뱅크 = +0x2000 세그먼트 = +128KB

    test [0x40ac],4 / mov ax,0xe000         ; 안 쓰는 **VRAM 4번째 면**도 페이지로 쓴다

⇒ **게임 자신은 0~256KB 를 쓰고, 256KB 위는 「캐시 페이지 풀」이다.** 풀에서 열 페이지
(80KB)를 떼면 완성형 2,350자(75,200B)가 통째로 들어간다 — **음절을 추릴 필요가 없다.**

⚠ 그 대신 **384KB 이상**을 요구하게 된다(256KB 뱅크가 있어야 한다). 배포 시 명시한다.
🔴 여기까지는 **정적 판독**이다. 실제로 그 자리가 비는지는 에뮬로 확인해야 한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

# 뱅크 존재 검사의 서명 — 이 자리가 사라지면 판독 전제가 무너진다.
PROBE_A = bytes.fromhex("26c7060000d896")
PROBE_B = bytes.fromhex("26c7060000ae89")
MEM_SIZE_READ = bytes.fromhex("a00105")  # mov al,[0x501] — BIOS 워크의 메모리 크기
CONFIG_BYTE = 0x40AC  # 유틸리티 메뉴가 쓰는 설정(뱅크 수 0~3 · bit2 = E000 면 사용)

FIRST_BANK_SEG = 0x4000  # 선형 256KB
BANK_STEP_SEG = 0x2000  # 128KB
PAGE_SEG = 0x0200  # 8KB
PAGES_PER_BANK = 0x10

HANGUL_BYTES = 2350 * 32


def find(flat: bytes, pat: bytes) -> list[int]:
    out, i = [], flat.find(pat)
    while i >= 0:
        out.append(i)
        i = flat.find(pat, i + 1)
    return out


def main() -> int:
    common.check_originals()
    flat = common.read_flat(common.disk_path("program"))
    a, b, m = find(flat, PROBE_A), find(flat, PROBE_B), find(flat, MEM_SIZE_READ)
    print(f"뱅크 존재 검사  {len(a)}곳 {[hex(x) for x in a]} / {len(b)}곳 {[hex(x) for x in b]}")
    print(f"메모리 크기 읽기 {len(m)}곳 {[hex(x) for x in m]}")
    if not (a and b and m):
        raise SystemExit("🔴 메모리 판독의 서명이 안 잡힌다 — 전제가 무너졌다. 문서를 고쳐라.")

    print()
    print("메모리 지도 (정적 판독)")
    print("  0x00000~0x0E000  시스템·본체        ← 시나리오 버퍼가 0000:E000")
    print("  0x10000~0x30000  게임 데이터        ← DS=0x1000·0x2000·0x3000")
    print("  0x40000~         **캐시 페이지 풀** ← 8KB × 16 / 뱅크, 128KB 씩 최대 3뱅크")
    print("  0xA0000~         VRAM (A000/A800/B000/B800) · E000 면은 남으면 캐시로")
    print()
    need_pages = -(-HANGUL_BYTES // (PAGE_SEG * 16))
    print(f"한글 완성형 2,350자 = {HANGUL_BYTES:,}B = 8KB 페이지 {need_pages}장")
    print(f"  뱅크 하나가 {PAGES_PER_BANK}장이니 **첫 뱅크에서 {need_pages}장**을 떼면 들어간다.")
    print("  ⇒ 음절을 추릴 필요가 없다(1,342자 서브셋도 검토했으나 불필요).")
    print(f"  ⚠ 대신 **384KB 이상**을 요구한다(세그먼트 {FIRST_BANK_SEG:#06x} 뱅크가 있어야 한다).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
