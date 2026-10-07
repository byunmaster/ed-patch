"""pce-ed1 조판 지문 — `scripts/check/typeset_fingerprint.py` 가 부르는 게임별 구현.

화면 문안 전량을 **빌드와 같은 조판기**(`typeset.pages`)에 태워 구역별 해시를 낸다. 이 게임의 조판기는
`shared/text/krwrap` 위에 얹혀 있어 공용이 줄바꿈을 흔들면 여기서 바뀐다. 구역 = 씬 파일(`script/scnNNN.json`
하나) + 전투 문구(`script/sys/battle.json`) 하나. 입장 배너(raw)와 손으로 줄을 맞춘 창(`\\n` 포함)은
조판기를 안 타므로 건너뛴다(`typeset_check.scene_rows` 와 같은 기준).
"""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import font
import messages as M
import typeset


def _scene(n: int) -> str:
    h = hashlib.sha1()
    for k, v in sorted(M.load_translations(n).items()):
        t = v.get("t", "")
        if not t or v.get("raw") or "\n" in t:
            continue
        h.update(f"{k}\x00".encode())
        for pg in typeset.pages(font.expand_packed(t), speaker=True):
            h.update(("\x01".join(pg) + "\x02").encode())
    return h.hexdigest()[:12]


def _battle() -> str:
    """전투 창은 대사창과 줄 수가 달라 `typeset_check.wrap`(같은 krwrap 규칙)으로 줄을 짠다."""
    import typeset_check as T

    h = hashlib.sha1()
    msgs = json.loads((common.GAME_DIR / "script" / "sys" / "battle.json").read_text("utf-8"))
    for k, t in sorted(msgs["messages"].items()):
        lines, _cuts = T.wrap(T.pick_josa(t.replace("{01}", "\n")))
        h.update(f"{k}\x00".encode())
        h.update(("\x01".join(lines) + "\x02").encode())
    return h.hexdigest()[:12]


def fingerprint() -> dict[str, str]:
    out = {}
    for p in sorted((common.GAME_DIR / "script").glob("scn*.json")):
        out[p.stem] = _scene(int(p.stem[3:]))
    out["battle"] = _battle()
    return out


if __name__ == "__main__":
    fp = fingerprint()
    print(len(fp), "구역")
