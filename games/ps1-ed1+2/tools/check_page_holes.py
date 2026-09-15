#!/usr/bin/env python3
"""⚠ **게이트 밖 · 정발 배정 시대 진단기**(2026-09-13 실측 — 자체 번역 전환 이후 재검토
없이 남았다). 손으로 돌리는 용도로만 쓴다.

정발 엔트리의 **쓰이는 페이지 사이에 구멍**이 있는 자리를 센다 — 오배정의 발자국.

**왜.** 3장 QA 첫 두 마을에서만 오배정이 여섯 나왔고 **전부 같은 모양**이었다(2026-08-11):
정발 한 엔트리를 PS1 여러 블록이 페이지 순서대로 나눠 물어야 하는데, 그중 한 블록이
**엉뚱한 엔트리로 점프**한다. 그러면 원래 물었어야 할 페이지가 **임자 없이 남는다.**

- 리젤 병사: `jp988` 이 `C_103#3` p2 를 무는데 **p0·p1 이 아무도 안 썼다** — 그 자리
  `jp986·987` 은 딴 표(`C_105#15`)를 물어 화면에 다른 대사가 나왔다.
- 마스쿤 폴스: `jp526·527` 이 `T_126#24` p2·p3 를 무는데 **p0·p1 이 비었다** — `jp524·525`
  가 `#22` 를 물어 **같은 문안이 두 번** 나왔다.

⚠ **기존 `past_find_page_gaps` 로는 안 잡힌다.** 그건 「안 쓰인 페이지 ↔ **미번역** 블록」을
짝짓는데, 이 부류는 **배정이 이미 붙어 있어서** 미번역이 아니다. 층이 다르다.

⚠ 구멍이 곧 오배정은 아니다 — 정발이 PS1 에 없는 페이지를 갖고 있으면 정상으로 남는다.
그래서 **꼬리 구멍(마지막 페이지 뒤)은 안 센다.** 쓰이는 페이지 **사이**만 본다.

  python3 tools/check_page_holes.py            # 씬별 요약
  python3 tools/check_page_holes.py -v         # 구멍 옆 블록이 무엇을 물고 있는지까지
"""

import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from common import OUT_DIR, ROOT
from patch_sys_ui import _scn_layout

_PAGE = re.compile(r"^(\d+)(~\d+)?(?:#(\d+))?")


def _used(scn):
    """{(표, 엔트리): {페이지: [eid …]}} — 지금 배정이 무는 자리."""
    amap = json.load(open(os.path.join(ROOT, "align_map.json"), encoding="utf-8")).get(scn, {})
    ovr = json.load(open(os.path.join(ROOT, "align_overrides.json"), encoding="utf-8")).get(scn, {})
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    variant, loose = set(), set()
    for k in set(amap) | set(ovr):
        o, a = ovr.get(k) or {}, amap.get(k) or {}
        table = o.get("table") or a.get("table")
        if not table or "ours" in o:
            continue
        chain = o.get("chain")
        if chain:
            for it in chain:
                m = _PAGE.match(str(it).lstrip("+"))
                if not m:
                    continue
                # ⚠ **변형(`~v`) 배정은 페이지가 아니다.** 리더별 대사 묶음(`19~1#0`)을
                # 페이지로 세면 「안 쓰인 변형」이 전부 구멍으로 뜬다 — SCN3 첫 판정에서
                # 후보 절반이 이것이었다(2026-08-11). 그 엔트리는 통째로 뺀다.
                if m.group(2):
                    variant.add((table, int(m.group(1))))
                ent = int(m.group(1))
                if m.group(3) is None:
                    # ⚠ `chain: [4, 5, 6, 7]` 처럼 **페이지 없이 엔트리만** 적은 항목은 그
                    # 엔트리를 통째로 쓴다 — p0 만 센 탓에 SCN1 후보 12곳 중 대부분이
                    # 이 오탐이었다(2026-08-11).
                    for pgi in range(max(1, len(_pages(table, ent)))):
                        out[(table, ent)][pgi].append(int(k))
                else:
                    out[(table, ent)][int(m.group(3))].append(int(k))
        else:
            # ⚠ **`chain` 없는 배정은 몇 페이지를 쓰는지 여기서 알 수 없다.** 엔트리를
            # 통째로 무는 경우와 창 수에 맞춰 p0 만 나가는 경우가 둘 다 있어서, 재조립 결과를
            # 봐야 갈린다. p0 만 센 뒤 **등급으로 가른다**(아래 `loose`) — 전체 사용으로
            # 세면 어부·밀매상 같은 진짜를 놓치고, p0 로만 세면 다중 페이지가 전부 뜬다.
            eid = o.get("entry_id", a.get("entry_id"))
            if eid is not None:
                out[(table, int(eid))][0].append(int(k))
                if len(_pages(table, int(eid))) > 1:
                    loose.add((table, int(eid)))
    for key in variant:
        out.pop(key, None)
    return out, loose


# 침묵 페이지 — 부호·제어코드만 든 정발 페이지. PS1 은 이 자리를 대개 `ours` 로 내므로
# 임자가 없어 보이지만 **결함이 아니다**(첫 전수에서 오탐 9곳 중 4곳이 이것이었다).
_SILENT = re.compile(r"^[\s.·・…！!\\x0-9A-Fa-f{}n/spk]*$")


def _pages(table, entry_id, cache={}):  # noqa: B006 — 표 로딩 캐시
    if table not in cache:
        p = os.path.join(OUT_DIR, "dos_kr", f"{table}.json")
        try:
            with open(p, encoding="utf-8") as f:
                cache[table] = {e["entry_id"]: e for e in json.load(f)["entries"]}
        except FileNotFoundError:
            cache[table] = {}
    e = cache[table].get(entry_id)
    if not e:
        return []
    return e["text"].removesuffix("{end}").split("{p}")


# 상점·정형 블록은 **공통 메시지로 처리하기로 했다**(유저 확정 2026-08-11) — 여러 맵이 같은
# 정발 엔트리를 나눠 쓰고 전용 빌더 관할이라 페이지가 남는 게 정상이다. 아이템·가격 주입
# 코드(`\x0E`·`` ` ``)나 `Gold` 가 든 엔트리로 가른다.
_SHOP = re.compile(r"\\x0[6E7]|`[0-9]|Gold|또 들러|또 오세요|어서 오십시|무기점|도구점|밀매상")


def _shop(table, entry_id):
    return any(_SHOP.search(p) for p in _pages(table, entry_id))


def _is_header(table, entry_id, page):
    """그 페이지가 **화자 헤더뿐**인가(`{spk}이름{/spk}` + 공백). 본문이 없으면 안 쓰여도 정상."""
    pg = _pages(table, entry_id)
    if page >= len(pg):
        return True
    body = re.sub(r"\{/?spk\}|\{n\}|\\x[0-9A-Fa-f]{2}", " ", pg[page])
    body = re.sub(r"\{spk\}[^{]*", " ", pg[page])
    return len(re.sub(r"\s+", "", body)) <= 8


def _silent(table, entry_id, page):
    """그 페이지가 **본문이 아닌가** — 부호뿐 · 화자 헤더뿐 · 한두 글자 조각.

    ⚠ 처음엔 한글 유무만 봤는데 `그 `(조각) · `{spk}대도 게일`(헤더뿐) 같은 페이지가
    A 로 떴다(SCN2·SCN5 판정에서 5곳 중 4곳이 이것이었다, 2026-08-11). 헤더는 **위치와
    무관하게** 빼고(p0 만 보면 안 된다), 본문은 한글 3자 이상일 때만 인정한다.
    """
    pg = _pages(table, entry_id)
    if page >= len(pg):
        return False
    body = re.sub(r"\{spk\}[^{]*\{/spk\}|\{spk\}[^{]*|\{/?spk\}", " ", pg[page])
    body = re.sub(r"\{n\}|\\x[0-9A-Fa-f]{2}|`[0-9]", " ", body)
    return len(re.findall(r"[가-힣]", body)) < 3


def candidates(scn):
    """[(표, 엔트리, 구멍 페이지, 무는 eid들, 등급)] — 한 씬의 후보. `scan` 과 같은 판정."""
    out = []
    used, loose = _used(scn)
    for (table, eid), pages in sorted(used.items()):
        if not pages:
            continue
        n = len(_pages(table, eid))
        gap = [p for p in range(n) if p not in pages] if n else []
        if not gap:
            continue
        gap = [g for g in gap if not _silent(table, eid, g)]
        if not gap:
            continue
        mid = [x for x in gap if any(pp < x for pp in pages)]
        head_only = len(gap) == 1 and gap[0] == 0 and _is_header(table, eid, 0)
        eids_all = sorted({e for v in pages.values() for e in v})
        spread = eids_all[-1] - eids_all[0] > 40 or _shop(table, eid)
        # ⚠ `chain` 없이 다중 페이지 엔트리를 무는 자리는 **뒷페이지의 임자가 불분명**해서
        # 구멍인지 아닌지를 여기서 못 가른다 → B 로 내린다(볼 값어치는 있다).
        grade = (
            None
            if spread
            else "B"
            if (table, eid) in loose
            else ("A" if (mid or len(gap) >= 2) else (None if head_only else "B"))
        )
        if grade:
            out.append((table, eid, gap, eids_all, grade))
    return out


def scan(verbose=False):
    tot, totB = 0, 0
    for scn, _lba, _size in _scn_layout():
        rows = candidates(scn)
        A = [r for r in rows if r[4] == "A"]
        B = [r for r in rows if r[4] == "B"]
        tot += len(A)
        totB += len(B)
        print(f"  {'✅' if not A else '⚠'} {scn}: A(본문 페이지 빔) {len(A)}곳 · B(볼 값어치) {len(B)}곳")
        for table, eid, gap, eids, g in (A + B if verbose else A):
            span = f"jp{eids[0]}~jp{eids[-1]}" if len(eids) > 1 else f"jp{eids[0]}"
            print(f"      [{g}] {table}#{eid}  p{','.join(map(str, gap))} 임자 없음  (무는 블록 {span})")
    print(
        f"\n{'✅ A 없음' if not tot else f'⚠ A(본문 페이지 빔) {tot}곳'} · B(볼 값어치) {totB}곳"
        "\n  ⚠ 구멍이 곧 오배정은 아니다 — 정발이 PS1 에 없는 페이지를 가진 자리도 있다."
        "\n     JP 원문과 대조해 판정한다."
    )
    return tot


def _where(scn, eid, cache={}):  # noqa: B006
    if scn not in cache:
        amap = json.load(open(os.path.join(ROOT, "align_map.json"), encoding="utf-8")).get(scn, {})
        ovr = json.load(
            open(os.path.join(ROOT, "align_overrides.json"), encoding="utf-8")
        ).get(scn, {})
        cache[scn] = (amap, ovr)
    amap, ovr = cache[scn]
    o, a = ovr.get(str(eid)) or {}, amap.get(str(eid)) or {}
    t = o.get("table") or a.get("table")
    if not t:
        return None
    return f"{t} {o.get('chain') or o.get('entry_id') or a.get('entry_id')}"


if __name__ == "__main__":
    sys.exit(1 if scan("-v" in sys.argv) else 0)
