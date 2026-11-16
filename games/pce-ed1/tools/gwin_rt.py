"""월드를 안 멈추는 **대사창 모양 자막**의 런타임 — 장면 초기화(`JSR $6F7D` 바로 뒤)에서 돈다(마스터 10-12 「b로 해보자」).

대사창은 월드를 멈추는 모달이라 연출과 동시에 못 쓴다(장면 2 실측). 그래서 **엔진 창과 같은 BG 타일**로 BAT 에 창을 직접 그린다(`gwin.py` — 틀 타일 0x500~0x508 은
늘 VRAM 에 있고, 글자는 0x660~0x6AF 기둥 타일). 월드는 장면 초기화가 `$5BCF`(1프레임 대기)로 양보하는 동안 그대로 흐른다(실측: 4초를 그렇게 기다려도 라이아스 컷신이 정상).

  · 매 프레임 창 영역(BAT 열 3~24 · 행 11~20, 220단어)을 읽어 **우리 창이 아니면 그 단어를 「밑그림」에 저장**하고 우리 창으로 다시 쓴다 — 장면 2 는 시작 약 2초에 엔진이
    맵 타일을 그 자리에 그린다(페이드 중). 인사가 끝나면 밑그림을 되돌려 맵이 그대로 남는다.
  · VDC 접근은 `SEI` 로 감싼다(IRQ1 핸들러도 VDC 레지스터를 쓴다). 행 단위로 짧게.
  · 코드·데이터는 전부 씬 블록 꼬리(RAM)에 산다 — 자기 수정(TIA/TAI 피연산자)도 거기서 한다.
"""

import contextlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asm65
import common
import gwin
import hook
import font
import messages as M
import narration_gates as N
import typeset

SPEC = common.GAME_DIR / "script" / "voice_gwin.json"
BASE = M.BASE
FPS = 59.826
CLOCK_F, CLOCK_S = 0xC1B2, 0xC1B3  # 플레이 시계: 초 안 프레임 · 초(하위 바이트)
P_SEL, P_LO, P_HI = 0x0000, 0x0002, 0x0003  # VDC 포트(ST0 = 레지스터 선택)
ROW_BYTES = gwin.W * 2  # 창 한 행 = 22단어 = 44B
RA0 = gwin.ROW0 * 64 + gwin.COL0  # 창 왼쪽 위의 BAT 단어 주소(707)
TOP = False  # 창 위치 — False = 아래(BAT 행 11, 화면 줄 134~213) · True = 위(행 1, 줄 54~133). `use_pos` 가 씬마다 바꾼다
TILE_WORD = gwin.TILE0 * 16  # 글자 타일의 VRAM 단어 주소
DESC = 10  # 쪽 서술: 시작 프레임(2) · 끝 프레임(2) · 타일 수(1)+0 · 타일 압축본 주소(2) · 창 단어 주소(2)
OPS = dict(hook.OPS)
OPS.update({k: v for k, v in asm65.OPC.items() if k[1] not in ("mpr", "blk")})  # 렌더러(안 B)가 쓰는 시프트·색인 명령까지
OPS.update({("CLI", "imp"): 0x58, ("CMP", "absy"): 0xD9, ("DEC", "abs"): 0xCE, ("LDX", "abs"): 0xAE, ("JMP", "indx"): 0x7C, ("TMA", "tma"): 0x43, ("STA", "absy"): 0x99})


class GwinError(Exception):
    pass


class Mini:
    """필요한 명령만 아는 작은 어셈블러 — 피연산자는 숫자 · 라벨 · `라벨+N` · `<라벨`(하위) · `>라벨`(상위)."""

    def __init__(self, org: int):
        self.org, self.out = org, bytearray()
        self.labels: dict[str, int] = {}
        self.fix: list[tuple[int, str, str]] = []

    @property
    def pc(self) -> int:
        return self.org + len(self.out)

    def L(self, name: str):
        self.labels[name] = self.pc

    def op(self, mn: str, mode: str = "imp", arg=None):
        self.out.append(OPS[(mn, mode)])
        if mode == "imp":
            return
        if mode in ("imm", "zp"):
            if isinstance(arg, str):
                self.fix.append((len(self.out), arg, "imm"))
                self.out.append(0)
            else:
                self.out.append(arg & 0xFF)
        elif mode in ("tma", "tam"):
            self.out.append(1 << arg)  # MPR 번호 → 비트
        elif mode == "rel":
            self.fix.append((len(self.out), arg, "rel"))
            self.out.append(0)
        else:  # abs · absx · absy · indx
            if isinstance(arg, str):
                self.fix.append((len(self.out), arg, "abs"))
                self.out += b"\0\0"
            else:
                self.out += arg.to_bytes(2, "little")

    def raw(self, b: bytes):
        self.out += b

    def word(self, label: str):
        """라벨 주소 2B(표용)."""
        self.fix.append((len(self.out), label, "abs"))
        self.out += b"\0\0"

    def val(self, expr: str) -> int:
        m = re.fullmatch(r"([<>]?)([A-Za-z_]\w*)([+-]\d+)?", expr)
        if not m:
            raise GwinError(f"피연산자 {expr!r}")
        v = self.labels[m.group(2)] + int(m.group(3) or 0)
        return v & 0xFF if m.group(1) == "<" else v >> 8 if m.group(1) == ">" else v

    def bytes(self) -> bytes:
        for pos, expr, kind in self.fix:
            if kind == "rel":
                d = self.val(expr) - (self.org + pos + 1)
                assert -128 <= d <= 127, (expr, d)
                self.out[pos] = d & 0xFF
            elif kind == "imm":
                self.out[pos] = self.val(expr) & 0xFF
            else:
                self.out[pos : pos + 2] = self.val(expr).to_bytes(2, "little")
        return bytes(self.out)


RASTER = os.environ.get("ED_GWIN_RC", "ring") != "0"  # "ring"(기본) 핸들러를 늘 매핑된 워크 RAM(RC_RING)에 복사 · "block" 블록 안(MPR5) · "noop" 진단
RC_MODE = os.environ.get("ED_GWIN_RC", "ring")
# 🔴 핸들러는 **늘 매핑된 RAM** 에 있어야 한다 — 블록(MPR5)에 두고 등록했더니 IRQ 가 MPR5 를 바꾼 사이(엔진이 다른 뱅크를 거는 구간)에 떨어져 쓰레기를 실행, VDC 설정이 통째로 깨졌다
#   (10-31 진단: noop 핸들러조차 화면이 회색으로 뭉개짐 · RAM 사본은 정상). 처음엔 LZ 이력 링(`$3F00~$3FFF`, 컨테이너를 풀 때만 쓴다)에 뒀다가
#   11-01 영구 자리로 옮겼다: `$3941~$398F`(79B) — 워크 RAM 전량 덤프 68장 겹치기(ram_map) + 정적 피연산자·블록 전송 스캔에서 참조 0 · 4프레임 간격 27,680표본 전부 0 ·
#   emucap **쓰기 BP**($3941~$398F · $3E46~$3E90) 로 부팅·타이틀·이어하기 ×3 · 씬 6 자막 · 마을·동굴 진입(LZ 풀기) · 메뉴(상태·시스템) · SAVE · 인게임 LOAD · 전투 ·
#   씬 98 자막 1만 프레임 · 씬 18 구역 걷기까지 히트 0. (다른 후보 `$3E46~$3E90` 도 깨끗하나 `$3B00~$3DFF`(마을 재진입 때 튄다)·LZ 링 사이라 안 골랐다.)
RC_RING = 0x3948  # rc1 32B · rc2 = +32 · RC_Y = +64 — 전부 `$3941~$398F` 안. 🔴 창 구간 래스터 고정(10-31 (가)) — 엔진이 걷기 중 맵을 픽셀 단위로 스크롤해(놀이판 BYR 피연산자 `$5932/$5934`, 뱅크 0x6A `$4096` 이 쓴다) BAT 타일 창이 서브타일 위상만큼 같이 흔들린다.
#   엔진 분할 연결표(`$43B4` 더하기 A=줄·X/Y=핸들러, `$43FE` 빼기 X=항목, 매 프레임 `$4360` 이 `$2B09` 로 펼침)에 창 윗줄(119 → 120 부터)·아랫줄(199) 항목을 넣어 창 구간만 BYR 을 타일 정렬값으로.
#   놀이판은 분할 줄 0x1F 뒤 BAT 행 0 이 줄 32 → 창 행 11 = 줄 120. 엔진 HUD 분할(줄 191)이 창 안이라 그 핸들러의 BYR 피연산자(`$594C/$594E`)도 창 윗줄 핸들러가 정렬값으로 덮는다.
RC_TOP = int(os.environ.get("ED_GWIN_RC_TOP", str(32 + gwin.ROW0 * 8 - 1 - 7)))  # 112 — 창 첫 행이 시작하는 줄의 앞 줄. 🔴 11-02 실측(제품 모달 창과 줄 단위 대조): 112 → 창 134~213 = 원판 모달 창과 **같다**(위 가장자리 134, 아래 213). 연결표 줄 L 의 효과: rc1 112 → 화면 134(L+22) · 엔진 HUD 분할 191 → 214(L+23, 핸들러가 길어 한 줄 늦다). 111 로 올리면 한 줄 위(133~212)라 틀린다
RC_F7 = os.environ.get("ED_GWIN_RC_F7", "0") == "1"  # 진단(기각) — `$F7` 을 2 로 강제하면 화면이 깨진다(rcf1). 작업 7 은 `$F7` 을 스스로 유지한다
RC_Y = RC_RING + 64  # $3988 🔴 핸들러가 읽는 창 첫 행 BAT y(rowb×8)의 **RAM 거울** — 블록 변수 `rowb` 를 IRQ 에서 읽으면 작업 7 이 맵 버퍼 뱅크를 MPR5 에 건 사이에 쓰레기를 읽는다(rcf0: 다시 그리는 프레임마다 창이 16px 위로)
PRE_SYNC = os.environ.get("ED_GWIN_PRE_SYNC", "1") == "1"  # 첫 쪽 미리 그리기를 VBlank 에 맞춘다(래스터 분할 지연 방지, 11-04)
PRE_N = int(os.environ.get("ED_GWIN_PRE_N", "4"))  # 프레임마다 도는 틱 분량 수
RC2 = os.environ.get("ED_GWIN_RC2", "0") == "1"  # 창 아랫줄 핸들러(rc2) 등록 — 11-02 부터 기본 꺼짐(창이 HUD 분할 앞에서 끝난다). 진단용
RC_BOT = int(os.environ.get("ED_GWIN_RC_BOT", str(RC_TOP + gwin.H * 8)))  # 199 — 창 아랫줄 핸들러 줄(시험: ED_GWIN_RC_BOT 로 한 줄씩 옮겨 본다, 11-02 Gold 위 흰 줄)
# 🔴 창 아래(줄 200~)는 맵이 아니라 **엔진 HUD 분할(줄 191, `$5938`)이 BYR 를 `$56/$57`(=215) 로 바꿔 그리는 아래 틀·Gold 줄**이다(11-02 마스터 「화면 하단이 잘린다」).
#   엔진은 스크롤이 바뀔 때마다 `$6083`(뱅크 0x6A)이 ZP `$56/$57` 을 `$594C/$594E`(그 핸들러의 ST1/ST2 즉치)에 베낀다. rc1 이 그 즉치를 창 행으로 덮으니 rc2 는 맵 y(V+168)가 아니라
#   **`$56 + (200 − 192)`** 로 되돌려야 하고, 창을 닫을 때 `$594C/$594E` 를 `$56/$57` 로 되돌려야 한다(안 돌리면 엔진이 `$6083` 을 다시 돌릴 때까지 틀이 없다 — 「거의 사라지고 중간중간 복구」).


@contextlib.contextmanager
def pos_ctx(top: bool):
    """`use_pos` 를 구간으로 — 끝나면 이전 위치로 되돌린다(중첩 가능: `patch_block` 안에서 `register_scene`)."""
    prev = TOP
    use_pos(top)
    try:
        yield
    finally:
        use_pos(prev)


def use_pos(top: bool) -> None:
    """씬의 창 위치(위/아래)에 맞춰 위치에 묶인 모듈 상수를 다시 정한다 — 굽기(`program_b`·`register_scene`·`patch_block`·`container_tail`) 앞에서 부른다."""
    global TOP, RA0, RC_TOP, RC_BOT
    TOP = bool(top)
    gwin.set_row0(1 if TOP else 11)
    RA0 = gwin.ROW0 * 64 + gwin.COL0
    RC_TOP = int(os.environ.get("ED_GWIN_RC_TOP", str(32 + gwin.ROW0 * 8 - 1 - 7)))
    RC_BOT = int(os.environ.get("ED_GWIN_RC_BOT", str(RC_TOP + gwin.H * 8)))


HUD_SPLIT = 191  # 엔진 HUD 분할 줄(핸들러 `$5938`, 다음 줄 192 부터 BYR = `$56`)
HUD_BYR_ZP = 0x56  # ZP `$56/$57` = HUD 분할 BYR(실측 215) — `$6083` 이 `$594C/$594E` 로 베낀다
HUD_BYR_OP = 0x594C  # 그 핸들러의 `ST1 #lo` 즉치(`$594E` = `ST2 #hi`)
HUD_ENGINE_COPY = (0x6A, 0x00A0, bytes.fromhex("a5568d4c59a5578d4e59"))  # 뱅크 0x6A `$60A0`: LDA $56 · STA $594C · LDA $57 · STA $594E — 빌드가 원판에서 대조한다
T7_SKIP = os.environ.get("ED_GWIN_T7", "1") == "1"  # 엔진 작업 7(맵 다시 그리기)의 창 자리 쓰기를 건너뛴다 — 깜빡임 원인(10-30 실측)
T7_BANK = 0x6B  # 작업 7 이 사는 본 프로그램 뱅크($8000 창, MPR4)
T7_ROW, T7_LO, T7_HI = 0x9908, 0x9922, 0x993C  # 행 시작 MAWR 상위 `STA $0003` · 타일 하위 `STA $0002` · 상위 `STA $0003` — 3B 씩
T7_OLD = {T7_ROW: bytes([0x8D, 0x03, 0x00]), T7_LO: bytes([0x8D, 0x02, 0x00]), T7_HI: bytes([0x8D, 0x03, 0x00])}
T7_COLS = 0x18  # 행마다 쓰는 단어 수(`$F8` 이 0x18→1 로 줄어든다, 쓰기 뒤에 줄인다) — 행은 열 2 에서 시작한다
T7_COL0 = 2


def t7_stubs(a: "Mini", rt: bool = False):
    """작업 7(`$9822` — `$86` 요청이 서면 BAT 행 0~21 · 열 2~25 를 맵 버퍼로 통째 다시 쓴다, 장면 6 에선 5프레임마다)의 쓰기 셋을 가로챈다.

    창이 보이는 동안(`vis`) 행 시작(`$9908`, MAWR 상위)에서 **한 번** 그 행이 창 행인지 정한다(`rowin` · 밑그림 행 주소). 창 행이 아니면 단어마다
    원래 쓰기 그대로(가볍게 — 처음 판은 단어마다 주소를 셈해 장면이 원판보다 늦어졌다, 10-30 실측). 창 행이면 창 칸(`$F8` = 0x17~2) 단어는
    **VRAM 에 쓰지 않고 밑그림에 저장**하고(창을 닫을 때 되돌아간다), 오른쪽 끝 칸(`$F8` = 1)은 MAWR 를 다시 잡고 쓴다.
    재그리기 동안 IRQ 틱이 MAWR 를 옮기지 않게 행마다 `busy` 를 세운다(틱은 0 이 될 때까지 VRAM 일을 쉰다).
    덮어쓴 뒤 다시 그리는 방식(1/5 프레임 창 없음, 10-30)과 달리 원판 쓰기 자체가 창을 안 덮으므로 깜빡임이 없다. 다른 화면 갱신은 안 건드린다."""
    op, L = a.op, a.L
    sites = ((T7_ROW, "t7row"), (T7_LO, "t7lo"), (T7_HI, "t7hi"))
    L("t7on")  # 메인 스레드(MPR4 = 본 프로그램)에서 — 원판 바이트가 맞을 때만 JSR 로 바꾼다
    op("TMA", "tma", 4)
    op("CMP", "imm", T7_BANK)
    op("BNE", "rel", "t7r")
    for site, _ in sites:
        op("LDA", "abs", site)
        op("CMP", "imm", 0x8D)
        op("BNE", "rel", "t7r")
        op("LDA", "abs", site + 1)
        op("CMP", "imm", T7_OLD[site][1])
        op("BNE", "rel", "t7r")
    for site, lab in sites:
        op("LDA", "imm", "<" + lab)
        op("STA", "abs", site + 1)
        op("LDA", "imm", ">" + lab)
        op("STA", "abs", site + 2)
        op("LDA", "imm", 0x20)  # JSR — 피연산자를 먼저 채운 뒤에 바꾼다
        op("STA", "abs", site)
    L("t7r")
    op("RTS")
    L("t7off")  # 원래대로(우리 JSR 이 걸려 있고 MPR4 가 본 프로그램일 때만)
    op("TMA", "tma", 4)
    op("CMP", "imm", T7_BANK)
    op("BNE", "rel", "t7r")
    op("LDA", "abs", T7_HI + 1)
    op("CMP", "imm", "<t7hi")
    op("BNE", "rel", "t7r")
    for site, _ in sites:
        op("LDA", "imm", 0x8D)
        op("STA", "abs", site)
        op("LDA", "imm", T7_OLD[site][1])
        op("STA", "abs", site + 1)
        op("STZ", "abs", site + 2)
    op("RTS")
    L("t7row")  # A = 행 시작 MAWR 상위 — 원래 쓰기를 하고 이 행을 판정한다
    op("STA", "abs", P_HI)
    op("PHA")
    op("LDA", "imm", 2)
    op("STA", "abs", "busy")
    op("STZ", "abs", "rowin")
    op("LDA", "abs", "ph")  # 끝난 뒤(6) 처음 불리면 원래대로 되돌린다(메인 스레드라 MPR4 가 확실하다)
    op("CMP", "imm", 6)
    op("BNE", "rel", "t7w0")
    op("JSR", "abs", "t7off")
    L("t7w0")
    op("LDA", "abs", "vis")
    op("BEQ", "rel", "t7wx")
    op("LDA", "zp", 0x10)
    op("AND", "imm", 0x3F)
    op("CMP", "imm", T7_COL0)
    op("BNE", "rel", "t7wx")
    op("LDA", "zp", 0x10)  # 행 = 주소 >> 6
    for _ in range(6):
        op("LSR")
    op("STA", "abs", "qt")
    op("LDA", "zp", 0x11)
    op("ASL")
    op("ASL")
    op("ORA", "abs", "qt")
    op("SEC")
    if rt:
        op("SBC", "abs", "rowb")  # 창 첫 행(스크롤에 맞춰 열 때 잡는다)
    else:
        op("SBC", "imm", gwin.ROW0)
    op("CMP", "imm", gwin.H)
    op("BCS", "rel", "t7wx")
    op("PHX")
    if rt:  # 밑그림은 행 고리 — 칸 = (행 + ubase) mod H
        op("CLC")
        op("ADC", "abs", "ubase")
        op("CMP", "imm", gwin.H)
        op("BCC", "rel", "t7r1")
        op("SBC", "imm", gwin.H)
        L("t7r1")
    op("TAX")  # 밑그림 행 주소 = under + 칸×ROW_BYTES → 아래 저장 명령 피연산자
    op("LDA", "imm", "<under")
    op("STA", "abs", "q0")
    op("LDA", "imm", ">under")
    op("STA", "abs", "q1")
    L("t7m")
    op("DEX")
    op("BMI", "rel", "t7m1")
    op("LDA", "abs", "q0")
    op("CLC")
    op("ADC", "imm", ROW_BYTES)
    op("STA", "abs", "q0")
    op("BCC", "rel", "t7m")
    op("INC", "abs", "q1")
    op("BRA", "rel", "t7m")
    L("t7m1")
    op("PLX")
    op("LDA", "abs", "q0")
    op("STA", "abs", "t7s1+1")
    op("LDA", "abs", "q1")
    op("STA", "abs", "t7s1+2")
    op("LDA", "abs", "q0")
    op("CLC")
    op("ADC", "imm", 1)
    op("STA", "abs", "t7s2+1")
    op("LDA", "abs", "q1")
    op("ADC", "imm", 0)
    op("STA", "abs", "t7s2+2")
    op("LDA", "imm", 1)
    op("STA", "abs", "rowin")
    L("t7wx")
    op("PLA")
    op("RTS")
    L("t7lo")  # A = 타일 하위
    op("STA", "abs", "lolatch")
    op("PHA")
    op("LDA", "abs", "rowin")
    op("BNE", "rel", "t7l1")
    op("PLA")
    op("STA", "abs", P_LO)
    op("RTS")
    L("t7l1")
    op("PLA")
    op("RTS")
    L("t7hi")  # A = 타일 상위
    op("PHA")
    op("LDA", "abs", "rowin")
    op("BNE", "rel", "t7h1")
    op("PLA")
    op("STA", "abs", P_HI)
    op("RTS")
    L("t7h1")
    op("LDA", "zp", 0xF8)
    op("CMP", "imm", T7_COLS)
    op("BEQ", "rel", "t7left")
    op("CMP", "imm", 1)
    op("BEQ", "rel", "t7right")
    op("PHX")  # 창 칸 — 밑그림[(0x17 − $F8)×2] 에 저장
    op("LDA", "imm", T7_COLS - 1)
    op("SEC")
    op("SBC", "zp", 0xF8)
    op("ASL")
    op("TAX")
    op("LDA", "abs", "lolatch")
    L("t7s1")
    op("STA", "absx", 0)
    op("STX", "abs", "qc")
    op("TSX")  # 스택: +1 X · +2 A(상위)
    op("LDA", "absx", 0x2102)
    op("LDX", "abs", "qc")
    L("t7s2")
    op("STA", "absx", 0)
    op("PLX")
    op("PLA")
    op("RTS")
    L("t7left")  # 행 첫 칸(열 2) — MAWR 는 엔진이 막 잡았다
    op("LDA", "abs", "lolatch")
    op("STA", "abs", P_LO)
    op("PLA")
    op("STA", "abs", P_HI)
    op("RTS")
    L("t7right")  # 행 끝 칸(열 25) — 창 칸을 건너뛰었으니 MAWR 를 다시 잡는다
    op("PHP")
    op("SEI")
    op("ST0", "imm", 0)
    op("LDA", "zp", 0x10)
    op("CLC")
    op("ADC", "imm", T7_COLS - 1)
    op("STA", "abs", P_LO)
    op("LDA", "zp", 0x11)
    op("ADC", "imm", 0)
    op("STA", "abs", P_HI)
    op("ST0", "imm", 2)
    op("LDA", "abs", "lolatch")
    op("STA", "abs", P_LO)
    op("PLP")
    op("PLA")
    op("STA", "abs", P_HI)
    op("RTS")


def _emit_vdc(a: Mini, rt: bool = False):
    """VDC 주소 잡기(setw/setr) · 16비트 더하기 셋 — 안 A·B 공용. `rt`: 밑그림은 **행 고리**(`ubase` 가 창 행 0 의 칸) — `adddp` 가 고리 끝(= `win`)에서 `under` 로 되감긴다."""
    op, L = a.op, a.L
    for name, reg in (("setw", 0), ("setr", 1)):  # A=하위 · X=상위 → MAWR(0) / MARR(1) 를 고르고 데이터 포트로
        L(name)
        op("STA", "abs", "tmp")
        op("ST0", "imm", reg)
        op("LDA", "abs", "tmp")
        op("STA", "abs", P_LO)
        op("STX", "abs", P_HI)
        op("ST0", "imm", 2)
        op("RTS")
    for name, var, step in (("addra", "ra", 64), ("addsp", "sp", ROW_BYTES), ("adddp", "dp", ROW_BYTES)):
        L(name)
        op("LDA", "abs", var)
        op("CLC")
        op("ADC", "imm", step)
        op("STA", "abs", var)
        op("BCC", "rel", name + "1")
        op("INC", "abs", var + "1")
        L(name + "1")
        if rt and name == "adddp":
            op("LDA", "abs", "dp1")
            op("CMP", "imm", ">win")
            op("BNE", "rel", "adddp2")
            op("LDA", "abs", "dp")
            op("CMP", "imm", "<win")
            op("BNE", "rel", "adddp2")
            op("LDA", "imm", "<under")
            op("STA", "abs", "dp")
            op("LDA", "imm", ">under")
            op("STA", "abs", "dp1")
            L("adddp2")
        op("RTS")
    if rt:
        L("slotaddr")  # A = 밑그림 칸(0~9) → dp/dp1 = under + A×ROW_BYTES
        op("TAX")
        op("LDA", "imm", "<under")
        op("STA", "abs", "dp")
        op("LDA", "imm", ">under")
        op("STA", "abs", "dp1")
        L("sa1")
        op("DEX")
        op("BMI", "rel", "sa2")
        op("JSR", "abs", "adddp")
        op("BRA", "rel", "sa1")
        L("sa2")
        op("RTS")


def _emit_uploadinit(a: Mini):
    op, L = a.op, a.L
    L("uploadinit")
    op("LDA", "imm", TILE_WORD & 0xFF)
    op("STA", "abs", "vw")
    op("LDA", "imm", TILE_WORD >> 8)
    op("STA", "abs", "vw1")
    op("LDA", "abs", "d+4")
    op("STA", "abs", "nt")
    op("LDA", "abs", "d+6")
    op("STA", "abs", "tsp")
    op("LDA", "abs", "d+7")
    op("STA", "abs", "tsp1")
    op("RTS")


def _emit_upload(a: Mini, rt: bool = False):
    upt = RT_UPT if rt else UPT
    """글자 타일 압축본(타일마다 8B)을 틱마다 UPT 개씩 4bpp 로 펴 VRAM 에 — 안 A·B 공용."""
    op, L = a.op, a.L
    L("upload")
    op("LDA", "abs", "nt")
    op("BNE", "rel", "u0")
    op("RTS")
    L("u0")
    op("CMP", "imm", upt)
    op("BCC", "rel", "u1")
    op("LDA", "imm", upt)
    L("u1")
    op("STA", "abs", "cnt")
    op("LDA", "abs", "nt")
    op("SEC")
    op("SBC", "abs", "cnt")
    op("STA", "abs", "nt")
    op("LDA", "abs", "vw")  # 메인 쪽이 MAWR 를 옮겼을 수 있으니 틱마다 다시 잡는다
    op("LDX", "abs", "vw1")
    op("JSR", "abs", "setw")
    op("LDA", "abs", "tsp")
    op("STA", "abs", "ts1+1")
    op("STA", "abs", "ts2+1")
    op("LDA", "abs", "tsp1")
    op("STA", "abs", "ts1+2")
    op("STA", "abs", "ts2+2")
    # 글자 타일 압축본(타일마다 8B) → 4bpp 로 펴 쓴다: 앞 16B = (FF, 비트) × 8행, 뒤 16B = (비트, 비트) × 8행
    L("tl")
    op("LDX", "imm", 0)
    L("t1")
    op("LDA", "imm", 0xFF)
    op("STA", "abs", P_LO)
    L("ts1")
    op("LDA", "absx", 0)
    if rt:
        op("AND", "abs", "pmask")  # 화자 줄이면 평면1 = 0 → 색 13(노랑)
    op("STA", "abs", P_HI)
    op("INX")
    op("CPX", "imm", 8)
    op("BNE", "rel", "t1")
    op("LDX", "imm", 0)
    L("t2")
    L("ts2")
    op("LDA", "absx", 0)
    op("STA", "abs", P_LO)
    op("STA", "abs", P_HI)
    op("INX")
    op("CPX", "imm", 8)
    op("BNE", "rel", "t2")
    for site in ("ts1", "ts2"):  # 다음 타일 = +8B
        op("LDA", "abs", site + "+1")
        op("CLC")
        op("ADC", "imm", 8)
        op("STA", "abs", site + "+1")
        op("LDA", "abs", site + "+2")
        op("ADC", "imm", 0)
        op("STA", "abs", site + "+2")
    op("LDA", "abs", "vw")
    op("CLC")
    op("ADC", "imm", 16)
    op("STA", "abs", "vw")
    op("BCC", "rel", "tl2")
    op("INC", "abs", "vw1")
    L("tl2")
    op("DEC", "abs", "cnt")
    op("BEQ", "rel", "tl3")
    op("JMP", "abs", "tl")
    L("tl3")
    op("LDA", "abs", "ts1+1")
    op("STA", "abs", "tsp")
    op("LDA", "abs", "ts1+2")
    op("STA", "abs", "tsp1")
    op("RTS")


def _emit_rowinit_rt(a: Mini):
    """창 첫 행 `rowb`(스크롤 반영) 부터 — ra = rowb×64 + COL0."""
    op, L = a.op, a.L
    L("rowinit")
    op("LDA", "abs", "rowb")
    op("LSR")
    op("LSR")
    op("STA", "abs", "ra1")
    op("LDA", "abs", "rowb")
    for _ in range(6):
        op("ASL")
    op("ORA", "imm", gwin.COL0)
    op("STA", "abs", "ra")
    op("LDA", "imm", gwin.H)
    op("STA", "abs", "row")
    op("RTS")


def _emit_rowinit(a: Mini):
    op, L = a.op, a.L
    L("rowinit")
    op("LDA", "imm", RA0 & 0xFF)
    op("STA", "abs", "ra")
    op("LDA", "imm", RA0 >> 8)
    op("STA", "abs", "ra1")
    op("LDA", "imm", gwin.H)
    op("STA", "abs", "row")
    op("RTS")


def _emit_sweep(a: Mini, rt: bool = False):
    """창 영역 훑기(sweepinit/sweep2/sweep1) — 안 A·B 공용. `startfull` 은 안 A 가 바로 앞에 둔다(흘러든다).
    `rt`(안 B): 둘째 타일 칸 0x556~0x5FF 도 「우리 것」 — 아니면 그 쪽이 보이는 동안 훑기가 글자 단어를 밑그림에 저장해 창을 닫을 때 글자가 되살아난다(gb7 실측)."""
    op, L = a.op, a.L
    L("sweepinit")  # A·X = 목표 이미지 주소(220단어) — 새 훑기를 시작한다
    op("STA", "abs", "sp")
    op("STX", "abs", "sp1")
    if rt:  # 밑그림 행 고리 — 창 행 0 의 칸은 ubase
        op("LDA", "abs", "ubase")
        op("JSR", "abs", "slotaddr")
    else:
        op("LDA", "imm", "<under")
        op("STA", "abs", "dp")
        op("LDA", "imm", ">under")
        op("STA", "abs", "dp1")
    op("JMP", "abs", "rowinit")
    L("sweep2")
    op("JSR", "abs", "sweep1")
    L("sweep1")  # 한 행: 읽어서 **우리 것이 아닌 단어는 밑그림에 저장**하고, 목표와 다르면 다시 쓴다
    op("LDA", "abs", "row")
    op("BNE", "rel", "s1go")
    op("RTS")
    L("s1go")
    op("LDA", "abs", "ra")
    op("LDX", "abs", "ra1")
    op("JSR", "abs", "setr")
    L("tai2")
    a.raw(bytes([0xF3, P_LO & 0xFF, P_LO >> 8, 0, 0, ROW_BYTES, 0]))  # TAI VRR → buf (build 가 buf 로 고친다)
    # 비교·밑그림 저장 명령의 피연산자(= 이 행의 목표 · 밑그림 주소)를 고친다
    for var, site in (("sp", "cmp1"), ("dp", "und1")):
        op("LDA", "abs", var)
        op("STA", "abs", site + "+1")
        op("LDA", "abs", var + "1")
        op("STA", "abs", site + "+2")
    for var, site in (("sp", "cmp2"), ("dp", "und2")):
        op("LDA", "abs", var)
        op("CLC")
        op("ADC", "imm", 1)
        op("STA", "abs", site + "+1")
        op("LDA", "abs", var + "1")
        op("ADC", "imm", 0)
        op("STA", "abs", site + "+2")
    op("STZ", "abs", "dirty")
    op("LDY", "imm", 0)
    L("cw")
    # 우리 것(= 틀·바탕 타일 0x500~0x508 또는 글자 타일 0x600~0x6AF, 팔레트 8)이면 밑그림에 저장하지 않는다
    op("LDA", "absy", "buf+1")
    op("CMP", "imm", 0x85)
    op("BNE", "rel", "c6")
    op("LDA", "absy", "buf")
    op("CMP", "imm", 9)
    op("BCC", "rel", "ours")
    if rt:  # 타일 칸 둘(0x556~0x65F) — 🔴 첫 칸 시작부터. 둘째 칸(0x5DB)부터만 봤을 땐 짝수 쪽 글자가 밑그림에 저장돼 닫을 때 글자만 맵 위에 남았다(gb12 11936 실측 · 틱 기계 시험)
        op("CMP", "imm", BANK_TILE0[0] & 0xFF)
        op("BCS", "rel", "ours")
    op("BRA", "rel", "nours")
    L("c6")
    op("CMP", "imm", 0x86)
    op("BNE", "rel", "nours")
    op("LDA", "absy", "buf")
    op("CMP", "imm", 0xB0)  # 타일 0x600~0x6AF
    op("BCC", "rel", "ours")
    L("nours")
    op("LDA", "absy", "buf")
    L("und1")
    op("STA", "absy", 0)
    op("LDA", "absy", "buf+1")
    L("und2")
    op("STA", "absy", 0)
    L("ours")
    op("LDA", "absy", "buf")
    L("cmp1")
    op("CMP", "absy", 0)
    op("BNE", "rel", "dif")
    op("LDA", "absy", "buf+1")
    L("cmp2")
    op("CMP", "absy", 0)
    op("BEQ", "rel", "nxt")
    L("dif")
    op("LDA", "imm", 1)
    op("STA", "abs", "dirty")
    L("nxt")
    op("INY")
    op("INY")
    op("CPY", "imm", ROW_BYTES)
    op("BNE", "rel", "cw")
    op("LDA", "abs", "dirty")
    op("BEQ", "rel", "nw")
    op("LDA", "abs", "ra")
    op("LDX", "abs", "ra1")
    op("JSR", "abs", "setw")
    op("LDA", "abs", "sp")
    op("STA", "abs", "tiaa+1")
    op("LDA", "abs", "sp1")
    op("STA", "abs", "tiaa+2")
    L("tiaa")
    a.raw(bytes([0xE3, 0, 0, P_LO & 0xFF, P_LO >> 8, ROW_BYTES, 0]))
    L("nw")
    op("JSR", "abs", "adddp")
    op("JSR", "abs", "addsp")
    op("JSR", "abs", "addra")
    op("DEC", "abs", "row")
    op("RTS")


def program(org: int, npages: int) -> tuple[Mini, dict[str, int]]:
    """코드 + 변수·버퍼 자리(0)까지. 반환 라벨로 데이터 자리를 안다. 서술표(`descs`)와 쪽 자료는 호출자가 뒤에 붙인다.

    진입 둘: `gw`(장면 초기화가 한 번 부른다 — 상태를 세우고 트램펄린을 연결한 뒤 곧바로 돌아온다) · `tick`(VBlank 마다 트램펄린이 부른다).
    시간은 **프레임 카운터**다: 플레이 시계(`$C1B2`)는 장면 초기화·컷신 중에 멈춰 있고(실측), `$5BCF`(A=1)는 메인 루프 한 바퀴라 시간 기준이 못 된다.
    쪽 하나의 단계(`ph`): 0 시작 기다림 → 1 빈 창 그리기 → 2 글자 타일 올리기 → 3 글자 창 그리기 → 4 보이는 중(끝 시각까지 다시 쓰기) → (다음 쪽 0 | 5 지우기) → 6 끝.
    """
    a = Mini(org)
    op, L = a.op, a.L
    L("sig")
    a.raw(hook.GW_MAGIC)
    L("gw")
    op("JSR", "abs", INST)
    op("STZ", "abs", GW_FLAG)  # 트램펄린 피연산자를 채우는 동안은 끈다
    op("PHP")
    op("SEI")
    op("LDA", "abs", FRAMECNT)
    op("STA", "abs", "b0")
    op("LDA", "abs", FRAMECNT + 1)
    op("STA", "abs", "b1")
    op("PLP")
    for v in ("ph", "pg", "row"):
        op("STZ", "abs", v)
    op("JSR", "abs", "getdesc")
    for k, (site, ex) in enumerate(((hook.TICK_SIG_OP[0], "sig"), (hook.TICK_SIG_OP[1], "sig+1"), (hook.TICK_CALL_OP, "tick"))):
        op("LDA", "imm", "<" + ex)
        op("STA", "abs", site)
        op("LDA", "imm", ">" + ex)
        op("STA", "abs", site + 1)
    if T7_SKIP:
        for v in ("vis", "rowin", "busy"):
            op("STZ", "abs", v)
        op("JSR", "abs", "t7on")
    op("TMA", "tma", 5)  # 지금 MPR5 가 틱 코드가 사는 뱅크다
    op("STA", "abs", GW_FLAG)
    op("RTS")
    # ── 틱 ──
    L("tick")
    op("LDA", "abs", FRAMECNT)
    op("SEC")
    op("SBC", "abs", "b0")
    op("STA", "abs", "fl")
    op("LDA", "abs", FRAMECNT + 1)
    op("SBC", "abs", "b1")
    op("STA", "abs", "fh")
    if T7_SKIP:  # 작업 7 이 재그리기 중이면(행마다 2 로 세운다) 이번 틱은 VRAM 일을 쉰다 — MAWR 를 옮기면 엔진 쓰기가 엉뚱한 곳으로 간다
        op("LDA", "abs", "busy")
        op("BEQ", "rel", "tk1")
        op("DEC", "abs", "busy")
        op("RTS")
        L("tk1")
    op("LDA", "abs", "ph")
    op("ASL")
    op("TAX")
    op("JMP", "indx", "jt")
    L("jt")
    for n in range(7):
        a.word(f"p{n}")
    L("p0")  # 이 쪽의 시작 시각을 기다린다
    op("LDX", "imm", 0)
    op("JSR", "abs", "passed")
    op("BCS", "rel", "p0go")
    op("RTS")
    L("p0go")
    op("LDA", "imm", 1)
    op("STA", "abs", "ph")
    if T7_SKIP:
        op("STA", "abs", "vis")
    op("LDA", "imm", "<blank")
    op("LDX", "imm", ">blank")
    op("JMP", "abs", "sweepinit")
    L("p1")  # 빈 창(밑그림 저장 포함)
    op("JSR", "abs", "sweep2")
    op("LDA", "abs", "row")
    op("BNE", "rel", "r1")
    op("LDA", "imm", 2)
    op("STA", "abs", "ph")
    op("JMP", "abs", "uploadinit")
    L("r1")
    op("RTS")
    L("p2")  # 글자 타일
    op("JSR", "abs", "upload")
    op("LDA", "abs", "nt")
    op("BNE", "rel", "r2")
    op("LDA", "imm", 3)
    op("STA", "abs", "ph")
    op("JMP", "abs", "startfull")
    L("r2")
    op("RTS")
    L("p3")  # 글자 창
    op("JSR", "abs", "sweep2")
    op("LDA", "abs", "row")
    op("BNE", "rel", "r3")
    op("LDA", "imm", 4)
    op("STA", "abs", "ph")
    op("JMP", "abs", "startfull")
    L("r3")
    op("RTS")
    L("p4")  # 보이는 중 — 엔진이 그 자리를 덮으면 밑그림에 저장하고 다시 쓴다
    op("LDX", "imm", 2)
    op("JSR", "abs", "passed")
    op("BCS", "rel", "p4end")
    for _ in range(STEADY_ROWS):
        op("JSR", "abs", "sweep1")
    op("LDA", "abs", "row")
    op("BNE", "rel", "r4")
    op("JMP", "abs", "startfull")
    L("r4")
    op("RTS")
    L("p4end")
    op("INC", "abs", "pg")
    op("LDA", "abs", "pg")
    op("CMP", "imm", npages)
    op("BEQ", "rel", "p4last")
    op("STZ", "abs", "ph")
    op("JMP", "abs", "getdesc")
    L("p4last")
    if T7_SKIP:
        op("STZ", "abs", "vis")
    op("LDA", "imm", 5)
    op("STA", "abs", "ph")
    op("LDA", "imm", "<under")
    op("LDX", "imm", ">under")
    op("JMP", "abs", "sweepinit")
    L("p5")  # 지우기 — 밑그림을 되돌린다
    op("JSR", "abs", "sweep2")
    op("LDA", "abs", "row")
    op("BNE", "rel", "r5")
    op("LDA", "imm", 6)
    op("STA", "abs", "ph")
    op("STZ", "abs", GW_FLAG)
    if T7_SKIP:
        op("JSR", "abs", "t7off")
    L("r5")
    L("p6")
    op("RTS")
    L("passed")  # 프레임 수 ≥ d[X..X+1] 이면 C=1
    op("LDA", "abs", "fl")
    op("SEC")
    op("SBC", "absx", "d")
    op("LDA", "abs", "fh")
    op("SBC", "absx", "d+1")
    op("RTS")
    # ── 쪽 서술 복사 ──
    L("getdesc")  # d[0..9] ← descs[pg×10]
    op("LDA", "abs", "pg")
    op("ASL")
    op("STA", "abs", "tmp")
    op("ASL")
    op("ASL")
    op("CLC")
    op("ADC", "abs", "tmp")
    op("TAX")
    op("LDY", "imm", 0)
    L("g1")
    op("LDA", "absx", "descs")
    op("STA", "absy", "d")
    op("INX")
    op("INY")
    op("CPY", "imm", DESC)
    op("BNE", "rel", "g1")
    op("RTS")
    _emit_vdc(a)
    # ── 글자 타일 올리기 — 틱마다 UPT 개씩 ──
    _emit_uploadinit(a)
    _emit_upload(a)
    # ── 창 영역 훑기 ──
    _emit_rowinit(a)
    L("startfull")  # 이 쪽의 글자 창을 목표로
    op("LDA", "abs", "d+8")
    op("LDX", "abs", "d+9")
    _emit_sweep(a)
    if T7_SKIP:
        t7_stubs(a)
    # ── 변수 · 버퍼 · 밑그림 · 서술표 ──
    for v in ("ph", "pg", "fl", "fh", "b0", "b1", "row", "cnt", "nt", "tmp", "dirty", "ra", "ra1", "sp", "sp1", "dp", "dp1", "vw", "vw1", "tsp", "tsp1", "vis", "lolatch", "q0", "q1", "qc", "qt", "rowin", "busy"):
        L(v)
        a.raw(b"\0")
    L("d")
    a.raw(bytes(DESC))
    L("buf")
    a.raw(bytes(ROW_BYTES))
    L("under")
    a.raw(bytes(ROW_BYTES * gwin.H))
    L("blank")
    a.raw(bytes(ROW_BYTES * gwin.H))
    L("descs")
    a.raw(bytes(DESC * npages))
    return a, a.labels


STEADY_ROWS = 5  # 보이는 중에 틱마다 확인하는 행 수 — 엔진의 맵 스크롤이 창 자리를 덮는 걸 빨리 되돌린다
UPT = 6  # 틱마다 올리는 글자 타일 수(타일 하나 약 400 사이클 — VBlank 안에 들게)
GW_FLAG = hook.GW_FLAG
FRAMECNT = N.FRAMECNT  # IRQ1 트램펄린(`hook.tick_routine`)이 VBlank 마다 올리는 16비트 카운터 — 상주부 `inst` 가 처음 쓸 때 꽂는다
INST = N._resident_asm().labels["inst"]


def frames(sec: float) -> int:
    """초 → 프레임 수."""
    f = round(sec * FPS)
    if not 0 <= f <= 0xFFFF:
        raise GwinError(f"{sec}초가 16비트 프레임 수를 넘는다")
    return f


def load() -> dict[str, dict]:
    return json.loads(SPEC.read_text("utf-8"))["scenes"] if SPEC.exists() else {}


def build_specs() -> dict[str, dict]:
    """빌드에 넣을 장면 — 기본은 없음. 이동 중 대사창은 깜빡여서 못 쓴다(마스터 10-12) — 「나중에 다시 확인」 대상이라 `ED_GWIN=1` 일 때만 켠다."""
    return load() if os.environ.get("ED_GWIN") == "1" else {}


def validate(spec: dict) -> list[str]:
    errs, last = [], 0.0
    for i, pg in enumerate(spec["pages"]):
        if pg["start"] < last - 1e-6 or pg["end"] <= pg["start"]:
            errs.append(f"쪽 {i}: 시각 {pg['start']}~{pg['end']} (앞 끝 {last})")
        last = pg["end"]
        try:
            gwin.make_window(pg.get("speaker"), pg["text"])
        except AssertionError as e:
            errs.append(f"쪽 {i}: {e}")
    return errs


def build(spec: dict, org: int, stub_len: int = 3 + 3 + 1) -> tuple[bytes, int]:
    """스텁 · 코드 · 자료를 이어 붙인 바이트(주소 `org` 부터)와 초기화 진입 주소. 스텁은 `JSR 원래` 를 먼저 한 뒤 `gw` 를 부르고 `RTS` 한다(`gw` 는 곧바로 돌아온다)."""
    errs = validate(spec)
    if errs:
        raise GwinError("\n".join(errs))
    pages = spec["pages"]
    a, lab = program(org + stub_len, len(pages))
    code = bytearray(a.bytes())
    blobs = bytearray()
    base = org + stub_len + len(code)
    descs = bytearray()
    for pg in pages:
        tiles, bat = gwin.make_window(pg.get("speaker"), pg["text"])
        ours = bytearray()
        for r in range(gwin.ROW0, gwin.ROW0 + gwin.H):
            for c in range(gwin.COL0, gwin.COL0 + gwin.W):
                ours += bat[(r, c)].to_bytes(2, "little")
        t_at, o_at = base + len(blobs), base + len(blobs) + len(tiles)
        blobs += tiles + ours
        descs += frames(pg["start"]).to_bytes(2, "little") + frames(pg["end"]).to_bytes(2, "little") + bytes([len(tiles) // 8, 0]) + t_at.to_bytes(2, "little") + o_at.to_bytes(2, "little")
    d0 = lab["descs"] - (org + stub_len)
    code[d0 : d0 + len(descs)] = descs
    blank = gwin.blank_bat()
    b0 = lab["blank"] - (org + stub_len)
    code[b0 : b0 + ROW_BYTES * gwin.H] = b"".join(blank[(r, c)].to_bytes(2, "little") for r in range(gwin.ROW0, gwin.ROW0 + gwin.H) for c in range(gwin.COL0, gwin.COL0 + gwin.W))
    # TAI 버퍼 목적지(`tai2`) 는 늘 `buf`
    t2 = lab["tai2"] - (org + stub_len)
    code[t2 + 3 : t2 + 5] = lab["buf"].to_bytes(2, "little")
    return bytes(code) + bytes(blobs), lab["gw"]


# ═════════════════════════════ 안 B — 런타임 글리프 조립 (제품 공사 2단계, 마스터 10-30 「B로 진행」) ═════════════════════════════
# 🔴 **씬 블록은 풀린 크기 0x1A00(6,656B)을 못 넘는다** — 씬 열기(`$6DF3`)가 블록을 고정 뱅크 0x76 에 풀고, 엔진은 그 뱅크 꼬리
#    `$BA00~$BBEF`(구역 작업표, `$6D28~` 가 구역 진입 때 짓고 다음 구역 진입이 읽는다)를 쓴다. 10-31 실측: 안 B 코드를 블록에 실어 8,163B 가
#    되자 표가 덮여 다음 구역(꽃의동굴) 진입이 AD_READ 를 길이 0xFA99 로 불러 메모리 전체를 쓸었다. 원판 최대 블록 6,595B(공통 블록 0).
#    그래서 코드·쪽 서술·줄 표는 **씬 컨테이너의 4번째 뱅크(섹터 12~15, 빌드가 `container_tail` 로 붙인다 — 11-01 부터 컨테이너의 안 B 씬들이 한 벌을 나눠 쓴다)** 에 두고, 블록엔 작업 7 스텁·
#    버퍼·얇은 통로(`gw`·`tick`)만 남긴다. 통로가 그 뱅크(= 컨테이너 첫 캐시 뱅크 + 3, `$378D[$61] + $3EF1 + $10 + 3`)를 MPR4($8000)에
#    잠깐 걸고 부른다 — 상주부·IRQ 트램펄린은 안 바꾼다(트램펄린은 여전히 MPR5 = 씬 뱅크일 때 블록의 `tick` 통로를 부른다).
RT = os.environ.get("ED_GWIN_RT", "1") == "1"  # 안 B(런타임 조립) — 제품 기본(마스터 11-05). "0" 은 옛 시제품 경로(진단)
BLOCK_MAX = 0x1A00  # 풀린 씬 블록 상한(위 주석) — `build.assemble` 게이트와 같은 값
CODE_ORG = 0x8000  # 컨테이너 4번째 뱅크를 MPR4 에 걸고 돈다
CODE_SECTOR = 12  # 16섹터(4뱅크) 컨테이너의 기본 — 데이터는 섹터 0~11(3뱅크) 안, 코드 영역은 섹터 12 부터. 🔴 뱅크 수가 다른 컨테이너는 `code_sector()` 로(11-01)


def code_sector(slot_sectors: int) -> int:
    """컨테이너(원판 칸 `slot_sectors`)의 코드 영역 시작 섹터 = 마지막 뱅크의 첫 섹터 — 캐시 점유(뱅크 수)를 원판보다 늘리면 안 된다(10-24: 5뱅크 컨테이너가 조용히 깨졌다).
    16섹터 → 12 · 10섹터(3뱅크, 1380·1508·1588·1620) → 8: 데이터가 그 앞(2뱅크 = 16KB)에 안 들면 나눠야 한다(1620 은 20KB → 나눔, 11-01 실측 「15섹터 = 4뱅크 > 원판 3뱅크」)."""
    return (-(-slot_sectors // 4) - 1) * 4
CODE_MAX = 4 * common.USER  # 코드 영역 = 컨테이너 4번째 뱅크 전체(섹터 12~15) — 공용 렌더러 + 고정 영역 원본 + 씬별 표(11-01 공용화)
# 🔴 고정 영역(11-01, 코드 영역 공용화): 씬 뱅크 0x76 의 꼬리 `$BC00~` 에 **씬과 무관한 자리**를 둔다 — 작업 7 스텁(MPR4 = 본 프로그램으로 돈다) · 그 변수 · 밑그림.
#   emucap 읽기·쓰기 BP 실측(물리 0xEDC00~0xEDFC9): 이어하기 뒤 필드·전투·마을·씬 6 자막·동굴·씬 98 자막·메뉴·SAVE·LOAD·씬 18 구역에서 히트 0. 로더는 오프닝·타이틀에서만
#   쓰고(`$EA9C`), 작업 7(`$9917`)은 `$BFCA~$BFFF` 를 읽는다 → 그 앞에서 끝낸다. 블록(≤0x1A00)·구역 작업표(`$BA00~$BBEF`)와 안 겹친다. 통로 `gw` 가 코드 뱅크의 원본(`fiximg`)을 TII 로 깐다.
FIXED_ORG = 0xBC00
FIXED_END = 0xBF80
RT_GLYPHS = 2  # 틱마다 그리는 글자 수(쪽이 보이는 중엔 1) — 🔴 틱은 VBlank 안에 끝나야 한다(길면 상단 띠 RCR 가르기가 늦어 띠가 겹쳐 보인다, 마스터 10-31 「화면 깨짐」). 시뮬 실측: 보이는 중 틱 ≈ 2,400명령 → 아래 예산으로 ≈ 1,000
RT_STEADY_ROWS = 2  # 안 B 보이는 중 틱마다 확인하는 행 수(안 A 는 STEADY_ROWS 5)
RT_UPT = 4  # 안 B 틱마다 올리는 타일 수
LB_COLS = 22  # 줄 버퍼 기둥 수 — 156px 줄의 마지막 기둥(19) + 끝 글자가 넘치는 두 기둥
LB_BYTES = LB_COLS * 16  # 기둥마다 16행 — 기둥 순서가 곧 타일 압축본 순서(위 8행 · 아래 8행)라 줄을 다 그리면 그대로 올린다
BANK_TILE0 = (0x556, 0x5DA)  # 타일 칸 둘(쪽 번호 홀짝, 133칸씩 0x556~0x5DA · 0x5DB~0x65F) — 보이는 쪽의 다음 쪽을 쉬는 칸에 미리 그린다(결함 ③). 🔴 0x660~0x6AF 는 엔진 글자 칸 — ON 에서도 엔진이 장비 창을 찍을 때 쓴다(gon 005 글리프 섞임).
#   🔴 0x554·0x555 도 엔진 메뉴 글자 칸이다(11-02 실측: 제품 롬 마을 메뉴에서 그 패턴 자리 0xAA80~ 에 한글 획 비트맵). 11-01 에 「VRAM 쓰기 BP 0」을 믿고 0x554 로 넓혔다가(ⓐ) 되돌렸다 —
#   emucap vram0 쓰기 BP 는 전역으로 걸어도 한 번도 안 맞는다(양성 대조 실패). 4줄 꽉 찬 쪽(134타일, 씬 196)은 ⓑ 글자 기둥 재사용(렌더러 변경, 반나절)으로 — 관리자 11-02.
BANK_TILES = BANK_TILE0[1] - BANK_TILE0[0]  # 133 — 한 쪽 최대 타일(씬 196 의 134타일 쪽은 ⓑ 뒤에)
SCROLL_Y = 0x2210  # 엔진의 BYR 그림자(`$5903` 이 매 프레임 레지스터 8 에 쓴다) — 엔진 창은 이 값에 맞춰 행을 잡는다(BYR 184 ↔ 창 행 11, 제품 OFF 실측)
SCROLL_Y0 = 184
NAME_COLOR_PLANE1 = 0  # 화자 줄 색 = 팔레트 8 의 13(노랑, OFF 창 실측) — 잉크 비트: 평면0 1 · 평면1 0 · 평면2 1 · 평면3 1 (본문 15 = 전부 1)
NREC = 4  # 줄 기록(화자 + 3줄): 기둥 수 · 타일 번호 lo · hi
GAP_FRAMES = 45  # 다음 쪽 시작이 이 쪽 끝보다 이만큼(0.75초) 넘게 늦으면 창을 닫았다 다시 연다(결함 ① 간격에 창이 남아 엔진 창과 겹침). 더 짧은 간격은 앞 글을 잠깐 남긴다 — 0.5초 깜빡임(쪽 5→6, gb8 실측)보다 낫다고 봤다(마스터 판정 대상)
PALH = gwin.PAL >> 8


def _emit_getdesc16(c: Mini, name: str, var: str, dst: str):
    """dst[0..9] ← descs[var×10] — 16비트 색인(쪽이 25 를 넘을 수 있다)."""
    op, L = c.op, c.L
    L(name)
    op("LDA", "abs", var)
    op("ASL")
    op("STA", "abs", "w0")
    op("LDA", "imm", 0)
    op("ROL")
    op("STA", "abs", "w1")
    op("LDA", "abs", "w0")
    op("STA", "abs", name + "_2+1")
    op("LDA", "abs", "w1")
    op("STA", "abs", name + "_2+2")
    for _ in range(2):
        op("ASL", "abs", "w0")
        op("ROL", "abs", "w1")
    op("LDA", "abs", "w0")
    op("CLC")
    op("ADC", "abs", name + "_2+1")
    op("STA", "abs", "w0")
    op("LDA", "abs", "w1")
    op("ADC", "abs", name + "_2+2")
    op("STA", "abs", "w1")
    op("LDA", "abs", "w0")
    op("CLC")
    op("ADC", "abs", "dbase")
    op("STA", "abs", name + "_2+1")
    op("LDA", "abs", "w1")
    op("ADC", "abs", "dbase+1")
    op("STA", "abs", name + "_2+2")
    op("LDY", "imm", 0)
    L(name + "_2")
    op("LDA", "absy", 0)
    op("STA", "absy", dst)
    op("INY")
    op("CPY", "imm", DESC)
    op("BNE", "rel", name + "_2")
    op("RTS")


def _emit_render(c: Mini):
    """준비기 — 쪽 `qg` 의 줄 표(`dq+6`: 줄마다 기둥 수 · 코드 수 · 코드 주소 2B, 0 으로 끝)를 읽어 줄마다 글리프 뱅크에서 글자를 줄 버퍼(`lb`)에
    그리고(`gwin_ref` 와 같은 규칙), 다 그리면 기둥 타일을 그 쪽의 타일 칸(`qb`)에 올린 뒤 줄 기록(`recs`: 기둥 수 · 첫 타일 번호)만 남긴다.
    창 그림은 보일 때 기록으로 만든다(`applyrec`). `rs`: 1 줄 시작 → 2 글자(틱마다 `RT_GLYPHS`) → 3 올리기 → 1 … · 표 끝이면 `ready[qb]` 를 세운다."""
    op, L = c.op, c.L
    L("pstart")  # 쪽 qg 준비 시작
    op("LDA", "abs", "qg")
    op("AND", "imm", 1)
    op("STA", "abs", "qb")
    op("JSR", "abs", "getdescq")
    op("LDA", "abs", "dq+6")
    op("STA", "abs", "rp")
    op("LDA", "abs", "dq+7")
    op("STA", "abs", "rp1")
    op("LDX", "abs", "qb")
    op("LDA", "absx", "tbl")
    op("STA", "abs", "tnl")
    op("LDA", "absx", "tbh")
    op("STA", "abs", "tnh")
    op("JSR", "abs", "tn2vw")
    op("JSR", "abs", "recbase")  # X = qb×12
    op("LDY", "imm", NREC * 3)
    L("pz1")
    op("STZ", "absx", "recs")
    op("INX")
    op("DEY")
    op("BNE", "rel", "pz1")
    op("STZ", "abs", "li")
    op("LDA", "imm", 1)
    op("STA", "abs", "rs")
    op("RTS")
    L("recbase")  # X = qb×12
    op("LDA", "abs", "qb")
    op("BEQ", "rel", "rb1")
    op("LDA", "imm", NREC * 3)
    L("rb1")
    op("TAX")
    op("RTS")
    L("tn2vw")  # vw = tn×16
    op("LDA", "abs", "tnl")
    for _ in range(4):
        op("ASL")
    op("STA", "abs", "vw")
    op("LDA", "abs", "tnl")
    for _ in range(4):
        op("LSR")
    op("STA", "abs", "vw1")
    op("LDA", "abs", "tnh")
    for _ in range(4):
        op("ASL")
    op("ORA", "abs", "vw1")
    op("STA", "abs", "vw1")
    op("RTS")
    L("rstep")
    op("LDA", "abs", "rs")
    op("CMP", "imm", 1)
    op("BNE", "rel", "rs2")
    op("JMP", "abs", "rline")
    L("rs2")
    op("CMP", "imm", 2)
    op("BNE", "rel", "rs3")
    op("JMP", "abs", "rglyphs")
    L("rs3")
    op("JMP", "abs", "rup")
    L("getb")  # A = [rp++] — 줄 표
    op("LDA", "abs", "rp")
    op("STA", "abs", "gbl+1")
    op("LDA", "abs", "rp1")
    op("STA", "abs", "gbl+2")
    L("gbl")
    op("LDA", "abs", 0)
    op("INC", "abs", "rp")
    op("BNE", "rel", "gb9")
    op("INC", "abs", "rp1")
    L("gb9")
    op("RTS")
    L("rline")  # 줄 시작 — 기둥 수 0 이면 쪽 끝
    op("JSR", "abs", "getb")
    op("CMP", "imm", 0)  # getb 의 INC 가 플래그를 바꿔 놓았다
    op("BNE", "rel", "rl1")
    op("LDX", "abs", "qb")  # 쪽 끝 — 이 칸이 준비됐다
    op("LDA", "imm", 1)
    op("STA", "absx", "ready0")
    op("INC", "abs", "qg")
    op("STZ", "abs", "rs")
    op("RTS")
    L("rl1")
    op("STA", "abs", "ncol")
    op("LDX", "imm", 0xFF)  # 기둥 수 비트7 = 화자 줄 → 평면1 마스크 0(노랑)
    op("AND", "imm", 0x80)
    op("BEQ", "rel", "rl2")
    op("LDX", "imm", NAME_COLOR_PLANE1)
    L("rl2")
    op("STX", "abs", "pmask")
    op("LDA", "abs", "ncol")
    op("AND", "imm", 0x7F)
    op("STA", "abs", "ncol")
    op("JSR", "abs", "getb")
    op("STA", "abs", "rn")
    op("JSR", "abs", "getb")
    op("STA", "abs", "gcl+1")
    op("JSR", "abs", "getb")
    op("STA", "abs", "gcl+2")
    op("STZ", "abs", "lb")  # 줄 버퍼 비우기 — 겹친 TII 가 0 을 앞에서 뒤로 민다
    c.raw(b"\x73")
    c.word("lb")
    c.word("lb+1")
    c.raw((LB_BYTES - 1).to_bytes(2, "little"))
    op("STZ", "abs", "px")
    op("LDA", "imm", 2)
    op("STA", "abs", "rs")
    L("rglyphs")
    op("LDA", "imm", RT_GLYPHS)
    op("LDX", "abs", "ph")  # 보이는 중(훑기와 겹침)엔 글자 하나만
    op("CPX", "imm", 4)
    op("BNE", "rel", "rg00")
    op("LDA", "imm", 1)
    L("rg00")
    op("STA", "abs", "gcnt")
    L("rg0")
    op("LDA", "abs", "rn")
    op("BNE", "rel", "rg1")
    op("LDA", "abs", "ncol")  # 줄을 다 그렸다 → 기둥 × 2 타일을 줄 버퍼에서 올린다
    op("ASL")
    op("STA", "abs", "nt")
    op("LDA", "imm", "<lb")
    op("STA", "abs", "tsp")
    op("LDA", "imm", ">lb")
    op("STA", "abs", "tsp1")
    op("LDA", "imm", 3)
    op("STA", "abs", "rs")
    op("RTS")
    L("rg1")
    op("JSR", "abs", "getc")
    op("STA", "abs", "gl")
    op("JSR", "abs", "getc")
    op("STA", "abs", "gt")
    op("DEC", "abs", "rn")
    op("JSR", "abs", "getadv")
    op("STA", "abs", "ad")
    op("LDA", "abs", "gl")
    op("CMP", "imm", font.VARIANT_LEAD0)  # F4~ (반각 공백 F8 24 등)은 안 그린다
    op("BCS", "rel", "rg2")
    op("JSR", "abs", "draw")
    L("rg2")
    op("LDA", "abs", "px")
    op("CLC")
    op("ADC", "abs", "ad")
    op("STA", "abs", "px")
    op("DEC", "abs", "gcnt")
    op("BNE", "rel", "rg0")
    op("RTS")
    L("getc")  # A = [코드 주소++] — 피연산자를 제자리에서 올린다
    L("gcl")
    op("LDA", "abs", 0)
    op("INC", "abs", "gcl+1")
    op("BNE", "rel", "gc9")
    op("INC", "abs", "gcl+2")
    L("gc9")
    op("RTS")
    L("getadv")  # (gl, gt) → A = 전진 px — 12 가 아닌 코드만 표에(리드 · 트레일 · px, 0 으로 끝)
    op("LDX", "imm", 0)
    L("ga1")
    L("ga_op0")  # 피연산자 = 씬 전진표(gwsel 이 채운다)
    op("LDA", "absx", 0)
    op("BEQ", "rel", "gadef")
    op("CMP", "abs", "gl")
    op("BNE", "rel", "ga2")
    L("ga_op1")
    op("LDA", "absx", 0)
    op("CMP", "abs", "gt")
    op("BNE", "rel", "ga2")
    L("ga_op2")
    op("LDA", "absx", 0)
    op("RTS")
    L("ga2")
    op("INX")
    op("INX")
    op("INX")
    op("BRA", "rel", "ga1")
    L("gadef")
    op("LDA", "imm", 12)
    op("RTS")
    # 한 글자 — 글리프 뱅크(MPR3 에 잠깐)에서 18B 를 꺼내 줄 버퍼의 px 자리에 OR
    L("draw")
    op("LDA", "abs", "gt")  # 뱅크 안 자리 = (트레일 − 24)×18 + (리드 홀수면 3960)
    op("SEC")
    op("SBC", "imm", font.TRAIL0)
    op("ASL")
    op("STA", "abs", "o0")
    op("STA", "abs", "w0")
    op("LDA", "imm", 0)
    op("ROL")
    op("STA", "abs", "o1")
    op("STA", "abs", "w1")
    for _ in range(3):
        op("ASL", "abs", "o0")
        op("ROL", "abs", "o1")
    op("LDA", "abs", "o0")
    op("CLC")
    op("ADC", "abs", "w0")
    op("STA", "abs", "o0")
    op("LDA", "abs", "o1")
    op("ADC", "abs", "w1")
    op("STA", "abs", "o1")
    op("LDA", "abs", "gl")
    op("AND", "imm", 1)
    op("BEQ", "rel", "dr0")
    op("LDA", "abs", "o0")
    op("CLC")
    op("ADC", "imm", font.GROUP_BYTES & 0xFF)
    op("STA", "abs", "o0")
    op("LDA", "abs", "o1")
    op("ADC", "imm", font.GROUP_BYTES >> 8)
    op("STA", "abs", "o1")
    L("dr0")
    op("LDA", "abs", "o0")
    op("STA", "abs", "cpl+1")
    op("LDA", "abs", "o1")
    op("CLC")
    op("ADC", "imm", 0x60)  # MPR3 창 $6000
    op("STA", "abs", "cpl+2")
    op("LDA", "abs", "gl")
    op("SEC")
    op("SBC", "imm", font.LEAD0)
    op("LSR")
    op("CLC")
    op("ADC", "imm", font.GLYPH_BANK0)
    op("STA", "abs", "bk")
    op("PHP")
    op("SEI")
    op("TMA", "tma", 3)
    op("STA", "abs", "sv")
    op("LDA", "abs", "bk")
    op("TAM", "tam", 3)
    op("LDY", "imm", 0)
    L("cpl")
    op("LDA", "absy", 0)
    op("STA", "absy", "gb")
    op("INY")
    op("CPY", "imm", font.PACKED_BYTES)
    op("BNE", "rel", "cpl")
    op("LDA", "abs", "sv")
    op("TAM", "tam", 3)
    op("PLP")
    # 기둥 셋의 시작 = lb + (px>>3)×16 → OR 명령 여섯의 피연산자
    op("LDA", "abs", "px")
    op("AND", "imm", 7)
    op("STA", "abs", "sh")
    op("LDA", "abs", "px")
    op("AND", "imm", 0xF8)
    op("STA", "abs", "w0")
    op("STZ", "abs", "w1")
    op("ASL", "abs", "w0")
    op("ROL", "abs", "w1")  # (px>>3)×16 = (px&F8)×2
    for k in range(3):
        op("LDA", "abs", "w0")
        op("CLC")
        op("ADC", "imm", f"<lb+{16 * k}")
        op("STA", "abs", f"pl{k}+1")
        op("STA", "abs", f"ps{k}+1")
        op("LDA", "abs", "w1")
        op("ADC", "imm", f">lb+{16 * k}")
        op("STA", "abs", f"pl{k}+2")
        op("STA", "abs", f"ps{k}+2")
    op("LDY", "imm", 0)  # 18B 안 자리(세 바이트 = 두 행)
    op("LDX", "imm", 2)  # 줄 안 행(글리프는 2행부터)
    L("dr1")
    op("LDA", "absy", "gb")  # 행 A: 상위 = b0 · 하위 = b1 & F0
    op("STA", "abs", "rhi")
    op("LDA", "absy", "gb+1")
    op("AND", "imm", 0xF0)
    op("STA", "abs", "rlo")
    op("JSR", "abs", "place")
    op("LDA", "absy", "gb+1")  # 행 B: 상위 = b1<<4 | b2>>4 · 하위 = b2<<4
    for _ in range(4):
        op("ASL")
    op("STA", "abs", "rhi")
    op("LDA", "absy", "gb+2")
    for _ in range(4):
        op("LSR")
    op("ORA", "abs", "rhi")
    op("STA", "abs", "rhi")
    op("LDA", "absy", "gb+2")
    for _ in range(4):
        op("ASL")
    op("STA", "abs", "rlo")
    op("JSR", "abs", "place")
    op("INY")
    op("INY")
    op("INY")
    op("CPY", "imm", font.PACKED_BYTES)
    op("BNE", "rel", "dr1")
    op("RTS")
    L("place")  # (rhi:rlo:0) >> sh 를 행 X 의 기둥 셋에 OR, X++
    op("LDA", "abs", "rhi")
    op("STA", "abs", "a1")
    op("LDA", "abs", "rlo")
    op("STA", "abs", "a2")
    op("STZ", "abs", "a3")
    op("LDA", "abs", "sh")
    op("BEQ", "rel", "pl9")
    op("STA", "abs", "shc")
    L("pl8")
    op("LSR", "abs", "a1")
    op("ROR", "abs", "a2")
    op("ROR", "abs", "a3")
    op("DEC", "abs", "shc")
    op("BNE", "rel", "pl8")
    L("pl9")
    for k in range(3):
        L(f"pl{k}")
        op("LDA", "absx", 0)
        op("ORA", "abs", f"a{k + 1}")
        L(f"ps{k}")
        op("STA", "absx", 0)
    op("INX")
    op("RTS")
    # 줄 타일 올리기 — `upload` 그대로(압축본 = 줄 버퍼). 다 올리면 줄 기록을 남기고 타일 번호를 넘긴다
    L("rup")
    op("JSR", "abs", "upload")
    op("LDA", "abs", "nt")
    op("BEQ", "rel", "ru1")
    op("RTS")
    L("ru1")
    op("JSR", "abs", "recbase")
    op("TXA")
    op("CLC")
    op("ADC", "abs", "li")
    op("ADC", "abs", "li")
    op("ADC", "abs", "li")
    op("TAX")
    op("LDA", "abs", "ncol")
    op("STA", "absx", "recs")
    op("LDA", "abs", "tnl")
    op("STA", "absx", "recs+1")
    op("LDA", "abs", "tnh")
    op("STA", "absx", "recs+2")
    op("LDA", "abs", "ncol")
    op("ASL")
    op("CLC")
    op("ADC", "abs", "tnl")
    op("STA", "abs", "tnl")
    op("BCC", "rel", "ru2")
    op("INC", "abs", "tnh")
    L("ru2")
    op("INC", "abs", "li")
    op("LDA", "imm", 1)
    op("STA", "abs", "rs")
    op("RTS")
    # 창 그림(`win`) = 빈 창 + 줄 기록 — 보일 때 한 번
    L("mkblank")
    for r in range(gwin.H):
        c.raw(b"\x73")
        c.word("tpl_t" if r == 0 else "tpl_b" if r == gwin.H - 1 else "tpl_m")
        c.word(f"win+{r * ROW_BYTES}")
        c.raw(ROW_BYTES.to_bytes(2, "little"))
    op("RTS")
    L("applyrec")  # A = 타일 칸(0/1) — 그 칸의 줄 기록을 창 그림에
    op("STA", "abs", "qb2")
    op("STZ", "abs", "pli")
    L("ar1")
    op("LDA", "abs", "qb2")
    op("BEQ", "rel", "ar2")
    op("LDA", "imm", NREC * 3)
    L("ar2")
    op("CLC")
    op("ADC", "abs", "pli")
    op("ADC", "abs", "pli")
    op("ADC", "abs", "pli")
    op("TAX")
    op("LDA", "absx", "recs")
    op("BEQ", "rel", "ar3")
    op("STA", "abs", "pn")
    op("LDA", "absx", "recs+1")
    op("STA", "abs", "ptl")
    op("LDA", "absx", "recs+2")
    op("STA", "abs", "pth")
    op("JSR", "abs", "putline")
    L("ar3")
    op("INC", "abs", "pli")
    op("LDA", "abs", "pli")
    op("CMP", "imm", NREC)
    op("BNE", "rel", "ar1")
    op("RTS")
    L("putline")  # 줄 pli: 기둥 pn 개, 타일 ptl/pth 부터 → win 의 두 행(위·아래)
    op("LDA", "abs", "pli")
    op("ASL")
    op("TAX")
    op("LDA", "absx", "lofs")
    op("CLC")
    op("ADC", "imm", "<win")
    op("STA", "abs", "w0")
    op("LDA", "absx", "lofs+1")
    op("ADC", "imm", ">win")
    op("STA", "abs", "w1")
    for site, off in (("bw0", 0), ("bw1", 1), ("bw2", ROW_BYTES), ("bw3", ROW_BYTES + 1)):
        op("LDA", "abs", "w0")
        op("CLC")
        op("ADC", "imm", off)
        op("STA", "abs", site + "+1")
        op("LDA", "abs", "w1")
        op("ADC", "imm", 0)
        op("STA", "abs", site + "+2")
    op("LDX", "imm", 0)
    op("LDY", "abs", "pn")
    L("pt1")  # 위 행 타일(ptl/pth) → 번호 +1 → 아래 행 타일 → +1 — 0x5FF→0x600 처럼 상위가 바뀌는 쌍도 맞게
    op("LDA", "abs", "ptl")
    L("bw0")
    op("STA", "absx", 0)
    op("LDA", "abs", "pth")
    op("ORA", "imm", PALH)
    L("bw1")
    op("STA", "absx", 0)
    op("JSR", "abs", "ptinc")
    op("LDA", "abs", "ptl")
    L("bw2")
    op("STA", "absx", 0)
    op("LDA", "abs", "pth")
    op("ORA", "imm", PALH)
    L("bw3")
    op("STA", "absx", 0)
    op("JSR", "abs", "ptinc")
    op("INX")
    op("INX")
    op("DEY")
    op("BNE", "rel", "pt1")
    op("RTS")
    L("ptinc")
    op("INC", "abs", "ptl")
    op("BNE", "rel", "pt2")
    op("INC", "abs", "pth")
    L("pt2")
    op("RTS")


def program_b(org: int, sid: int = 0, code_bank: int = CODE_SECTOR // 4) -> tuple[Mini, Mini, Mini, dict[str, int]]:
    """안 B — (블록 쪽 `a`, 고정 영역 `f`, 컨테이너 4번째 뱅크 쪽 `c`, 합친 라벨). 라벨은 셋을 합쳐 푼다(서로 절대 주소로 부른다). 11-01 공용화:

    블록 쪽(씬마다 ≈100B): 서명 · 통로 `gw`(코드 뱅크 셈 → 트램펄린 피연산자 → 고정 영역 깔기(TII) → `slot` = 씬 번호 → `gwr`) / `tick`(MPR4 에 코드 뱅크를 걸고 `tickr`).
    고정 영역(`$BC00~`, 씬 무관): 작업 7 스텁과 그 변수(작업 7 은 MPR4 = 본 프로그램으로 돈다) · `under` 밑그림. 컨테이너 쪽(공용, 한 벌): 래스터 핸들러 원본 ·
    버퍼(`win` 창 그림 · `lb` 줄 버퍼 · `buf` · `gb`) · 렌더러 · 변수 · 고정 영역 원본 `fiximg` · 그 뒤에 `container_tail` 이 씬별 표(전진표 · 서술표 · 줄 표)와 디렉터리 `dir` 를 붙인다.
    `gwsel` 이 `slot` 으로 디렉터리를 찾아 `npg`·`dbase`·전진표 피연산자를 채운다 — 한 컨테이너의 안 B 씬 여럿이 렌더러 한 벌을 나눠 쓴다.
    표시기(`ph`): 0 시작 시각·준비 완료 기다림 → 1 밑그림 미리 읽기(한 틱, 화면 변화 없음) → 3 글자 창 통째로 쓰기(한 틱) → 4 보이는 중 →
    끝: 다음 쪽이 바로 이어지면 0(창이 떠 있으니 1·3 없이 행만 한 틱에 바꾼다 `fastopen`) · 간격이 있으면 5 지우기(한 틱) 뒤 0 · 마지막이면 5 뒤 6.
    열기·바꾸기·닫기가 다 한 틱이라 반쪽 창 프레임이 없다(gb12 실측: 처음 열기가 행 단위 훑기라 2~3프레임 반쪽이 남았다).
    준비기(`prep`)는 쪽 `qg`(≤ 보이는 쪽 + 1)를 쉬는 타일 칸에 미리 그린다. 쪽 0 만은 초기화(`gwr`)가 메인 스레드에서 `pre0` 로 한꺼번에 그린다(첫 쪽 지연)."""
    a, f, c = Mini(org), Mini(FIXED_ORG), Mini(CODE_ORG)
    # ───────────── 고정 영역(씬 뱅크 꼬리 $BC00~, 씬 무관) — 작업 7 이 MPR4 = 본 프로그램으로 돌며 읽고 쓰는 것 전부 ─────────────
    op, L = f.op, f.L
    if T7_SKIP:
        t7_stubs(f, rt=True)
    for v in ("ph", "gwbank", "vis", "lolatch", "q0", "q1", "qc", "qt", "rowin", "busy", "rowb", "ubase", "rcon", "rce1", "rce2", "slot"):
        L(v)
        f.raw(b"\0")
    L("under")
    f.raw(bytes(ROW_BYTES * gwin.H))
    L("fixend")
    if f.pc > FIXED_END:
        raise GwinError(f"고정 영역 {f.pc - FIXED_ORG}B > {FIXED_END - FIXED_ORG}B")
    fixed = f.bytes()  # 고정 영역은 자기 라벨만 쓴다 — 먼저 굳혀 코드 뱅크에 원본으로 싣는다
    # ───────────── 블록 쪽(씬마다 ≈100B) — 서명 · 통로 둘 ─────────────
    op, L = a.op, a.L
    L("sig")
    a.raw(hook.GW_MAGIC)
    L("gw")  # 통로 — 코드 뱅크 = 컨테이너 첫 캐시 뱅크 + 3 (`$6E04~$6E12` 와 같은 셈). 🔴 상주부(`INST`)와 작업 7 스텁 설치(`t7on`, MPR4 = 0x6B 를 확인)는 MPR4 를 바꾸기 전·후에
    op("STZ", "abs", GW_FLAG)  # 앞 장면의 틱이 살아 있을 수 있다 — 피연산자를 채우는 동안은 끈다
    op("JSR", "abs", INST)
    op("LDY", "zp", 0x61)
    op("LDA", "absy", 0x378D)
    op("CLC")
    op("ADC", "abs", 0x3EF1)
    op("ADC", "imm", 0x10 + code_bank)  # 코드 뱅크 = 컨테이너의 마지막 뱅크(`code_sector`)
    op("TAX")  # X = 코드 뱅크
    for site, ex in ((hook.TICK_SIG_OP[0], "sig"), (hook.TICK_SIG_OP[1], "sig+1"), (hook.TICK_CALL_OP, "tick")):  # 트램펄린 피연산자 — 블록 쪽 라벨이라 여기서(gwr 는 공용 코드)
        op("LDA", "imm", "<" + ex)
        op("STA", "abs", site)
        op("LDA", "imm", ">" + ex)
        op("STA", "abs", site + 1)
    op("TMA", "tma", 4)
    op("PHA")
    op("TXA")
    op("TAM", "tam", 4)
    a.raw(bytes([0x73]))  # TII fiximg → 고정 영역(스텁 · 변수 0 · 밑그림 0)
    a.fix.append((len(a.out), "fiximg", "abs"))
    a.raw(b"\0\0" + FIXED_ORG.to_bytes(2, "little") + len(fixed).to_bytes(2, "little"))
    op("STX", "abs", "gwbank")
    op("LDA", "imm", sid)
    op("STA", "abs", "slot")  # 공용 gwr 가 디렉터리에서 이 씬의 표를 고른다
    op("JSR", "abs", "gwr")
    op("PLA")
    op("TAM", "tam", 4)
    if T7_SKIP:
        op("JSR", "abs", "t7on")  # vis·rowin·busy 는 원본 0
    op("RTS")
    L("tick")
    op("TMA", "tma", 4)
    op("PHA")
    op("LDA", "abs", "gwbank")
    op("TAM", "tam", 4)
    op("JSR", "abs", "tickr")
    op("PLA")
    op("TAM", "tam", 4)
    if T7_SKIP:  # 끝(ph=6)이면 작업 7 원래 바이트를 되돌린다 — MPR4 가 본 프로그램일 때만 되므로 될 때까지 틱마다 시도(작업 7 쪽 `t7row` 도 한다)
        op("LDA", "abs", "ph")
        op("CMP", "imm", 6)
        op("BNE", "rel", "tkx")
        op("JSR", "abs", "t7off")
        L("tkx")
    op("RTS")
    # ───────────── 컨테이너 뱅크 쪽(공용) — 래스터 핸들러 원본 · 버퍼 · 코드 · 표 ─────────────
    op, L = c.op, c.L
    if RASTER:  # 래스터 핸들러 **원본** — `shown` 이 늘 매핑된 RAM(RC_RING)으로 복사한다(틱 안이라 MPR4 = 코드 뱅크)
        # 🔴 BYR 는 「쓴 줄의 다음 줄에 보일 BAT y」다(VDC 가 쓴 값부터 다시 센다) — 놀이판은 줄 31 에 V 를 써서 줄 32 가 BAT y=V. 창 첫 행(BAT y = rowb×8)을 줄 120 에 고정하려면
        #   줄 119 에 rowb×8 을 쓰고, 창 아래(줄 200)는 엔진이 보였을 y = V + (200 − 32) 로 되돌린다. 엔진 HUD 분할(줄 191 → 192)의 피연산자는 창 열 번째 행(rowb×8 + 72)으로.
        #   처음 시도(V&0xF8 / V 그대로)는 이 셈을 몰라 화면이 통째로 밀렸다(g98c 첫 촬영).
        L("rc1")  # 창 윗줄: BYR ← rowb×8(RAM 거울 RC_Y) · HUD 분할 피연산자 ← rowb×8 + 72. 🔴 블록 변수를 읽지 않는다(MPR5 가 IRQ 때 다를 수 있다)
        if RC_MODE == "noop":
            op("JMP", "abs", 0x40A6)
        op("JSR", "abs", 0x4455)
        op("ST0", "imm", 8)
        op("LDA", "abs", RC_Y)
        op("STA", "abs", 0x0002)
        op("STZ", "abs", 0x0003)
        # (11-02) HUD 분할 즉치(`$594C`) 패치를 걷었다 — 창이 134~213 이면 엔진 분할(214~)이 창 바로 아래라 원판 그대로 215 를 쓰면 된다
        if RC_F7:
            op("LDA", "imm", 2)
            op("STA", "zp", 0xF7)
        op("JMP", "abs", 0x40A6)
        while c.pc - c.labels["rc1"] < 32:  # rc1 칸 32B(ring 사본 배치용)
            c.raw(b"\xea")  # NOP
        L("rc2")  # 창 아랫줄(199): BYR ← `$56` + (200 − 192) — HUD 분할이 보였을 y(아래 틀·Gold 줄). 11-02 전엔 V + 168(맵)이라 틀이 사라졌다
        if RC_MODE == "noop":
            op("JMP", "abs", 0x40A6)
        op("JSR", "abs", 0x4455)
        op("ST0", "imm", 8)
        if TOP:  # 창이 위(줄 54~133)면 그 아래는 맵이다 — 창 윗줄에 쓴 타일 정렬값(RC_Y = rowb×8)에서 창 높이(RC_BOT − RC_TOP)만큼 간 값에 스크롤의 서브타일 위상(V & 7)을 더해 엔진이 보였을 BYR 로 되돌린다
            #   (BAT 가 64행이라 BYR 9비트로 더하면 맵 밖(검정)으로 간다 — 첫 시험 test-top: 엔진 그림자 V 로 셈하니 창 아래가 검었다)
            op("LDA", "abs", SCROLL_Y)
            op("AND", "imm", 7)
            op("CLC")
            op("ADC", "abs", RC_Y)
            op("CLC")
            op("ADC", "imm", RC_BOT - RC_TOP)
            op("STA", "abs", 0x0002)
            op("LDA", "imm", 0)
            op("ADC", "imm", 0)
            op("STA", "abs", 0x0003)
        else:
            op("LDA", "zp", HUD_BYR_ZP)
            op("CLC")
            op("ADC", "imm", RC_BOT + 1 - (HUD_SPLIT + 1))
            op("STA", "abs", 0x0002)
            op("LDA", "zp", HUD_BYR_ZP + 1)
            op("ADC", "imm", 0)
            op("STA", "abs", 0x0003)
        if RC_F7:
            op("LDA", "imm", 2)
            op("STA", "zp", 0xF7)
        op("JMP", "abs", 0x40A6)
    L("buf")
    c.raw(bytes(ROW_BYTES))
    L("gb")
    c.raw(bytes(font.PACKED_BYTES))
    L("win")
    c.raw(bytes(ROW_BYTES * gwin.H))
    L("lb")
    c.raw(bytes(LB_BYTES))
    L("gwr")
    op("STZ", "abs", GW_FLAG)  # 트램펄린 피연산자를 채우는 동안은 끈다
    op("PHP")
    op("SEI")
    op("LDA", "abs", FRAMECNT)
    op("STA", "abs", "b0")
    op("LDA", "abs", FRAMECNT + 1)
    op("STA", "abs", "b1")
    op("PLP")
    for v in ("ph", "pg", "row", "qg", "rs", "ready0", "ready1", "last", "reopen", "wopen", "ubase", "rcon"):
        op("STZ", "abs", v)
    op("JSR", "abs", "gwsel")  # slot(씬 번호) → 디렉터리에서 이 씬의 쪽 수 · 서술표 · 전진표
    op("JSR", "abs", "getdesc")
    op("JSR", "abs", "pre0")  # 첫 쪽을 지금 바로(메인 스레드) 다 그린다 — 틱이 켜지기 전이라 서로 안 끼어든다
    op("TMA", "tma", 5)  # 지금 MPR5 가 통로가 사는 씬 뱅크다
    op("STA", "abs", GW_FLAG)
    op("RTS")
    # ── 씬 표 고르기 — 디렉터리 `dir`: 항목 6B [씬 번호 · 서술표 lo hi · 전진표 lo hi · 쪽 수] … 0xFF 끝(container_tail 이 쓴다) ──
    L("gwsel")
    op("LDX", "imm", 0)
    L("gs1")
    op("LDA", "absx", "dir")
    op("CMP", "imm", 0xFF)
    op("BEQ", "rel", "gs9")  # 없으면 쪽 수 0 — 틱이 바로 끝낸다(빌드가 막는다)
    op("CMP", "abs", "slot")
    op("BEQ", "rel", "gs2")
    op("TXA")
    op("CLC")
    op("ADC", "imm", 6)
    op("TAX")
    op("BRA", "rel", "gs1")
    L("gs2")
    op("LDA", "absx", "dir+1")
    op("STA", "abs", "dbase")
    op("LDA", "absx", "dir+2")
    op("STA", "abs", "dbase+1")
    for k, lab_ in enumerate(("ga_op0", "ga_op1", "ga_op2")):  # 전진표 피연산자 셋 = 표 + 0·1·2
        op("CLC")
        op("LDA", "absx", "dir+3")
        op("ADC", "imm", k)
        op("STA", "abs", lab_ + "+1")
        op("LDA", "absx", "dir+4")
        op("ADC", "imm", 0)
        op("STA", "abs", lab_ + "+2")
    op("LDA", "absx", "dir+5")
    op("STA", "abs", "npg")
    L("gs9")
    op("RTS")
    # ── 첫 쪽 동기 미리 그리기(11-01, 첫 쪽 지연) ──
    # 틱은 VBlank 예산(글자 2·타일 4 /틱) 때문에 첫 쪽 타일을 올리는 데 ≈65틱이 걸려 첫 쪽이 음성보다 ≈1초 늦게 떴다(씬 98 실측 6765 → 6832).
    # 「씬 열기에서 미리 그리기」(두 입구)는 자리가 없다 — 씬 98 입장 핸들러($A128, 블록 머리 벡터 1)에서 음성 호출까지 7,785사이클(0.07프레임)이고
    # 그 앞은 엔진의 적재 경로(블록 코드가 아직 없다). 대신 음성 호출 자리에서 `prep` 를 틱 한 번 분량씩 IRQ 를 막고(각 ≤ 1,855명령) 쪽 0 이
    # 준비될 때까지 돌린다 — 틱 65회분이 메인 스레드에선 ≈4프레임. 시계(b0/b1)는 이미 잡았으니 뒤 쪽 시각은 그대로. 상한 256회(표가 깨져도 안 멈춘다).
    L("pre0")
    op("STZ", "abs", "pren")
    op("LDA", "abs", FRAMECNT)
    op("STA", "abs", "pfc")
    L("pre1")
    if PRE_SYNC:  # 11-04 마스터 「순간적으로 위·아래 깨짐」 — 틱 분량(≤1,855명령)을 IRQ 를 막고 돌리면 그 사이 래스터 분할(줄 191·207·240)이 최대 한 틱만큼 늦어 화면 줄이 어긋난다(gon d607d021 헤드리스: 음성 호출 뒤 2프레임).
        #   분할이 없는 구간 = VBlank 시작(FRAMECNT 이 오르는 때)부터 다음 프레임 줄 31 까지(≈53줄)에만 돌린다 — 프레임마다 PRE_N 틱.
        L("pre1w")
        op("LDA", "abs", FRAMECNT)
        op("CMP", "abs", "pfc")
        op("BEQ", "rel", "pre1w")
        op("STA", "abs", "pfc")
    for k in range(PRE_N if PRE_SYNC else 1):
        op("PHP")
        op("SEI")
        op("JSR", "abs", "prep")
        op("PLP")
        op("LDA", "abs", "ready0")  # 쪽 0 = 칸 0
        op("BNE", "rel", "pre2")
    op("INC", "abs", "pren")
    op("BNE", "rel", "pre1")
    L("pre2")
    op("LDA", "zp", 0xF7)  # 엔진의 VDC 레지스터 선택 그림자대로 되돌린다 — `setw` 가 2(VWR)로 두고 나온다. 틱에선 엔진 IRQ 가 되돌리지만 여긴 메인 스레드다
    op("STA", "abs", 0x0000)
    op("RTS")
    # ── 틱 ──
    L("tickr")
    op("LDA", "abs", FRAMECNT)
    op("SEC")
    op("SBC", "abs", "b0")
    op("STA", "abs", "fl")
    op("LDA", "abs", FRAMECNT + 1)
    op("SBC", "abs", "b1")
    op("STA", "abs", "fh")
    if T7_SKIP:  # 작업 7 이 재그리기 중이면 이번 틱은 VRAM 일을 쉰다(준비기도 — 타일 올리기가 MAWR 를 옮긴다)
        op("LDA", "abs", "busy")
        op("BEQ", "rel", "tk1")
        op("DEC", "abs", "busy")
        op("RTS")
        L("tk1")
    op("JSR", "abs", "prep")
    op("LDA", "abs", "ph")
    op("ASL")
    op("TAX")
    op("JMP", "indx", "jt")
    L("jt")
    for n in range(7):
        c.word(f"p{n}")
    L("p0")  # 시작 시각 + 이 쪽의 준비를 기다린다
    op("LDX", "imm", 0)
    op("JSR", "abs", "passed")
    op("BCS", "rel", "p0a")
    op("RTS")
    L("p0a")
    op("LDA", "abs", "pg")
    op("AND", "imm", 1)
    op("TAX")
    op("LDA", "absx", "ready0")
    op("BNE", "rel", "p0go")
    op("RTS")
    L("p0go")
    op("JSR", "abs", "latch")  # 창 행 = ROW0 + (BYR − 184)/8 — 엔진 창과 같은 자리(마스터 006: 스크롤이 다르면 창이 뜬다)
    op("JSR", "abs", "mkblank")
    op("LDA", "abs", "pg")
    op("AND", "imm", 1)
    op("JSR", "abs", "applyrec")
    op("LDA", "abs", "wopen")  # 창이 떠 있는 채 쪽만 바뀌면 한 틱에 통째로
    op("BNE", "rel", "fastopen")
    op("LDA", "imm", 1)  # 처음 열기 — 다음 틱에 밑그림을 미리 읽고(p1) 그다음 틱에 통째로 쓴다(p3)
    op("STA", "abs", "ph")
    op("RTS")
    L("fastopen")  # 창이 이미 떠 있으면(앞 쪽이 보이던 중) 행 열을 한 틱에 통째로 바꾼다 — 반쪽 창 프레임이 안 생긴다(마스터 003·「매끄럽지 않음」)
    op("LDA", "imm", "<win")
    op("LDX", "imm", ">win")
    op("JSR", "abs", "fastrows")
    L("shown")  # 창이 떠 있다 — 보이는 중(p4)으로
    op("LDA", "imm", 4)
    op("STA", "abs", "ph")
    if RASTER:
        op("JSR", "abs", "rcy")  # 창 첫 행 BAT y 거울
        op("LDA", "abs", "rcon")
        op("BNE", "rel", "rcskip")
        if RC_MODE == "ring":  # 진단 — 핸들러 둘(rc1 = 32B 칸, rc2 = 그 다음 32B)을 늘 매핑된 RAM 으로 복사해 등록
            c.raw(bytes([0x73]))
            c.fix.append((len(c.out), "rc1", "abs"))
            c.raw(b"\0\0" + RC_RING.to_bytes(2, "little") + (64).to_bytes(2, "little"))
        op("LDA", "imm", RC_TOP)
        if RC_MODE == "ring":
            op("LDX", "imm", RC_RING & 0xFF)
            op("LDY", "imm", RC_RING >> 8)
        else:
            op("LDX", "imm", "<rc1")
            op("LDY", "imm", ">rc1")
        op("JSR", "abs", 0x43B4)  # 분할 더하기 → X = 항목
        op("STX", "abs", "rce1")
        if RC2 or TOP:  # (11-02 기본 꺼짐) 창 아랫줄 핸들러 — 창 끝(213)이 HUD 분할(214) 앞이라 엔진이 스스로 되돌린다
            op("LDA", "imm", RC_BOT)
            if RC_MODE == "ring":
                op("LDX", "imm", (RC_RING + 32) & 0xFF)
                op("LDY", "imm", (RC_RING + 32) >> 8)
            else:
                op("LDX", "imm", "<rc2")
                op("LDY", "imm", ">rc2")
            op("JSR", "abs", 0x43B4)
            op("STX", "abs", "rce2")
        op("LDA", "imm", 1)
        op("STA", "abs", "rcon")
        L("rcskip")
    if T7_SKIP:
        op("LDA", "imm", 1)
        op("STA", "abs", "vis")
    op("LDA", "imm", 1)
    op("STA", "abs", "wopen")
    L("showinit")
    op("LDA", "imm", "<win")
    op("LDX", "imm", ">win")
    op("JMP", "abs", "sweepinit")
    L("p1")  # 미리 읽기 — 창 10행을 밑그림에 읽기만 한다(한 틱, TAI 10번 — 화면은 안 바뀐다). 기다리는 동안 스크롤이 움직였으면 행을 다시 잡는다
    op("LDA", "abs", SCROLL_Y)
    op("CMP", "abs", "byr0")
    op("BEQ", "rel", "p1r")
    op("JSR", "abs", "latch")
    L("p1r")
    op("JSR", "abs", "readrows")
    op("LDA", "imm", 3)
    op("STA", "abs", "ph")
    op("RTS")
    L("p2")
    op("RTS")
    L("p3")  # 쓰기 — 읽은 뒤 스크롤이 움직였으면 다시 읽고(p1), 아니면 창 그림을 한 틱에 통째로. 🔴 `vis` 는 여기서 켠다 — 켜진 뒤엔 작업 7 이 창 칸을
    #   VRAM 대신 밑그림에 쓰므로 그 뒤의 VRAM 읽기는 낡은 값이다(미리 읽기보다 먼저 켜면 안 된다)
    op("LDA", "abs", SCROLL_Y)
    op("CMP", "abs", "byr0")
    op("BEQ", "rel", "p3w")
    op("LDA", "imm", 1)
    op("STA", "abs", "ph")
    op("RTS")
    L("p3w")
    op("LDA", "imm", "<win")
    op("LDX", "imm", ">win")
    op("JSR", "abs", "fastrows")
    op("JMP", "abs", "shown")
    L("readrows")  # 창 10행을 VRR 에서 밑그림(`under`)으로 — 처음 여는 자리라 우리 타일이 없으니 `sweep1` 의 「우리 것」 거르기 없이 그대로
    op("STZ", "abs", "ubase")  # 처음 열기 — 고리 기준 0(창 행 r = 칸 r)
    op("LDA", "imm", "<under")
    op("STA", "abs", "rta+3")
    op("LDA", "imm", ">under")
    op("STA", "abs", "rta+4")
    op("JSR", "abs", "rowinit")
    L("rr1")
    op("LDA", "abs", "ra")
    op("LDX", "abs", "ra1")
    op("JSR", "abs", "setr")
    L("rta")
    c.raw(bytes([0xF3, P_LO & 0xFF, P_LO >> 8, 0, 0, ROW_BYTES, 0]))  # TAI VRR → 밑그림 행
    op("LDA", "abs", "rta+3")
    op("CLC")
    op("ADC", "imm", ROW_BYTES)
    op("STA", "abs", "rta+3")
    op("BCC", "rel", "rr2")
    op("INC", "abs", "rta+4")
    L("rr2")
    op("JSR", "abs", "addra")
    op("DEC", "abs", "row")
    op("BNE", "rel", "rr1")
    op("RTS")
    if RASTER:
        L("rcy")  # RC_Y ← rowb×8 (래스터 핸들러용 RAM 거울)
        op("LDA", "abs", "rowb")
        op("ASL")
        op("ASL")
        op("ASL")
        op("STA", "abs", RC_Y)
        op("RTS")
    L("fastrows")  # A·X = 220단어 그림 → 창 10행에 읽기 없이 쓴다(한 틱, TIA 10번)
    op("STA", "abs", "fta+1")
    op("STX", "abs", "fta+2")
    op("JSR", "abs", "rowinit")
    L("fr1")
    op("LDA", "abs", "ra")
    op("LDX", "abs", "ra1")
    op("JSR", "abs", "setw")
    L("fta")
    c.raw(bytes([0xE3, 0, 0, P_LO & 0xFF, P_LO >> 8, ROW_BYTES, 0]))  # TIA 그림 행 → VWR
    op("LDA", "abs", "fta+1")
    op("CLC")
    op("ADC", "imm", ROW_BYTES)
    op("STA", "abs", "fta+1")
    op("BCC", "rel", "fr2")
    op("INC", "abs", "fta+2")
    L("fr2")
    op("JSR", "abs", "addra")
    op("DEC", "abs", "row")
    op("BNE", "rel", "fr1")
    op("RTS")
    L("p4")  # 보이는 중 — 엔진이 그 자리를 덮으면 밑그림에 저장하고 다시 쓴다
    op("LDX", "imm", 2)
    op("JSR", "abs", "passed")
    op("BCC", "rel", "p4go")
    op("JMP", "abs", "p4end")
    L("p4go")
    op("LDA", "abs", SCROLL_Y)  # 보이는 중에 스크롤이 바뀌면 — 8px 한 칸이면 **한 틱 이동**(아래 shift), 그 밖이면 옛 행을 되돌리고(p5) 새 행에 다시 연다(reopen)
    op("CMP", "abs", "byr0")
    op("BNE", "rel", "p4chg")
    op("JMP", "abs", "p4s")
    L("p4chg")
    op("SEC")
    op("SBC", "abs", "byr0")
    op("CMP", "imm", 8)
    op("BEQ", "rel", "shdn")
    op("CMP", "imm", 0xF8)
    op("BEQ", "rel", "shup")
    op("LDA", "imm", 1)
    op("STA", "abs", "reopen")
    if T7_SKIP:
        op("STZ", "abs", "vis")
    op("LDA", "imm", 5)
    op("STA", "abs", "ph")
    op("JMP", "abs", "clrinit")
    # 🔴 한 틱 이동(10-31 — 엔진은 맵을 8px 단위로 스크롤하고 우리 틱은 BYR 쓰기와 같은 VBlank 라, 여기서 다 옮기면 다음 프레임부터 맞는다; 닫고 다시 열면 4~5프레임 한 행 어긋남 = 「흔들림」):
    #   아래로(BYR +8): 옛 행 0(칸 ubase)을 되돌리고 그 칸에 새 바닥 행(옛 행 10)을 읽어 두고 ubase+1 · 위로(−8): 옛 행 9(칸 ubase+9)를 되돌리고 그 칸에 새 꼭대기 행(옛 행 −1)을 읽고 ubase−1.
    #   겹치는 9행의 밑그림은 고리라 그대로. 비용 = TIA 1 + TAI 1 + fastrows(TIA 10) — fastrows 한 틱과 거의 같다.
    L("shdn")
    op("LDA", "abs", "ubase")
    op("JSR", "abs", "slotaddr")
    op("JSR", "abs", "rowinit")  # ra = 옛 행 0
    op("JSR", "abs", "row1w")  # 되돌림
    op("LDA", "abs", "ra")  # ra += 10행(0x280) = 새 바닥 행
    op("CLC")
    op("ADC", "imm", 0x80)
    op("STA", "abs", "ra")
    op("LDA", "abs", "ra1")
    op("ADC", "imm", 0x02)
    op("STA", "abs", "ra1")
    op("JSR", "abs", "row1r")
    op("LDA", "abs", "ubase")
    op("INC")
    op("CMP", "imm", gwin.H)
    op("BCC", "rel", "shd1")
    op("LDA", "imm", 0)
    L("shd1")
    op("STA", "abs", "ubase")
    op("INC", "abs", "rowb")
    op("BRA", "rel", "shfin")
    L("shup")
    op("LDA", "abs", "ubase")  # 칸 = ubase − 1 (mod H) = 옛 행 9 의 칸
    op("DEC")
    op("BPL", "rel", "shu1")
    op("LDA", "imm", gwin.H - 1)
    L("shu1")
    op("STA", "abs", "ubase")  # 새 ubase(= 새 행 0 의 칸)로 미리 둔다
    op("JSR", "abs", "slotaddr")
    op("JSR", "abs", "rowinit")  # ra = 옛 행 0
    op("LDA", "abs", "ra")  # ra += 9행(0x240) = 옛 행 9
    op("CLC")
    op("ADC", "imm", 0x40)
    op("STA", "abs", "ra")
    op("LDA", "abs", "ra1")
    op("ADC", "imm", 0x02)
    op("STA", "abs", "ra1")
    op("JSR", "abs", "row1w")  # 되돌림
    op("JSR", "abs", "rowinit")
    op("LDA", "abs", "ra")  # ra −= 1행(0x40) = 새 꼭대기 행
    op("SEC")
    op("SBC", "imm", 0x40)
    op("STA", "abs", "ra")
    op("LDA", "abs", "ra1")
    op("SBC", "imm", 0)
    op("STA", "abs", "ra1")
    op("JSR", "abs", "row1r")
    op("DEC", "abs", "rowb")
    L("shfin")
    if RASTER:
        op("JSR", "abs", "rcy")
    op("LDA", "abs", SCROLL_Y)
    op("STA", "abs", "byr0")
    op("LDA", "imm", "<win")
    op("LDX", "imm", ">win")
    op("JSR", "abs", "fastrows")  # 새 행에 창 10행 통째로
    op("JMP", "abs", "showinit")
    L("p4s")
    for _ in range(RT_STEADY_ROWS):
        op("JSR", "abs", "sweep1")
    op("LDA", "abs", "row")
    op("BNE", "rel", "r4")
    op("JMP", "abs", "showinit")
    L("r4")
    op("RTS")
    L("p4end")
    op("LDA", "abs", "d+2")
    op("STA", "abs", "pe")
    op("LDA", "abs", "d+3")
    op("STA", "abs", "pe+1")
    op("LDA", "abs", "pg")  # 이 쪽의 타일 칸을 놓는다(타일은 다음 쪽 행이 바뀔 때까지 화면에 남지만, 그 칸에 다음다음 쪽을 그리는 건 `prep` 이 ph=4 까지 기다린다)
    op("AND", "imm", 1)
    op("TAX")
    op("STZ", "absx", "ready0")
    op("INC", "abs", "pg")
    op("LDA", "abs", "pg")
    op("CMP", "abs", "npg")
    op("BEQ", "rel", "p4last")
    op("JSR", "abs", "getdesc")
    op("LDA", "abs", "d")  # 다음 시작 − 이 끝 > GAP_FRAMES 이면 간격 — 창을 닫았다 다시 연다
    op("SEC")
    op("SBC", "abs", "pe")
    op("STA", "abs", "tmp")
    op("LDA", "abs", "d+1")
    op("SBC", "abs", "pe+1")
    op("BNE", "rel", "p4gap")
    op("LDA", "abs", "tmp")
    op("CMP", "imm", GAP_FRAMES)
    op("BCS", "rel", "p4gap")
    op("STZ", "abs", "ph")
    op("RTS")
    L("p4gap")
    if T7_SKIP:
        op("STZ", "abs", "vis")
    op("LDA", "imm", 5)
    op("STA", "abs", "ph")
    op("BRA", "rel", "clrinit")
    L("p4last")
    if T7_SKIP:
        op("STZ", "abs", "vis")
    op("LDA", "imm", 0xFF)
    op("STA", "abs", "last")
    op("LDA", "imm", 5)
    op("STA", "abs", "ph")
    L("clrinit")  # 지우기 — 밑그림을 한 틱에 통째로 되돌린다(읽기 없이, 고리 순서)
    op("STZ", "abs", "wopen")
    if RASTER:
        op("LDA", "abs", "rcon")
        op("BEQ", "rel", "rcoff")
        op("LDX", "abs", "rce1")
        op("JSR", "abs", 0x43FE)  # 분할 빼기
        if RC2 or TOP:
            op("LDX", "abs", "rce2")
            op("JSR", "abs", 0x43FE)
        op("STZ", "abs", "rcon")
        L("rcoff")
    op("JSR", "abs", "ringrows")
    op("STZ", "abs", "row")
    op("RTS")
    L("ringrows")  # 밑그림(행 고리, ubase 칸부터) 10행을 창 행에 쓴다 — fastrows 와 같되 원본 포인터가 고리 끝(win)에서 under 로 되감긴다
    op("LDA", "abs", "ubase")
    op("JSR", "abs", "slotaddr")
    op("LDA", "abs", "dp")
    op("STA", "abs", "rgwa+1")
    op("LDA", "abs", "dp1")
    op("STA", "abs", "rgwa+2")
    op("JSR", "abs", "rowinit")
    L("rgw1")
    op("LDA", "abs", "ra")
    op("LDX", "abs", "ra1")
    op("JSR", "abs", "setw")
    L("rgwa")
    c.raw(bytes([0xE3, 0, 0, P_LO & 0xFF, P_LO >> 8, ROW_BYTES, 0]))  # TIA 밑그림 행 → VWR
    op("LDA", "abs", "rgwa+1")
    op("CLC")
    op("ADC", "imm", ROW_BYTES)
    op("STA", "abs", "rgwa+1")
    op("BCC", "rel", "rgw2")
    op("INC", "abs", "rgwa+2")
    L("rgw2")
    op("LDA", "abs", "rgwa+2")  # 고리 끝(= win)이면 under 로
    op("CMP", "imm", ">win")
    op("BNE", "rel", "rgw3")
    op("LDA", "abs", "rgwa+1")
    op("CMP", "imm", "<win")
    op("BNE", "rel", "rgw3")
    op("LDA", "imm", "<under")
    op("STA", "abs", "rgwa+1")
    op("LDA", "imm", ">under")
    op("STA", "abs", "rgwa+2")
    L("rgw3")
    op("JSR", "abs", "addra")
    op("DEC", "abs", "row")
    op("BNE", "rel", "rgw1")
    op("RTS")
    L("row1w")  # dp/dp1 → 한 행(ra) 쓰기(TIA)
    op("LDA", "abs", "dp")
    op("STA", "abs", "r1w+1")
    op("LDA", "abs", "dp1")
    op("STA", "abs", "r1w+2")
    op("LDA", "abs", "ra")
    op("LDX", "abs", "ra1")
    op("JSR", "abs", "setw")
    L("r1w")
    c.raw(bytes([0xE3, 0, 0, P_LO & 0xFF, P_LO >> 8, ROW_BYTES, 0]))
    op("RTS")
    L("row1r")  # 한 행(ra) 읽기(TAI) → dp/dp1
    op("LDA", "abs", "dp")
    op("STA", "abs", "r1r+3")
    op("LDA", "abs", "dp1")
    op("STA", "abs", "r1r+4")
    op("LDA", "abs", "ra")
    op("LDX", "abs", "ra1")
    op("JSR", "abs", "setr")
    L("r1r")
    c.raw(bytes([0xF3, P_LO & 0xFF, P_LO >> 8, 0, 0, ROW_BYTES, 0]))
    op("RTS")
    L("p5")  # 지우기 끝 처리(clrinit 이 이미 되돌렸다)
    op("LDA", "abs", "row")
    op("BNE", "rel", "r5")
    op("LDA", "abs", "last")
    op("BNE", "rel", "p5end")
    op("STZ", "abs", "ph")  # 간격 뒤 다음 쪽 기다림 · reopen 이면 같은 쪽을 새 행에 다시 연다(p0 → 준비 끝 → 바로)
    op("STZ", "abs", "reopen")
    op("RTS")
    L("p5end")
    op("LDA", "imm", 6)
    op("STA", "abs", "ph")
    op("STZ", "abs", GW_FLAG)  # 작업 7 원래 바이트 복원(`t7off`)은 여기서 못 한다(MPR4 가 코드 뱅크) — 작업 7 쪽 `t7row` 가 ph=6 을 보고 한다
    L("r5")
    L("p6")
    op("RTS")
    L("latch")  # byr0 ← BYR 그림자 · rowb ← ROW0 + (byr0 − 184)/8 (부호 있음, 32행 안)
    op("LDA", "abs", SCROLL_Y)
    op("STA", "abs", "byr0")
    op("SEC")
    op("SBC", "imm", SCROLL_Y0)
    for _ in range(3):  # 부호 있는 /8
        op("CMP", "imm", 0x80)
        op("ROR")
    op("CLC")
    op("ADC", "imm", gwin.ROW0)
    op("AND", "imm", 31)
    op("STA", "abs", "rowb")
    op("RTS")
    L("passed")  # 프레임 수 ≥ d[X..X+1] 이면 C=1
    op("LDA", "abs", "fl")
    op("SEC")
    op("SBC", "absx", "d")
    op("LDA", "abs", "fh")
    op("SBC", "absx", "d+1")
    op("RTS")
    # ── 준비기 — 쪽 qg ≤ pg+1 을 쉬는 칸에 ──
    L("prep")
    op("LDA", "abs", "rs")
    op("BEQ", "rel", "pr0")
    op("JMP", "abs", "rstep")
    L("pr0")
    op("LDA", "abs", "qg")
    op("CMP", "abs", "npg")
    op("BCS", "rel", "pret")
    op("CMP", "abs", "pg")
    op("BEQ", "rel", "pr1")  # qg == pg: 아직 안 보인 쪽 — 바로
    op("LDA", "abs", "pg")
    op("CLC")
    op("ADC", "imm", 1)
    op("CMP", "abs", "qg")
    op("BNE", "rel", "pret")  # qg ≠ pg+1 → 기다린다
    op("LDA", "abs", "ph")  # qg == pg+1: 그 칸은 pg−1 의 것 — pg 의 행이 다 바뀐 뒤(ph=4)라야 화면에서 사라졌다
    op("CMP", "imm", 4)
    op("BNE", "rel", "pret")
    L("pr1")
    op("LDA", "abs", "qg")
    op("AND", "imm", 1)
    op("TAX")
    op("LDA", "absx", "ready0")
    op("BNE", "rel", "pret")  # 그 칸에 아직 안 보인 쪽이 들어 있다
    op("JMP", "abs", "pstart")
    L("pret")
    op("RTS")
    _emit_getdesc16(c, "getdesc", "pg", "d")
    _emit_getdesc16(c, "getdescq", "qg", "dq")
    _emit_vdc(c, rt=True)
    _emit_upload(c, rt=True)
    _emit_rowinit_rt(c)
    _emit_sweep(c, rt=True)
    _emit_render(c)
    # ── 변수 · 표 · 서술표 ──
    for v in ("pg", "qg", "qb", "qb2", "fl", "fh", "b0", "b1", "row", "cnt", "nt", "tmp", "dirty", "ra", "ra1", "sp", "sp1", "dp", "dp1", "vw", "vw1", "tsp", "tsp1",
              "rs", "ncol", "rn", "gl", "gt", "ad", "px", "gcnt", "o0", "o1", "w0", "w1", "bk", "sv", "sh", "shc", "rhi", "rlo", "a1", "a2", "a3",
              "li", "tnl", "tnh", "rp", "rp1", "last", "pli", "pn", "ptl", "pth", "ready0", "ready1", "byr0", "reopen", "pmask", "wopen", "pren", "pfc"):
        L(v)
        c.raw(b"\0")
    L("pe")
    c.raw(b"\0\0")
    L("d")
    c.raw(bytes(DESC))
    L("dq")
    c.raw(bytes(DESC))
    L("recs")
    c.raw(bytes(2 * NREC * 3))
    L("tbl")
    c.raw(bytes(t & 0xFF for t in BANK_TILE0))
    L("tbh")
    c.raw(bytes(t >> 8 for t in BANK_TILE0))
    L("lofs")  # 줄 li 의 위 행 단어 자리(창 그림 안 바이트) — 화자 · 줄1 · 줄2 · 줄3
    c.raw(b"".join(((r - gwin.ROW0) * ROW_BYTES + (gwin.TEXT_COL0 - gwin.COL0) * 2).to_bytes(2, "little") for r in gwin.LINE_ROWS))
    blank = gwin.blank_bat()
    for name, r in (("tpl_t", 0), ("tpl_m", 1), ("tpl_b", gwin.H - 1)):
        L(name)
        c.raw(b"".join(blank[(gwin.ROW0 + r, col)].to_bytes(2, "little") for col in range(gwin.COL0, gwin.COL0 + gwin.W)))
    L("npg")  # 이 씬의 쪽 수(gwsel)
    c.raw(b"\0")
    L("dbase")  # 이 씬의 서술표 주소(gwsel)
    c.raw(b"\0\0")
    L("fiximg")  # 고정 영역 원본 — 통로 `gw` 가 TII 로 $BC00 에 깐다
    c.raw(fixed)
    labels = {**a.labels, **f.labels, **c.labels}
    assert len(labels) == len(a.labels) + len(f.labels) + len(c.labels), "라벨이 세 쪽에 겹친다"
    a.labels = f.labels = c.labels = labels
    return a, f, c, labels


def rt_lines(spk: str | None, text: str, btab: dict[str, bytes]) -> list[tuple[bytes, int]]:
    """쪽 → [(줄 글리프 코드, 기둥 수)…] — `gwin.make_window` 와 같은 줄(화자 + 다시 조판한 한 쪽)."""
    import gwin_ref

    adv = gwin_ref.adv_exceptions(btab)
    out = []
    for ln in ([spk] if spk else []) + gwin.page_lines(spk, text):  # 줄은 명세가 가른 대로(`gwin.page_lines` — 다시 짜면 10칸 규칙에 걸린다)
        codes = font.encode(ln, btab, msg=True)
        w = sum(adv.get(codes[i : i + 2], 12) for i in range(0, len(codes), 2))
        out.append((codes, (w + 7) // 8))
    return out


def rt_advtab(plines: list[list[tuple[bytes, int]]], btab: dict[str, bytes]) -> bytes:
    """전진 px 가 12 가 아닌 코드 중 이 쪽들이 쓰는 것만 — (리드, 트레일, px)… + 0."""
    import gwin_ref

    used = {c[i : i + 2] for lines in plines for c, _ in lines for i in range(0, len(c), 2)}
    adv = gwin_ref.adv_exceptions(btab)
    tab = b"".join(bytes([k[0], k[1], v]) for k, v in sorted(adv.items()) if k in used) + b"\0"
    if len(tab) > 255:
        raise GwinError("전진 표가 색인(X)을 넘는다")
    return tab


def _check_spec(spec: dict, btab: dict[str, bytes]) -> list[list[tuple[bytes, int]]]:
    errs = validate(spec)
    if errs:
        raise GwinError("\n".join(errs))
    pages = spec["pages"]
    plines = [rt_lines(pg.get("speaker"), pg["text"], btab) for pg in pages]
    for pg, lines in zip(pages, plines, strict=True):
        tiles, _ = gwin.make_window(pg.get("speaker"), pg["text"])
        if sum(n for _, n in lines) * 2 != len(tiles) // 8:
            raise GwinError(f"기둥 수가 make_window 와 다르다: {pg['text'][:20]!r}")
        if any(n > LB_COLS - 2 for _, n in lines):
            raise GwinError("줄이 줄 버퍼보다 넓다")
        if sum(n for _, n in lines) * 2 > BANK_TILES:
            raise GwinError(f"쪽 타일 {sum(n for _, n in lines) * 2} > 타일 칸 {BANK_TILES}: {pg['text'][:20]!r}")
    return plines


SCENE_EXTRA: dict[int, list[int]] = {}  # 씬 id → 둘째 이후 음성 호출 자리의 표 열쇠(`_extra_key`) — `container_tail` 이 씬 표와 함께 붙인다
_EXTRA_KEYS: dict[tuple[int, int], int] = {}


def _extra_key(sid: int, idx: int) -> int:
    """둘째 이후 음성 호출 자리의 `slot` 열쇠 — 씬 번호(≤224)와 안 겹치는 0xE1~0xFD 를 (씬, 번호)마다 하나씩 준다."""
    if (sid, idx) not in _EXTRA_KEYS:
        k = 0xE1 + len(_EXTRA_KEYS)
        if k >= 0xFE:
            raise GwinError("둘째 이후 음성 호출 열쇠가 모자란다")
        _EXTRA_KEYS[(sid, idx)] = k
    return _EXTRA_KEYS[(sid, idx)]


SCENE_PARTS: dict[int, dict] = {}  # 씬 id → 씬별 표 재료(`register_scene`) — `container_tail` 이 컨테이너 4번째 뱅크에 모아 붙인다


def register_scene(sid: int, spec: dict, blk: bytes, btab: dict[str, bytes]) -> None:
    """씬의 안 B 표 재료를 등록한다 — 쪽(시작·끝 프레임) · 줄(코드 · 기둥 수 · 화자 줄 플래그 · 블록 안 주소 또는 None) · 전진표."""
    with pos_ctx(spec.get("top", False)):
        _register_scene(sid, spec, blk, btab)


def _register_scene(sid: int, spec: dict, blk: bytes, btab: dict[str, bytes]) -> None:
    pages = spec["pages"]
    plines = _check_spec(spec, btab)
    lines = []
    for pg, pl in zip(pages, plines, strict=True):
        rows = []
        for li, (codes, ncol) in enumerate(pl):
            at = blk.find(codes)
            rows.append((codes, ncol | (0x80 if li == 0 and pg.get("speaker") else 0), BASE + at if at >= 0 else None))
        lines.append(rows)
    SCENE_PARTS[sid] = {"top": bool(spec.get("top", False)), "frames": [(frames(pg["start"]), frames(pg["end"])) for pg in pages], "lines": lines, "advtab": rt_advtab(plines, btab)}


def container_tail(sids: list[int]) -> tuple[bytes, dict[str, int]]:
    """컨테이너 4번째 뱅크 바이트 — 공용 렌더러 + 고정 영역 원본 + 씬별 표(전진표 · 서술표 · 줄 표 · 블록에 없는 줄 코드) + 디렉터리. (바이트, 라벨)."""
    sids = sorted({k for sid in sids for k in [sid, *SCENE_EXTRA.get(sid, [])]})  # 씬 + 그 씬의 둘째 이후 음성 호출 열쇠
    tops = {SCENE_PARTS[sid]["top"] for sid in sids}
    if len(tops) > 1:
        raise GwinError(f"한 컨테이너에 창 위치가 다른 씬이 섞였다(씬 {sorted(sids)}) — 코드 영역은 컨테이너마다 한 벌")
    with pos_ctx(tops.pop() if tops else False):
        return _container_tail(sids)


def _container_tail(sids: list[int]) -> tuple[bytes, dict[str, int]]:
    _a, _f, c, lab = program_b(BASE, 0)
    for sid in sorted(sids):
        p = SCENE_PARTS[sid]
        c.L(f"adv{sid}")
        c.raw(p["advtab"])
        tabs_len = sum(4 * len(rows) + 1 for rows in p["lines"])  # 줄 표(줄마다 4B + 끝 0)를 먼저 다 놓고, 블록에서 못 찾은 줄 코드는 그 뒤에
        tabs, extra, descs = bytearray(), bytearray(), bytearray()
        c.L(f"desc{sid}")
        base = c.pc + DESC * len(p["lines"])
        for (st, en), rows in zip(p["frames"], p["lines"], strict=True):
            t_at = base + len(tabs)
            for codes, flag, addr in rows:
                if addr is None:
                    addr = base + tabs_len + len(extra)
                    extra += codes
                tabs += bytes([flag, len(codes) // 2]) + addr.to_bytes(2, "little")
            tabs.append(0)
            descs += st.to_bytes(2, "little") + en.to_bytes(2, "little") + b"\0\0" + t_at.to_bytes(2, "little") + b"\0\0"
        assert len(tabs) == tabs_len
        c.raw(bytes(descs) + bytes(tabs) + bytes(extra))
    c.L("dir")
    for sid in sorted(sids):
        if not 0 <= sid < 0xFF or len(SCENE_PARTS[sid]["frames"]) > 0xFF:
            raise GwinError(f"scn{sid:03d}: 디렉터리 항목 범위 밖")
        c.raw(bytes([sid]))
        c.word(f"desc{sid}")
        c.word(f"adv{sid}")
        c.raw(bytes([len(SCENE_PARTS[sid]["frames"])]))
    c.raw(b"\xff")
    code = bytearray(c.bytes())
    t2 = lab["tai2"] - CODE_ORG
    code[t2 + 3 : t2 + 5] = lab["buf"].to_bytes(2, "little")  # TAI 버퍼 목적지는 늘 `buf`
    if len(code) > CODE_MAX:
        raise GwinError(f"안 B 코드 영역 {len(code)}B > {CODE_MAX}B(씬 {sorted(sids)})")
    return bytes(code), lab


def fixed_image(lab: dict[str, int], code: bytes) -> bytes:
    """코드 영역 안의 고정 영역 원본(`fiximg` — 통로 `gw` 가 $BC00 에 깐다)."""
    o = lab["fiximg"] - CODE_ORG
    return code[o : o + lab["fixend"] - FIXED_ORG]




def called_name(blk: bytes, m: "M.Message", msgs: dict, speakers: dict[str, str]) -> str | None:
    """화자 머리가 없는 메시지 바로 앞의 `10 addr`(공유 하위 문구 호출)이 **이름만 있는 메시지**면 그 이름 — OFF 흐름이 「시녀」를 찍는 길(씬 6 `10 1D A8`, 마스터 10-31 gon 001)."""
    if m.start >= 3 and blk[m.start - 3] == 0x10:
        addr = (blk[m.start - 2] | blk[m.start - 1] << 8) - BASE
        for mm in msgs.values():
            if mm.start == addr and mm.speaker and not mm.jp.strip():
                return speakers.get(mm.speaker, mm.speaker)
    return None


def common_speaker(nn: int) -> str:
    """공용 화자 `09 nn` 의 우리 표기 — 파티 캐릭터 레코드(뱅크 0x74 +0x330, 64B × 4)의 이름을 시스템 문구 빌드(`sysbuild`)와 같은 길로 읽는다."""
    import sysbuild as SB
    import sysstrings as S

    r = S.read_speakers()[nn]
    kr = SB.fixed_kr("speakers", r["jp"], SB._load("names.json"), SB.glossary())
    if not kr:
        raise GwinError(f"공용 화자 {nn} 의 우리 표기가 없다")
    return kr



INLINE_LEAD_KEYS = {"9223868c8171327f"}  # `translate.INLINE_LEAD` 와 같은 열쇠 — translate 를 import 하면 순환이다
LEAD = 0.05  # 초 — 비모달 자막 쪽을 시작 시각보다 미리 시작하는 양. 안 B 는 미리 읽기 1틱 + 쓰기 1틱이라 3프레임이면 된다(gb12 실측 — 0.5초였을 땐 씬 6 라이아스
#   첫 쪽이 전환 맵 그리기(11400~11416)보다 먼저 떠 맵에 덮였다)


def audit_absent(sid: int, k: int | None = None, voice_gate=None) -> set[tuple[str, int]]:
    """`script/voice_audit.json` 의 「없음」 쪽 (메시지 열쇠, 쪽 1부터) — 그 씬의 시각표 토막(`scn<씬>_s*`)만."""
    p = common.GAME_DIR / "script" / "voice_audit.json"
    if not p.exists():
        return set()
    import voice_editor_data as VED

    legacy = set(VED.LEGACY_CLIP.values())  # 옛 토막 이름을 쓰는 시각표 장면(scn017_x0·scn040_g0·scn196_g0 …)
    # 🔴 토막(`k`)을 알면 그 토막 줄만 — 같은 메시지 열쇠가 두 토막(분기)에 있으면 한쪽의 「없음」(예 46 s0 「짐이」 — 돈 갈래 음성엔 없음)이 다른 토막(s1 짐 갈래 음성엔 있음)의 쪽까지 지웠다(11-08)
    only = None if k is None else VED.LEGACY_CLIP.get((sid, voice_gate), f"scn{sid:03d}_s{k}")
    return {(r["key"], r["page"]) for r in json.loads(p.read_text("utf-8"))["rows"] if r["voice_match"] == "없음" and (r["clip"].startswith(f"scn{sid:03d}_s") or (r["clip"] in legacy and r["clip"].startswith(f"scn{sid:03d}_"))) and (only is None or r["clip"] == only)}


ON_WIDE_SPLIT: list[tuple[int, str, int]] = []  # 타일 칸을 넘어 둘로 쪼갠 자막 쪽 (씬, 열쇠, 쪽) — 보고용
ON_OVERFLOW: list[tuple[int, str, int, int]] = []  # on_flow_spec 이 합친 줄 수 초과 쪽 (씬, 열쇠, 조판 쪽 수, 시각표 쪽 수) — 시험 굽기 보고용


def on_flow_spec(sid: int) -> dict:
    """씬의 비모달 자막 명세 — 시각표 토막(`voice_sched.json` 의 씬 목록)마다 음성 호출 자리 하나. 첫 토막이 본 명세이고 나머지는 `extra` 로 매단다(11-05: 게이트·분기가 둘 이상인 씬
    — 168·88·196·151 은 게이트마다, 46·50·63 은 한 게이트의 음성 호출마다 — 이 첫 토막만 자막이 붙던 구멍을 막는다)."""
    import voice_sched as VS

    n = len(VS.load(drafts=True)[str(sid)])
    spec = _on_flow_spec(sid, 0)
    extra = [_on_flow_spec(sid, k) for k in range(1, n)]
    if extra:
        spec["extra"] = extra
    return spec


def _on_flow_spec(sid: int, k: int = 0) -> dict:
    with typeset.on_flow():  # 음성 자막 조판 — 종전 쪽 나눔(마스터 11-11)
        return _on_flow_spec_(sid, k)


def _on_flow_spec_(sid: int, k: int = 0) -> dict:
    """**원판 ON 흐름을 그대로 두고** 음성 시각표(`voice_sched.json` 씬의 `ends` · `on_overlay`)로 만든 비모달 자막 명세(시제품 — `ED_GWIN_ON=<씬>` 시험 빌드).
    쪽 = 시각표의 메시지 쪽(엔진이 ON 에서도 띄우는 창 `on_overlay.skip` 은 뺀다), 시작 = 앞 쪽 끝(또는 `starts` 마스터 열림), 끝 = 시각표 끝."""
    import voice_editor_data as VED
    import voice_sched as VS

    seg = VS.load(drafts=True)[str(sid)][k]  # 초안(마스터 검수 전)도 시험 빌드엔 올린다 — 제품은 `load()` 가 뺀다
    ov = seg.get("on_overlay", {})
    blk = Path(sorted(common.OUT_DIR.glob(f"text/*_{sid:03d}.bin"))[0]).read_bytes()
    msgs = {m.key: m for m in M.parse(blk)}
    tr, sp = M.load_translations(sid), M.load_speakers()
    pages, prev, prev_end = [], 0.0, 0.0
    absent = audit_absent(sid, k, seg.get("voice_gate"))  # 음성에 없는 쪽(voice_audit 「없음」, 마스터 11-03 「음성이 없으면 자막도 빼야지」)
    for it in seg["msgs"]:
        m = msgs[it["key"]]
        text = ov.get("text", {}).get(it["key"]) or VED.joined_kr(blk, it["key"], tr, {x["key"] for x in seg["msgs"]}) or tr[it["key"]]["t"]  # 같은 창 이음·이름 변수(「로우」「게일」)까지 채운 문안(편집기와 같은 자료)
        spk_arg = False if it["key"] in INLINE_LEAD_KEYS else (M.speaker_kind(m, sid) or bool(it.get("speaker")))
        # 마스터 11-10 「첫줄 13칸은 음성자막만」 — ON 자막 창은 이름을 제 행에 그리니 첫 줄 10칸 규칙(이름 곁 밀림)이 필요 없다. 13칸으로 짜되 쪽 수가 늘거나 갈리면 종전(`nl=` 가드).
        pgs = typeset.pages(font.expand_packed(text), speaker="nl=" if spk_arg is True else spk_arg, four=True, keep_windows=typeset.keep_windows(sid))
        if it.get("split"):  # 11-04 OFF 창과 같은 경계 — 한 창으로 이어진 원문 메시지 둘을 두 자막 쪽으로(뒷 조각엔 이름이 없다). 끝 시각은 `on_overlay.ends[열쇠]` = [앞 조각 끝, 뒷 조각 끝]
            import voice_sched as VS2

            lst = list(msgs.values())
            parts = VS2.tail_join(blk, lst, next(k for k, x in enumerate(lst) if x.key == it["key"]), tr, parts=True)
            pgs = typeset.pages(font.expand_packed(parts[0][1]), speaker="nl=", four=True, keep_windows=typeset.keep_windows(sid)) + typeset.pages(font.expand_packed(parts[1][1]), speaker=False, four=True, keep_windows=typeset.keep_windows(sid))
        ends = VS.fit_ends(ov.get("ends", {}).get(it["key"], it["ends"]), len(pgs))  # 원문 창 기준으로 합쳐 쪽이 줄었으면 끝 시각도 합친다
        if len(pgs) > len(ends):  # 줄 수 초과로 조판이 쪽을 더 가른다 — 막지 않고 그대로 굽는다(마스터 11-03 「칸 초과가 어떻게 나오는지도 봐야지」). 시각표의 마지막 쪽 구간(앞 쪽 끝~끝)을 넘친 쪽 수로 균등 나눈다
            ON_OVERFLOW.append((sid, it["key"], len(pgs), len(ends)))
            k = len(pgs) - len(ends) + 1
            s0 = ends[-2] if len(ends) > 1 else max(ov.get("starts", {}).get(it["key"], 0.0), prev_end)
            ends = [*ends[:-1], *[round(s0 + (ends[-1] - s0) * (j + 1) / k, 2) for j in range(k)]]  # 비모달 전용 끝 시각 — 엔진이 ON 에서도 띄우는 창(장비 셋, 13.05초)과 겹치지 않게 앞 쪽을 일찍 닫는다(10-31 실측: 겹치면 훑기가 엔진 창 틀을 지운다)
        assert len(pgs) == len(ends), (it["key"], len(pgs), ends)
        for i, (pg, end) in enumerate(zip(pgs, ends, strict=True)):
            if it["key"] in ov.get("skip", []):
                prev = end
                continue
            if (it["key"], i + 1) in absent:  # 음성에 없는 쪽 — ON 자막 목록에서 뺀다(OFF 창 문안은 그대로). 앞 쪽은 제 끝 시각까지 그대로 떠 있다
                if os.environ.get("ED_GWIN_ABSENT") == "flash":  # 비교용(시험) — 쪽 끝 시각을 앞 쪽에 붙여 즉시 넘김: 시작 = 끝 = 앞 쪽 끝(한 틱 번쩍)
                    start = max(prev_end, prev)
                    spk = None
                    pages.append({"speaker": spk, "text": "\n".join(pg), "start": round(start, 2), "end": round(start + 0.1, 2)})
                    prev = prev_end = round(start + 0.1, 2)
                    continue
                prev = end  # 뺀 쪽의 시간 구간은 비운다 — 다음 쪽은 시각표의 자기 시작(이 쪽 끝)에서 연다
                continue
            if i == 0 and it["key"] in ov.get("starts", {}):  # 마스터가 연 시각(starts)을 준 쪽은 **보이는 앞 쪽 끝**까지만 기다린다 — 뺀(안 나가는) 줄의 시각표 끝이 이 쪽 열림을 늦추지 않게(46·062, 11-08)
                start = max(prev_end, ov["starts"][it["key"]])
            else:
                start = max(prev, ov.get("starts", {}).get(it["key"], 0.0) if i == 0 else prev)
            start = max(prev_end, start - LEAD) if pages else start  # 리드 — 미리 읽기·쓰기 틱이 도는 동안 미리 시작한다(앞 쪽이 끝난 뒤부터)
            spk = (sp.get(it["speaker"], it["speaker"]) if it.get("speaker") else sp.get(m.speaker, m.speaker) if m.speaker else VED.speaker_override(blk, it["key"]) or common_speaker(m.common) if m.common is not None else called_name(blk, m, msgs, sp)) if i == 0 else None  # 이름은 첫 쪽만(이어지는 쪽은 4줄·이름 없음)
            if len(pg) >= 2 and gwin.make_window(spk, "\n".join(pg))[0].__len__() // 8 > BANK_TILES:  # 🔴 타일 칸(133)을 넘는 쪽(씬 196 첫 쪽 134, 11-05) — 자막 쪽만 둘로 쪼갠다(원문 창·OFF 흐름은 그대로). 이름 줄은 앞 쪽, 끝 시각은 반반
                h = len(pg) // 2
                mid = round(start + (end - start) / 2, 2)
                pages.append({"speaker": spk, "text": "\n".join(pg[:h]), "start": round(start, 2), "end": mid})
                pages.append({"speaker": None, "text": "\n".join(pg[h:]), "start": mid, "end": end})
                ON_WIDE_SPLIT.append((sid, it["key"], i + 1))
                prev = prev_end = end
                continue
            pages.append({"speaker": spk, "text": "\n".join(pg), "start": round(start, 2), "end": end})
            prev = prev_end = end
    for ex in seg.get("on_extra", []):  # 🔴 원문 메시지에 없는 자막 쪽(마스터 편집기 추가 행 idx≥1000 — 한 메시지 안에서 화자가 갈리거나 원문 자막이 빠진 자리). 모달 표(`ends`)엔 안 들어가고 비모달 쪽 목록에만 시각 순서로 끼인다
        epgs = typeset.pages(font.expand_packed(ex["text"]), speaker="nl=", four=True, keep_windows=typeset.keep_windows(sid))
        assert len(epgs) == 1, (sid, ex["id"], len(epgs))  # 한 쪽만 — 여러 쪽이면 행을 나눠 추가한다
        at = next((j for j, pg_ in enumerate(pages) if pg_["start"] >= ex["start"]), len(pages))
        e_end = min(ex["end"], pages[at]["start"]) if at < len(pages) else ex["end"]  # 다음 쪽의 리드(`LEAD`)가 앞당겨 열리면 그 앞에서 닫는다
        if at and pages[at - 1]["end"] > ex["start"]:  # 마스터 시각이 앞 쪽과 겹치면 앞 쪽을 이 쪽 시작에서 닫는다(한 화면에 창 하나)
            pages[at - 1]["end"] = ex["start"]
        pages.insert(at, {"speaker": sp.get(ex["speaker"], ex["speaker"]), "text": "\n".join(epgs[0]), "start": ex["start"], "end": e_end})
    if os.environ.get("ED_GWIN_ON_SLICE"):  # 시제품: 쪽 자료가 씬 블록(8KB)에 다 안 든다 — 일부 쪽만(예 `3:7`)
        a, _, b = os.environ["ED_GWIN_ON_SLICE"].partition(":")
        pages = pages[int(a) : int(b)]
    spec = {"pages": pages, "top": seg.get("pos") == "top"}
    if (seg.get("voice_gate") is None or k) and seg.get("voice_at"):  # 게이트 밖 음성 호출(ALWAYS 류 — 씬 224 아그니쟈 독백): 호출 자리(블록 오프셋)를 바로
        spec["voice_at"] = int(seg["voice_at"], 16)
    else:
        spec["voice_call_gate"] = seg.get("voice_from", seg["voice_gate"])  # 원판 ON 에서 음성을 트는 게이트(씬 18 은 앞 게이트 — `voice_sched` 의 voice_from)
    return spec


def check_engine_contracts() -> None:
    """래스터 핸들러가 기대는 엔진 바이트를 원판에서 대조한다 — HUD 분할 즉치 복사(`$6083`: ZP `$56/$57` → `$594C/$594E`). 어긋나면 rc2·닫기가 엉뚱한 y 를 쓴다."""
    import common

    bank, off, want = HUD_ENGINE_COPY
    rel = 34 + (bank - 0x68) * 4 + off // common.USER
    got = common.user_sector(rel)[off % common.USER : off % common.USER + len(want)]
    if got != want:
        raise GwinError(f"엔진 HUD 분할 즉치 복사 코드가 기대와 다르다(뱅크 {bank:#x} +{off:#06x}): {got.hex()} ≠ {want.hex()}")


def patch_block(sid: int, blk: bytes, spec: dict | None = None, btab: dict[str, bytes] | None = None, code_bank: int = CODE_SECTOR // 4) -> tuple[bytes, int]:
    spec = spec or load().get(str(sid))
    if not spec:
        return blk, 0
    with pos_ctx(spec.get("top", False)):
        out, n = _patch_block(sid, blk, spec, btab, code_bank)
    ds = os.environ.get("ED_DEBUG_START")
    if ds and n and str(sid) in ds.split(","):  # 🔴 디버그 전용(시험 빌드) — 씬 블록 머리 점프를 첫 음성 호출 자리(스텁 호출)로 돌려 로드하면 음성·자막이 바로 시작된다(마스터 싱크 확인용, 「디버그 시작」)
        assert common.BUILD_TAG.startswith(("test-", "pce-ed1-voicecheck")), "ED_DEBUG_START 는 시험 빌드(ED_BUILD_TAG=test-* · 마스터 싱크 확인용 pce-ed1-voicecheck)에서만"
        m = re.search(rb"\x20[\x00-\xff][\xa0-\xbf]\xea\xea\xea\xea", out)
        if m:
            b = bytearray(out)
            b[1], b[2] = (0xA000 + m.start()) & 0xFF, (0xA000 + m.start()) >> 8
            out = bytes(b)
    return out, n


def _patch_block(sid: int, blk: bytes, spec: dict, btab: dict[str, bytes] | None, code_bank: int) -> tuple[bytes, int]:
    if "voice_call_gate" in spec or "voice_at" in spec:  # 음성 호출(JSR $5815 + 인라인 4B) 자리에서 시작한다 — 호출을 스텁 안에 복사하고 그 뒤에 초기화
        # 🔴 음성 호출 자리마다 스텁 + 블록 쪽 프로그램을 한 벌씩(11-05): 토막이 둘 이상인 씬(`spec["extra"]`)은 두 번째부터 열쇠(`slot`)를 `_extra_key` 로 받아 컨테이너 코드 영역 디렉터리에 따로 선다
        orig_blk = bytes(blk)
        out = bytearray(blk)
        SCENE_EXTRA[sid] = []
        patches = []
        for idx, sp in enumerate([spec, *spec.get("extra", [])]):
            if "voice_at" in sp:  # 게이트 밖 호출 — 자리를 바로 받는다(그 자리에 진짜 호출이 있어야 한다)
                v = N.VOICE_AT.match(orig_blk, sp["voice_at"])
                if not v:
                    raise GwinError(f"scn{sid:03d}: +{sp['voice_at']:#x} 에 음성 호출이 없다")
            else:
                gates = [m.start() for m in re.finditer(re.escape(N.GATE), orig_blk)]
                g = gates[sp["voice_call_gate"]]
                tgt = g + 5 + orig_blk[g + 4]
                v = N.VOICE_AT.search(orig_blk, g + 5, tgt)
                if not v:
                    raise GwinError(f"scn{sid:03d}: 게이트 {sp['voice_call_gate']} 의 ON 경로에 음성 호출이 없다")
            key = sid if idx == 0 else _extra_key(sid, idx)
            if idx:
                SCENE_EXTRA[sid].append(key)
            stub_at = BASE + len(out)
            stub_len = 7 + 3 + 1
            if RT:
                if btab is None:
                    raise GwinError(f"scn{sid:03d}: 안 B 는 번역 블록의 글리프 표가 있어야 한다")
                register_scene(key, sp, bytes(out), btab)  # 표는 컨테이너 4번째 뱅크(`container_tail`)에
                a, _f, _c, lab = program_b(stub_at + stub_len, key, code_bank)
                body, gw = a.bytes(), lab["gw"]
            else:
                body, gw = build(sp, stub_at, stub_len)
            stub = orig_blk[v.start() : v.start() + 7] + b"\x20" + gw.to_bytes(2, "little") + b"\x60"
            out += stub + body
            patches.append((v.start(), stub_at))
        if len(out) > (BLOCK_MAX if RT else 0x2000):
            raise GwinError(f"scn{sid:03d}: 자막을 붙이면 블록이 {len(out)}B — 한계를 넘는다")
        for at, stub_at in patches:
            out[at : at + 7] = b"\x20" + stub_at.to_bytes(2, "little") + b"\xea" * 4
        return bytes(out), 1
    if RASTER:
        check_engine_contracts()
    hook_at, expect = int(spec["hook"], 16), int(spec["expect"], 16)
    out = bytearray(blk)
    if out[hook_at] != 0x20 or (out[hook_at + 1] | out[hook_at + 2] << 8) != expect:
        raise GwinError(f"scn{sid:03d} +{hook_at:#x}: `JSR {expect:#06x}` 가 아니다 — {bytes(out[hook_at:hook_at + 3]).hex()}")
    stub_at = BASE + len(out)
    body, gw = build(spec, stub_at)
    stub = bytes(out[hook_at : hook_at + 3]) + b"\x20" + gw.to_bytes(2, "little") + b"\x60"
    out += stub + body
    if len(out) > 0x2000:
        raise GwinError(f"scn{sid:03d}: 인사 창을 붙이면 블록이 {len(out)}B — 뱅크(8KB)를 넘는다")
    out[hook_at + 1 : hook_at + 3] = stub_at.to_bytes(2, "little")
    return bytes(out), 1
