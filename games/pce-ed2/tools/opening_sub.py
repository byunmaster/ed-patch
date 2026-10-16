"""오프닝 나레이션 자막 — 타이틀·오프닝 모듈(rel 4098)에 **스프라이트 자막**을 심는다 (2026-10-13).

    python3 games/pce-ed2/tools/opening_sub.py            # 조립 결과·크기·타임라인 확인
    python3 games/pce-ed2/tools/opening_sub.py --preview  # 줄 이미지를 PNG 로(work/review/opening/)

pce-ed1 `opening_sub.py` 와 **같은 방식**(빌드 때 줄을 스프라이트 셀로 미리 굽고, 실행 중엔 VRAM 으로 옮기기만 한다)이지만
ED2 의 사정이 훨씬 단순해 새로 썼다(조사 근거: docs/devlog.md 2026-10-13 「오프닝 음성」):

  · 오프닝 = 카드 화면에서 Run → 모듈 `$5518` 의 `JSR $E012`(CD_PLAY, 트랙 21 = 나레이션 143초) → 세피아 슬라이드쇼.
    **모듈은 rel 4098 ×32섹터(뱅크 0x68~0x6F)** 이고 본 프로그램(rel 130)과 다른 이미지다 — 자유 공간이 따로 있다.
  · VRAM 은 앞 24KB 만 쓰고 SAT($7F00) 밖은 통째로 비어 있다. 표시 해상도는 전 장면 같다(VSR 0x0F02 · CR 0xC8 =
    BG·스프라이트 켜짐) — ED1 처럼 장면마다 높이를 보정하지 않아도 된다. 게임이 매 프레임 SAT 를 DMA 하므로 VRAM 의 SAT 만 쓰면 된다.
  · 스프라이트 팔레트 8 은 늘 0 이다. 색은 IRQ1 이 VCE 로 올리는 **팔레트 그림자**(`$2BBB`)의 해당 항목(`$2EBD~`)에 쓴다.
  · 훅은 하나 — CD_PLAY 호출(`$5518`)을 우리 스텁으로. 스텁이 RAM(`$2300`)에 init 을 복사해 거기서 CD_READ(자막 셀 → 뱅크 0x70~)·
    CD_PLAY·IRQ 훅 설치를 한다(CD_READ 는 MPR 을 건드리므로 RAM 에서). IRQ1 의 `JSR $E063`(`$4099`)은 **런타임에** RAM 트램펄린으로 바꿔 낀다.
  · 시각 원점: CD_PLAY 복귀에서 프레임 카운터 0(IRQ 블록이 한 번 돌 때마다 +1). 자막 시각 = AUDIO_LAG + 초 × 59.826 (AUDIO_LAG 는 mednafen 에서 0 — 아래 상수의 실측 설명).

⚠ 셀 하나 = 16×16 스프라이트 = 64워드. 데이터는 평면 0(글자)·1(테두리)만 싣고(64B), 평면 2·3 은 런타임이 0 으로 채운다.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import asm
import common
from asm import Asm

from shared import fonts

SUBS = common.GAME_DIR / "data" / "opening_sub.json"

# ── 디스크 · 메모리 자리 ──────────────────────────────────────────────────
MODULE_REL = 4098  # 타이틀·오프닝 모듈(IPL 둘째 적재 rel 4098 ×32 → 뱅크 0x68~0x6F)
MODULE_BANK0 = 0x68
BANK = 8192
CDPLAY_BANK, CDPLAY_OFF = 0x68, 0x1518  # `20 12 E0`(JSR $E012) — 논리 $5518
IRQ_BANK, IRQ_OFF = 0x68, 0x00D2  # IRQ1 끝의 `E6 2F 07 38`(INC $2F · RMB0 $38) — 논리 $40D2. $2F 는 **매 VBlank** 올라가는 진짜 프레임 수다(아래 devlog)
CODE_BANK, CODE_OFF = 0x69, 0x0549  # 모듈의 0xFF 패딩(뱅크 0x69 +0x549 ~ 0x6A +0x1E00, 14.5KB) — 논리 $6549 (MPR3=0x69 늘 걸림)
CODE_ADDR = 0x6000 + CODE_OFF
CODE_MAX = 0x1000  # 코드·표 상한(뱅크 0x69 의 남은 6.8KB 안에서 4KB)
DATA_REL = 4151  # 원본에서 통째로 0 인 섹터 78개(rel 4151~4228, 거울 +36864 도 0 — 패키지 칸 밖) — 14섹터를 쓴다
DATA_BANK = 0x70  # 오프닝 내내 비어 있는 뱅크(원판 덤프 7개 실측: 0x70~0x7F · 0x81~0x87 전부 0)
OPENING_TRACK = 0x21  # CD_PLAY 인자 $F8 — 게이트 겸 확인용(스텁은 이 호출 자리 하나에만 걸려 있어 따로 안 가른다)

TRAMP_IRQ = 0x22C0  # 워크 RAM — 원판 7개 덤프에서 늘 0 인 $22BC~$2615 안
V_FR, V_ON, V_UPG, V_UPB, V_UPC, V_UPN, V_UPK, V_SAVE, V_TMP = (
    0x22E0, 0x22E2, 0x22E3, 0x22E4, 0x22E5, 0x22E6, 0x22E7, 0x22E8, 0x22E9,
)  # fmt: skip
V_CODE, V_YL = 0x22EA, 0x22EC  # 16비트(패턴 코드 · y)
V_F7 = 0x22EF  # IRQ 가 들어올 때 끊긴 쪽의 VDC 레지스터 선택값 — 0~2 면 끊긴 쪽이 MAWR/VWR 쓰기 한복판(게임이 그림을 CD→VRAM 으로 읽는 중일 수 있다)
Z_DEF, DEFER_MAX = 0xCB, 90  # 연속으로 미룬 틱 수 · 그만큼 미루면 「늘 2」 구간이라 그냥 한다
V_BG = 0x22EE  # BG 자막을 그렸으면 1 — 지울 때만 BAT 를 만진다(스킵해 타이틀로 간 뒤엔 건드리지 않는다)
RAM_INIT, RAM_INIT_MAX = 0x2300, 0xC0
Z_EV, Z_DP, Z_PG, Z_T0, Z_T1, Z_A, Z_B, Z_X = 0xC0, 0xC2, 0xC4, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA  # ZP $20C0~ (원판 덤프 7개에서 0)
PAL_SHADOW = 0x2BBB  # IRQ1 이 VCE 로 올리는 512색 그림자
PAL8_C1 = PAL_SHADOW + 512 + 8 * 32 + 2  # 스프라이트 팔레트 8 의 색 1(글자·흰) — 색 2(테두리·검정)가 그 뒤
PAL_BG15_C1 = PAL_SHADOW + 15 * 32 + 2  # BG 팔레트 15 의 색 1(글자·흰) — 색 2(테두리·검정)가 그 뒤
SAT_WORD = 0x7F00  # VRAM 워드 주소
SLOT0, SLOTS = 36, 28  # 우리 스프라이트 슬롯(별밤은 0~31 을 쓴다) — 한 항목 = 32×16 스프라이트(셀 둘)
BUF_CELLS = 40  # 첫째 버퍼(0x4000)의 셀 수 — 누적 쪽 최대
BUF1_CELLS = 36  # 둘째 버퍼(0x4A00)는 36 셀까지 — VRAM 0x5300 워드부터는 게임이 덮어쓴다(실측: 40 셀 쪽 끝이 깨졌다). 36 셀 넘는 쪽은 첫째 버퍼로(`buf_of`)
BUF_WORDS = (0x4000, 0x4000 + BUF_CELLS * 64)  # 셀 버퍼 둘(VRAM 워드). 코드 = BUF>>5 가 4 의 배수여야 32 폭 스프라이트가 된다
SPR_ATTR = 0x0188  # 팔레트 8 · SPBG=1(그림 위)
FLAG_ZP = 0x38  # 게임의 IRQ 처리 플래그 — 비트 2 = 팔레트 다시 올림
V_OPENING = 0x2B7C  # 작업 슬롯 1 의 상태 — 오프닝 내내 0xFF(원판 덤프 7개 · 우리 빌드 덤프 실측), 스킵해 타이틀로 가면 1 — 바뀌면 우리는 물러난다. ⚠ `$2268` 은 BIOS 가 쓰는 MPR 그림자라 CD_READ 를 부르는 우리 빌드에선 값이 달라진다(0x80≠0x6C)

# ── 조판 ─────────────────────────────────────────────────────────────────
W, H = 256, 232
CELL = 12  # 글리프 셀(px)
ADV_LATIN = 8
LINE_CAP = 244  # 줄 폭 상한(px) — 화면(256) 안. 16px 격자를 줄 시작에서 어긋나게 잡아(line_cells `pad`) 마지막 32 폭 스프라이트가 x≤223 에 들게 한다(마스터 10-14 「칸을 늘리자」)
CELL_PX = 16
GLYPH_ROWS = 14
LINE_H = 18
MAX_LINES = 2
BOTTOM_SINGLE = False  # 번역 규칙 2-14 — 한 줄 자막을 두 줄의 둘째 줄 높이(바닥)에. 마스터가 검은 띠 아래 한 줄을 보고 「이상하다」 해서 규칙이 다시 정해질 때까지 끈다(10-15) — 값 하나로 켠다
Y0 = 187  # 첫 줄 윗단(화면 행) — 마지막 줄 잉크 아래끝 ~ 화면 아래끝 16px(마스터 10-15 「16px로 통일」). 레터박스 그림은 184 아래가 검정이다
Y0_3, LINE_3 = 184, 16  # 세 줄 쪽(마스터 10-14 「건강하게 자랐다」 합침) — 검은 띠(184~232)에 들게 윗단을 올리고 줄 간격을 좁힌다
Y0_ACC, LINE_ACC = 44, 18  # 이어 붙이는 별하늘 묶음(group)의 윗단·줄 간격 — pce-ed1 별하늘과 같은 값(마스터 10-13). ⚠ 별(스프라이트 32 개)이 행 96~160 에 몰려 스캔라인 16 스프라이트 한도를 채우므로 다섯 줄 묶음의 아랫줄이 잘릴 수 있다(24·16 으로 올렸던 이유) — 실화면 확인 결과는 devlog
Y0_TOP = 44  # 별하늘(우주 배경) 구간은 위에서부터 — pce-ed1 오프닝 별하늘 자막과 같은 값(TOP 44, 줄 간격 LINE_H 18). 대본에서 "lay":"top" (마스터 10-13)
DY = fonts.GALMURI11_DY
FPS = 59.826
AUDIO_LAG = 0  # 프레임 카운터 0(CD_PLAY 복귀) → 음성 t=0. 🔴 mednafen 은 CD-DA 를 탐색 지연 없이 **즉시** 시작한다(세이브스테이트의 CDDA 읽기 위치로 실측: V_FR=19 에 20.7프레임 · V_FR=3019 에 3021.6프레임 — 오디오가 카운터보다 1~2프레임 앞). 그래서 이전 값 110→90→78 은 기준점이 틀린 채 쪽 시각(받아쓰기 t0 — 첫 쪽은 1.1초 일찍 잡혔다)으로 때운 것이다(마스터 10-14 「세리오스 목소리가 먼저 나오는데 자막이 늦게 나왔어」). 실기는 탐색 시간만큼 오디오가 늦게 시작하니 자막이 먼저 뜬다 — 실기 값은 따로 재야 한다
END_HOLD = 30  # 음성 끝 뒤 자막을 더 두는 프레임(0.5초 — 마스터 10-14 「말끝나자마자 닫히는 게 타이트」). 다음 쪽 시작과 겹치면 다음 쪽 보이기가 대신 덮는다
UPLOAD_LEAD = 30  # 보이기 전에 올리기 시작하는 프레임
CELLS_PER_TICK = 2


def _adv(ch):
    return ADV_LATIN if ord(ch) < 0x1100 else CELL


def text_w(s):
    return sum(_adv(c) for c in s)


def center_w(text):
    """가운데 맞춤용 폭(px) — 줄 끝 「.」「,」「…」 글자는 뺀다(번역 규칙 2-8, 마스터 10-15 「마침표만 다른 두 줄은 시작이 맞는다」)."""
    t = text.rstrip(".,…")
    return text_w(t) + 2


def wrap_words(text, cap=LINE_CAP):
    lines, cur = [], ""
    for w_ in text.split(" "):
        t = f"{cur} {w_}" if cur else w_
        if text_w(t) + 2 > cap and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def render_line(text):
    """한 줄 → (white, outline) 0/1 배열(14행 × (폭+2))."""
    import numpy as np

    bdf = fonts.galmuri()
    wpx = text_w(text) + 2
    m = np.zeros((GLYPH_ROWS, wpx), dtype=np.uint8)
    x = 1
    for c in text:
        if c != " ":
            b = bdf.bits(c, dy=DY, rows=LINE_H - 2, width=CELL)[:12]
            if c == "…":
                b = np.zeros_like(b)
                b[10, [1, 5, 9]] = 1
            h, w_ = b.shape
            w_ = min(w_, wpx - x)
            m[1 : 1 + h, x : x + w_] |= b[:, :w_]
        x += _adv(c)
    edge = np.zeros_like(m)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                edge |= np.roll(np.roll(m, dy, 0), dx, 1)
    edge &= ~m
    return m, edge


PIC_MARGIN = 4  # 그림 가장자리 ↔ 글 안쪽 여백(px) = 반각 공백 한 칸 폭(SPACE_PX 4) — 마스터 10-13 「그림 시작지점에서 반각공백정도 띄우고」(9px → 4px)
PIC_L, PIC_R = 32, 216  # 그림 칸(화면 x, 오른쪽은 배타) — 에뮬 캡처 실측(영웅 그림 x 32~215)


# ── 별하늘 BG 자막(마스터 10-13 「한 화면에」) ─────────────────────────────
# 별하늘은 BG 가 한 가지 빈 타일(0x7EF)뿐이다(실측: 보이는 32칸 전부) — 자막을 스프라이트가 아니라 BG 타일에 그리면 별 스프라이트의
# 스캔라인 16 개 한도와 무관하다(다섯째 줄이 깨지던 원인). 글자는 8×8 타일(평면 0 = 글자 · 평면 1 = 테두리)로 쪼개 VRAM $4000~ 에 올리고
# BAT(64×64, 한 줄 64 워드) 를 쪽마다 한 줄씩 채운다. 줄 높이 16(타일 둘) · 호흡 사이 한 타일 줄(8px) 빈칸.
BG_ROW0 = 7  # 첫 글줄의 BAT 행 — 별하늘은 줄이 쌓여 가는 누적 노출(넷 단계)이다. **마지막 단계(두 덩이 전체)가 화면 세로 가운데**에 오게 골랐다(마스터 10-16 「우주 장면 아래쪽으로 치우친 것 같다, 중앙에 오도록」 — 10-15 에 단계마다 편차의 최댓값을 줄이려 행 9 로 잡았더니 전체 장면이 +21px 아래였다). 행 7 · 글 내림 0: 마지막 단계 잉크 위·아래 여백 56·53px(실측 — 내림 2 였을 땐 58·51, 처음 행 9 는 74·35). 앞 단계(일부만 보이는 동안)는 위로 치우친다 — 마스터 판정 대기
BG_COL0 = 6  # 글 왼쪽 끝 = 8px × 6 = 48 — pce-ed1 별하늘 캡처 실측(341 폭 화면 63px = 화면 비율 18.5% → 256 폭 47px)을 8px 격자에 맞춤. 마스터 10-13 「우주화면 글자위치는 pce-ed1 오프닝 기준」
BG_PAL = 15  # BAT 팔레트 — 색 1 흰 · 색 2 검정(`t_f` 가 그림자에 쓴다)
BG_TILE0 = 0x400  # 타일 번호 시작 = VRAM 워드 $4000(스프라이트 버퍼 자리 — 별하늘엔 스프라이트 자막이 없다)
BG_TILES_MAX = (0x5300 - 0x4000) // 16  # 타일 수 상한(워드 $4000~$5300 = 304 타일 — 게임이 $5300 부터 덮어쓴다)
BG_BLANK = 0x07EF  # 원판 BAT 의 빈 칸(팔레트 0 · 타일 0x7EF)
# 호흡 사이 빈 줄은 없다(마스터 10-13) — 대본 `"gap": 타일 행 수` 가 있는 쪽 앞에만 둔다(「아무도 알아채지 못했다.」 다음 한 줄 = 2)
BG_SHIFT_Y = 0  # 줄 블록(16행) 안에서 글(14행)을 내리는 양
BG_CLEAR_ROWS = 24  # 지울 BAT 행 수(행 5 부터)


def line_cells(text, center=False, left=False, x0=None):
    """한 줄 → (격자 시작 x, [64B 셀 | None(빈 셀)]). 셀 = 평면0 16워드 + 평면1 16워드(14·15행은 0). 행은 16비트 리틀엔디언, 비트15 = 왼쪽.
    `x0` 를 주면 글 시작을 거기로(블록 맞춤). 줄이 넓어 마지막 32 폭 스프라이트가 x>223(SAT x 한 바이트 한계)이 되면 격자를 왼쪽으로 물려
    (글 앞에 빈 열 `pad` 개) 마지막 스프라이트가 x=223 에 오게 한다 — 반환 x 는 격자 시작(음수 가능, ≥-31)."""
    import numpy as np

    m, edge = render_line(text)
    wpx = m.shape[1]
    # 줄 시작은 그림 왼쪽 끝에 맞추고, 그림 폭을 넘는 줄(또는 제목 쪽 `align: center`)만 그림 가운데 기준(마스터 10-13)
    if x0 is None:  # 줄마다 그림(띠) 가운데 — 마스터 10-15 「음성 자막은 가운데 정렬, 애니메이션 자막 같은 느낌으로」
        x0 = max(0, (PIC_L + PIC_R - center_w(text)) // 2)
    ncell = (wpx + CELL_PX - 1) // CELL_PX
    pad = 0
    if x0 + CELL_PX * (ncell + (ncell & 1)) - 32 > 223:
        pad = x0 - (223 - 32 * (-(-(223 - x0) // 32)))
        m = np.pad(m, ((0, 0), (pad, 0)))
        edge = np.pad(edge, ((0, 0), (pad, 0)))
        wpx += pad
    cells = []
    for c in range((wpx + CELL_PX - 1) // CELL_PX):
        out = bytearray()
        for plane in (m, edge):
            for r in range(16):
                w = 0
                if r < GLYPH_ROWS:
                    for bit in range(16):
                        x = c * CELL_PX + bit
                        if x < wpx and plane[r, x]:
                            w |= 0x8000 >> bit
                out += w.to_bytes(2, "little")
        cells.append(bytes(out) if any(out) else None)
    return x0 - pad, cells


def line_tiles(text):
    """한 줄 → 타일 열 목록 [(위 타일, 아래 타일)] — 타일 = 8×8 BG 타일 32B(평면 0·1 한 행씩 끼워 8행 → 평면 2·3 은 0) 또는 None(빈 타일)."""
    import numpy as np

    m, edge = render_line(text)
    assert not m[:, 0].any(), text  # 왼쪽 한 열은 글 잉크가 없다(테두리만) — 떼어 내 글 잉크를 8px 격자에 맞춘다
    h, w = m.shape
    cols = (w - 1 + 7) // 8
    blk = np.zeros((2, 16, cols * 8), dtype=np.uint8)  # [평면][행][열]
    blk[0, BG_SHIFT_Y : BG_SHIFT_Y + h, : w - 1] = m[:, 1:]
    blk[1, BG_SHIFT_Y : BG_SHIFT_Y + h, : w - 1] = edge[:, 1:]
    out = []
    for c in range(cols):
        pair = []
        for half in (0, 1):
            tile = bytearray()
            for r in range(8):
                for plane in (0, 1):
                    v = 0
                    for bit in range(8):
                        v |= int(blk[plane, half * 8 + r, c * 8 + bit]) << (7 - bit)
                    tile.append(v)
            tile += bytes(16)
            pair.append(bytes(tile) if any(tile) else None)
        out.append(tuple(pair))
    return out


def bg_page(lines, t0, t1, grp, st, gap=0):
    """별하늘 한 호흡(쪽) → 쪽 dict. `st` = 그룹 상태 {row, pages, n, tiles} — 이미 올린 타일은 다시 안 올리고(번호 재사용), BAT 줄은 새 줄만 쓴다."""
    import struct

    if st["pages"]:
        st["row"] += gap
    first = st["n"]
    new, rows = [], []
    for line in lines:
        cols = line_tiles(line)
        col0 = min(32 - len(cols), max(0, round((256 - center_w(line)) / 2 / 8)))  # 줄마다 화면 가운데(8px 격자) — 마스터 10-15
        assert col0 + len(cols) <= 32, (line, len(cols))
        for half in (0, 1):
            ent = [BG_BLANK] * 32
            for c, pair in enumerate(cols):
                tl = pair[half]
                if tl is None:
                    continue
                idx = st["tiles"].get(tl)
                if idx is None:
                    idx = st["tiles"][tl] = BG_TILE0 + st["n"]
                    st["n"] += 1
                    new.append(tl)
                ent[col0 + c] = (BG_PAL << 12) | idx
            rows.append(((st["row"] + half) * 64, struct.pack("<32H", *ent)))
        st["row"] += 2
    assert st["n"] <= BG_TILES_MAX and st["row"] <= BG_ROW0 + BG_CLEAR_ROWS, (st["n"], st["row"])
    st["pages"] += 1
    blob = b"".join(new) + b"".join(r for _a, r in rows)
    return {
        "t0": t0, "t1": t1, "lines": list(lines), "cells": [], "group": grp, "y0": 0,
        "bg": {"dest": (BG_TILE0 + first) * 16, "ntiles": len(new), "rows": [a for a, _r in rows]}, "blob": blob,
    }  # fmt: skip


def split_pages(text):
    """`|` = 쪽 나눔 · `\n` = 줄 나눔(손으로 정한 꼴). 둘 다 없으면 어절 자동 줄바꿈."""
    if "|" in text or "\n" in text:
        return [pg.split("\n") for pg in text.split("|")]
    return _split_auto(text)


def _split_auto(text):
    """문장 → 페이지(최대 2줄) 목록. 3줄째가 필요하면 새 페이지(어절 경계 · 쉼표·마침표 뒤를 선호하지 않고 채우는 만큼)."""
    lines = wrap_words(text)
    pages = [lines[i : i + MAX_LINES] for i in range(0, len(lines), MAX_LINES)]
    # 마지막 페이지가 한 줄뿐이고 앞이 꽉 찼으면 균형을 위해 그대로 둔다(어절 단위라 안전)
    return pages


def build_pages(script=None):
    """대본 → 페이지 목록 [{t0, t1(초), lines, cells: [(x, row, 64B)]}] 와 셀 수 통계. 긴 문장은 글자 수 비례로 시간을 나눈다."""
    data = script or json.loads(SUBS.read_text(encoding="utf-8"))
    pages = []
    bgst = None
    acc_group, acc = None, []  # 같은 group 의 쪽은 지우지 않고 아래로 이어 붙인다(별하늘 — 마스터 10-13 「한 화면에 append」)
    for sub in data["subs"]:
        pgs = split_pages(sub["text"])
        grp = sub.get("group")
        if grp is None or grp != acc_group:
            acc_group, acc = grp, []
            bgst = {"row": BG_ROW0, "pages": 0, "n": 0, "tiles": {}}
        weights = [sum(len(l) for l in p) for p in pgs]
        tot = sum(weights)
        t = sub["t0"]
        cuts = sub.get("cuts")  # 쪽 경계를 파형에서 잰 시각(초)으로 직접 준다 — 없으면 글자 수 비례(10-14: 「|」 쪽 중간이 실제 발화와 어긋났다)
        assert cuts is None or len(cuts) == len(pgs) - 1, (sub["text"], cuts)
        starts = [sub["t0"]] + list(cuts or []) + [sub["t1"]]
        for k, (p, wt) in enumerate(zip(pgs, weights)):
            dur = starts[k + 1] - starts[k] if cuts else (sub["t1"] - sub["t0"]) * wt / tot
            t = starts[k] if cuts else t
            if sub.get("lay") == "top":  # 별하늘 — BG 타일 자막(스프라이트 아님)
                assert grp is not None, "별하늘 쪽은 group 이 있어야 한다(한 화면에 이어 붙인다)"
                pages.append(bg_page(p, t, t + dur, grp, bgst, sub.get("gap", 0) if p is pgs[0] else 0))
                t += dur
                continue
            for line in p:
                x0, cs = line_cells(line)
                acc.append((line, x0, cs))
            if grp is None:
                rows, acc = acc, []
            else:
                rows = list(acc)
            three = grp is None and len(rows) > 2
            pitch = LINE_3 if three else LINE_H if grp is None else LINE_ACC
            cells = []
            for row, (_line, x0, cs) in enumerate(rows):
                for k in range(0, len(cs), 2):  # 32×16 스프라이트 = 이웃한 셀 둘
                    a, b = cs[k], cs[k + 1] if k + 1 < len(cs) else None
                    if a is None and b is None:
                        continue
                    cells.append((x0 + CELL_PX * k, row * pitch, a or bytes(64)))
                    cells.append((x0 + CELL_PX * (k + 1), row * pitch, b or bytes(64)))
            assert len(cells) <= BUF_CELLS and len(cells) // 2 <= SLOTS, (p, len(cells))
            pages.append({"t0": t, "t1": t + dur, "lines": [r[0] for r in rows], "cells": cells, "blob": b"".join(c[2] for c in cells), "group": grp, "y0": Y0_ACC if grp is not None else Y0_3 if three else Y0 + (LINE_H if BOTTOM_SINGLE and len(rows) == 1 else 0), "lead": sub.get("lead", UPLOAD_LEAD)})
            t += dur
    return pages


# ── 데이터 블롭(디스크) · 페이지 표 · 사건 표 ───────────────────────────────
def pack_data(pages):
    """페이지의 셀 바이트를 뱅크 경계를 안 넘게 이어 붙인다 → (블롭 bytes, 페이지별 (뱅크 번호, 창 주소))."""
    blob = bytearray()
    where = []
    for p in pages:
        need = len(p["blob"])
        off = len(blob) % BANK
        if off + need > BANK:
            blob += bytes(BANK - off)
            off = 0
        where.append((DATA_BANK + len(blob) // BANK, 0xA000 + off))  # MPR5($A000) 창 기준
        blob += p["blob"]
    sectors = (len(blob) + 2047) // 2048
    blob += bytes(sectors * 2048 - len(blob))
    return bytes(blob), where


def f(t):
    return int(round(t * FPS)) + AUDIO_LAG


def buf_of(pages):
    """쪽마다 쓸 버퍼(0/1) — 이웃은 서로 다른 버퍼. 36 셀을 넘는 쪽은 짝수(첫째) 버퍼에 오게 맞춘다."""
    big = {i % 2 for i, p in enumerate(pages) if len(p["cells"]) > BUF1_CELLS}
    assert len(big) <= 1, "큰 쪽이 두 패리티에 걸린다 — 쪽을 나눠라"
    off = big.pop() if big else 0
    return [(i + off) % 2 for i in range(len(pages))]


def events(pages):
    """[(프레임, op, a, b)] — op 1 = 올리기(page, buf) · 2 = 보이기(page, buf) · 3 = 지우기 · 0xFF = 끝."""
    ev = []
    bufs = buf_of(pages)
    for i, p in enumerate(pages):
        buf = bufs[i]
        if "bg" not in p:  # BG 쪽은 올리기 없이 보이기 때 한 번에(타일 수십 개 + BAT 줄)
            ev.append((f(p["t0"]) - p.get("lead", UPLOAD_LEAD), 1, i, buf))
        ev.append((f(p["t0"]), 2, i, buf))
        nxt = f(pages[i + 1]["t0"]) if i + 1 < len(pages) else None
        end = f(p["t1"]) + END_HOLD
        if nxt is None or (pages[i + 1]["group"] is None or pages[i + 1]["group"] != p["group"]) and end < nxt - 12:
            ev.append((min(end, nxt - 1) if nxt else end, 3, 0, 0))
    last = pages[-1]
    ev.append((f(last["t1"]) + 120, 0xFF, 0, 0))
    ev.sort(key=lambda e: (e[0], e[1]))
    return ev


# ── 6280 어셈블 ───────────────────────────────────────────────────────────
OPS_EXTRA = {
    ("ST0", "imm"): 0x03,
    ("ST1", "imm"): 0x13,
    ("ST2", "imm"): 0x23,
    ("INC", "abs"): 0xEE,
    ("DEC", "abs"): 0xCE,
    ("LDA", "zpx"): 0xB5,
    ("STA", "zpx"): 0x95,
    ("SMB2", "zp"): 0xA7,
    ("RMB0", "zp"): 0x07,
    ("ADC", "absx"): 0x7D,
    ("CMP", "absx"): 0xDD,
    ("STX", "abs"): 0x8E,
    ("LDX", "abs"): 0xAE,
    ("LDY", "abs"): 0xAC,
    ("STY", "abs"): 0x8C,
    ("LDX", "zp"): 0xA6,
    ("LDY", "zp"): 0xA4,
    ("CPX", "zp"): 0xE4,
    ("ORA", "zp"): 0x05,
    ("LDA", "absy"): 0xB9,
    ("INC", "zp"): 0xE6,
    ("STA", "zp"): 0x85,
    ("SBC", "abs"): 0xED,
}
for _k, _v in OPS_EXTRA.items():
    asm.OPS.setdefault(_k, _v)


class A(Asm):
    def op(self, mn, mode="imp", arg=None):
        if mode in ("zpx", "zpy"):
            self.out.append(asm.OPS[(mn, mode)])
            self.out.append(arg & 0xFF)
            return
        super().op(mn, mode, arg)

    def block(self, opc, src, dst, ln):
        self.out.append(opc)
        for v in (src, dst, ln):
            if isinstance(v, str):
                self.fix.append((len(self.out), v, "abs"))
                self.out += b"\0\0"
            else:
                self.out += v.to_bytes(2, "little")

    def tia(self, src, dst, ln):
        self.block(0xE3, src, dst, ln)

    def tii(self, src, dst, ln):
        self.block(0x73, src, dst, ln)


def _vdc_addr(a, hi, lo):
    """MAWR 선택 + 워드 주소 (hi:lo 즉값)."""
    a.op("ST0", "imm", 0)
    a.op("ST1", "imm", lo)
    a.op("ST2", "imm", hi)
    a.op("ST0", "imm", 2)


def tick_code(L):
    """모듈 코드 — 스텁 · 틱 · 올리기 · 사건 · 보이기 · 지우기. `L` = 앞 패스의 라벨 주소(첫 패스는 0)."""
    a = A(CODE_ADDR)
    g = lambda k: L.get(k, 0)
    # ── 스텁(CD_PLAY 호출 자리가 JSR 로 들어온다) ─────────────────────────────
    a.label("stub")
    a.tii(g("rinit_img"), RAM_INIT, g("rinit_len"))
    a.tii(g("tramp_img"), TRAMP_IRQ, TRAMP_LEN)
    a.op("JMP", "abs", RAM_INIT)
    # ── 틱(IRQ 트램펄린이 부른다) ───────────────────────────────────────────
    a.label("tick")
    a.op("LDA", "abs", V_ON)
    a.op("BNE", "rel", "t_go")
    a.op("RTS")
    a.label("t_go")
    a.op("LDA", "abs", V_OPENING)
    a.op("CMP", "imm", 0xFF)
    a.op("BEQ", "rel", "t_in")
    a.op("JSR", "abs", "hide")  # 스킵 — 타이틀 위에 자막을 남기지 않는다
    a.op("STZ", "abs", V_ON)
    a.op("RTS")
    a.label("t_in")
    a.op("INC", "abs", V_FR)
    a.op("BNE", "rel", "t_f")
    a.op("INC", "abs", V_FR + 1)
    a.label("t_f")
    a.op("LDA", "imm", 0xFF)  # 팔레트 그림자: 색 1 흰(0x1FF) · 색 2 검정
    a.op("STA", "abs", PAL8_C1)
    a.op("LDA", "imm", 0x01)
    a.op("STA", "abs", PAL8_C1 + 1)
    a.op("STZ", "abs", PAL8_C1 + 2)
    a.op("STZ", "abs", PAL8_C1 + 3)
    a.op("LDA", "imm", 0xFF)  # BG 팔레트 15 도 같게(별하늘 BG 자막)
    a.op("STA", "abs", PAL_BG15_C1)
    a.op("LDA", "imm", 0x01)
    a.op("STA", "abs", PAL_BG15_C1 + 1)
    a.op("STZ", "abs", PAL_BG15_C1 + 2)
    a.op("STZ", "abs", PAL_BG15_C1 + 3)
    a.op("LDA", "abs", V_F7)  # 끊긴 쪽이 VDC 쓰기 한복판이면 VRAM 일(올리기·보이기·지우기)을 미룬다 — 우리가 MAWR 를 옮기면 게임이 읽던 그림 데이터가 엉뚱한 곳에 들어가 그림이 잘린다(마스터 10-15)
    a.op("CMP", "imm", 3)
    a.op("BCS", "rel", "t_g0")
    a.op("INC", "zp", Z_DEF)
    a.op("LDA", "zp", Z_DEF)
    a.op("CMP", "imm", DEFER_MAX)
    a.op("BCS", "rel", "t_g")
    a.op("RTS")
    a.label("t_g0")
    a.label("t_g")
    a.op("STZ", "zp", Z_DEF)
    a.op("LDA", "abs", V_UPG)
    a.op("CMP", "imm", 0xFF)
    a.op("BEQ", "rel", "t_ev")
    a.op("JSR", "abs", "upload")
    a.label("t_ev")
    a.op("JSR", "abs", "events")
    a.op("RTS")
    # ── 페이지 찾기: A = 페이지 번호 → Z_PG ───────────────────────────────────
    a.label("findpage")
    a.op("ASL", "imp")
    a.op("TAX")
    a.op("LDA", "absx", "pagetab")
    a.op("STA", "zp", Z_PG)
    a.op("LDA", "absx", "pagetab1")
    a.op("STA", "zp", Z_PG + 1)
    a.op("RTS")
    # ── 올리기: 틱마다 셀 CELLS_PER_TICK 개를 VRAM 버퍼로 ───────────────────────
    a.label("upload")
    a.op("LDX", "imm", CELLS_PER_TICK)
    a.label("u_loop")
    a.op("STX", "abs", V_TMP)
    a.op("LDA", "abs", V_UPC)
    a.op("CMP", "abs", V_UPN)
    a.op("BCC", "rel", "u_do")
    a.op("LDA", "imm", 0xFF)
    a.op("STA", "abs", V_UPG)
    a.op("RTS")
    a.label("u_do")
    # 목적지 워드 = BUF + UPC*64 : lo = (UPC & 3) << 6 · hi = BUF_hi + (UPC >> 2)
    a.op("AND", "imm", 3)
    for _ in range(6):
        a.op("ASL", "imp")
    a.op("STA", "abs", V_YL)  # lo 보관
    a.op("LDA", "abs", V_UPC)
    a.op("LSR", "imp")
    a.op("LSR", "imp")
    a.op("CLC")
    a.op("LDX", "abs", V_UPB)
    a.op("BNE", "rel", "u_b1")
    a.op("ADC", "imm", BUF_WORDS[0] >> 8)
    a.op("BRA", "rel", "u_set")
    a.label("u_b1")
    a.op("ADC", "imm", BUF_WORDS[1] >> 8)
    a.label("u_set")
    a.op("STA", "abs", V_YL + 1)
    a.op("ST0", "imm", 0)
    a.op("LDA", "abs", V_YL)
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "abs", V_YL + 1)
    a.op("STA", "abs", 0x0003)
    a.op("ST0", "imm", 2)
    a.op("TMA", "tma", 5)  # MPR5 에 데이터 뱅크
    a.op("STA", "abs", V_SAVE)
    a.op("LDA", "abs", V_UPK)
    a.op("TAM", "tam", 5)
    a.op("LDA", "zp", Z_DP)  # TIA 원본 주소 자가수정
    a.op("STA", "abs", g("u_tia") + 1)
    a.op("LDA", "zp", Z_DP + 1)
    a.op("STA", "abs", g("u_tia") + 2)
    a.label("u_tia")
    a.tia(0xA000, 0x0002, 64)  # 평면 0·1 (글자·테두리)
    a.op("LDA", "abs", V_SAVE)
    a.op("TAM", "tam", 5)
    a.tia("zeros", 0x0002, 64)  # 평면 2·3 = 0
    a.op("CLC")
    a.op("LDA", "zp", Z_DP)
    a.op("ADC", "imm", 64)
    a.op("STA", "zp", Z_DP)
    a.op("BCC", "rel", "u_nc")
    a.op("INC", "zp", Z_DP + 1)
    a.label("u_nc")
    a.op("INC", "abs", V_UPC)
    a.op("LDX", "abs", V_TMP)
    a.op("DEX")
    a.op("BEQ", "rel", "u_end")
    a.op("JMP", "abs", "u_loop")
    a.label("u_end")
    a.op("LDA", "abs", V_UPC)
    a.op("CMP", "abs", V_UPN)
    a.op("BCC", "rel", "u_ret")
    a.op("LDA", "imm", 0xFF)
    a.op("STA", "abs", V_UPG)
    a.label("u_ret")
    a.op("RTS")
    # ── 사건 처리 ───────────────────────────────────────────────────────────
    a.label("events")
    a.op("CLY")
    a.op("LDA", "izpy", Z_EV)
    a.op("STA", "zp", Z_T0)
    a.op("INY")
    a.op("LDA", "izpy", Z_EV)
    a.op("STA", "zp", Z_T1)
    a.op("LDA", "abs", V_FR + 1)  # 프레임 ≥ t ?
    a.op("CMP", "zp", Z_T1)
    a.op("BCC", "rel", "e_no")
    a.op("BNE", "rel", "e_due")
    a.op("LDA", "abs", V_FR)
    a.op("CMP", "zp", Z_T0)
    a.op("BCC", "rel", "e_no")
    a.label("e_due")
    a.op("INY")
    a.op("LDA", "izpy", Z_EV)  # op
    a.op("STA", "zp", Z_X)
    a.op("INY")
    a.op("LDA", "izpy", Z_EV)
    a.op("STA", "zp", Z_A)
    a.op("INY")
    a.op("LDA", "izpy", Z_EV)
    a.op("STA", "zp", Z_B)
    a.op("LDA", "zp", Z_X)
    a.op("CMP", "imm", 0xFF)
    a.op("BEQ", "rel", "e_end")
    a.op("CMP", "imm", 1)
    a.op("BEQ", "rel", "e_up")
    a.op("CMP", "imm", 2)
    a.op("BEQ", "rel", "e_show")
    a.op("JSR", "abs", "hide")
    a.op("BRA", "rel", "e_adv")
    a.label("e_end")
    a.op("JSR", "abs", "hide")
    a.op("STZ", "abs", V_ON)
    a.op("RTS")
    a.label("e_up")  # 올리기 시작: 페이지 레코드 [0]=뱅크 [1,2]=창 주소 [3]=셀 수
    a.op("LDA", "zp", Z_A)
    a.op("JSR", "abs", "findpage")
    a.op("LDA", "zp", Z_B)
    a.op("STA", "abs", V_UPB)
    a.op("LDA", "zp", Z_A)
    a.op("STA", "abs", V_UPG)
    a.op("STZ", "abs", V_UPC)
    a.op("CLY")
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "abs", V_UPK)
    a.op("INY")
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "zp", Z_DP)
    a.op("INY")
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "zp", Z_DP + 1)
    a.op("INY")
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "abs", V_UPN)
    a.op("BRA", "rel", "e_adv")
    a.label("e_show")
    a.op("JSR", "abs", "show")
    a.label("e_adv")
    a.op("CLC")
    a.op("LDA", "zp", Z_EV)
    a.op("ADC", "imm", 5)
    a.op("STA", "zp", Z_EV)
    a.op("BCC", "rel", "e_nc")
    a.op("INC", "zp", Z_EV + 1)
    a.label("e_nc")
    a.op("JMP", "abs", "events")
    a.label("e_no")
    a.op("RTS")
    # ── 보이기: SAT 항목을 VRAM 에. 레코드 [3]=셀 수 [4,5]=y0 워드 [6..]=(x+32, 줄) ──
    a.label("show")
    a.op("LDA", "zp", Z_A)
    a.op("JSR", "abs", "findpage")
    a.op("SMB2", "zp", FLAG_ZP)  # 팔레트 다시 올림
    a.op("LDY", "imm", 3)
    a.op("LDA", "izpy", Z_PG)
    a.op("BNE", "rel", "s_spr")  # 셀 수 0 = BG 쪽
    a.op("JMP", "abs", "bgshow")
    a.label("s_spr")
    # 패턴 코드 = (BUF>>5) + 2*i
    a.op("LDA", "zp", Z_B)
    a.op("BNE", "rel", "s_b1")
    a.op("LDA", "imm", (BUF_WORDS[0] >> 5) & 0xFF)
    a.op("STA", "abs", V_CODE)
    a.op("LDA", "imm", BUF_WORDS[0] >> 13)
    a.op("BRA", "rel", "s_c")
    a.label("s_b1")
    a.op("LDA", "imm", (BUF_WORDS[1] >> 5) & 0xFF)
    a.op("STA", "abs", V_CODE)
    a.op("LDA", "imm", BUF_WORDS[1] >> 13)
    a.label("s_c")
    a.op("STA", "abs", V_CODE + 1)
    _vdc_addr(a, (SAT_WORD + SLOT0 * 4) >> 8, (SAT_WORD + SLOT0 * 4) & 0xFF)
    a.op("LDY", "imm", 3)
    a.op("LDA", "izpy", Z_PG)
    a.op("LSR", "imp")
    a.op("STA", "zp", Z_T0)  # 항목 수(셀 둘 = 한 32×16 스프라이트)
    a.op("LDX", "imm", 0)  # 쓴 항목 수
    a.op("LDY", "imm", 6)  # 메타 위치
    a.label("s_loop")
    a.op("CPX", "zp", Z_T0)
    a.op("BCS", "rel", "s_blank")
    # y = y0 + (줄 ? 18 : 0)
    a.op("LDY", "imm", 4)
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "abs", V_YL)
    a.op("INY")
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "abs", V_YL + 1)
    a.op("TXA")
    a.op("ASL", "imp")
    a.op("CLC")
    a.op("ADC", "imm", 6)
    a.op("TAY")  # 6 + 2*i = x 위치
    a.op("INY")  # 줄 위치
    a.op("LDA", "izpy", Z_PG)
    a.op("BEQ", "rel", "s_r0")
    a.op("STA", "abs", V_TMP)  # 줄 y 오프셋(px, 줄 × LINE_H)
    a.op("CLC")
    a.op("LDA", "abs", V_YL)
    a.op("ADC", "abs", V_TMP)
    a.op("STA", "abs", V_YL)
    a.op("BCC", "rel", "s_r0")
    a.op("INC", "abs", V_YL + 1)
    a.label("s_r0")
    a.op("LDA", "abs", V_YL)
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "abs", V_YL + 1)
    a.op("STA", "abs", 0x0003)
    a.op("DEY")
    a.op("LDA", "izpy", Z_PG)  # x+32
    a.op("STA", "abs", 0x0002)
    a.op("STZ", "abs", 0x0003)
    a.op("LDA", "abs", V_CODE)
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "abs", V_CODE + 1)
    a.op("STA", "abs", 0x0003)
    a.op("LDA", "imm", SPR_ATTR & 0xFF)
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "imm", SPR_ATTR >> 8)
    a.op("STA", "abs", 0x0003)
    a.op("CLC")  # 코드 += 2
    a.op("LDA", "abs", V_CODE)
    a.op("ADC", "imm", 4)  # 32 폭 = 패턴 둘
    a.op("STA", "abs", V_CODE)
    a.op("BCC", "rel", "s_nx")
    a.op("INC", "abs", V_CODE + 1)
    a.label("s_nx")
    a.op("INX")
    a.op("BRA", "rel", "s_loop")
    a.label("s_blank")  # 남은 슬롯 y=0 (화면 밖)
    a.op("CPX", "imm", SLOTS)
    a.op("BCS", "rel", "s_done")
    for _ in range(4):
        a.op("STZ", "abs", 0x0002)
        a.op("STZ", "abs", 0x0003)
    a.op("INX")
    a.op("BRA", "rel", "s_blank")
    a.label("s_done")
    a.op("RTS")
    # ── 지우기: 슬롯 전부 0 ─────────────────────────────────────────────────
    a.label("hide")
    a.op("JSR", "abs", "hide_spr")
    a.op("LDA", "abs", V_BG)  # BG 자막은 그렸을 때만 지운다(스킵해 타이틀로 간 뒤 BAT 를 건드리지 않는다)
    a.op("BEQ", "rel", "h_ret")
    a.op("STZ", "abs", V_BG)
    a.op("LDA", "imm", (BG_ROW0 * 64) & 0xFF)
    a.op("STA", "abs", V_YL)
    a.op("LDA", "imm", (BG_ROW0 * 64) >> 8)
    a.op("STA", "abs", V_YL + 1)
    a.op("LDX", "imm", BG_CLEAR_ROWS)
    a.label("h_row")
    a.op("ST0", "imm", 0)
    a.op("LDA", "abs", V_YL)
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "abs", V_YL + 1)
    a.op("STA", "abs", 0x0003)
    a.op("ST0", "imm", 2)
    a.tia("blankrow", 0x0002, 64)
    a.op("CLC")
    a.op("LDA", "abs", V_YL)
    a.op("ADC", "imm", 64)
    a.op("STA", "abs", V_YL)
    a.op("BCC", "rel", "h_nc")
    a.op("INC", "abs", V_YL + 1)
    a.label("h_nc")
    a.op("DEX")
    a.op("BNE", "rel", "h_row")
    a.label("h_ret")
    a.op("RTS")
    a.label("hide_spr")
    _vdc_addr(a, (SAT_WORD + SLOT0 * 4) >> 8, (SAT_WORD + SLOT0 * 4) & 0xFF)
    a.op("LDX", "imm", SLOTS)
    a.label("h_loop")
    for _ in range(4):
        a.op("STZ", "abs", 0x0002)
        a.op("STZ", "abs", 0x0003)
    a.op("DEX")
    a.op("BNE", "rel", "h_loop")
    a.op("RTS")
    # ── BG 쪽 보이기: 레코드 [0]=뱅크 [1,2]=창 주소 [3]=0 [4]=새 타일 수 [5,6]=타일 목적지 워드 [7]=BAT 줄 수 [8..]=줄 목적지 워드(2B) ──
    # 데이터 = 새 타일(32B 씩) 뒤에 BAT 줄(64B 씩)
    a.label("bgshow")
    a.op("JSR", "abs", "hide_spr")
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", V_BG)
    a.op("CLY")
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "abs", V_UPK)
    a.op("INY")
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "zp", Z_DP)
    a.op("INY")
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "zp", Z_DP + 1)
    a.op("LDY", "imm", 4)
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "abs", V_UPN)  # 새 타일 수
    a.op("INY")
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "abs", V_YL)
    a.op("INY")
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "abs", V_YL + 1)
    a.op("INY")
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "abs", V_UPC)  # BAT 줄 수
    a.op("TMA", "tma", 5)
    a.op("STA", "abs", V_SAVE)
    a.op("LDA", "abs", V_UPK)
    a.op("TAM", "tam", 5)
    a.op("LDA", "abs", V_UPN)
    a.op("BEQ", "rel", "b_rows")
    a.op("ST0", "imm", 0)  # 타일 올리기 — MAWR = 목적지(이어서 쓴다)
    a.op("LDA", "abs", V_YL)
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "abs", V_YL + 1)
    a.op("STA", "abs", 0x0003)
    a.op("ST0", "imm", 2)
    a.label("b_tile")
    a.op("LDA", "zp", Z_DP)
    a.op("STA", "abs", g("b_tia") + 1)
    a.op("LDA", "zp", Z_DP + 1)
    a.op("STA", "abs", g("b_tia") + 2)
    a.label("b_tia")
    a.tia(0xA000, 0x0002, 32)
    a.op("CLC")
    a.op("LDA", "zp", Z_DP)
    a.op("ADC", "imm", 32)
    a.op("STA", "zp", Z_DP)
    a.op("BCC", "rel", "b_tnc")
    a.op("INC", "zp", Z_DP + 1)
    a.label("b_tnc")
    a.op("DEC", "abs", V_UPN)
    a.op("BNE", "rel", "b_tile")
    a.label("b_rows")
    a.op("LDA", "imm", 8)
    a.op("STA", "abs", V_TMP)  # 레코드 안 줄 목적지 위치
    a.label("b_row")
    a.op("LDA", "abs", V_UPC)
    a.op("BEQ", "rel", "b_done")
    a.op("LDY", "abs", V_TMP)
    a.op("ST0", "imm", 0)
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "abs", 0x0002)
    a.op("INY")
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "abs", 0x0003)
    a.op("INY")
    a.op("STY", "abs", V_TMP)
    a.op("ST0", "imm", 2)
    a.op("LDA", "zp", Z_DP)
    a.op("STA", "abs", g("b_rtia") + 1)
    a.op("LDA", "zp", Z_DP + 1)
    a.op("STA", "abs", g("b_rtia") + 2)
    a.label("b_rtia")
    a.tia(0xA000, 0x0002, 64)
    a.op("CLC")
    a.op("LDA", "zp", Z_DP)
    a.op("ADC", "imm", 64)
    a.op("STA", "zp", Z_DP)
    a.op("BCC", "rel", "b_rnc")
    a.op("INC", "zp", Z_DP + 1)
    a.label("b_rnc")
    a.op("DEC", "abs", V_UPC)
    a.op("BRA", "rel", "b_row")
    a.label("b_done")
    a.op("LDA", "abs", V_SAVE)
    a.op("TAM", "tam", 5)
    a.op("RTS")
    a.label("zeros")
    a.data(bytes(64))
    a.label("blankrow")
    a.data(BG_BLANK.to_bytes(2, "little") * 32)
    return a


def rinit_code(L, bank, rel, nsec):
    """RAM(`$2300`) init — CD_READ(자막 셀) · 상태 초기화 · 진짜 CD_PLAY · IRQ 훅 설치."""
    r = A(RAM_INIT)
    for m in (3, 4, 5, 6):
        r.op("TMA", "tma", m)
        r.op("PHA")
    r.op("LDX", "imm", 0)
    r.label("save")
    r.op("LDA", "zpx", 0xF8)
    r.op("PHA")
    r.op("INX")
    r.op("CPX", "imm", 8)
    r.op("BNE", "rel", "save")
    r.label("rd")
    for zp, val in (
        (0xF8, nsec), (0xF9, 0), (0xFA, bank), (0xFB, 0),
        (0xFC, rel >> 16), (0xFD, (rel >> 8) & 0xFF), (0xFE, rel & 0xFF), (0xFF, 6),
    ):  # fmt: skip
        r.op("LDA", "imm", val)
        r.op("STA", "zp", zp)
    r.op("JSR", "abs", 0xE009)  # CD_READ — pce-ed1 오프닝 자막이 쓰는 규약과 같다(_al 섹터 수 · _bl 뱅크 · _dl:_ch:_cl 섹터 · _dh=6)
    r.op("CMP", "imm", 0)
    r.op("BNE", "rel", "rd")
    r.op("STZ", "abs", V_FR)
    r.op("STZ", "abs", V_FR + 1)
    r.op("STZ", "abs", V_UPC)
    r.op("STZ", "abs", V_BG)
    r.op("LDA", "imm", 0xFF)
    r.op("STA", "abs", V_UPG)
    ev = L.get("events_tab", 0)
    r.op("LDA", "imm", ev & 0xFF)
    r.op("STA", "zp", Z_EV)
    r.op("LDA", "imm", ev >> 8)
    r.op("STA", "zp", Z_EV + 1)
    r.op("LDX", "imm", 8)
    r.label("restore")
    r.op("DEX")
    r.op("PLA")
    r.op("STA", "zpx", 0xF8)
    r.op("CPX", "imm", 0)
    r.op("BNE", "rel", "restore")
    r.op("JSR", "abs", 0xE012)  # 진짜 CD_PLAY — 이 복귀가 프레임 원점
    r.op("PHA")
    r.op("SEI")
    r.op("LDA", "imm", TRAMP_IRQ & 0xFF)  # `E6 2F 07 38` → `20 <트램펄린> EA` (트램펄린이 INC $2F · RMB0 $38 을 대신한다)
    r.op("STA", "abs", 0x4000 + IRQ_OFF + 1)
    r.op("LDA", "imm", TRAMP_IRQ >> 8)
    r.op("STA", "abs", 0x4000 + IRQ_OFF + 2)
    r.op("LDA", "imm", 0xEA)
    r.op("STA", "abs", 0x4000 + IRQ_OFF + 3)
    r.op("LDA", "imm", 0x20)
    r.op("STA", "abs", 0x4000 + IRQ_OFF)
    r.op("LDA", "imm", 1)
    r.op("STA", "abs", V_ON)
    r.op("CLI")
    r.op("PLA")
    r.op("STA", "abs", V_TMP)
    for m in (6, 5, 4, 3):
        r.op("PLA")
        r.op("TAM", "tam", m)
    r.op("LDA", "abs", V_TMP)
    r.op("RTS")
    return r


TRAMP_LEN = 15


def tramp_code(tick):
    t = A(TRAMP_IRQ)
    t.op("INC", "zp", 0x2F)  # 원래 자리가 하던 일 — 매 VBlank 프레임 수 올림 · 재진입 가드 해제
    t.op("RMB0", "zp", FLAG_ZP)
    t.op("TSX")
    t.op("LDA", "absx", 0x2103)  # 핸들러가 스택에 넣어 둔 $F7(끊긴 쪽의 VDC 레지스터 선택) — JSR 복귀 주소 둘 위(대관식 ending_sub 과 같은 자리)
    t.op("STA", "abs", V_F7)
    t.op("JSR", "abs", tick)
    t.op("RTS")
    out = t.bytes()
    assert len(out) == TRAMP_LEN
    return out


def assemble(pages, where):
    """→ (모듈 코드+표 bytes, 라벨, 사건 수). 두 패스(라벨 주소를 앞 패스에서 얻는다)."""
    L: dict[str, int] = {}
    ev = events(pages)
    for _ in range(3):
        a = tick_code(L)
        base = CODE_ADDR
        # 표: 페이지 표(2B 포인터) 두 배열(lo 배열 · hi 배열은 한 배열의 홀짝이라 필요 없다 — 아래 findpage 가 absx 로 읽는다)
        recs = []
        for p, (bank, win) in zip(pages, where):
            if "bg" in p:
                bg = p["bg"]
                rec = bytearray([bank, win & 0xFF, win >> 8, 0, bg["ntiles"], bg["dest"] & 0xFF, bg["dest"] >> 8, len(bg["rows"])])
                for ra in bg["rows"]:
                    rec += ra.to_bytes(2, "little")
                recs.append(bytes(rec))
                continue
            y0 = p["y0"] + 64
            rec = bytearray([bank, win & 0xFF, win >> 8, len(p["cells"]), y0 & 0xFF, y0 >> 8])
            for x, yoff, _cb in p["cells"][::2]:
                assert 0 <= x + 32 <= 255, (p["lines"], x)
                rec += bytes([x + 32, yoff])
            recs.append(bytes(rec))
        # 라벨 확정 전 주소 계산: 코드 길이는 라벨 값과 무관하다
        code_len = len(a.out)
        rinit_len = len(rinit_code(L, DATA_BANK, DATA_REL, 0).bytes())
        tramp_img = base + code_len
        rinit_img = tramp_img + TRAMP_LEN
        pagetab = rinit_img + rinit_len
        pagetab1 = pagetab + 1
        recs_at = pagetab + 2 * len(pages)
        addrs = []
        off = recs_at
        for r_ in recs:
            addrs.append(off)
            off += len(r_)
        events_tab = off
        L.update(
            rinit_img=rinit_img, rinit_len=rinit_len, tramp_img=tramp_img,
            pagetab=pagetab, pagetab1=pagetab1, events_tab=events_tab, u_tia=a.labels.get("u_tia", 0), b_tia=a.labels.get("b_tia", 0), b_rtia=a.labels.get("b_rtia", 0),
        )  # fmt: skip
        L.update({k: v for k, v in a.labels.items()})
    return a, L, recs, addrs, ev


def build_module(pages, where, nsec):
    a, L, recs, addrs, ev = assemble(pages, where)
    # 마지막 패스 — 라벨 값이 확정된 상태로 다시
    a = tick_code(L)
    # 라벨 참조(pagetab/pagetab1) 해결용 — Asm.bytes 가 자기 라벨만 안다. 외부 라벨은 직접 박는다
    a.labels["pagetab"] = L["pagetab"]
    a.labels["pagetab1"] = L["pagetab1"]
    code = bytearray(a.bytes())
    rinit = rinit_code(L, DATA_BANK, DATA_REL, nsec).bytes()
    assert len(rinit) <= RAM_INIT_MAX, len(rinit)
    tramp = tramp_code(a.labels["tick"])
    tab = bytearray()
    for ad in addrs:
        tab += ad.to_bytes(2, "little")
    # findpage 는 absx 로 pagetab(+0) 과 pagetab1(+1) 을 읽는다 — X = 2*page 라 홀짝 배열과 같다
    out = bytes(code) + tramp + rinit + bytes(tab) + b"".join(recs)
    evb = bytearray()
    for t, op, pa, pb in ev:
        assert 0 <= t < 65536, t
        evb += bytes([t & 0xFF, t >> 8, op, pa, pb])
    out += bytes(evb)
    assert len(out) <= CODE_MAX, len(out)
    return out, L


def writes(pages=None):
    """빌드가 쓸 (선형 바이트, 새 바이트, 기대 원본, 라벨) 목록과 요약."""
    pages = pages or build_pages()
    blob, where = pack_data(pages)
    nsec = len(blob) // 2048
    module, L = build_module(pages, where, nsec)
    lin = lambda bank, off: MODULE_REL * 2048 + (bank - MODULE_BANK0) * BANK + off
    out = [
        (lin(CODE_BANK, CODE_OFF), module, b"\xff" * len(module), "opening_sub 코드·표"),
        (lin(CDPLAY_BANK, CDPLAY_OFF), bytes([0x20, L["stub"] & 0xFF, L["stub"] >> 8]), bytes([0x20, 0x12, 0xE0]), "opening_sub CD_PLAY 훅"),
        (DATA_REL * 2048, blob, bytes(len(blob)), "opening_sub 셀 데이터"),
    ]  # fmt: skip
    return out, {"pages": len(pages), "cells": sum(len(p["cells"]) for p in pages), "module": len(module), "sectors": nsec, "stub": L["stub"], "tick": L["tick"]}


def apply(w):
    """`Writer` 에 모듈 패치와 데이터를 쓴다."""
    if os.environ.get("ED_SUB_OFF"):  # 시험용 — 자막 없는 기준선(원판과 화면 비교용)
        print("  오프닝 자막: ED_SUB_OFF — 건너뜀")
        return None
    spans, info = writes()
    for linear, new, expect, label in spans:
        w.put(linear, new, expect, label)
    print(f"  오프닝 자막: 페이지 {info['pages']} · 셀 {info['cells']} · 코드·표 {info['module']}B · 데이터 {info['sectors']}섹터 (rel {DATA_REL}~)")
    return info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    a = ap.parse_args()
    pages = build_pages()
    spans, info = writes(pages)
    print(info)
    for i, p in enumerate(pages):
        print(f"{i:2d} {p['t0']:6.1f}-{p['t1']:6.1f}s  셀 {len(p['cells']):2d}  {' / '.join(p['lines'])}")
    ev = events(pages)
    print("사건", len(ev), ev[:6])
    if a.preview:
        import numpy as np
        from PIL import Image

        out = common.REVIEW_DIR / "opening"
        out.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(pages):
            img = np.zeros((H, W, 3), dtype=np.uint8)
            for x, yoff, cb in p["cells"]:
                for plane, col in ((1, (0, 0, 0)), (0, (255, 255, 255))):
                    for r in range(GLYPH_ROWS):
                        wv = int.from_bytes(cb[plane * 32 + r * 2 : plane * 32 + r * 2 + 2], "little")
                        for bit in range(16):
                            if wv & (0x8000 >> bit):
                                yy, xx = p["y0"] + yoff + r, x + bit
                                if 0 <= yy < H and 0 <= xx < W:
                                    img[yy, xx] = col if plane == 0 else (90, 90, 140)
            Image.fromarray(img).save(out / f"p{i:02d}.png")
        print("미리보기 →", out)


if __name__ == "__main__":
    main()
