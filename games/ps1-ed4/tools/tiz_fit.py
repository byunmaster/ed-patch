"""TIZ/MAZ/MPZ 재삽입이 **원 크기 안에 들어가는가** — 측정 + 실험용 인코더(사전 없음 → 사전 있음).

    python3 tools/tiz_fit.py [--names C_845.TIZ,C_846.TIZ,…]

🔴 먼저 잰 것: **리터럴만으로(압축 없이) 담으면 원 크기를 넘는가.** 넘는다면 압축기(런 · 쌍 반복 · 사전)가 있어야 한다.
인코더는 `shared.ps1.tiz.decompress` 로 **되풀어 같은지** 검산한다(「썼다」와 「다시 읽힌다」는 다르다).
⚠ 원 압축기와 바이트 같은 출력을 목표로 하지 않는다 — 선택을 모른다. 기준은 「풀면 같은가」와 「크기」다.
공용으로 올릴지는 재삽입이 실제로 필요한 그림이 정해진 뒤에 본다(둘째 소비자 없음 — YAGNI).
"""

import argparse
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

from shared.ps1 import gmf_arc, tiz

HEAD = tiz.STREAM_MIN  # 134 = 6 + 사전 표 128


def literal_only_size(n):
    """압축 없이 리터럴 런만으로 담은 크기 — 머리·빈 사전 표 + (op 1B + ≤64B)."""
    return HEAD + n + (n + 63) // 64


def encode_plain(raw, kind=1):
    """런(바이트 반복) · 쌍 반복 · 리터럴 — 사전 없음. 항상 `tiz.decompress` 로 풀린다."""
    out = bytearray()
    i, n = 0, len(raw)
    lit = bytearray()

    def flush():
        nonlocal lit, out
        while lit:
            k = min(len(lit), 64)
            out.append(0x80 | (k - 1))
            out += lit[:k]
            lit = lit[k:]

    while i < n:
        j = i
        while j < n and raw[j] == raw[i] and j - i < 64:
            j += 1
        run = j - i
        pj = i
        if i + 4 <= n:
            pair = raw[i : i + 2]
            pj = i
            while pj + 2 <= n and raw[pj : pj + 2] == pair and (pj - i) // 2 < 64:
                pj += 2
        prun = (pj - i) // 2 if pj > i else 0
        if run >= 3 and run * 1 >= prun * 2:
            flush()
            out += bytes([run - 1, raw[i]])
            i = j
        elif prun >= 2:
            flush()
            out += bytes([0x40 | (prun - 1)]) + raw[i : i + 2]
            i = pj
        else:
            lit.append(raw[i])
            i += 1
    flush()
    return bytes([kind, 3]) + struct.pack("<I", n) + b"\x00" * 128 + bytes(out)


def encode_dict(raw, kind=1):
    """`encode_plain` + 사전 64 — 자주 나오는 2~15바이트 조각을 골라(절약량 순) `C0~FF` 로 참조한다(탐욕, 실험용)."""
    n = len(raw)
    cand = collections.Counter()
    for L in (15, 12, 10, 8, 6, 5, 4):
        for i in range(0, n - L, 1):
            seg = raw[i : i + L]
            if len(set(seg)) > 1 and not (seg[0] == seg[1] == seg[2]):
                cand[seg] += 1
    scored = sorted(
        ((c - 1) * len(s) - len(s) - 2 for s, c in cand.items() if c > 1),
        reverse=True,
    )
    picked = []
    for seg, c in sorted(cand.items(), key=lambda kv: -((kv[1] - 1) * len(kv[0]) - len(kv[0]) - 2)):
        if len(picked) >= 64 or c < 2 or (c - 1) * len(seg) - len(seg) - 2 <= 0:
            continue
        if any(seg in p or p in seg for p in picked):
            continue
        picked.append(seg)
    del scored
    if not picked:
        return encode_plain(raw, kind)
    # 사전 표 + 바이트열
    ent, blob, pos = [0] * 64, b"", HEAD
    for k, s in enumerate(picked):
        ent[k] = (len(s) << 12) | pos
        pos += len(s)
        blob += s
    # 스트림: 위치마다 가장 긴 사전 일치를 쓰고, 아니면 plain 규칙
    out = bytearray()
    i = 0
    lit = bytearray()

    def flush():
        nonlocal lit, out
        while lit:
            k = min(len(lit), 64)
            out.append(0x80 | (k - 1))
            out += lit[:k]
            lit = lit[k:]

    by_first = collections.defaultdict(list)
    for k, s in enumerate(picked):
        by_first[s[0]].append((len(s), k, s))
    for v in by_first.values():
        v.sort(reverse=True)
    while i < n:
        hit = next(
            ((k, s) for _l, k, s in by_first.get(raw[i], ()) if raw[i : i + len(s)] == s), None
        )
        j = i
        while j < n and raw[j] == raw[i] and j - i < 64:
            j += 1
        if hit and (j - i < 3 or len(hit[1]) > 2):
            flush()
            out.append(0xC0 | hit[0])
            i += len(hit[1])
        elif j - i >= 3:
            flush()
            out += bytes([j - i - 1, raw[i]])
            i = j
        else:
            lit.append(raw[i])
            i += 1
    flush()
    head = bytes([kind, 3]) + struct.pack("<I", n) + struct.pack("<64H", *ent)
    return head + blob + bytes(out)


def iter_blocks():
    with common.open_disc() as d:
        seen = set()
        for path, lba, size in d.files():
            if "/SC" not in path or not path.endswith(common.ARCHIVE_EXT) or size < 64:
                continue
            data = d.read_extent(lba, size)
            try:
                _, ents = gmf_arc.arc_parse(data)
            except gmf_arc.ArchiveError:
                continue
            for nm, off, sz in ents:
                if nm.endswith((".TIZ", ".MAZ", ".MPZ")):
                    base = nm.split("\\")[-1]
                    if base in seen:
                        continue
                    seen.add(base)
                    yield path, base, data[off : off + sz]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", default="")
    a = ap.parse_args()
    want = set(filter(None, a.names.split(",")))
    common.verify_source()
    tot = collections.Counter()
    rows = []
    for _path, base, blk in iter_blocks():
        if want and base not in want:
            continue
        raw = tiz.decompress(blk)
        lit = literal_only_size(len(raw))
        plain = encode_plain(raw)
        assert tiz.decompress(plain) == raw, base
        dic = encode_dict(raw)
        assert tiz.decompress(dic) == raw, base
        best = min(len(plain), len(dic))
        tot["n"] += 1
        tot["lit_over"] += lit > len(blk)
        tot["plain_over"] += len(plain) > len(blk)
        tot["best_over"] += best > len(blk)
        tot["orig"] += len(blk)
        tot["lit"] += lit
        tot["plain"] += len(plain)
        tot["best"] += best
        rows.append((base, len(raw), len(blk), lit, len(plain), len(dic)))
    n = tot["n"]
    print(
        f"고유 {n}개 (TIZ·MAZ·MPZ) — 원 압축 합 {tot['orig']:,}B\n"
        f"  리터럴만      합 {tot['lit']:,}B · 원 크기 초과 {tot['lit_over']}/{n}\n"
        f"  런·쌍(사전X)  합 {tot['plain']:,}B · 원 크기 초과 {tot['plain_over']}/{n}\n"
        f"  + 사전        합 {tot['best']:,}B(둘 중 작은 쪽) · 원 크기 초과 {tot['best_over']}/{n}"
    )
    for r in rows:
        if want or r[0] in (
            "C_845.TIZ",
            "C_846.TIZ",
            "C_840.TIZ",
            "C_847.TIZ",
            "C_857.TIZ",
            "C_844.TIZ",
            "WMAP_0.TIZ",
        ):
            print(
                f"  {r[0]:8s} 푼 {r[1]:6,} · 원 {r[2]:6,} · 리터럴 {r[3]:6,} · 런·쌍 {r[4]:6,} · +사전 {r[5]:6,}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
