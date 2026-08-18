#!/usr/bin/env python3
"""SCN 블록 ↔ 맵(지명) 귀속, 그리고 정발 테이블 ↔ 맵 대응 학습.

정렬을 씬 단위가 아니라 **맵 단위**로 좁히기 위한 기반이다. 전 게임 정발 풀(2,622개)에서
찾으면 엉뚱한 맵의 비슷한 문장이 1순위로 올라온다 — 크루즈 마을 블록이면 크루즈 마을
테이블 안에서만 찾게 하면 오매칭이 줄고, 정답이 2순위로 밀려 있던 것도 올라온다.

**근거(2026-07-30 실측)**: SCN 맵 세그먼트는 지명 헤더로 시작하므로(`patch_sys_ui`가
지명을 바이트 검색으로 찾는 그 헤더) 블록의 `file_offset`을 헤더 오프셋과 비교하면 맵이
정해진다. 정발 쪽은 테이블명이 이미 맵을 인코딩한다 — 확정 매핑에서 학습하면 순도 100%로
`T_00x→엘아스타 · T_01x→루디아 · T_02x→크루즈 마을 · T_03x→베르가 광산 · T_04x→네리아 항구`가
나온다. 이 규칙만으로 회수가능 후보 9건이 맵 불일치로 걸렸고, **9건 전부가 사람이 원문을
읽고 오매칭으로 판정한 것과 일치했다.**

⚠ **맵 일치는 기각용이지 확인용이 아니다.** 같은 맵 안에서도 오매칭이 난다
(`jp284` 의미 반대 · `jp554` 화자 반대 — 둘 다 맵은 맞았다).
⚠ **상점 테이블은 맵을 넘나든다**(도구점·밀매상). 여러 맵에서 관측되면 맵 무관으로 뺀다.

usage:
  scn_maps.py ED1 1        해당 씬의 맵 세그먼트·블록 귀속 요약
  scn_maps.py ED1 --learn  전 씬에서 테이블→맵 대응 학습 결과
"""

import bisect
import collections
import json
import os
import re
import sys

import common
from common import OUT_DIR, ROOT

# 최빈 맵 점유율이 이 이상이면 그 맵으로 학습한다. **개수가 아니라 점유율로 본다** —
# 앵커에는 오정렬 노이즈가 섞여 있어(align 무플래그 쌍도 전부 옳지는 않다) 소수 관측
# 하나로 맵무관 처리하면 정작 필요한 곳에서 제약이 꺼진다(T_024 크루즈13:네리아2:베르가1:
# 루디아1 → 76%인데 맵무관으로 빠지던 버그, 2026-07-30).
_PURITY_MIN = 0.7
# 상위 두 맵이 모두 이 이상이면 진짜 양다리(상점 등)로 보고 맵 제약을 면제한다
_EXEMPT_SHARE = 0.3
_SCENES = tuple(range(1, 7))


def _scn_file(game, scn):
    from patch_sys_ui import SCN_FILES

    for name, lba, size in SCN_FILES:
        if name == f"{game}SCN{scn}":
            return name, lba, size
    raise KeyError(f"{game}SCN{scn} 없음")


def segments(game, scn):
    """[(file_offset, 지명KR)] — 맵 세그먼트 시작점. 원본 SCN 바이트에서 지명 헤더를 찾는다."""
    from patch_sys_ui import PLACES

    _, lba, size = _scn_file(game, scn)
    data = common.extract(lba, size)
    seen, hits = set(), []
    for jp, kr in PLACES:
        jb = jp.encode("shift_jis")
        for m in re.finditer(re.escape(jb), data):
            i, e = m.start(), m.end()
            # patch_sys_ui.patch_scn_headers 와 같은 헤더 판별(앞=포인터꼬리/널, 뒤=널종단)
            ok = i == 0 or data[i - 1] in (0x80, 0x00) or data[e : e + 4] == b"\x00" * 4
            if ok and e < len(data) and data[e] == 0 and i not in seen:
                seen.add(i)
                hits.append((i, kr))
    hits.sort()
    return hits


def block_maps(game, scn, cache=True):
    """{entry_id: 지명KR} — 블록이 어느 맵 세그먼트에 속하는지."""
    path = os.path.join(OUT_DIR, "scn_maps", f"{game}SCN{scn}.json")
    if cache and os.path.exists(path):
        return {int(k): v for k, v in json.load(open(path, encoding="utf-8")).items()}
    segs = segments(game, scn)
    offs = [s[0] for s in segs]
    names = [s[1] for s in segs]
    doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{game}SCN{scn}.json"), encoding="utf-8"))
    out = {}
    for e in doc["entries"]:
        k = bisect.bisect_right(offs, int(e["file_offset"], 16)) - 1
        out[e["entry_id"]] = names[k] if k >= 0 else None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(
        {str(k): v for k, v in out.items()}, open(path, "w", encoding="utf-8"), ensure_ascii=False
    )
    return out


def instances(game, scn):
    """[(lo, hi, 지명, n_entries)] — 맵 **인스턴스**(방·구역) 경계.

    세그먼트 구조 `[지명][대사 블록들][메시지 점프테이블]`의 반복에서 **점프테이블이 꼬리**다
    (테이블 시작 = 다음 세그먼트 시작 − 테이블 크기, 바이트까지 일치 실측 2026-07-30).
    지명보다 12배 세밀하다 — 루디아는 지명으론 440블록 한 덩어리인데 인스턴스로는 9개(각 ~36).
    한 인스턴스가 정발 테이블 1~3개에 대응하므로 사실상 NPC 단위에 가깝다.
    """
    import struct

    _, lba, size = _scn_file(game, scn)
    d = common.extract(lba, size)
    W = [struct.unpack_from("<I", d, i)[0] for i in range(0, len(d) - 3, 4)]

    def ok(w):
        return w == 0 or (0x80160000 <= w < 0x80200000)

    runs, cur = [], 0
    for i, w in enumerate(W):
        if ok(w):
            cur += 1
        else:
            if cur >= 24:
                runs.append((i - cur, cur))
            cur = 0
    if cur >= 24:
        runs.append((len(W) - cur, cur))
    segs = segments(game, scn)
    soff = [x[0] for x in segs]
    snm = [x[1] for x in segs]
    out, prev = [], 0
    for st, n in runs:
        s = st * 4
        k = bisect.bisect_right(soff, s) - 1
        out.append((prev, s, snm[k] if k >= 0 else None, n))
        prev = s + n * 4
    return out


def block_instances(game, scn, cache=True):
    """{entry_id: 인스턴스키} — 인스턴스키 = "지명#i" (맵보다 세밀한 정렬 제약용)."""
    path = os.path.join(OUT_DIR, "scn_maps", f"{game}SCN{scn}_inst.json")
    if cache and os.path.exists(path):
        return {int(k): v for k, v in json.load(open(path, encoding="utf-8")).items()}
    inst = instances(game, scn)
    doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{game}SCN{scn}.json"), encoding="utf-8"))
    seen = collections.Counter()
    keys = []
    for lo, hi, nm, _n in inst:
        seen[nm] += 1
        keys.append((lo, hi, f"{nm}#{seen[nm]}"))
    out = {}
    for e in doc["entries"]:
        o = int(e["file_offset"], 16)
        out[e["entry_id"]] = next((k for lo, hi, k in keys if lo <= o < hi), None)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(
        {str(k): v for k, v in out.items()}, open(path, "w", encoding="utf-8"), ensure_ascii=False
    )
    return out


_HANDLER_WINDOW = 0x18  # 핸들러 관용구 크기(6 MIPS 명령)
_NOOP_MIN = 4  # 이 횟수 이상 반복되는 핸들러 주소 = 미사용 ID들이 공유하는 no-op


def msg_ids(game, scn, cache=True):
    """({entry_id: [메시지ID…]}, {인스턴스키: 실제 메시지 수}) — 점프테이블에서 역추출.

    세그먼트 꼬리의 점프테이블은 `table[메시지ID] = 핸들러 RAM주소`다. 핸들러는 24B
    (6 MIPS 명령) 간격의 관용구 — 인자 세팅 + jal sprintf + 공용 꼬리 점프 — 라, 그 24B 창
    안의 lui/addiu 텍스트 참조를 `reinsert_kr_pilot.find_refs`로 뽑아 블록 경계와 대조하면
    **메시지ID → 블록**이 나온다. RAM↔파일은 `file = RAM − OVERLAY_RAM_BASE`.

    실측(SCN1): 554건 · 서로 다른 블록 403개 · **한 블록에 ID 2개 이상 걸린 것 81개**
    (같은 대사를 상황별로 재사용 — 중복 배정 판단에 쓸 수 있다).
    부산물인 **인스턴스별 실제 메시지 수**를 정발 테이블 엔트리 수와 대조하면 유사도 없이
    개수만으로 인스턴스↔테이블 대응을 검증할 수 있다.

    ⚠ 창을 200B로 잡으면 이웃 핸들러 참조까지 긁혀 블록이 7~8개로 뭉개진다. 24B로 좁힐 것.
    ⚠ 미사용 ID는 공용 no-op 핸들러 하나를 공유한다(엘아스타 117엔트리 중 87개가 같은 주소).
      최빈 주소를 빼야 실제 메시지 수가 나온다.
    """
    path = os.path.join(OUT_DIR, "scn_maps", f"{game}SCN{scn}_msg.json")
    if cache and os.path.exists(path):
        d = json.load(open(path, encoding="utf-8"))
        return {int(k): v for k, v in d["blocks"].items()}, d["counts"]

    import struct

    from reinsert_kr_pilot import OVERLAY_RAM_BASE, find_refs

    _, lba, size = _scn_file(game, scn)
    data = common.extract(lba, size)
    doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{game}SCN{scn}.json"), encoding="utf-8"))
    by_off = {int(e["file_offset"], 16): e["entry_id"] for e in doc["entries"]}
    offs = sorted(by_off)
    text_end = offs[-1] + 1

    seen = collections.Counter()
    blocks, counts = collections.defaultdict(list), {}
    for _lo, hi, nm, n in instances(game, scn):
        seen[nm] += 1
        key = f"{nm}#{seen[nm]}"  # block_instances 와 같은 키 규약
        if hi + n * 4 > len(data):
            continue
        ents = [struct.unpack_from("<I", data, hi + i * 4)[0] for i in range(n)]
        freq = collections.Counter(e for e in ents if e)
        top, ntop = freq.most_common(1)[0] if freq else (0, 0)
        noop = top if ntop >= _NOOP_MIN else None
        used = set()
        for mid, ram in enumerate(ents):
            if not ram or ram == noop or not (0x80160000 <= ram < 0x80200000):
                continue
            h = ram - OVERLAY_RAM_BASE
            if not (0 <= h < len(data) - _HANDLER_WINDOW):
                continue
            for _io, _lu, _op, addr in find_refs(data[h : h + _HANDLER_WINDOW], text_end):
                k = bisect.bisect_right(offs, addr - OVERLAY_RAM_BASE) - 1
                if k >= 0:
                    blocks[by_off[offs[k]]].append(mid)
                    used.add(mid)
        counts[key] = len(used)

    blocks = {k: sorted(set(v)) for k, v in blocks.items()}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(
        {"blocks": {str(k): v for k, v in blocks.items()}, "counts": counts},
        open(path, "w", encoding="utf-8"),
        ensure_ascii=False,
    )
    return blocks, counts


def _anchors(game, scn):
    """확정 매핑 (jp_id, 정발테이블) — 오버라이드(사람 확정) + align 채택쌍."""
    out = []
    ovp = os.path.join(ROOT, "align_overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")).get(f"{game}SCN{scn}", {})
    for jid, v in ov.items():
        if jid.isdigit() and not v.get("exclude") and "table" in v:
            out.append((int(jid), v["table"]))
    ap = os.path.join(OUT_DIR, "align", f"{game}_SCN{scn}.json")
    if os.path.exists(ap):
        for p in json.load(open(ap, encoding="utf-8"))["pairs"]:
            # ⚠ `kr` 이 없거나 table 이 None 인 쌍이 섞인다(비운 블록 등) — 그대로 넘기면
            # `table_pool` 이 `None.startswith` 로 죽는다(2026-08-12 실측).
            if not p.get("flags") and (p.get("kr") or {}).get("table"):
                out.append((p["jp"]["entry_id"], p["kr"]["table"]))
    return out


def table_maps(game, scenes=_SCENES):
    """({테이블: 지명}, {맵무관 테이블}) — 확정 매핑에서 학습한다."""
    tally = collections.defaultdict(collections.Counter)
    for scn in scenes:
        try:
            bm = block_maps(game, scn)
        except (KeyError, FileNotFoundError):
            continue
        for jid, tbl in _anchors(game, scn):
            m = bm.get(jid)
            if m:
                tally[tbl][m] += 1
    learned, exempt = {}, set()
    for tbl, c in tally.items():
        tot = sum(c.values())
        ranked = c.most_common()
        top, ntop = ranked[0]
        if ntop / tot >= _PURITY_MIN:
            learned[tbl] = top
        elif len(ranked) > 1 and ranked[1][1] / tot >= _EXEMPT_SHARE:
            exempt.add(tbl)  # 상점처럼 여러 맵에 실제로 등장
        elif os.environ.get("EXEMPT_UNLEARNED"):
            # ⚠ 아래 '제약 없이 내려간다'는 주석과 소비자 구현이 어긋나 있다. 소비자는
            # `learned.get(t)==맵 or t in exempt` 로 풀을 만들므로(assign_pages.main),
            # 미학습 테이블은 무제약이 아니라 **모든 맵의 풀에서 빠진다** — 그 엔트리를
            # 정답으로 가진 블록은 어떤 배정기도 못 맞힌다(전 씬 실측 202건 중 102건).
            #
            # ⛔ **그런데 이걸 켜도 LaBSE 배정기는 이득을 못 본다**(2026-07-31 크루즈 마을):
            #   풀 311→557(+79%) · 도달 가능해진 정답 4건 → 그중 회수 **0건**,
            #   정밀도 91.9%→85.1%(불일치 5→10). 넓힌 방을 코사인 top-1 이 못 쓴다.
            # ⇒ 풀 드롭은 진짜 결함이지만 **문턱만 고쳐서는 회수가 안 된다.** 넓은 후보를
            #   감당할 배정기(인스턴스 통째 읽기)와 같이 가야 의미가 있다. 그때까지 기본 off.
            exempt.add(tbl)
        # 둘 다 아니면 학습하지 않는다(제약 없이 씬 로직으로 내려간다)
    return learned, exempt


def table_instances(game, scenes=_SCENES, min_n=1, min_share=0.0):
    """{정발테이블: {인스턴스키}} — 확정 매핑에서 학습. 맵보다 세밀한 정렬 제약.

    맵 단위(순도 100%)보다 거칠지만 훨씬 좁다 — 인스턴스 순도 중앙값 87.9%(2026-07-30).
    홀드아웃 검증(크루즈 마을 140블록, 문턱 0.75)에서 정밀도 **83.3% → 88.2%**.
    학습이 안 된 테이블은 제약을 걸지 않는다(맵 제약만 적용).

    ⚠ 한때 97.7%로 측정됐는데 **잘못된 수치**였다 — 그 실험은 홀드아웃 블록을 학습에서
    빼서 마스크가 우연히 촘촘해진 것이었다. 실제 학습으로는 88.2%가 상한이다.
    병목은 알고리즘이 아니라 **앵커 품질**이다: align 무플래그 쌍의 오배정을 흡수해
    "이 테이블은 저 인스턴스에도 걸친다"고 잘못 배우고, min_n/min_share 로 걸러도
    좋은 신호까지 같이 날아가 순이득이 없었다.
    """
    tally = collections.defaultdict(collections.Counter)
    for scn in scenes:
        try:
            bi = block_instances(game, scn)
        except (KeyError, FileNotFoundError):
            continue
        for jid, tbl in _anchors(game, scn):
            k = bi.get(jid)
            if k:
                tally[tbl][k] += 1
    # ⚠ 앵커에는 오정렬 노이즈가 섞여 있다(align 무플래그 쌍도 전부 옳지는 않다). 관측 1회
    # 짜리를 그대로 넣으면 테이블이 여러 인스턴스에 걸쳐 제약이 느슨해진다 — 실측으로
    # min_n=1 은 정밀도 87%, min_n=2 부터 90%대(2026-07-30 홀드아웃).
    out = {}
    for t, c in tally.items():
        tot = sum(c.values())
        keep = {k for k, n in c.items() if n >= min_n and n / tot >= min_share}
        if keep:
            out[t] = keep
    return out


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else "ED1"
    if "--learn" in sys.argv:
        learned, exempt = table_maps(game)
        by = collections.defaultdict(list)
        for t, m in learned.items():
            by[m].append(t)
        print(f"학습된 테이블→맵 {len(learned)}개 / 맵무관 {len(exempt)}개")
        for m, ts in sorted(by.items(), key=lambda x: -len(x[1])):
            print(f"  {m:14} {len(ts):3}개  {sorted(ts)[:8]}")
        print(f"  맵무관(상점 등): {sorted(exempt)}")
        return
    if "--msg" in sys.argv:
        scn = int(sys.argv[2])
        blocks, counts = msg_ids(game, scn, cache=False)
        multi = sum(1 for v in blocks.values() if len(v) > 1)
        n = sum(len(v) for v in blocks.values())
        print(f"{game}SCN{scn}: 메시지ID→블록 {n}건 · 블록 {len(blocks)}개 · 다중ID {multi}개")
        for k, c in sorted(counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  {k:20} 실제 메시지 {c}")
        return
    scn = int(sys.argv[2])
    segs = segments(game, scn)
    bm = block_maps(game, scn, cache=False)
    c = collections.Counter(v for v in bm.values() if v)
    print(f"{game}SCN{scn}: 세그먼트 {len(segs)}개 / 블록 {len(bm)}개")
    for m, n in c.most_common():
        print(f"  {m:14} 블록 {n}")


if __name__ == "__main__":
    main()
