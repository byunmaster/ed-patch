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


def apply(disc):
    """(넣은 그림 수, {파일 경로: 새 바이트열}) — `file` 이 있는 자리만."""
    from PIL import Image

    want = {}
    for it in catalog(disc):
        if it.get("file"):
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
                png = os.path.join(asset_dir(disc), it["file"])
                if not os.path.exists(png):
                    raise SystemExit(f"🔴 {png} 가 없다 (자리표가 가리킨다)")
                _, t = ts[it["index"]]
                raw = tim.replace(raw, t, Image.open(png))
                n += 1
            data[off : off + sz] = raw
        if data is not None:
            out[path] = bytes(data)
    return n, out
