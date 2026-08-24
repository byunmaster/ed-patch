"""문안을 이미지에 써 넣는다 — **길이 보존**.

    python3 games/ss-ed3/tools/reinsert.py --check    # 계약만 본다(안 쓴다)

블록 길이를 안 바꾼다(`docs/status.md` 5절). 모자란 바이트는 `typeset.pad_to_budget` 이
줄 끝 공백으로 채우고, **길이가 1바이트라도 달라지면 곧바로 운다.**

번역 정본은 `games/ss-ed3/script/<맵>.json` — 키는 블록 색인, 값은 우리 문안이다.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
import common as C
import hangul_map as H
import mapfile as M
import typeset as T

SCRIPT_DIR = os.path.join(C.GAME_DIR, "script")


def load_script(stem):
    p = os.path.join(SCRIPT_DIR, f"{stem}.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def fit(text, budget):
    """우리 문안을 원문 바이트 예산에 맞춘다 — `(맞춘 문안, 사유)`."""
    if T.overflows(text):
        return None, "창 계약을 넘는다(17×3)"
    out = T.pad_to_budget(text, budget)
    if out is None:
        out = T.pad_to_budget(text, budget, keep_last=False)
    if out is None:
        have = T.body_bytes(text)
        return None, f"예산 {budget}B 에 못 맞춘다(문안 {have}B)"
    return out, None


def patch_blocks(data, stem, table):
    """`(새 bytes, 넣은 수, [(블록, 사유)])` — 길이 불변."""
    script = load_script(stem)
    if not script:
        return data, 0, []
    blocks = M.blocks(data)
    out = bytearray(data)
    done = 0
    bad = []
    for key, kr in script.items():
        i = int(key)
        if not 0 <= i < len(blocks):
            bad.append((key, f"블록 색인이 범위 밖({len(blocks)})"))
            continue
        blk = blocks[i]
        budget = len(blk["body"])
        fitted, why = fit(kr, budget)
        if fitted is None:
            bad.append((key, why))
            continue
        raw = H.encode_kr(fitted, table)
        if len(raw) != budget:
            bad.append((key, f"길이가 변했다 {len(raw)} != {budget}"))
            continue
        out[blk["off"] : blk["off"] + budget] = raw
        done += 1
    return bytes(out), done, bad


def main():
    check = "--check" in sys.argv
    table = H.load()
    total = done = 0
    bad = []
    with C.open_disc(1) as d:
        for n, lba, size in d.files():
            if not (n.startswith("/MAP/") and n.endswith(".BIN")):
                continue
            stem = os.path.basename(n).rsplit(".", 1)[0]
            if not load_script(stem):
                continue
            b = d.read_extent(lba, size)
            _, k, err = patch_blocks(b, stem, table)
            total += len(load_script(stem))
            done += k
            bad += [(f"{stem}[{i}]", w) for i, w in err]
    print(f"문안 {total}  넣음 {done}  실패 {len(bad)}" + ("  (검사만)" if check else ""))
    for k, w in bad[:10]:
        print(f"  ❌ {k} — {w}")
    if bad:
        raise SystemExit(1)
    print("✅ 전부 길이 보존으로 들어간다")


if __name__ == "__main__":
    main()
