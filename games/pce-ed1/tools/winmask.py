"""창 맨 위 장치(11-19 통합 — 뱅크 0x73 꼬리)

창 맨 위 규칙(마스터 11-19 「창이 떠 있으면 창 영역은 늘 맨 위」) — 상주 **창 사각형 표** 하나 + SAT 스텁 하나. 씬 57 어둠 원 개별 스텁(옛 `dark_sat.py`)을 일반 장치로 갈아끼웠다. 전부 뱅크 0x73 꼬리 FF 1280B — 마스터 상태 31개 FF 그대로 + 쓰기 BP 0 히트(devlog)로 선언. 메인 스레드는 먼 호출로, 틱(IRQ)은 MPR3 에 0x73 을 잠깐 걸어 쓴다(트램펄린 영 페이지 충돌).

── 구조(공통부: 엔진 주소를 모르는 부분 / 엔진 의존부: 아래 「PCE II 이식」) ──
· **창 사각형 표**(공통): 슬롯 4개 × 5B `[활성, y0, y1, x0, x1]`(4px 단위, SAT 좌표 = 스크린샷 줄 + 46 · 스크린샷 x + 14 를 4 로 나눈 값 — 11-21 실측, 반열림 구간 `[y0, y1)`·`[x0, x1)`) + 임시 4B.
  슬롯 0 = 시스템 메뉴 · 1 = 목록 팝업 · 2 = 대사·자막 창 · 3 = 그 밖(상점·전투·디버그). 활성 = 1 · 2(2 = 통째로 창 안인 스프라이트만 뒤로 — 메뉴) · 0 이면 꺼짐(이 영역은 이미지에서 0 으로 구워 둔다).
· **SAT 스텁**(공통): 게임 SAT 루프가 조각마다 **패턴 워드**를 쓰는 8B(`LDA ($FA),Y · STA $0002 · INY · LDA ($FA),Y`, `$6567`)를 `JSR 스텁` + `BRA $6587` 로 바꾼다(11-21 — 옛 자리는
  속성 낮은 바이트 8B `$6579` 였다. 잘린 그림 사본이 패턴까지 바꿔야 해서 앞으로 옮겼다). 스텁이 조각의 남은 네 바이트(패턴 lo/hi · 속성 lo/hi)를 다 쓰고 Y 를 조각 끝으로 올린다.
  **활성 슬롯의 사각형과 한 칸이라도 겹친 스프라이트**(폭·높이 무관)의 우선순위 비트(7)만 끈다 → 스프라이트가 BG 창 타일 뒤로 간다(창 안 투명 칸은 비친다). 창 밖 스프라이트는 그대로.
  스프라이트 위치·크기: `$FC/$FD` = x · `$FE/$FF` = y(SAT 좌표 9비트) · `($FA),Y` = 속성 높은 바이트(비트 0 = 폭 32 · 비트 4·5 = 높이 16/32/64) — 모두 4 로 나눠 8비트로 비교한다.
· **잘린 그림 사본 이음**(엔진 의존 — `sprmask.py`): 어둠 원 개체(종류 0x78~0x81)의 조각은 스텁이 사각형 판정 대신 `sprmask.PRES[남은 조각 수]` 를 본다 — 0 = 옛 판정(폴백) ·
  1 = 창 밖(앞) · 2 = 통째로 창 안(뒤) · 비트 7 = 사본(패턴 워드 `0x100 | 값 & 0x7F`, 앞). 개체의 첫 조각에서 `sprmask.sigchk`(좌표·서술자·창 상태 서명)를 한 번 부르고,
  프레임 후크가 프레임마다 `FLAG` 를 지우고 구울 것이 남았으면(`PCUR`) `sprmask.plan` 을 부른다. 서 있는 동안은 둘 다 일을 안 한다(스텁의 표 조회뿐).
· **등록·해제**(공통 루틴): `win_*` 루틴을 엔진 쪽 창 열기·닫기 지점에서 `JSR` 로 부른다(슬롯 값만 쓴다).

── PCE II 이식 시 바꿀 곳(엔진 의존부) ──
 ① 스텁을 거는 자리 = 게임 SAT 루프의 속성 쓰기(`SITE_*`; PCE II 에서는 같은 일을 하는 루프를 찾아 8B 대체) · 스프라이트 변수 주소(`$FC~$FF`·`($FA),Y`·`$36E9,X`·`$F9`)
 ② 표·스텁이 사는 자리(여기서는 뱅크 0x73 꼬리 = 표도 스텁 창에 같이 있어 스텁이 뱅크를 안 바꾼다; `$C000`(뱅크 0x74)은 SAT 루프 때 MPR6=0x6A 라 못 쓴다 — 실측)
 ③ 창 열기·닫기 후크 자리(창 종류마다 엔진 코드가 다르다) — 이 파일의 `win_*` 호출만 박으면 된다.
 공통부(표 형식·겹침 판정·`win_*`)는 그대로 쓴다.
"""

import hook
import sprmask

BANK = 0x73  # 표 + 등록 루틴 + SAT 스텁 전부 — 뱅크 0x73 꼬리 FF 1280B(`freespace.BANK73_TAIL`). 호출은 전부 먼 호출 → `$8000` 창
WINDOW = 0x8000
TAIL_OFF = 0x1B00  # 뱅크 안 오프셋(원판 FF 꼬리 시작)
TAIL_LEN = 0x2000 - TAIL_OFF
NSLOT = 4
SLOT_B = 5
TBL = WINDOW + TAIL_OFF
TMP = TBL + NSLOT * SLOT_B  # 임시 tY·tX·tW·tH·d4
TBL_LEN = NSLOT * SLOT_B + 5
REG_ORG = TBL + TBL_LEN
REG_LEN = 221  # 사이트 8B 둘 + 등록 루틴들 + 프레임 후크 + d4·htab 길이 이상(실제 220B — 11-22 뱅크 끝 인터럽트 벡터 사본 6B + 그 뒤 못 쓰는 4B + 어절 판정 1B 를 내느라 232 에서 조였다)
STUB_BANK = BANK
STUB_ORG = REG_ORG + REG_LEN
STUB_OFF = STUB_ORG - WINDOW
STUB_LEN = 280  # 스텁 길이 이상
TOTAL_LEN = TBL_LEN + REG_LEN + STUB_LEN  # 뱅크 0x73 꼬리에서 쓰는 몫
assert TOTAL_LEN == 526  # 🔴 뒤에 `musicresume`(→ 어절 판정 → `sprmask` 데이터)가 바로 붙는다 — 몫을 늘리면 이웃이 다 밀린다

SITE_BANK = 0x69
# 조각마다 패턴 번호를 쓰는 머리(`$6567`): `LDA ($FA),Y · STA $0002 · INY · LDA ($FA),Y`(8B) — 여기서 스텁으로 넘어가 패턴·속성 네 바이트를 스텁이 다 쓰고 `$6587`(조각 루프 끝)로 건너뛴다.
# (11-21 까지는 속성 쓰기 `$6579` 8B 였다 — 어둠 원 조각의 **패턴 번호**를 사본으로 바꾸려면(`sprmask`) 패턴을 쓰기 전에 잡아야 한다)
SITE_OFF = 0x0567
SITE_OLD = bytes.fromhex("b1fa8d0200c8b1fa")
SITE_SKIP = 0x18  # 먼 호출 6B 뒤 `BRA +$18` → `$6587`
SITE_WINDOW = 0xA000 + SITE_OFF  # SAT 루프를 도는 동안 뱅크 0x69 는 MPR5(`$A000`)에도 걸려 있다(실측: MPR3=MPR5=0x69) — 먼 호출은 MPR3·MPR4 만 바꾼다
# SAT 루프 함수 머리(`$6491`): `LDA #0 · STA $F7 · ST0 #0` 6B → 프레임 후크 먼 호출
FH_OFF = 0x0491
FH_OLD = bytes.fromhex("a90085f70300")

SLOT_MENU, SLOT_LIST, SLOT_DLG, SLOT_ETC = 0, 1, 2, 3
# 틱(IRQ) 쪽 코드(gwin_rt)는 먼 호출(트램펄린이 영 페이지 `$35~$3B` 를 써 인터럽트로 끊긴 메인 스레드의 먼 호출을 망친다)을 못 쓴다 → MPR3(`$6000`)에 뱅크 0x73 을 잠깐 걸고 같은 자리를 `$6000` 창 주소로 쓴다
TICK_MPR = 3
TICK_SHIFT = 0x6000 - WINDOW

# 대사·자막 창 사각형 — 4px 단위(SAT y = 스크린샷 줄 + 46 — 11-21 실측, 그전 주석의 +47 은 한 줄 어긋난 값). 아래 창 = 스크린샷 줄 130~209(틀 포함), 위 창 = 줄 54~133.
# x 는 창 틀 안쪽만(마스터 11-20 「횃불 원 좌우 옆이 평평해져」 — x 전체로 두면 창 옆 칸 밖의 원 조각까지 BG 뒤로 갔다). 🔴 화면 왼쪽·오른쪽 장식 테두리 스프라이트(HUD 틀, SAT x 32~48·224~240, 폭 16 3조각씩)는 창 높이와 겹쳐도 가리지 않는다 —
# 가리면 BG 뒤로 가 맵이 테두리 자리에 비친다(마스터 11-20 「음성 이벤트마다 왼쪽 테두리에 맵이 비침」, 베르가·갇힌 사람·라이아스·아크담). 그래서 x 는 [12, 56) = SAT 48~224(왼쪽 테두리 조각 끝 48, 오른쪽 시작 224)
DLG_BOTTOM = (45, 90, 12, 56)  # y0=45(SAT 180 = 스크린샷 줄 134, 아래 창 윗 경계) · y1=90(넉넉히 화면 아래). 🔴 11-23 전엔 44(줄 130)라 창 바로 위 줄 130~133 에 발이 걸친 인물이 통째로 BG 뒤로 갔다(위 창 y1 과 같은 문제)
DLG_TOP = (25, 44, 12, 56)  # SAT 100~175(줄 54~129). 🔴 y1 을 창 끝(줄 133 → 45)이 아니라 44 로 — 창 밖 아래에 선 파티 머리가 줄 130~133 에 걸쳐 겹침으로 잡히면 통째로 BG 뒤로 가 사라졌다(마스터 11-23 씬 168 베라미스, 45 에서도 사라짐·44 에서 보임. 투명 줄이라 창 틀 위로 비치지 않는다)
# 시스템 메뉴(주문·사용·장비…) — 실화면(스크린샷 341×232) 창 (34,50)~(98,178) 을 SAT 단위로: **SAT y = 줄 + 46 · SAT x = 스크린샷 x + 14**(스크린샷 왼쪽 18px 은 가장자리 — 커서 조각 SAT x 52~108 이
# 창 안 하늘색 상자 x 38~95 와 겹치고, 주인공 SAT x 112 가 스크린샷 x 98 에 서는 것으로 보정, 11-21). 🔴 처음엔 x 에 +32 를 썼다 — 창이 18px 오른쪽으로 잡혀 창 밖 오른쪽 가장자리에 선 주인공이 「창 안」으로 판정돼 BG 뒤로 가 **통째로 사라졌다**(마스터 11-21 「원본은 주인공이 겹쳐도 사라지지 않아」 · 원판 SAT 주인공 조각 속성 `9B`(우선순위 1) vs 제품 `1B`). 아래·오른쪽 끝은 내림(넘치면 창 밖 스프라이트까지 BG 뒤로 가 바닥이 드러난다)
MENU_RECT = (25, 56, 12, 28)

# 원판 `$623E`/`$6253`(뱅크 0x6A — 파티 두 개체 `$379B`·`$379C` 의 우선순위 비트 끄기/켜기)을 통째로 이 뱅크로 옮긴다. 🔴 이건 「메뉴 열기」가 아니라 「파티 우선순위 끄기」다 — 버린다 처리기·전투 끝 복귀도 부른다.
# 그래서 슬롯 0(메뉴 사각형)은 여기서 안 켠다(11-21 — 켰더니 버린다 목록·확정 화면에서 메뉴 열이 없는데 사각형이 살아 원 조각이 189px 빠졌다). 켜는 곳은 메뉴 열을 실제로 그리는 `menu_top`, 끄는 곳은 `menu_hide`·`menu_close`
ENG_BANK = 0x6A
ENG_OPEN_OFF, ENG_CLOSE_OFF = 0x23E, 0x253  # `$623E` · `$6253`
# 메뉴 본 루프(뱅크 0x6E `$6000~`): `$6016` JSR $5D41·JSR $5BA3(6B, 열 그리기) · `$607E` JSR $5D41·LDA #0·STA $12(7B, 항목 고른 뒤 열 걷기)
LOOP_BANK = 0x6E
LOOP_TOP = (0x16, bytes.fromhex("20415d20a35b"))
LOOP_HIDE = (0x7E, bytes.fromhex("20415da9008512"))
ENG_ROUT_OLD = (bytes.fromhex("ae9b371e593518"), bytes.fromhex("ae9b371e593538"))  # 각 루틴 머리 7B(LDX · ASL · CLC|SEC)


def _site_stub_far() -> bytes:
    """사이트에 심는 스텁 먼 호출 8B(`JSR $4FD8` + 인자 뱅크 + 스텁 주소 + `BRA $6587`)."""
    return b"\x20\xd8\x4f" + bytes([STUB_BANK - 0x68 - 1]) + STUB_ORG.to_bytes(2, "little") + bytes([0x80, SITE_SKIP])


def slot_addr(slot: int, field: int = 0) -> int:
    return TBL + slot * SLOT_B + field


_R: dict = {}  # 뱅크 0x74 쪽 라벨(절대 주소) — `_regs()` 를 먼저 만든다


def _stub() -> "hook.Asm":
    _R.update(_regs().labels)
    sp = sprmask.labels()
    a = hook.Asm(STUB_ORG)
    # 진입: X = 개체 · Y = 서술자 색인(패턴 낮은 바이트) · `$33` = 남은 조각 수. 나갈 때: 패턴 lo·hi · 속성 lo·hi 를 썼고 Y += 3, X 그대로
    a.label("stub")
    a.op("LDA", "absx", 0x3559)  # 원판 `$6573` 의 세 명령(우선순위 비트 → `$F9` 비트 7) — 패턴 쓰기보다 먼저 해도 같다(`$F9` 는 조각마다 `STZ`)
    a.op("ASL")
    a.op("ROR", "zp", 0xF9)
    a.op("LDA", "absx", 0x3509)
    a.op("SEC")
    a.op("SBC", "imm", sprmask.RING_KIND0)
    a.op("CMP", "imm", sprmask.RING_KINDS)
    a.op("BCS", "rel", "gen")
    # ── 어둠 원 조각(`sprmask`) — 이 개체를 이번 프레임에 처음 보면 서명 검사(개체가 둘이면 프레임마다 서로 서명을 갈아 치워 늘 폴백) ──
    a.op("TXA")
    a.op("INC")
    a.op("CMP", "abs", sprmask.FLAG)
    a.op("BEQ", "rel", "look")
    a.op("LDA", "imm", sprmask.CODE_BANK)
    a.op("TAM", "tam", 3)  # 먼 호출 트램펄린이 돌아갈 때 MPR3 을 되돌린다
    a.op("JSR", "abs", sp["sigchk"])
    a.label("look")
    a.op("PHX")
    a.op("LDX", "zp", 0x33)
    a.op("LDA", "absx", sprmask.PRES)
    a.op("PLX")
    a.op("CMP", "imm", 0)
    a.op("BEQ", "rel", "gen")  # 아직 모름 — 옛 판정으로
    a.op("BMI", "rel", "copy")
    a.op("CMP", "imm", 2)  # 1 = 앞(C=0) · 2 = 통째로 창 안(C=1)
    a.op("JSR", "abs", "pat_orig")  # (C 를 안 건드린다)
    a.op("LDA", "absx", 0x36E9)
    a.op("BCC", "rel", "fr")
    a.op("JMP", "abs", "clr")
    a.label("fr")
    a.data(b"\x05\xf9")  # ORA $F9
    a.op("JMP", "abs", "attr")
    a.label("copy")  # 사본 — 패턴 워드 = 0x100 | (값 & 0x7F), 우선순위는 원래대로(앞)
    a.op("AND", "imm", 0x7F)
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", 0x0003)
    a.op("INY")
    a.op("INY")
    a.op("LDA", "absx", 0x36E9)
    a.data(b"\x05\xf9")
    a.op("JMP", "abs", "attr")
    # ── 그 밖 스프라이트 — 원래 패턴 + 사각형 판정 ──
    a.label("gen")
    a.op("JSR", "abs", "pat_orig")
    a.op("LDA", "absx", 0x36E9)
    a.data(b"\x05\xf9")  # ORA $F9
    a.op("PHA")
    a.op("PHX")
    a.op("PHY")
    # 커서 스프라이트(종류 0x63~0x67 — 서술자 패턴 0x294~, 메뉴 항목 폭에 따라 3~9조각)는 창에 딸린 것이라 가리지 않는다(마스터 11-20 「커서 반토막」: 창 안에 통째로 든 오른쪽 조각이 BG 뒤로 가 사라졌다)
    a.op("LDA", "absx", 0x3509)
    a.op("SEC")
    a.op("SBC", "imm", 0x63)
    a.op("CMP", "imm", 5)
    a.op("BCS", "rel", "notcur")
    a.op("JMP", "abs", "done")  # `BCC done` 은 분기 범위(±127)를 넘는다
    a.label("notcur")
    # w4 = 4 + 4×(폭 32)
    a.op("LDA", "izpy", 0xFA)
    a.op("AND", "imm", 1)
    a.op("ASL")
    a.op("ASL")
    a.op("ADC", "imm", 4)
    a.op("STA", "abs", TMP + 2)
    # h4 — 높이 코드(비트 4·5): 0 → 4 · 1·2 → 8 · 3 → 16
    a.op("LDA", "izpy", 0xFA)
    for _ in range(4):
        a.op("LSR")
    a.op("AND", "imm", 3)
    a.op("TAX")
    a.op("LDA", "absx", _R["htab"])
    a.op("STA", "abs", TMP + 3)
    # y4 · x4 = (위치 >> 2) — 부분 루틴 d4(A = lo, X = hi → A)
    a.op("LDX", "zp", 0xFF)
    a.op("LDA", "zp", 0xFE)
    a.op("JSR", "abs", _R["d4"])
    a.op("STA", "abs", TMP + 0)
    a.op("LDX", "zp", 0xFD)
    a.op("LDA", "zp", 0xFC)
    a.op("JSR", "abs", _R["d4"])
    a.op("STA", "abs", TMP + 1)
    # 슬롯 순회
    a.op("LDX", "imm", 0)  # (CLX 1B 로 줄이면 121B — cpu65 시뮬레이터가 CLX 를 모른다)
    a.label("next")
    a.op("LDA", "absx", TBL)
    a.op("BEQ", "rel", "skip")
    a.op("CMP", "imm", 2)
    a.op("BEQ", "rel", "inside")  # 활성 값 2 = 「완전히 안쪽」 모드
    a.op("LDA", "abs", TMP + 0)
    a.op("CMP", "absx", TBL + 2)  # y4 < y1
    a.op("BCS", "rel", "skip")  # (안 뛰면 C=0 — 아래 ADC 에 CLC 불필요)
    a.op("ADC", "abs", TMP + 3)
    a.op("CMP", "absx", TBL + 1)  # y4 + h4 > y0
    a.op("BCC", "rel", "skip")
    a.op("BEQ", "rel", "skip")
    a.op("LDA", "abs", TMP + 1)
    a.op("CMP", "absx", TBL + 4)  # x4 < x1
    a.op("BCS", "rel", "skip")
    a.op("ADC", "abs", TMP + 2)
    a.op("CMP", "absx", TBL + 3)  # x4 + w4 > x0
    a.op("BCC", "rel", "skip")
    a.op("BEQ", "rel", "skip")
    a.label("hit")
    a.op("PLY")  # 겹침 — 우선순위 끔
    a.op("PLX")
    a.op("PLA")
    a.label("clr")
    a.op("AND", "imm", 0x7F)
    a.op("BRA", "rel", "attr")
    # 완전히 안쪽 모드 — 스프라이트 전체가 사각형 안(y0 ≤ y4, y4+h4 ≤ y1, x0 ≤ x4, x4+w4 ≤ x1)일 때만 끈다: 창 가장자리에 걸친 큰 스프라이트(어둠 원 조각)는 통째로 BG 뒤로 가 바닥이 드러나므로 그대로 둔다
    a.label("inside")
    a.op("LDA", "abs", TMP + 0)
    a.op("CMP", "absx", TBL + 1)
    a.op("BCC", "rel", "skip")
    a.op("CLC")
    a.op("ADC", "abs", TMP + 3)
    a.op("CMP", "absx", TBL + 2)
    a.op("BEQ", "rel", "in_x")
    a.op("BCS", "rel", "skip")
    a.label("in_x")
    a.op("LDA", "abs", TMP + 1)
    a.op("CMP", "absx", TBL + 3)
    a.op("BCC", "rel", "skip")
    a.op("CLC")
    a.op("ADC", "abs", TMP + 2)
    a.op("CMP", "absx", TBL + 4)
    a.op("BEQ", "rel", "hit")
    a.op("BCC", "rel", "hit")
    a.label("skip")
    a.op("TXA")
    a.op("CLC")
    a.op("ADC", "imm", SLOT_B)
    a.op("TAX")
    a.op("CPX", "imm", NSLOT * SLOT_B)
    a.op("BNE", "rel", "next")
    a.label("done")
    a.op("PLY")
    a.op("PLX")
    a.op("PLA")
    a.label("attr")  # A = 속성 낮은 바이트 · Y = 속성 높은 바이트 색인
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "izpy", 0xFA)
    a.op("STA", "abs", 0x0003)
    a.op("INY")
    a.op("RTS")
    a.label("pat_orig")  # 원래 패턴 번호 두 바이트(사이트에서 치운 명령) — Y += 2, C 그대로
    a.op("LDA", "izpy", 0xFA)
    a.op("STA", "abs", 0x0002)
    a.op("INY")
    a.op("LDA", "izpy", 0xFA)
    a.op("STA", "abs", 0x0003)
    a.op("INY")
    a.op("RTS")
    return a


def _party_prio(a: "hook.Asm", on: bool) -> None:
    """원판 `$623E`/`$6253` 와 같은 일 — 파티 두 개체(`$379B`·`$379C`)의 `$3559,X` 비트 7 을 끄기(on=False)/켜기. 끝에 RTS."""
    for ptr in (0x379B, 0x379C):
        a.op("LDX", "abs", ptr)
        a.op("ASL", "absx", 0x3559)
        a.op("SEC" if on else "CLC")
        a.op("ROR", "absx", 0x3559)
    a.op("RTS")


def _regs() -> "hook.Asm":
    a = hook.Asm(REG_ORG)
    a.label("site_on")  # 프레임 후크가 `TII` 로 사이트에 옮겨 심는 8B 둘(스텁 먼 호출 · 원판)
    a.data(_site_stub_far())
    a.label("site_off")
    a.data(SITE_OLD)
    a.label("dlg_bottom")
    a.op("LDX", "imm", 0)
    a.op("BRA", "rel", "dlg_copy")
    a.label("dlg_top")
    a.op("LDX", "imm", 5)
    a.label("dlg_copy")
    a.op("LDY", "imm", 0)
    a.label("dlg_lp")
    a.op("LDA", "absx", "dlg_rects")
    a.op("STA", "absy", slot_addr(SLOT_DLG))
    a.op("INX")
    a.op("INY")
    a.op("CPY", "imm", SLOT_B)
    a.op("BNE", "rel", "dlg_lp")
    a.op("RTS")
    a.label("dlg_close")
    a.op("STZ", "abs", slot_addr(SLOT_DLG))
    a.op("RTS")
    # 시스템 메뉴 — 열기: 슬롯 0 에 사각형 + 원판 동작(우선순위 끄기) · 닫기: 슬롯 0 끄기 + 원판 동작(켜기)
    a.label("menu_show")  # 슬롯 0 에 메뉴 사각형을 켠다(A·X 파괴)
    a.op("LDX", "imm", 0)
    a.label("mo_lp")
    a.op("LDA", "absx", "menu_rect")
    a.op("STA", "absx", slot_addr(SLOT_MENU))
    a.op("INX")
    a.op("CPX", "imm", SLOT_B)
    a.op("BNE", "rel", "mo_lp")
    a.op("RTS")
    # 🔴 `menu_open`(엔진 `$623E`)은 사각형을 켜지 않는다 — `$623E` 는 「메뉴 열기」가 아니라 **「파티 우선순위 끄기」**라 메뉴 열이 걷힌 뒤에도 불린다(11-21 실측: 「버린다」 처리기가
    # `menu_hide` 뒤에 `$623E` 를 다시 불러 슬롯 0 이 메뉴 열 사각형으로 켜진 채였다 → 열이 걷힌 자리의 조각이 BG 뒤로 가 맵이 드러났다(28px), 사본은 거기를 지웠다(189px)).
    # 열 사각형은 열을 그리는 자리(`menu_top`)만 켠다 — 첫 열기도 `$623E` 바로 뒤에 본 루프 머리(`$6016`)를 지난다
    a.label("menu_open")
    _party_prio(a, False)
    # 메뉴 본 루프(뱅크 0x6E `$6016`) 머리 — 메뉴 열 줄을 (다시) 그리는 `JSR $5D41 · JSR $5BA3` 를 대신한다: 사각형 켜기 + 원래 두 호출
    a.label("menu_top")
    a.op("JSR", "abs", "menu_show")
    a.op("JSR", "abs", 0x5D41)
    a.op("JSR", "abs", 0x5BA3)
    a.op("RTS")
    # 항목을 고른 직후(`$607E`) — 메뉴 열을 걷고(`JSR $5D41`) 부 메뉴로 들어간다: 사각형 끄기 + 원래 `LDA #0 · STA $12`
    a.label("menu_hide")
    a.op("STZ", "abs", slot_addr(SLOT_MENU))
    a.op("JSR", "abs", 0x5D41)
    a.op("LDA", "imm", 0)
    a.op("STA", "zp", 0x12)
    a.op("RTS")
    a.label("menu_close")
    a.op("STZ", "abs", slot_addr(SLOT_MENU))
    _party_prio(a, True)
    # 프레임당 한 번(SAT 루프 함수 머리 — 뱅크 0x69 `$6491` 의 `LDA #0 · STA $F7 · ST0 #0` 6B 를 먼 호출로 대신한다): 창이 하나라도 켜져 있으면 속성 쓰기 사이트를 스텁 먼 호출로, 아니면 원판 8B 로 갈아 끼운다.
    # 스프라이트마다 먼 호출(스텁 ≈ +1줄/스프라이트 — 마스터 11-20 「버린다 뚫림」 지움 Line 여유를 먹었다)을 창이 없는 프레임에선 0 으로. 루프 도중엔 사이트를 안 바꾼다(IRQ 쪽 슬롯 변경은 다음 프레임 머리에서 반영 — 1프레임 늦다)
    a.label("frame_hook")
    # 🔴 사이트는 `$A000` 창(MPR5)으로 고친다 — 이 SAT 함수는 타이틀·파일 선택에서도 돌고 거기선 MPR5 가 다른 뱅크라 그대로 쓰면 엉뚱한 뱅크를 덮어 멈춘다(11-20 실측: 파일 선택 뒤 PC 가 데이터로 빠짐). 0x69 일 때만 바꾼다
    a.op("TMA", "tma", 5)
    a.op("CMP", "imm", SITE_BANK)
    a.op("BNE", "rel", "fh_end")
    a.op("LDA", "abs", slot_addr(0))
    for k in range(1, NSLOT):
        a.op("ORA", "abs", slot_addr(k))
    a.op("BEQ", "rel", "fh_off")
    a.tii(REG_ORG, SITE_WINDOW, 8)
    # 잘린 그림 사본(`sprmask`) — 「이번 프레임에 본 어둠 원 개체」를 지우고, 구울 조각이 남았으면 계획자를 한 번 돌린다(프레임당 `sprmask.BUDGET` 셀 — 다 구우면 PCUR=0 이라 비용 0)
    a.op("STZ", "abs", sprmask.FLAG)
    a.op("LDA", "abs", sprmask.PCUR)
    a.op("BEQ", "rel", "fh_end")
    a.op("LDA", "imm", sprmask.CODE_BANK)
    a.op("TAM", "tam", 3)  # 트램펄린이 돌아갈 때 MPR3 을 되돌린다
    a.op("JSR", "abs", sprmask.labels()["plan"])
    a.op("BRA", "rel", "fh_end")
    a.label("fh_off")
    a.tii(REG_ORG + 8, SITE_WINDOW, 8)
    a.op("STZ", "abs", sprmask.SIG + 5)  # 창이 다 꺼졌다 — 서명을 못 쓰게(서술자 포인터 상위 0 은 없는 값) 해 두면 다음에 창이 뜰 때 처음부터 다시 굽는다
    a.op("STZ", "abs", sprmask.PCUR)
    a.label("fh_end")
    a.op("LDA", "imm", 0)  # 원래 자리의 명령 — `LDA #0 · STA $F7 · ST0 #0`
    a.op("STA", "zp", 0xF7)
    a.op("ST0", "imm", 0)
    a.op("RTS")
    a.label("menu_rect")
    a.data(bytes((2,) + MENU_RECT))  # 활성 2 = 완전히 안쪽 모드
    a.label("dlg_rects")
    a.data(bytes((1,) + DLG_BOTTOM) + bytes((1,) + DLG_TOP))
    a.label("htab")
    a.data(bytes([4, 8, 8, 16]))
    a.label("d4")  # (X:A) >> 2 → A  (X < 4)
    a.op("LSR")
    a.op("LSR")
    a.op("STA", "abs", TMP + 4)
    a.op("TXA")
    for _ in range(6):
        a.op("ASL")
    a.op("ORA", "abs", TMP + 4)
    a.op("RTS")
    return a


def stub_code() -> bytes:
    return _stub().bytes()


def reg_code() -> bytes:
    return _regs().bytes()


def labels() -> dict:
    """절대 주소 — 스텁·등록 루틴·표 모두 뱅크 0x73 `$8000` 창."""
    d = dict(_stub().labels)
    d.update(_regs().labels)
    return d


def table_init() -> bytes:
    return bytes(TBL_LEN)  # 전 슬롯 꺼짐


def site_new() -> bytes:
    """먼 호출(`JSR $4FD8` + 뱅크 + 주소) + `BRA $6587` — 트램펄린은 인자 뱅크를 MPR3 에, 다음 뱅크를 MPR4($8000)에 건다 → 스텁이 $8000 창이면 인자 = 뱅크 − 0x68 − 1."""
    assert labels()["stub"] == STUB_ORG
    return _site_stub_far()


def frame_hook_patch() -> tuple[int, int, bytes, bytes]:
    """(뱅크, 뱅크 안 오프셋, 원판 6B, 새 6B) — SAT 루프 함수 머리를 프레임 후크 먼 호출로."""
    return SITE_BANK, FH_OFF, FH_OLD, far_call("frame_hook")


def rects_addr(top: bool) -> int:
    """대사 창 사각형 5B(`[활성, y0, y1, x0, x1]`)의 `$8000` 창 주소 — 아래 창이 앞, 위 창이 뒤."""
    return labels()["dlg_rects"] + (SLOT_B if top else 0)


def far_call(label: str) -> bytes:
    """등록 루틴을 부르는 먼 호출 6B(`JSR $4FD8` + 인자 + 주소) — A·Y 보존·X 불변(트램펄린), 루틴이 RTS 로 돌아온다."""
    return b"\x20\xd8\x4f" + bytes([BANK - 0x68 - 1]) + labels()[label].to_bytes(2, "little")


def engine_patches() -> list[tuple[str, int, int, bytes, bytes]]:
    """(이름, 뱅크, 뱅크 안 오프셋, 원판 7B, 새 7B) — 엔진 `$623E`/`$6253` 머리를 먼 호출 + RTS 로(남는 뒤쪽 바이트는 죽은 코드로 둔다)."""
    out = []
    for name, off, old in zip(("menu_open", "menu_close"), (ENG_OPEN_OFF, ENG_CLOSE_OFF), ENG_ROUT_OLD):
        out.append((name, ENG_BANK, off, old, far_call(name) + b"\x60"))
    out.append(("menu_top", LOOP_BANK, LOOP_TOP[0], LOOP_TOP[1], far_call("menu_top")))
    out.append(("menu_hide", LOOP_BANK, LOOP_HIDE[0], LOOP_HIDE[1], far_call("menu_hide") + b"\xea"))
    return out
