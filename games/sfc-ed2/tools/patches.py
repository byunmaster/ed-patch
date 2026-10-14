"""sfc-ed2 코드 패치 목록 — 롬 코드·점프표를 고치는 자리 전부(원본 바이트를 단언하고 새 바이트를 쓴다).

 · 글꼴 이전: `$C0:9F56` 의 기준·소스 뱅크 상수(전각 글리프표 → `$D8:0000`)
 · 트램펄린: 대사 제어코드 `$17` → 24비트 점프(`17 lo hi bank`), 스텁 `$C0:FB10`
 · 창 블록 로더: `$C0:D6A7` 의 `mvn $7F,$C0` → `[$AC],y` 24비트 복사 루프(`$C0:FB40`)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

# 글꼴 이전 — 전각 글리프표를 `$D8:0000` 으로 옮긴다(원본은 `$D6:81D1`, 반각 글꼴 앞이라 1,284자뿐).
# 소비자는 `$C0:9F56` 한 곳: `adc #$81D1`(기준) · `mvn $00,$D6`(소스 뱅크) — 둘을 고친다. 길이 `$12` 는 그대로.
FONT_BANK = 0xD8
FONT_SLOTS = 2048  # 2바이트 코드 `$8000~$87FF` 전부
SOUND_OPT_ADDR_LO = bytes([0x00, 0xFF])
SOUND_OPT_ADDR_HI = bytes([0x08, 0xFF])
PATCHES = [  # (주소, 원본 바이트, 새 바이트) — 원본이 다르면 그 자리에서 죽는다
    (0xC09F71, bytes([0xD1, 0x81]), bytes([0x00, 0x00])),
    (0xC09F81, bytes([0xD6]), bytes([FONT_BANK])),
    # 사운드 선택 창의 옵션 칸(스테레오/모노럴) — 원본은 옵션당 6B(`mvn` 5+1)를 줄 버퍼 `$7F:D43B` 에 복사한다. 전각 4자(8B)가 들어가도록
    # 복사를 `$D43A` 부터 8B 로 넓히고(`$D43A~D441` 은 뒤가 전부 공백 — 창 안쪽 폭 안), 원본 문자열(`$D0C3`/`$D0C9`, 뒤가 코드)은 `$C0:FF00` 으로 옮긴다.
    (0xC0D075, bytes([0xC3, 0xD0]), SOUND_OPT_ADDR_LO),  # ldx #$D0C3 → #$FF00 (스테레오)
    (0xC0D080, bytes([0xC9, 0xD0]), SOUND_OPT_ADDR_HI),  # ldx #$D0C9 → #$FF08 (모노럴)
    (0xC0D083, bytes([0x3B, 0xD4]), bytes([0x3A, 0xD4])),  # ldy #$D43B → #$D43A
    (0xC0D086, bytes([0x05]), bytes([0x07])),  # lda #$0005 → #$0007 (8B)
    (0xC0FF08, bytes([0xFF] * 8), bytes.fromhex("D3C9D7D9" "20202020")),  # 모노럴 — 원문(반각 가타카나 4자) + 공백 4
]

# 트램펄린 — 대사 제어코드 `$17`(원본 핸들러는 `rts` 뿐, 단위 안 출현 1회) 을 **24비트 점프**로 바꾼다: `17 lo hi bank`.
# 메시지 머리를 이 4바이트로 덮고 번역문은 확장 뱅크에 둔다(`$0F` 는 같은 뱅크 16비트라 뱅크를 못 넘는다).
# 핸들러는 `$0F`(`$C0:AD89`)와 같은 규약이다: Y = 제어코드 다음 색인(16비트), `[$A6]` 가 텍스트 포인터. 뱅크 `$C0` 끝 0xFF 빈 자리에 둔다.
STUB_ADDR = 0xC0FB10
STUB = bytes.fromhex(
    "B7A6" "C8" "8DAC00"  # lda [$A6],y ; iny ; sta $00AC   (lo)
    "B7A6" "C8" "8DAD00"  # lda [$A6],y ; iny ; sta $00AD   (hi)
    "B7A6" "8DA800"  # lda [$A6],y ; sta $00A8             (bank — 마지막에 읽고 바꾼다)
    "ACAC00" "8CA600"  # ldy $00AC ; sty $00A6
    "A00000" "60"  # ldy #$0000 ; rts
)
TRAMP_CODE = 0x17
TRAMP_ENTRY = 0xC0AB43 + 2 * TRAMP_CODE  # 제어코드 점프표(핸들러 주소 − 1, 리틀엔디언)
PATCHES += [
    (TRAMP_ENTRY, bytes([0xA2, 0xAE]), ((STUB_ADDR - 1) & 0xFFFF).to_bytes(2, "little")),
    (STUB_ADDR, b"\xff" * len(STUB), STUB),
]

# 창 블록 로더(`$C0:D6A7`)는 `mvn $7F,$C0` 으로 블록을 복사해 **소스 뱅크가 $C0 에 박혀 있다** — 블록을 확장 뱅크로 못 옮긴다.
# 복사 구간(`$C0:D6D9~D6E5`, 13B)을 `JML $C0:FB40` 으로 돌려 `[$AC],y`(24비트) 복사 루프로 바꾼다. 진입 상태: A·X·Y 16비트,
# `$11E8` = 블록 길이(5 + rows×stride), `[$AC..$AE]` = 블록 24비트 주소. 복귀는 원본 꼬리(`sep #$30; lda #0; pha; plb; plp; rtl`)와 같다.
LOADER_ADDR = 0xC0D6D9
LOADER_OLD = bytes.fromhex("AEAC00" "A028D4" "ADE811" "3A" "547FC0")
LOADER_STUB_ADDR = 0xC0FB40
LOADER_STUB = bytes.fromhex(
    "E220"  # sep #$20
    "A20000" "A00000"  # ldx #0 ; ldy #0
    "B7AC" "9F28D47F" "C8" "E8" "CCE811" "D0F3"  # loop: lda [$AC],y ; sta $7F:D428,x ; iny ; inx ; cpy $11E8 ; bne loop
    "E230" "A900" "48" "AB" "28" "6B"  # sep #$30 ; lda #0 ; pha ; plb ; plp ; rtl
)
PATCHES += [
    (LOADER_ADDR, LOADER_OLD, bytes([0x5C, LOADER_STUB_ADDR & 0xFF, (LOADER_STUB_ADDR >> 8) & 0xFF, LOADER_STUB_ADDR >> 16]) + b"\xea" * 9),
    (LOADER_STUB_ADDR, b"\xff" * len(LOADER_STUB), LOADER_STUB),
]

# 조사(은/는 · 이/가 · 을/를 · 과/와) 런타임 훅 — 직전에 그린 글자의 받침 유무로 조사 글리프를 고른다(번역 규칙 3-5: 병기 `은(는)` 을 화면에 남기지 않는다).
#  · 전각 글리프 가져오기 `$C0:9F56`(대사·UI 공용) 첫머리 `rep #$30 · lda $1B18`(5B)을 `JSL stub1 · NOP` 으로 바꾼다:
#      색인이 가짜 조사 글리프(`$87F0~$87F3`)면 받침 변수에 맞는 실제 조사 글리프로 바꿔 `$1B18` 에 쓰고, 그린 글자의 받침 부류를 변수 `JOSA_VAR` 에 기록한다.
#  · 반각 글리프 `$C0:90E8` 첫머리(`php` 다음 5B)도 같게(`stub2`): 숫자는 읽는 소리(영·일·삼·육·칠·팔 = 받침)로, 공백이 아닌 나머지는 받침 없음.
#  · 받침 표(2,048B, 색인 → 0/1)와 조사 쌍 표(4쌍 × [받침 있음, 없음] 글리프 코드)·숫자 표는 빌드가 `$D8:F000~`에 쓴다.
import asm65816

JOSA_VAR = 0x7FFFFE  # WRAM $7F:FFFE — 코드가 참조하지 않는 구석(원본 전체에서 `FE FF 7F` 없음)
JOSA_TABLE = 0xD8F000  # 받침 표(색인×1B)
JOSA_PAIRS = 0xD8F800  # 조사 쌍(4쌍 × 4B: 받침 있음 코드, 받침 없음 코드, 리틀엔디언)
JOSA_DIGITS = 0xD8F820  # 숫자 0~9 받침(10B)
JOSA_BASE = 0x87F0  # 가짜 조사 글리프 시작(2바이트 코드) — 색인 0x7F0~0x7F3
JOSA_COUNT = 4
JOSA_STUB1 = 0xC0FB80
JOSA_STUB2 = 0xC0FBE0


def _stub1() -> bytes:
    a = asm65816.Asm(JOSA_STUB1 & 0xFFFF, 0xC0)
    a.rep(imm=0x30)
    a.lda(addr=0x1B18, mode="abs")  # A = 코드(16비트)
    a.cmp(imm=JOSA_BASE, m16=True)
    a.bcc(label="store")
    a.cmp(imm=JOSA_BASE + JOSA_COUNT, m16=True)
    a.bcs(label="store")
    a.sec()
    a.sbc(imm=JOSA_BASE, m16=True)
    a.asl()
    a.asl()  # ×4
    a.tax()
    a.sep(imm=0x20)
    a.lda(addr=JOSA_VAR, mode="long")  # 받침 부류
    a.beq(label="vowel")
    a.rep(imm=0x20)
    a.lda(addr=JOSA_PAIRS, mode="longx")  # 받침 있음 쪽
    a.bra(label="set")
    a.label("vowel")
    a.rep(imm=0x20)
    a.lda(addr=JOSA_PAIRS + 2, mode="longx")  # 받침 없음 쪽
    a.label("set")
    a.sta(addr=0x1B18, mode="abs")
    a.label("store")  # A = 그릴 코드
    a.pha()
    a.sec()
    a.sbc(imm=0x8000, m16=True)
    a.tax()
    a.sep(imm=0x20)
    a.lda(addr=JOSA_TABLE, mode="longx")
    a.sta(addr=JOSA_VAR, mode="long")
    a.rep(imm=0x20)
    a.pla()
    a.rtl()
    return a.assemble()


def _stub2() -> bytes:
    a = asm65816.Asm(JOSA_STUB2 & 0xFFFF, 0xC0)
    a.rep(imm=0x30)
    a.lda(addr=0x1B18, mode="abs")
    a.pha()
    a.op("and", imm=0x00FF, m16=True)
    a.cmp(imm=0x30, m16=True)
    a.bcc(label="other")
    a.cmp(imm=0x3A, m16=True)
    a.bcs(label="other")
    a.sec()
    a.sbc(imm=0x30, m16=True)
    a.tax()
    a.sep(imm=0x20)
    a.lda(addr=JOSA_DIGITS, mode="longx")
    a.sta(addr=JOSA_VAR, mode="long")
    a.bra(label="done")
    a.label("other")
    a.cmp(imm=0x20, m16=True)  # A 는 아직 16비트
    a.beq(label="done")  # 공백은 받침 부류를 안 바꾼다
    a.sep(imm=0x20)
    a.lda(imm=0x00)
    a.sta(addr=JOSA_VAR, mode="long")
    a.label("done")
    a.rep(imm=0x20)
    a.pla()
    a.rtl()
    return a.assemble()


STUB1, STUB2 = _stub1(), _stub2()
PATCHES += [
    (0xC09F56, bytes.fromhex("C230AD181B"), bytes([0x22]) + JOSA_STUB1.to_bytes(3, "little") + b"\xea"),
    (0xC090E9, bytes.fromhex("C230AD181B"), bytes([0x22]) + JOSA_STUB2.to_bytes(3, "little") + b"\xea"),
    (JOSA_STUB1, b"\xff" * len(STUB1), STUB1),
    (JOSA_STUB2, b"\xff" * len(STUB2), STUB2),
]


# 반각 글꼴(`$D6:DC19 + (코드−$20)×16`, 8×16)은 ASCII 순서가 아니다 — `!`=$21 · `?`=$22 · `-`=$2D · 숫자·영문은 제자리지만 `,`($2C) `.`($2E) 는 **빈 글리프**다(일본어 대본이 안 쓴다).
# 한국어 문장부호를 위해 두 칸을 그린다(숫자와 같은 밑선: 행 13~14). `$25~$29`(HUD 조각)·`$23 $24`(▼)는 건드리지 않는다. `?` 는 $22 로 인코딩한다(kr.py).
HALF_BASE = 0xD6DC19
HALF_GLYPHS = {
    0x2C: (13, ["...##...", "...##...", "...#...."]),  # ,
    0x2E: (13, ["...##...", "...##..."]),  # .
}
for _code, (_row, _pic) in HALF_GLYPHS.items():
    _data = bytearray(16)
    for _i, _line in enumerate(_pic):
        _data[_row + _i] = int(_line.replace("#", "1").replace(".", "0"), 2)
    PATCHES.append((HALF_BASE + (_code - 0x20) * 16, bytes(16), bytes(_data)))

EXCEPT = [(common.snes2off(a), common.snes2off(a) + len(n)) for a, _o, n in PATCHES]
FONT_OUT = common.snes2off(FONT_BANK << 16)


