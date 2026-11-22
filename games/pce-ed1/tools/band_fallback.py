"""장 제목 띠(세이브 LOAD 뒤 빈 띠) — 캐시 칸이 없을 때 글리프 뱅크 1(0x87)의 앞 섹터를 잠시 빌려 띠를 읽고 되돌린다(11-06 마스터 「(가)안」).

🔴 원인(실측): 로드 직후 살아 있는 캐시 그룹이 한글판 14칸을 다 써서 띠 자원(rec 210, 1섹터)을 올릴 칸이 없다. 띠 루틴(뱅크 0x70 `$7242`)은
`JSR $56D8`(로더)의 **캐리를 안 보고** 그대로 그려서 빈 띠가 된다. 원판은 16칸이라 14·15번 칸이 비어 거기에 올린다.

고침: 로더가 실패하면(C=1) ① 빈 그룹 번호를 하나 잡아 슬롯 15(= 글리프 뱅크 1 = 뱅크 0x87)에 매기고 ② 그 뱅크 앞 섹터에 띠를 CD 에서 곧장 읽는다(로더 `$5720~`
와 같은 BIOS `CD_READ $E009` 호출 꼴). 띠 루틴이 그리고 나서 그룹을 풀 때(`JSR $5597`) 슬롯이 15 였으면 **그 섹터를 글리프 원본 위치(디스크 rel 118 =
프로그램 이미지 뱅크 0x7D 앞 섹터)에서 다시 읽어 글리프를 되돌린다**(실패하면 8번 재시도). 띠를 그리는 동안은 글자를 찍는 일이 없다(맵 적재 뒤 연출 전).
자리: 뱅크 0x70 `$731E~` FF 패딩(3298B) — 띠 루틴이 선 같은 뱅크라 호출 때 늘 걸려 있다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hook

LOAD_ORG = 0x7320  # 뱅크 0x70 +0x1320
CALL_SITE = 0x7248  # `JSR $56D8`(띠 로더 호출) — 뱅크 0x70 +0x1248
FREE_SITE = 0x731A  # `JSR $5597`(띠 그룹 풀기) — 뱅크 0x70 +0x131A
LOADER, ALLOC_GROUP, FREE_GROUP, CD_READ = 0x56D8, 0x578A, 0x5597, 0xE009
BAND_REL = 210  # 띠 자원 디스크 rel (= 로더의 X,Y + 0x22)
GLYPH1_REL = 118  # 글리프 뱅크 1 앞 섹터의 디스크 위치 — 프로그램 이미지 rel 34 + (0x7D − 0x68)×4
BORROW_SLOT = 15  # 캐시 슬롯 15 = 뱅크 0x87 = 글리프 뱅크 1
BORROW_BANK = 0x87


def _cd_read(a: hook.Asm, rel: int) -> None:
    """로더 `$5716~$5732` 와 같은 CD 읽기 — 1섹터를 뱅크 0x87 앞에. 호출 뒤 A = BIOS 결과(0 = 성공), MPR6 은 호출한 쪽이 되돌린다."""
    a.op("LDA", "imm", 1)
    a.op("STA", "zp", 0xF8)
    a.op("LDA", "imm", rel & 0xFF)
    a.op("STA", "zp", 0xFE)
    a.op("LDA", "imm", rel >> 8)
    a.op("STA", "zp", 0xFD)
    a.op("STZ", "zp", 0xFC)
    a.op("LDA", "imm", 0xFF)
    a.op("STA", "zp", 0x76)
    a.op("TMA", "tma", 6)
    a.op("PHA")
    a.op("LDA", "imm", 6)
    a.op("STA", "zp", 0xFF)
    a.op("LDA", "imm", BORROW_BANK)
    a.op("STA", "zp", 0xFA)
    a.op("JSR", "abs", CD_READ)


def _asm() -> tuple[hook.Asm, int]:
    a = hook.Asm(LOAD_ORG)
    # ── 띠 로드: 원래 호출 + 실패 때 글리프 뱅크 1 을 빌려 읽는다
    a.op("JSR", "abs", LOADER)
    a.op("BCC", "rel", "ret")
    a.op("JSR", "abs", ALLOC_GROUP)  # 빈 그룹 번호 → Y (C=1 이면 없음)
    a.op("BCS", "rel", "fail")
    a.op("LDA", "imm", BORROW_SLOT)
    a.op("STA", "absy", 0x378D)  # 그룹 → 슬롯 15
    a.op("STY", "abs", 0x3798)  # 로더 임시칸(`$3798`) 을 빌려 쓴다 — 로더가 쓰는 동안만 의미가 있다
    _cd_read(a, BAND_REL)
    a.op("LDY", "abs", 0x3798)
    a.op("CMP", "imm", 0)
    a.op("BNE", "rel", "bad")
    a.op("PLA")
    a.op("TAM", "tam", 6)
    a.op("CLC")
    a.op("RTS")
    a.label("bad")
    a.op("PLA")
    a.op("TAM", "tam", 6)
    a.op("LDA", "imm", 0x80)
    a.op("STA", "absy", 0x378D)  # 그룹을 다시 빈 것으로
    a.label("fail")
    a.op("SEC")
    a.label("ret")
    a.op("RTS")
    # ── 띠 그룹 풀기: 원래 `JSR $5597` + 슬롯 15 를 빌렸으면 글리프 뱅크 1 앞 섹터를 디스크에서 되돌린다
    free_at = a.pc
    a.op("PHA")
    a.op("TAY")
    a.op("LDA", "absy", 0x378D)
    a.op("TAX")
    a.op("PLA")
    a.op("PHX")
    a.op("JSR", "abs", FREE_GROUP)
    a.op("PLX")
    a.op("CPX", "imm", BORROW_SLOT)
    a.op("BNE", "rel", "done")
    a.label("restore")  # 글리프 뱅크 1 앞 섹터 되돌리기 — `transient_fallback` 도 여기로 뛴다(`restore_at`)
    a.op("LDY", "imm", 8)
    a.label("retry")
    a.op("PHY")
    _cd_read(a, GLYPH1_REL)
    a.op("TAX")
    a.op("PLA")
    a.op("TAM", "tam", 6)
    a.op("PLY")
    a.op("CPX", "imm", 0)
    a.op("BEQ", "rel", "done")
    a.op("DEY")
    a.op("BNE", "rel", "retry")
    a.label("done")
    a.op("RTS")
    return a, free_at


def code() -> tuple[bytes, int]:
    """(코드 바이트, 띠 그룹 풀기 입구 주소) — 로드 입구는 `LOAD_ORG`."""
    a, free_at = _asm()
    return a.bytes(), free_at


def restore_at() -> int:
    """글리프 뱅크 1 앞 섹터를 디스크에서 되돌리는 고리의 주소(8번 재시도 뒤 RTS · A·X·Y 를 쓴다 · MPR6 은 되돌린다)."""
    a, _ = _asm()
    return a.labels["restore"]


if __name__ == "__main__":
    b, f = code()
    print(len(b), "B  free_at", hex(f))
    print(b.hex())
