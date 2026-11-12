"""마스터 판정 잠금 어댑터 — 공용 판정기(`scripts/check/master_rulings.py`)에 문안 지도(`textmap/`)의 한글 칸을 준다.

자리 = `<textmap 파일 이름>/<키>`(`segments/$D70325` 등), 갈래는 파일 이름(`segments` · `spans` · `cells` …). 제어 태그는 그대로 둔다."""

import glob
import json
from pathlib import Path

TEXTMAP = Path(__file__).resolve().parents[1] / "textmap"


def _strs(o, p=""):
    if isinstance(o, str):
        yield p, o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from _strs(v, f"{p}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _strs(v, f"{p}/{i}")


def corpus() -> list[tuple[str, str, str]]:
    """`[(자리, 갈래, 문안)]` — textmap 의 `kr` 필드(해시 `h` 는 뺀다)."""
    out = []
    for f in sorted(glob.glob(str(TEXTMAP / "*.json"))):
        name = Path(f).stem
        for p, s in _strs(json.loads(Path(f).read_text(encoding="utf-8"))):
            if p.endswith("/h"):
                continue
            out.append((name + (p.removesuffix("/kr")), name, s))
    return out
