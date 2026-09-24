"""엔딩 음성 자막 — 엔딩 모듈(rel 898)에 **오프닝과 같은 스프라이트 자막 런타임**을 심는다(2026-09-24).

    python3 games/pce-ed1/tools/ending_sub.py            # 조립 결과·타임라인 확인

마스터 확정 2026-09-24: 「이번 라운드가 엔딩까지 포함이야. 엔딩 바로 진행하자. 이번에는 하단에만 자막」.

런타임은 `opening_sub.py` 한 벌을 **따로 불러와**(importlib — 같은 파이썬 모듈을 두 번 쓰면 전역이
섞인다) 손잡이 값만 엔딩 것으로 바꿔 굽는다. 코드는 하나, 값만 둘이다(DRY — 둘째 소비자가 실재).
엔딩 모듈이 타이틀 모듈과 같은 엔진이라 가능하다: IRQ1 핸들러의 `JSR $E063`, 메인 루프 끝의 JSR,
팔레트 그림자 `$272E`, 화면 높이 `$2D54`, SAT `$7F00` 가 전부 같은 모양이다(실측).

다른 점(전부 값으로 잰 것 — devlog 2026-09-24):
  · 🔴 **스트립을 둘 RAM 이 없다** — 모듈이 확장 RAM 256KB(뱅크 0x68~0x87)를 통째로 쓴다. 대신 모듈은
    ADPCM RAM 을 **데이터 저장소로** 쓰고(앞 18KB 만 AD_TRANS, 재생 없음 · AD_READ 로 꺼내 읽는다)
    나머지 46KB 가 빈다. 스트립을 거기(AD_TRANS $8000~) 싣고 셀마다 AD_READ 로 꺼낸다(STRIP_MODE).
  · 코드 자리는 모듈 +0x64D9~+0x7FFF(6.9KB, 원판 0) 중 스태프롤(staffroll.py, +0x6500~) 뒤.
    곡이 끝난 뒤 오마케 적재가 이 자리를 덮으므로(쓰기 BP 실측) **마지막 장면 뒤 스스로 물러난다**
    (DONE_FRAME: SAT 를 지우고 IRQ·메인 루프 훅을 원래 JSR 로 되돌린다).
  · CD_PLAY 때 코드 뱅크(0x6B)가 $8000 창이 아니라 $A000 창(MPR5)에 있다 → 스텁을 거친다(INIT_WINDOW).
  · 화면이 144~192줄로 짧다 — 높이 보정 상한을 48 까지(YADJ_MAX), 자리는 **하단 한 가지**(page_y_table).
  · 장면마다 빈 청크가 11개뿐인 곳이 있어 자막은 **2줄까지**(SUB_MAX_ROWS).
"""

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common

_spec = importlib.util.spec_from_file_location("ending_rt", HERE / "opening_sub.py")
rt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rt)

import staffroll

# ── 엔딩 값 ────────────────────────────────────────────────────────────────
rt.NAME = "ending"
rt.SUBS = common.GAME_DIR / "script" / "ending_sub.json"
rt.SCENES = HERE / "data" / "ending_scenes.json"
rt.MODULE_REL = 898
rt.CDPLAY_OFF = 0x180B  # `JSR $E012` (모듈 +0x180B, 논리 $580B — CD_PLAY BP 의 복귀 주소로 찾았다)
rt.OPENING_ARGS = (
    0x50,
    0x47,
)  # 엔딩 CD_PLAY 인자 $F8·$F9 = 50:47:36 (트랙20) — init 의 트랙 게이트
rt.TITLE_JSR_OFF = None  # 타이틀 진입 정리 훅 없음 — DONE_FRAME 으로 스스로 물러난다
rt.IRQ_JSR_ADDR = 0x41FD  # IRQ1 핸들러의 `JSR $E063` (모듈 +0x1FD)
rt.LOOP_JSR_ADDR = 0x404F  # 메인 루프 마지막 `JSR $414B` (+0x4F)
rt.LOOP_TARGET = 0x414B
rt.CODE_BANK = 0x6B
_code_off = (staffroll.NEW_OFF + len(staffroll.build().split(b"\x1a", 1)[0]) + 1 + 0x1F) & ~0x1F
rt.CODE_OFF = _code_off  # 모듈 오프셋(= 뱅크 0x6B + (off − 0x6000))
rt.CODE_ADDR = 0x8000 + (_code_off - 0x6000)
rt.CODE_MAX = 0x8000 - _code_off
rt.INIT_WINDOW = 0xA000  # CD_PLAY 때 MPR5 = 0x6B
rt.STRIP_MODE = "adpcm"
rt.ADPCM_BASE = 0x8000
rt.CELL_BUF = 0x3C00  # 엔딩 내내 0 인 워크 RAM($3AF0~$3DA1, 덤프 79장)
rt.DATA_REL = 434  # 빈 섹터 rel 422~449 중 오프닝(422~433) 뒤
rt.YADJ_MAX = 49  # 144줄 화면 = (240−144)/2 = 48
rt.SUB_MAX_ROWS = 2
rt.SHORTEST_SCREEN = 144
rt.BACKUP_SLOTS = []  # 빌리지 않는다
rt.BAND = True  # 🔴 까만 띠 자막(마스터 2026-09-24) — 표시를 프레임 바닥까지 늘리고 그림 밑변에서 BG 를 끈다
# 자막 덩어리 바닥의 프레임 행. 표시는 프레임 240행까지 늘어나지만 에뮬(mednafen)·TV 는 아래 8줄쯤을
# 잘라 보여서 228 에 둔다. 띠가 좁은 그림(176줄 = 띠 32줄)에서 두 줄이면 위가 그림 밑에 몇 줄 걸친다.
# 띠가 없는 그림(240줄, 마지막 대지 장면)에선 종전처럼 그림 위에 뜬다.
BOTTOM_ROW = 228
rt.BAND_CENTER = True
rt.RASTER_SAFE = True  # 그리기에서 SEI 를 안 건다 — 띠 RCR 이 늦으면 띠 윗단에 그림 타일이 비친다(마스터 캡처 2026-09-25)
rt.WRAP_W = 7 * 32 - 2  # 띠엔 게임 스프라이트가 없어 스트립 7개를 다 쓴다(왼쪽 정렬, 마스터 2026-09-25)
rt.BAND_FLOOR = 2  # 한 줄도 그림 밑변보다 2행 아래부터(띠가 좁은 장면 — 「어이구…」)
VIS_BOTTOM = 232  # 띠의 보이는 바닥(프레임 행)
rt.PAGE_Y_BIAS = 64  # page_y = 64 + 프레임 행 은 한 바이트를 넘는다 — 표엔 프레임 행만
rt.DONE_FRAME = None  # 아래 build_all 에서 장면 표의 done_frame 으로


def page_y_table(pages, page_lay):
    """까만 띠 **가운데**(마스터 2026-09-24 「까만띠 중앙에」). 표엔 띠가 가장 넓은 경우의 가운데(236 − bh/2)를,
    런타임이 장면마다 y_adj/2 를 빼서 그 장면 띠의 가운데로 옮긴다. 띠 = 그림 밑변(120 + h/2)~프레임 232행
    (에뮬·TV 가 아래 8줄쯤을 자른다). 띠가 좁거나 없으면(240줄) 바닥을 BOTTOM_ROW 에 맞춘다(page_ymax)."""
    out, ymax = [], []
    for i, rows in enumerate(pages):
        n = len(rows)
        if n:
            assert page_lay[i] == "bottom", (i, page_lay[i], "엔딩은 하단만")
            assert n <= rt.SUB_MAX_ROWS, (i, n, "엔딩 자막은 2줄까지 — script/ending_sub.json 에서 나눠라")
        # 🔴 한 줄도 **두 줄일 때와 같은 top** 에 둔다(마스터 2026-09-25 — 가운데 정렬이 아니라)
        bh = rt.LINE_H * (rt.SUB_MAX_ROWS - 1) + rt.GLYPH_ROWS
        y = (VIS_BOTTOM + 120 + 240 // 2) // 2 - bh // 2  # h=240 일 때의 가운데 식: (232 + 240)/2 − bh/2
        out.append(y - rt.PAGE_Y_BIAS + 64)
        bh_real = rt.LINE_H * (max(n, 1) - 1) + rt.GLYPH_ROWS  # 바닥 한계는 그 페이지의 실제 높이로
        ymax.append(VIS_BOTTOM - 1 - bh_real - rt.PAGE_Y_BIAS + 64)  # 바닥을 보이는 끝(231행)까지 — 좁은 띠에서도 가운데에 가깝게
        # 가장 짧은 그림에서도 위가 그림 밑변보다 아래(띠 안)
        top144 = y - (240 - rt.SHORTEST_SCREEN) // 4
        assert min(top144, BOTTOM_ROW - bh) >= 120 + rt.SHORTEST_SCREEN // 2 - 2, (i, top144, bh)
    rt.PAGE_YMAX[:] = ymax
    return out


rt.page_y_table = page_y_table


def _setup():
    import json

    sc = json.loads(rt.SCENES.read_text(encoding="utf-8"))
    rt.DONE_FRAME = sc["done_frame"]
    assert rt.CODE_OFF >= staffroll.NEW_OFF + len(staffroll.build().split(b"\x1a", 1)[0]) + 1


def build_all():
    _setup()
    return rt.build_all()


def apply(f, touched):
    _setup()
    return rt.apply(f, touched)


def main():
    _setup()
    sub, lines, pages, events, banks, _table, code = rt.build_all()
    print(
        f"코드 ${rt.CODE_ADDR:04X}(모듈 +0x{rt.CODE_OFF:X}) {len(code)}B / {rt.CODE_MAX} · 스트립 {len(banks[0])}B = {rt.STRIP_SECTORS}섹터"
    )
    for sec, page in events:
        print(
            f"  {sec:7.2f}s f{rt.frames_of(sec, sub['timing']):5d} → page {page}: {[None if r is None else lines[r] for r in pages[page]]}"
        )


if __name__ == "__main__":
    main()
