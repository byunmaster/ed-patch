"""전투 「나타났다」 줄 화면 확인(4-6 색) — `battle_sweep` 와 같은 덩이 교체 전투인데, 전투가 시작되는 첫 프레임부터 **화면 전체**를 찍는다
(`battleview.fight` 는 로그 창만 오려 낸 뒤 첫 쪽만 안정되면 찍어 나타남 줄 쪽을 놓친다).

    python3 appear_shot.py --iso <디버그 이미지> --out <폴더> --chunks 2690:18976 386:44911 [--lines 6]
산출: `<out>/<rel>_<덩이>_<번호>_<프레임>.png`(화면 전체, 바뀔 때마다) — 줄 번호는 나타남 줄.
"""

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_sweep as bs
import battleview as bv
import pceview
from PIL import Image


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bram", default="/root/save/pce-ed2/ed2.sav")
    ap.add_argument("--chunks", nargs="+", required=True)
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--allow-stale", action="store_true")
    ap.add_argument("--orig", action="store_true", help="원판 롬(일본어)을 돌린다 — 지역 글리프 표를 안 바꾼다(원판엔 없다). 이미지 옆에 같은 이름 cue 가 있어야 한다")
    a = ap.parse_args()
    import romtag

    romtag.check(a.iso, a.allow_stale)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cue = str(Path(a.iso).with_suffix(".cue"))
    pre = out / "pre.state"
    e = bv.to_encounter(cue, a.bram, str(pre))
    st = pre.read_bytes()
    want = {tuple(int(x) for x in c.split(":")) for c in a.chunks}
    n = 0
    for gid, key, idx, lines5, gl in bs.fights(a.iso, None, want):
        p = out / "cur.state"
        p.write_bytes(pceview.patch_state(st, bv.synth_chunk(lines5), b"" if a.orig else gl, 38))
        e.load(str(p))
        e.run(2)
        seen: set[str] = set()
        k = 0
        for i in range(a.frames // 6):
            e.run(6)
            h = hashlib.md5(e.frame_img.tobytes()).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            Image.fromarray(e.frame_img[0:224, 0:256]).save(out / f"{gid}_a{idx[0]}_{k:02d}.png")
            k += 1
            if k >= 14:
                break
        n += 1
        print(gid, key, idx, k, flush=True)
    print(f"끝 — 전투 {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
