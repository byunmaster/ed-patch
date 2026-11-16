"""번역 에이전트용 묶음 — 아직 번역 안 된 멤버를 모아 `show` 출력(원문 포함)을 묶음 파일로 낸다.

⚠ 출력엔 **원문(JP)이 들어 있다** — 저장소 밖(`.local/work/inbox/ps1-ed4/agent/in/`)에만 쓴다. 커밋 금지.
    python3 tools/agent_pack.py <출력 폴더> [--max N] [--chapters CDEFG]
묶음 하나 = 같은 아카이브(맵) 멤버들, 번역할 조각 수 합이 `--max`(기본 600) 안팎. 파일 첫 줄에 번역할 조각 수를 적는다.
"""

import collections
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import dump
import reinsert
import script_kr as sk


def main(argv):
    out_dir = argv[1]
    mx = int(argv[argv.index("--max") + 1]) if "--max" in argv else 600
    chs = argv[argv.index("--chapters") + 1] if "--chapters" in argv else "CDEFG"
    common.verify_source()
    have = sk.load_all()
    todo = collections.OrderedDict()
    for path, nm, data, off, sz in dump.script_members():
        if path[1] not in chs:
            continue
        segs = reinsert.member_segments(data[off : off + sz])
        rows = have.get((path, nm), {})
        left = [i for i, c in enumerate(segs) if c and i not in rows]
        if left:
            todo.setdefault(path, []).append((nm, data[off : off + sz], len(left)))
    batches, cur, n = [], [], 0
    for path, ms in todo.items():
        for nm, mem, k in ms:
            if cur and n + k > mx * 1.3 or (cur and cur[-1][0] != path and n >= mx * 0.6):
                batches.append(cur)
                cur, n = [], 0
            cur.append((path, nm, mem, k))
            n += k
    if cur:
        batches.append(cur)
    os.makedirs(out_dir, exist_ok=True)
    for bi, b in enumerate(batches, 1):
        total = sum(k for *_x, k in b)
        arcs = sorted({p.split("/")[-1].replace(".DAT", "") for p, *_ in b})
        name = f"{b[0][0][1]}{bi:02d}"
        with open(os.path.join(out_dir, f"{name}.txt"), "w", encoding="utf-8") as f:
            f.write(f"# 묶음 {name} — 번역할 조각 {total} · 멤버 {len(b)} · 아카이브 {' '.join(arcs)}\n\n")
            for path, nm, mem, k in b:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    sk.view(path, nm, mem, show_all=False)
                short = nm.split("\\")[-1].replace(".BIN", "")
                f.write(f"## {path.split('/')[-1].replace('.DAT', '')} {short}   (번역할 조각 {k})\n")
                f.write(buf.getvalue() + "\n")
        print(name, total, len(b), arcs)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
