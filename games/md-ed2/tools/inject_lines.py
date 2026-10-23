"""시험 문자 주입 — 한 쪽에 줄을 3·4·5개 넣어 하네스가 실제로 몇 줄까지 찍는지 본다(이름 있는/없는 쪽).

    python3 tools/inject_lines.py [--out DIR]

한글 글리프 코드(`hangul_codes.json`)로 줄 n 개짜리 스트림(줄 사이 `01`, 끝 `00`)을 우편함 `SAY` 로 띄운다. 산출 `sweep/real-vs-harness/inject_*.png` + 줄 띠 표.
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_sweep as BS
import common
import headless
import scene_sweep as S
from PIL import Image

SCRATCH = S.MOD_AT + 0x2100  # 모듈 칸 끝자락(최대 8,720B 중 쓰지 않는 자리)
OUT = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "sweep" / "real-vs-harness"


def bands(frame):
    m = (frame[:, :, 0] >= 236) & (frame[:, :, 1] >= 236) & (frame[:, :, 2] >= 236)
    rows = np.where(m[140:224, 50:300].sum(axis=1) > 4)[0] + 140
    g, s, pv = [], None, None
    for r in rows:
        if s is None:
            s = r
        elif r != pv + 1:
            g.append((int(s), int(pv)))
            s = r
        pv = r
    if s is not None:
        g.append((int(s), int(pv)))
    return g


def main() -> None:
    out = OUT
    codes = json.loads(
        (common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")
    )
    enc = lambda t: b"".join(codes[ch].to_bytes(2, "big") for ch in t)
    c = headless.Core(str(BS.ROM))
    st = S.new_game_state(c, out.parent / "scene")
    res = []
    for named in (False, True):
        for n in (3, 4, 5):
            body = b"\x01".join(enc("란도플로라스신디") for _ in range(n)) + b"\x00"
            head = b"\x1e" + enc("란도") + b"\x04\x01" if named else b""
            c.load_state(st)
            c.poke(SCRATCH, head + body)
            d = out / f"inj_{'n' if named else 'u'}{n}"
            d.mkdir(exist_ok=True)
            k, status = S.say(c, SCRATCH, d, "p")
            for p in sorted(d.glob("p_*.png")):
                res.append(
                    f"{'이름 있음' if named else '이름 없음'} 줄 {n}개 → 줄 띠 {bands(np.array(Image.open(p).convert('RGB')))} ({p.name}, {status})"
                )
    (out / "inject.txt").write_text("\n".join(res) + "\n", encoding="utf-8")
    print("\n".join(res))


if __name__ == "__main__":
    main()
