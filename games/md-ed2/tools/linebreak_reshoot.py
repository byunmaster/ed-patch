"""줄·쪽 나눔 규칙(2-16) 재촬영 — 바뀐 스트림만 전(ED_LAYOUT=0)·후 롬으로 `scene_sweep` 에 태운다.

    python3 tools/linebreak_reshoot.py <before|after> <롬> <오프셋표.json> <출력 DIR>

오프셋표 = {"before": {"BBB-K:스트림키": [구운 오프셋]}, "after": {...}} (스크래치에서 문안 일치로 만든다).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_sweep as BS
import scene_sweep as SS

which, rom, table, out = sys.argv[1:5]
BS.ROM = Path(rom)
offs = json.loads(Path(table).read_text())[which]
sel = [f"{k.split(':')[0]}:{o:x}" for k, v in offs.items() for o in v]
sys.argv = ["scene_sweep", *sel, "--out", out]
SS.main()
