"""그림 교체 — 자리표(`graphics_<disc>.json`)의 `file` 을 이미지에 넣는다.

우리가 그린 PNG 는 `assets/graphics/<disc>/` 에 **커밋된다**(우리 작업물이다).
원본 그림은 `work/review/tim/` 에만 두고 커밋하지 않는다.

🔴 **크기·bpp 가 같으면 바이트 수가 같다** — 이 게임의 그림 멤버는 압축이 아니라서
   아카이브 재배치도, 파일 크기 변화도 없다. 그래서 교체가 싸다.
🔴 자리는 「멤버 안 몇 번째 TIM 인가」다. `dump_tim.py --catalog` 가 크기까지 대조해
   **밀린 채로 그리는 사고**를 막는다.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
import common
import dump_tim
import tim


def catalog(disc):
    p = os.path.join(common.ROOT, f"graphics_{disc}.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)["images"]


def asset_dir(disc):
    return os.path.join(common.ROOT, "assets", "graphics", disc)


def overlay(raw, t, spec):
    """원본 그림 위에 글자 칸만 지우고 한글을 얹은 **같은 길이의** 바이트열 — 그림 PNG 를 커밋하지 않는 길.

    창 테두리처럼 **글자가 일부뿐인 그림**은 통째로 다시 그리면 원본 그림을 커밋하게 된다.
    그래서 빌드 때 원본을 읽어 `clear` 칸을 비우고 `lines` 를 그린다.
    🔴 **색인 단위로 쓴다** — `tim.replace`(색→색인 되짚기)를 거치면 같은 색이 두 색인에 있는
       팔레트(이 그림은 0·1 이 둘 다 흰색)에서 **칸 밖 화살표까지 색인이 바뀌었다**(2026-10-05 실측
       48픽셀). 게임이 색인별로 팔레트를 갈아 깜빡이게 하면 화면이 달라지므로, 칸 밖은 바이트까지
       그대로 둔다. 바탕·잉크 색인은 원본 픽셀(`bg_at`·`ink_at`)에서 집는다.
    """
    from shared.fonts import galmuri

    assert t["bpp"] == 4, "4bpp 만 다룬다"
    out = bytearray(raw)
    stride = t["w"] * 2
    pix0 = t["end"] - stride * t["h"]

    def get(x, y):
        v = out[pix0 + y * stride + x // 2]
        return (v >> 4) if x & 1 else (v & 0xF)

    def put(x, y, i):
        k = pix0 + y * stride + x // 2
        out[k] = (out[k] & 0x0F) | (i << 4) if x & 1 else (out[k] & 0xF0) | i

    bg, ink = get(*spec["bg_at"]), get(*spec["ink_at"])
    x0, y0, w, h = spec["clear"]
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            put(x, y, bg)
    f = galmuri(spec["font"])
    for lx, ly, text in spec["lines"]:
        for i, ch in enumerate(text):
            b = f.bits(ch, dx=spec.get("dx", 0), dy=spec.get("dy", 0), rows=16, width=16)
            for r in range(16):
                for c in range(16):
                    if b[r, c]:
                        X, Y = lx + i * spec["pitch"] + c, ly + r
                        assert x0 <= X < x0 + w and y0 <= Y < y0 + h, f"{text!r}: 칸 밖 ({X},{Y})"
                        put(X, Y, ink)
    return bytes(out)


def overlay_labels(raw, t, spec):
    """크레딧 그림의 **분야 라벨 줄만** 한글로 갈아 끼운 같은 길이의 바이트열(번역 규칙 3-7 — 이름은 그대로).

    줄마다 `[y0, y1, 글]` — 그 줄의 잉크 가로 범위의 가운데에 맞춰(원판 정렬을 따른다) 같은 높이에 앉힌다.
    줄 위아래 1행까지 바탕 색인으로 비우고 잉크 색인으로 쓴다(색인 단위 — 칸 밖은 바이트까지 그대로).
    🔴 `dead_rows` — 크레딧 두루마리가 **그리지 않는 그림 행**(조각 이음매의 마지막 행 · 쪽 끝 235~255, 실측 10-17 행 번호 눈금).
    원본에선 늘 빈 행이라 안 보이지만 우리 글자가 걸리면 그 줄만 잘린다(「션」 ㄴ 바닥). 걸리면 빌드가 선다.
    글꼴은 Galmuri14(`narration.render_line` 과 같은 길 — 아스키 비례폭·가운데 맞춤 규칙을 한 곳에 둔다).
    """
    import narration
    import numpy as np

    assert t["bpp"] == 4, "4bpp 만 다룬다"
    out = bytearray(raw)
    stride = t["w"] * 2
    width = t["w"] * 4
    pix0 = t["end"] - stride * t["h"]
    bg, ink = spec["bg"], spec["ink"]

    def get(x, y):
        v = out[pix0 + y * stride + x // 2]
        return (v >> 4) if x & 1 else (v & 0xF)

    def put(x, y, i):
        k = pix0 + y * stride + x // 2
        out[k] = (out[k] & 0x0F) | (i << 4) if x & 1 else (out[k] & 0xF0) | i

    for y0, y1, text in spec["rows"]:
        xs = [x for x in range(width) if any(get(x, y) != bg for y in range(y0, y1))]
        assert xs, f"{text!r}: 줄 {y0}~{y1} 에 잉크가 없다 — 자리가 밀렸다"
        cx = (min(xs) + max(xs)) / 2.0
        for y in range(max(0, y0 - 1), min(t["h"], y1 + 1)):
            for x in range(width):
                put(x, y, bg)
        m, _ = narration.render_line(text, spec["font"])
        ys, cs = np.nonzero(m.any(1))[0], np.nonzero(m.any(0))[0]
        m = m[ys.min() : ys.max() + 1, cs.min() : cs.max() + 1]
        h, w = m.shape
        ty, tx = max(0, (y0 + y1) // 2 - h // 2), int(round(cx - w / 2))
        assert tx >= 0 and tx + w <= width, f"{text!r}: 가로가 그림 밖이다"
        dead = [y for y in spec.get("dead_rows", []) if ty <= y < ty + h]
        assert not dead, f"{text!r}: 화면에 안 그려지는 행 {dead} 에 잉크가 걸린다(dead_rows)"
        for r in range(h):
            for c in range(w):
                if m[r, c]:
                    put(tx + c, ty + r, ink)
    return bytes(out)


def apply(disc):
    """(넣은 그림 수, {파일 경로: 새 바이트열}) — `file`·`overlay` 가 있는 자리만."""
    from PIL import Image

    want = {}
    for it in catalog(disc):
        if it.get("file") or it.get("overlay") or it.get("labels"):
            want.setdefault(it["member"], []).append(it)
    if not want:
        return 0, {}
    out, n = {}, 0
    for path, (lba, size) in sorted(common.iso_files(disc).items()):
        data = None
        for key, items in want.items():
            if not key.startswith(path + "!"):
                continue
            if data is None:
                data = bytearray(common.read_lba(disc, lba, size))
            nm = key.split("!", 1)[1]
            try:
                _, ents = common.arc_parse(bytes(data))
            except common.ArchiveError:
                ents = [(os.path.basename(path), 0, size)]
            m = {e[0]: (e[1], e[2]) for e in ents}
            if nm not in m:
                raise SystemExit(f"🔴 {key}: 멤버가 없다")
            off, sz = m[nm]
            blob = bytes(data[off : off + sz])
            raw, ts = dump_tim.images(blob)
            if raw is not blob and len(raw) != len(blob):
                raise SystemExit(f"🔴 {key}: 압축 멤버는 아직 못 바꾼다")
            for it in items:
                _, t = ts[it["index"]]
                if it.get("overlay"):
                    raw = overlay(raw, t, it["overlay"])
                    n += 1
                    continue
                if it.get("labels"):
                    raw = overlay_labels(raw, t, it["labels"])
                    n += 1
                    continue
                png = os.path.join(asset_dir(disc), it["file"])
                if not os.path.exists(png):
                    raise SystemExit(f"🔴 {png} 가 없다 (자리표가 가리킨다)")
                raw = tim.replace(raw, t, Image.open(png))
                n += 1
            data[off : off + sz] = raw
        if data is not None:
            out[path] = bytes(data)
    return n, out
