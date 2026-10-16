"""재삽입 구조 게이트 — 멤버를 파싱해 **포인터가 다 풀리고 항등 재구축이 바이트 동일한가.**

두 가지를 본다:

1. **항등 재구축** — 같은 코드열로 다시 싸면 원본과 **바이트 동일**해야 한다.
   아니면 우리 파서가 구조를 잘못 읽고 있는 것이고, 그 상태로 문안을 넣으면 조용히 깨진다.
2. **포인터 해석률** — `0x90 <u16>` 자리가 조각 시작에 떨어지는 비율.
   🔴 **못 푼 자리가 있는 멤버**(152)는 그 자리를 **이벤트 VM 데이터로 본다**(마스터 10-12 「재구성해」 —
   `scriptmap.rebuild(event_data=True)`, 근거와 한계는 그 독스트링). 사실은 진짜 포인터인데 우리 스캔이 놓친 것이면
   조각을 옮기는 순간 조용히 어긋나므로, 지키는 건 **구조 검산**(`scriptmap.verify_rebuild` — 스크립트 구간은 포인터 자리만
   바뀐다)과 **멤버 크기 게이트**(`check_member_budget.py`)다. 이 도구는 항등 재구축과 해석률을 센다.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import scriptmap

TEXT_MEMBER = {"ed3": "\\DATA\\", "ed4": "\\BIN\\"}


def scan(disc, limit=None):
    key = TEXT_MEMBER[disc]
    rows = []
    for path, (lba, size) in sorted(common.iso_files(disc).items()):
        if "/SC" not in path or not path.endswith(".DAT"):
            continue
        data = common.read_lba(disc, lba, size)
        try:
            _, ents = common.arc_parse(data)
        except common.ArchiveError:
            continue
        for name, o, msz in ents:
            if key not in name:
                continue
            mem = data[o : o + msz]
            base = scriptmap.text_base(mem)
            if not (2 < base < msz):
                rows.append((path, name, None, 0, 0, False))
                continue
            info = scriptmap.parse(mem)
            try:
                out, _ = scriptmap.rebuild(mem, [c for _, c in info["segments"]])
                ident = out == mem
            except scriptmap.ScriptError:
                ident = False
            rows.append((path, name, base, len(info["pointers"]), info["resolved"], ident))
        if limit and len(rows) >= limit:
            break
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--limit", type=int, default=0, help="멤버 수 상한(빠른 확인용)")
    a = ap.parse_args()
    common.verify_source(a.disc)
    rows = scan(a.disc, a.limit or None)
    if not rows:
        raise SystemExit(f"⏭ {a.disc}: 이벤트 멤버를 못 찾았다")
    # 세 칸으로 가른다 — 「길이 자유」로 다룰 수 있는 것만 게이트로 본다.
    unknown = [r for r in rows if r[2] is None]  # 헤더가 이 규격이 아니다 (예: `*B.BIN`)
    known = [r for r in rows if r[2] is not None]
    clean = [r for r in known if r[5] and r[3] == r[4]]  # 항등 ✓ + 포인터 전부 풀림
    risky = [r for r in known if r[5] and r[3] != r[4]]  # 항등은 되는데 못 푼 자리가 있다
    broken = [r for r in known if not r[5]]  # 🔴 파서가 구조를 잘못 읽는다
    tot = sum(r[3] for r in known)
    res = sum(r[4] for r in known)
    print(
        f"{a.disc}: 멤버 {len(rows):,} (규격 {len(known):,} · 다른 규격 {len(unknown):,}) · "
        f"포인터 {tot:,} · 조각 시작 적중 {res:,} ({res / max(tot, 1):.2%})"
    )
    print(
        f"  길이 자유로 다룰 수 있음: {len(clean):,}  · 못 푼 자리 있음(이벤트 데이터로 보고 길이 자유): {len(risky):,}"
    )
    for path, n, base, np_, nr, _ident in broken[:8]:
        print(f"  🔴 {path} {n}: 항등 재구축 실패 (base={base} 포인터 {np_} 풀림 {nr})")
    if broken:
        print("  🔴 파서가 구조를 잘못 읽고 있다 — 이 상태로 문안을 넣으면 조용히 깨진다")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
