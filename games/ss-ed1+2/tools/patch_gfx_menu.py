"""시작 화면 버튼 한글화 — `START/MENU1·2.DAT` 의 `はじめから`/`つづきから`.

**규격**(2026-08-22 실측) — 선형 8bpp **320×254**, 팔레트는 `MENU*.PAL`(256색 RGB555 BE).
⚠ 셀 배치가 아니다. VDP2 셀일 줄 알고 8×8 로 깔아 봤다가 어긋났다 — 그냥 좌→우, 위→아래다.
⚠ 화면은 224행인데 파일은 254행이다. 남는 30행에도 값이 들어 있어 **자르지 않는다.**

**버튼** y 193~218 · 왼쪽 x 48~111 · 오른쪽 x 225~287 (각 64×26). 두 파일이 같은 자리다.

⚠ 획은 **어두운 쪽**이다(금색 바탕 위 짙은 글자) — PS1 과 같다. 작은 화면에선 흰 글자처럼
보여서 부등호를 뒤집었다가 버튼이 통째로 까매졌다(2026-08-22). **확대해서 눈으로 보고**
정한다 — 「밝기 임계」류는 방향을 틀려도 코드가 조용히 돈다.

**수법은 PS1 과 같다**(`ps1-ed1+2/tools/patch_gfx_title.py`) — 획 픽셀만 **버튼 안쪽 색**으로
덮고 한글을 얹은 뒤 **기존 팔레트에 최근접 양자화**한다. 인페인트는 안 쓴다(버튼 밖 색을
당겨와 테두리를 오염시킨다).
⚠ 금색은 **세로 그라디언트**라 행마다 다른 색으로 채운다 — 한 색으로 채우면 띠가 생긴다.

    python3 tools/patch_gfx_menu.py --apply
"""

import os
import sys

import numpy as np
from scipy.ndimage import distance_transform_edt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

W, H = 320, 254
FILES = ("MENU1", "MENU2")
# (x0, x1, y0, y1, 문안) — x1·y1 은 포함
# ⚠ 사각은 **알약보다 넉넉하게** 잡는다. 딱 맞게 잡았더니 `は` 의 첫 획이 경계 밖에 걸려
#   지워지지 않고 세로 잔상으로 남았다(유저 지적 2026-08-22). 실제 알약 모양은 아래
#   「따뜻한 색」 마스크가 잡으므로, 사각은 **넉넉히 감싸기만** 하면 된다.
BUTTONS = (
    (43, 116, 189, 222, "처음부터"),
    (220, 292, 189, 222, "이어하기"),
)
NEODGM = os.path.join(common.ROOT, "shared", "fonts", "neodgm.ttf")
GOLD_MARGIN = 40  # R 이 B 보다 이만큼 크면 금색 — 지도(파랑·올리브)와 가르는 값
# 🔴 알약 **모양 하나 + 자리 넷**. 여덟이 같은 도안이라 실루엣도 같아야 한다.
# `PILL_TOP` = 위 절반 각 행의 좌·우 들여쓰기(px). 아래는 뒤집어 붙여 **상하 대칭**을 보장한다.
# ⚠ 실측 원본에는 8~9행에 5·4 같은 튀는 값이 있었다 — 거기 **일본어 획이 테두리에 닿아**
#   검출이 깨진 것이다. 그래서 런타임 검출을 버리고 상수로 박는다.
# 🔴 **알약 모양 하나 + 자리 넷.** `PILL_PROF[r]` = 그 행의 좌·우 들여쓰기(px).
#   위 절반만 재고 아래로 뒤집어 **상하 대칭**을 보장한다.
# 값은 **꼬리(선택) 스프라이트에서 쟀다** — 화면 쪽은 위아래에 지도·문장이 걸려 검출이 샌다
#   (실측: MENU2 이어하기가 34행을 다 잡았다). 꼬리 스트립은 알약과 남색 배경뿐이다.
# ⚠ 런타임 검출로 되돌리지 말 것. 색 실루엣 + 덩어리 + 행채움까지 붙여 봤는데도 위 자리에서
#   배경으로 샜다(2026-08-24 재시도). 상수가 맞다.
#
# 🔴 **원본은 두 버튼 높이가 다르다** — `처음부터` 25행 · `이어하기` 26행. 새턴·PS1 둘 다
#   그렇다(실측). **우리는 25 하나로 통일한다**(유저 확정 2026-08-24) — PS1 이 이미 그렇게
#   해 두었고 화면에서 멀쩡하다.
#   ⚠ 26행짜리의 남는 아랫줄은 **잔재 링이 배경으로 되메운다.** 그러려면 링이 퍼올 진짜
#     지도가 뷰 안에 있어야 한다 — 꼬리 뷰를 알약 딱 맞게 자르니 퍼올 게 없어 원본 알약
#     가장자리를 옆으로 늘려 **회색 줄**이 됐다(실측 `idx4(72,64,64)`×54). PS1 은 뷰가
#     타이틀 그림 전체라 그 일이 안 났다. 그래서 `SEL_BUTTONS` 를 위아래로 넓혔다.
PILL_TOP = [5, 4, 4, 3, 2, 2, 1, 1, 1, 0, 0, 0]  # 위 절반의 좌·우 들여쓰기(px)
PILL_PROF = PILL_TOP + [0] + PILL_TOP[::-1]  # 25행 — 상하 대칭
PILL_W = 64  # 알약 폭
# 원본 알약 높이(행) — 우리 것은 25 로 통일했지만 **지워야 할 범위는 원본 것**이다.
PILL_ORIG_H = {"처음부터": 25, "이어하기": 26}
PILL_AT = [(5, 4), (4, 4), (11, 2), (12, 2)]  # 좌상 자리 — 화면 둘, 꼬리 둘
PILL_STATE = ["screen", "screen", "tail", "tail"]  # 글자색을 묶는 단위
INSET = 0  # 알약에서 이만큼 안쪽만 건드린다 — 테두리·캡은 원본 그대로
# ⚠ 2 로 두면 그 2px 링에 걸친 일본어가 **가장자리 잔점**으로 남는다(유저 지적 2026-08-23).
#   1 이면 잔점이 사라지고 윤곽은 그대로다(0 까지 재 봤는데 1 이 안전 여유가 있다).
RADIUS = 6  # 캡 반경(실측: 맨 윗행이 가운데보다 좌우 5px 좁다)
CAP_PAD = 4  # 글자 상자를 캡에서 이만큼 띄운다
VPAD = 3  # 글자 상자 세로 여백
# ⚠ 글자 색은 **최빈이 아니라 「충분히 흔한 것 중 가장 어두운 색」**이다 — 최빈으로 잡았더니
# MENU2 에서 안티에일리어싱 갈색(RGB(112,88,24))이 뽑혀 글자가 흐려졌다(실측).
INK_MIN_COUNT = 8  # 글자색 후보로 칠 최소 픽셀 수(양쪽 버튼 합산)
BORDER = 1  # 알약 테두리로 남길 두께 — 2px 로 두면 그 링에 걸친 일본어 획이 잔상으로 남았다
INSET = 0  # 알약을 이만큼 깎아 칠한다 — 0 이면 실루엣 전체. 잔점을 나중에 지우기보다
# **처음부터 넓게 칠해 덮는다**(유저 지시 2026-08-23). 1~2 로 두면 그 링에 걸친 일본어가
# 가장자리 잔점으로 남는다(실측: 「이어하기」 오른쪽 쉼표 같은 조각).
# 글자를 놓을 때만 쓰는 **추가 여백**. 알약은 양끝이 둥글어 `INSET` 만으론 글자가 캡에 닿는다.
TEXT_MARGIN = 2
# 네 버튼 **전부**에서 안 넘치는 크기. 자동맞춤에 맡기면 화면마다 갈린다(실측 10 vs 11).
# ⚠ 10px 은 원본보다 한참 작았다(원본 획 60x21 · 우리 40x9). 위에서 상자를 넓혀
# 여덟 상자 전부에 들어가는 최댓값이 13px 이다(52x11).
PIN_SIZE = (
    14  # PS1 알약과 같은 크기(유저 확정 2026-08-23). 원문보다 세로 2~4px 작지만 캡 여유가 있다
)
# 글자 임계 — **알약 밝기 대비**로 잡는다(중앙 휘도 × 이 값).
# 🔴 절대값(200)으로 뒀더니 **선택 상태 버튼에서 글자를 못 잡았다** — 그쪽은 알약이 더 밝아
#   글자 휘도도 160~250 으로 올라간다(미선택은 24 안팎). 유저 지적으로 발각.
#   상대값이면 두 상태를 한 규칙으로 덮는다. 0.6 이 네 자리에서 가장 고르다(실측).
INK_RATIO = 0.6
HALO = 2  # 획 둘레 팽창 — 글자의 **밝은 테두리**까지 지운다(안 하면 유령이 남는다)


# 🔴 **선택 상태 버튼은 화면 밖에 따로 있다.** 화면(320×224) 뒤 9,728B 에 밝은 판이 있고
#   **폭이 320 이 아니라 72** 다. 그래서 오래 「잡데이터」로 보였다 — 폭을 짐작으로 넣지 말고
#   **자기상관으로 stride 를 찾았다**(72 가 평균차 24.8 로 압도적, 다음이 32.4).
#   ⚠ 미선택만 고치면 **선택했을 때 일본어가 그대로 뜬다**(유저 지적 2026-08-22 — 인게임에서
#     왼쪽 선택 버튼만 `はじめから` 였다). 두 판을 다 고쳐야 상태를 오가도 안 흔들린다.
TAIL_OFF = 320 * 224
TAIL_W = 72
# ⚠ **알약보다 위아래로 넉넉히 잡는다**(위 2행 · 아래 1~2행). 딱 맞게 자르면 잔재 링이
#   퍼올 배경이 뷰 안에 없어 원본 알약 가장자리를 옆으로 늘려 버린다(2026-08-24 실측).
#   ⚠ 아래로 두 행 넘게 늘리지 않는다 — 꼬리 스트립 y133 부터는 팔레트 0(미사용)이라
#     그걸 퍼오면 자홍색이 번진다.
SEL_BUTTONS = ((72, 99, "처음부터"), (104, 132, "이어하기"))


def load(mm, files, name):
    """(파일 전체 바이트, 팔레트). ⚠ 화면(320×254) 뒤에도 데이터가 있어 **통째로** 든다."""
    lba, size = files[f"/START/{name}.DAT"]
    raw = np.frombuffer(common.read_extent(mm, lba, size), dtype=np.uint8)
    lba, size = files[f"/START/{name}.PAL"]
    p = common.read_extent(mm, lba, size)
    pal = np.array(
        [
            (
                ((v := int.from_bytes(p[i : i + 2], "big")) & 0x1F) << 3,
                ((v >> 5) & 0x1F) << 3,
                ((v >> 10) & 0x1F) << 3,
            )
            for i in range(0, 512, 2)
        ],
        dtype=np.uint8,
    )
    return raw.copy(), pal


def screen_view(raw):
    """화면 픽셀 (254×320)."""
    return raw[: W * H].reshape(H, W)


def tail_view(raw):
    """화면 밖 선택 상태 스프라이트 (stride 72)."""
    t = raw[TAIL_OFF:]
    n = len(t) // TAIL_W * TAIL_W
    return t[:n].reshape(-1, TAIL_W)


SS = 4  # 글자를 이 배율로 그린 뒤 축소한다 — 아래 주석


def render_text(text, w, h, pin=None):
    """버튼 안에 들어갈 한글 **알파맵**(0~255). 폭에 맞춰 자동으로 줄인다.

    🔴 **임계로 자르지 않는다.** 잘라 내면 11px 급에서 획이 1px 민선이 되어 **얇고 성겨**
    보인다(유저 지적 2026-08-22). PS1 은 같은 폰트를 **4배로 그린 뒤 LANCZOS 로 축소**해
    가장자리에 중간 톤을 남긴다 — 그 톤이 금색과 섞이며 획이 굵어 보인다. 같은 길을 쓴다.
    ⚠ PS1 이 기각한 것들도 그대로 피한다 — `stroke_width` 굵히기(작은 버튼에서 뭉갠다) ·
      글자색 더 짙게(원본 톤과 어긋난다) · 알파 감마(계단이 드러난다).
    """
    from PIL import Image, ImageDraw, ImageFont

    # ⚠ 폭은 `getlength` 가 아니라 **`getbbox` 로 잰다** — advance 는 실제 잉크보다 좁게
    #   나와 마지막 글자가 잘렸다(실측). 잉크 상자를 기준으로 맞추고 그만큼 밀어 넣는다.
    for size in [pin] if pin else range(h, 6, -1):
        ft = ImageFont.truetype(NEODGM, size, layout_engine=ImageFont.Layout.BASIC)
        x0, y0, x1, y1 = ft.getbbox(text)
        tw, th = x1 - x0, y1 - y0
        if tw <= w and th <= h:
            big = Image.new("L", (w * SS, h * SS), 0)
            fb = ImageFont.truetype(NEODGM, size * SS, layout_engine=ImageFont.Layout.BASIC)
            bx0, by0, bx1, by1 = fb.getbbox(text)
            ImageDraw.Draw(big).text(
                (((w * SS) - (bx1 - bx0)) // 2 - bx0, ((h * SS) - (by1 - by0)) // 2 - by0),
                text,
                255,
                font=fb,
            )
            return np.asarray(big.resize((w, h), Image.LANCZOS)).astype(np.float32) / 255.0
    raise SystemExit(f"버튼에 안 들어간다: {text!r} (상자 {w}x{h})")


def _dilate(m, n):
    """4방향 팽창 n회 — 획 둘레의 테두리·안티에일리어스를 같이 잡는다."""
    for _ in range(n):
        out = m.copy()
        out[1:] |= m[:-1]
        out[:-1] |= m[1:]
        out[:, 1:] |= m[:, :-1]
        out[:, :-1] |= m[:, 1:]
        m = out
    return m


def _component(m, r, c):
    """(r,c) 에서 4방향으로 이어진 덩어리만 남긴다 — 알약과 안 붙은 배경을 뗀다."""
    out = np.zeros_like(m)
    if not m[r, c]:
        return m
    stack = [(r, c)]
    out[r, c] = True
    while stack:
        y, x = stack.pop()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < m.shape[0] and 0 <= nx < m.shape[1] and m[ny, nx] and not out[ny, nx]:
                out[ny, nx] = True
                stack.append((ny, nx))
    return out


def _span_fill(m):
    """행마다 첫 True ~ 마지막 True 사이를 채운다 — 알약 실루엣이 그대로 나온다.

    ⚠ 이 근사는 **행마다 덩어리가 하나일 때만** 옳다. 알약은 그렇다(볼록). 마스크가 밖으로
    새면 이 방식이 그 오차를 **가로로 증폭**하므로, 색 기준을 먼저 엄격히 잡아야 한다.
    """
    out = np.zeros_like(m)
    for r in range(m.shape[0]):
        xs = np.nonzero(m[r])[0]
        if xs.size:
            out[r, xs[0] : xs[-1] + 1] = True
    return out


def _fill_holes(m):
    """**안쪽 구멍만** 메운다 — 윤곽은 한 픽셀도 안 넓힌다.

    ⚠ 행마다 좌우 끝 사이를 채우는 방식은 **둥근 캡을 사각으로 뭉개** 칠이 버튼 밖으로
    삐져나갔다(유저 지적 2026-08-22). 바깥에서 흘러들어오지 **못하는** 자리만 구멍이다.
    """
    h, w = m.shape
    outside = np.zeros_like(m)
    stack = []
    for r in range(h):
        for c in (0, w - 1):
            if not m[r, c] and not outside[r, c]:
                outside[r, c] = True
                stack.append((r, c))
    for c in range(w):
        for r in (0, h - 1):
            if not m[r, c] and not outside[r, c]:
                outside[r, c] = True
                stack.append((r, c))
    while stack:
        y, x = stack.pop()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and not m[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                stack.append((ny, nx))
    return m | ~outside


def _erode(m, n):
    """4방향 침식 n회 — 알약 덩어리에서 테두리를 남기고 안쪽만 얻는다."""
    for _ in range(n):
        out = m.copy()
        out[1:] &= m[:-1]
        out[:-1] &= m[1:]
        out[:, 1:] &= m[:, :-1]
        out[:, :-1] &= m[:, 1:]
        m = out
    return m


def _rects(raw):
    """(그릴 대상 2D 뷰, 문안) 목록 — 화면의 미선택 버튼 + 꼬리의 선택 버튼."""
    scr, tail = screen_view(raw), tail_view(raw)
    out = [(scr[y0 : y1 + 1, x0 : x1 + 1], t) for x0, x1, y0, y1, t in BUTTONS]
    out += [(tail[r0 : r1 + 1], t) for r0, r1, t in SEL_BUTTONS]
    return out


def _pill_cells(w, h, at, text="처음부터"):
    """알약 화소의 **(가상 좌표) → (뷰 좌표)** 매핑.

    가상 좌표는 알약을 펼친 25행 × `PILL_W` 격자다. 뷰가 좁아 오른쪽이 넘치면 **다음 줄
    왼쪽**으로 이어진다.

    🔴 **되감김은 같은 줄이 아니라 다음 줄이다**(유저 QA 2026-08-24 — 「선택일 때 오른쪽
      테두리가 미선택보다 1px 위」). 꼬리 스트립은 72폭 줄이 이어진 선형 버퍼라, 알약
      64px 이 x=11 에서 시작하면 마지막 3px 은 그 줄 끝을 넘어 **다음 줄 0~2 열**에 놓인다.
      같은 줄로 감았더니 오른쪽 캡만 한 줄 위로 올라갔다.
      ⚠ PS1 에선 이 문제가 없다 — 알약이 스프라이트 안에 다 들어가 넘치지 않는다.
    ⚠ 화면(미선택) 알약은 뷰 안에 다 들어와 넘침이 없다 — 이 매핑이 그대로 항등이다.

    반환: `(뷰 마스크, 가상 마스크, 가상→뷰 행 배열, 열 배열)`.
    """
    ox, oy = at
    prof = PILL_PROF
    n = len(prof)
    vm = np.zeros((n, PILL_W), bool)
    vr = np.zeros((n, PILL_W), int)
    vc = np.zeros((n, PILL_W), int)
    for r, pad in enumerate(prof):
        for x in range(PILL_W):
            lin = ox + x
            vr[r, x], vc[r, x] = oy + r + lin // w, lin % w
            vm[r, x] = pad <= x < PILL_W - pad
    ok = (vr >= 0) & (vr < h)
    m = np.zeros((h, w), bool)
    m[vr[vm & ok], vc[vm & ok]] = True
    return m, vm & ok, vr, vc


def _pill_mask(w, h, at, text="처음부터", inset=None):
    """알약 마스크(뷰 좌표).

    🔴 여기까지 방식을 넷 갈아탔다. 되풀이하지 않도록 남긴다.
      ① 색·밝기로 잡기 → 그늘·탈색·옆 스프라이트에 걸려 새거나 덜 잡았다(유저 지적 다섯 번).
      ② PS1 식 **합성 둥근사각** → 모서리가 실제 캡보다 튀어나와(실측 118px) 거기 어두운
         지도가 「획」으로 잡혀 **칠이 알약 밖으로 나갔다**.
      ③ 사각으로 가둔 색 실루엣 → 일본어가 테두리에 닿은 자리에서 검출이 깨져 자리마다 달랐다.
         2026-08-24 에 덩어리+행채움까지 붙여 다시 시도했는데 또 샜다(MENU2 이어하기가 34행을
         통째로 잡았다). **상수가 맞다 — 또 시도하지 말 것.**
      ✅ 모양을 **한 번 재서 상수로 박고** 자리만 넷 둔다.
    `PILL_PROF[r]` = 그 행의 좌·우 들여쓰기(px), 알약 폭은 `PILL_W`.
    """
    ins = INSET if inset is None else inset
    m, _vm, _vr, _vc = _pill_cells(w, h, at, text)
    return _erode(m, ins) if ins else m


def _local_fill(rgb, dom, mask, win=6):
    """mask 픽셀을 **같은 행 ±win 안의 성한 픽셀 중앙값**으로 메운다(제자리 갱신).

    테두리 링에 쓴다 — 거기서 「그 행의 밝은 금색」으로 메우면 어두운 윤곽이 밝게 떠 버린다.
    """
    h, w = dom.shape
    for r in range(h):
        xs = np.nonzero(mask[r])[0]
        if not xs.size:
            continue
        ok = np.nonzero(dom[r] & ~mask[r])[0]
        if not ok.size:
            continue
        src = rgb[r].copy()
        for x in xs:
            k = win
            near = ok[np.abs(ok - x) <= k]
            while near.size < 3 and k < w:
                k *= 2
                near = ok[np.abs(ok - x) <= k]
            rgb[r, x] = np.median(src[near], axis=0)


def _ink_color(raw, pal):
    """**상태별로 글자색 하나**를 고른다 — 미선택(화면) 둘, 선택(꼬리) 둘.

    ⚠ 버튼마다 따로 뽑았더니 같은 상태인데 색이 갈렸다(유저 지적 2026-08-23 —
      「미선택일때 처음 이어 폰트색상이 좀 다른것 같은데」). 실측: 화면은 RGB(0,0,0) vs
      (16,8,0), 꼬리는 (72,64,56) vs (104,96,56) 까지 벌어졌다.
    ⚠ 상태를 **하나로 합치지도 않는다** — 원본이 원래 다르다. 미선택 알약(어두운 금색)엔
      거의 검정, 선택 알약(밝은 노랑)엔 짙은 회올리브다. 상태 안에서만 통일한다.
    같은 상태 두 버튼의 획 픽셀을 모아, **충분히 흔한 것 중 가장 어두운 색**을 쓴다.
    """
    hist = {}
    for idx, (sub, _t) in enumerate(_rects(raw)):
        h, w = sub.shape
        mask = _pill_mask(w, h, PILL_AT[idx], _t)
        lum = pal[sub].astype(int).sum(2)
        inr = lum[mask]
        thr = (np.percentile(inr, 75) + np.percentile(inr, 25)) / 2
        v, c = np.unique(sub[(lum < thr) & mask], return_counts=True)
        d = hist.setdefault(PILL_STATE[idx], {})
        for i, n in zip(v, c, strict=True):
            d[int(i)] = d.get(int(i), 0) + int(n)
    # ⚠ 「최빈 대비 비율」로 거르면 안 된다 — 둘을 합치면 최빈이 커져 **어두운 색이 통째로
    #   탈락**한다(실측: MENU2 꼬리가 RGB(64,64,56) → (136,128,56) 로 밝아졌다).
    #   절대 개수로 자른다: 우연한 한두 픽셀만 빼고 그중 가장 어두운 색.
    out = {}
    for st, d in hist.items():
        cand = [i for i, n in d.items() if n >= INK_MIN_COUNT]
        out[st] = min(cand, key=lambda i: int(pal[i].astype(int).sum()))
    return out


# 🔴 **알약을 새로 그린다**(유저 확정 2026-08-23, PS1·게임선택 판과 같은 방식). 원본은
#   금색 세로 그라디언트에 줄무늬가 있어 지저분하고, 획만 덮어 칠하니 잔재·잡티가 끝없이 났다.
#   단색 + 1px 테두리로 다시 그린다. ⚠ 원본엔 테두리가 없어서 1px 로만 얹는다.
#   색은 원본 금색의 **p70** 이다 — 최빈·중앙값은 그라디언트 아래쪽이 섞여 탁하다.
#   ⚠ PS1 과 **같은 값**으로 둔다(유저 확정 2026-08-23 「두 기종 동일」). 각 기종 원본의
#     p70 은 #c8a858 / #d0b058 로 미세하게 달랐다 — 눈에 안 띄는 차이라 하나로 묶는다.
PILL_BODY = {"screen": (0xD0, 0xB0, 0x58), "tail": (0xF8, 0xF0, 0x50)}
PILL_BORDER_F = 0.55  # 테두리 = 본체 색 × 이 값
PILL_RESIDUE = 2  # 알약 바깥 이만큼을 배경으로 되메운다(원본 안티에일리어스 잔재)


def patch_one(raw, pal, verbose=False):
    """제자리 갱신. 반환: 바뀐 픽셀 수."""
    changed = 0
    ink_by_state = _ink_color(raw, pal)
    for idx, (sub, text) in enumerate(_rects(raw)):
        h, w = sub.shape
        rect = PILL_AT[idx]
        mask, vm, vr, vc = _pill_cells(w, h, rect, text)
        state = PILL_STATE[idx]
        body = np.array(PILL_BODY[state], np.float64)
        border = body * PILL_BORDER_F
        # 🔴 **테두리는 펼친 좌표에서 잰다.** 뷰 좌표에서 이웃을 보면 되감김 이음매가
        #   「알약 끝」으로 잡혀 한가운데에 갈색 세로줄이 생긴다(유저 QA 2026-08-24 —
        #   실측 x0·x71 이 rgb(144,120,40) = 본체×0.55). 펼친 격자에선 알약이 이어져 있어
        #   평범한 4방향 이웃 검사가 그대로 맞는다.
        ve = vm & ~(
            np.pad(vm, 1)[:-2, 1:-1]
            & np.pad(vm, 1)[2:, 1:-1]
            & np.pad(vm, 1)[1:-1, :-2]
            & np.pad(vm, 1)[1:-1, 2:]
        )
        edge = np.zeros_like(mask)
        edge[vr[ve], vc[ve]] = True
        out = pal[sub].astype(np.float64)
        out[mask] = body
        out[edge] = border
        # 한글 — 알약 사각에서 캡·여백만큼 안으로.
        ox, oy = rect
        cx0, cx1 = ox + CAP_PAD, ox + PILL_W - CAP_PAD
        ry0, ry1 = oy + VPAD, oy + len(PILL_PROF) - VPAD
        alpha = render_text(text, cx1 - cx0, ry1 - ry0, pin=PIN_SIZE)
        ink = pal[ink_by_state[state]].astype(np.float64)
        box = out[ry0:ry1, cx0:cx1]
        box[...] = box * (1 - alpha[..., None]) + ink * alpha[..., None]
        d2 = ((pal.astype(np.float32)[None, None] - out[:, :, None]) ** 2).sum(3)
        q = d2.argmin(2).astype(np.uint8)
        # ⚠ **알약 바깥 링도 배경으로 되메운다** — 원본 알약의 안티에일리어스가 실루엣
        #   바깥으로 삐져나와 잔재로 남는다(PS1 실측: 1px 안에 8~48화소).
        # 🔴 **링은 원본 알약이 차지하던 행 안에서만 칠한다.** 링의 목적은 원본 알약의
        #   안티에일리어스 잔재를 지우는 것이지 배경을 다시 칠하는 게 아니다. 뷰를 넓히고
        #   나서 링이 알약 위아래의 **원래 안 건드리던 배경까지** 덮어 화면에 줄이 생겼다
        #   (유저 QA 2026-08-24 — 「선택일 때 처음부터는 위에 한 줄, 이어하기는 위아래로」).
        #   ⚠ 색으로 가르려다 실패했다 — MENU2 는 **배경이 따뜻해서** 「금색이면 알약」이
        #     안 통한다(뷰 맨 윗줄까지 걸렸다). 그래서 **행 범위**로 가둔다.
        #   ⚠ 원본 높이가 버튼마다 다르다(`PILL_ORIG_H`) — 25 로 통일한 우리 알약보다
        #     `이어하기` 가 한 줄 크고, 그 한 줄이 정확히 지워야 할 자리다.
        rowok = np.zeros(h, bool)
        rowok[oy : oy + PILL_ORIG_H[text]] = True
        ring = _dilate(mask, PILL_RESIDUE) & ~mask & rowok[:, None]
        if ring.any():
            src = pal[sub].astype(np.float32)
            # 🔴 **피할 자리는 「알약 + 링」뿐이다.** 예전엔 `_dilate(mask, 2)` 전체를 피했는데,
            #   그러면 알약 바로 아래 두 줄이 통째로 막혀 **퍼올 지도가 없어진다** — 남는 줄이
            #   한 색(`idx171`)으로 뭉갰다(유저 QA 2026-08-24, 실측). 링만 피하면 그 **바로
            #   아래 진짜 지도**가 최근접이 되어 세로로 자연스럽게 이어진다.
            _, ind = distance_transform_edt(mask | ring, return_indices=True)
            fill = src[ind[0], ind[1]]
            dr = ((pal.astype(np.float32)[None, None] - fill[:, :, None]) ** 2).sum(3)
            sub[ring] = dr.argmin(2).astype(np.uint8)[ring]
        sub[mask] = q[mask]
        changed += int(mask.sum() + ring.sum())
        if verbose:
            print(f"    {text}: 알약 {int(mask.sum())} 화소 다시 그림")
    return changed


def main():
    apply = "--apply" in sys.argv
    common.verify_source()
    _f, mm = common.open_image()
    files = {p: (l, s) for p, l, s in common.iso_files(mm)}
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if apply and not os.path.exists(dst):
        raise SystemExit(f"먼저 자막을 넣는다(patch_title.py --apply) — {dst} 가 없다")
    for name in FILES:
        raw, pal = load(mm, files, name)
        n = patch_one(raw, pal, verbose=True)
        print(f"  {name}: 픽셀 {n} 변경")
        if not apply:
            continue
        lba, size = files[f"/START/{name}.DAT"]
        with open(dst, "r+b") as f:
            ns = common.write_at(f, lba, size, 0, raw.tobytes(), label=f"{name}.DAT 버튼")
        print(f"    → 섹터 {ns}")
    if not apply:
        print("  (미리보기만 — 실제로 넣으려면 `--apply`)")


if __name__ == "__main__":
    main()
