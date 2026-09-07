"""우리 문안 ↔ **DOS 정발 대사**를 짝지어 뜻이 갈린 자리를 뽑는다.

역번역(`backtrans.py`)이 「우리 문안 → 일본어 → 원문」으로 재는 것과 **다른 축**이다.
여기서는 **같은 원문을 옮긴 남의 한국어**와 맞춘다 — 뜻은 맞는데 **뉘앙스가 다른** 자리,
그리고 우리가 **놓친 어감**이 여기서 드러난다.

🔴 **정발은 기준이 아니다**(게임 `CLAUDE.md`). 이건 **검토 자료**지 저본이 아니다 —
DOS 판은 이식이라 잘린 대사·바뀐 대사가 있고, 옛 번역이라 오역도 있다.
**다르면 다시 읽어 보라는 신호**일 뿐, 정발을 따라가는 도구가 아니다.

짝은 **글자 2-gram TF-IDF 코사인**으로 찾는다. 같은 원문을 옮긴 두 한국어는 고유명사와
숫자를 공유해서 이게 잘 붙는다(실측: 이름 줄은 1.00, 대사는 0.4~0.7).

    python3 tools/compare_dos.py MAP016          # 한 맵
    python3 tools/compare_dos.py                 # 옮긴 맵 전부
    python3 tools/compare_dos.py MAP016 --show 60

⚠ 뽑히는 것은 **원저작물**이다. 화면으로만 보고 `work/review/` 밖으로 내보내지 않는다
(루트 「저작권」). 네트워크가 안 드니 손으로 돌린다 — 게이트가 아니다.
"""

import argparse
import collections
import glob
import json
import math
import os
import re

import common as C

KO = re.compile(r"[가-힣]")
KEEP = re.compile(r"[^가-힣0-9]")
DOS_DIR = os.path.join(C.ROOT, "originals", "kr", "dos-ed3")
#   ⚠ 너무 흔한 조각은 후보를 수만 개로 부풀리기만 한다 — 점수에도 거의 기여하지 않는다.
COMMON_DF = 400


def dos_lines():
    """정발 `.DAT` 에서 한국어 줄만. 제어 바이트가 곧 줄 경계다(평문 EUC-KR)."""
    out = []
    for f in sorted(glob.glob(os.path.join(DOS_DIR, "ED3_DT0*.DAT"))):
        with open(f, "rb") as fh:
            b = fh.read()
        cur = []
        for x in b:
            if 32 <= x < 127 or x >= 0xA1:
                cur.append(x)
                continue
            if cur:
                try:
                    t = bytes(cur).decode("cp949").strip()
                except UnicodeDecodeError:
                    t = ""
                if len(KO.findall(t)) >= 2:
                    out.append(t)
            cur = []
    return out


class Index:
    """2-gram TF-IDF 역색인. 3.9만 줄에 1 초쯤 걸린다."""

    def __init__(self, lines):
        self.L = lines
        self.G = [self._g(x) for x in lines]
        self.idx = collections.defaultdict(list)
        for i, g in enumerate(self.G):
            for k in g:
                self.idx[k].append(i)
        self.df = {k: len(v) for k, v in self.idx.items()}
        self.N = len(lines) or 1
        self.nrm = [math.sqrt(sum(v * v for v in self._v(g).values())) or 1.0 for g in self.G]

    @staticmethod
    def _g(s):
        s = KEEP.sub("", s)
        return collections.Counter(s[i : i + 2] for i in range(len(s) - 1)) or collections.Counter(
            s
        )

    def _v(self, g):
        return {
            k: (1 + math.log(v)) * math.log(self.N / (1 + self.df.get(k, 1))) for k, v in g.items()
        }

    def best(self, q):
        vq = self._v(self._g(q))
        nq = math.sqrt(sum(v * v for v in vq.values())) or 1.0
        sc = collections.defaultdict(float)
        for k, w in vq.items():
            d = self.df.get(k, 0)
            if d == 0 or d > COMMON_DF:  # 정발에 없는 조각은 후보를 못 준다
                continue
            wk = math.log(self.N / (1 + d))
            for i in self.idx[k]:
                gv = self.G[i].get(k, 0)
                if gv:
                    sc[i] += w * (1 + math.log(gv)) * wk
        if not sc:
            return 0.0, ""
        i, v = max(sc.items(), key=lambda kv: kv[1] / self.nrm[kv[0]])
        return v / (nq * self.nrm[i]), self.L[i]


_NEG = re.compile(r"안\s|못\s|없|말고|마라|아니|않")
_NUM = re.compile(r"[0-9０-９]+")


def _diverge(a, b):
    """두 문안이 **다른 말을 하고 있나** — 부정 · 숫자 · 물음이 한쪽에만 있으면 그렇다.

    ⚠ 표현 차이(어미·존대·낱말 선택)는 걸러 낸다. 그건 우리가 **일부러** 다르게 쓴 것이고
    (정발은 기준이 아니다), 만 줄을 넘어 사람이 못 본다.
    """
    return (
        bool(_NEG.search(a)) != bool(_NEG.search(b))
        or _NUM.findall(a) != _NUM.findall(b)
        or ("?" in a) != ("?" in b)
    )


def our_lines(stem):
    """`(블록, 우리 줄)` — 제어코드로 자른다(정발 쪽 줄 경계와 결이 같다)."""
    p = os.path.join(C.GAME_DIR, "script", f"{stem}.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    out = []
    for k, v in d.items():
        if not (k.isdigit() and isinstance(v, str)):
            continue
        for ln in re.split(r"[\n\f]", v):
            ln = ln.strip()
            if len(KO.findall(ln)) >= 4:  # 「응.」 같은 건 아무 데나 붙는다
                out.append((k, ln))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stem", nargs="?", help="MAP016 (없으면 옮긴 맵 전부)")
    #   ⚠ 아주 낮으면 **짝이 틀린 것**이고 아주 높으면 **볼 것이 없다**(거의 같은 문장).
    #   쓸모 있는 자리는 「같은 대사인 게 분명한데 표현이 다른」 가운데 띠다.
    ap.add_argument("--lo", type=float, default=0.45, help="이보다 낮으면 짝이 틀렸다고 본다")
    ap.add_argument("--hi", type=float, default=0.80, help="이보다 높으면 거의 같은 문장이라 뺀다")
    ap.add_argument("--show", type=int, default=40)
    #   🔴 띠 안이 만 줄을 넘어 사람이 못 본다(실측 16,352). 대부분은 **뜻은 같고 표현만
    #     다른** 것이라 볼 값이 없다. `--diverge` 는 **뜻이 갈릴 만한 신호**만 남긴다 —
    #     부정 · 숫자 · 물음. 셋 다 한쪽에만 있으면 문장이 다른 말을 하고 있다는 뜻이다.
    ap.add_argument("--diverge", action="store_true", help="뜻이 갈릴 만한 자리만")
    a = ap.parse_args()

    stems = (
        [a.stem]
        if a.stem
        else sorted(
            os.path.basename(p)[:-5]
            for p in glob.glob(os.path.join(C.GAME_DIR, "script", "MAP*.json"))
        )
    )
    ix = Index(dos_lines())
    print(f"정발 {len(ix.L):,} 줄 · 대조 {len(stems)} 맵")

    pairs, miss, n, found = [], 0, 0, 0
    for s in stems:
        for blk, ln in our_lines(s):
            n += 1
            sc, hit = ix.best(ln)
            if a.diverge and sc >= a.lo and not _diverge(ln, hit):
                found += 1
                continue
            if sc >= a.lo:
                found += 1
                if sc <= a.hi:
                    pairs.append((sc, s, blk, ln, hit))
            else:
                miss += 1

    pairs.sort(reverse=True)
    print(f"\n짝 찾음 {found} / {n} 줄 ({found / max(n, 1):.0%}) · 못 찾음 {miss}")
    print(f"그중 볼 것 {len(pairs)} — 점수 {a.lo}~{a.hi} 띠(같은 대사인 게 분명한데 표현이 다르다)")
    print("⚠ 다르다고 틀린 게 아니다. **정발은 기준이 아니라 검토 자료**다.\n")
    for sc, s, blk, ln, hit in pairs[: a.show]:
        print(f"  [{sc:.2f}] {s}:{blk}")
        print(f"    우리 {ln}")
        print(f"    정발 {hit}")
    if len(pairs) > a.show:
        print(f"\n… {len(pairs) - a.show} 개 더 — `--show` 로 늘린다")


if __name__ == "__main__":
    main()
