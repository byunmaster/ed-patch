"""커서 선택지(`3B` 연산) 창을 전부 새 롬으로 찍는다 — 맵으로 뛰어 선택 연산 바이트만 주입한다(`dialog_harness.inject` 와 같은 길).

  python3 tools/choice_reshoot.py --out <폴더> [--cue …] [--only FT3006,OT0150]

산출: `<out>/<맵>_<위치>.png`(전체 화면) · `<out>/index.tsv`(맵·위치·열·행·상태). 위치 = 연산 오프셋.
선택지 목록은 **빌드된 멤버**에서 `choice_cols.scan` 으로 읽는다 — 램 블록(= 멤버)의 같은 자리를 주입한다.
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import choice_cols
import common
import dialog_harness as D
import headless_ps1 as H
import scriptmap
from warp_table import table


def targets(disc="ed3"):
    """[(맵, 연산 위치, 열, 행)] — 원판 멤버에서."""
    ch = {n: c for n, c, _p, _a in table(disc)}
    out = []
    iso = common.iso_files(disc)
    for path, (lba, size) in sorted(iso.items()):
        if not (path.startswith("/SCE") and path.endswith(".DAT")):
            continue
        data = common.read_lba(disc, lba, size)
        try:
            ents = common.arc_parse(data)[1]
        except common.ArchiveError:
            continue
        for nm, off, sz in ents:
            mem = data[off : off + sz]
            name = nm.replace("\\", "/").split("/")[-1].split(".")[0]
            if name not in ch:
                continue
            try:
                info = scriptmap.parse(mem)
            except Exception:
                continue
            tgt = {at: t for at, t, _f in info["targets"]}
            for p, cols, rows, _ids in choice_cols.scan(mem, info):
                # 🔴 `90` 연산자는 램 주소 짝수에 맞춰 읽어 항목이 4~5바이트다(패드) — 끝은 마지막 포인터 자리 + 2
                sites = [at for at in sorted(tgt) if p + 4 <= at <= p + 4 + 4 * rows + 2][:rows]
                out.append((name, p, cols, rows, ch[name], sites[-1] + 2 - p))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=D.DEFAULT_CUE)
    ap.add_argument("--only")
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    emu = H.Emu(a.cue)
    D.boot(emu, None, a.cue)
    os.makedirs(a.out, exist_ok=True)
    idx = os.path.join(a.out, "index.tsv")
    if not os.path.exists(idx):
        open(idx, "w", encoding="utf-8").write("맵\t위치\t열\t행\t상태\n")
    cur, cur_map = 0, None
    for name, p, cols, rows, chap, ln in targets():
        if only and name not in only:
            continue
        png = os.path.join(a.out, f"{name}_{p}.png")
        if os.path.exists(png):
            continue
        if cur_map != name:
            cur = D.jump(emu, name, chap[0], cur)
            cur_map = name
            snap = os.path.join(a.out, "_s.state")
            emu.save(snap)
        else:
            emu.load(snap)
            emu.run(2)
        blk = emu.u32(D.BASE)
        mem = emu.peek(blk, p + ln + 8)
        seq = mem[p : p + ln]
        d = ((blk + p) - D.BUF) & 1
        D.inject(emu, seq, d)
        emu.run(200)
        for _ in range(4):  # 페이드·이동 중이면 까만 화면 — 밝아질 때까지 더 돈다
            if np.asarray(emu.frame).mean() > 8:
                break
            emu.run(300)
        fr = np.ascontiguousarray(emu.frame)
        Image.fromarray(fr).save(png)
        open(idx, "a", encoding="utf-8").write(f"{name}\t{p}\t{cols}\t{rows}\t찍음\n")
        print(name, p, flush=True)


if __name__ == "__main__":
    main()
