#!/usr/bin/env python3
"""원문 사본 게이트 — 우리가 번역해 바꾼 **대본 멤버 밖**의 이미지 어디에 원판 대사 바이트가 그대로 남았나.

    python3 tools/check_image_copies.py --built <빌드 이미지.bin> [--orig <원본.bin>] [--freeze]

왜(PCE I 사고, 관리자 11-17): 원판 디스크에 대사 블록 **사본**이 우리가 고친 자리 밖(맵별 레코드 안)에 따로 있었고, 정상 진행이 그 사본을 읽어
장면 전체가 원문으로 나왔다. 빌드·게이트는 고친 자리만 분모로 봐서 못 잡았다. `check_image_residue` 도 같은 멤버의 같은 자리만 비교한다.
그래서 **이미지 전체**에서 찾는다: 원본 대본 멤버의 텍스트 런에서 `N` 코드 창을 뽑아(16비트 코드 · 짝수·홀수 정렬 둘 다) 구운 이미지의 **모든 파일**
(대본 멤버 `..\\DATA\\*.BIN` 은 빼고 — 그쪽은 `check_image_residue` 몫이다) 바이트와 맞대고, 그대로 남은 창이 든 파일·런 수를 센다.
기준선 `image_copies_baseline.json`(파일 → 런 수)보다 **늘면 실패**, 줄면 `--freeze`. 기준선 값은 「읽히지 않는다고 확인한 알려진 사본」이다.
⚠ 압축된 사본은 바이트로 못 찾는다 — 압축 덩어리는 `check_exe_jp_left`·화면 일본어 게이트 몫이다.
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import dump_script
from check_image_residue import TEXT_MEMBER, members

N = 5  # 코드 수 — 원문 5코드 연속(check_image_residue 와 같다). 이미지 전체에서 우연히 맞을 확률은 무시할 만하다(15비트^5)
MUL = np.uint64(1000003)
MIN_DISTINCT = 3  # 한 창에 서로 다른 코드가 이만큼은 있어야 글이다 — 「えぇぇぇぇ」 같은 반복은 그림 데이터와 우연히 맞는다(실측: 엔딩 그림 파일 넷)


def _window_ok(w):
    """창이 글자 대역에 있고 반복이 아닌가."""
    return all(dump_script.KANA_LO <= x < 0x8000 for x in w) and len(set(w)) >= MIN_DISTINCT


BASELINE = os.path.join(common.ROOT, "image_copies_baseline.json")


def hashes(a):
    """uint16 배열 → 길이 len-N+1 의 uint64 창 해시(오버플로 래핑 허용)."""
    m = len(a) - N + 1
    if m <= 0:
        return np.zeros(0, dtype=np.uint64)
    h = a[:m].astype(np.uint64)
    for k in range(1, N):
        h = h * MUL + a[k : k + m].astype(np.uint64)
    return h


def orig_hashes(orig_bin):
    """원본 대본 멤버 텍스트 런의 N 코드 창 해시 집합(정렬 배열)."""
    out = []
    for blob in members(orig_bin).values():
        for _, c in dump_script.runs_of(blob):
            if not dump_script.is_text(c):
                continue
            ws = [i for i in range(len(c) - N + 1) if _window_ok(c[i : i + N])]
            if ws:
                a = np.asarray(c, dtype=np.uint16)
                h = hashes(a)
                out.append(h[ws])
    return np.unique(np.concatenate(out)) if out else np.zeros(0, dtype=np.uint64)


def scan_file(data, grams):
    """한 파일 바이트에서 원문 창이 그대로 남은 런 수(연속한 창은 한 런)."""
    best = 0
    for par in (0, 1):
        b = data[par : len(data) - ((len(data) - par) & 1)]
        if len(b) < 2 * N:
            continue
        a = np.frombuffer(b, dtype="<u2")
        h = hashes(a)
        idx = np.nonzero(np.isin(h, grams))[0]
        idx = [i for i in idx if _window_ok([int(x) for x in a[i : i + N]])]
        runs = 0
        prev = -10
        for i in idx:
            if i - prev > 1:
                runs += 1
            prev = i
        best = max(best, runs)
    return best


def mask_text_members(path, data):
    """`SCE*/SC*.DAT` 의 대본 멤버 범위를 0 으로 민다(그쪽은 check_image_residue 몫)."""
    if not (path.startswith("/SCE") and path.endswith(".DAT")):
        return data
    try:
        ents = common.arc_members(data)
    except common.ArchiveError:
        return data
    buf = bytearray(data)
    for nm, (off, sz) in ents.items():
        if nm.startswith("..") and TEXT_MEMBER in nm:
            buf[off : off + sz] = bytes(sz)
    return bytes(buf)


def scan(built, orig=None):
    grams = orig_hashes(orig or common.orig_bin("ed3"))
    files = common.iso_tree(built)[0]
    found = {}
    for path, (lba, size) in sorted(files.items()):
        if size < 2 * N:
            continue
        data = mask_text_members(path, common.read_lba("ed3", lba, size, path=built))
        n = scan_file(data, grams)
        if n:
            found[path] = n
    return found


def load_baseline():
    if not os.path.exists(BASELINE):
        return {}
    with open(BASELINE, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--built", required=True)
    ap.add_argument("--orig")
    ap.add_argument("--freeze", action="store_true")
    a = ap.parse_args()
    found = scan(a.built, a.orig)
    base = load_baseline()
    print(
        f"  원문 사본(대본 멤버 밖 · {N}코드 창): 파일 {len(found)}개 · 런 {sum(found.values()):,}개 · 기준선 {sum(base.values()):,}개"
    )
    for k, v in sorted(found.items(), key=lambda x: -x[1])[:15]:
        print(f"    {k}: {v}")
    if a.freeze:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(found.items())), f, ensure_ascii=False, indent=1)
            f.write("\n")
        print("  기준선 갱신")
        return 0
    up = [
        f"{k}: {v} > 기준선 {base.get(k, 0)}"
        for k, v in sorted(found.items())
        if v > base.get(k, 0)
    ]
    if up:
        print("🔴 대본 멤버 밖에 원문 사본이 남았다:\n  " + "\n  ".join(up[:20]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
