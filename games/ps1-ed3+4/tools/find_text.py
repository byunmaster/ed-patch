"""대본 전수 조사 — **코드표로 읽히는 16비트 열이 어디에 더 있나.**

맵 대사(`..\\DATA\\*.BIN`)만 덤프해 놓고 「대본을 다 안다」고 하면 안 된다. 시스템 문구·
메뉴·아이템·전투·HUD 는 다른 자리에 있고, **SJIS 가 아니라 우리 코드표로만 읽힌다**
(그래서 옛 정찰이 「ED3.EXE 는 마커 0」이라고 봤다).

판정은 밀도로 한다 — 어떤 구간을 16비트로 읽었을 때 카나 비중이 일본어답게 나오는가.
⚠ 이건 **후보 좁히기**지 판정이 아니다. 찾은 자리는 반드시 디코드해서 눈으로 본다.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import textenc

KANA_LO, KANA_HI = 0x3F, 0x100
TEXT_HI = 0x800


def runs(data, min_len=4, min_kana=0.35):
    """[(바이트오프셋, [코드…])] — 0xFFFF 로 갈린 조각 중 카나 밀도가 충분한 것."""
    import struct

    n = len(data) // 2
    if n == 0:
        return []
    w = struct.unpack(f"<{n}H", data[: n * 2])
    out, cur, start = [], [], 0
    for i, v in enumerate(w):
        if v == textenc.TERM or v >= TEXT_HI:
            if len(cur) >= min_len:
                k = sum(1 for x in cur if KANA_LO <= x < KANA_HI)
                if k / len(cur) >= min_kana:
                    out.append((start * 2, cur))
            cur, start = [], i + 1
        else:
            if not cur:
                start = i
            cur.append(v)
    if len(cur) >= min_len:
        k = sum(1 for x in cur if KANA_LO <= x < KANA_HI)
        if k / len(cur) >= min_kana:
            out.append((start * 2, cur))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--show", type=int, default=6, help="자리마다 보여 줄 예시 수")
    ap.add_argument("--min-syms", type=int, default=40, help="이만큼 안 되는 자리는 안 보고한다")
    a = ap.parse_args()
    common.verify_source(a.disc)
    rows = []
    for path, (lba, size) in sorted(common.iso_files(a.disc).items()):
        if size > 8 << 20 or "/XA/" in path or "/MOV/" in path or path.endswith("/"):
            continue
        data = common.read_lba(a.disc, lba, size)
        # 아카이브면 멤버마다, 아니면 통째로
        targets = [(path, data)]
        try:
            _, ents = common.arc_parse(data)
            targets = [(f"{path}!{n}", data[o : o + s]) for n, o, s in ents]
        except common.ArchiveError:
            pass
        for name, blob in targets:
            rs = runs(blob)
            syms = sum(len(c) for _, c in rs)
            if syms >= a.min_syms:
                rows.append((name, len(blob), len(rs), syms, rs))
    rows.sort(key=lambda r: -r[3])
    tot = sum(r[3] for r in rows)
    print(f"{a.disc}: 텍스트가 있는 자리 {len(rows):,} · 심볼 합계 {tot:,}")
    seen_arc = set()
    for name, blob, nr, syms, rs in rows:
        arc = name.split("!")[0]
        # 같은 아카이브의 DATA 멤버는 이미 아는 자리라 한 줄로 접는다
        if "\\DATA\\" in name or "\\BIN\\" in name:
            if arc in seen_arc:
                continue
            seen_arc.add(arc)
            print(f"  {arc} (맵 대사 멤버들 — 이미 아는 자리)")
            continue
        print(f"\n  ★ {name}  ({blob:,}B · 런 {nr} · 심볼 {syms:,})")
        for off, codes in rs[: a.show]:
            print(f"      @{off:>6} {textenc.decode(codes, a.disc)[:52]}")


if __name__ == "__main__":
    main()
