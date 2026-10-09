"""글리프 비트맵을 찾는다 — **코드표를 자로 쓴다.**

표가 「JIS 순서에서 쓰는 글자만」이므로 **글리프도 같은 순서**로 놓여 있을 것이다.
그러면 코드 c 의 글리프가 어떤 글자인지 이미 알고, 그 글자의 **잉크량**(켜진 비트 수)을
다른 12×12 폰트(새턴 ED3 `KANJI12.FON`)에서 가져올 수 있다.

⇒ 후보 (오프셋 O, 보폭 S) 마다 「코드순 잉크량 수열」을 뽑아 기준과 **상관**을 재면,
   진짜 폰트만 0.8 이상이 나온다. 밀도·연속성 같은 일반 휴리스틱은 그림 데이터에도
   걸려 잡음이 2,600건이었다(2026-09-03 실측) — 이 자는 안 그렇다.
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import textenc

SATURN_FON = os.path.join(
    common.main_repo(),
    ".claude",
    "worktrees",
    "ss-ed3",
    "games",
    "ss-ed3",
    "work",
    "derived",
    "KANJI12.FON",
)
SAT_STRIDE, SAT_W, SAT_H = 18, 12, 12
POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.int32)


def saturn_ink():
    """{글자: 잉크량} — 새턴 12×12 폰트에서. 색인은 (구−1)×94 + (점−1) JIS 순차."""
    raw = open(SATURN_FON, "rb").read()
    arr = np.frombuffer(raw, dtype=np.uint8)
    n = len(raw) // SAT_STRIDE
    ink = POPCOUNT[arr[: n * SAT_STRIDE].reshape(n, SAT_STRIDE)].sum(axis=1)
    out = {}
    for ku in range(1, 95):
        for ten in range(1, 95):
            ch = textenc.kuten_char(ku, ten)
            if ch is None:
                continue
            i = (ku - 1) * 94 + (ten - 1)
            if i < n:
                out[ch] = int(ink[i])
    return out


def reference_jis(lo=0, hi=None):
    """(색인 배열, 기준 잉크량) — **JIS 순차** 배치를 가정한 기준.

    ⚠ 「글리프 순서 = 코드 순서」는 가정이다. 같은 개발사(GMF)의 PS1 ED1+2 는 폰트가
      **JIS 순차**이고 코드 변환은 런타임에 한다(`games/ps1-ed1+2/tools/font_map.py`).
      그래서 두 가정을 다 훑는다 — 안 그러면 있는 폰트를 「없다」고 결론 낸다.
    """
    ink = saturn_ink()
    order = textenc.jis_order()
    hi = hi or len(order)
    idx, vals = [], []
    for i in range(lo, min(hi, len(order))):
        ch = order[i]
        if ch in ink:
            idx.append(i - lo)
            vals.append(ink[ch])
    return np.array(idx, dtype=np.int64), np.array(vals, dtype=np.float64)


def reference(disc, lo=0x3F, hi=0x800):
    """(코드 배열, 기준 잉크량 배열) — 표에 있고 기준 폰트에도 있는 코드만."""
    ink = saturn_ink()
    m = textenc.charmap(disc)
    codes, vals = [], []
    for c in range(lo, hi):
        ch = m.get(c)
        if ch and ch in ink:
            codes.append(c)
            vals.append(ink[ch])
    return np.array(codes, dtype=np.int64), np.array(vals, dtype=np.float64)


def scan(path, codes, ref, strides, step=2, min_corr=0.55, chunk=1 << 15, bpp=1):
    """⚠ 잉크를 재는 자가 bpp 마다 다르다 — 1bpp 는 켜진 **비트** 수, 4bpp 는 **농도 합**이다.
    4bpp 폰트(안티에일리어싱)를 1bpp 자로 재면 상관이 안 선다."""
    raw = np.frombuffer(open(path, "rb").read(), dtype=np.uint8)
    weight = POPCOUNT[raw] if bpp == 1 else ((raw >> 4) + (raw & 0xF))
    cum = np.concatenate([[0], np.cumsum(weight.astype(np.int64))])
    ref_c = ref - ref.mean()
    ref_n = np.sqrt((ref_c**2).sum())
    hits = []
    for S in strides:
        need = int(codes[-1] + 1) * S
        if need >= len(raw):
            continue
        starts = np.arange(0, len(raw) - need, step, dtype=np.int64)
        for i in range(0, len(starts), chunk):
            base = starts[i : i + chunk][:, None]  # (B,1)
            a = base + codes[None, :] * S
            ink = (cum[a + S] - cum[a]).astype(np.float64)  # (B, N)
            c = ink - ink.mean(axis=1, keepdims=True)
            n = np.sqrt((c**2).sum(axis=1))
            with np.errstate(invalid="ignore", divide="ignore"):
                corr = (c @ ref_c) / (n * ref_n)
            good = np.nonzero(corr > min_corr)[0]
            for g in good:
                hits.append((float(corr[g]), int(base[g, 0]), S))
    hits.sort(reverse=True)
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--strides", default="16,18,24,32,36,48,72,128")
    ap.add_argument("--step", type=int, default=2)
    ap.add_argument("--min-corr", type=float, default=0.55)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--order", choices=("code", "jis"), default="code")
    ap.add_argument("--bpp", type=int, choices=(1, 4), default=1)
    ap.add_argument("--jis-from", type=int, default=1410, help="JIS 순차 기준의 시작 색인(1410=亜)")
    ap.add_argument("--jis-n", type=int, default=1200)
    a = ap.parse_args()
    if a.order == "jis":
        codes, ref = reference_jis(a.jis_from, a.jis_from + a.jis_n)
        print(f"기준: JIS 순차 (색인 {a.jis_from}~ , 표본 {len(codes):,})")
    else:
        codes, ref = reference(a.disc)
        print(f"기준: 코드 순서 (표본 {len(codes):,}자)")
    strides = [int(s) for s in a.strides.split(",")]
    for p in a.paths:
        hits = scan(p, codes, ref, strides, a.step, a.min_corr, bpp=a.bpp)
        print(f"== {os.path.basename(p)}  후보 {len(hits)}")
        seen = set()
        for corr, off, S in hits:
            key = (S, off // (S * 8))
            if key in seen:
                continue
            seen.add(key)
            print(f"   corr={corr:.3f}  off=0x{off:06X}  stride={S}")
            if len(seen) >= a.top:
                break


if __name__ == "__main__":
    main()
