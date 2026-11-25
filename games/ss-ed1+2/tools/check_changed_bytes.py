#!/usr/bin/env python3
"""**바뀐 바이트 감사** — 원판 대비 최종 이미지에서 바뀐 모든 바이트가 쓰기 장부(`common._ledger`)의 선언된 쓰기로 설명되는지 본다.

    python3 tools/check_changed_bytes.py            # 보고
    python3 tools/check_changed_bytes.py --strict   # 설명 안 되는 변경이 있으면 실패 (check.sh)

🔴 왜(SFC II 동결, 11-07): 전체 이미지에서 포인터 바이트 패턴을 찾아 새 주소로 바꾸는 재배치는 **우연히 같은 바이트를 가진 음악·팔레트·그래픽 데이터까지**
   고친다. 쓰기 장부는 「우리가 한 쓰기」만 안다 — 장부 밖에서 바뀐 바이트(=전역 치환의 부작용·장부를 우회한 쓰기)는 여기서만 잡힌다.
둘을 본다:
 ① 파일별 — 장부의 쓰기를 **라벨의 파일 이름**으로 그 파일에 붙이고(시작 lba = (a−o)/2048 이 그 파일의 원판·최종 lba 중 하나여야 한다 — 아니면 **엉뚱한 파일에 쓴 것**),
    라벨에 파일이 없는 쓰기는 lba 로 찾는다(후보가 하나가 아니면 「모호」로 세어 알린다). 원판·최종 파일의 바이트 비교에서 선언 구간 밖 변경이 있으면 실패.
    (원판보다 늘어난 꼬리는 0 으로 보고 같은 잣대로 본다.)
 ② 이미지 전체 섹터 — 바뀐 섹터가 **최종 파일 범위·디렉터리**가 아니면(볼륨 서술자·경로표·파일 사이·원판 파일의 옛 자리) 따로 센다. 허용은 PVD(16)뿐.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common

US = 2048


def dir_sectors(mm):
    """디렉터리 레코드가 든 섹터 집합(루트부터 걷는다)."""
    pvd = common.sector_user(mm, 16)
    root = pvd[156 : 156 + 34]
    todo = [(int.from_bytes(root[2:6], "little"), int.from_bytes(root[10:14], "little"))]
    out = set()
    while todo:
        lba, size = todo.pop()
        for i in range((size + US - 1) // US):
            out.add(lba + i)
        data = common.read_extent(mm, lba, size)
        pos = 0
        while pos < len(data):
            n = data[pos]
            if n == 0:
                pos = (pos // US + 1) * US
                continue
            rec = data[pos : pos + n]
            if rec[25] & 2 and rec[33 : 33 + rec[32]] not in (b"\x00", b"\x01"):
                todo.append(
                    (int.from_bytes(rec[2:6], "little"), int.from_bytes(rec[10:14], "little"))
                )
            pos += n
    return out


def attribute(led_path, O, B):
    """장부 → ({파일: [(시작,끝)]}, 엉뚱한 파일 목록, 모호 건수)."""
    t1 = {l: n for n, (l, s) in O.items()}
    t2 = {l: n for n, (l, s) in B.items()}
    dec, wrong, ambiguous = {}, [], 0
    with open(led_path, encoding="utf-8") as f:
        for ln in f:
            r = json.loads(ln)
            o, lab = r.get("o"), r.get("l", "")
            if o is None or " 크기" in lab or " LBA " in lab:  # 디렉터리 레코드 갱신
                continue
            s = (r["a"] - o) // US
            cand = {t[s] for t in (t1, t2) if s in t}
            name = lab.split(" ")[0]
            if name in O or name in B:
                if name not in cand:
                    wrong.append((r["t"], lab[:40], s))
                    continue
            else:
                if len(cand) != 1:
                    ambiguous += 1
                    if not cand:
                        wrong.append((r["t"], lab[:40], s))
                        continue
                name = sorted(cand)[0]
            dec.setdefault(name, []).append([o, o + r["n"]])
    return dec, wrong, ambiguous


def merge(rs):
    rs.sort()
    m = []
    for a, b in rs:
        if m and a <= m[-1][1]:
            m[-1][1] = max(m[-1][1], b)
        else:
            m.append([a, b])
    return m


def files_audit(mo, mb, O, B, dec):
    bad = []
    for n, (l, s) in O.items():
        if n not in B:
            continue
        l2, s2 = B[n]
        a = bytes(common.read_extent(mo, l, s))
        b = bytes(common.read_extent(mb, l2, s2))
        a = a + b"\x00" * max(0, len(b) - len(a))
        m = len(b)
        if a[:m] == b:
            continue
        cov = merge(dec.get(n, []))
        ci, n_un, first = 0, 0, None
        for i in range(m):
            if a[i] != b[i]:
                while ci < len(cov) and cov[ci][1] <= i:
                    ci += 1
                if not (ci < len(cov) and cov[ci][0] <= i):
                    n_un += 1
                    first = i if first is None else first
        if n_un:
            bad.append((n, n_un, first))
    return bad


def sector_audit(mo, mb, B):
    """이미지 전체 섹터 비교 — 바뀐 섹터 중 최종 파일·디렉터리 밖."""
    inside = set(dir_sectors(mb))
    for n, (l, s) in B.items():
        inside.update(range(l, l + (s + US - 1) // US))
    n_sec = min(len(mo), len(mb)) // common.SECTOR
    out = []
    for lba in range(n_sec):
        o = lba * common.SECTOR
        if mo[o : o + common.SECTOR] != mb[o : o + common.SECTOR] and lba not in inside:
            out.append(lba)
    return out, len(mo) // common.SECTOR, len(mb) // common.SECTOR


def run(orig, build, led):
    fo, mo = common.open_image(orig)
    fb, mb = common.open_image(build)
    O = {n: (l, s) for n, l, s in common.iso_files(mo)}
    B = {n: (l, s) for n, l, s in common.iso_files(mb)}
    dec, wrong, amb = attribute(led, O, B)
    bad = files_audit(mo, mb, O, B, dec)
    outside, no, nb = sector_audit(mo, mb, B)
    return bad, wrong, amb, outside, (no, nb)


def main():
    build = os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.bin")
    led = os.path.join(common.BUILD_DIR, "write_ledger.jsonl")
    if "--build" in sys.argv:
        build = sys.argv[sys.argv.index("--build") + 1]
    bad, wrong, amb, outside, (no, nb) = run(common.ORIG_BIN, build, led)
    ok = True
    print(f"라벨 없는 쓰기 중 파일이 모호한 것 {amb}건")
    for w in wrong[:10]:
        print(f"  ❌ 라벨의 파일이 그 lba 의 파일이 아니다(엉뚱한 파일에 쓴 것): {w}")
    for n, c, f in bad:
        print(f"  ❌ {n}: 선언 밖 변경 {c}B (첫 {f:#x})")
    ext = [x for x in outside if x != 16]
    if ext:
        print(f"  ❌ 파일·디렉터리 밖에서 바뀐 섹터 {len(ext)}개: {ext[:10]}")
    if no != nb:
        print(f"  ⚠ 섹터 수가 다르다 {no}→{nb}")
    ok = not (bad or wrong or ext or amb)
    print(
        "✅ 선언 밖 변경 0 · 엉뚱한 파일 0 · 파일 밖 변경 섹터 PVD 뿐"
        if ok
        else "❌ 바뀐 바이트 감사 실패"
    )
    if not ok and "--strict" in sys.argv:
        sys.exit(1)


if __name__ == "__main__":
    main()
