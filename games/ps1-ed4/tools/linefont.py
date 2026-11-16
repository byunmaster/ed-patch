"""한 줄을 Galmuri BDF 로 **픽셀 단위**로 그린다 — 그림에 박힌 글(내레이션·스태프롤)을 우리가 다시 그릴 때 쓴다.

ps1-ed3 `narration.py` 의 Galmuri 갈래를 옮겼다(그쪽은 ED3 전용 neodgm 도안 얹기까지 한 파일이라 통째로 못 가져온다). 둘째 소비자가 ps1-ed3 라 **공용 후보**다(`shared/gfx/`).

- 한글은 칸 폭(폰트 이름의 숫자) 으로 흘리고, **아스키는 비례폭**이다(BDF `DWIDTH` — 숫자 8 · 쉼표 4 · 공백 5). 절반으로 흘리면 숫자가 잘린다(ED3 실측).
- 말줄임표(`…`)는 폰트 글리프를 안 쓰고 **바닥에 점 셋**을 직접 찍는다(번역 규칙 1-3 — 일본식 가운데 점 금지). 이어진 말줄임표는 한 덩어리로 간격을 고르게.
"""

import os

import numpy as np

from shared import fonts

ELLIPSIS = {"…": 3}
_ADV = {}


def cell_of(name):
    return int("".join(c for c in name if c.isdigit()))


def advance(name):
    """BDF 의 `DWIDTH` — 코드포인트 → 보내는 폭(`shared/fonts` 로더는 BBX 만 들고 버린다)."""
    if name not in _ADV:
        adv, cp = {}, None
        with open(os.path.join(fonts.HERE, f"{name}.bdf"), encoding="utf-8", errors="replace") as f:
            for line in f:
                t = line.split()
                if not t:
                    continue
                if t[0] == "ENCODING":
                    cp = int(t[1])
                elif t[0] == "DWIDTH" and cp is not None:
                    adv[cp] = int(t[1])
        _ADV[name] = adv
    return _ADV[name]


def _text(txt, name):
    f = fonts.galmuri(name)
    cell, adv = cell_of(name), advance(name)
    cols = []
    for ch in txt:
        wide = cell if ord(ch) >= 0x80 else adv.get(ord(ch), cell // 2)
        if ch == " ":
            cols.append(np.zeros((cell * 3, wide), bool))
            continue
        if not f.has(ch):
            raise ValueError(f"글리프 없음: {ch!r} ({name})")
        g = f.bits(ch, dy=cell, rows=cell * 3, width=cell + 8)[:, :wide].astype(bool)
        if ch == ",":  # 🔴 쉼표 꼬리가 온점 행보다 한 행 아래로 나와 줄 사이 빈 행으로 샌다(마스터 10-25 「대지에 사람이 위쪽 점」) — 꼬리가 바닥(온점) 행에 오게 한 행 올린다
            g = np.roll(g, -1, axis=0)
        cols.append(g)
    return np.concatenate(cols, axis=1) if cols else np.zeros((cell * 3, 1), bool)


def _baseline(name):
    """말줄임표를 앉힐 줄 = 온점의 아랫줄."""
    cell = cell_of(name)
    b = fonts.galmuri(name).bits(".", dy=cell, rows=cell * 3, width=cell + 8)
    return int(np.nonzero(b.any(axis=1))[0].max())


def _dots(n_chars, name):
    cell = cell_of(name)
    n = 3 * n_chars
    width = cell * n_chars
    pitch = max(2, round(cell / 3))
    span = pitch * (n - 1) + 1
    x0 = (width - span) // 2
    m = np.zeros((cell * 3, width), bool)
    base = _baseline(name)
    for k in range(n):
        m[base, x0 + k * pitch] = True
    return m


def render(txt, name="Galmuri11"):
    """한 줄 → (불리언 행렬, 잉크 윗줄 맞춤으로 자른 것). 말줄임표만 따로 찍어 잇는다."""
    parts, buf, run = [], "", 0
    for ch in txt + "\0":
        if ch in ELLIPSIS:
            if buf:
                parts.append(_text(buf, name))
                buf = ""
            run += 1
            continue
        if run:
            parts.append(_dots(run, name))
            run = 0
        if ch != "\0":
            buf += ch
    if buf:
        parts.append(_text(buf, name))
    if not parts:
        return np.zeros((1, 1), bool)
    h = max(p.shape[0] for p in parts)
    m = np.concatenate([np.pad(p, ((0, h - p.shape[0]), (0, 0))) for p in parts], axis=1)
    ys = np.nonzero(m.any(axis=1))[0]
    return m[ys.min() :] if len(ys) else m


def width_of(txt, name="Galmuri11", *, trim_tail=True):
    """줄 폭(px). 가운데 맞춤 폭은 줄 끝 문장부호(`.` `,` `…`)를 뺀다(번역 규칙 2-8) — `trim_tail`."""
    body = txt.rstrip(".,…") if trim_tail else txt
    return render(body, name).shape[1] if body else 0
