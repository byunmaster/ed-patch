"""멤버 크기 예산 — **번역을 넣은 아카이브가 제자리에서 재배치되나** (전수).

    python3 tools/check_member_budget.py --disc ed3

대본 멤버는 한국어로 옮기면 원본보다 커질 수 있다. 문안을 줄이지 않고 **아카이브 안에서 뒤 멤버를 밀어**
해결한다(`arcpack` — 마스터 10-12). 이 게이트는 빌드와 **같은 함수**(`build.encode_member` → `scriptmap.rebuild(event_data=True)`
→ `arcpack.plan`)로 아카이브마다 「섹터 수가 안 늘고 들어가나」를 센다 — 안 들어가면(다른 파일을 옮겨야 하면) 실패다.
🔴 재구축이 안 되는 멤버(`ScriptError`)도 실패다.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arcpack
import build
import common
import hangul_map
import scriptmap
import script as sc


def scan(disc, canon=None, table=None):
    """([(경로, 필요 B, 여유 B, 거둔 B)], [(키, 사유)], 넘친 멤버 수, 넘친 합계 B)."""
    if canon is None:
        canon, _ = sc.load_effective(disc)
    if table is None:
        # 코드 수는 글리프 자리와 무관하다(글자당 코드 하나) — 시험 빌드와 같은 자리표로 센다.
        need = list(hangul_map.EXTRA) + hangul_map.needed_chars(disc)
        table, _ = hangul_map.assign(disc, hangul_map.test_slots(disc), chars=need)
    plans, bad = [], []
    over_n = over_b = 0
    report = {"skipped": 0}
    for path, (lba, size) in sorted(common.iso_files(disc).items()):
        if "/SC" not in path or not path.endswith(".DAT"):
            continue
        data = common.read_lba(disc, lba, size)
        try:
            _, ents = common.arc_parse(data)
        except common.ArchiveError:
            continue
        repl = {}
        for nm, off, sz in ents:
            lines = canon.get((path, nm))
            if not lines:
                continue
            mem = bytes(data[off : off + sz])
            lines = {i: dict(r) for i, r in lines.items()}  # 조사 변환이 정본을 안 바꾸게 사본으로
            segs = build.encode_member(disc, path, nm, mem, lines, table, report)
            try:
                newmem, _ = scriptmap.rebuild(mem, segs, event_data=True)
            except scriptmap.ScriptError as e:
                bad.append((sc.key_of(path, nm), f"재구축 실패 — {e}"))
                continue
            repl[nm] = newmem
            if len(newmem) > sz:
                over_n += 1
                over_b += len(newmem) - sz
        if not repl:
            continue
        try:
            p = arcpack.plan(data, repl)
        except arcpack.PackError as e:
            bad.append((path, str(e)))
            continue
        if p["grow"] > 0 or p["reclaimed"]:
            plans.append((path, p["grow"], p["slack"], p["reclaimed"]))
    return plans, bad, over_n, over_b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    a = ap.parse_args()
    common.verify_source(a.disc)
    plans, bad, over_n, over_b = scan(a.disc)
    for key, why in bad:
        print(f"  🔴 {key}: {why}")
    print(
        f"{a.disc}: 멤버 크기 — 원본보다 큰 멤버 {over_n}개(합계 {over_b:+d}B) · 재배치하는 아카이브 {len(plans)}개 "
        f"(늘어난 길이 합계 {sum(p[1] for p in plans):+d}B · 거둔 꼬리 {sum(p[3] for p in plans)}B)"
        + (f" · 🔴 안 되는 것 {len(bad)}" if bad else " · ✅ 전부 섹터 여유 안")
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
