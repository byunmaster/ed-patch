"""🔴 원판 대사 사본 검사 — 우리가 번역해 바꾼 문안의 **원판 일본어 바이트가 제품 이미지 어딘가에 그대로 남았나**.

배경(PCE I, 마스터 11-17): 원판 디스크에 대사 블록 사본이 우리가 고친 자리 밖에 따로 있었고, 정상 진행이
그 사본을 읽어 장면이 일본어로 나왔다. 빌드·게이트는 고친 자리만 분모로 봐서 못 잡는다.
여기서는 **이미지 전체**(유저 데이터 LBA 순 이음)에서 번역된 줄의 원문 조각(SJIS, 12바이트 이상)을 바이트 검색한다.

    python3 tools/check_orig_copies.py [--image BIN] [--orig]   # --orig = 원판 이미지에서 센다(표본 확인용)

사본 0 이면 통과, 아니면 실패. 허용 목록(`orig_copies_allow.json`: 파일 경로 → 사유)은 「읽히지 않는다」를 시험 롬으로
확인한 자리만 — 사유 필수.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common  # noqa: E402

MINB = 12
ALLOW = os.path.join(os.path.dirname(HERE), "orig_copies_allow.json")


def needles():
    import names_corpus as n

    out = set()
    for _key, jp, kr, _kind in n.pairs():
        if not jp or kr is None or kr == jp:
            continue
        for seg in re.split(r"\n|%[a-z]", jp):
            seg = seg.strip(" ")
            try:
                b = seg.encode("cp932")
            except UnicodeEncodeError:
                continue
            # 가나·한자(2바이트) 를 한 글자 이상 포함한 것만 — 순수 ASCII 조각은 코드·표와 겹친다
            if len(b) >= MINB and any(c >= 0x81 for c in b):
                out.add(b)
    return sorted(out)


def main():
    img = common.ORIG_BIN if "--orig" in sys.argv else None
    if "--image" in sys.argv:
        img = sys.argv[sys.argv.index("--image") + 1]
    if img is None:
        img = os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.bin")
    if not os.path.exists(img):
        print(f"❌ 이미지 없음: {img}")
        return 2
    nd = needles()
    allow = json.load(open(ALLOW)) if os.path.exists(ALLOW) else {}
    with tempfile.TemporaryDirectory() as td:
        pat, dump = os.path.join(td, "p"), os.path.join(td, "d")
        # grep -F 는 줄 단위라 패턴에 개행이 없어야 한다(조각 분할로 보장). 패턴 파일은 바이트 그대로.
        with open(pat, "wb") as f:
            f.write(b"\n".join(nd) + b"\n")
        fh, mm = common.open_image(img)
        total = len(mm) // common.SECTOR
        with open(dump, "wb") as f:
            for lba in range(total):
                f.write(common.sector_user(mm, lba))
        files = common.iso_files(mm)
        mm.close()
        fh.close()
        env = dict(os.environ, LC_ALL="C")
        # 개행(0x0a)이 데이터에 있어도 grep -b 는 바이트 오프셋을 준다
        r = subprocess.run(
            ["grep", "-a", "-b", "-o", "-F", "-f", pat, dump], capture_output=True, env=env
        )
        hits = []
        for ln in r.stdout.split(b"\n"):
            if b":" not in ln:
                continue
            off, _, txt = ln.partition(b":")
            if off.isdigit():
                hits.append((int(off), txt))
    def owner(off):
        for p, l, s in files:
            if l <= off // 2048 < l + (s + 2047) // 2048:
                return p, off - l * 2048
        return "(파일 밖)", off

    by = {}
    for off, txt in hits:
        p, fo = owner(off)
        # 허용: 파일째(`경로`) 또는 자리째(`경로@0x파일오프셋`) — 사유 필수
        if p in allow or f"{p}@{fo:#x}" in allow:
            continue
        by.setdefault(p, []).append((off // 2048, txt, fo))
    bad = by
    print(f"조각 {len(nd)}종 · 적중 {len(hits)} · 허용 밖 파일 {len(by)}개")
    for p, v in sorted(bad.items()):
        print(f"  ❌ {p}: {len(v)}곳 (LBA {v[0][0]}~, 파일 +{v[0][2]:#x}) 예) {v[0][1].decode('cp932', 'replace')[:30]}")
    if "--orig" in sys.argv:
        return 0
    if bad:
        print(f"❌ 원판 일본어 사본 {sum(len(v) for v in bad.values())}곳 · {len(bad)}파일 남음")
        return 1
    print("✅ 원판 일본어 사본 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
