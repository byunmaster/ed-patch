"""구형 시스템 카드 안내 화면(「슈퍼 시스템 카드를 사용해 주십시오.」) 한글화 — 코드 훅으로 한글 타일을 덮어쓴다.

배경(2026-10-15 조사 — docs/devlog.md): IPL(`$4000`, rel 2~21)이 카드 버전 < 3 이면 rel 4~27(24섹터)을 뱅크 0x80~ 에 올려 `$4000` 으로 간다.
그 프로그램이 그림(공주·기사·카드)과 **글씨 띠**(BAT 행 23~25, 타일 0x211~0x24E, 4평면·팔레트 1)를 그린다. 글씨는 압축 그림 자산이라 풀지 않고,
**그림이 다 올라간 뒤 한 번 한글 타일·BAT 를 VRAM 에 덮어쓴다**(원판 그림 불변).

배치(전부 rel 4~27 안, IPL 스텁·정상 부팅 구역(rel ≥ 34) 불변):
  · 훅 호출부 — 메인 루프 끝 `JSR $4094`(rel 4 +0x43, 논리 `$4043`) → `JSR HOOK`
  · 훅 코드 — 0 런(이미지 +0x2240 = 논리 `$6240`, 원판 0 이 577B) 안
  · 데이터 — rel 25~27(원판 0 의 3섹터, 뱅크 0x85 +0x800 = 이미지 +0xA800). 훅이 MPR5(`$A000`)에 뱅크 0x85 를 잠깐 걸고 읽는다
  · 한 번만: RAM `$3090`(원판 0 인 작업 RAM) 플래그. BAT[24][0] 이 원판 글씨 타일(`$1218`)로 보일 때까지 기다린 뒤(그림이 아직 안 올라왔으면 원판이 나중에
    덮어쓰므로) 쓴다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import hook
from hook import Asm

hook.OPS.update({("ST1", "imm"): 0x13, ("ST2", "imm"): 0x23, ("NOP", "imp"): 0xEA, ("CLI", "imp"): 0x58})

# ── 값 하나로 바꿀 수 있는 것(마스터 10-15: 문안·정렬) ───────────────────────────
TEXT = "슈퍼 시스템 카드를 사용해 주십시오."
ALIGN = "center"  # "center" | "left"(원판은 왼쪽 x=2 부터 폭 가득)
# 🔴 음성 자막(마스터 10-16 「카드화면 음성 자막」) — 같은 띠에 음성 시작(`$180C` 비트3)부터 (문안, 시작 초). 문안·시각은 값 하나씩이다.
#   받아쓰기·파형 근거는 docs/devlog.md 10-16 — 문안은 관리자·마스터 확정 전 초안.
SUBS = [
    ("시스템 카드의 버전이 다릅니다.", 0.4),
    ("게임을 시작하려면", 3.3),
    ("3.00 이상의 시스템 카드를 사용해 주세요.", 5.7),
    ("자세한 내용은 설명서를 봐 줘.", 8.5),
]
SUB_SPACE = 6  # 자막 공백 전진 px(기본 8) — 3번이 한 줄(256px)에 들어가게(마스터 10-17 「원문 말씨」)
VOICE_END_S = 12.6  # 마지막 문장 끝(파형 에너지가 바닥으로 떨어지는 때)
TAIL_S = 0.5  # 말 끝 +0.5초(번역 규칙 2-15) 뒤 고정 문구로 복귀
FPS = 60
HDR_BYTES = 0x100  # 시각표 칸
ROW_BYTES = 8 * 32  # 타일 행 하나의 마스크 = 256B(8줄 × 32열)
FIX_BYTES = 2 * ROW_BYTES  # 고정 문구 — 타일 행 24~25, 글자 마스크 하나
SUB_BYTES = 2 * 2 * ROW_BYTES  # 자막 한 벌 — 타일 행 26~27 × (글자 · 외곽선) 마스크
FIX_ROWS, SUB_ROWS = (24, 25), (26, 27)
FIX_INK_TOP = 191  # 고정 문구 잉크 첫 행 = 원판 글씨 줄(y 191~) 그대로
SUB_INK_TOP = 208  # 자막 잉크 첫 행 — 외곽선 바닥 y 219(화면 아래 끝에서 12px, 본 게임 필드 UI 끝선)

# ── 좌표 규약 ───────────────────────────────────────────────────────────────
IPL_REL = 4  # 안내 프로그램 시작 섹터(rel)
LOGICAL0 = 0x4000  # 이미지 +0 ↔ 논리 $4000
CALL_OFF = 0x43  # 메인 루프 끝의 `JSR $4094`(20 94 40)
CALL_ORIG = b"\x20\x94\x40"
CODE_OFF = 0x2240  # 이미지 안 0 런(+0x223F, 577B) — 뱅크 0x81 +0x240. 🔴 루프 중엔 MPR3 가 뱅크 0 이라 `$6240` 이 안 보인다 → 트램펄린이 잠깐 건다
TRAMP_OFF = 0x1845  # 항상 보이는 `$4000~$5FFF` 안의 0 틈(+0x1845, 15B) — 논리 $5845. `TMA/TAM #3` + `JSR $6240`
CODE_MAX = 0x223F + 577 - CODE_OFF
DATA_OFF = 0xA800  # rel 25 시작 = 뱅크 0x85 +0x800
DATA_BANK, DATA_ADDR = 0x85, 0xA800
DATA_MAX = (27 - 25 + 1) * common.USER
FLAG_ADDR = 0x3090  # 원판 0 인 작업 RAM
BAT_ROWS = (24, 25, 26, 27)  # 우리가 쓰는 타일 행. 🔴 행 23(y 183~190, 열 21~27)은 달걀 그림 아랫부분(타일 `$211~$217`) — BAT 도 타일 데이터도 안 건드린다(마스터 10-17 「훼손하지 말자」)
BAT_STRIDE = 64  # BAT 한 행 = 64 워드
BAND_Y0 = 184  # 행 23 의 화면 y
GLYPH_Y0 = 191  # 원판 글자 첫 행 — 마스크 행 1 이 여기에 놓인다
FIRST_TILE = 0x218  # 128장(행 24~27 × 32열)이 이 번호부터 연속 — `$211~$217` 은 달걀 타일이라 건너뛴다(원판 글씨 타일 `$218~$24E` + 그 뒤 원판 0 이던 번호, 스프라이트 패턴은 0x384~)
FIX_TILE = FIRST_TILE
SUB_TILE = FIRST_TILE + 64


def render_mask(text: str):
    """한글 글씨 마스크 → (24행 × 256열 0/1 배열, 가로 시작 x). 글꼴·폭 규약은 오프닝 자막과 같은 Galmuri 11 12px · 공백 반각."""
    import numpy as np
    import opening_sub as o

    m, _edge = o.render_line(text)  # 14행 × W (글자 행 1~12)
    ink_w = m.shape[1] - 2
    band = np.zeros((24, 256), dtype=np.uint8)
    x0 = (256 - ink_w) // 2 - 1 if ALIGN == "center" else 1
    assert x0 >= 0 and x0 + m.shape[1] <= 256, f"한글 안내문이 띠(256px)를 넘는다: 폭 {ink_w}px"
    r0 = GLYPH_Y0 - BAND_Y0 - 1  # 마스크 행 1 → 띠 행 GLYPH_Y0−BAND_Y0
    for y in range(1, 13):
        for x in range(m.shape[1]):
            if m[y, x]:
                band[r0 + y, x0 + x] = 1
    return band, x0


def tile_bytes(rows8, outline8=None) -> bytes:
    """8행 글자 비트(행마다 정수 0~255, 왼쪽 = MSB) → 32B. 평면 0 = 외곽선이 아닌 곳 1(배경 색 1 · 글자 15), 평면 1~3 = 글자.
    외곽선 픽셀은 색 번호 0(투명 → 뒤 배경색 = 검정). 외곽선이 없으면(None) 평면 0 전부 1 — 원판 글씨 타일 규약(덤프 실측)과 같다."""
    out = bytearray()
    for k, b in enumerate(rows8):
        e = outline8[k] if outline8 else 0
        out += bytes((0xFF & ~e, b))  # 평면 0·1
    for b in rows8:
        out += bytes((b, b))  # 평면 2·3
    return bytes(out)


def _glyphs(text: str, space: int):
    """한 줄 → (글자 마스크 m, 외곽선 e) 불리언 배열(14행). 영상 자막 렌더러와 같은 글꼴·외곽선 규칙이고 공백 전진만 `space` px."""
    import numpy as np
    import fonts
    import opening_sub as o

    bdf = fonts.galmuri()
    adv = [(space if c == " " else a) for c, a in zip(text, o._advs(text))]
    wpx = sum(adv) + 2
    m = np.zeros((o.GLYPH_ROWS, wpx), dtype=np.uint8)
    x = 1
    for c, a_ in zip(text, adv):
        if c != " ":
            b = bdf.bits(c, dy=o.DY, rows=o.LINE_H - 2, width=o.CELL)[:12]
            h, w_ = b.shape
            w_ = min(w_, wpx - x)
            m[1 : 1 + h, x : x + w_] |= b[:, :w_]
        x += a_
    e = np.zeros_like(m)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                e |= np.roll(np.roll(m, dy, 0), dx, 1)
    e &= ~m
    return m.astype(bool), e.astype(bool)


def _raster(text: str, ink_top: int, rows: tuple[int, ...], outline: bool, space: int = 8):
    """글자(·외곽선)를 타일 행 `rows` 의 마스크(바이트 배열)로. 타일 행 r 은 화면 y = 8r−1 ~ 8r+6 이다. (글자 바이트, 외곽선 바이트)."""
    import numpy as np

    m, e = _glyphs(text, space)
    if outline:  # 자막 — 외곽선 포함 닿는 폭의 가운데
        ink = np.where((m | e).any(axis=0))[0]
        x0 = (256 - int(ink[-1] - ink[0] + 1)) // 2 - int(ink[0])
    else:  # 고정 문구 — 종전 그대로(전진 폭 가운데: `render_mask` 와 같은 식)
        x0 = (256 - (m.shape[1] - 2)) // 2 - 1
    y_top = 8 * rows[0] - 1
    hgt = 8 * len(rows)
    W = np.zeros((hgt, 256), dtype=bool)
    E = np.zeros((hgt, 256), dtype=bool)
    for plane, arr in ((m, W), (e, E)):
        if plane is e and not outline:
            continue
        for y in range(plane.shape[0]):
            for x in range(plane.shape[1]):
                if plane[y, x]:
                    yy = ink_top - 1 + y - y_top
                    xx = x0 + x
                    assert 0 <= yy < hgt and 0 <= xx < 256, (text, y, x, yy, xx)
                    arr[yy, xx] = True

    def pack(a):
        out = bytearray()
        for tr in range(len(rows)):
            for k in range(8):
                for c in range(32):
                    v = 0
                    for b in range(8):
                        v = (v << 1) | int(a[tr * 8 + k, c * 8 + b])
                    out.append(v)
        return bytes(out)

    return pack(W), pack(E)


def fixed_bytes() -> bytes:
    """고정 문구 마스크(행 24~25, 512B) — 원판 글씨 줄 그대로(잉크 y 191~), 가운데 정렬."""
    w, _e = _raster(TEXT, FIX_INK_TOP, FIX_ROWS, False)
    assert len(w) == FIX_BYTES
    return w


def sub_bytes(text: str | None) -> bytes:
    """자막 한 벌(행 26~27) = 글자 마스크 512B + 외곽선 마스크 512B. text=None 이면 빈 띠."""
    if text is None:
        return bytes(SUB_BYTES)
    w, e = _raster(text, SUB_INK_TOP, SUB_ROWS, True, SUB_SPACE)
    return w + e


def band_tiles(text: str | None, fixed: bool = False) -> list[bytes]:
    """마스크를 훅이 펴는 그대로 → 32B 타일(고정 문구 64장 · 자막 64장). 테스트·미리보기용 — 훅 동작의 기준."""
    if fixed:
        raw = fixed_bytes()
        return [tile_bytes([raw[(r * 8 + k) * 32 + c] for k in range(8)]) for r in range(2) for c in range(32)]
    raw = sub_bytes(text)
    w, e = raw[:ROW_BYTES * 2], raw[ROW_BYTES * 2 :]
    return [
        tile_bytes([w[(r * 8 + k) * 32 + c] for k in range(8)], [e[(r * 8 + k) * 32 + c] for k in range(8)])
        for r in range(2)
        for c in range(32)
    ]


def schedule_frames() -> list[tuple[int, int]]:
    """(음성 시작 후 프레임, 띠 번호) — 0 = 고정 문구. 마지막 = 말 끝 +0.5초에 고정 문구로 복귀."""
    ev = [(round(t * FPS), i + 1) for i, (_txt, t) in enumerate(SUBS)]
    ev.append((round((VOICE_END_S + TAIL_S) * FPS), 0))
    return ev


def build_data() -> bytes:
    """뱅크 0x85 +0x800 에 놓을 자료 — `+0x000` 시각표(`[프레임 lo][hi][띠]`… 끝 `00 FF`) · `+0x100` 고정 문구 마스크(512B) ·
    `+0x300 + n×0x400` 자막 n 한 벌(n=0 빈 띠 — 그 외곽선 칸(0)이 고정 문구의 외곽선으로 공유된다, 1~4 자막)."""
    hdr = bytearray()
    for fr, n in schedule_frames():
        assert 0 < fr < 0xFF00
        hdr += bytes((fr & 0xFF, fr >> 8, n))
    hdr += b"\x00\xff"
    assert len(hdr) <= HDR_BYTES, len(hdr)
    out = bytearray(hdr) + bytes(HDR_BYTES - len(hdr))
    out += fixed_bytes()
    for text in [None] + [t for t, _s in SUBS]:
        out += sub_bytes(text)
    assert len(out) <= DATA_MAX, f"띠 자료 {len(out)}B > {DATA_MAX}B"
    return bytes(out)


def build_tramp() -> bytes:
    """`JSR $5845` 로 불린다 — MPR3 에 뱅크 0x81 을 걸고 훅 본체(`$6240`)를 부른 뒤 되돌린다(14B)."""
    a = Asm(LOGICAL0 + TRAMP_OFF)
    a.op("TMA", "tma", 3)
    a.op("PHA")
    a.op("LDA", "imm", 0x81)
    a.op("TAM", "tam", 3)
    a.op("JSR", "abs", LOGICAL0 + CODE_OFF)
    a.op("PLA")
    a.op("TAM", "tam", 3)
    a.op("RTS")
    code = a.bytes()
    assert len(code) <= 15, len(code)
    return code


# 훅 작업 RAM(원판 0 인 `$3090~`) — 상태 · 프레임 카운터(16) · 음성 시작 시각(16) · 음성 시작 봤나 · 시각표 위치 · 띠 그렸나 · 경과(16) · 행 수
FRAME8_ZP = 0x24
S_STATE, S_CNT, S_T0, S_VF, S_IDX, S_DRAWN, S_DL, S_ROWS, S_TCALL, S_LAST8, S_VLO, S_VHI = (
    FLAG_ADDR,
    FLAG_ADDR + 1,
    FLAG_ADDR + 3,
    FLAG_ADDR + 5,
    FLAG_ADDR + 6,
    FLAG_ADDR + 7,
    FLAG_ADDR + 8,
    FLAG_ADDR + 10,
    FLAG_ADDR + 12,  # `AD_CPLAY` 를 부른 때의 카운터(호출부 래퍼가 적는다)
    FLAG_ADDR + 13,
    FLAG_ADDR + 14,  # 타일을 쓸 VRAM 워드 주소(하위·상위) — `drawrows` 인자
    FLAG_ADDR + 15,
)
START_OFFS = 39  # 래퍼가 소리 시작을 못 봤을 때의 대비값 — 호출 → 소리가 나기까지 프레임(v2.1 에뮬 실측 RdAddr)
RISE_LAT = 14  # `$180C` 비트3 이 오른 뒤 소리가 실제로 나기까지(v2.1 에뮬 실측: 비트3 상승 ≈ 호출+25, 소리 ≈ 호출+39). 
PLAYING_LAT = 7  # 래퍼가 돌아왔을 때 비트3 이 이미 서 있으면 소리 시작 ≈ 지금 + 이 값. 실측(에뮬): v1.0 은 BIOS 가 재생 시작까지 기다렸다 돌아와 소리 = 지금(0), v2.1 은 비트3 이 서고 14프레임 뒤 소리 — 둘의 가운데로 잡는다(±7프레임 ≈ 0.12초)
POLL_MAX = 90  # 래퍼가 비트3 상승을 기다리는 최대 프레임
PLAYCALL_OFF = 0x2969  # `JSR $E03F`(AD_CPLAY) — 안내 프로그램의 음성 재생 호출부(뱅크 0x81 +0x969)
PLAYCALL_ORIG = b"\x20\x3f\xe0"
ADPCM_STAT = 0x180C  # 비트3 = ADPCM 재생 중(나레이션 훅과 같은 신호)


def build_code() -> tuple[bytes, int]:
    """훅 본체 → (바이트, 진입 논리 주소). 진입 = `$6240`(MPR3 = 뱅크 0x81 일 때).

    매 호출(메인 루프 한 바퀴 ≈ 한 프레임): ① 프레임 카운터++ ② `$180C` 비트3 이 오르면 그때 카운터 = 음성 시작
    ③ 띠를 한 번 그린다(원판 글씨 타일이 보일 때 — 그림이 다 올라온 뒤) ④ 음성 시작 뒤엔 시각표를 보며 띠를 갈아 끼운다. 끝(고정 문구 복귀) 뒤엔 아무것도 안 한다.
    """
    entry = LOGICAL0 + CODE_OFF
    a = Asm(entry)
    vdc_sel = 0x0000
    lo, hi = 0x0002, 0x0003  # VDC 데이터(VWR) 하위·상위 — 상위를 쓰면 확정
    a.label("hook")
    a.op("JSR", "abs", 0x4094)  # 원래 호출
    a.op("LDA", "abs", S_STATE)
    a.op("BNE", "rel", "running")
    a.op("INC", "abs", S_STATE)  # 첫 호출 — 작업 RAM 초기화(원판 0 이라 믿지만 한 번 못 박는다)
    for v in (S_CNT + 1, S_T0 + 1):  # S_IDX·S_DRAWN 은 S_STATE 와 마찬가지로 부팅 때 BIOS 가 0 으로 비운 RAM 에 기댄다(코드 자리가 6B 모자랐다)
        a.op("STZ", "abs", v)
    a.op("LDA", "zp", FRAME8_ZP)  # 호출 뒤 경과 = 지금 − 호출 때(8비트 — 안내 프로그램 초기화는 256프레임 안에 끝난다)
    a.op("SEC")
    a.op("SBC", "abs", S_TCALL)
    a.op("STA", "abs", S_CNT)
    a.op("LDA", "zp", FRAME8_ZP)
    a.op("STA", "abs", S_LAST8)
    a.op("LDA", "abs", S_VF)  # 래퍼가 소리 시작을 적어 뒀으면 그대로, 래퍼가 안 돌았으면(VF=0) 대비값
    a.op("BNE", "rel", "t0ok")
    a.op("LDA", "imm", START_OFFS)
    a.op("STA", "abs", S_T0)
    a.label("t0ok")
    a.op("LDA", "imm", 1)
    a.label("running")
    a.op("CMP", "imm", 2)
    a.op("BNE", "rel", "go")
    a.op("RTS")  # 끝났다
    a.label("go")
    a.op("LDA", "zp", FRAME8_ZP)  # 경과(16비트) += ISR 카운터 증가분
    a.op("SEC")
    a.op("SBC", "abs", S_LAST8)
    a.op("CLC")
    a.op("ADC", "abs", S_CNT)
    a.op("STA", "abs", S_CNT)
    a.op("BCC", "rel", "c1")
    a.op("INC", "abs", S_CNT + 1)
    a.label("c1")
    a.op("LDA", "zp", FRAME8_ZP)
    a.op("STA", "abs", S_LAST8)
    a.op("LDA", "abs", S_DRAWN)
    a.op("BNE", "rel", "tick")
    # ── 띠 첫 그림: BAT[24][0] 이 원판 글씨 타일($1218)로 보일 때만 ──
    a.op("SEI")
    a.op("ST0", "imm", 0x01)
    a.op("ST1", "imm", 0x00)
    a.op("ST2", "imm", 0x06)
    a.op("ST0", "imm", 0x02)
    for _ in range(4):
        a.op("NOP")
    a.op("LDA", "abs", 0x0002)
    a.op("CMP", "imm", 0x18)
    a.op("BNE", "rel", "notready")
    a.op("LDA", "abs", 0x0003)
    a.op("CMP", "imm", 0x12)
    a.op("BNE", "rel", "notready")
    a.op("JSR", "abs", "enter")
    a.op("JSR", "abs", "drawbat")
    a.op("LDA", "imm", 0)  # 고정 문구(행 24~25): 글자 마스크 `+0x100`, 외곽선 = 빈 띠(0)의 외곽선 칸(전부 0)
    a.op("STA", "zp", 0xFC)
    a.op("STA", "zp", 0xFA)
    a.op("LDA", "imm", (DATA_ADDR >> 8) + (HDR_BYTES >> 8))
    a.op("STA", "zp", 0xFD)
    a.op("LDA", "imm", (DATA_ADDR >> 8) + ((HDR_BYTES + FIX_BYTES + FIX_BYTES) >> 8))
    a.op("STA", "zp", 0xFB)
    a.op("LDA", "imm", (FIX_TILE * 16) & 0xFF)
    a.op("STA", "abs", S_VLO)
    a.op("LDA", "imm", (FIX_TILE * 16) >> 8)
    a.op("STA", "abs", S_VHI)
    a.op("JSR", "abs", "drawrows")
    a.op("LDA", "imm", 0)  # 자막 띠 0 = 빈 띠
    a.op("JSR", "abs", "drawset")
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", S_DRAWN)
    a.op("JSR", "abs", "leave")
    a.label("notready")
    a.op("LDA", "zp", 0xF7)  # 프로그램이 VDC 레지스터 선택 그림자를 $F7 에 둔다 — IRQ 가 복원에 쓴다
    a.op("STA", "abs", vdc_sel)
    a.op("CLI")
    a.op("RTS")
    # ── 시각표: 음성 시작 뒤 경과 ≥ 다음 항목 시각이면 그 띠로 ──
    a.label("tick")
    a.op("SEC")
    a.op("LDA", "abs", S_CNT)
    a.op("SBC", "abs", S_T0)
    a.op("STA", "abs", S_DL)
    a.op("LDA", "abs", S_CNT + 1)
    a.op("SBC", "abs", S_T0 + 1)
    a.op("STA", "abs", S_DL + 1)
    a.op("BCS", "rel", "t1")
    a.op("RTS")  # 아직 소리가 안 났다
    a.label("t1")
    a.op("SEI")
    a.op("JSR", "abs", "enter")
    a.label("due")
    a.op("LDA", "imm", DATA_ADDR & 0xFF)
    a.op("STA", "zp", 0xFC)
    a.op("LDA", "imm", DATA_ADDR >> 8)
    a.op("STA", "zp", 0xFD)
    a.op("LDA", "abs", S_IDX)
    a.op("TAY")
    a.op("INY")
    a.op("LDA", "izpy", 0xFC)  # 항목 상위 — FF 면 끝
    a.op("CMP", "imm", 0xFF)
    a.op("BEQ", "rel", "tdone")
    a.op("DEY")
    a.op("LDA", "izpy", 0xFC)
    a.op("STA", "zp", 0xFE)  # 항목 하위
    a.op("INY")
    a.op("LDA", "izpy", 0xFC)
    a.op("STA", "zp", 0xFF)  # 항목 상위
    a.op("SEC")
    a.op("LDA", "abs", S_DL)
    a.op("SBC", "zp", 0xFE)
    a.op("LDA", "abs", S_DL + 1)
    a.op("SBC", "zp", 0xFF)
    a.op("BCC", "rel", "tleave")  # 아직
    a.op("INY")
    a.op("LDA", "izpy", 0xFC)  # 띠 번호
    a.op("PHA")
    a.op("LDA", "abs", S_IDX)
    a.op("CLC")
    a.op("ADC", "imm", 3)
    a.op("STA", "abs", S_IDX)
    a.op("PLA")
    a.op("JSR", "abs", "drawset")
    a.op("BRA", "rel", "due")
    a.label("tdone")
    a.op("LDA", "imm", 2)
    a.op("STA", "abs", S_STATE)
    a.label("tleave")
    a.op("JSR", "abs", "leave")
    a.op("LDA", "zp", 0xF7)
    a.op("STA", "abs", vdc_sel)
    a.op("CLI")
    a.op("RTS")
    # ── enter/leave: MPR5 에 자료 뱅크 · $FC~$FF 보존 ──
    a.label("enter")
    a.op("PLX")  # 반환 주소를 잠시 치운다
    a.op("PLY")
    a.op("TMA", "tma", 5)
    a.op("PHA")
    a.op("LDA", "imm", DATA_BANK)
    a.op("TAM", "tam", 5)
    for z in (0xFA, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF):
        a.op("LDA", "zp", z)
        a.op("PHA")
    a.op("PHY")
    a.op("PHX")
    a.op("RTS")
    a.label("leave")
    a.op("PLX")
    a.op("PLY")
    for z in (0xFF, 0xFE, 0xFD, 0xFC, 0xFB, 0xFA):
        a.op("PLA")
        a.op("STA", "zp", z)
    a.op("PLA")
    a.op("TAM", "tam", 5)
    a.op("PHY")
    a.op("PHX")
    a.op("RTS")
    # ── 자막 띠 n(A): 글자·외곽선 마스크 포인터를 정하고 `drawrows` 로 ──
    a.label("drawset")
    a.op("ASL", "imp")
    a.op("ASL", "imp")  # n × 4 = n × 0x400 의 상위 바이트
    a.op("CLC")
    a.op("ADC", "imm", (DATA_ADDR >> 8) + ((HDR_BYTES + FIX_BYTES) >> 8))
    a.op("STA", "zp", 0xFD)  # 글자 마스크 포인터
    a.op("CLC")
    a.op("ADC", "imm", ROW_BYTES * 2 >> 8)
    a.op("STA", "zp", 0xFB)  # 외곽선 마스크 = 글자 +0x200
    a.op("LDA", "imm", 0)
    a.op("STA", "zp", 0xFC)
    a.op("STA", "zp", 0xFA)
    a.op("LDA", "imm", (SUB_TILE * 16) & 0xFF)
    a.op("STA", "abs", S_VLO)
    a.op("LDA", "imm", (SUB_TILE * 16) >> 8)
    a.op("STA", "abs", S_VHI)
    # ── 타일 행 2줄(64장)을 펴 VRAM 에: 평면 0 = ~외곽선 · 평면 1~3 = 글자. 글자 포인터 `$FC`, 외곽선 포인터 `$FA`, VRAM 워드 주소 S_VLO/S_VHI ──
    a.label("drawrows")
    a.op("LDA", "imm", 0x00)
    a.op("STA", "abs", vdc_sel)  # MAWR
    a.op("LDA", "abs", S_VLO)
    a.op("STA", "abs", lo)
    a.op("LDA", "abs", S_VHI)
    a.op("STA", "abs", hi)
    a.op("LDA", "imm", 0x02)
    a.op("STA", "abs", vdc_sel)  # VWR
    a.op("LDA", "imm", 2)
    a.op("STA", "abs", S_ROWS)
    a.label("row")
    a.op("LDA", "imm", 0)
    a.op("STA", "zp", 0xFE)
    a.label("col")
    a.op("LDX", "zp", 0xFE)
    a.op("TXA")
    a.op("TAY")
    a.op("LDX", "imm", 8)
    a.label("pa")
    a.op("LDA", "izpy", 0xFA)
    a.op("EOR", "imm", 0xFF)
    a.op("STA", "abs", lo)
    a.op("LDA", "izpy", 0xFC)
    a.op("STA", "abs", hi)
    a.op("TYA")
    a.op("CLC")
    a.op("ADC", "imm", 32)
    a.op("TAY")
    a.op("DEX")
    a.op("BNE", "rel", "pa")
    a.op("LDX", "imm", 8)
    a.label("pb")
    a.op("LDA", "izpy", 0xFC)
    a.op("STA", "abs", lo)
    a.op("STA", "abs", hi)
    a.op("TYA")
    a.op("CLC")
    a.op("ADC", "imm", 32)
    a.op("TAY")
    a.op("DEX")
    a.op("BNE", "rel", "pb")
    a.op("INC", "zp", 0xFE)
    a.op("LDA", "zp", 0xFE)
    a.op("CMP", "imm", 32)
    a.op("BNE", "rel", "col")
    a.op("INC", "zp", 0xFD)
    a.op("INC", "zp", 0xFB)
    a.op("DEC", "abs", S_ROWS)
    a.op("BNE", "rel", "row")
    a.op("RTS")
    # ── BAT 행 24~27 → 타일 FIRST_TILE~ 연속(팔레트 1) ──
    a.label("drawbat")
    a.op("LDA", "imm", FIRST_TILE & 0xFF)
    a.op("STA", "zp", 0xFE)
    a.op("LDA", "imm", FIRST_TILE >> 8)
    a.op("STA", "zp", 0xFF)
    a.op("LDA", "imm", (BAT_ROWS[0] * BAT_STRIDE) & 0xFF)
    a.op("STA", "zp", 0xFC)
    a.op("LDA", "imm", (BAT_ROWS[0] * BAT_STRIDE) >> 8)
    a.op("STA", "zp", 0xFD)
    a.op("LDA", "imm", len(BAT_ROWS))
    a.op("STA", "abs", S_ROWS)
    a.label("brow")
    a.op("LDA", "imm", 0x00)
    a.op("STA", "abs", vdc_sel)
    a.op("LDA", "zp", 0xFC)
    a.op("STA", "abs", lo)
    a.op("LDA", "zp", 0xFD)
    a.op("STA", "abs", hi)
    a.op("LDA", "imm", 0x02)
    a.op("STA", "abs", vdc_sel)
    a.op("LDY", "imm", 32)
    a.label("bw")
    a.op("LDA", "zp", 0xFE)
    a.op("STA", "abs", lo)
    a.op("LDA", "zp", 0xFF)
    a.op("ORA", "imm", 0x10)
    a.op("STA", "abs", hi)
    a.op("INC", "zp", 0xFE)
    a.op("BNE", "rel", "bn")
    a.op("INC", "zp", 0xFF)
    a.label("bn")
    a.op("DEY")
    a.op("BNE", "rel", "bw")
    a.op("CLC")
    a.op("LDA", "zp", 0xFC)
    a.op("ADC", "imm", BAT_STRIDE)
    a.op("STA", "zp", 0xFC)
    a.op("BCC", "rel", "bq")
    a.op("INC", "zp", 0xFD)
    a.label("bq")
    a.op("DEC", "abs", S_ROWS)
    a.op("BNE", "rel", "brow")
    a.op("RTS")
    # ── 음성 재생 호출 래퍼 — 안내 프로그램의 `JSR $E03F`(AD_CPLAY, 뱅크 0x81 안이라 같은 뱅크의 이 코드를 바로 부른다) 대신 ──
    #    BIOS 를 부른 뒤 ① 프레임 카운터를 적고 ② `$180C` 비트3(ADPCM 재생 중)이 이미 서 있으면 지금이 소리 시작(v1.0), 아니면 오를 때까지(최대 POLL_MAX 프레임) 기다려
    #    그 프레임 + RISE_LAT 를 소리 시작으로 적는다(v2.1). 못 봤으면 START_OFFS. A(결과)·플래그는 호출부가 곧 `CMP #0` 하니 A 만 보존한다.
    a.label("wrapplay")
    a.op("JSR", "abs", 0xE03F)
    a.op("PHA")
    a.op("LDA", "zp", FRAME8_ZP)
    a.op("STA", "abs", S_TCALL)
    a.op("LDA", "abs", ADPCM_STAT)
    a.op("AND", "imm", 0x08)
    a.op("BEQ", "rel", "wpoll")
    a.op("LDA", "imm", PLAYING_LAT)  # 이미 재생 중
    a.op("BRA", "rel", "wset")
    a.label("wpoll")
    a.op("SEC")
    a.op("LDA", "zp", FRAME8_ZP)
    a.op("SBC", "abs", S_TCALL)
    a.op("CMP", "imm", POLL_MAX)
    a.op("BCS", "rel", "wgive")
    a.op("LDA", "abs", ADPCM_STAT)
    a.op("AND", "imm", 0x08)
    a.op("BEQ", "rel", "wpoll")
    a.op("SEC")
    a.op("LDA", "zp", FRAME8_ZP)
    a.op("SBC", "abs", S_TCALL)
    a.op("CLC")
    a.op("ADC", "imm", RISE_LAT)
    a.op("BRA", "rel", "wset")
    a.label("wgive")
    a.op("LDA", "imm", START_OFFS)
    a.label("wset")
    a.op("STA", "abs", S_T0)
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", S_VF)
    a.op("PLA")
    a.op("RTS")
    code = a.bytes()
    assert len(code) <= CODE_MAX, f"훅 코드 {len(code)}B > {CODE_MAX}B"
    global _WRAP_ENTRY
    _WRAP_ENTRY = a.labels["wrapplay"]
    return code, entry


_WRAP_ENTRY = 0


def play_entry() -> int:
    """음성 재생 래퍼의 논리 주소(MPR3 = 뱅크 0x81 일 때 `$6xxx`)."""
    build_code()
    return _WRAP_ENTRY


def apply(f, touched) -> str:
    from shared.disc import mode1

    code, entry = build_code()
    data = build_data()
    T2 = common.T2_SECTOR

    def patch(img_off, new, expect, label):
        rel = IPL_REL + img_off // common.USER
        o = img_off % common.USER
        assert o + len(new) <= common.USER or True
        # 섹터 경계를 넘으면 나눠서 쓴다
        done = 0
        while done < len(new):
            r = IPL_REL + (img_off + done) // common.USER
            oo = (img_off + done) % common.USER
            n = min(len(new) - done, common.USER - oo)
            mode1.write_at(f, T2 + r, common.USER, oo, new[done : done + n], label=label, expect=expect[done : done + n])
            touched.append((T2 + r, 1))
            done += n

    tramp = build_tramp()
    tent = LOGICAL0 + TRAMP_OFF
    patch(CALL_OFF, b"\x20" + tent.to_bytes(2, "little"), CALL_ORIG, "syscard call")
    patch(TRAMP_OFF, tramp, b"\0" * len(tramp), "syscard trampoline")
    patch(CODE_OFF, code, b"\0" * len(code), "syscard hook code")
    patch(PLAYCALL_OFF, b"\x20" + play_entry().to_bytes(2, "little"), PLAYCALL_ORIG, "syscard AD_CPLAY call")
    patch(DATA_OFF, data, b"\0" * len(data), "syscard hangul tiles")
    return f"시스템 카드 안내 한글 띠: 코드 {len(code)}B · 타일·BAT 자료 {len(data)}B (rel {IPL_REL}~27 안, 정상 부팅 구역 불변)"


def verify_iso(iso) -> str:
    """굽고 난 이미지에서 훅 호출부·코드·자료가 의도한 그대로인지 되읽는다 + 안내 프로그램 이미지의 나머지(원판 쪽)는 안 바뀌었는지."""
    code, entry = build_code()
    data = build_data()
    with open(iso, "rb") as f:
        got = bytearray()
        for rel in range(IPL_REL, 28):
            f.seek((common.T2_SECTOR + rel) * common.RAW + common.USER_OFF)
            got += f.read(common.USER)
    tramp = build_tramp()
    assert got[CALL_OFF : CALL_OFF + 3] == b"\x20" + (LOGICAL0 + TRAMP_OFF).to_bytes(2, "little"), "훅 호출부가 다르다"
    assert got[TRAMP_OFF : TRAMP_OFF + len(tramp)] == tramp, "트램펄린이 다르다"
    assert got[CODE_OFF : CODE_OFF + len(code)] == code, "훅 코드가 다르다"
    assert got[PLAYCALL_OFF : PLAYCALL_OFF + 3] == b"\x20" + play_entry().to_bytes(2, "little"), "AD_CPLAY 호출부가 다르다"
    assert got[DATA_OFF : DATA_OFF + len(data)] == data, "한글 타일 자료가 다르다"
    orig = b"".join(common.track_data(IPL_REL + i, 1) for i in range(24))
    diff = [i for i in range(len(orig)) if orig[i] != got[i]]
    allowed = set(range(PLAYCALL_OFF, PLAYCALL_OFF + 3)) | set(range(CALL_OFF, CALL_OFF + 3)) | set(range(TRAMP_OFF, TRAMP_OFF + len(tramp))) | set(range(CODE_OFF, CODE_OFF + len(code))) | set(range(DATA_OFF, DATA_OFF + len(data)))
    assert set(diff) <= allowed, "안내 프로그램 이미지의 다른 자리가 바뀌었다"
    return f"시스템 카드 안내 되읽기 OK — 호출부 3B · 트램펄린 {len(tramp)}B · 코드 {len(code)}B · 자료 {len(data)}B, 이미지 나머지 불변"


def preview(out_dir) -> None:
    """굽기 전 미리보기 — 원판 강제 경로 화면(`orig-forced-old-path.png`) 위에 고정 문구와 자막 넷의 띠(1배·4배)."""
    import numpy as np
    from PIL import Image

    out_dir = Path(out_dir)
    a = np.array(Image.open(out_dir / "orig-forced-old-path.png").convert("RGB"))
    bg = (36, 180, 144)
    for n, text in enumerate([TEXT] + [t for t, _s in SUBS]):
        band, x0 = render_mask(text)
        new = a.copy()
        new[BAND_Y0 : BAND_Y0 + 24, :, :] = bg
        for y in range(24):
            for x in range(256):
                if band[y, x]:
                    new[BAND_Y0 + y, x] = (252, 252, 252)
        Image.fromarray(new).save(out_dir / f"preview-band{n}-1x.png")
        Image.fromarray(new).resize((1024, 928), Image.NEAREST).save(out_dir / f"preview-band{n}-4x.png")
        print(f"띠 {n}: 폭 {int(band.any(axis=0).sum())}px(시작 x={x0}) — {text}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--preview":
        preview(sys.argv[2])
    else:
        code, entry = build_code()
        print(f"훅 {len(code)}B @ ${entry:04X} (여유 {CODE_MAX - len(code)}B) · 자료 {len(build_data())}B / {DATA_MAX}B · 시각표 {schedule_frames()}")
