"""씬 문안 → 화면에 나가는 바이트 조각(포맷 + 실제 인자).

`reinsert_kr_pilot.iter_candidates` 가 내는 씬 바이트를 빌드 이미지 안에서 찾아 오프셋을 잡고,
씬 오버레이의 sprintf 호출(`arg_scan`)에서 그 포맷에 실제로 들어가는 `%c` 인자(이름창 2/1 · 종단 6/8/11/12)를 뽑는다.
"""

import contextlib
import io
import json
import os
import sys

from . import arg_scan
from .image_io import Image

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = {"ED1": 0x8016A000, "ED2": 0x80165000}  # 씬 오버레이 적재 주소
SPRINTF = {"ED1": 0x800CC740, "ED2": 0x800A8134}


def _repo():
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    with contextlib.redirect_stdout(io.StringIO()):
        import reinsert_kr_pilot as R
    return R


def _layout() -> dict[str, tuple[int, int]]:
    """빌드 이미지 안 씬 오버레이 자리 — 빌드가 만드는 `derived/scn_layout.json`(원판 SCN_FILES 와 다르다)."""
    _repo()
    from common import OUT_DIR

    with open(os.path.join(OUT_DIR, "scn_layout.json"), encoding="utf-8") as f:
        return {k: (v["lba"], v["size"]) for k, v in json.load(f).items()}


def build(scn: str, image: Image):
    """scn(예 ED1SCN2) → [{eid, pieces:[{hex, args}]}] — 이미지 안 바이트 기준."""
    R = _repo()
    lba, size = _layout()[scn]
    d = image.read(lba, size)
    area = scn[:3]
    ar = arg_scan.scan(d, BASE[area], SPRINTF[area])
    with contextlib.redirect_stdout(io.StringIO()):
        cands = list(R.iter_candidates([scn]))
    out = []
    for _name, eid, _raw, cand, _t in cands:
        o = d.find(cand)
        pieces = []
        i = 0
        while i < len(cand):
            if cand[i] == 0:
                i += 1
                continue
            j = cand.find(b"\0", i)
            j = len(cand) if j < 0 else j
            a = ar.get(o + i)
            pieces.append({"hex": cand[i:j].hex(), "args": a[0] if a else None})
            i = j
        out.append({"scn": scn, "eid": eid, "pieces": pieces})
    return out
