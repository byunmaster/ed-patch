"""전투 로그 런타임 어절 줄바꿈 훅 (마스터 10-18 「로그성 메시지는 개행 없이 엔진이 어절 단위로」 · 공통 규칙 09-30).

엔진 현황(실측 10-18 · 코드 읽기): 글자 단위 줄넘김만 있다 — 글리프 그리기 직전 `$67CC`(뱅크 0x6C)가 `x+폭 > 2*$79-1` 이면 줄을 넘긴다. 어절 개념도, 앞을 미리 보는 일도 없다.
이름(`13 nn`)은 런타임에 `$E78E` 버퍼로 펼쳐져 폭을 빌드 때 알 수 없다 → 줄 폭을 빌드가 박던 지금 방식은 긴 이름에서 틀린다.

훅 둘(뱅크 0x71, 텍스트 해석기 `$672F` 가 있는 뱅크 — 마운트 `$6000`):
  ① 공백(`60`) 처리 `$675C: JMP $688C` — 공백 뒤 다음 어절의 폭을 스트림에서 미리 읽어, 공백까지 넣으면 줄 끝(`$79*2-1`)을 넘으면 공백 대신 줄 넘김(`$4812`+`$6806` = `0D` 와 같은 길).
  ② 이름 펼침 끝 `$6948: LDA #$8E; STA $7C` — 이어질 글의 포인터는 소프트웨어 스택에서 읽는다(이 시점 `$7C` 는 이미 이름 쪽). 버퍼 `$E78E` 의 이름 폭 + 이름 뒤에 붙은 글자(조사 등)의 폭이 줄에 안 들어가면 이름 앞에서 줄을 넘긴다(이름이 어절 첫머리일 때 — 바로 앞 공백은 줄 끝에 남아 안 보인다).
**켜는 조건**: 스트림이 작업 버퍼(`$30E5`~, 메시지 복사본)이고 창이 전투 로그 창(`LOG_WIN`)일 때만 — 메뉴·대사의 공백 정렬은 그대로다.
  ⚠ 문장에 표지 제어를 끼우는 안은 안 된다(실측 10-18): 메시지 복사가 `17` 을 `15 04`(붉은색 시작)로 펼치고, `1F` 는 뒤 글자를 깨뜨린다 — 제어 바이트는 엔진이 건드리지 않는 칸이 없다 — 대사·메뉴의 공백 정렬은 그대로다(표지는 빌드가 전투 로그 문장에만 붙인다).
폭 단위 = 4px(글리프 3 · ASCII 한 바이트 2 · 공백 `60` 1 · 색·속성 제어 0). 어절 끝 = `60`·`00`·`0D`·`12`·이름(`13`)·그 밖의 제어.
스크래치 = 영 페이지 `$EC~$EF`(글리프 훅과 같은 자리 — 글리프를 그리는 동안엔 안 쓴다). 레지스터는 A·X 만 건드린다(호출자가 `$2C` 를 다시 읽는다).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asm
import layout

BANK = 0x71
CODE_OFF = 0x13FB  # 뱅크 0x71 의 0xFF 패딩(3,077B) 머리 — 마운트 `$73FB`
ORG = 0x6000 + CODE_OFF
SPACE_SEAM = 0x075D  # `$675C: JMP $688C` 의 피연산자
SPACE_OLD = bytes([0x8C, 0x68])
NAME_SEAM = 0x0948  # `$6948: LDA #$8E; STA $7C`(4B) → `JSR 훅; NOP`
NAME_OLD = bytes([0xA9, 0x8E, 0x85, 0x7C])
LOG_WIN = (2, 0x11, 0x16, 9)  # 전투 로그 창 `$77/$78/$79/$7A`(좌표 x·y · 폭 · 높이, 타일) — 실측 10-18
BUF = 0x30E5  # 작업 버퍼 — 메시지 문자열이 복사되는 자리

READ = 0x5021  # 스트림 한 바이트 읽기(A 로, `$7C/$7D` 전진)
LONGCALL = 0x4812  # `JSR $4812; BIT <대상>` = 뱅크 0x6C 의 대상 호출 규약
NEWLINE_TARGET = 0x6806  # 뱅크 0x6C — `0D` 처리(줄 머리면 아무것도 안 한다)
SPACE_ORIG = 0x688C
NAME_BUF = 0xE78E
LINE_START = 0x30DD
SSP, SSTACK = 0x8C, 0xEA04  # 소프트웨어 스택 포인터(영 페이지) · 바닥
PTR, WID, LIM = 0xEC, 0xEE, 0xEF  # $EC/$ED = 저장한 스트림 포인터


def _routine() -> asm.Asm:
    a = asm.Asm(ORG)

    def save_ptr():
        a.op("LDA", "zp", 0x7C)
        a.op("STA", "zp", PTR)
        a.op("LDA", "zp", 0x7D)
        a.op("STA", "zp", PTR + 1)

    def load_ptr():
        a.op("JSR", "abs", "lptr")

    # --- 켜짐 판정: C=0 켬 · C=1 끔 — 창이 전투 로그 창일 때만
    a.label("gate_win")
    a.op("LDX", "imm", 3)
    a.label("gw")
    a.op("LDA", "absx", 0x2077)
    a.op("CMP", "absx", "WIN")
    a.op("BNE", "rel", "gno")
    a.op("DEX")
    a.op("BPL", "rel", "gw")
    a.op("CLC")
    a.op("RTS")
    a.label("gno")
    a.op("SEC")
    a.op("RTS")
    # 스트림이 작업 버퍼($30xx~$31xx)일 때만 — 공백 훅은 지금 포인터 `$7D`
    a.label("gate")
    a.op("LDA", "zp", 0x7D)
    a.label("gate_hi")  # A = 스트림 포인터 상위 바이트 — 스트림이 작업 버퍼든 롬 문자열이든(플레이어 공격 로그 「…에게 11의 피해!!」는 롬 문자열이다 — qa 10-20) 창이 전투 로그 창이면 켠다
    a.op("BRA", "rel", "gate_win")

    a.label("lptr")  # 저장한 스트림 포인터를 되돌린다
    a.op("LDA", "zp", PTR)
    a.op("STA", "zp", 0x7C)
    a.op("LDA", "zp", PTR + 1)
    a.op("STA", "zp", 0x7D)
    a.op("RTS")

    # --- 어절 폭: 스트림 `$7C` 에서 어절 끝까지 읽어 `$EE` 에 더한다(포인터는 전진 — 호출자가 저장·복원)
    a.label("scan")
    a.label("s_next")
    a.op("JSR", "abs", READ)
    a.op("CMP", "imm", 0x00)
    a.op("BEQ", "rel", "s_end")
    a.op("CMP", "imm", 0x60)
    a.op("BEQ", "rel", "s_end")
    a.op("CMP", "imm", 0x20)
    a.op("BCC", "rel", "s_ctrl")
    a.op("CMP", "imm", 0x80)
    a.op("BCC", "rel", "s_asc")
    a.op("CMP", "imm", 0xA0)
    a.op("BCC", "rel", "s_two")
    a.op("CMP", "imm", 0xE0)
    a.op("BCC", "rel", "s_one")
    a.label("s_two")  # 2바이트 글리프 — 트레일을 읽어 넘긴다
    a.op("JSR", "abs", READ)
    a.label("s_one")
    a.op("LDA", "imm", 3)
    a.op("BRA", "rel", "s_add")
    a.label("s_asc")  # ASCII 한 바이트(반각 부호 · 숫자) = 8px = 2 단위
    a.op("LDA", "imm", 2)
    a.label("s_add")
    a.op("CLC")
    a.op("ADC", "zp", WID)
    a.op("STA", "zp", WID)
    a.op("BRA", "rel", "s_next")
    a.label("s_ctrl")
    a.op("CMP", "imm", 0x0D)
    a.op("BEQ", "rel", "s_end")
    a.op("CMP", "imm", 0x04)
    a.op("BCC", "rel", "s_end")  # 00~03
    a.op("CMP", "imm", 0x08)
    a.op("BCC", "rel", "s_next")  # 04~07 = 속성(폭 0)
    a.op("CMP", "imm", 0x0E)
    a.op("BEQ", "rel", "s_next")
    a.op("CMP", "imm", 0x0F)
    a.op("BEQ", "rel", "s_next")
    a.op("CMP", "imm", 0x14)
    a.op("BEQ", "rel", "s_next")
    a.op("CMP", "imm", 0x15)
    a.op("BEQ", "rel", "s_15")
    a.op("CMP", "imm", 0x1E)  # 1E nn — 수 자리표(런타임에 자릿수가 정해진다): 어림 4자리(8단위)로 재서 어절이 줄 끝을 넘을 때 앞에서 줄을 넘긴다(qa 10-20 「…11의 피해 / !!」)
    a.op("BNE", "rel", "s_end")
    a.op("JSR", "abs", READ)
    a.op("LDA", "imm", 8)
    a.op("BRA", "rel", "s_add")
    a.label("s_15")
    a.op("JSR", "abs", READ)  # 15 nn — 인자 하나
    a.op("BRA", "rel", "s_next")
    a.label("s_end")
    a.op("RTS")

    # --- 넘치나: A = 한계 → C=1 이면 `x + 폭 ≥ 한계`
    a.label("fit")
    a.op("STA", "zp", LIM)
    a.op("LDA", "zp", 0x73)
    a.op("CLC")
    a.op("ADC", "zp", WID)
    a.op("CMP", "zp", LIM)
    a.op("RTS")

    a.label("newline")  # `0D` 와 같은 호출 — 뒤따르는 BIT 는 규약의 일부(호출 규약이 반환 주소의 BIT 피연산자를 읽는다)
    a.op("JSR", "abs", LONGCALL)
    a.data(bytes([0x2C, NEWLINE_TARGET & 0xFF, NEWLINE_TARGET >> 8]))
    a.op("RTS")

    # --- 훅 ① 공백
    a.label("space")
    a.op("JSR", "abs", "gate")
    a.op("BCS", "rel", "sp_orig")
    a.op("LDA", "zp", 0x73)
    a.op("CMP", "abs", LINE_START)
    a.op("BEQ", "rel", "sp_orig")  # 줄 머리의 공백은 그대로
    save_ptr()
    a.op("STZ", "zp", WID)
    a.op("JSR", "abs", "scan")
    load_ptr()
    a.op("LDA", "zp", 0x79)
    a.op("ASL")
    a.op("DEC")  # 한계 = 2*$79-1
    a.op("JSR", "abs", "fit")
    a.op("BCC", "rel", "sp_orig")
    a.op("JSR", "abs", "newline")  # 공백 대신 줄 넘김
    a.op("RTS")
    a.label("sp_orig")
    a.op("JMP", "abs", SPACE_ORIG)

    # --- 훅 ② 이름 펼침 끝 — 이 시점 `$7C/$7D` 는 이미 이름 쪽이고, 이어질 글의 포인터는 소프트웨어 스택(`$EA04,X` — `$4FED` 가 `$7D $7C $2C0B $2C07` 순으로 밀어 둔다)의 맨 위 넷에 있다
    a.label("name")
    a.op("LDX", "zp", SSP)
    a.op("LDA", "absx", SSTACK - 4)  # 이어질 글 포인터 상위
    a.op("STA", "zp", PTR + 1)
    a.op("LDA", "absx", SSTACK - 3)  # 하위
    a.op("STA", "zp", PTR)
    a.op("LDA", "zp", PTR + 1)
    a.op("JSR", "abs", "gate_hi")
    a.op("BCS", "rel", "nm_done")
    a.op("LDA", "zp", 0x73)
    a.op("CMP", "abs", LINE_START)
    a.op("BEQ", "rel", "nm_done")  # 줄 머리의 이름은 그대로
    a.op("STZ", "zp", WID)
    a.op("LDA", "imm", NAME_BUF & 0xFF)
    a.op("STA", "zp", 0x7C)
    a.op("LDA", "imm", NAME_BUF >> 8)
    a.op("STA", "zp", 0x7D)
    a.op("JSR", "abs", "scan")  # 이름 글자
    load_ptr()
    a.op("JSR", "abs", "scan")  # 이름 바로 뒤에 붙은 글자(조사 · 부호)
    a.op("LDA", "zp", 0x79)
    a.op("ASL")  # 한계 = 2*$79 (공백 없음)
    a.op("JSR", "abs", "fit")
    a.op("BCC", "rel", "nm_done")
    a.op("JSR", "abs", "newline")
    a.label("nm_done")
    a.op("LDA", "imm", NAME_BUF & 0xFF)  # 원래 명령(`LDA #$8E; STA $7C`) — `$7D` 는 원래 코드가 이어서 쓴다
    a.op("STA", "zp", 0x7C)
    a.op("RTS")
    a.label("WIN")  # 로그 창 `$77~$7A`
    a.data(bytes(LOG_WIN))
    return a


def code() -> bytes:
    return _routine().bytes()


def labels() -> dict[str, int]:
    a = _routine()
    a.bytes()
    return a.labels


def reserve(prog: layout.Prog) -> int:
    n = len(code())
    prog.reserve(BANK, CODE_OFF, n)
    return n


def install(prog: layout.Prog) -> None:
    a = _routine()
    b = a.bytes()
    assert prog.o(BANK, SPACE_SEAM, 2) == SPACE_OLD, "공백 이음매 원본 바이트가 다르다"
    assert prog.o(BANK, NAME_SEAM, 4) == NAME_OLD, "이름 이음매 원본 바이트가 다르다"
    prog.put(BANK, CODE_OFF, b, "wrap routine")
    prog.put(BANK, SPACE_SEAM, a.labels["space"].to_bytes(2, "little"), "wrap seam space $675C")
    prog.put(BANK, NAME_SEAM, bytes([0x20]) + a.labels["name"].to_bytes(2, "little") + bytes([0xEA]), "wrap seam name $6948")
