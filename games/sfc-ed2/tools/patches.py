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
    # 세이브·로드 목록 줄 — EP 여섯 자리 숫자 바로 뒤에 지명이 붙어 「０엘아스타」 로 읽힌다(원판은 전각 지명의 여백에 기댄 꼴). 지명 복사 시작을 한 칸 뒤($7F:CD3D)로 밀어 반각 공백 하나를 둔다
    # 저장·로드·삭제 안내 — 안내 문장을 버퍼 `$7F:D496` 로 `mvn` 복사하는 길이를 26B → 30B 로 넓힌다(`lda #$0019` → `#$001D`). 합쇼체(「어디에 세이브하시겠습니까?」 27B)가 26B 에 안 든다.
    # 문장은 spans.json `move` 로 뱅크 $CB 빈 자리(0 패딩 30B)로 옮기고 `ldx #imm16` 세 곳을 돌린다.
    (0xCB66F3, bytes.fromhex("A91900"), bytes.fromhex("A91D00")),
    (0xCB6A33, bytes([0xFF]), bytes([0x00])),  # ldx #$FF → #$00 (지명 복사 시작 색인)
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

# 아이템 이름 15B — 이름 버퍼 `$1201~$120F`(15B, 끝 토큰 `06` 은 `$120F`)에 한 바이트짜리 반각 공백 때문에 15B 가 된 이름(성스러운 지팡이 …)이 안 든다.
# 이름 표를 16B 칸 새 표로 옮기고(빌드가 `ITEM_TABLE` 을 쓴다) 칸 안에 끝 토큰을 직접 둔다: 복사 15B(`$C1:3365`) · 곱셈 칸 16(`$C1:334D`) · `$120F=06` 쓰기 삭제(5B nop).
# 15B 를 꽉 채운 이름은 `06` 이 없으므로 소비자 둘(`$C0:DA00` 줄 버퍼 16B · `$C0:DD1D` 17B)의 「끝 토큰 검사」를 스텁으로 바꿔 **색인 14 에서도 멈추게** 한다.
ITEM_STUB_A = 0xC0FC40
ITEM_STUB_B = 0xC0FC60
FLUSH_STUB = 0xC0FC80


def _flush() -> bytes:
    """`$C0:9454` 직전에 줄 끝 불완전 타일을 DMA 에 넣는다 — `$1323`=1 이면 마지막 글자의 남은 4px 가 이미 다음 캔버스 타일(`$1358`)에 들어 있다(`$C0:92F3` 이 N·N+1 두 타일에 쓴다)
    그저 완성 타일 수에 안 세어져 버려졌을 뿐이다. 8비트 A·X, 호출은 JSL — 끝에서 원래 두 명령(`lda $119F · sta $119C`)을 실행하고 RTL."""
    body = bytes([0xEE, 0x58, 0x13])  # inc $1358
    head = bytes([0xAD, 0x23, 0x13, 0xF0, len(body)])  # lda $1323 · beq done
    return head + body + bytes([0xAD, 0x9F, 0x11, 0x8D, 0x9C, 0x11, 0x6B])  # done: lda $119F · sta $119C · rtl


_FLUSH = _flush()
_STUB_A = bytes.fromhex("C906D0034C08DAE00ED0 04C84C1ADA4C04DA".replace(" ", ""))
_STUB_B = bytes.fromhex("C906D0034C25DDE00ED009C8A92097 97C84C3FDD4C21DD".replace(" ", ""))
PATCHES += [
    (0xC13365, bytes([0x0E]), bytes([0x0F])),  # cpx #$000E → #$000F (복사 바이트 수)
    (0xC1334D, bytes([0x0E]), bytes([0x10])),  # lda #$0E → #$10 (표 칸 크기)
    (0xC13369, bytes.fromhex("A9068D0F12"), b"\xea" * 5),  # lda #$06 · sta $120F — 끝 토큰은 이제 표에 있다
    (0xC0DA00, bytes.fromhex("C906F004"), bytes([0x4C, ITEM_STUB_A & 0xFF, (ITEM_STUB_A >> 8) & 0xFF, 0xEA])),
    (0xC0DD1D, bytes.fromhex("C906F004"), bytes([0x4C, ITEM_STUB_B & 0xFF, (ITEM_STUB_B >> 8) & 0xFF, 0xEA])),
    # 글줄 출력기 `$C0:9395` 끝(`$C0:9454`): 전각 글자(12px)가 8px 타일에 걸쳐 쌓이므로 줄 끝에 **4px 짜리 불완전 타일**(`$1323`=1)이 남으면 그 타일을 버렸다 —
    # 줄 끝에 반각 공백을 둔 원본은 안 보이던 결함이고, 정본 표기 15B 이름(92px = 11타일 + 4px)은 마지막 글자 절반이 잘린다. 끝에서 `$1358` 을 하나 올려 그 타일도 내보낸다.
    (0xC09454, bytes.fromhex("AD9F118D9C11"), bytes([0x22, FLUSH_STUB & 0xFF, (FLUSH_STUB >> 8) & 0xFF, FLUSH_STUB >> 16, 0xEA, 0xEA])),
    (FLUSH_STUB, b"\xff" * len(_FLUSH), _FLUSH),
    # 목록·장비 창 셋(`$C0:D916` 4줄 · `$C0:DA7E` 7줄 · `$C0:DF23` 필드 사용)의 폭을 한 칸 넓힌다 — 이름 12타일이 오른쪽 테두리에 안 겹치게
    (0xC0D918, bytes([0x0B]), bytes([0x0C])),
    (0xC0DA80, bytes([0x0B]), bytes([0x0C])),
    (0xC0DF25, bytes([0x0B]), bytes([0x0C])),
    # 장비 창 이름 복사(`$C0:D7BF` 계열 넷)는 복사 앞에 `$120F` 를 반각 공백으로 덮는다 — 끝 토큰 `06` 자리를 지우려는 것이나, 15B 이름은 그 자리가 마지막 글자 하위 바이트다(깨진 글자 「壁」).
    # 덮기를 없앤다: 짧은 이름이면 `06` 이 줄에 복사되지만 출력기는 `$18` 미만 제어 바이트를 건너뛴다.
    (0xC0D7F0, bytes.fromhex("A9208D0F12"), b"\xea" * 5),
    (0xC0D835, bytes.fromhex("A9208D0F12"), b"\xea" * 5),
    (0xC0D87A, bytes.fromhex("A9208D0F12"), b"\xea" * 5),
    (0xC0D8BF, bytes.fromhex("A9208D0F12"), b"\xea" * 5),
    (ITEM_STUB_A, b"\xff" * len(_STUB_A), _STUB_A),
    (ITEM_STUB_B, b"\xff" * len(_STUB_B), _STUB_B),
]

# 세이브·로드 목록 줄 열 맞춤(마스터 10-13 「1 서장 L 1 E 레벨…」) — 슬롯 번호 · 장 라벨 · L 레벨 · E · EP 7자리 · 지명을 한 칸씩 띄운다.
# 줄 버퍼 `$7F:CD28`(35B, +0 = `1F`): +1 슬롯 · +3~6 장 라벨(2칸 4B) · +8 `L` · +9~10 레벨 · +12 `E` · +13~19 EP 7자리 · +20 공백 · +21~ 지명(6자 12B 까지).
# 반각 한 칸 8px · 전각 12px · 줄 한도 224px: 8+8+24+8+8+16+8+8+56+8 = 152px → 지명 72px(6자) 딱 맞음. EP 7자리는 원판이 7번째 자리를 `E` 칸에 덮어 쓰던 것을 칸을 따로 둔 것.
PATCHES += [
    (0xCB69A2, bytes([0x2A]), bytes([0x2B])),  # 장 라벨 복사 목적지 `$CD2A` → `$CD2B`(+3)
    (0xCB69A5, bytes([0x05]), bytes([0x03])),  # 장 라벨 복사 길이 6B → 4B(`mvn` A = 길이-1)
    (0xCB69D1, bytes([0x32]), bytes([0x31])),  # 레벨 십의 자리 `$CD32` → `$CD31`(+9)
    (0xCB69D8, bytes([0x33]), bytes([0x32])),  # 레벨 일의 자리 `$CD33` → `$CD32`
    (0xCB69DE, bytes([0x31]), bytes([0x30])),  # `L` `$CD31` → `$CD30`(+8)
    # EP: 원판은 `$1B2D|$1B2E` 가 비면 `E`(`$CD35`) 아니면 7번째 자리 숫자를 그 칸에. → `E` 는 `$CD34`, 7번째 자리(`$1B2E`)는 `$CD35`(숫자 여섯은 원래대로 `$CD36~3B`)
    (0xCB6A9F, bytes.fromhex("AD2D1B0D2E1BC920F009AD2E1B8F35CD7F8006A9458F35CD7F"),
     bytes.fromhex("AD2E1B8F35CD7FA9458F34CD7F") + b"\xea" * 12),
    # 🔴 줄이 224px(28타일)를 넘으면 출력기가 넘친 타일을 다음 타일 줄 자리(+28)에 써서 아랫 타일이 깨진다(둘째·셋째 줄 슬롯 번호). 원판은 지명 뒤에 반각 공백(8px)을 달고 끝 표시를 썼는데 6자 지명이면 224px 를 4px 넘는다.
    # 지명 복사 루프(`$CB:6A34~51`)를 고쳐 ① 지명 뒤 공백을 없애고(끝 표시만) ② 12B(6자)에서 자른다 — 7자 길 이름(큐베라～프로스)은 끝 글자가 빠진다.
    (0xCB6A34, bytes.fromhex("B7ACC920D00280 08E89F3CCD7FC880F0E8A9209F3CCD7FE8A9009F3CCD7F".replace(" ", "")),
     bytes.fromhex("B7ACC920F00AE89F3CCD7FC8E00CD0F0E8A9009F3CCD7F") + b"\xea" * 7),
]

# 오프닝 둘째 쪽 「넘치는 애정 속에 자라 15세가 되었다.」 가 한 줄 한도 216px 를 넘어(232px) 둘로 나눈다(마스터 10-13, 규칙 3-6: 문안은 그대로 · 줄을 나눈다).
# 줄 스크립트 `$C1:CD3D`(값 = 줄 세로 칸, `02` = 빈 줄) 의 그 줄 바로 아래 빈 칸(`02`)을 줄 번호 `$14`(= 20)로 바꾸고, 그 칸의 문자열 포인터는 `opsplit.json` 이 새 문자열로 돌린다.
# 오프닝 줄 스크립트 `$C1:CD3D`(68B) — ① `$C1:CD51`(둘째 쪽 15세 줄 아래 빈 칸 `02` → `$14`) ② 쪽마다 글 덩어리를 **세로 가운데**로 옮긴다(마스터 10-14 「세로로도 중앙에 와야할듯」).
# 원판은 쪽마다 손으로 세로 위치를 잡았고 위로 1~2칸 치우친다(위 여백 4~8 · 아래 여백 6~10칸). 우리는 글 줄(빈 칸 `02` 제외) 첫 행~끝 행(+2) 높이 H 로 위 여백 ≈ (28 − H)/2 칸에 맞춘다(28 = 화면 224px).
# 짝수 칸만 쓴다 — 홀수 칸(반 줄 단위)으로 옮기면 쪽이 통째로 안 그려졌다(시험 10-14). 그래서 위 여백은 짝수로 내린다(동률이면 위쪽): 4쪽만 4→6 으로 내려가고 나머지는 원판과 같은 자리다.
# 이 쪽의 `02` 는 행 번호가 아니라 빈 줄 표시이므로 건드리지 않고, 빈 문자열 칸(쪽 끝 표시 포함)의 행은 쪽과 함께 같은 만큼 옮긴다. 0 = 쪽 끝 · 1 = 스크립트 끝.
PATCHES += [
    (
        0xC1CD3D,
        bytes.fromhex("0406020a0c021012140218000406020a0c02101202160006080a020e10120216000406020a0c0e1012021600080a020e1002140006080a0c0e1002141600080a0c021001"),
        bytes.fromhex("0406020a0c021012140218000406020a0c02101214160006080a020e10120216000608020c0e101214021800080a020e1002140006080a0c0e1002141600080a0c021001"),
    ),
]

# 낱말 단위 줄바꿈(마스터 10-21 「전투 줄바꿈은 구조로」) — 메시지 출력기는 줄 폭을 넘으면 **글자 가운데서** 끊는다(「회복되/었다」). 정적 조판은 이름·숫자 같은 런타임 변수가 앞에 붙는 조각의 앞 줄 폭을 모른다.
# 출력기 반각 글자 길(`$C0:A894 jmp $A96C`)에 끼어, 공백(`$20`) 앞에서 **뒤따르는 낱말**의 폭(전각 3 · 반각 2 단위, 사전·함수·제어 토큰에서 멈춤)을 앞질러 읽고
# 지금 줄 폭(`$1B13`) + 공백 2 + (마지막 글자를 뺀) 낱말 폭이 52 이상이면 공백을 찍지 않고 줄바꿈(`$C0:AEB6`)한다 — 출력기는 글자를 **찍은 뒤** 폭 ≥ 52 에서야 끊으므로 낱말의 마지막 글자는 52 를 넘어도 한 줄에 든다. 낱말이 없으면(공백 뒤가 곧 제어 토큰) 그대로 찍는다. 정적 조판이 이미 맞춘 줄은 이 조건이 안 걸린다.
WRAP_STUB = 0xC0FD00
_WRAP = bytes.fromhex("c920f0084c6ca9a9204c6ca9ad131bf0f65aa20000b7a6c8c9219024c9809019c988900cc9e09011c9f0b014c9e29010c8e8e8e8a903eb80dce8e8a902eb80d57a8af0c3eb488a38e301830168186d131b6902c93490b05a20b6ae7a60")
PATCHES += [
    (0xC0A894, bytes([0x4C, 0x6C, 0xA9]), bytes([0x4C, WRAP_STUB & 0xFF, (WRAP_STUB >> 8) & 0xFF])),
    (WRAP_STUB, b"\xff" * len(_WRAP), _WRAP),
]

EXCEPT = [(common.snes2off(a), common.snes2off(a) + len(n)) for a, _o, n in PATCHES]
FONT_OUT = common.snes2off(FONT_BANK << 16)


