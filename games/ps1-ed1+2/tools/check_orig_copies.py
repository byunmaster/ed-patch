#!/usr/bin/env python3
"""**원판 대사 사본 검사** — 우리가 번역해 바꾼 자리 밖에 원판 일본어 바이트가 그대로 남은 사본이 있는가 (마스터 11-17).

배경: PCE I 에서 원판 디스크에 같은 대사 블록의 사본이 맵 레코드 안에 따로 있었고, 정상 진행이 그 사본을 읽어 장면 전체가
일본어로 나왔다. 빌드·게이트는 「우리가 고친 자리」만 분모로 봐서 못 잡았다. 그래서 분모를 뒤집는다 —
**원판 이미지 전체**에서 일본어(SJIS) 덩이를 뽑고, 제품 이미지에서 **바뀐** 덩이(= 번역한 자리)만 바늘로 삼아
제품 이미지 **전체**에서 바이트 검색한다. 바늘이 다른 자리에 그대로 있으면 그게 사본이다(바뀐 자리 자체엔 이미 없다).

 · 바늘 = 원판에서 SJIS 2바이트 글자(가나·한자·전각)만 이어진 덩이 중 {MINCH}자 이상이고, 제품의 같은 자리 바이트가 다른 것.
 · 사본 = 제품 이미지 어딘가(어느 섹터든)에서 그 덩이가 원판 바이트 그대로 나온 것. 서로 겹치는 같은 사본은 한 건으로 센다.
 · 기준선(`orig_copies_baseline.json`)에 있는 사본은 「읽히지 않음」을 시험 롬으로 확인한 것 — 새 사본이 늘면 실패(래칫).
   기준선 값은 `LBA:바늘 앞 8바이트 hex` 열쇠와 사유다.
 · 압축 블록은 못 본다 — 이 게임 텍스트는 평문(SCN·EXE)이라 해당 없음(압축 텍스트가 생기면 이 검사를 넓힌다).

  python3 tools/check_orig_copies.py [--kr-bin 이미지] [-v] [--freeze]
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BUILD_DIR, ORIG_BIN, ROOT

MINCH = 10  # 10자(20바이트) 이상 — 짧은 덩이(「ございます。」 류)는 우연 일치가 넘친다
BASE = os.path.join(ROOT, "orig_copies_baseline.json")
SEC, HDR, USER = 2352, 24, 2048
REASON = "원판 위치의 옛 사본 — 이동한 씬 파일의 옛 자리·오프닝/엔딩 실행파일 안(디렉터리·포인터 미참조, 정적 확인) · 시험 롬 읽힘 확인 대기"


def user_stream(path):
    a = np.fromfile(path, dtype=np.uint8)
    n = len(a) // SEC
    return np.ascontiguousarray(a[: n * SEC].reshape(n, SEC)[:, HDR : HDR + USER]).reshape(-1)


def sjis_runs(u):
    """원판 사용자 데이터에서 SJIS 2바이트 글자만 이어진 덩이 [(시작, 끝)] — 짝수·홀수 정렬을 둘 다 본다."""
    lead = ((u >= 0x81) & (u <= 0x9F)) | ((u >= 0xE0) & (u <= 0xEF))
    trail = (u >= 0x40) & (u <= 0xFC) & (u != 0x7F)
    ok = np.zeros(len(u), dtype=bool)  # 위치 i 에서 2바이트 글자가 시작하는가
    ok[:-1] = lead[:-1] & trail[1:]
    runs = []
    # 글자 시작 위치들을 2칸 간격 사슬로 잇는다: ok[i] & ok[i+2] & …
    idx = np.nonzero(ok)[0]
    if len(idx) == 0:
        return runs
    # 사슬: i 다음이 i+2 인 연속
    brk = np.nonzero(np.diff(idx) != 2)[0]
    starts = np.concatenate(([0], brk + 1))
    ends = np.concatenate((brk, [len(idx) - 1]))
    for s, e in zip(starts, ends):
        n = e - s + 1
        if n >= MINCH:
            runs.append((int(idx[s]), int(idx[e]) + 2))
    return runs


def windows8(buf, lo, hi):
    """buf[lo:hi] 각 위치의 8바이트 창 → uint64 (hi-lo 개)."""
    n = hi - lo
    w = np.zeros(n, dtype=np.uint64)
    for k in range(8):
        w |= buf[lo + k : lo + k + n].astype(np.uint64) << np.uint64(8 * k)
    return w


def scan(kr_bin):
    o = user_stream(ORIG_BIN)
    p = user_stream(kr_bin)
    if len(o) != len(p):
        raise SystemExit(f"  ❌ 안 쟀다 — 사용자 데이터 길이가 다르다({len(o)} ≠ {len(p)})")
    needles = {}  # bytes → 원판 자리 목록
    nruns = 0
    for s, e in sjis_runs(o):
        nruns += 1
        if o[s:e].tobytes() == p[s:e].tobytes():
            continue  # 안 바꾼 자리 — 번역 대상이 아니다
        needles.setdefault(o[s:e].tobytes(), []).append(s)
    keys = {}
    for nd in needles:
        keys.setdefault(int.from_bytes(nd[:8], "little"), []).append(nd)
    karr = np.array(sorted(keys), dtype=np.uint64)
    hits = []
    step = 1 << 23
    pp = np.concatenate([p, np.zeros(8, dtype=np.uint8)])
    for lo in range(0, len(p), step):
        hi = min(lo + step, len(p))
        w = windows8(pp, lo, hi)
        pos = np.nonzero(np.isin(w, karr))[0]
        for i in pos:
            off = lo + int(i)
            for nd in keys[int(w[i])]:
                if pp[off : off + len(nd)].tobytes() == nd:
                    hits.append((off, nd))
    # 같은 자리의 짧은 바늘이 긴 바늘 안에 든 중복은 가장 긴 것 하나로
    hits.sort(key=lambda h: (h[0], -len(h[1])))
    out = []
    last_end = -1
    for off, nd in hits:
        if off < last_end:
            continue
        out.append((off, nd))
        last_end = off + len(nd)
    return nruns, len(needles), out, o


def key_of(off, nd):
    return f"{off // USER}:{nd[:8].hex()}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kr-bin", default=os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin"))
    ap.add_argument("-v", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(a.kr_bin) or not os.path.exists(ORIG_BIN):
        print("  ❌ 안 쟀다 — 최종 이미지 또는 원본 이미지 없음")
        return 1
    nruns, nneed, hits, o = scan(a.kr_bin)
    base = json.load(open(BASE, encoding="utf-8")) if os.path.exists(BASE) else {}
    cur = {key_of(off, nd): off for off, nd in hits}
    new = [k for k in cur if k not in base]
    print(
        f"  원판 대사 사본 검사 [ps1-ed1+2] — 원판 일본어 덩이 {nruns} · 바뀐(번역) 바늘 {nneed} · "
        f"제품에 원판 그대로 남은 사본 {len(hits)}(기준선 {len(base)}) · 새 사본 {len(new)}"
    )
    if a.v or new:
        for off, nd in hits:
            k = key_of(off, nd)
            if a.v or k in new:
                sec = off // USER
                txt = nd.decode("cp932", "replace")[:24]
                print(f"    {'❌ 새' if k in new else '  기준선'} LBA {sec}+{off % USER} · {len(nd)}B · {txt}")
    if a.freeze:
        json.dump({k: base.get(k, REASON) for k in cur}, open(BASE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("  기준선 갱신", len(cur))
        return 0
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
