"""대관식(패키지 38) 성우 대사 자막 — CD-DA 트랙 23(약 301초)에 맞춰 스프라이트 자막을 띄운다 (2026-10-14).

    python3 games/pce-ed2/tools/ending_sub.py            # 조립 결과·크기·타임라인 확인

오프닝 자막(`opening_sub.py`)과 **같은 방식**(빌드 때 줄을 스프라이트 셀로 미리 굽고, 실행 중엔 VRAM 으로 옮기기만 한다)이지만 사정이 달라 따로 쓴다:

  · 패키지 38(rel 4866, 123섹터 = 뱅크 0x68~0x86)은 **통째로 차 있다** — 빈 곳이 뱅크 0x6A 의 0xFF 374B(+0x1C8A)와 뱅크 0x86 끝의 0 1575B(+0x11D9)뿐이다.
    그래서 ① 셀 데이터는 **ADPCM RAM**(64KB — 이 장면에선 안 쓴다)에 둔다: 디스크 빈 섹터 → BIOS `AD_TRANS`(`$E033`, `$F8`=섹터 수 · `$FA/FB`=ADPCM 주소 ·
    `$FC~FE`=섹터 · `$FF`=0)로 CD_PLAY **전에** 올려 두고, 읽기는 `$1808/09` 주소 → `$180D` 래치 → `$180A`(바쁨 `$180C` 비트 7). 에뮬 실측(10-14).
    ② 코드는 뱅크 0x86 끝(+0x11E0~)에 두고 로더 섹터 수를 123→124 로 올려(rel 2 표 `[38]`) 끝까지 쓴다. IRQ 트램펄린(RAM)이 MPR3 에 0x86 을 걸어 부른다.
    ③ 스텁·RAM 초기화 이미지는 뱅크 0x6A 의 374B 안에 둔다(CD_PLAY 호출 `$5589` 시점 MPR4=0x6A).
  · 훅은 하나 — 패키지 +0x1589 의 `JSR $E012`(CD_PLAY, 트랙 0x23)를 스텁으로. 시각 원점은 오프닝과 같다(CD_PLAY 복귀 = 프레임 0, IRQ 가 매 VBlank 올리는 `$2F` 와 별개로 우리 카운터).
  · VRAM 은 장면 그림이 거의 다 써서 비는 곳(바이트 38912~43008 = 워드 `$4C00`·32 셀, 61440~ = 워드 `$7800`·28 셀)에 버퍼 둘을 둔다 — 장면마다 확인이 필요하다.
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
import band
import opening_sub as o

SUBS = common.GAME_DIR / "data" / "ending_sub.json"
VRAM_JSON = common.GAME_DIR / "data" / "ending_vram.json"

FPS = o.FPS
AUDIO_LAG = o.AUDIO_LAG  # CD_PLAY 복귀 → 음성 t=0(프레임) — 오프닝과 같은 엔진·같은 값
END_HOLD = 30  # 음성 끝 뒤 자막을 더 두는 프레임(0.5초 — 번역 규칙 2-15, 마스터 10-15). 클로즈업·장면 전환과 같이 닫기로 한 쪽은 그 시각에서 0.5초를 뺀 값을 t1 로 둔다
UPLOAD_LEAD = 10  # 보이기 몇 프레임 전에 올리기 시작(버퍼가 하나라 그 사이엔 자막이 잠깐 빈다)
PKG_REL = 4866  # 패키지 38
BANK = 8192
BANK0 = 0x68
HOOK_OFF = 0x1589  # `20 12 E0`(CD_PLAY) — 논리 $5589
STUB_BANK, STUB_OFF, STUB_MAX = 0x6A, 0x1C8A, 374  # 뱅크 0x6A 의 0xFF 런(창 $8000 기준 $9C8A)
CODE_BANK, CODE_OFF = 0x86, 0x11E0  # 뱅크 0x86 끝의 0 런(로더 섹터 수를 124 로 올려 +0x2000 까지)
CODE_ADDR = 0x6000 + CODE_OFF  # MPR3 창
CODE_MAX = 0x2000 - CODE_OFF
COUNT_TABLE_LINEAR = 2 * 2048 + 38  # rel 2 오프셋 38 = 패키지 38 섹터 수(0x7B → 0x7C)
COUNT_OLD, COUNT_NEW = 0x7B, 0x7C
# 🔴 로더가 더 읽는 124째 섹터(rel 4989)는 **비어 있지 않다** — 첫 177B 가 원래 자료다. 거기를 코드로 덮었더니 다음 장면(레이시아·아트라스 악수 그림)이 통째 쓰레기로 깨졌다(마스터 10-14, 기준 롬은 멀쩡) —
# 그 자료를 지키고 이어지는 자리(+0x18B1~)에 표를 둔다(코드는 앞 빈 런에, 이벤트 표는 구멍 뒤에 통째로).
HOLE_LO = 0x6000 + 0x1800  # MPR3 창 안 구멍 시작(= 뱅크 0x86 +0x1800 = 124째 섹터 머리)
DATA_REL = (
    4170  # 디스크의 통째 0 섹터(rel 4151~4228 · 거울 +36864 도 0) — 오프닝이 4151~4166 을 쓴다
)
DATA_MAX_SEC = 22  # ADPCM 0x5000~ (44KB)
ADPCM_BASE = 0x5000  # 🔴 셀 데이터를 올리는 ADPCM 주소 — 0 이 아니다: 게임이 ADPCM RAM 앞 ~19.5KB(0x4D50 까지)에 다음 장면(악수 그림) 자료를 미리 올려 두는데, 0 부터 덮었더니 그 장면이 통째 쓰레기로 깨졌다(마스터 10-14, 기준 롬 ADPCM RAM 덤프로 확인)
ADPCM_MAX = 65536 - ADPCM_BASE

IRQ_OFF = 0x00D2  # `E6 2F 07 38`(INC $2F · RMB0 $38) — 논리 $40D2
TRAMP_IRQ = 0x22C0
V_FR, V_ON, V_UPG, V_UPB, V_UPC, V_UPN, V_SAVE, V_TMP = (
    0x22E0,
    0x22E2,
    0x22E3,
    0x22E4,
    0x22E5,
    0x22E6,
    0x22E8,
    0x22E9,
)
V_CODE, V_YL = 0x22EA, 0x22EC
V_KB = 0x22E7
V_CLN = 0x22E4  # 마지막으로 올린 쪽의 셀 수(숨기기에서 블록을 0 으로 지운 뒤 0)  # 보이기 루프: 레코드 안 이 스프라이트의 시작 위치
V_NT = 0x22EE
V_F7 = 0x22EB  # IRQ 가 들어올 때 끊긴 쪽의 VDC 레지스터 선택값(`$F7` 그림자 — 스택에 저장돼 있다). 0~2 면 끊긴 쪽이 MAWR/VWR 쓰기 한복판이다
V_CRK, V_CRN = 0x22E8, 0x22EF  # 블록 지우기 진행(옛 V_SAVE · V_N 자리 — 안 쓰인다): 다음 블록의 레코드 안 위치 · 남은 블록 수. 0 이 아니면 지우는 중이라 올리기·사건이 쉰다
CLEAR_PER_TICK = 2  # 틱마다 지우는 블록 수 — 블록 하나가 TIA 256B(≈1600 사이클 ≈ 3.5줄)라 한 번에 열 개를 지우면 래스터 IRQ(띠 그림 켜기 줄 55)가 아홉 줄 늦어 그림 위쪽이 한 프레임 잘렸다(마스터 10-15 「자막 끝나고 순간 그림 잘림」, 에뮬 1프레임 실측)
RAM_INIT, RAM_INIT_MAX = 0x2300, 0xC0
Z_EV, Z_DP, Z_PG, Z_T0, Z_T1, Z_A, Z_B, Z_X = 0xC0, 0xC2, 0xC4, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA
Z_SHP, Z_SHH = 0xCE, 0xCF  # 지금 보이는 쪽 번호+1(0 = 없음) · 그 쪽을 띄울 때의 표시 높이 — 장면이 세피아↔전체 화면으로 바뀌면 y 를 다시 계산해 다시 보인다(안 그러면 128줄 창 밖에 남아 사라진다, 마스터 10-14 #1)
Z_DEF = 0xCB  # 연속으로 미룬 틱 수
DEFER_MAX = 90
Z_UP = 0xCC  # 올리는 중인 쪽 레코드 포인터(2B) — 보이기가 Z_PG 를 바꿔도 올리기는 제 쪽을 읽는다  # ZP $20C0~
PAL_SHADOW = 0x2BBB
PAL8_C1 = PAL_SHADOW + 512 + 8 * 32 + 2
SAT_WORD = 0x7F00
SAT_X_UNUSED = 0x7E00  # 합성 SAT(256 워드) — 우리 스프라이트가 앞 슬롯, 게임의 SAT 를 뒤에 붙인다. 게임의 얼굴·옷 스프라이트(슬롯 0~31)가 우리 것(36~)보다 앞이라 글자를 가려서(에뮬 실측 10-14), 우리 것을 맨 앞으로 보낸다
SLOT0, SLOTS = (
    4,
    12,
)  # SAT 슬롯 4~19 — 게임의 스프라이트 쓰기 루틴(`$4AF0`)이 시작 슬롯을 `$30DC` 로 받으므로 거기를 20 으로 올려 비워 둔다. 슬롯 0~3 은 0 으로 둔다: 일부 장면(위로 훑는 그림)의 BAT 가 SAT 첫 타일(VRAM 0x7F00)을 그림 타일로 참조해, 거기에 우리 스프라이트 값이 있으면 화면 아래에 쓰레기 줄무늬가 보인다(에뮬 실측 10-14)
BUFS = (
    0x3000,
    0x3000,
)  # VRAM 워드 — 타일 0x300~0x3FF(바이트 0x6000~0x7FFF). 장면 그림은 왼쪽 그림 0x100~0x1E0 · 다음 장면 미리 올린 오른쪽 반 0x700~0x7E8 · 위로 훑는 장면 0x54B~ 를 쓴다(BAT 실측 10-14). 0x4C00(0x4C0)·0x7800(0x780)은 장면에 따라 그림과 겹쳐 깨졌다
BUF_CELLS = (32, 32)
SPR_ATTR = 0x0188
FLAG_ZP = 0x38
CELLS_PER_TICK = 2  # 틱마다 올리는 셀 수 — 6 이면 AD_READ(384B)+TIA 가 한 틱에 ≈ 28줄이라 래스터 IRQ(띠 그림 켜기 줄 55)가 늦어 그림 위가 한 프레임 잘렸다(마스터 10-15, 에뮬 1프레임 실측)
Y0_TOP = 16  # 위쪽 배치(군중 장면 — 아래는 사람·위는 하늘이라 게임 스프라이트가 위에 적다, 마스터 10-15): 위 여백 16px. 대본 `"top": [쪽 번호]`
Y0 = 187  # 마지막 줄 잉크 아래끝 ~ 화면 아래끝 16px(마스터 10-15)
BOTTOM_SINGLE = True  # 번역 규칙 2-14 — 그림 위에 얹힌 한 줄 자막은 두 줄 쪽의 둘째 줄 높이(바닥). 대관식은 전부 그림 위(마스터 10-15)
V_HEIGHT = 0x26E6  # 게임의 장면 높이 변수 — 0x80 이면 세피아 레터박스 장면(`band.py` 가 표시창을 232 줄로 넓혀 띠에도 자막이 뜬다), 아니면 전체 화면. 바뀌면 자막을 다시 보인다(Z_SHH)

W = 256
LINE_CAP = 206
BAND_CAP = 244  # 검은 띠 안 줄의 폭 상한 — 띠에는 게임 스프라이트가 없어 한 줄 16칸까지 쓴다(마스터 10-16 「까만 부분만 한 줄로」). 오프닝 상한과 같다
TOP_CAP = 244  # 위쪽 배치 쪽의 줄 폭 상한 — 위 줄(y16~31)은 게임 칸이 0 이라 16칸까지 쓴다(마스터 10-15 「길게」). 240 → 244: 마지막 장면 「당신이라면 분명 좋은 지도자가 될 거야.」(242)를 한 줄로(마스터 10-16, 시험 롬 실화면: 잉크 x12~245). 오프닝 상한과 같은 값


def line_cells(text, pad=0):
    """한 줄 → (왼쪽 시작 x, [64B 셀 | None], 폭) — 화면(256) 가운데. `pad` = 격자를 글자보다 왼쪽으로 내미는 px(셀 안에서 글자를 오른쪽으로 민다)."""
    m, edge = o.render_line(text)
    wpx = m.shape[1]
    x0 = (W - wpx) // 2
    cells = []
    for c in range((wpx + pad + o.CELL_PX - 1) // o.CELL_PX):
        out = bytearray()
        for plane in (m, edge):
            for r in range(16):
                w = 0
                if r < o.GLYPH_ROWS:
                    for bit in range(16):
                        x = c * o.CELL_PX + bit - pad
                        if 0 <= x < wpx and plane[r, x]:
                            w |= 0x8000 >> bit
                out += w.to_bytes(2, "little")
        cells.append(bytes(out) if any(out) else None)
    return x0, cells, wpx


def build_pages(script=None, with_alloc=True):
    data = script or json.loads(SUBS.read_text(encoding="utf-8"))
    pages = []
    for sub in data["subs"]:
        pgs = o.split_pages(sub["text"])
        cuts = sub.get("cuts")
        assert cuts is None or len(cuts) == len(pgs) - 1, (sub["text"], cuts)
        starts = [sub["t0"]] + list(cuts or []) + [sub["t1"]]
        weights = [sum(len(l) for l in p) for p in pgs]
        tot = sum(weights)
        t = sub["t0"]
        for k, (p, wt) in enumerate(zip(pgs, weights, strict=False)):
            if cuts:
                t, dur = starts[k], starts[k + 1] - starts[k]
            else:
                dur = (sub["t1"] - sub["t0"]) * wt / tot
            cells = []
            for row, line in enumerate(p):
                cap = TOP_CAP if k in sub.get("top", ()) else BAND_CAP if band.in_band(t + dur / 2) else LINE_CAP + 8
                assert o.text_w(line) + 2 <= cap, line
                x0 = (W - o.center_w(line)) // 2  # 줄마다 가운데(줄 끝 「.」「,」「…」 폭 제외 — 번역 규칙 2-8, 마스터 10-15)
                pad = 0
                _x0c, cs, _w = line_cells(line)
                while x0 - pad + o.CELL_PX * 2 * ((len(cs) + 1) // 2 - 1) > 223 and pad < 31:  # 스프라이트 x 는 1바이트(x+32 ≤ 255) — 마지막 32 폭 스프라이트가 x≤223 에 들게 격자를 왼쪽으로 민다(오프닝 `pad` 와 같은 꼴)
                    pad += 1
                    _x0c, cs, _w = line_cells(line, pad)
                x0 -= pad
                for kk in range(0, len(cs), 2):  # 32×16 스프라이트 = 이웃한 셀 둘
                    a, b = cs[kk], cs[kk + 1] if kk + 1 < len(cs) else None
                    if a is None and b is None:
                        continue
                    cells.append((x0 + o.CELL_PX * kk, row * o.LINE_H, a or bytes(64)))
                    cells.append((x0 + o.CELL_PX * (kk + 1), row * o.LINE_H, b or bytes(64)))
            assert len(cells) <= max(BUF_CELLS), (p, len(cells))
            assert (len(cells) + 1) // 2 <= SLOTS, (p, len(cells))  # 우리 스프라이트 슬롯 4~15 — 더 넣으면 게임 스프라이트(신디 장면 48 개)가 잘린다
            pages.append(
                {
                    "blocks": None,
                    "t0": t,
                    "t1": t + dur,
                    "lines": list(p),
                    "cells": cells,
                    "blob": b"".join(c[2] for c in cells),
                    "group": None,
                    "y0": sub.get("y0", {}).get(str(k), Y0_TOP) if k in sub.get("top", ()) else Y0 + (o.LINE_H if BOTTOM_SINGLE and len(p) == 1 and not band.in_band(t + dur / 2) else 0) - o.LINE_H * max(0, len(p) - 2),  # 세 줄 쪽은 윗단을 한 줄 올려 마지막 줄(바닥)을 둘째 줄 자리에 둔다 — 줄당 스프라이트 16칸 한도 때문에 줄을 나눈 쪽(10-15)  # 번역 규칙 2-14 — 그림 위 한 줄은 둘째 줄 높이(바닥), **그림 아래 검은 띠 안 한 줄은 첫째 줄 높이**(마스터 미리보기 C, 10-15 — 띠 바닥에 붙이면 그림과 떨어져 어색)
                    "noreshow": k in sub.get("noreshow", ()),
                }
            )
            t += dur
    if not with_alloc:  # vram_alloc.py 가 배정을 새로 만들 때 — 옛 배정 json 과 쪽 수가 안 맞아도 된다
        return pages
    alloc = json.loads(VRAM_JSON.read_text(encoding="utf-8"))[
        "pages"
    ]  # `vram_alloc.py` 가 에뮬 스냅샷에서 만든 쪽별 VRAM 블록
    assert len(alloc) == len(pages), (
        f"VRAM 배정 {len(alloc)}쪽 ≠ 쪽 {len(pages)} — vram_alloc.py 를 다시 돌린다"
    )
    for p, bl in zip(pages, alloc, strict=False):
        assert len(bl) >= (len(p["cells"]) + 1) // 2 and all((b & ~1) % 128 == 0 for b in bl), (
            p["lines"],
            bl,
        )
        p["blocks"] = bl
    for c in data.get("cleanup", []):  # 청소 쪽(안 보이는 쪽) — 이 시각에 지정 블록을 0 으로 되돌린다. 그림 패턴이 미리 올라가는 칸(용 날개 · 마스터 10-15 「양날개에 신디 자막」)에 앞 쪽들이 남긴 글자 잔재가 장면 첫 프레임에 비쳐 보이지 않게 한다
        blks = [b & ~1 for b in c["blocks"]]  # 하위 비트 0 = 지우는 블록
        assert 0 < len(blks) <= max(BUF_CELLS) // 2, c  # 보이지 않으니 슬롯 한도(SLOTS)와 무관 — 올리기 버퍼만 맞으면 된다
        cells = []
        for b in blks:
            cells += [(0, 0, bytes(64)), (o.CELL_PX, 0, bytes(64))]
        pages.append(
            {
                "blocks": blks, "t0": c["t"], "t1": c["t"] + 0.05, "lines": ["(청소)"], "cells": cells,
                "blob": bytes(64 * len(cells)), "group": None, "y0": 240, "noreshow": False,
            }
        )  # fmt: skip
    pages.sort(key=lambda p: p["t0"])
    return pages


# 장면 전환 시각(초) — 에뮬 실측(10-16): 게임이 `$20F3` 에 BG 끄기(8)를 쓰는 순간, 프레임 ÷ 59.826. 73.10·173.24 는 한 프레임 깜빡임이다.
TRANSITIONS = (23.85, 38.61, 60.54, 73.10, 84.43, 101.93, 112.43, 117.56, 124.76, 156.30, 173.24, 194.51, 207.84, 227.23,
               230.90, 237.76, 241.67, 243.44, 245.01, 246.78, 254.89, 260.96, 263.53, 266.71, 297.55)  # fmt: skip
CUT_GUARD = 0.06  # 전환 이만큼(초) 앞에서 닫는다


def end_time(t1):
    """쪽을 닫는 시각(초) — 음성 끝 + 0.5초 대기(2-15). 음성이 전환 앞에서 끝나면 그 대기가 전환을 넘지 않게 전환 직전에서 자른다(마스터 10-16 「0.5초 때문에 다음 장면에 남은 것」)."""
    end = t1 + END_HOLD / FPS
    for t in TRANSITIONS:
        if t1 < t <= end + CUT_GUARD:
            return t - CUT_GUARD
    return end


def f(t):
    return round(t * FPS) + AUDIO_LAG


def buf_of(pages):
    """쪽마다 버퍼(0 = 32 셀 · 1 = 28 셀) — 이웃은 다른 버퍼, 28 셀을 넘는 쪽은 0 번(짝수 쪽)에 온다."""
    big = {i % 2 for i, p in enumerate(pages) if len(p["cells"]) > BUF_CELLS[1]}
    assert len(big) <= 1, "큰 쪽이 두 패리티에 걸린다 — 쪽을 나눠라"
    off = big.pop() if big else 0
    return [(i + off) % 2 for i in range(len(pages))]


CELL_REC = 64
BUF_RAM = 0x2480  # AD_READ 가 채우는 RAM(최대 6셀 = 384B, $2480~$25FF) — rinit 코드 자리($2300~$23AA) 뒤 빈 곳(에뮬 실측: 0)


def pack_data(pages):
    """쪽 셀 바이트를 이어 붙인다 → (블롭, 쪽별 첫 셀 ADPCM 주소)."""
    blob = bytearray()
    where = []
    for p in pages:
        where.append(ADPCM_BASE + len(blob))
        blob += p["blob"]
    assert len(blob) <= ADPCM_MAX, len(blob)
    sectors = (len(blob) + 2047) // 2048
    assert sectors <= DATA_MAX_SEC, sectors
    blob += bytes(sectors * 2048 - len(blob))
    return bytes(blob), where


def events(pages):
    """[(프레임, op, a, b)] — op 3 = 지우기 · 4 = 지우기+올리기(page) · 1 = 올리기(page, buf) · 2 = 보이기(page, buf) · 0xFF = 끝. 버퍼가 하나라 올리기 직전에 늘 지운다."""
    if os.environ.get(
        "ED_SUB_PROBE"
    ):  # 시험용 — 카운터(V_FR)만 돌고 자막은 안 올린다(vram_alloc 용 깨끗한 스냅샷)
        return [(f(pages[-1]["t1"]) + 120, 0xFF, 0, 0)]
    ev = []
    for i, p in enumerate(pages):
        up = f(p["t0"]) - UPLOAD_LEAD
        ev.append((up, 4, i, 0))  # 지우기 + 올리기(한 사건 — 표가 쪽당 5B 줄어든다)
        if p["lines"] != ["(청소)"]:  # 청소 쪽은 올리기(0 쓰기)만 — 보이면 안 되고, 지우기는 다음 쪽의 올리기 사건이 한다
            ev.append((f(p["t0"]), 2, i, 0))
        nxt = f(pages[i + 1]["t0"]) if i + 1 < len(pages) else None
        end = f(end_time(p["t1"]))
        if nxt is None or end < nxt - UPLOAD_LEAD - 2:
            ev.append((end, 3, 0, 0))
    ev.append((f(pages[-1]["t1"]) + 120, 0xFF, 0, 0))
    ev.sort(key=lambda e: (e[0], 0 if e[1] in (3, 4) else e[1]))
    return ev


for _k, _v in {("TSB", "abs"): 0x0C, ("DEC", "imp"): 0x3A, ("TRB", "abs"): 0x1C}.items():
    asm.OPS.setdefault(_k, _v)


class A(o.A):
    pass


def _vdc_addr(a, hi, lo):
    a.op("ST0", "imm", 0)
    a.op("ST1", "imm", lo)
    a.op("ST2", "imm", hi)
    a.op("ST0", "imm", 2)


def tick_code(L):
    a = A(CODE_ADDR)
    g = lambda k: L.get(k, 0)
    # ── 틱(IRQ 트램펄린이 MPR3=0x86 을 건 채 부른다) ───────────────────────────
    a.label("tick")
    a.op("INC", "abs", V_FR)
    a.op("BNE", "rel", "t_f")
    a.op("INC", "abs", V_FR + 1)
    a.label("t_f")
    a.op(
        "LDA", "imm", SLOT0 + SLOTS
    )  # 게임 스프라이트 시작 슬롯 — 앞 16 슬롯은 우리 몫(0~3 은 비움, 4~15 는 글자 — 게임 스프라이트가 우리 글자를 가리지 않게).
    # 🔴 16 이다(옛 20): 신디 장면은 게임 스프라이트가 48 개라 20 이면 44 개만 써서 날개·머리가 사라졌다(마스터 10-14 「신디 얼굴 깨짐」, 기준 롬 SAT 48 항목 실측).
    # 가변(쪽마다 4+수)은 안 된다 — 게임이 틈틈이 슬롯 0 부터 다시 써서 우리 항목이 덮인다(에뮬 실측: 쪽 14~ 자막이 통째로 사라졌다)
    a.op("STA", "abs", 0x30DC)
    a.op("LDA", "imm", 0xFF)  # 팔레트 그림자: 스프라이트 팔레트 8 색 1 흰(0x1FF) · 색 2 검정
    a.op("STA", "abs", PAL8_C1)
    a.op("LDA", "imm", 0x01)
    a.op("STA", "abs", PAL8_C1 + 1)
    a.op("STZ", "abs", PAL8_C1 + 2)
    a.op("STZ", "abs", PAL8_C1 + 3)
    a.op("LDA", "imm", 0x81)  # VCE 에 직접도 쓴다: 스프라이트 팔레트 8 색 1(=0x181) 흰 · 색 2 검정 — 페이드(프레이아 장면)에서 게임이 그림자를 어둡게 써 BIOS 가 올린 프레임에 글자가 한 프레임 어두워졌다(마스터 10-15 「자막이 살짝 깜빡」, 에뮬 1프레임 실측)
    a.op("STA", "abs", 0x0402)
    a.op("LDA", "imm", 0x01)
    a.op("STA", "abs", 0x0403)
    a.tia("pal8", 0x0404, 4)  # 목적지가 0404·0405 를 번갈아 받는다 → 색 1 = 0x01FF · 색 2 = 0
    a.op(
        "SMB2", "zp", FLAG_ZP
    )  # 팔레트를 매 틱 다시 올린다 — 장면이 팔레트를 새로 올리면 우리 색이 지워진다(에뮬 실측: 세피아 장면에서 자막이 안 보였다)
    # 끊긴 쪽이 VDC 쓰기 한복판(MAWR/VWR 선택 중)이면 이번 틱의 VRAM 일은 미룬다 — 우리가 MAWR 를 옮기면 그쪽 데이터가 엉뚱한 곳에 쓰이고 게임 그림 줄이 하나 빠진다(에뮬 실측 10-14: 장면 BAT 한 줄 유실).
    # 연속 DEFER_MAX 틱을 미루면 그냥 한다(끊긴 쪽이 늘 2 를 남겨 두는 구간에서 굶지 않게). 옛 「32틱에 한 번 강행」은 그림 읽기 한복판에 걸려 그림이 띠로 잘렸다(마스터 10-15 레이시아 클로즈업)
    a.op("LDA", "abs", V_F7)
    a.op("CMP", "imm", 3)
    a.op("BCS", "rel", "t_go0")
    a.op("INC", "zp", Z_DEF)  # 연속으로 미룬 틱 수 — 게임이 그림을 읽는 구간은 몇 프레임이라 90(1.5초) 연속이면 「늘 2」 구간이라 그냥 한다
    a.op("LDA", "zp", Z_DEF)
    a.op("CMP", "imm", DEFER_MAX)
    a.op("BCS", "rel", "t_go")
    a.op("RTS")
    a.label("t_go0")
    a.label("t_go")
    a.op("STZ", "zp", Z_DEF)
    a.op("LDA", "zp", Z_SHP)  # 보이는 쪽이 있고 화면이 꺼졌으면(장면 전환 — 게임이 CR 의 BG 를 끈다) 「전환 뒤 안 띄움」 쪽은 그 순간 닫는다(전환 뒤 그림이 우리 블록을 덮어 조각 잔상이 남는다 — 마스터 10-15 「화면전환할때 자막 잔상」)
    a.op("BEQ", "rel", "t_hc")
    a.op("LDA", "zp", 0xF3)  # BIOS 의 CR 그림자(`$20F3`) — 0x80 = BG 켜짐
    a.op("BMI", "rel", "t_hc")
    a.op("LDA", "zp", Z_SHP)
    a.op("DEC", "imp")
    a.op("STA", "zp", Z_A)
    a.op("JSR", "abs", "findpage")
    a.op("LDY", "imm", 0)
    a.op("LDA", "izpy", Z_PG)
    a.op("BEQ", "rel", "t_hc")
    a.op("JSR", "abs", "hide")
    a.label("t_hc")
    a.op("LDA", "zp", Z_SHP)  # 보이는 쪽이 있고 표시 높이가 그 사이 바뀌었으면(세피아 ↔ 전체) 같은 쪽을 새 높이로 다시 보인다
    a.op("BEQ", "rel", "t_up")
    a.op("LDA", "abs", V_HEIGHT)
    a.op("CMP", "zp", Z_SHH)
    a.op("BEQ", "rel", "t_up")
    a.op("LDA", "zp", Z_SHP)
    a.op("DEC", "imp")
    a.op("STA", "zp", Z_A)
    a.op("JSR", "abs", "findpage")
    a.op("LDY", "imm", 0)
    a.op("LDA", "izpy", Z_PG)  # 레코드 [0] 1 = 장면 전환 뒤엔 다시 띄우지 않고 닫는다(마스터 10-15 「장면전환후엔 이 자막 안띄워도 될듯」)
    a.op("BEQ", "rel", "t_rs")
    a.op("JSR", "abs", "hide")
    a.op("BRA", "rel", "t_up")
    a.label("t_rs")
    a.op("JSR", "abs", "show")
    a.label("t_up")
    a.op("JSR", "abs", "cstep")
    a.op("LDA", "abs", V_CRN)
    a.op("BEQ", "rel", "t_uq")
    a.op("RTS")  # 지우는 중 — 올리기·사건은 다 지운 뒤(같은 블록을 새 쪽이 올리는데 지우기가 뒤늦게 덮으면 안 된다)
    a.label("t_uq")
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
    # ── 올리기: 틱마다 셀 CELLS_PER_TICK 개 — BIOS AD_READ **한 번**으로 ADPCM → RAM 버퍼, 이어서 셀마다 VDC 로 ──
    # (에뮬 실측 10-14: 한 프레임에 AD_READ 를 두 번 부르면 둘째가 비어 온다. 직접 포트 읽기는 읽기 위치가 어긋난다. 한 틱 한 번만 부른다.)
    a.label("upload")
    a.op("SEC")
    a.op("LDA", "abs", V_UPN)
    a.op("SBC", "abs", V_UPC)
    a.op("CMP", "imm", CELLS_PER_TICK)
    a.op("BCC", "rel", "u_nok")
    a.op("LDA", "imm", CELLS_PER_TICK)
    a.label("u_nok")
    a.op("STA", "abs", V_NT)
    a.op("BNE", "rel", "u_go")
    a.op("LDA", "imm", 0xFF)
    a.op("STA", "abs", V_UPG)
    a.op("RTS")
    a.label("u_go")
    a.op("LDX", "imm", 0)
    a.label("u_sv")
    a.op("LDA", "zpx", 0xF8)
    a.op("PHA")
    a.op("INX")
    a.op("CPX", "imm", 8)
    a.op("BNE", "rel", "u_sv")
    a.op("LDA", "abs", V_NT)  # 바이트 수 = n × 64 (16비트)
    a.op("LSR", "imp")
    a.op("LSR", "imp")
    a.op("STA", "zp", 0xF9)
    a.op("LDA", "abs", V_NT)
    for _ in range(6):
        a.op("ASL", "imp")
    a.op("STA", "zp", 0xF8)
    a.op("LDA", "imm", BUF_RAM & 0xFF)
    a.op("STA", "zp", 0xFA)
    a.op("LDA", "imm", BUF_RAM >> 8)
    a.op("STA", "zp", 0xFB)
    a.op("LDA", "zp", Z_DP)
    a.op("STA", "zp", 0xFC)
    a.op("LDA", "zp", Z_DP + 1)
    a.op("STA", "zp", 0xFD)
    a.op("STZ", "zp", 0xFF)
    a.op("JSR", "abs", 0xE036)
    a.op("LDX", "imm", 8)
    a.label("u_rs")
    a.op("DEX")
    a.op("PLA")
    a.op("STA", "zpx", 0xF8)
    a.op("CPX", "imm", 0)
    a.op("BNE", "rel", "u_rs")
    # Z_DP += n × 64
    a.op("LDA", "abs", V_NT)
    a.op("LSR", "imp")
    a.op("LSR", "imp")
    a.op("STA", "abs", V_TMP)
    a.op("LDA", "abs", V_NT)
    for _ in range(6):
        a.op("ASL", "imp")
    a.op("CLC")
    a.op("ADC", "zp", Z_DP)
    a.op("STA", "zp", Z_DP)
    a.op("LDA", "zp", Z_DP + 1)
    a.op("ADC", "abs", V_TMP)
    a.op("STA", "zp", Z_DP + 1)
    # TIA 원본 주소를 버퍼 처음으로(자가수정)
    a.op("LDA", "imm", BUF_RAM & 0xFF)
    a.op("STA", "abs", g("u_tia") + 1)
    a.op("LDA", "imm", BUF_RAM >> 8)
    a.op("STA", "abs", g("u_tia") + 2)
    a.label("u_cell")
    # 목적지 워드 = 이 셀이 속한 스프라이트의 블록 주소(레코드 6+4s+2) + (홀수 셀이면 64)
    a.op("LDA", "abs", V_UPC)
    a.op("LSR", "imp")
    a.op("ASL", "imp")
    a.op("ASL", "imp")
    a.op("CLC")
    a.op("ADC", "imm", 8)
    a.op("TAY")
    a.op("LDA", "izpy", Z_UP)
    a.op(
        "AND", "imm", 0xFC
    )  # 하위 비트 = 「지우지 않는」 블록 표시(원래 내용이 있던 자리 — 숨길 때 0 으로 밀면 게임 그림이 사라진다)
    a.op("STA", "abs", V_YL)
    a.op("INY")
    a.op("LDA", "izpy", Z_UP)
    a.op("STA", "abs", V_YL + 1)
    a.op("LDA", "abs", V_UPC)
    a.op("AND", "imm", 1)
    a.op("BEQ", "rel", "u_ev")
    a.op("LDA", "abs", V_YL)
    a.op("CLC")
    a.op("ADC", "imm", 0x40)
    a.op("STA", "abs", V_YL)
    a.label("u_ev")
    a.op("ST0", "imm", 0)
    a.op("LDA", "abs", V_YL)
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "abs", V_YL + 1)
    a.op("STA", "abs", 0x0003)
    a.op("ST0", "imm", 2)
    a.label("u_tia")
    a.tia(BUF_RAM, 0x0002, 64)  # 평면 0·1
    a.tia("zeros", 0x0002, 64)  # 평면 2·3 = 0
    a.op("CLC")
    a.op("LDA", "abs", g("u_tia") + 1)
    a.op("ADC", "imm", 64)
    a.op("STA", "abs", g("u_tia") + 1)
    a.op("BCC", "rel", "u_nc")
    a.op("INC", "abs", g("u_tia") + 2)
    a.label("u_nc")
    a.op("INC", "abs", V_UPC)
    a.op("DEC", "abs", V_NT)
    a.op("BNE", "rel", "u_cell")
    a.op("LDA", "abs", V_UPC)
    a.op("CMP", "abs", V_UPN)
    a.op("BCC", "rel", "u_ret")
    a.op("LDA", "imm", 0xFF)
    a.op("STA", "abs", V_UPG)
    a.label("u_ret")
    a.op("RTS")
    # ── 사건 처리 ──────────────────────────────────────────────────────────
    a.label("events")
    a.op("LDA", "abs", V_CRN)
    a.op("BEQ", "rel", "e_go")
    a.op("RTS")
    a.label("e_nj")  # 분기 거리(−128~127) 때문에 e_no 로 가는 중간 디딤돌
    a.op("JMP", "abs", "e_no")
    a.label("e_go")
    a.op("CLY")
    a.op("LDA", "izpy", Z_EV)
    a.op("STA", "zp", Z_T0)
    a.op("INY")
    a.op("LDA", "izpy", Z_EV)
    a.op("STA", "zp", Z_T1)
    a.op("LDA", "abs", V_FR + 1)  # 프레임 ≥ t ?
    a.op("CMP", "zp", Z_T1)
    a.op("BCC", "rel", "e_nj")
    a.op("BNE", "rel", "e_due")
    a.op("LDA", "abs", V_FR)
    a.op("CMP", "zp", Z_T0)
    a.op("BCC", "rel", "e_nj")
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
    a.op("CMP", "imm", 4)
    a.op("BEQ", "rel", "e_hup")
    a.op("CMP", "imm", 1)
    a.op("BEQ", "rel", "e_up")
    a.op("CMP", "imm", 2)
    a.op("BEQ", "rel", "e_show")
    a.op("JSR", "abs", "hide")
    a.op("BRA", "rel", "e_adv")
    a.label("e_end")
    a.op("JSR", "abs", "hide")
    a.label("e_endl")  # 끝에선 남은 블록을 한꺼번에 지운다(래스터가 걸릴 그림이 없다)
    a.op("LDA", "abs", V_CRN)
    a.op("BEQ", "rel", "e_endz")
    a.op("JSR", "abs", "cstep")
    a.op("BRA", "rel", "e_endl")
    a.label("e_endz")
    a.op("STZ", "abs", V_ON)
    a.op("RTS")
    a.label("e_hup")  # 지우기 뒤 올리기
    a.op("JSR", "abs", "hide")
    a.op("LDA", "abs", V_CRN)
    a.op("BEQ", "rel", "e_up")
    a.op("RTS")  # 다 못 지웠다 — 사건은 안 넘기고 다음 틱에 다시(지우기가 끝나면 hide 는 빈손이고 올리기로 간다)
    a.label("e_up")  # 올리기 시작: 쪽 레코드 [0]=0 [1,2]=ADPCM 주소 [3]=셀 수
    a.op("LDA", "zp", Z_A)
    a.op("JSR", "abs", "findpage")
    a.op("LDA", "zp", Z_PG)
    a.op("STA", "zp", Z_UP)
    a.op("LDA", "zp", Z_PG + 1)
    a.op("STA", "zp", Z_UP + 1)
    a.op("LDA", "zp", Z_A)
    a.op("STA", "abs", V_UPG)
    a.op("STZ", "abs", V_UPC)
    a.op("LDY", "imm", 3)
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "abs", V_CLN)  # 지울 셀 수 — 이 쪽이 지워질 때(숨기기) 블록을 0 으로 되돌린다
    a.op("LDY", "imm", 1)
    a.op("LDA", "izpy", Z_PG)
    a.op(
        "STA", "zp", Z_DP
    )  # ADPCM 읽기 주소(셀마다 래치한다 — 한 번 래치해 두면 시간이 지나며 주소가 어긋난다. 에뮬 실측 10-14)
    a.op("INY")
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "zp", Z_DP + 1)
    a.op("INY")
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "abs", V_UPN)
    a.op("BRA", "rel", "e_adv")
    a.label("e_show")
    a.op("LDA", "abs", V_UPG)  # 올리기가 안 끝났으면 보이기를 미룬다(안 그러면 글자가 반쪽으로 뜬다 — 지우기가 먼저 돌아 올리기가 늦어진 에뮬 실측 10-15)
    a.op("CMP", "imm", 0xFF)
    a.op("BEQ", "rel", "e_sh1")
    a.op("RTS")
    a.label("e_sh1")
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
    # ── 보이기: SAT 항목을 VRAM 에. 레코드 [3]=셀 수 [4,5]=y0 워드 [6..]=(x+32, 줄 y 오프셋) ──
    a.label("show")
    a.op("LDA", "zp", Z_A)
    a.op("INC", "imp")
    a.op("STA", "zp", Z_SHP)
    a.op("LDA", "abs", V_HEIGHT)
    a.op("STA", "zp", Z_SHH)
    a.op("LDA", "zp", Z_A)
    a.op("JSR", "abs", "findpage")
    a.op("SMB2", "zp", FLAG_ZP)  # 팔레트 다시 올림
    _vdc_addr(a, (SAT_WORD + SLOT0 * 4) >> 8, (SAT_WORD + SLOT0 * 4) & 0xFF)
    a.op("LDY", "imm", 3)
    a.op("LDA", "izpy", Z_PG)
    a.op("LSR", "imp")
    a.op("STA", "zp", Z_T0)  # 항목 수(셀 둘 = 한 32×16 스프라이트)

    a.op("LDX", "imm", 0)
    a.label("s_loop")
    a.op("CPX", "zp", Z_T0)
    a.op("BCC", "rel", "s_go")
    a.op("JMP", "abs", "s_blank")
    a.label("s_go")
    a.op("TXA")
    a.op("ASL", "imp")
    a.op("ASL", "imp")
    a.op("CLC")
    a.op("ADC", "imm", 6)
    a.op("STA", "abs", V_KB)
    a.op("LDY", "imm", 4)
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "abs", V_YL)
    a.op("INY")
    a.op("LDA", "izpy", Z_PG)
    a.op("STA", "abs", V_YL + 1)
    a.label("s_fullh")
    a.op("LDY", "abs", V_KB)
    a.op("INY")  # 줄 위치
    a.op("LDA", "izpy", Z_PG)
    a.op("BEQ", "rel", "s_r0")
    a.op("STA", "abs", V_TMP)
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
    a.op("LDY", "abs", V_KB)
    a.op("LDA", "izpy", Z_PG)  # x+32
    a.op("STA", "abs", 0x0002)
    a.op("STZ", "abs", 0x0003)
    a.op("INY")
    a.op("INY")
    a.op("LDA", "izpy", Z_PG)  # 블록 워드 주소 하위(0 또는 0x80) — 하위 비트 둘은 표지(1 = 지우지 않음 · 2 = 오른쪽 셀이 빈 좁은 스프라이트(16 폭))라 `>> 5` 로 사라진다
    a.op("STA", "abs", V_YL)
    a.op("LSR", "imp")
    a.op("LSR", "imp")
    a.op("LSR", "imp")
    a.op("LSR", "imp")
    a.op("LSR", "imp")
    a.op("STA", "abs", V_TMP)
    a.op("INY")
    a.op("LDA", "izpy", Z_PG)  # 상위
    a.op("STA", "abs", V_CODE)
    a.op("ASL", "imp")
    a.op("ASL", "imp")
    a.op("ASL", "imp")
    a.op("ORA", "abs", V_TMP)
    a.op("STA", "abs", 0x0002)  # 패턴 코드 = 워드 >> 5
    a.op("LDA", "abs", V_CODE)
    for _ in range(5):
        a.op("LSR", "imp")
    a.op("STA", "abs", 0x0003)
    a.op("LDA", "imm", o.SPR_ATTR & 0xFF)
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "abs", V_YL)  # 좁은 표지면 CGX 비트를 끈다(SPR_ATTR 상위 = 1) — 줄당 스프라이트 16칸 한도에서 칸을 아낀다
    a.op("AND", "imm", 2)
    a.op("LSR", "imp")
    a.op("EOR", "imm", o.SPR_ATTR >> 8)
    a.op("STA", "abs", 0x0003)
    a.op("INX")
    a.op("JMP", "abs", "s_loop")
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
    # ── 지우기: 슬롯 전부 0 ───────────────────────────────────────────────
    a.label("hide")
    a.op("STZ", "zp", Z_SHP)
    _vdc_addr(
        a, SAT_WORD >> 8, SAT_WORD & 0xFF
    )  # 0~3 번도 같이 0 으로 — 앞 단계 패키지가 남긴 스프라이트 값이 보이지 않게
    a.op("LDX", "imm", SLOT0 + SLOTS)
    a.label("h_loop")
    for _ in range(4):
        a.op("STZ", "abs", 0x0002)
        a.op("STZ", "abs", 0x0003)
    a.op("DEX")
    a.op("BNE", "rel", "h_loop")
    # 올린 블록을 0 으로 되돌린다 — 장면은 안 쓰는 VRAM 이 0 이라고 믿는다(스프라이트 패턴의 투명한 부분 등). 글자가 남으면 다음 장면 그림에 조각이 박힌다(에뮬 실측 10-14)
    a.op("LDA", "abs", V_CLN)
    a.op("BEQ", "rel", "h_ret")
    a.op("INC", "imp")
    a.op("LSR", "imp")
    a.op("STA", "abs", V_CRN)  # 스프라이트 수 = 지울 블록 수
    a.op("STZ", "abs", V_CLN)
    a.op("LDA", "imm", 0xFF)
    a.op("STA", "abs", V_UPG)  # 올리던 것도 멈춘다
    a.op("LDA", "imm", 8)
    a.op("STA", "abs", V_CRK)
    a.op("JSR", "abs", "cstep")
    a.label("h_ret")
    a.op("RTS")
    # ── 블록 지우기 한 걸음: 틱마다 CLEAR_PER_TICK 블록 ──
    a.label("cstep")
    a.op("LDA", "abs", V_CRN)
    a.op("BEQ", "rel", "c_ret")
    a.op("LDX", "imm", CLEAR_PER_TICK)
    a.label("c_blk")
    a.op("LDY", "abs", V_CRK)
    a.op("LDA", "izpy", Z_UP)
    a.op("STA", "abs", V_TMP)
    a.op("AND", "imm", 0xFC)
    a.op("STA", "abs", V_YL)
    a.op("LDA", "abs", V_TMP)
    a.op("AND", "imm", 1)
    a.op("STA", "abs", V_TMP)  # 1 = 지우지 않는 블록
    a.op("INY")
    a.op("LDA", "izpy", Z_UP)
    a.op("STA", "abs", V_YL + 1)
    a.op("LDA", "abs", V_TMP)
    a.op("BNE", "rel", "c_next")
    a.op("ST0", "imm", 0)
    a.op("LDA", "abs", V_YL)
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "abs", V_YL + 1)
    a.op("STA", "abs", 0x0003)
    a.op("ST0", "imm", 2)
    for _ in range(4):
        a.tia("zeros", 0x0002, 64)
    a.label("c_next")
    a.op("CLC")
    a.op("LDA", "abs", V_CRK)
    a.op("ADC", "imm", 4)
    a.op("STA", "abs", V_CRK)
    a.op("DEC", "abs", V_CRN)
    a.op("BEQ", "rel", "c_ret")
    a.op("DEX")
    a.op("BNE", "rel", "c_blk")
    a.label("c_ret")
    a.op("RTS")
    a.label("zeros")
    a.data(bytes(64))
    a.label("pal8")
    a.data(bytes([0xFF, 0x01, 0x00, 0x00]))
    return a


TRAMP_LEN = 18


def tramp_code(tick):
    """RAM(`$22C0`) — 원래 IRQ 자리(`INC $2F · RMB0 $38`)를 대신하고, 켜져 있으면 MPR3 에 0x86 을 걸어 틱을 부른다."""
    t = A(TRAMP_IRQ)
    t.op("INC", "zp", 0x2F)
    t.op("RMB0", "zp", FLAG_ZP)
    t.op("LDA", "abs", V_ON)
    t.op("BEQ", "rel", "out")
    t.op("TSX")
    t.op(
        "LDA", "absx", 0x2103
    )  # 핸들러가 스택에 넣어 둔 $F7(끊긴 쪽의 VDC 레지스터 선택) — JSR 복귀 주소 둘 위
    t.op("STA", "abs", V_F7)
    t.op("TMA", "tma", 3)
    t.op("PHA")
    t.op("LDA", "imm", CODE_BANK)
    t.op("TAM", "tam", 3)
    t.op("JSR", "abs", tick)
    t.op("PLA")
    t.op("TAM", "tam", 3)
    t.label("out")
    t.op("RTS")
    out = t.bytes()
    assert len(out) <= 32, len(out)
    return out


def rinit_code(L, nsec):
    """RAM(`$2300`) init — AD_TRANS(셀 → ADPCM) · 상태 초기화 · 진짜 CD_PLAY · IRQ 훅 설치."""
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
        (0xF8, nsec), (0xF9, 0), (0xFA, ADPCM_BASE & 0xFF), (0xFB, ADPCM_BASE >> 8),
        (0xFC, DATA_REL >> 16), (0xFD, (DATA_REL >> 8) & 0xFF), (0xFE, DATA_REL & 0xFF), (0xFF, 0),
    ):  # fmt: skip
        r.op("LDA", "imm", val)
        r.op("STA", "zp", zp)
    r.op("JSR", "abs", 0xE033)  # AD_TRANS — 에뮬 실측(10-14): 0 = 성공
    r.op("CMP", "imm", 0)
    r.op("BNE", "rel", "rd")
    r.op("STZ", "abs", V_FR)
    r.op("STZ", "abs", V_FR + 1)
    r.op("STZ", "abs", V_UPC)
    r.op("STZ", "abs", V_CLN)
    r.op("STZ", "abs", V_CRN)
    r.op("STZ", "zp", Z_DEF)
    r.op("STZ", "zp", Z_SHP)
    r.op("STZ", "zp", Z_SHH)
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
    r.op("LDA", "imm", TRAMP_IRQ & 0xFF)  # `E6 2F 07 38` → `20 <트램펄린> EA`
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


def hole_len() -> int:
    """124째 섹터(원판 자료)의 앞쪽 보존 길이 — 마지막 0 아닌 바이트까지."""
    d = common.user_sector(PKG_REL + 123)
    nz = [i for i, b in enumerate(d) if b]
    return nz[-1] + 1 if nz else 0


def place(cur: int, n: int, hole: tuple[int, int]) -> int:
    """길이 n 덩이를 cur 에 놓되 구멍 `[lo, hi)` 과 겹치면 구멍 뒤로 민다 → 시작 주소."""
    lo, hi = hole
    if cur < hi and cur + n > lo:
        return hi
    return cur


def assemble(pages, where):
    ev = events(pages)
    L: dict[str, int] = {}
    hole = (HOLE_LO, HOLE_LO + hole_len())
    for _ in range(3):
        a = tick_code(L)
        recs = []
        for p, ad in zip(pages, where, strict=False):
            y0 = p["y0"] + 64
            rec = bytearray([1 if p.get("noreshow") else 0, ad & 0xFF, ad >> 8, len(p["cells"]), y0 & 0xFF, y0 >> 8])
            for k, ((x, yoff, _cb), blk) in enumerate(zip(p["cells"][::2], p["blocks"], strict=False)):
                assert 0 <= x + 32 <= 255, (p["lines"], x)
                if p["lines"] != ["(청소)"] and not any(p["cells"][2 * k + 1][2]):  # 오른쪽 셀이 비면 16 폭 스프라이트(줄당 16칸 한도에서 한 칸 아낀다)
                    blk |= 2
                rec += bytes([x + 32, yoff, blk & 0xFF, blk >> 8])
            recs.append(bytes(rec))
        code_len = len(a.out)
        assert CODE_ADDR + code_len <= hole[0], (code_len, "코드가 구멍 앞 빈 런에 안 든다")
        pagetab = CODE_ADDR + code_len
        pagetab1 = pagetab + 1
        cur = pagetab + 2 * len(pages)
        addrs = []
        for r_ in recs:
            cur = place(cur, len(r_), hole)
            addrs.append(cur)
            cur += len(r_)
        evlen = len(ev) * 5
        ev_at = place(cur, evlen, hole)
        assert ev_at + evlen <= 0x8000, (ev_at, evlen, "표가 뱅크 끝을 넘는다")
        L.update(pagetab=pagetab, pagetab1=pagetab1, events_tab=ev_at)
        L.update({k: v for k, v in a.labels.items()})
    return a, L, recs, addrs, ev


def build(pages=None):
    pages = pages or build_pages()
    blob, where = pack_data(pages)
    nsec = len(blob) // 2048
    a, L, recs, addrs, ev = assemble(pages, where)
    a = tick_code(L)
    a.labels["pagetab"] = L["pagetab"]
    a.labels["pagetab1"] = L["pagetab1"]
    code = bytearray(a.bytes())
    tab = b"".join(ad.to_bytes(2, "little") for ad in addrs)
    evb = bytearray()
    for t, op, pa, pb in ev:
        assert 0 <= t < 65536, t
        evb += bytes([t & 0xFF, t >> 8, op, pa, pb])
    segs = [(CODE_ADDR, bytes(code) + tab)] + [(ad, r_) for ad, r_ in zip(addrs, recs, strict=False)] + [(L["events_tab"], bytes(evb))]
    hole_lo, hole_hi = HOLE_LO, HOLE_LO + hole_len()
    for ad, b_ in segs:  # 구멍(원판 자료)을 안 건드린다
        assert ad + len(b_) <= hole_lo or ad >= hole_hi, (hex(ad), len(b_))
        assert ad + len(b_) <= 0x8000, (hex(ad), len(b_))
    module = segs
    # 뱅크 0x6A 런: 스텁 · 트램펄린 이미지 · RAM init 이미지
    rinit = rinit_code(L, nsec).bytes()
    assert len(rinit) <= RAM_INIT_MAX, len(rinit)
    tramp = tramp_code(a.labels["tick"])
    s = A(0x8000 + STUB_OFF)
    s.label("stub")
    s.tii("rinit_img", RAM_INIT, len(rinit))
    s.tii("tramp_img", TRAMP_IRQ, len(tramp))
    s.op("JMP", "abs", RAM_INIT)
    stub_len = len(s.out)
    base = 0x8000 + STUB_OFF
    tramp_img = base + stub_len
    rinit_img = tramp_img + len(tramp)
    s2 = A(base)
    s2.labels["rinit_img"] = rinit_img
    s2.labels["tramp_img"] = tramp_img
    s2.label("stub")
    s2.tii("rinit_img", RAM_INIT, len(rinit))
    s2.tii("tramp_img", TRAMP_IRQ, len(tramp))
    s2.op("JMP", "abs", RAM_INIT)
    stub = s2.bytes() + tramp + rinit
    assert len(stub) <= STUB_MAX, (len(stub), STUB_MAX)
    return module, stub, base, blob, nsec, L


def writes(pages=None):
    pages = pages or build_pages()
    module, stub, stub_addr, blob, nsec, _L = build(pages)
    pkg = bytes(common.track_data(PKG_REL, 128))
    base = PKG_REL * 2048
    lin = lambda bank, off: base + (bank - BANK0) * BANK + off
    stub_lin = lin(STUB_BANK, STUB_OFF) - base
    out = [
        (COUNT_TABLE_LINEAR, bytes([COUNT_NEW]), bytes([COUNT_OLD]), "ending_sub 패키지 38 섹터 수 123→124"),
    ]  # fmt: skip
    for ad, b_ in module:  # 코드·표 — 124째 섹터의 원판 자료(구멍)를 비켜 간다
        at = lin(CODE_BANK, ad - 0x6000)
        out.append((at, b_, pkg[at - base : at - base + len(b_)], f"ending_sub 코드·표(뱅크 0x86 +0x{ad - 0x6000:04X})"))
    out += [
        (lin(STUB_BANK, STUB_OFF), stub, pkg[stub_lin : stub_lin + len(stub)], "ending_sub 스텁·RAM 이미지(뱅크 0x6A)"),
        (base + HOOK_OFF, bytes([0x20, stub_addr & 0xFF, stub_addr >> 8]), bytes([0x20, 0x12, 0xE0]), "ending_sub CD_PLAY 훅"),
        (DATA_REL * 2048, blob, bytes(len(blob)), "ending_sub 셀 데이터(ADPCM 로 올린다)"),
    ]  # fmt: skip
    band_spans, band_info = band.spans(pkg, base, lin, STUB_BANK, STUB_OFF, len(stub), stub_lin)
    out += band_spans
    info = {
        "pages": len(pages),
        "cells": sum(len(p["cells"]) for p in pages),
        "module": sum(len(b_) for _a, b_ in module),
        "stub": len(stub),
        "sectors": nsec,
        "blob": len(blob),
        **band_info,
    }
    return out, info


def apply(w):
    if os.environ.get("ED_SUB_OFF"):  # 시험용 — 자막 없는 기준선(VRAM 배정·비교용)
        print("  대관식 자막: ED_SUB_OFF — 건너뜀")
        return None
    spans, info = writes()
    for linear, new, expect, label in spans:
        w.put(linear, new, expect, label)
    print(
        f"  대관식 자막: 쪽 {info['pages']} · 셀 {info['cells']} · 코드·표 {info['module']}B(상한 {CODE_MAX}) · 스텁 {info['stub']}B · 데이터 {info['sectors']}섹터 (rel {DATA_REL}~)"
    )
    return info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.parse_args()
    pages = build_pages()
    _spans, info = writes(pages)
    print(info)
    for i, p in enumerate(pages):
        print(
            f"{i:2d} {p['t0']:6.1f}-{p['t1']:6.1f}s  셀 {len(p['cells']):2d}  {' / '.join(p['lines'])}"
        )
    ev = events(pages)
    print("사건", len(ev), ev[:4])


if __name__ == "__main__":
    main()
