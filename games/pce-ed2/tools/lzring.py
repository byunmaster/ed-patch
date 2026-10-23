"""642 전용 512B 링 복호기 변형(마스터 10-22 「3은 일단 a」) — 대본 덩이 압축의 창을 256B → 512B 로 넓혀 642 의 연출 멈춤을 다 살린다(`lz.py` 머리말: 표식·니블 쪼개기).

기전: 대사 불러오기 래퍼(뱅크 0x6E `$7D84`)는 덩이를 풀기 전에 `JMP $5796`(복호 초기화)을 부르고, 한 바이트씩 `$7D91 → JMP $57AC`(복호 한 바이트)로 당긴다.
 ① `$7D8E` 의 `JMP $5796` 을 우리 초기화로 돌린다(뱅크 0x6E 의 패딩 꼬리). 초기화는 원래 `$5796` 을 부른 뒤 덩이 첫 바이트를 본다 —
    `7C`(표식)이면 그 바이트를 삼키고 512B 상태(쓰기 인덱스 `$EE:EF` · 남은 복사 길이 0)를 세운 뒤 **`$7D9F` 의 `JMP $57AC` 의 목적지를 우리 한 바이트 루틴으로 바꾼다**
    (게임 코드가 원래 자기 명령 바이트를 고쳐 쓰는 방식 그대로 — 뱅크는 CD RAM 이다). 아니면 `$57AC` 로 되돌려 놓는다 → **표식 없는 덩이(다른 패키지 전부, 642 의 안 고친 덩이)는 원판과 같은 경로**다.
 ② 한 바이트 루틴(뱅크 0x68 영(0) 패딩 꼬리 — 늘 `$4000` 에 걸려 있다): 원판 `$57AC` 와 같은 모양(플래그는 `$5763`, 니블은 `$5776` 재사용)이되
    되참조의 니블에서 길이 3비트(+2)와 링 인덱스 9번째 비트를 나눠 쓰고, 읽기·쓰기 포인터가 `$EE00~$EFFF` 두 쪽을 돈다. X·Y 는 건드리지 않는다.
링 자리 `$EE00~$EFFF`(뱅크 0x87 512B)는 10-22 독 주입 대조로 확인한 빈 칸이다(`docs/status.md`).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout
import longline
import lz

DEFAULT_PKGS = {642, 1538, 1282}  # 512B 링 변형을 쓰는 패키지(rel) — 642 멈춤 복원 · 1538 글리프 예산 · 1282 멈춤 복원(마스터 10-22 「그렇게 가자」)
# 패키지별 스위치(환경 변수, 쉼표로 번호): `ED_LZ256=1282,642` → 그 패키지는 원래 256B 압축으로 굽는다(인게임에서 그 장면 글자가 깨질 때) · `ED_LZ512=898` → 그 패키지도 새 압축으로


def _nums(name: str) -> set[int]:
    return {int(x) for x in os.environ.get(name, "").replace(" ", "").split(",") if x}


PKGS = (DEFAULT_PKGS | _nums("ED_LZ512")) - _nums("ED_LZ256")

INIT_BANK, INIT_OFF = 0x6E, 0x1FBB  # 뱅크 0x6E 의 0xFF 패딩 꼬리(긴 줄 루틴 뒤 69B)
FETCH_BANK, FETCH_END = 0x68, 0x1473 + 241  # 뱅크 0x68 영(0) 패딩의 끝 — 앞쪽은 글리프 풀이 쓴다
INIT_SEAM = 0x1D8E  # `$7D8E: JMP $5796`
INIT_SEAM_OLD = bytes.fromhex("4c9657")
FETCH_JMP = 0x1D9F  # `$7D9F: JMP $57AC` — 초기화가 목적지(+1, +2)를 고친다
FETCH_JMP_OLD = bytes.fromhex("4cac57")
RING_HI = 0xEE  # 링 첫 쪽(`$EE00`) — 둘째 쪽은 `$EF00`


def _fetch(org: int) -> longline._A:
    a = longline._A(org)
    a.label("F")
    a.b(0xA9)  # LDA #남은 복사 길이 (피연산자가 상태 — 아래 CNT)
    a.label("CNT")
    a.b(0x00)
    a.rel(0xD0, "copy")  # BNE copy
    a.abs_(0x20, 0x5763)  # JSR $5763 — 플래그 비트 → C (1 = 리터럴)
    a.rel(0x90, "match")  # BCC match
    a.b(0xB2, 0x31, 0xE6, 0x31, 0xD0, 0x02, 0xE6, 0x32)  # LDA ($31); INC $31; BNE +2; INC $32 — 리터럴 1B
    a.rel(0x80, "store")  # BRA store
    a.label("match")
    a.b(0xB2, 0x31, 0xE6, 0x31, 0xD0, 0x02, 0xE6, 0x32)  # 되참조 인덱스 하위 8비트
    a.abs_(0x8D, "RDLO")  # STA 읽기 하위
    a.abs_(0x20, 0x5776)  # JSR $5776 — 니블
    a.b(0x48)  # PHA
    a.b(0x29, 0x07, 0x1A, 0x1A)  # AND #7; INC; INC — 길이
    a.abs_(0x8D, "CNT")  # STA 남은 길이
    a.b(0x68, 0x4A, 0x4A, 0x4A)  # PLA; LSR ×3 — 인덱스 9번째 비트
    a.b(0x09, RING_HI)  # ORA #$EE
    a.abs_(0x8D, "RDHI")  # STA 읽기 상위
    a.label("copy")
    a.b(0xAD)  # LDA $EE00 (읽기)
    a.label("RDLO")
    a.b(0x00)
    a.label("RDHI")
    a.b(RING_HI)
    a.abs_(0xEE, "RDLO")  # INC 읽기 하위
    a.rel(0xD0, "c1")  # BNE c1
    a.b(0x48)  # PHA
    a.abs_(0xAD, "RDHI")
    a.b(0x49, 0x01)  # EOR #1 — 쪽 넘기기 ($EE ↔ $EF)
    a.abs_(0x8D, "RDHI")
    a.b(0x68)  # PLA
    a.label("c1")
    a.abs_(0xCE, "CNT")  # DEC 남은 길이
    a.label("store")
    a.b(0x8D)  # STA $EE00 (쓰기)
    a.label("WRLO")
    a.b(0x00)
    a.label("WRHI")
    a.b(RING_HI)
    a.abs_(0xEE, "WRLO")  # INC 쓰기 하위
    a.rel(0xD0, "done")  # BNE done
    a.b(0x48)
    a.abs_(0xAD, "WRHI")
    a.b(0x49, 0x01)
    a.abs_(0x8D, "WRHI")
    a.b(0x68)
    a.label("done")
    a.b(0x60)  # RTS
    return a


def _init(org: int, fetch_org: int) -> longline._A:
    f = _fetch(fetch_org)
    L = f.labels
    a = longline._A(org)
    a.label("I")
    a.abs_(0x20, 0x5796)  # JSR $5796 — 원판 초기화(포인터 · 플래그 · 니블)
    a.b(0xB2, 0x31)  # LDA ($31) — 덩이 첫 바이트
    a.b(0xC9, lz.MARK2)  # CMP #$7C — 표식인가
    a.rel(0xD0, "normal")  # BNE normal
    a.b(0xE6, 0x31, 0xD0, 0x02, 0xE6, 0x32)  # 표식 삼키기
    a.b(0xA9, 0xEF)  # LDA #$EF
    a.abs_(0x8D, L["WRLO"])  # 쓰기 인덱스 하위 = $EF
    a.b(0xA9, RING_HI)
    a.abs_(0x8D, L["WRHI"])  # 쓰기 쪽 = $EE
    a.abs_(0x9C, L["CNT"])  # STZ 남은 길이
    a.b(0xA9, L["F"] & 0xFF, 0xA2, L["F"] >> 8)  # LDA #<F; LDX #>F
    a.rel(0x80, "set")
    a.label("normal")
    a.b(0xA9, 0xAC, 0xA2, 0x57)  # LDA #<$57AC; LDX #>$57AC
    a.label("set")
    a.abs_(0x8D, 0x6000 + FETCH_JMP + 1)  # STA $7DA0
    a.abs_(0x8E, 0x6000 + FETCH_JMP + 2)  # STX $7DA1
    a.b(0x60)
    return a


def _fetch_org() -> int:
    n = len(_fetch(0).done())
    return 0x4000 + FETCH_END - n


def fetch_code() -> bytes:
    return _fetch(_fetch_org()).done()


def init_code() -> bytes:
    return _init(0x6000 + INIT_OFF, _fetch_org()).done()


def reserve(prog: layout.Prog) -> None:
    prog.reserve(INIT_BANK, INIT_OFF, len(init_code()))
    prog.reserve(FETCH_BANK, FETCH_END - len(fetch_code()), len(fetch_code()))


def install(prog: layout.Prog) -> None:
    assert prog.o(INIT_BANK, INIT_SEAM, 3) == INIT_SEAM_OLD, "복호 초기화 이음매 원본 바이트가 다르다"
    assert prog.o(INIT_BANK, FETCH_JMP, 3) == FETCH_JMP_OLD, "복호 한 바이트 이음매 원본 바이트가 다르다"
    ic, fc = init_code(), fetch_code()
    assert set(prog.o(INIT_BANK, INIT_OFF, len(ic))) == {0xFF}, "복호 초기화 자리가 비어 있지 않다"
    off = FETCH_END - len(fc)
    assert set(prog.o(FETCH_BANK, off, len(fc))) == {0}, "복호 한 바이트 자리가 영 칸이 아니다"
    prog.put(INIT_BANK, INIT_OFF, ic, "lzring 초기화(512B 링 표식 검사)")
    prog.put(FETCH_BANK, off, fc, "lzring 한 바이트(512B 링)")
    prog.put(INIT_BANK, INIT_SEAM, bytes([0x4C]) + (0x6000 + INIT_OFF).to_bytes(2, "little"), "lzring 이음매 $7D8E → 우리 초기화")
