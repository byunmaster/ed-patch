#!/usr/bin/env python3
"""**원판 사본 잔존 감사** — 우리가 번역해 바꾼 원판 바이트(평문 일본어 · 압축 블록 포함)가 제품 이미지 **다른 자리에 원판 그대로 남았나**.

    python3 games/ss-ed3/tools/check_orig_copies.py            # 감사(선언 밖 사본 → rc 1)
    python3 games/ss-ed3/tools/check_orig_copies.py --list     # 전부 보여 준다

🔴 왜(PCE I 실측 11-17): 원판 디스크에 대사 블록 **사본**이 우리가 고친 자리 밖(맵별 레코드 안)에 따로 있었고, 정상 진행이 그 사본을 읽어
   2장 장면 전체가 일본어 원문으로 나왔다. 빌드·게이트는 「고친 자리」만 분모로 봐서 못 잡는다 — 이 검사는 **분모를 이미지 전체로** 잡는다.
   방법: `build.patched()` 의 (원본, 새것) 쌍에서 ① 바뀐 바이트 구간(길이가 같은 파일) ② 새것에 없는 원본의 SJIS 글 덩이(12바이트↑)를 뽑아,
   그 **원판 바이트**를 제품 트랙 1 전체(사용자 데이터)에서 찾는다. 나오면 그 자리가 어느 파일인지 적는다(옮긴 파일의 옛 자리는 가린다).
   옮긴 파일의 **옛 자리**(원본 바이트가 그대로 남는 것이 정상 — 디렉터리가 가리키지 않는다)는 사본으로 안 센다.
"""

import argparse
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import common as C
import relocate as RL

ALLOW = os.path.join(
    C.GAME_DIR, "orig_copies_allow.json"
)  # {파일 이름: 사유} — 읽히지 않음을 확인한 죽은 사본만
SECTOR, USER = 2352, 2048
MINDIFF = 24  # 바뀐 구간 최소 길이(바이트)
MINRUN = 12  # SJIS 글 덩이 최소 길이
KEY = 8
KANA = re.compile(
    rb"[\x82][\x9f-\xf1]|[\x83][\x40-\x96]"
)  # 히라가나·가타카나 — 글이면 가나가 든다(그래픽·충돌 표가 한자로 디코드되는 오탐을 거른다)
SJIS = re.compile(rb"(?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]){6,}")


def user_stream(img):
    raw = np.fromfile(img, dtype=np.uint8)
    n = len(raw) // SECTOR
    return raw[: n * SECTOR].reshape(n, SECTOR)[:, C.USER_OFF : C.USER_OFF + USER].reshape(-1)


def segments(old, new):
    """원판 바이트 덩이 — 바뀐 구간 + 새것에 없는 SJIS 글."""
    out = set()
    if len(old) == len(new):
        idx = np.flatnonzero(np.frombuffer(old, np.uint8) != np.frombuffer(new, np.uint8))
        if len(idx):
            for grp in np.split(idx, np.flatnonzero(np.diff(idx) > 8) + 1):
                lo, hi = int(grp[0]), int(grp[-1]) + 1
                if (
                    hi - lo >= MINDIFF and len(set(old[lo:hi])) >= 8
                ):  # 채움·반복(0·FF 따위)은 사본이 아니다
                    out.add(bytes(old[lo:hi]))
    for m in SJIS.finditer(old):
        s = m.group()
        #   같은 자리에 그대로 있으면 안 바꾼 부분이다 · 가나가 3자 미만이면 글이 아니다
        if len(s) >= MINRUN and len(KANA.findall(s)) >= 3 and new[m.start() : m.end()] != s:
            out.add(s)
    return out


def key_at(sg):
    """덩이 안에서 서로 다른 바이트가 5종↑인 첫 8바이트 창의 자리 — 0·FF 채움 위치를 키로 쓰면 이미지 전체가 걸린다. 없으면 None."""
    for i in range(len(sg) - KEY + 1):
        if len(set(sg[i : i + KEY])) >= 5:
            return i
    return None


def search(stream, segs):
    """`{덩이: [스트림 오프셋…]}` — 덩이 안의 8바이트 창을 해시로 훑고 전체로 확인한다."""
    by = {}
    for sg in segs:
        kp = key_at(sg)
        if kp is not None:
            by.setdefault(int.from_bytes(sg[kp : kp + KEY], "little"), []).append((sg, kp))
    keys = np.array(sorted(by), dtype=np.uint64)
    hits = {}
    CH = 1 << 26
    for st in range(0, len(stream), CH):
        buf = stream[st : st + CH + KEY - 1].tobytes()
        for j in range(KEY):  # 8개 어긋난 시작으로 uint64 를 그대로 읽는다(시프트 없이)
            m = (len(buf) - j) // KEY
            if m <= 0:
                continue
            k = np.frombuffer(buf, dtype="<u8", count=m, offset=j)
            idx = np.searchsorted(keys, k)
            idx[idx == len(keys)] = 0
            for p in np.flatnonzero(keys[idx] == k):
                a = st + j + int(p) * KEY
                for sg, kp in by[int(k[p])]:
                    h = a - kp
                    if (
                        h >= 0
                        and bytes(stream[h : h + min(64, len(sg))]) == sg[:64]
                        and bytes(stream[h : h + len(sg)]) == sg
                    ):
                        hits.setdefault(sg, []).append(h)
    return hits


def audit(disc):
    img = build.out_paths(disc)[0]
    if not os.path.exists(img):
        return None
    lay = RL.Layout(disc)
    segs = {}
    with C.open_disc(disc) as d:
        orig = {n: (lba, size) for n, lba, size in d.files()}
        for name, _lba, _size, _old, new, _cnt in build.patched(disc, lay):
            if (
                _old is None or name not in orig or name.startswith("/CPK/")
            ):  # 무비 CPK 는 영상(자막을 영상에 구운 것)이라 글 덩이가 아니다 —  # 폰트는 통째 갈이 · 옮긴 파일의 「원본」은 빈 섹터라 원판에서 직접 읽는다
                continue
            for s in segments(d.read_extent(*orig[name]), new):
                segs.setdefault(s, name)
    stream = user_stream(img)
    #   옮긴 파일의 **옛 자리**는 원본 바이트가 그대로 남는 게 정상(디렉터리가 가리키지 않는다) — 훑기 전에 0 으로 가린다(안 가리면 사본 수천 줄에 묻히고 20분이 걸린다)
    for _n, old_lba, _new_lba, nsec in lay.moved:
        stream[old_lba * USER : (old_lba + nsec) * USER] = 0
    hits = search(stream, set(segs))
    with C.open_disc(disc) as d:
        files = sorted((lba, lba + -(-size // USER), n) for n, lba, size in d.files())
    rows = set()
    for s, offs in hits.items():
        for a in offs:
            lba = a // USER
            owner = next((n for lo, hi, n in files if lo <= lba < hi), "(파일 밖)")
            rows.add(("사본", owner, lba, segs[s], len(s)))
    return sorted(rows), len(segs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    allow = {}
    if os.path.exists(ALLOW):
        with open(ALLOW, encoding="utf-8") as fh:
            allow = json.load(fh)["allow"]
    bad = 0
    for disc in C.DISCS:
        r = audit(disc)
        if r is None:
            print(f"  ⓘ 원판 사본 감사는 못 쟀다 — disc{disc} 빌드 이미지가 없다")
            return 0
        rows, nseg = r
        copies = [x for x in rows if x[0] == "사본"]
        left = [x for x in copies if x[1] not in allow]
        print(
            f"  원판 사본 감사 disc{disc} — 원판 덩이 {nseg}"
            f" · 사본 {len(copies)} (선언 {len(copies) - len(left)} · 선언 밖 {len(left)})"
        )
        if a.list:
            for x in rows:
                print("   ", x)
        for x in left[:20]:
            print(
                f"    ❌ 원판 바이트가 {x[1]} LBA {x[2]} 에 남았다 (원 출처 {x[3]}, {x[4]}B) — 읽히는 길이면 고치고, 죽은 사본이면 사유와 함께 선언한다"
            )
        bad += len(left)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
