"""음성 자막 편집기 자료 — 오프닝(트랙 21)·대관식(트랙 23) 시각표를 편집기용 `data.json` 으로 낸다 (마스터 10-18 「편집기 만들자」).

    python3 games/pce-ed2/tools/subeditor_data.py     # work/review/subeditor/data.json (+ audio/ 가 있으면 길이)

편집기 페이지는 `tools/subeditor/index.html` 이고, 게시할 때 `data.json` · `audio/open.mp3` · `audio/end.mp3` 를 같이 올린다.
이 자료는 **커밋하지 않는다**(work/ — 받아쓰기 일본어 포함). 편집값을 롬 자료로 되돌리는 건 `subeditor_apply.py`.

JS 쪽 예산 계산이 빌드와 같은 숫자를 내는지 보려고, 쪽마다 빌드가 실제로 낸 셀 수(`cells0`)를 같이 싣는다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import ending_sub as e
import opening_sub as o

OUT = common.GAME_DIR / "work" / "review" / "subeditor"
CDDA = common.GAME_DIR / "work" / "review" / "cdda"


def _cells_per_sub(pages, script, split):
    """sub 마다 쪽별 셀 수 — build_pages 결과를 sub 의 쪽 수만큼 잘라 준다."""
    out, k = [], 0
    for sub in script["subs"]:
        n = len(split(sub["text"]))
        out.append([len(p["cells"]) for p in pages[k : k + n]])
        k += n
    return out


def main() -> None:
    op = json.loads(o.SUBS.read_text(encoding="utf-8"))
    en = json.loads(e.SUBS.read_text(encoding="utf-8"))
    op_pages = o.build_pages(op)
    en_pages = [p for p in e.build_pages(en) if p["lines"] != ["(청소)"]]
    op_cells = _cells_per_sub(op_pages, op, o.split_pages)
    en_cells = _cells_per_sub(en_pages, en, o.split_pages)
    words = json.loads((CDDA / "t21_words.json").read_text(encoding="utf-8"))
    rows = []
    for clip, script, cells in (("open", op, op_cells), ("end", en, en_cells)):
        for i, sub in enumerate(script["subs"]):
            rows.append({"clip": clip, "idx": i, "sub": sub, "cells0": cells[i]})
    # 대관식 코드·표 크기 기준(예산 추정의 기준점) — 편집기는 같은 식으로 계산한 차이를 더한다
    module0 = e.writes(e.build_pages())[1]["module"]
    data = {
        "clips": [
            {"clip": "open", "title": "오프닝 나레이션", "track": 21},
            {"clip": "end", "title": "대관식", "track": 23},
        ],
        "consts": {
            "FPS": o.FPS, "END_HOLD": o.END_HOLD, "UPLOAD_LEAD_OPEN": o.UPLOAD_LEAD, "UPLOAD_LEAD_END": e.UPLOAD_LEAD,
            "CUT_GUARD": e.CUT_GUARD, "LINE_CAP": o.LINE_CAP, "ADV_LATIN": o.ADV_LATIN, "CELL": o.CELL,
            "END_LINE_CAP": e.LINE_CAP + 8, "BAND_CAP": e.BAND_CAP, "TOP_CAP": e.TOP_CAP,
            "OPEN_BUF": [o.BUF_CELLS, o.BUF1_CELLS], "OPEN_SLOTS": o.SLOTS, "END_BUF": e.BUF_CELLS[0],
            "OPEN_CELLS0": sum(len(p["cells"]) for p in op_pages),
            "END_MODULE0": module0, "END_MODULE_MAX": e.CODE_MAX,
            "END_DATA_MAX": e.ADPCM_MAX,
            "END_CELLS0": sum(len(p["cells"]) for p in en_pages),
            "END_EVENTS0": len(e.events(e.build_pages())),
            "BAND": [list(s) for s in e.band.SEGMENTS],
            "TRANSITIONS": list(e.TRANSITIONS),
            "END_PAGES0": len(en_pages),
            "END_BLOB0": len(e.pack_data(e.build_pages())[0]),
            "END_SLOTS": e.SLOTS,
        },
        "rows": rows,
        "words": words,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"행 {len(rows)} · 단어 {len(words)} · 대관식 모듈 {module0}B → {OUT / 'data.json'}")


if __name__ == "__main__":
    main()
