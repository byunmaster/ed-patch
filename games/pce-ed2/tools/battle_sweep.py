"""전 몬스터 전투 문구 촬영(마스터 10-19 밤샘 검수) — 슬라임 전투의 덩이 자리에 몬스터 하나의 실제 줄을 바꿔 넣고 실제 전투 로그 창으로 찍는다.

    python3 battle_sweep.py --iso <디버그 이미지> --out <폴더> [--budget 1100] [--only 386]
한 번에(전투 하나) = 나타남 줄 하나 + 이름 줄 + 행동 줄 하나(같은 몬스터 덩이의 줄). 덩이의 줄을 다 보이도록 나타남·행동을 돌려 가며 전투를 여러 번 돈다.
산출: `<out>/<rel>_<덩이>_<번호>_<쪽>.png`(로그 창 부근) · `index.tsv`(파일 · 덩이 · 나타남 줄 · 이름 줄 · 행동 줄) · `done.txt`(끝낸 전투 — 이어 돈다).
⚠ 가짜 부류(덩이 교체) — `battleview.py` 머리말.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle
import battleview as bv
import common
import package
import pcehl
import pceview

RELS = [386, 514, 642, 770, 898, 1026, 1154, 1282, 1410, 1538, 1666, 1794, 2690]


def kind(i: int, l: bytes, o: bytes = b"") -> str:
    """줄 종류 — 원문(o)으로 가른다: 나타남(「が現れた」 · `16` 이름 상자가 낀 줄) · 이름 라벨(`06…04` 로 감싼 이름 + 구별 문자 — A' A" 꼴 포함) · 행동(`1B`) · 그 밖."""
    if not l:
        return "empty"
    if l[:1] == b"\x1b":
        return "act"
    if b"\x16" in l or (o and battle.APPEAR in battle._plain(o)):
        return "appear"
    if o and b"\x06" in o and b"\x04" in o and b"\x12" not in o and b"\x1b" not in o:
        return "name"
    if l[-1:] in (b"A", b"B", b"C", b"D"):
        return "name"
    if i == 0 or l[-1:] == b"\x12":
        return "appear"
    return "other"


def fights(iso: str, only: set[int] | None, chunks: set[tuple[int, int]] | None = None):
    for rel in RELS:
        if only and rel not in only:
            continue
        orig = bytes(common.track_data(rel, 128))
        fin = pceview.iso_pkg(iso, rel)
        _, ot = package.msg_table(orig)
        _, ft = package.msg_table(fin)
        fch = dict(package.chunks(fin))
        gl = fin[ft[0] : ft[0] + 16 * 255]
        for a, b in package.chunks(orig):
            if orig[a : a + 8] == package.SENTINEL:
                continue
            d = package.decode_chunk(orig, a, b)[0]
            if not battle.is_battle_chunk(d):
                continue
            if chunks and (rel, a) not in chunks:
                continue
            fs = ft[ot.index(a)]
            L = package.decode_chunk(fin, fs, fch[fs])[0].split(b"\x00")
            Oraw = package.decode_chunk(orig, a, b)[0].split(b"\x00")
            K = [kind(i, l, Oraw[i] if i < len(Oraw) else b"") for i, l in enumerate(L)]
            ap = [i for i, k in enumerate(K) if k == "appear"] or [0]
            nm = [i for i, k in enumerate(K) if k == "name"]
            ac = [i for i, k in enumerate(K) if k in ("act", "other")]
            if not nm:  # 이름 줄이 없는 덩이(보스 등) — 행동 줄 앞 이름 자리는 비운다
                nm = [None]
            n = max(len(ap), len(ac), 1)
            for j in range(n):
                i_ap = ap[j % len(ap)]
                i_ac = ac[j % len(ac)] if ac else None
                i_nm = nm[j % len(nm)]
                nb = L[i_nm] if i_nm is not None else b""
                act = L[i_ac] if i_ac is not None else b""
                lines5 = [L[i_ap], nb, act, b"", act]  # 이름B 자리는 비운다 — `07`(대상 이름)이 엔진이 채우는 아군 이름(아트라스)으로 나온다(원판 롬 같은 교체 실측)
                yield f"{rel}_{a}_{j:02d}", f"{rel}:{a}", (i_ap, i_nm, i_ac), lines5, gl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bram", default="/root/save/pce-ed2/ed2.sav")
    ap.add_argument("--budget", type=int, default=1100)
    ap.add_argument("--only", type=int, nargs="*")
    ap.add_argument("--chunks", nargs="*", help="`rel:덩이` 만(고친 덩이 재촬영)")
    ap.add_argument("--frames", type=int, default=1500)
    ap.add_argument("--cue", help="에뮬용 cue(기본: 이미지 옆 같은 이름)")
    ap.add_argument("--allow-stale", action="store_true", help="롬 소스 지문이 지금 소스와 달라도 찍는다")
    a = ap.parse_args()
    import romtag

    desc = romtag.check(a.iso, a.allow_stale)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "rom.txt", "a") as f:
        f.write(desc + "\n")
    work = out / "_work"
    work.mkdir(exist_ok=True)
    done_f = out / "done.txt"
    done = set(done_f.read_text().split()) if done_f.exists() else set()
    cue = a.cue or str(Path(a.iso).with_suffix(".cue"))
    pre = work / "pre.state"
    e = bv.to_encounter(cue, a.bram, str(pre))
    st = pre.read_bytes()
    t0 = time.time()
    n = 0
    for gid, key, idx, lines5, gl in fights(a.iso, set(a.only) if a.only else None, {tuple(int(x) for x in c.split(":")) for c in a.chunks} if a.chunks else None):
        if gid in done:
            continue
        if time.time() - t0 > a.budget:
            print(f"예산 {a.budget}s 소진 — 전투 {n}, 이어서 다시 돌린다")
            return 3
        shots = bv.fight(e, st, bv.synth_chunk(lines5), gl, out, gid, frames=a.frames, step=10)
        with open(out / "index.tsv", "a") as f:
            f.write(f"{gid}\t{key}\t{idx[0]}\t{idx[1]}\t{idx[2]}\t{len(shots)}\n")
        with open(done_f, "a") as f:
            f.write(gid + "\n")
        n += 1
        print(gid, key, idx, len(shots), flush=True)
    print(f"끝 — 전투 {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
