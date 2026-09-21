"""오프닝 나레이션 자막 — 타이틀 모듈(rel 322)에 **스프라이트 자막**을 심는다 (2026-09-20).

    python3 games/pce-ed1/tools/opening_sub.py            # 조립 결과·크기·타임라인 확인
    python3 games/pce-ed1/tools/opening_sub.py --preview  # 줄 스트립을 PNG 로(work/review/opening/)

왜 이렇게 만드나(조사 근거는 docs/devlog.md 2026-09-20 (9)):
  · 별하늘 나레이션은 **타이틀 모듈(rel 322, 뱅크 0x68~0x80)** 이 돌린다(rel 514 가 아니다). 그
    모듈엔 글자를 그리는 코드가 없고, 배경은 장면마다 VRAM 을 통째로 다시 채우며 팬은 BXR/BYR
    스크롤로 한다 ⇒ BG 타일에 글자를 얹으면 같이 흘러간다. **스프라이트**로 얹는다(모듈은
    스프라이트를 로고·대관식 장면에서만 0~39번까지 쓴다 → 우리는 36~63번).
  · 글자는 실행 중에 안 그린다 — **빌드 때 줄마다 스프라이트 셀(16×16, 흰 글자+검은 테두리)로
    미리 굽고**, 실행 중엔 그 바이트를 VRAM 으로 옮기기만 한다(예행연습 영상과 픽셀이 같다).
  · 우리 데이터(줄 스트립)는 오프닝 내내 비어 있는 뱅크 0x85~0x87·0x6B 에 CD_READ 로 올린다
    (디스크의 빈 섹터 rel 422~437). 코드·표는 모듈 자신의 빈 자리(뱅크 0x6A +0xD40~, 원판 0)에
    넣어 모듈과 같이 적재된다 — CD_PLAY 직전에 도는 초기화가 그 뱅크가 $8000 에 걸린 채로 돈다.
  · 후킹은 셋, 디스크 패치는 **하나**뿐이다: CD_PLAY 호출(`JSR $E012`, 모듈 +0x1AB1) → 우리 init.
    init 이 IRQ1 핸들러의 `JSR $E063`(+0x4A5)과 메인 루프의 `JSR $43F3`(+0x39)을 **RAM 에서**
    트램펄린($2330·$2300)으로 바꿔 끼운다 — 디스크에서 바꾸면 init 전엔 그 자리가 0(BRK)이라
    죽기 때문이다.
  · 시각 원점: 프레임 카운터는 CD_PLAY 복귀에서 0. 자막 시각 = 원점 + 110프레임(영상 t=0)
    + 초×59.826. `script/opening_sub.json` 의 timing 으로 조절한다.
  · 장면이 바뀌면 배경이 VRAM 을 덮으므로, **그림 로드 구간마다 다른 청크 목록**(`tools/data/
    opening_scenes.json`)을 쓴다. VRAM 이 거의 꽉 차 있어(다음 그림 타일을 미리 올려 둔다) 빈 청크만으론
    모자라는 구간은 **뒤 그림이 쓸 청크를 빌려** RAM 에 백업했다가 로드 직전(end)에 되돌린다.
    로드 히트 −150(quiet)부터는 그리지 않는다 — 게임이 히트 전부터 다음 그림을 VRAM 에 쓴다.
  · 시계: 게임은 그림 로드 때 IRQ 를 막아 우리 프레임 카운터가 장면마다 뒤처진다(누적 185프레임).
    사건·장면 프레임은 전부 실측 손실을 뺀 **카운터 눈금**으로 적는다(timing.stalls · scenes 표).

⚠ 사용하는 하드웨어 상수: SAT 는 VRAM $7F00(DVSSR), 스프라이트 팔레트 8번(모듈은 14·15만 쓴다),
   32×32 스프라이트 하나가 **두 줄**(18px 간격)을 담는다 — 위 셀엔 줄 A(0~13행), 아래 셀엔 줄 B 를
   2행 내려(18행부터) 넣는다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import hook
from hook import Asm

from shared import fonts

SUBS = common.GAME_DIR / "script" / "opening_sub.json"
SCENES = Path(__file__).resolve().parent / "data" / "opening_scenes.json"

# ── 조판(예행연습 영상 v13 과 같다) ────────────────────────────────────────
W, H = 256, 232
CELL, ADV_LATIN = 12, 8
LEFT_MARGIN, RIGHT_MARGIN = 20, 20
TOP, LINE_H = 44, 18
LINE_CAP = 10
DY = fonts.GALMURI11_DY
GLYPH_ROWS = 14  # 12px 글리프 + 테두리 → 14행(0~13), 셀 16행 중 14·15는 빈 행

# ── 디스크·메모리 자리 ────────────────────────────────────────────────────
MODULE_REL = 322  # 타이틀 모듈. 모듈 +off ↔ rel 322 + off//2048 : off%2048, 논리 $4000+off (뱅크 0x68+)
CDPLAY_OFF = 0x1AB1  # `JSR $E012`
IRQ_JSR_ADDR = 0x44A5  # IRQ1 핸들러의 `JSR $E063` (모듈 +0x4A5, 뱅크 0x68 = $4000 창)
LOOP_JSR_ADDR = 0x4039  # 메인 루프 마지막 `JSR $43F3` (+0x39)
CODE_OFF = 0x4D40  # 뱅크 0x6A +0xD40 — 원판 0 인 13KB 자리의 머리. 논리 $8D40(MPR4=0x6A)
CODE_ADDR = 0x8000 + (CODE_OFF - 0x4000)
CODE_MAX = 0x5800 - CODE_OFF  # 뱅크 0x6A +0x1800 까지(2.7KB) — 그 뒤 2KB 는 백업 슬롯
DATA_REL = 422  # 빈 섹터 rel 422~449(28개, 원판 0) — 우리는 12개만 쓴다
STRIP_BANKS = (0x85, 0x86, 0x87)  # 오프닝 내내 0 인 뱅크(덤프 29개 실측)
STRIP_BANK_SECTORS = {0x85: 0, 0x86: 4, 0x87: 8}  # DATA_REL 기준 섹터 오프셋
CELL_BYTES = GLYPH_ROWS * 2 * 2  # 셀 = plane0 14행 + plane1 14행, 행마다 2B = 56B
# 빌린 VRAM 청크(512B)의 백업 슬롯 — (뱅크, MPR3 창 $6000 기준 오프셋). 오프닝 내내 0 인 자리들.
BACKUP_SLOTS = (
    [(0x6B, o) for o in range(0, 0x2000, 0x200)]  # 모듈 안의 빈 8KB
    + [(0x6A, o) for o in (0x1800, 0x1A00, 0x1C00, 0x1E00)]  # 코드 뒤
    + [(0x80, 0x1C00), (0x80, 0x1E00)]  # 모듈 마지막 뱅크 꼬리
    + [(0xF8, 0x1A00), (0xF8, 0x1C00)]  # 워크 RAM $3A00~$3DFF
)

TRAMP_MAIN, TRAMP_IRQ = 0x2300, 0x2330  # 워크 RAM(오프닝 내내 0, 12덤프)
RAM_INIT, RAM_INIT_MAX = 0x2380, 0xC0  # init 본체(BIOS CD_READ·CD_PLAY 호출) — $2380~$243F
SAT_SHADOW = 0x2440  # 우리 SAT 항목 28개 그림자(28×8 = 224B, $2440~$251F) — 그리기는 여기에, VRAM 엔 flush 가 쓴다
SAT_GAMETMP = 0x2540  # 게임 스프라이트 항목 옮길 때 임시(최대 24개 × 8 = 192B, $2540~$25FF)
V_FRAME, V_EVIDX, V_PAGE, V_SCENE, V_DIRTY, V_SIG, V_INIT, V_SCNPTR, V_SIGADDR = (
    0x2350, 0x2352, 0x2353, 0x2354, 0x2355, 0x2356, 0x2358, 0x2359, 0x235B
)
Z_SRC, Z_SCN, Z_T0, Z_T1, Z_T2, Z_T3 = 0xC0, 0xC2, 0xC4, 0xC5, 0xC6, 0xC7  # ZP $2042~$20E6 은 모듈이 안 쓴다
SPR_BASE = 36  # 우리 스프라이트 36~63 (모듈은 로고 0~39·대관식 0~21)
SPR_PER_PAIR = 7  # 32px × 7 = 224px ≥ 216
SPR_ATTR = 0x1188  # CGY=1(32높이) CGX=1(32폭) SPBG=1 팔레트 8
SPR_PAL = 8
SAT_VRAM = 0x7F00
PAL_SHADOW = 0x272E  # IRQ1 핸들러가 TIA 로 VCE 에 올리는 512색 그림자(실측 일치)

hook.OPS.update(
    {
        ("ST0", "imm"): 0x03,
        ("ST1", "imm"): 0x13,
        ("ST2", "imm"): 0x23,
        ("CLI", "imp"): 0x58,
        ("INC", "abs"): 0xEE,
        ("DEC", "abs"): 0xCE,
        ("INC", "zp"): 0xE6,
        ("DEC", "zp"): 0xC6,
        ("CMP", "abs"): 0xCD,
        ("CMP", "zp"): 0xC5,
        ("SBC", "abs"): 0xED,
        ("SBC", "zp"): 0xE5,
        ("SBC", "absx"): 0xFD,
        ("ADC", "abs"): 0x6D,
        ("LDX", "imm"): 0xA2,
        ("LDX", "zp"): 0xA6,
        ("LDY", "abs"): 0xAC,
        ("LDY", "zp"): 0xA4,
        ("STX", "zp"): 0x86,
        ("STX", "abs"): 0x8E,
        ("STY", "zp"): 0x84,
        ("STY", "abs"): 0x8C,
        ("DEY", "imp"): 0x88,
        ("CPX", "imm"): 0xE0,
        ("CPX", "zp"): 0xE4,
        ("CPY", "abs"): 0xCC,
        ("CPY", "imm"): 0xC0,
        ("ORA", "imm"): 0x09,
        ("STA", "absx"): 0x9D,
        ("STZ", "absx"): 0x9E,
        ("LDX", "abs"): 0xAE,
        ("BPL", "rel"): 0x10,
        ("BMI", "rel"): 0x30,
        ("JSR", "abs"): 0x20,
        ("LDA", "zpx"): 0xB5,
        ("STA", "zpx"): 0x95,
        ("ORA", "zp"): 0x05,
        ("LDA", "absy_"): 0xB9,
        ("STZ", "zpx"): 0x74,
        ("TSX", "imp"): 0xBA,
        ("NOP", "imp"): 0xEA,
        ("STA", "absy"): 0x99,
        ("SBC", "izpy"): 0xF1,
        ("ADC", "izpy"): 0x71,
        ("CMP", "izpy"): 0xD1,
        ("ROR", "imp"): 0x6A,
        ("ROL", "imp"): 0x2A,
        ("AND", "abs"): 0x2D,
        ("EOR", "imm"): 0x49,
        ("BIT", "abs"): 0x2C,
    }
)
_orig_op = Asm.op


def _op(self, mn, mode="imp", arg=None):
    if mode == "zpx":
        self.out.append(hook.OPS[(mn, mode)])
        self.out.append(arg & 0xFF)
        return
    return _orig_op(self, mn, mode, arg)


Asm.op = _op


# ── 조판·렌더 ───────────────────────────────────────────────────────────
def _adv(ch):
    return ADV_LATIN if ord(ch) < 0x1100 else CELL


def wrap(text, max_w=W - LEFT_MARGIN - RIGHT_MARGIN):
    words = text.split(" ")
    lines, cur, curw = [], "", 0
    for w_ in words:
        ww = sum(_adv(c) for c in w_) + (ADV_LATIN if cur else 0)
        if curw + ww > max_w and cur:
            lines.append(cur)
            cur, curw = w_, sum(_adv(c) for c in w_)
        else:
            cur = f"{cur} {w_}" if cur else w_
            curw += ww
    if cur:
        lines.append(cur)
    return lines


def render_line(text):
    """한 줄 → (white(14×Wpx), outline(14×Wpx)) 0/1 배열. 영상 스크립트의 draw()+png() 와 같은 규칙."""
    import numpy as np

    bdf = fonts.galmuri()
    wpx = sum(_adv(c) for c in text) + 2
    m = np.zeros((GLYPH_ROWS, wpx), dtype=np.uint8)
    x = 1
    for c in text:
        if c != " ":
            b = bdf.bits(c, dy=DY, rows=LINE_H - 2, width=CELL)[:12]  # 글리프는 0~11행
            if c == "…":  # 한국식 말줄임표 — 마침표 높이(10행)에 점 셋
                b = np.zeros_like(b)
                b[10, [1, 5, 9]] = 1
            h, w_ = b.shape
            w_ = min(w_, wpx - x)  # 마지막 반각 글자는 셀(12)보다 자리(8)가 좁다 — 캔버스 안으로 자른다
            m[1 : 1 + h, x : x + w_] |= b[:, :w_]  # 테두리 1px 여유로 1행·1열 내린다
        x += _adv(c)
    edge = np.zeros_like(m)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                edge |= np.roll(np.roll(m, dy, 0), dx, 1)
    edge &= ~m
    return m, edge


def strip_cells(text):
    """한 줄 → 16×16 셀 바이트 목록. 셀 = plane0(14행×2B, 흰) + plane1(14행×2B, 테두리) = 56B
    (15·16행은 늘 0 이라 안 싣는다 — 런타임이 채운다). 행은 16비트 워드 리틀엔디언,
    **비트 15 가 왼쪽 픽셀**(VDC 스프라이트 규약)."""
    m, edge = render_line(text)
    ncell = (m.shape[1] + 15) // 16
    cells = []
    for c in range(ncell):
        out = bytearray()
        for plane in (m, edge):
            for r in range(GLYPH_ROWS):
                w = 0
                for bit in range(16):
                    x = c * 16 + bit
                    if x < plane.shape[1] and plane[r, x]:
                        w |= 0x8000 >> bit
                out += w.to_bytes(2, "little")
        cells.append(bytes(out))
    return cells


# ── 타임라인 → 페이지·사건 (예행연습 영상 v13 의 규칙 그대로) ─────────────
def timeline(subs, rules):
    """→ (lines[str], pages[list[row line-idx|None]], events[(sec, page_idx)])."""
    cuts = [c for c in rules["scene_cuts"] if c not in rules["cut_ignore"]]
    tail, lead, gap_clear, cap = rules["clear_tail"], rules["scene_lead"], rules["gap_clear"], rules["line_cap"]
    ss = sorted(subs, key=lambda x: x[0])
    ev = [(t, 0, "cut", None) for t in cuts]
    for i, (st, en, text) in enumerate(ss):
        nxt = ss[i + 1][0] if i + 1 < len(ss) else 1e9
        ev.append((en + tail, 1, "end", nxt - en > gap_clear))
        ev.append((st, 2, "start", text))
    ev.sort(key=lambda e: (e[0], e[1]))
    lines: list[str] = []
    def lid(s):
        if s not in lines:
            lines.append(s)
        return lines.index(s)
    committed: list = []
    current = None
    cur_start = None
    pending = False
    states = []  # (t, rows)
    def emit(t):
        rows = committed + (current or [])
        assert len(rows) <= cap, rows
        if not states or states[-1][1] != rows:
            states.append((t, list(rows)))
    for t, _, kind, payload in ev:
        if kind == "start":
            if current:
                committed, current = committed + current, None
            if payload.startswith("\f") and committed:
                committed = []
            payload = payload.lstrip("\f")
            new = ([None] if payload.startswith("\n") else []) + [lid(s) for s in wrap(payload.lstrip("\n"))]
            if len(committed) + len(new) > cap:
                committed = []
            current, cur_start = new, t
        elif kind == "end":
            if current:
                committed, current = committed + current, None
            if pending or payload:
                committed, pending = [], False
        elif kind == "cut":
            if current is None:
                committed = []
            elif t - cur_start <= lead:
                committed = []
            else:
                pending = True
        emit(t)
    pages: list[tuple] = [()]  # 0 = 빈 페이지
    events = []
    for t, rows in states:
        key = tuple(rows)
        if key not in pages:
            pages.append(key)
        events.append((t, pages.index(key)))
    return lines, pages, events


# ── 데이터 묶기 ────────────────────────────────────────────────────────────
def pack_strips(lines):
    """줄 스트립을 뱅크에 순서대로 싣는다(8KB 경계는 안 넘긴다). → (banks{bank: bytes}, table[(bank, off, ncell)])."""
    banks = {b: bytearray() for b in STRIP_BANKS}
    order = list(STRIP_BANKS)
    bi = 0
    table = []
    for text in lines:
        cells = strip_cells(text)
        blob = b"".join(cells)
        assert len(blob) <= 0x2000
        while len(banks[order[bi]]) + len(blob) > 0x2000:
            bi += 1
            if bi >= len(order):
                raise SystemExit("줄 스트립이 뱅크 넷(32KB)을 넘는다")
        b = order[bi]
        table.append((b, len(banks[b]), len(cells)))
        banks[b] += blob
    return {b: bytes(v) for b, v in banks.items()}, table


def frames_of(sec, timing):
    """자막 초 → 런타임 프레임 카운터 값. 벽시계 프레임(원점 = CD_PLAY 복귀)에서, 그 시점까지 게임이
    그림 로드 중 IRQ 를 막아 잃은 프레임(timing.stalls, 실측)을 뺀다 — 카운터는 그만큼 뒤처져 있다."""
    w = int(round(sec * timing["fps"])) + timing["audio_start_offset_frames"]
    loss = 0
    for w0, lost in timing.get("stalls", []):
        if w >= w0:
            loss = lost
    return w - loss


# ── 실행 코드 ──────────────────────────────────────────────────────────────
def runtime(lines_tab, pages, events, scenes, timing) -> bytes:
    """뱅크 0x6A +0xD40(논리 $8D40, MPR4) 에 들어가는 코드 + 표."""
    a = Asm(CODE_ADDR)
    # ── init: JSR 로 들어온다(CD_PLAY 자리). A 에 CD_PLAY 결과를 그대로 돌려줘야 한다.
    a.label("init")
    a.op("LDA", "abs", V_INIT)
    a.op("BEQ", "rel", "init_go")
    a.op("JMP", "abs", 0xE012)  # 재시도 경로 — 이미 초기화됐다
    a.label("init_go")
    a.tii(0, TRAMP_MAIN, 0)  # 자리만 — 아래서 실제 값으로 고친다
    tii_main_pos = len(a.out) - 7
    a.tii(0, TRAMP_IRQ, 0)
    tii_irq_pos = len(a.out) - 7
    a.tii(0, RAM_INIT, 0)
    tii_init_pos = len(a.out) - 7
    a.op("JMP", "abs", RAM_INIT)  # 되돌아갈 주소는 모듈 것 그대로 스택에 있다

    # ── RAM init($2380): BIOS 호출은 여기서 — MPR3~6 을 저장·복원한다 ──
    # 🔴 $F8~$FF 는 CD_READ **와** CD_PLAY 가 같이 쓰는 파라미터 자리다. 우리를 부르기 **직전**
    # 게임이 이미 CD_PLAY 인자(재생할 트랙의 MSF·모드)를 여기 깔아 뒀는데, 우리가 자막 스트립을
    # 읽으려고 CD_READ 를 부르면 그 값을 지워 버린다 — 되돌리지 않으면 **엉뚱한 인자로 진짜
    # CD_PLAY 를 부르게 돼 나레이션이 아예 안 나온다**(2026-09-21, 마스터 "소리가 안 나와"
    # 세 번째 보고 뒤에야 발견 — 자막 시각은 프레임 카운터로만 굴러가서 소리가 나든 안 나든
    # 화면은 똑같이 맞아 보여 이 축을 놓치고 있었다). 그대로 저장해 뒀다 되돌린다.
    ri = Asm(RAM_INIT)
    for m in (3, 4, 5, 6):
        ri.op("TMA", "tma", m)
        ri.op("PHA")
    ri.op("LDX", "imm", 0)
    ri.label("save_f8ff")
    ri.op("LDA", "zpx", 0xF8)
    ri.op("PHA")
    ri.op("INX")
    ri.op("CPX", "imm", 8)
    ri.op("BNE", "rel", "save_f8ff")
    for bank, rel, cnt in ((0x85, DATA_REL, 12),):
        ri.label(f"rd_{bank:02X}")
        for zp, val in ((0xF8, cnt), (0xF9, 0), (0xFA, bank), (0xFB, 0), (0xFC, rel >> 16), (0xFD, (rel >> 8) & 0xFF), (0xFE, rel & 0xFF), (0xFF, 6)):
            ri.op("LDA", "imm", val)
            ri.op("STA", "zp", zp)
        ri.op("JSR", "abs", 0xE009)  # CD_READ — 모듈 자신의 적재 템플릿($408D)과 같은 규약(_dh=6, _bl=뱅크)
        ri.op("CMP", "imm", 0)
        ri.op("BNE", "rel", f"rd_{bank:02X}")
    for v in (V_FRAME, V_FRAME + 1, V_EVIDX, V_PAGE, V_SCENE, V_RESTORED, V_SATDIRTY, V_HIDING):
        ri.op("STZ", "abs", v)
    ri.op("LDA", "imm", 1)
    ri.op("STA", "abs", V_DIRTY)
    ri.op("LDA", "imm", 0xFF)
    ri.op("STA", "abs", V_SIGADDR + 1)  # 서명 없음 표시
    ri.op("STA", "abs", V_LASTPAGE)  # 이전 페이지 없음 표시 — 첫 그리기는 무조건 전부 쓴다
    ri.op("LDA", "imm", "scenes_lo")  # 장면 포인터 = SCENES 표 머리(값은 뒤에서 채운다)
    ri.op("STA", "abs", V_SCNPTR)
    ri.op("LDA", "imm", "scenes_hi")
    ri.op("STA", "abs", V_SCNPTR + 1)
    ri.op("LDX", "imm", 8)  # 게임이 깔아 둔 진짜 CD_PLAY 인자를 되돌린다(반대 순서로 꺼낸다)
    ri.label("restore_f8ff")
    ri.op("DEX")
    ri.op("PLA")
    ri.op("STA", "zpx", 0xF8)
    ri.op("CPX", "imm", 0)
    ri.op("BNE", "rel", "restore_f8ff")
    ri.op("JSR", "abs", 0xE012)  # 진짜 CD_PLAY — 이 복귀가 프레임 원점
    ri.op("PHA")
    ri.op("SEI")
    for addr, tgt in ((IRQ_JSR_ADDR, TRAMP_IRQ), (LOOP_JSR_ADDR, TRAMP_MAIN)):
        ri.op("LDA", "imm", tgt & 0xFF)
        ri.op("STA", "abs", addr + 1)
        ri.op("LDA", "imm", tgt >> 8)
        ri.op("STA", "abs", addr + 2)
    ri.op("LDA", "imm", 1)
    ri.op("STA", "abs", V_INIT)
    ri.op("CLI")
    ri.op("PLA")
    ri.op("STA", "abs", V_TMP_K)  # A 잠시 보관
    for m in (6, 5, 4, 3):
        ri.op("PLA")
        ri.op("TAM", "tam", m)
    ri.op("LDA", "abs", V_TMP_K)
    ri.op("RTS")

    # ── 트램펄린 원본(init 이 워크 RAM 으로 복사) ──
    a.label("tramp_main")
    tm = Asm(TRAMP_MAIN)
    tm.op("TMA", "tma", 4)
    tm.op("PHA")
    tm.op("LDA", "imm", 0x6A)
    tm.op("TAM", "tam", 4)
    tm.op("JSR", "abs", "main")  # 라벨은 바깥 어셈블러 것 — 아래서 손으로 박는다
    tm.op("PLA")
    tm.op("TAM", "tam", 4)
    tm.op("JMP", "abs", 0x43F3)
    a.label("tramp_irq")
    ti = Asm(TRAMP_IRQ)
    ti.op("JSR", "abs", 0xE063)
    ti.op("INC", "abs", V_FRAME)
    ti.op("BNE", "rel", "done")
    ti.op("INC", "abs", V_FRAME + 1)
    ti.label("done")
    ti.op("RTS")

    # ── main: 매 프레임(메인 루프 끝) ──
    a.label("main")
    # 1. 사건: FRAME >= EVENTS[EVIDX].frame 인 동안 페이지 갱신
    a.label("ev_loop")
    a.op("LDA", "abs", V_EVIDX)
    a.op("ASL")
    a.op("CLC")
    a.op("ADC", "abs", V_EVIDX)
    a.op("TAX")  # X = idx*3
    a.op("SEC")
    a.op("LDA", "abs", V_FRAME)
    a.op("SBC", "absx", "events")
    a.op("LDA", "abs", V_FRAME + 1)
    a.op("SBC", "absx", "events+1")
    a.op("BCC", "rel", "ev_done")  # FRAME < ev.frame
    a.op("LDA", "absx", "events+2")
    a.op("STA", "abs", V_PAGE)
    a.op("INC", "abs", V_EVIDX)
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", V_DIRTY)
    a.op("BRA", "rel", "ev_loop")
    a.label("ev_done")
    # 2. 장면. (a) 이 장면의 end <= FRAME 이면 스프라이트부터 숨긴다(그림 로드 직전).
    #          (a') 그 다음 프레임에야 빌린 청크를 되돌린다 — 숨김이 하드웨어에 적용(다음 VBlank)
    #          되기 **전에** 청크 내용을 바꾸면, 아직 그 청크를 보여주는 중인 우리 글자가
    #          배경 원본 바이트로 화면 활성 구간에 찢겨 보인다(마스터 실기 확인 2026-09-21 —
    #          mednafen 은 이 타이밍을 안 봐서 못 잡았다. do_draw 의 HIDING 2단계와 같은 이유).
    #          (b) 다음 장면의 switch <= FRAME 이면 넘어가서(포인터 += 34) 빌릴 청크를 백업하고 다시 그린다.
    # V_RESTORED: 0=평소 1=되돌림 완료(숨은 채 대기) 2=숨기기만 한 상태(다음 프레임에 되돌린다)
    a.label("sc_loop")
    a.op("LDA", "abs", V_SCNPTR)
    a.op("STA", "zp", Z_SCN)
    a.op("LDA", "abs", V_SCNPTR + 1)
    a.op("STA", "zp", Z_SCN + 1)
    a.op("LDA", "abs", V_RESTORED)
    a.op("BEQ", "rel", "sc_check_end")
    a.op("CMP", "imm", 2)
    a.op("BEQ", "rel", "sc_finish_restore")
    a.op("JMP", "abs", "sc_switch")  # 1: 이미 다 됐다
    a.label("sc_check_end")
    a.op("LDY", "imm", SC_END)
    a.op("SEC")
    a.op("LDA", "abs", V_FRAME)
    a.op("SBC", "izpy", Z_SCN)
    a.op("INY")
    a.op("LDA", "abs", V_FRAME + 1)
    a.op("SBC", "izpy", Z_SCN)
    a.op("BCC", "rel", "sc_switch")
    a.op("JSR", "abs", "hide_all")
    a.op("LDA", "imm", 2)
    a.op("STA", "abs", V_RESTORED)
    a.op("JMP", "abs", "main_end")  # 이번 프레임엔 되돌리지 않는다 — 숨김이 적용될 다음 프레임에
    a.label("sc_finish_restore")
    a.op("JSR", "abs", "restore_all")
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", V_RESTORED)
    a.label("sc_switch")
    a.op("LDY", "imm", SCENE_ENTRY + SC_SWITCH)  # 다음 항목의 switch_lo
    a.op("SEC")
    a.op("LDA", "abs", V_FRAME)
    a.op("SBC", "izpy", Z_SCN)
    a.op("INY")
    a.op("LDA", "abs", V_FRAME + 1)
    a.op("SBC", "izpy", Z_SCN)
    a.op("BCC", "rel", "sc_done")
    a.op("CLC")
    a.op("LDA", "abs", V_SCNPTR)
    a.op("ADC", "imm", SCENE_ENTRY)
    a.op("STA", "abs", V_SCNPTR)
    a.op("LDA", "abs", V_SCNPTR + 1)
    a.op("ADC", "imm", 0)
    a.op("STA", "abs", V_SCNPTR + 1)
    a.op("STA", "zp", Z_SCN + 1)
    a.op("LDA", "abs", V_SCNPTR)
    a.op("STA", "zp", Z_SCN)
    a.op("JSR", "abs", "backup_all")
    a.op("STZ", "abs", V_RESTORED)
    a.op("STZ", "abs", V_HIDING)  # 장면 경계는 already hide_all 을 거쳤다 — 새 장면은 곧장 그린다
    a.op("LDA", "imm", 0xFF)
    a.op("STA", "abs", V_LASTPAGE)  # 새 장면 = 새 물리 청크 배정 — 건너뛰기 판정을 리셋한다
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", V_DIRTY)
    a.op("JMP", "abs", "sc_loop")
    a.label("sc_done")
    # 3. 팔레트(매 프레임): 그림자 + VCE 직접. SP8 색1=흰(1FF) 색2=검정(000)
    sp8 = PAL_SHADOW + 0x200 + SPR_PAL * 32
    a.op("LDA", "imm", 0xFF)
    a.op("STA", "abs", sp8 + 2)
    a.op("LDA", "imm", 0x01)
    a.op("STA", "abs", sp8 + 3)
    a.op("STZ", "abs", sp8 + 4)
    a.op("STZ", "abs", sp8 + 5)
    a.op("SEI")
    a.op("LDA", "imm", (0x100 + SPR_PAL * 16 + 1) & 0xFF)
    a.op("STA", "abs", 0x0402)
    a.op("LDA", "imm", (0x100 + SPR_PAL * 16 + 1) >> 8)
    a.op("STA", "abs", 0x0403)
    a.op("LDA", "imm", 0xFF)
    a.op("STA", "abs", 0x0404)
    a.op("LDA", "imm", 0x01)
    a.op("STA", "abs", 0x0405)
    a.op("STZ", "abs", 0x0404)
    a.op("STZ", "abs", 0x0405)
    a.op("CLI")
    # 4. 그리기 게이트. 되돌린 상태(그림 로드 중)거나 이 장면의 quiet 을 지났으면 안 그린다 — 게임이 히트 전에
    #    다음 그림 타일을 VRAM 에 쓰기 시작하므로 그 뒤에 우리가 쓰면 그림이 깨진다(실측 2026-09-20). 서명 자가복구는
    #    같은 이유로 뺐다(덮인 걸 되그리면 곧 다음 그림을 망친다). 사건은 계속 쌓이고 switch 때 한 번에 그린다.
    a.op("LDA", "abs", V_RESTORED)
    a.op("BNE", "rel", "main_end")
    a.op("LDY", "imm", SC_QUIET)
    a.op("SEC")
    a.op("LDA", "abs", V_FRAME)
    a.op("SBC", "izpy", Z_SCN)
    a.op("INY")
    a.op("LDA", "abs", V_FRAME + 1)
    a.op("SBC", "izpy", Z_SCN)
    a.op("BCS", "rel", "main_end")  # FRAME >= quiet
    a.op("LDA", "abs", V_DIRTY)
    a.op("BNE", "rel", "do_draw")
    a.label("main_end")
    # 5. SAT: 게임 스프라이트가 있는 장면(game_n>0)은 매 프레임, 아니면 그림자가 바뀐 프레임만 flush
    a.op("LDY", "imm", SC_GAMEN)
    a.op("LDA", "izpy", Z_SCN)
    a.op("BNE", "rel", "do_flush")
    a.op("LDA", "abs", V_SATDIRTY)
    a.op("BNE", "rel", "do_flush")
    a.op("RTS")
    a.label("do_flush")
    a.op("JSR", "abs", "sat_flush")
    a.op("STZ", "abs", V_SATDIRTY)
    a.op("RTS")
    a.label("do_draw")
    # 🔴 화면에 나오는 중인 스프라이트의 VRAM 을 그 자리에서 다시 쓰면(SATB DMA 는 다음
    # VBlank 에야 적용되니 하드웨어가 아직 옛 내용을 보여주는 채로 바이트가 바뀐다)
    # **화면 활성 구간에 찢겨 보인다**(실기·정확한 코어 실측, 2026-09-21 마스터 폰 확인 —
    # mednafen 은 이 타이밍을 안 봐서 못 잡았다). 그런데 **문장이 그냥 한 줄 늘어나는
    # 보통의 경우엔 이전 줄들 내용이 하나도 안 바뀐다** — 그런 페이지 전환까지 매번 숨겼다
    # 그리면 화면이 자꾸 깜빡인다(마스터 지적 2026-09-21: "폰트가 깜빡이는데 안 깜빡이는건
    # 불가능이야?"). ⇒ `check_risky` 로 **실제로 화면에 떠 있는 줄의 내용이 바뀌는 자리가
    # 하나라도 있는지**만 본다 — 없으면(순수 추가·신규 공개) 지연 없이 곧장 그린다.
    # 있으면(「\f」 강제 새 페이지처럼 옛 줄을 진짜로 지우는 경우)만 2단계로 가른다:
    # ① 이번 프레임엔 전부 숨기기만 하고 안 그린다(dirty 는 유지, 숨김은 다음 프레임에 적용) ②
    # 그다음 프레임(HIDING=1)에 실제로 그린다 — 그때는 28개 전부 화면 밖이라 마음대로 써도 안전.
    a.op("LDA", "abs", V_HIDING)
    a.op("BNE", "rel", "dd_go")
    a.op("JSR", "abs", "check_risky")
    a.op("BEQ", "rel", "dd_go")  # 안전 — 지연 없이 곧장
    a.op("JSR", "abs", "hide_all")
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", V_HIDING)
    a.op("JMP", "abs", "main_end")
    a.label("dd_go")
    # 🔴 draw() 가 끝난 **뒤에** V_LASTPAGE 를 갱신한다 — draw() 안의 건너뛰기 판정은 아직
    # "직전에 실제로 그린 페이지"를 봐야 하므로, 미리 지금 페이지로 바꿔 버리면 자기 자신과
    # 비교해 전부 "안 바뀜"으로 오판해 아무것도 안 그리게 된다.
    a.op("JSR", "abs", "draw")
    a.op("LDA", "abs", V_PAGE)
    a.op("STA", "abs", V_LASTPAGE)
    a.op("STZ", "abs", V_DIRTY)
    a.op("STZ", "abs", V_HIDING)
    a.op("JMP", "abs", "main_end")

    # ── draw: 현재 페이지를 현재 장면 청크에 올리고 SAT 를 쓴다 ──
    # 스프라이트 슬롯 s(0~27) = pair*7 + k. 청크 = scene.chunks[보이는 순번]. SAT 36+s.
    a.label("draw")
    a.op("LDA", "imm", 0xFF)
    a.op("STA", "abs", V_SIGADDR + 1)
    a.op("LDA", "abs", V_PAGE)
    a.op("ASL")
    a.op("ASL")
    a.op("ASL")
    a.op("STA", "zp", Z_T2)  # Z_T2 = PAGE*8 (pages 표 인덱스)
    a.op("STZ", "zp", Z_T3)  # Z_T3 = 슬롯 s
    a.op("STZ", "abs", V_TMP_NUSED)  # 이번 그리기에서 쓴 청크 수
    a.label("slot_loop")
    a.op("LDA", "zp", Z_T3)
    a.op("CMP", "imm", 4 * SPR_PER_PAIR)
    a.op("BCC", "rel", "slot_go")
    a.op("JMP", "abs", "draw_fin")
    a.label("slot_go")
    # pair = s // 7, k = s % 7  (7 로 나누기: 뺄셈 루프)
    a.op("LDA", "zp", Z_T3)
    a.op("LDX", "imm", 0)
    a.label("div7")
    a.op("CMP", "imm", SPR_PER_PAIR)
    a.op("BCC", "rel", "div7_done")
    a.op("SBC", "imm", SPR_PER_PAIR)  # C=1 보장
    a.op("INX")
    a.op("BRA", "rel", "div7")
    a.label("div7_done")
    a.op("STA", "abs", V_TMP_K)
    a.op("STX", "abs", V_TMP_PAIR)
    # 줄 A/B 인덱스
    a.op("TXA")
    a.op("ASL")
    a.op("CLC")
    a.op("ADC", "zp", Z_T2)
    a.op("TAX")
    a.op("LDA", "absx", "pages")
    a.op("STA", "abs", V_TMP_LA)
    a.op("LDA", "absx", "pages+1")
    a.op("STA", "abs", V_TMP_LB)
    # 이 슬롯에 셀이 있나: k*2 < ncell(A) or < ncell(B)
    a.op("LDA", "abs", V_TMP_K)
    a.op("ASL")
    a.op("STA", "abs", V_TMP_C)  # 셀 번호 c = 2k
    a.op("LDA", "abs", V_TMP_LA)
    a.op("JSR", "abs", "ncell_of")  # A ← ncell(줄) (0xFF 면 0)
    a.op("CMP", "abs", V_TMP_C)
    a.op("BEQ", "rel", "chk_b")
    a.op("BCS", "rel", "slot_show")
    a.label("chk_b")
    a.op("LDA", "abs", V_TMP_LB)
    a.op("JSR", "abs", "ncell_of")
    a.op("CMP", "abs", V_TMP_C)
    a.op("BEQ", "rel", "slot_hide")
    a.op("BCS", "rel", "slot_show")
    a.label("slot_hide")
    a.op("JSR", "abs", "sat_hide")
    a.op("JMP", "abs", "slot_next")
    a.label("slot_show")
    # 청크 = scene.chunks[n] (512B 단위), n = 이번 그리기에서 보이는 슬롯의 순번.
    # 슬롯 번호(s)가 아니라 순번으로 배정해야 빈 청크가 적은 장면(t160 은 21개)에서
    # 숨긴 슬롯이 청크를 먹지 않는다 — 필요 수는 build_all 이 장면마다 검사한다.
    a.op("LDA", "abs", V_SCNPTR)
    a.op("STA", "zp", Z_SCN)
    a.op("LDA", "abs", V_SCNPTR + 1)
    a.op("STA", "zp", Z_SCN + 1)
    a.op("LDA", "abs", V_TMP_NUSED)
    a.op("INC", "abs", V_TMP_NUSED)
    a.op("CLC")
    a.op("ADC", "imm", SC_CHUNKS)  # chunks 는 항목 +6 부터
    a.op("TAY")
    a.op("LDA", "izpy", Z_SCN)
    a.op("STA", "abs", V_TMP_CHUNK)
    # 청크 단위 512B(=32×32 스프라이트 하나) → VRAM 워드 주소 = chunk*256: hi = chunk, lo = 0
    a.op("STA", "abs", V_TMP_VHI)
    a.op("STZ", "abs", V_TMP_VLO)
    # 첫 스프라이트면 서명 주소 = 그 셀 plane0 3행(워드+3)
    a.op("LDA", "abs", V_SIGADDR + 1)
    a.op("CMP", "imm", 0xFF)
    a.op("BNE", "rel", "sig_set")
    a.op("CLC")
    a.op("LDA", "abs", V_TMP_VLO)
    a.op("ADC", "imm", 3)
    a.op("STA", "abs", V_SIGADDR)
    a.op("LDA", "abs", V_TMP_VHI)
    a.op("ADC", "imm", 0)
    a.op("STA", "abs", V_SIGADDR + 1)
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", V_TMP_SIGWANT)
    a.label("sig_set")
    # 건너뛰기: 직전에 그린 페이지(V_LASTPAGE)의 같은 pair 자리가 지금과 완전히 같은 줄
    # 배정이면(앞줄이 그대로 이어지는 보통의 "한 줄 추가" 전환) VRAM 을 다시 안 쓴다 — 화면에
    # 나오는 중인 스프라이트를 불필요하게 건드리는 걸 원천적으로 줄인다(찢김·깜빡임 둘 다).
    # 🔴 단, do_draw 가 이미 HIDING 경로(위험해서 전부 숨긴 뒤 이 프레임에 그리는 중)라면 이
    # 건너뛰기를 아예 쓰지 않는다 — hide_all 이 SAT 를 이미 다 지워 놨으므로, 내용이 같다고
    # sat_show 까지 건너뛰면 그 슬롯이 다시는 안 나타난다(꺼진 채로 굳는다).
    a.op("LDA", "abs", V_HIDING)
    a.op("BNE", "rel", "slot_write")
    a.op("LDA", "abs", V_LASTPAGE)
    a.op("CMP", "imm", 0xFF)
    a.op("BEQ", "rel", "slot_write")
    a.op("LDA", "abs", V_TMP_PAIR)
    a.op("ASL")
    a.op("STA", "zp", Z_T0)
    a.op("LDA", "abs", V_LASTPAGE)
    a.op("ASL")
    a.op("ASL")
    a.op("ASL")
    a.op("CLC")
    a.op("ADC", "zp", Z_T0)
    a.op("TAX")
    a.op("LDA", "absx", "pages")
    a.op("CMP", "abs", V_TMP_LA)
    a.op("BNE", "rel", "slot_write")
    a.op("LDA", "absx", "pages+1")
    a.op("CMP", "abs", V_TMP_LB)
    a.op("BNE", "rel", "slot_write")
    a.op("JMP", "abs", "slot_next")  # 완전히 같다 — SAT 도 그대로 둔다
    a.label("slot_write")
    # MAWR 설정 후 셀 넷: TL(A,c) TR(A,c+1) BL(B,c,+2행) BR(B,c+1,+2행)
    a.op("JSR", "abs", "set_mawr")
    for which, shift in (("A", 0), ("A", 1), ("B", 0), ("B", 1)):
        a.op("LDA", "abs", V_TMP_LA if which == "A" else V_TMP_LB)
        a.op("STA", "abs", V_TMP_LINE)
        a.op("LDA", "abs", V_TMP_C)
        if shift:
            a.op("INC")
        a.op("STA", "abs", V_TMP_CELL)
        a.op("LDA", "imm", 0 if which == "A" else 2)
        a.op("STA", "abs", V_TMP_SHIFT)
        a.op("JSR", "abs", "put_cell")
    a.op("STZ", "abs", V_TMP_SIGWANT)
    a.op("JSR", "abs", "sat_show")
    a.label("slot_next")
    a.op("INC", "zp", Z_T3)
    a.op("JMP", "abs", "slot_loop")
    a.label("draw_fin")
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", V_SATDIRTY)  # 그림자가 바뀌었다 — main 끝에서 flush
    a.op("RTS")

    # ncell_of: A=줄 인덱스(0xFF=없음) → A=셀 수
    a.label("ncell_of")
    a.op("CMP", "imm", 0xFF)
    a.op("BNE", "rel", "nc_go")
    a.op("CLA")
    a.op("RTS")
    a.label("nc_go")
    a.op("ASL")
    a.op("ASL")
    a.op("TAX")
    a.op("LDA", "absx", "lines+3")
    a.op("RTS")

    # set_mawr: MAWR ← V_TMP_VLO/VHI, 선택 = VWR. (SEI 는 put_cell 안에서 건다 — 여기선 MAWR 만)
    a.label("set_mawr")
    a.op("SEI")
    a.op("ST0", "imm", 0x00)
    a.op("LDA", "abs", V_TMP_VLO)
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "abs", V_TMP_VHI)
    a.op("STA", "abs", 0x0003)
    a.op("LDA", "zp", 0xF7)
    a.op("STA", "abs", 0x0000)
    a.op("CLI")
    a.op("RTS")

    # put_cell: 줄 V_TMP_LINE 의 셀 V_TMP_CELL 을 VWR 로 64워드 쓴다(V_TMP_SHIFT 행 내려서).
    #   줄 없음/셀 범위 밖이면 0 을 64워드. plane2·3 은 늘 0. MPR3 에 스트립 뱅크를 잠깐 건다.
    a.label("put_cell")
    a.op("SEI")
    a.op("ST0", "imm", 0x02)
    a.op("LDA", "abs", V_TMP_LINE)
    a.op("CMP", "imm", 0xFF)
    a.op("BNE", "rel", "pc_a")
    a.op("JMP", "abs", "pc_zero")
    a.label("pc_a")
    a.op("JSR", "abs", "ncell_of")
    a.op("CMP", "abs", V_TMP_CELL)
    a.op("BEQ", "rel", "pc_z2")
    a.op("BCS", "rel", "pc_go")
    a.label("pc_z2")
    a.op("JMP", "abs", "pc_zero")
    a.label("pc_go")
    # src = $6000 + line.off + cell*56 ; MPR3 = line.bank. cell*56 은 16비트 누산(cell ≤ 14)
    a.op("LDA", "abs", V_TMP_LINE)
    a.op("ASL")
    a.op("ASL")
    a.op("TAX")
    a.op("TMA", "tma", 3)
    a.op("STA", "zp", Z_T0)
    a.op("LDA", "absx", "lines")
    a.op("TAM", "tam", 3)
    a.op("LDA", "absx", "lines+1")
    a.op("STA", "zp", Z_SRC)
    a.op("LDA", "absx", "lines+2")
    a.op("STA", "zp", Z_SRC + 1)
    a.op("LDX", "abs", V_TMP_CELL)
    a.op("BEQ", "rel", "pc_src_done")
    a.label("pc_src_add")
    a.op("CLC")
    a.op("LDA", "zp", Z_SRC)
    a.op("ADC", "imm", CELL_BYTES)
    a.op("STA", "zp", Z_SRC)
    a.op("LDA", "zp", Z_SRC + 1)
    a.op("ADC", "imm", 0)
    a.op("STA", "zp", Z_SRC + 1)
    a.op("DEX")
    a.op("BNE", "rel", "pc_src_add")
    a.label("pc_src_done")
    a.op("LDA", "zp", Z_SRC + 1)
    a.op("ORA", "imm", 0x60)
    a.op("STA", "zp", Z_SRC + 1)
    # plane0 · plane1: shift 행 0 → 14행 복사 → (2-shift) 행 0
    for plane in range(2):
        a.op("LDA", "abs", V_TMP_SHIFT)
        a.op("BEQ", "rel", f"p{plane}_copy")
        a.op("STZ", "abs", 0x0002)
        a.op("STZ", "abs", 0x0003)
        a.op("STZ", "abs", 0x0002)
        a.op("STZ", "abs", 0x0003)
        a.label(f"p{plane}_copy")
        a.op("LDY", "imm", plane * GLYPH_ROWS * 2)
        a.label(f"p{plane}_loop")
        a.op("LDA", "izpy", Z_SRC)
        a.op("STA", "abs", 0x0002)
        a.op("INY")
        a.op("LDA", "izpy", Z_SRC)
        a.op("STA", "abs", 0x0003)
        a.op("INY")
        a.op("CPY", "imm", (plane + 1) * GLYPH_ROWS * 2)
        a.op("BNE", "rel", f"p{plane}_loop")
        a.op("LDA", "abs", V_TMP_SHIFT)
        a.op("BNE", "rel", f"p{plane}_tail_done")  # shift=2 면 꼬리 0 행 없음
        a.op("STZ", "abs", 0x0002)
        a.op("STZ", "abs", 0x0003)
        a.op("STZ", "abs", 0x0002)
        a.op("STZ", "abs", 0x0003)
        a.label(f"p{plane}_tail_done")
    a.op("LDA", "zp", Z_T0)
    a.op("TAM", "tam", 3)
    a.op("LDX", "imm", 32)
    a.op("BRA", "rel", "pc_zero_n")
    a.label("pc_zero")
    a.op("LDX", "imm", 64)
    a.label("pc_zero_n")
    a.op("STZ", "abs", 0x0002)
    a.op("STZ", "abs", 0x0003)
    a.op("DEX")
    a.op("BNE", "rel", "pc_zero_n")
    # 서명: 첫 스프라이트의 TL 셀이면 plane0 3행 워드를 기억한다 — VRAM 을 되읽어 둔다
    a.op("LDA", "abs", V_TMP_SIGWANT)
    a.op("BEQ", "rel", "pc_end")
    a.op("STZ", "abs", V_TMP_SIGWANT)
    a.op("ST0", "imm", 0x01)
    a.op("LDA", "abs", V_SIGADDR)
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "abs", V_SIGADDR + 1)
    a.op("STA", "abs", 0x0003)
    a.op("ST0", "imm", 0x02)
    a.op("LDA", "abs", 0x0002)
    a.op("STA", "abs", V_SIG)
    a.op("LDA", "abs", 0x0003)
    a.op("STA", "abs", V_SIG + 1)
    # MAWR 을 다음 셀 자리로 되돌린다(되읽기가 MARR 만 건드리므로 MAWR 은 그대로다)
    a.label("pc_end")
    a.op("LDA", "zp", 0xF7)
    a.op("STA", "abs", 0x0000)
    a.op("CLI")
    a.op("RTS")

    # sat_hide / sat_show: SAT[36+s] 를 쓴다. s = Z_T3. y=64+TOP+36*pair, x=32+xbase+32k
    # sat_hide / sat_show: 그림자 SAT_SHADOW[s] 를 쓴다(VRAM 은 sat_flush 가). s = Z_T3.
    #   y = 64+TOP+36*pair, x = 32+xbase+32k, 패턴 = chunk*8, 속성 SPR_ATTR
    a.label("sat_hide")
    a.op("JSR", "abs", "sat_idx")
    a.op("STZ", "absx", SAT_SHADOW)
    a.op("STZ", "absx", SAT_SHADOW + 1)  # y=0 → 화면 밖
    a.op("RTS")
    a.label("sat_show")
    a.op("JSR", "abs", "sat_idx")
    a.op("LDA", "abs", V_TMP_PAIR)  # y = 64+TOP + 36*pair
    a.op("ASL")
    a.op("ASL")
    a.op("STA", "zp", Z_T1)  # 4p
    a.op("ASL")
    a.op("ASL")
    a.op("ASL")  # 32p
    a.op("CLC")
    a.op("ADC", "zp", Z_T1)  # 36p (≤108)
    a.op("ADC", "imm", 64 + TOP)
    a.op("STA", "absx", SAT_SHADOW)
    a.op("STZ", "absx", SAT_SHADOW + 1)
    a.op("LDA", "abs", V_TMP_K)  # x = 32 + xbase + 32k
    for _ in range(5):
        a.op("ASL")
    a.op("CLC")
    a.op("LDY", "imm", SC_XBASE)
    a.op("ADC", "izpy", Z_SCN)  # xbase (Z_SCN 은 slot_show 에서 세팅됨)
    a.op("STA", "zp", Z_T1)
    a.op("CLA")
    a.op("ADC", "imm", 0)
    a.op("STA", "zp", Z_T0)  # hi
    a.op("LDA", "zp", Z_T1)
    a.op("CLC")
    a.op("ADC", "imm", 32)
    a.op("STA", "absx", SAT_SHADOW + 2)
    a.op("LDA", "zp", Z_T0)
    a.op("ADC", "imm", 0)
    a.op("STA", "absx", SAT_SHADOW + 3)
    a.op("LDA", "abs", V_TMP_CHUNK)  # 패턴 코드 = 워드주소>>5 = chunk*8 (32×32 는 하위 2비트 무시)
    a.op("ASL")
    a.op("ASL")
    a.op("ASL")
    a.op("STA", "absx", SAT_SHADOW + 4)
    a.op("LDA", "abs", V_TMP_CHUNK)
    for _ in range(5):
        a.op("LSR")
    a.op("STA", "absx", SAT_SHADOW + 5)
    a.op("LDA", "imm", SPR_ATTR & 0xFF)
    a.op("STA", "absx", SAT_SHADOW + 6)
    a.op("LDA", "imm", SPR_ATTR >> 8)
    a.op("STA", "absx", SAT_SHADOW + 7)
    a.op("RTS")
    a.label("sat_idx")  # X = s*8
    a.op("LDA", "zp", Z_T3)
    a.op("ASL")
    a.op("ASL")
    a.op("ASL")
    a.op("TAX")
    a.op("RTS")

    # sat_flush: 그림자 28항목 → VRAM SAT[spr_base..] + SATB DMA 예약. 장면의 game_n > 0 이면(게임이 스프라이트를
    #   0..game_n-1 에 매 프레임 쓰는 장면 — 군중) 먼저 게임 항목을 28.. 으로 옮긴다: SAT 번호가 작을수록 앞에 오므로
    #   우리 글자가 게임 스프라이트(사람들) 뒤에 가려지지 않게 우리가 0..27 을 차지한다(실측 2026-09-21).
    a.label("sat_flush")
    a.op("LDY", "imm", SC_GAMEN)
    a.op("LDA", "izpy", Z_SCN)
    a.op("BEQ", "rel", "sf_ours")
    a.op("ASL")
    a.op("ASL")
    a.op("ASL")
    a.op("STA", "zp", Z_T2)  # 게임 항목 바이트 수(≤192)
    a.op("SEI")
    a.op("ST0", "imm", 0x01)  # MARR = $7F00
    a.op("STZ", "abs", 0x0002)
    a.op("LDA", "imm", SAT_VRAM >> 8)
    a.op("STA", "abs", 0x0003)
    a.op("ST0", "imm", 0x02)
    a.op("LDX", "imm", 0)
    a.label("sf_rd")
    a.op("LDA", "abs", 0x0002)
    a.op("STA", "absx", SAT_GAMETMP)
    a.op("INX")
    a.op("LDA", "abs", 0x0003)
    a.op("STA", "absx", SAT_GAMETMP)
    a.op("INX")
    a.op("CPX", "zp", Z_T2)
    a.op("BNE", "rel", "sf_rd")
    a.op("ST0", "imm", 0x00)  # MAWR = $7F00 + 28*4
    a.op("LDA", "imm", (4 * SPR_PER_PAIR * 4) & 0xFF)
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "imm", SAT_VRAM >> 8)
    a.op("STA", "abs", 0x0003)
    a.op("ST0", "imm", 0x02)
    a.op("LDX", "imm", 0)
    a.label("sf_wr")
    a.op("LDA", "absx", SAT_GAMETMP)
    a.op("STA", "abs", 0x0002)
    a.op("INX")
    a.op("LDA", "absx", SAT_GAMETMP)
    a.op("STA", "abs", 0x0003)
    a.op("INX")
    a.op("CPX", "zp", Z_T2)
    a.op("BNE", "rel", "sf_wr")
    a.op("CLI")
    a.label("sf_ours")
    a.op("SEI")
    a.op("ST0", "imm", 0x00)  # MAWR = $7F00 + spr_base*4
    a.op("LDY", "imm", SC_SPRBASE)
    a.op("LDA", "izpy", Z_SCN)
    a.op("ASL")
    a.op("ASL")
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "imm", SAT_VRAM >> 8)
    a.op("STA", "abs", 0x0003)
    a.op("ST0", "imm", 0x02)
    a.op("LDX", "imm", 0)
    a.label("sf_ours_w")
    a.op("LDA", "absx", SAT_SHADOW)
    a.op("STA", "abs", 0x0002)
    a.op("INX")
    a.op("LDA", "absx", SAT_SHADOW)
    a.op("STA", "abs", 0x0003)
    a.op("INX")
    a.op("CPX", "imm", 4 * SPR_PER_PAIR * 8)
    a.op("BNE", "rel", "sf_ours_w")
    a.op("ST0", "imm", 0x13)  # DVSSR = $7F00 → 다음 VBlank 에 SATB DMA
    a.op("ST1", "imm", SAT_VRAM & 0xFF)
    a.op("ST2", "imm", SAT_VRAM >> 8)
    a.op("LDA", "zp", 0xF7)
    a.op("STA", "abs", 0x0000)
    a.op("CLI")
    a.op("RTS")

    # check_risky: V_LASTPAGE(직전에 실제로 그린 페이지) 와 V_PAGE(지금 그릴 페이지) 를 pair
    # 4개(줄 8개) 다 비교해, **전에 뭔가 보이고 있던 pair 의 내용이 지금 달라지는 자리가
    # 하나라도 있으면** "위험"(A=1) — 화면에 나오는 중인 스프라이트 내용을 실제로 바꿔야
    # 하니 숨기고 한 프레임 쉬어야 한다. 전에 아무것도 없던 pair(새로 드러나는 줄)나 내용이
    # 그대로인 pair 는 안전하다. 장면 첫 그리기(V_LASTPAGE=0xFF)는 전에 아무것도 없었으니
    # 항상 안전. 반환: A=0/Z=1 안전, A=1/Z=0 위험.
    a.label("check_risky")
    a.op("LDA", "abs", V_LASTPAGE)
    a.op("CMP", "imm", 0xFF)
    a.op("BNE", "rel", "cr_go")
    a.op("JMP", "abs", "cr_safe")
    a.label("cr_go")
    a.op("ASL")
    a.op("ASL")
    a.op("ASL")
    a.op("STA", "zp", Z_T0)  # old_base = lastpage*8
    a.op("LDA", "abs", V_PAGE)
    a.op("ASL")
    a.op("ASL")
    a.op("ASL")
    a.op("STA", "zp", Z_T1)  # new_base = page*8
    for pair in range(4):
        off = pair * 2
        a.op("LDA", "zp", Z_T0)
        a.op("CLC")
        a.op("ADC", "imm", off)
        a.op("TAX")
        a.op("LDA", "absx", "pages")  # 옛 LA
        a.op("STA", "zp", Z_T2)
        a.op("INX")
        a.op("LDA", "absx", "pages")  # 옛 LB
        a.op("STA", "zp", Z_T3)
        a.op("CMP", "imm", 0xFF)
        a.op("BNE", "rel", f"cr_had{pair}")
        a.op("LDA", "zp", Z_T2)
        a.op("CMP", "imm", 0xFF)
        a.op("BNE", "rel", f"cr_had{pair}")
        a.op("JMP", "abs", f"cr_next{pair}")  # 옛 LA·LB 둘 다 없음 — 이 pair 는 전에 안 보였다
        a.label(f"cr_had{pair}")
        a.op("LDA", "zp", Z_T1)
        a.op("CLC")
        a.op("ADC", "imm", off)
        a.op("TAX")
        a.op("LDA", "absx", "pages")  # 새 LA
        a.op("CMP", "zp", Z_T2)
        a.op("BEQ", "rel", f"cr_la_ok{pair}")
        a.op("JMP", "abs", "cr_risky")
        a.label(f"cr_la_ok{pair}")
        a.op("INX")
        a.op("LDA", "absx", "pages")  # 새 LB
        a.op("CMP", "zp", Z_T3)
        a.op("BEQ", "rel", f"cr_next{pair}")
        a.op("JMP", "abs", "cr_risky")
        a.label(f"cr_next{pair}")
    a.label("cr_safe")
    a.op("LDA", "imm", 0)
    a.op("RTS")
    a.label("cr_risky")
    a.op("LDA", "imm", 1)
    a.op("RTS")

    # hide_all: 우리 스프라이트 28개를 전부 화면 밖으로(SAT y=0) + SATB DMA
    a.label("hide_all")
    a.op("STZ", "zp", Z_T3)
    a.label("ha_loop")
    a.op("JSR", "abs", "sat_hide")
    a.op("INC", "zp", Z_T3)
    a.op("LDA", "zp", Z_T3)
    a.op("CMP", "imm", 4 * SPR_PER_PAIR)
    a.op("BNE", "rel", "ha_loop")
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", V_SATDIRTY)
    a.op("RTS")

    # backup_all / restore_all: 현재 장면(Z_SCN)의 chunks[nsafe..27] 을 슬롯 0.. 에 복사 / 되돌린다.
    #   슬롯 = BACKUP_SLOTS[i-nsafe] (뱅크, $6000 창 오프셋). 청크 하나 = 256 워드. MPR3 를 잠깐 바꾼다.
    for name, direction in (("backup_all", "v2r"), ("restore_all", "r2v")):
        a.label(name)
        a.op("LDY", "imm", SC_NSAFE)
        a.op("LDA", "izpy", Z_SCN)
        a.op("STA", "abs", V_TMP_I)  # i = nsafe
        a.op("STZ", "abs", V_TMP_SLOT)
        a.label(f"{name}_loop")
        a.op("LDA", "abs", V_TMP_I)
        a.op("CMP", "imm", 4 * SPR_PER_PAIR)
        a.op("BCC", "rel", f"{name}_go")
        a.op("RTS")
        a.label(f"{name}_go")
        a.op("LDA", "abs", V_TMP_SLOT)
        a.op("CMP", "imm", len(BACKUP_SLOTS))
        a.op("BCC", "rel", f"{name}_go2")
        a.op("RTS")  # 슬롯 부족(빌드가 막는다)
        a.label(f"{name}_go2")
        a.op("CLC")
        a.op("ADC", "abs", V_TMP_SLOT)
        a.op("TAX")  # X = slot*2
        a.op("LDA", "abs", V_TMP_I)
        a.op("CLC")
        a.op("ADC", "imm", SC_CHUNKS)
        a.op("TAY")
        a.op("LDA", "izpy", Z_SCN)  # 청크 번호 = VRAM 워드주소 hi
        # 🔴 0xFF = 표 채움(그 장면이 실제로 쓰는 청크는 여기서 끝). 종전엔 마지막 청크를
        # 복제해 채워서 **안 빌린 장면도 28칸까지 돌며 같은 자리를 열 번 넘게 백업·복원**했다.
        # 한 칸이 512B 라 그게 곧 한 프레임의 태반이고, 게임의 그림 로드와 부딪히는 창이 된다.
        a.op("CMP", "imm", 0xFF)
        a.op("BNE", "rel", f"{name}_go3")
        a.op("RTS")
        a.label(f"{name}_go3")
        a.op("STA", "zp", Z_T1)
        a.op("TMA", "tma", 3)
        a.op("STA", "zp", Z_T0)
        a.op("LDA", "absx", "slots")
        a.op("TAM", "tam", 3)
        a.op("LDA", "absx", "slots+1")
        a.op("ORA", "imm", 0x60)  # 🔴 MPR3 창 $6000 을 더해야 한다 — 빠뜨리면 $0000~ (I/O 페이지: VDC·VCE) 에 쓴다(실측 2026-09-20)
        a.op("STA", "zp", Z_SRC + 1)  # $60xx 창 안의 오프셋 hi (lo = 0)
        a.op("STZ", "zp", Z_SRC)
        a.op("SEI")
        a.op("ST0", "imm", 0x00 if direction == "r2v" else 0x01)  # MAWR / MARR
        a.op("STZ", "abs", 0x0002)
        a.op("LDA", "zp", Z_T1)
        a.op("STA", "abs", 0x0003)
        a.op("ST0", "imm", 0x02)
        a.op("LDX", "imm", 2)  # 256 워드 = 512B = Y 0..255 두 바퀴
        a.label(f"{name}_page")
        a.op("LDY", "imm", 0)
        a.label(f"{name}_w")
        if direction == "v2r":
            a.op("LDA", "abs", 0x0002)
            a.op("STA", "izpy", Z_SRC)
            a.op("INY")
            a.op("LDA", "abs", 0x0003)
            a.op("STA", "izpy", Z_SRC)
        else:
            a.op("LDA", "izpy", Z_SRC)
            a.op("STA", "abs", 0x0002)
            a.op("INY")
            a.op("LDA", "izpy", Z_SRC)
            a.op("STA", "abs", 0x0003)
        a.op("INY")
        a.op("BNE", "rel", f"{name}_w")
        a.op("INC", "zp", Z_SRC + 1)
        a.op("DEX")
        a.op("BNE", "rel", f"{name}_page")
        a.op("LDA", "zp", 0xF7)
        a.op("STA", "abs", 0x0000)
        a.op("CLI")
        a.op("LDA", "zp", Z_T0)
        a.op("TAM", "tam", 3)
        a.op("INC", "abs", V_TMP_I)
        a.op("INC", "abs", V_TMP_SLOT)
        a.op("JMP", "abs", f"{name}_loop")

    # ── 표 ──
    a.label("slots")
    for bank, off in BACKUP_SLOTS:
        a.data(bytes((bank, off >> 8)))
    a.label("events")
    for sec, page in events:
        f = frames_of(sec, timing)
        a.data(bytes((f & 0xFF, f >> 8, page)))
    a.data(b"\xff\xff\x00")
    a.label("pages")
    for rows in pages:
        r = list(rows) + [None] * (8 - len(rows))
        a.data(bytes(0xFF if x is None else x for x in r))
    a.label("lines")
    for bank, off, ncell in lines_tab:
        a.data(bytes((bank, off & 0xFF, off >> 8, ncell)))
    a.label("scenes")
    for s in scenes:
        qu, end, sw = s["quiet"], s["end"], s["switch"]
        chunks = list(s["chunks"])
        chunks += [0xFF] * (4 * SPR_PER_PAIR - len(chunks))  # 0xFF = 끝 표식(draw 는 need 까지만 쓰니 안 닿는다)
        a.data(bytes((qu & 0xFF, qu >> 8, end & 0xFF, end >> 8, sw & 0xFF, sw >> 8, s["x_base"], s["nsafe"], s.get("spr_base", SPR_BASE), s.get("game_n", 0))) + bytes(chunks))
    a.data(b"\xff\xff" * 3 + b"\0" * (SCENE_ENTRY - 6))  # 끝 표식(switch=0xFFFF: 안 넘어간다)
    a.label("end")

    # 트램펄린 라벨 해결: main 주소를 알아야 한다 → 두 번 조립
    main_addr = a.labels["main"]
    tm2 = Asm(TRAMP_MAIN)
    tm2.op("TMA", "tma", 4)
    tm2.op("PHA")
    tm2.op("LDA", "imm", 0x6A)
    tm2.op("TAM", "tam", 4)
    tm2.op("JSR", "abs", main_addr)
    tm2.op("PLA")
    tm2.op("TAM", "tam", 4)
    tm2.op("JMP", "abs", 0x43F3)
    ri.labels["scenes_lo"] = a.labels["scenes"] & 0xFF
    ri.labels["scenes_hi"] = a.labels["scenes"] >> 8
    tm_bytes, ti_bytes, ri_bytes = tm2.bytes(), ti.bytes(), ri.bytes()
    assert len(tm_bytes) <= TRAMP_IRQ - TRAMP_MAIN and len(ti_bytes) <= V_FRAME - TRAMP_IRQ
    assert len(ri_bytes) <= RAM_INIT_MAX, len(ri_bytes)
    a.labels["scenes_lo"] = a.labels["scenes"] & 0xFF
    a.labels["scenes_hi"] = a.labels["scenes"] >> 8
    # 라벨+오프셋(`events+1` 류)을 풀어 준다
    for pos, lab, kind in a.fix:
        if "+" in lab and lab not in a.labels:
            base, off = lab.split("+")
            a.labels[lab] = a.labels[base] + int(off)
    code = bytearray(a.bytes())
    # 트램펄린 바이트를 코드 뒤에 붙이고 TII 원본 주소를 채운다
    tm_pos = CODE_ADDR + len(code)
    ti_pos = tm_pos + len(tm_bytes)
    ri_pos = ti_pos + len(ti_bytes)
    code += tm_bytes + ti_bytes + ri_bytes
    for pos, src, ln in ((tii_main_pos, tm_pos, len(tm_bytes)), (tii_irq_pos, ti_pos, len(ti_bytes)), (tii_init_pos, ri_pos, len(ri_bytes))):
        code[pos + 1 : pos + 3] = src.to_bytes(2, "little")
        code[pos + 5 : pos + 7] = ln.to_bytes(2, "little")
    assert len(code) <= CODE_MAX, len(code)
    return bytes(code)


SCENE_ENTRY = 10 + 4 * SPR_PER_PAIR  # quiet(2) end(2) switch(2) x_base(1) nsafe(1) spr_base(1) game_n(1) chunks(28)
SC_QUIET, SC_END, SC_SWITCH, SC_XBASE, SC_NSAFE, SC_SPRBASE, SC_GAMEN, SC_CHUNKS = 0, 2, 4, 6, 7, 8, 9, 10
V_TMP_K, V_TMP_PAIR, V_TMP_LA, V_TMP_LB, V_TMP_C, V_TMP_CHUNK, V_TMP_VLO, V_TMP_VHI = (
    0x2360, 0x2361, 0x2362, 0x2363, 0x2364, 0x2365, 0x2366, 0x2367
)
V_TMP_LINE, V_TMP_CELL, V_TMP_SHIFT, V_TMP_SIGWANT, V_TMP_NUSED = 0x2368, 0x2369, 0x236A, 0x236B, 0x236C
V_RESTORED, V_TMP_I, V_TMP_SLOT, V_SATDIRTY, V_HIDING, V_LASTPAGE = 0x236D, 0x236E, 0x236F, 0x2370, 0x2371, 0x2372  # 되돌림 상태 · 백업 루프 인덱스 · SAT 그림자 변경 · 지우기 선행 중 · 마지막으로 실제로 그린 페이지(0xFF=없음)


def _imm_label_fix(a: Asm):
    """`LDA #label` 은 미니 어셈블러가 모른다 — 즉치에 라벨을 넣은 자리를 뒤에서 채운다."""


# LDA imm 에 문자열 라벨을 허용하도록 op 를 한 번 더 감싼다
_op2 = Asm.op


def _op3(self, mn, mode="imp", arg=None):
    if mode == "imm" and isinstance(arg, str):
        self.out.append(hook.OPS[(mn, mode)])
        self.fix.append((len(self.out), arg, "imm"))
        self.out.append(0)
        return
    return _op2(self, mn, mode, arg)


Asm.op = _op3
_bytes0 = Asm.bytes


def _bytes1(self):
    for pos, lab, kind in list(self.fix):
        if kind == "imm":
            self.out[pos] = self.labels[lab] & 0xFF
    self.fix = [f for f in self.fix if f[2] != "imm"]
    return _bytes0(self)


Asm.bytes = _bytes1


# ── 조립·적용 ──────────────────────────────────────────────────────────────
def sprites_needed(lines, rows):
    """페이지 한 장이 먹는 스프라이트(=청크) 수 — 짝(두 줄)마다 ceil(max(ncell)/2)."""
    nc = [len(strip_cells(t)) for t in lines]
    r = list(rows) + [None] * (len(rows) % 2)
    return sum((max(nc[a] if a is not None else 0, nc[b] if b is not None else 0) + 1) // 2 for a, b in zip(r[::2], r[1::2]))


def plan_scenes(lines, pages, events, scenes, timing):
    """장면마다 필요한 청크 수를 세어 chunks = safe + (모자란 만큼 borrow) 로 확정한다.
    넘치면(safe+borrow 로도 모자라거나 백업 슬롯이 모자라면) 배경 타일을 덮게 되므로 빌드 실패."""
    evf = [(frames_of(t, timing), p) for t, p in events]
    out = []
    for i, s in enumerate(scenes):
        lo = s["switch"]
        hi = scenes[i + 1]["switch"] if i + 1 < len(scenes) else 1 << 30
        active = [p for f, p in evf if f < lo][-1:] + [p for f, p in evf if lo <= f < hi]
        need = max((sprites_needed(lines, pages[p]) for p in active), default=0)
        safe, borrow = list(s["safe"]), list(s["borrow"])
        if need > len(safe) + len(borrow):
            raise SystemExit(f"장면 {s['name']}: 자막에 청크 {need}개가 필요한데 safe {len(safe)} + borrow {len(borrow)}")
        take = borrow[: max(0, need - len(safe))]
        if len(take) > len(BACKUP_SLOTS):
            raise SystemExit(f"장면 {s['name']}: 빌릴 청크 {len(take)}개 > 백업 슬롯 {len(BACKUP_SLOTS)}")
        chunks = (safe + take)[: 4 * SPR_PER_PAIR]
        nsafe = min(len(safe), len(chunks))
        assert len(chunks) >= need and need <= 4 * SPR_PER_PAIR
        out.append(dict(s, chunks=chunks, nsafe=nsafe, need=need))
    return out


def build_all():
    sub = json.loads(SUBS.read_text(encoding="utf-8"))
    sc = json.loads(SCENES.read_text(encoding="utf-8"))["scenes"]
    lines, pages, events = timeline(sub["lines"], sub["rules"])
    sc = plan_scenes(lines, pages, events, sc, sub["timing"])
    banks, table = pack_strips(lines)
    code = runtime(table, pages, events, sc, sub["timing"])
    return sub, lines, pages, events, banks, table, code


def apply(f, touched):
    """build.py 가 부른다 — 코드 패치 1곳 + 코드/표 블록 + 스트립 섹터."""
    from shared.disc import mode1

    sub, lines, pages, events, banks, table, code = build_all()
    # 1. CD_PLAY 호출 → init
    rel, off = MODULE_REL + CDPLAY_OFF // common.USER, CDPLAY_OFF % common.USER
    mode1.write_at(
        f, common.T2_SECTOR + rel, common.USER, off,
        b"\x20" + CODE_ADDR.to_bytes(2, "little"), label="opening CD_PLAY→init", expect=b"\x20\x12\xe0",
    )
    touched.append((common.T2_SECTOR + rel, 1))
    # 2. 코드+표 → 모듈 +0x4D40~ (섹터 경계를 걸치므로 섹터마다 write_at)
    pos = 0
    while pos < len(code):
        off = CODE_OFF + pos
        rel, o = MODULE_REL + off // common.USER, off % common.USER
        n = min(common.USER - o, len(code) - pos)
        mode1.write_at(
            f, common.T2_SECTOR + rel, common.USER, o, code[pos : pos + n],
            label=f"opening code rel {rel}", expect=b"\0" * n,
        )
        touched.append((common.T2_SECTOR + rel, 1))
        pos += n
    # 3. 스트립 → rel 422~ (뱅크마다 4섹터, 원판 0)
    for bank, secoff in STRIP_BANK_SECTORS.items():
        blob = banks[bank] + b"\0" * (0x2000 - len(banks[bank]))
        lba = common.T2_SECTOR + DATA_REL + secoff
        mode1.write_user_data(f, lba, blob, label=f"opening strips bank {bank:02X}", expect=b"\0" * len(blob))
        touched.append((lba, 4))
    used = sum(len(b) for b in banks.values())
    return f"오프닝 자막: 줄 {len(lines)} · 페이지 {len(pages)} · 사건 {len(events)} · 스트립 {used}B · 코드+표 {len(code)}B"


def main():
    sub, lines, pages, events, banks, table, code = build_all()
    print(f"줄 {len(lines)} 페이지 {len(pages)} 사건 {len(events)}; 코드+표 {len(code)}B (최대 {CODE_MAX})")
    print("스트립 바이트:", {f"{b:02X}": len(v) for b, v in banks.items()})
    for sec, page in events:
        print(f"  {sec:7.2f}s f{frames_of(sec, sub['timing']):5d} → page {page}: {[None if r is None else lines[r][:10] for r in pages[page]]}")
    if "--preview" in sys.argv:
        from PIL import Image
        import numpy as np

        out = common.REVIEW_DIR / "opening"
        out.mkdir(parents=True, exist_ok=True)
        for i, text in enumerate(lines[:6]):
            m, e = render_line(text)
            img = np.zeros((GLYPH_ROWS, m.shape[1], 3), dtype=np.uint8) + 96
            img[m == 1] = 255
            img[(e == 1) & (m == 0)] = 0
            Image.fromarray(img).resize((m.shape[1] * 3, GLYPH_ROWS * 3), Image.NEAREST).save(out / f"line{i}.png")
        print("미리보기:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
