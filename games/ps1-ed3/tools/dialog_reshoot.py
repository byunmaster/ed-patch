"""맵의 대사 창을 전부 다시 찍는다 — **글자가 처음 나타날 때까지 기다린 뒤 멎으면** 찍는다(노이즈 프레임·덜 그려진 창 방지, 10-20 qa 지적).

  python3 tools/dialog_reshoot.py --maps GT0101,FR5210 --out <폴더> [--cue …] [--state …]

산출: `<out>/<맵>/NNN.png`(창 띠 — 하네스와 같은 번호) · `<out>/index.tsv`(맵·번호·시퀀스·잉크 픽셀·상태). 상태: 정상 · 글자없음 · 창없음(안 멎음/안 열림, 전체 화면을 `NNNx.png` 로 남김).
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dialog_harness as D
import dialog_verify as V
import headless_ps1 as H
from warp_table import table


def static_windows(mem, blk):
    """[(창 번호, 주입 바이트, 정렬 d, [조각 번호…])] — **굽은 멤버 바이트**에서 대사 창 체인을 일반형(`0F [인자] [op…] 90 V (op… 90 W)* 00`, 줄·쪽·변수 op 허용)으로 뽑는다.
    `D.windows` 는 `0F 90 V (01 90 W)* 00` 만 봐서 쪽·변수가 낀 창(대부분의 NPC 대사)을 놓친다. 판별은 `check_var_spacing.chains` 와 같다."""
    import scriptmap
    from check_var_spacing import _ops_back

    info = scriptmap.parse(mem)
    base = info["base"]
    idx = {s: i for i, (s, _c) in enumerate(info["segments"])}
    sites = dict(info["pointers"])

    def nxt(q):
        ops, j = [], q + 2
        while j < len(mem) and 1 <= mem[j] <= 7:
            ops.append(mem[j])
            j += 1
        if ops and j < len(mem) and mem[j] == 0x90:
            q2 = j + 1 + ((j + 1) & 1)
            if q2 in sites:
                return ops, q2, j
        return ops, None, j

    linked = {n for q in sites if (n := nxt(q)[1]) is not None}
    out = []
    for q in sorted(sites):
        if q in linked:
            continue
        i = q - 1 if mem[q - 1] == 0x90 else q - 2
        if i < 3 or mem[i] != 0x90:
            continue
        _head, k = _ops_back(mem, i)
        a = k if mem[k] == 0x0F else (k - 1 if mem[k - 1] == 0x0F else None)
        if a is None:
            continue
        chain, cq, ok = [], q, True
        while True:
            t = base + (sites[cq] & ~1)
            if t not in idx:
                ok = False
                break
            chain.append(idx[t])
            _ops, q2, j = nxt(cq)
            if q2 is None:
                break
            cq = q2
        if not ok:
            continue
        end = cq + 2  # 마지막 조각 뒤 종결 00
        if mem[end] != 0:
            continue
        pre = mem[a - 2 : a] if a >= 2 and mem[a - 2] == 0x12 else b""
        d = ((blk + a) - (D.BUF + len(pre))) & 1
        out.append((len(out), pre + mem[a : end + 1], d, chain))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=D.DEFAULT_CUE)
    ap.add_argument("--state")
    ap.add_argument("--cap", type=int, default=2400)
    ap.add_argument("--changed", help="JSON {멤버: [줄 번호]} — 이 줄이 든 창만 찍는다(바뀐 줄만 보기). 줄열쇠는 index 열 「줄열쇠」")
    a = ap.parse_args()
    keys_for = None
    want = {}
    if a.changed:
        import json

        import dialog_labels

        want = {m: set(v) for m, v in json.load(open(a.changed, encoding="utf-8")).items()}
        keys_for = dialog_labels.labeler(a.cue)
    ch = {n: c for n, c, _p, _a in table("ed3")}
    emu = H.Emu(a.cue)
    D.boot(emu, a.state, a.cue)
    os.makedirs(a.out, exist_ok=True)
    idx = os.path.join(a.out, "index.tsv")
    if not os.path.exists(idx):
        open(idx, "w", encoding="utf-8").write("맵\t번호\t오프셋\t시퀀스\t잉크\t상태\t줄열쇠\n")
    cur = 0
    skipped = []
    for name in a.maps.split(","):
        d = os.path.join(a.out, name)
        if os.path.exists(os.path.join(d, "done")):
            continue
        if name not in ch:  # 점프 표에 없는 멤버(CM 변형 등) — 조용히 빠지지 않게 목록을 남긴다
            skipped.append(name)
            print(name, "건너뜀(점프 표에 없음)", flush=True)
            with open(os.path.join(a.out, "skipped.txt"), "a", encoding="utf-8") as f:
                f.write(name + "\n")
            continue
        cur = D.jump(emu, name, ch[name][0], cur)
        os.makedirs(d, exist_ok=True)
        snap = os.path.join(d, "_s.state")
        emu.save(snap)
        # 🔴 창은 `D.windows` — 포인터 목표가 조각 시작인 대사 창만, 번호 n = 짝 표의 창 번호. 옛 `sequences` 는 데이터 `0F 90 00 20` 같은 가짜를
        #    대사로 찍어 노이즈 창을 냈고 진짜 창을 놓쳤다(FT4300: 창 39 ↔ 옛 32 — 10-20 qa).
        wins = D.windows(emu)
        if keys_for:  # 바뀐 줄만 — 굽은 멤버 바이트에서 정적으로 창을 뽑아 그 창만 주입(런타임 블록은 입장 이벤트로 바뀌어 있을 수 있다)
            mb = keys_for.member_bytes(name)
            wins = static_windows(mb, emu.u32(D.BASE)) if mb else []
            chains_of = {k: ";".join(f"{name}#{i}" for i in ch_) for k, _sb, _al, ch_ in wins}
            wins = [(k, sb, al) for k, sb, al, ch_ in wins if want.get(name) and set(ch_) & want[name]]
        blk_changed = False
        rows = []
        for k, s, al in wins:
            off = 0
            lk = chains_of.get(k, "") if keys_for else ""
            emu.load(snap)
            emu.run(2)
            base = emu.frame.copy()
            D.inject(emu, s, al)
            b, n = V.wait_text(emu, base, cap=a.cap)
            if b is None or n <= 0:
                Image.fromarray(np.ascontiguousarray(emu.frame)).save(os.path.join(d, f"{k:03d}x.png"))
                rows.append((name, k, off, s.hex(), 0, "글자없음" if n == 0 else "창없음", lk))
                continue
            Image.fromarray(np.ascontiguousarray(emu.frame[b[0] : b[1]])).save(os.path.join(d, f"{k:03d}.png"))
            rows.append((name, k, off, s.hex(), n, "정상" + ("(블록 바뀜)" if blk_changed else ""), lk))
        os.remove(snap)
        with open(idx, "a", encoding="utf-8") as f:
            for r in rows:
                f.write("\t".join(map(str, r)) + "\n")
        open(os.path.join(d, "done"), "w").close()
        print(name, len(rows), flush=True)


if __name__ == "__main__":
    main()
