"""월드를 안 멈추는 **대사창 모양 자막**의 런타임 — 장면 초기화(`JSR $6F7D` 바로 뒤)에서 돈다(마스터 10-12 「b로 해보자」).

대사창은 월드를 멈추는 모달이라 연출과 동시에 못 쓴다(장면 2 실측). 그래서 **엔진 창과 같은 BG 타일**로 BAT 에 창을 직접 그린다(`gwin.py` — 틀 타일 0x500~0x508 은
늘 VRAM 에 있고, 글자는 0x660~0x6AF 기둥 타일). 월드는 장면 초기화가 `$5BCF`(1프레임 대기)로 양보하는 동안 그대로 흐른다(실측: 4초를 그렇게 기다려도 라이아스 컷신이 정상).

  · 매 프레임 창 영역(BAT 열 3~24 · 행 11~20, 220단어)을 읽어 **우리 창이 아니면 그 단어를 「밑그림」에 저장**하고 우리 창으로 다시 쓴다 — 장면 2 는 시작 약 2초에 엔진이
    맵 타일을 그 자리에 그린다(페이드 중). 인사가 끝나면 밑그림을 되돌려 맵이 그대로 남는다.
  · VDC 접근은 `SEI` 로 감싼다(IRQ1 핸들러도 VDC 레지스터를 쓴다). 행 단위로 짧게.
  · 코드·데이터는 전부 씬 블록 꼬리(RAM)에 산다 — 자기 수정(TIA/TAI 피연산자)도 거기서 한다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import gwin
import hook
import messages as M
import narration_gates as N

SPEC = common.GAME_DIR / "script" / "voice_gwin.json"
BASE = M.BASE
FPS = 59.826
CLOCK_F, CLOCK_S = 0xC1B2, 0xC1B3  # 플레이 시계: 초 안 프레임 · 초(하위 바이트)
P_SEL, P_LO, P_HI = 0x0000, 0x0002, 0x0003  # VDC 포트(ST0 = 레지스터 선택)
ROW_BYTES = gwin.W * 2  # 창 한 행 = 22단어 = 44B
RA0 = gwin.ROW0 * 64 + gwin.COL0  # 창 왼쪽 위의 BAT 단어 주소(707)
TILE_WORD = gwin.TILE0 * 16  # 글자 타일의 VRAM 단어 주소
DESC = 10  # 쪽 서술: 시작 프레임(2) · 끝 프레임(2) · 타일 수(1)+0 · 타일 압축본 주소(2) · 창 단어 주소(2)
OPS = dict(hook.OPS)
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
        elif mode == "tma":
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
    # ── VDC 주소 ──
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
        op("RTS")
    # ── 글자 타일 올리기 — 틱마다 UPT 개씩 ──
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
    L("upload")
    op("LDA", "abs", "nt")
    op("BNE", "rel", "u0")
    op("RTS")
    L("u0")
    op("CMP", "imm", UPT)
    op("BCC", "rel", "u1")
    op("LDA", "imm", UPT)
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
    # ── 창 영역 훑기 ──
    L("rowinit")
    op("LDA", "imm", RA0 & 0xFF)
    op("STA", "abs", "ra")
    op("LDA", "imm", RA0 >> 8)
    op("STA", "abs", "ra1")
    op("LDA", "imm", gwin.H)
    op("STA", "abs", "row")
    op("RTS")
    L("startfull")  # 이 쪽의 글자 창을 목표로
    op("LDA", "abs", "d+8")
    op("LDX", "abs", "d+9")
    L("sweepinit")  # A·X = 목표 이미지 주소(220단어) — 새 훑기를 시작한다
    op("STA", "abs", "sp")
    op("STX", "abs", "sp1")
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
    # 우리 것(= 틀·바탕 타일 0x500~0x508 또는 글자 타일 0x660~0x6AF, 팔레트 8)이면 밑그림에 저장하지 않는다
    op("LDA", "absy", "buf+1")
    op("CMP", "imm", 0x85)
    op("BNE", "rel", "c6")
    op("LDA", "absy", "buf")
    op("CMP", "imm", 9)
    op("BCC", "rel", "ours")
    op("BRA", "rel", "nours")
    L("c6")
    op("CMP", "imm", 0x86)
    op("BNE", "rel", "nours")
    op("LDA", "absy", "buf")
    op("SEC")
    op("SBC", "imm", 0x60)
    op("CMP", "imm", 0x50)
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
    # ── 변수 · 버퍼 · 밑그림 · 서술표 ──
    for v in ("ph", "pg", "fl", "fh", "b0", "b1", "row", "cnt", "nt", "tmp", "dirty", "ra", "ra1", "sp", "sp1", "dp", "dp1", "vw", "vw1", "tsp", "tsp1"):
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


def build(spec: dict, org: int) -> tuple[bytes, int]:
    """스텁 · 코드 · 자료를 이어 붙인 바이트(주소 `org` 부터)와 초기화 진입 주소. 스텁은 `JSR 원래` 를 먼저 한 뒤 `gw` 를 부르고 `RTS` 한다(`gw` 는 곧바로 돌아온다)."""
    errs = validate(spec)
    if errs:
        raise GwinError("\n".join(errs))
    pages = spec["pages"]
    stub_len = 3 + 3 + 1
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


def patch_block(sid: int, blk: bytes) -> tuple[bytes, int]:
    spec = load().get(str(sid))
    if not spec:
        return blk, 0
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
