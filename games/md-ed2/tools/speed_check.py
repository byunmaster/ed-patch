"""메시지 속도 「멈춤」(3)과 「보통」(1) 으로 같은 스트림을 찍어 쪽마다 대사 영역 픽셀이 같은지 센다 — 「멈춤」 표시 경로의 결함 확인용(마스터 10-19).

    python3 tools/speed_check.py [표본수=40] [--out DIR]

표본 = 한글 문안이 있는 스트림을 모듈 앞에서부터 고르게(모듈 걸러 하나씩). 산출: `sweep/speed-check/result.tsv`(스트림 | 쪽 수 보통/멈춤 | 다른 쪽 수) + 다른 쪽의 두 PNG.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import battle_sweep as BS
import common
import condtail_sweep as CT
import headless
import scene
import scene_sweep as S
from PIL import Image

ROOT = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "sweep"


def main() -> None:
    a = sys.argv[1:]
    out = ROOT / "speed-check"
    if "--out" in a:
        i = a.index("--out")
        out = Path(a[i + 1])
        del a[i : i + 2]
    only = None
    if "--only" in a:  # 「BBB-K/새오프셋,…」 — 이 스트림들만
        i = a.index("--only")
        only = [x.split("/") for x in a[i + 1].split(",")]
        del a[i : i + 2]
    use_orig = "--orig" in a  # 원판 롬(같은 후크)으로 같은 스트림(원판 오프셋으로 짝지음)을 찍는다
    if use_orig:
        a.remove("--orig")
    n = int(a[0]) if a else 40
    out.mkdir(parents=True, exist_ok=True)
    rom_path = CT.orig_hook_rom() if use_orig else BS.ROM
    c = headless.Core(str(rom_path))
    st = S.new_game_state(c, ROOT / "scene") if not use_orig else CT.throne(c, rom_path, out)
    mods = S.built_modules(BS.ROM.read_bytes())
    picks = []
    if only:
        newm = {f"{b:03d}-{k}": m for b, k, m in mods}
        origm = {f"{b:03d}-{k}": m for b, k, m in archives.modules(common.rom())}
        for key, off in only:
            off = int(off, 16)
            if use_orig:
                o = scene.parse_module(origm[key])
                new, pair = scene.pair_streams(o, newm[key])
                inv = {v: k_ for k_, v in pair.items()}
                if off in inv:
                    picks.append((key, origm[key], inv[off]))
            else:
                picks.append((key, newm[key], off))
    else:
        for bi, k, m in mods[:: max(len(mods) // n, 1)]:
            mod = scene.parse_module(m)
            for o, s_ in sorted(mod.streams.items()):
                t = b"".join(x.raw for x in s_.tokens if x.kind == "text")
                if sum(1 for ch in t if ch >= 0x80) >= 12:
                    picks.append((f"{bi:03d}-{k}", m, o))
                    break
            if len(picks) >= n:
                break
    rows = ["스트림\t쪽(보통)\t쪽(멈춤)\t다른 쪽\t프레임(보통)\t프레임(멈춤)"]
    for key, m, o in picks:
        res = {}
        for tag, v in (("n", 1), ("s", 3)):
            c.load_state(st)
            S.set_speed(c, v)
            c.poke(S.MOD_AT, m)
            d = out / f"{key}_{o:04x}_{tag}"
            d.mkdir(exist_ok=True)
            # 프레임 수는 BUSY 가 풀릴 때까지(say 는 끝나면 돌아온다)
            n_pages, status = S.say(c, S.MOD_AT + o, d, "p")
            res[tag] = [np.array(Image.open(p).convert("RGB")) for p in sorted(d.glob("p_*.png"))]
        nn, ss = res["n"], res["s"]
        bad = sum(
            1
            for x, y in zip(nn, ss, strict=False)
            if int((np.abs(x[120:].astype(int) - y[120:].astype(int)).sum(axis=2) > 0).sum()) > 40
        )
        if len(nn) != len(ss):
            bad += abs(len(nn) - len(ss))
        rows.append(f"{key}/{o:04x}\t{len(nn)}\t{len(ss)}\t{bad}\t-\t-")
        print(rows[-1], flush=True)
    (out / "result.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
