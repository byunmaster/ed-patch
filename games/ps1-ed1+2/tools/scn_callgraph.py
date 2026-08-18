#!/usr/bin/env python3
"""**코드가 어느 대사를 부르는가** — SCN 오버레이에서 호출 그래프를 뽑는다.

**왜.** 오배정은 화면만 봐선 못 잡는다. 유저가 짚은 불변식이 하나 있다(2026-08-12):

    NPC 는 PS1 과 정발이 1:1 이고 이벤트도 같다. **NPC 가 남의 대사를 하거나
    이벤트에서 다른 이벤트의 텍스트가 나오면 안 된다.**

그 불변식을 검사하려면 「이 블록을 누가 부르는가」를 알아야 하는데, 지금까지는 그게 없어
유사도로 추정했다. 그런데 SCN 은 텍스트 뒤에 **네이티브 MIPS 코드**를 달고 있고(SCN1 은
206KB 중 128KB), 그 코드가 `lui`+`addiu` 로 **블록의 절대주소를 직접 만든다.** 그러니
정적으로 뽑힌다 — SCN1 실측 주소 후보 1,252개 중 **1,030개가 블록 시작점에 정확히 적중**.

얻는 것 셋:

- **맵 귀속이 추정이 아니라 사실이 된다.** `scn_maps` 는 지명 헤더 위치로 가르는데,
  이건 코드가 실제로 무엇을 부르는지다. 함수 47개가 각각 연속 블록 구간을 문다.
- **한 함수 안에서 정발 표가 갈리면 오배정 후보다.** 지배 표가 뚜렷하고 소수파가 튄다.
- **아무도 안 부르는 블록**(죽은 블록)이 드러난다.

⚠ **표가 갈린다고 곧 오배정은 아니다.** 상점·현자처럼 여러 맵이 같은 표를 나눠 쓰는
자리가 실재한다(`T_011` 도구점 · `T_333`). 여러 함수에 걸쳐 나타나는 표는 자동 면제한다 —
`scn_maps._EXEMPT_SHARE` 와 같은 발상이다 — 다만 비율이 아니라 **개수**로 가른다.

⚠ 아직 **맵 단위**지 NPC 단위가 아니다. 함수 하나가 한 맵의 NPC 전체를 갖는다.
NPC 로 내려가려면 함수 안 분기를 더 쪼개야 한다.

  python3 tools/scn_callgraph.py             # 전 씬 — 표가 갈리는 함수
  python3 tools/scn_callgraph.py ED1SCN1 -v  # 한 씬, 함수별 블록 구간까지
"""

import bisect
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import common
from common import MIPS_ADDIU, MIPS_ORI, OUT_DIR, ROOT
from patch_sys_ui import SCN_FILES

# 한 표가 이 **개수** 이상의 함수(맵)에 나타나면 맵을 넘나드는 공용 표로 보고 면제한다.
# ⚠ 비율(함수 수의 25%)로 뒀더니 씬이 클수록 임계가 올라가 정작 새야 할 게 안 샜다 —
# 밀매상 `T_04x` 는 마을마다 있어 6맵에 걸치는데 SCN3 에서는 임계가 7이라 통과했다.
# 상점·현자·성 입구 공통 문구는 **개수**로 갈린다(2026-08-12).
_EXEMPT_FN_MIN = 3
_MIN_DOMINANT = 4  # 지배 표를 인정하는 최소 관측 수 — 이보다 적으면 판정을 보류한다


def _scn_bytes(scn):
    """⚠ **원본에서 읽는다.** `patch_sys_ui._scn_layout()` 은 재배치 **후** LBA 라
    빌드 산출물을 가리킨다 — 원본 좌표는 `SCN_FILES`."""
    for name, lba, size in SCN_FILES:
        if name == scn:
            return common.extract(lba, size)
    raise KeyError(scn)


def _map_of(table):
    """정발 표 이름에서 **맵**을 뽑는다 — `T_042` 의 `T_04`.

    정발 규약은 `<종류><맵><시점>` 이다(`T_00x` 엘아스타 · `T_01x` 루디아 · `T_02x` 크루즈).
    끝자리만 다른 표는 **같은 방의 시점 사본**이라 한 맵 핸들러에 섞여도 정상이다 —
    그걸 안 가르면 SCN5 에서만 73곳이 뜨는데 대부분이 이 오탐이었다(2026-08-12).
    """
    return table.rsplit("/", 1)[-1][:-1]


def _blocks(scn):
    """{파일 오프셋: 블록 번호} 와 텍스트 끝 오프셋."""
    p = os.path.join(OUT_DIR, "scn_jp", f"{scn}.json")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    off = {int(e["file_offset"], 16): e["entry_id"] for e in d["entries"]}
    return off, int(d["source"]["text_end"], 16)


def _base(addrs, offs):
    """텍스트가 로드되는 절대주소를 **역산**한다 — 주소에서 블록 오프셋을 뺀 최빈값.

    씬마다 다를 수 있어 상수로 못 박지 않는다. ⚠ 동점이면 **작은 쪽**을 고른다(결정성).
    """
    vote = collections.Counter()
    for a in addrs:
        for o in offs:
            vote[a - o] += 1
    if not vote:
        return None
    best = max(vote.values())
    return min(b for b, c in vote.items() if c == best)


def refs(scn):
    """[(코드 오프셋, 블록 번호)] — 코드가 블록 주소를 만드는 자리."""
    data = _scn_bytes(scn)
    byoff, text_end = _blocks(scn)
    code = data[text_end:]
    pairs = [
        (imm + text_end, addr)
        for imm, _lui, _op, addr in common.iter_lui_pairs(code, (MIPS_ADDIU, MIPS_ORI))
    ]
    # 베이스 투표는 앞쪽 블록으로만 — 전량이면 O(주소×블록) 이 커지는데 정확도는 그대로다
    b = _base([a for _p, a in pairs], sorted(byoff)[:400])
    if b is None:
        return []
    return [(p, byoff[a - b]) for p, a in pairs if (a - b) in byoff]


def functions(scn):
    """{함수 시작 오프셋: [블록 번호 …]} — 함수 경계는 `addiu sp,sp,-N`."""
    data = _scn_bytes(scn)
    _byoff, text_end = _blocks(scn)
    starts = []
    for p in range(text_end, len(data) - 3, 4):
        w = int.from_bytes(data[p : p + 4], "little")
        if (w >> 26) == MIPS_ADDIU and ((w >> 21) & 31) == 29 and ((w >> 16) & 31) == 29:
            if (w & 0xFFFF) >= 0x8000:  # 음수 = 프레임 확보
                starts.append(p)
    out = collections.defaultdict(list)
    for p, eid in refs(scn):
        i = bisect.bisect_right(starts, p) - 1
        out[starts[i] if i >= 0 else 0].append(eid)
    return {k: sorted(set(v)) for k, v in sorted(out.items())}


def _assigned(scn):
    """{블록 번호: 정발 표}"""
    amap = json.load(open(os.path.join(ROOT, "align_map.json"), encoding="utf-8")).get(scn, {})
    ovr = json.load(open(os.path.join(ROOT, "align_overrides.json"), encoding="utf-8")).get(scn, {})
    out = {}
    for k in set(amap) | set(ovr):
        o, a = ovr.get(k) or {}, amap.get(k) or {}
        t = o.get("table") or a.get("table")
        if t:
            out[int(k)] = t
    return out


def exempt_tables():
    """맵을 넘나드는 **공용 표** — 전 씬 합산으로 센다.

    ⚠ 씬별로 세면 샌다. 밀매상·현자 전수처럼 씬을 가로질러 쓰이는 표가 한 씬 안에서는
    한두 함수에만 보이기 때문이다(SCN5 의 `T_040` 이 그랬다, 2026-08-12).
    """
    seen = collections.Counter()
    for scn, _lba, _size in SCN_FILES:
        asg = _assigned(scn)
        for eids in functions(scn).values():
            seen.update({asg[e] for e in eids if e in asg})
    return {t for t, n in seen.items() if n >= _EXEMPT_FN_MIN}


def candidates(scn, exempt=None):
    """[(함수, 지배 표, [(블록, 표) …])] — 지배 표에서 벗어난 블록."""
    fns = functions(scn)
    asg = _assigned(scn)
    if exempt is None:
        exempt = exempt_tables()
    out = []
    for f, eids in sorted(fns.items()):
        # ⚠ **지배 표는 공용 표를 뺀 뒤에 센다.** 일원화한 상점·현자 문구가 한 맵에서
        # 다수를 차지해 지배로 뽑히면, 정작 그 맵의 진짜 표가 전부 「벗어남」으로 뒤집힌다
        # (SCN3 fn@0x2e0a4 이 그랬다 — 지배가 `T_040` 으로 잡혀 리스톤 저택 6블록이 떴다).
        c = collections.Counter(asg[e] for e in eids if e in asg and asg[e] not in exempt)
        if not c:
            continue
        top, n = c.most_common(1)[0]
        if n < _MIN_DOMINANT:
            continue
        m = _map_of(top)
        odd = [
            (e, asg[e]) for e in eids if e in asg and _map_of(asg[e]) != m and asg[e] not in exempt
        ]
        if odd:
            out.append((f, top, sorted(odd)))
    return out


def scan(scenes=None, verbose=False):
    tot = 0
    exempt = exempt_tables()
    for scn, _lba, _size in SCN_FILES:
        if scenes and scn not in scenes:
            continue
        fns = functions(scn)
        rows = candidates(scn, exempt)
        tot += sum(len(o) for _f, _t, o in rows)
        n = sum(len(v) for v in fns.values())
        print(
            f"  {'✅' if not rows else '⚠'} {scn}: 함수 {len(fns)} · 블록 귀속 {n}"
            f" · 맵을 벗어난 블록 {sum(len(o) for _f, _t, o in rows)}곳"
        )
        for f, top, odd in rows:
            joined = " ".join(f"jp{e}:{t.split('/')[-1]}" for e, t in odd)
            print(f"      fn@{f:#x} (지배 {top.split('/')[-1]}) ← {joined}")
        if verbose:
            for f, eids in fns.items():
                print(f"        fn@{f:#x}: {len(eids)}블록 jp{eids[0]}~jp{eids[-1]}")
    print(
        f"\n{'✅ 맵을 벗어난 블록 없음' if not tot else f'⚠ 맵을 벗어난 블록 {tot}곳'}"
        "\n  ⚠ 벗어남이 곧 오배정은 아니다 — 정발이 PS1 과 다른 맵에 같은 대사를 둔 자리가 있다."
        "\n     JP 원문과 정발 문안을 읽고 판정한다."
    )
    return tot


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    sys.exit(1 if scan(set(args) if args else None, "-v" in sys.argv) else 0)
