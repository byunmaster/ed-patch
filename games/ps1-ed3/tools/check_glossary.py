"""고유명사 정본 게이트 — **정본과 원본이 어긋났나**를 본다.

여기서 잡는 사고는 셋이다:

1. 🔴 **정본에 있는데 원본엔 없는 항목** — 오타이거나, 원본 표를 다시 뜨면서 자리가 밀린 것이다.
   진행률과 달리 이건 **지금 고칠 수 있으므로** 실패로 친다(늘 빨간불인 게이트는 아무도 안 본다).
2. 🔴 **한 우리말 표기가 서로 다른 원문 둘에 붙었다** — 화면에서 같은 이름이 두 가지로 읽힌다.
   ⚠ 단 **갈래가 다르면 정상**이다(ED4 의 소환수는 몬스터이면서 마법 이름이다).
3. ⚠ **정발을 따르기로 한 갈래(인물·지명)인데 근거가 없다** — 경고지 실패가 아니다.
   PS1 리메이크에만 있는 자리(성 내부·층 이름)는 정발에 짝이 아예 없다.
4. ⚠ **새턴 ED3(같은 작품)와 표기가 갈렸다** — ED3 은 같은 작품의 다른 이식이라
   이름이 갈리면 한쪽이 틀린 것이다. ⚠ 그 트리가 없는 머신에선 조용히 건너뛴다
   (늘 빨간불인 게이트는 아무도 안 본다).

⚠ **번역 진행률은 실패가 아니다.** 아직 안 옮긴 낱말은 「할 일」이지 「실패」가 아니다.
"""

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import glossary
import textenc


def words(disc):
    """{갈래: [원문…]} — **원본에서 그 자리에서 다시 뽑는다.**

    ⚠ `work/derived/` 의 덤프를 읽지 않는다 — 파생물이 없으면 이 검사가 **조용히 건너뛰어**,
      정작 중요한 대조가 안 도는 게이트가 된다(체크리스트 4-B 「검사기 자신의 커버리지」).
      원본은 어차피 게이트가 요구하므로 여기서 바로 훑는 편이 구멍이 없다.
    """
    import dump_names

    cm = textenc.charmap(disc)
    lba, size = common.iso_files(disc)[dump_names.EXE[disc]]
    data = common.read_lba(disc, lba, size)
    labels = dump_names.REGIONS[disc]
    regs = dump_names.split(dump_names.regions(dump_names.strings(data, cm)), labels)
    by = collections.defaultdict(list)
    for r in regs:
        r["kind"] = labels.get(r["start"], "?")
        if r["kind"] in glossary.KINDS:
            for s in r["items"]:
                if s not in by[r["kind"]]:
                    by[r["kind"]].append(s)
    # 🔴 표 바로 뒤 첫 항목은 구역 스캐너가 못 본다(`exetext.glued_entries`) — 빌드는 표로
    #    그 자리를 옮기므로, 여기서 빠지면 정본에 넣은 이름이 「원본에 없는 항목」으로 운다.
    import exetext

    kind_at = {off: r["kind"] for r in regs for off in r["offs"]}
    tables = exetext.scan_tables(data, cm) + exetext.detached_tables(data, disc)
    for off, mates in exetext.glued_entries(data, tables):
        kind = exetext.kind_of(mates, kind_at)
        codes, _ = exetext.raw_string(data, off)
        if kind not in glossary.KINDS or not codes or any(c not in cm for c in codes):
            continue
        s = textenc.decode(codes, disc)
        if len(codes) <= dump_names.MAX_LEN and s not in by[kind]:
            by[kind].append(s)
    return by


SIBLING = {"ed3": ("ss-ed3", "glossary_manual.json")}


def sibling_diff(disc, cats):
    """같은 작품의 다른 이식(새턴 ED3)과 표기가 갈린 자리."""
    if disc not in SIBLING:
        return []
    game, fname = SIBLING[disc]
    p = os.path.join(common.main_repo(), ".claude", "worktrees", game, "games", game, fname)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        other = json.load(f)["categories"]
    flat = {}
    for d in other.values():
        for k, v in d.items():
            flat.setdefault(k, v)
    out = []
    for kind, d in sorted(cats.items()):
        bad = [(jp, kr, flat[jp]) for jp, kr in d.items() if jp in flat and flat[jp] != kr]
        if bad:
            out.append(
                f"{kind}: {game} 와 갈린 표기 {len(bad)} — "
                + " · ".join(f"{jp} 여기「{a}」 저기「{b}」" for jp, a, b in bad[:5])
            )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    a = ap.parse_args()
    if not glossary.exists(a.disc):
        print(f"⏭ {a.disc}: 고유명사 정본이 아직 없다")
        return 0
    g = glossary.load(a.disc)
    cats = g["categories"]
    ev = g.get("evidence", {})
    common.verify_source(a.disc)
    src = words(a.disc)
    fail = []

    n = sum(len(v) for v in cats.values())
    filled = sum(1 for v in cats.values() for x in v.values() if x)
    print(
        f"{a.disc}: 정본 {n}항목 · 옮긴 것 {filled} ({filled * 100 // max(n, 1)}%) · 근거 {len(ev)}"
    )

    if True:
        for kind, d in sorted(cats.items()):
            have = set(src.get(kind, ()))
            ghost = [jp for jp in d if jp not in have]
            if ghost:
                fail.append(f"{kind}: 원본에 없는 항목 {len(ghost)} — {' · '.join(ghost[:6])}")
            miss = [jp for jp in src.get(kind, ()) if jp not in d]
            if miss:
                print(f"  ⬜ {kind}: 아직 안 옮긴 낱말 {len(miss)} — {' · '.join(miss[:6])}")

    seen = collections.defaultdict(list)
    for kind, d in cats.items():
        for jp, kr in d.items():
            if kr:
                seen[(kind, kr)].append(jp)
    for (kind, kr), jps in sorted(seen.items()):
        if len(jps) > 1:
            fail.append(f"{kind}: 「{kr}」 가 원문 {len(jps)}개에 붙었다 — {' · '.join(jps)}")

    for kind in glossary.FROM_OFFICIAL:
        bare = [jp for jp in cats.get(kind, {}) if jp not in ev]
        if bare:
            print(
                f"  ⚠ {kind}: 정발 근거가 없는 항목 {len(bare)} (우리가 정한 자리) — {' · '.join(bare[:6])}"
            )

    for m in sibling_diff(a.disc, cats):
        print(f"  ⚠ {m}")

    for m in fail:
        print(f"  🔴 {m}")
    print(f"{a.disc}: 고유명사 정본 — {'🔴 어긋났다' if fail else '✅ 원본과 맞는다'}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
