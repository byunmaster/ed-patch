#!/usr/bin/env python3
"""조사가 앞 낱말의 **받침과 맞는지** 훑는다 — 정발 오타와 병기 누락을 잡는다.

세 축이다. 전부 「게임을 몰지 않고」 검출되고, 전부 **0건 유지**가 목표다.

**① 받침 불일치(정발 오타).** `여러분를` · `카드을` 처럼 조사가 앞 음절의 받침과 안 맞는
자리. 정발 원문에 실재하는 오타라 `dos_spelling_fixes` 로 교정한다(유저 방침: 정발 우선이되
맞춤법은 교정).

⚠ **은/는·이/가·과/와는 못 본다.** 관형사형 어미와 조사를 어휘만으로 못 가르기 때문이다 —
`먹는`·`있는`·`없는` 이 전부 「받침 뒤 는」이라 받침 규칙으로는 오탐이 된다(실측: 645건 중
645건이 오탐, 상위가 있는 336 · 없는 75 · 않는 37). `과/와` 도 `사과`·`효과`·`결과` 에서
같은 일이 난다. 그래서 **을/를 한 축만** 본다 — 여기선 관형사형(`먹을`·`잡을`)이 항상 받침
뒤라 규칙과 충돌하지 않는다. 남는 오탐은 단일 형태소(`마을`·`가을`)뿐이라 STOP 으로 끊는다.

**② 변수 뒤 고정 조사(병기 누락).** 이름·아이템이 주입되는 슬롯 바로 뒤에 조사가 **한 형태로**
박힌 자리. 주입값의 받침이 매번 달라지므로 병기(`은(는)`)로 써야 런타임 훅이 푼다
(`patch_josa_hook`). 훅이 아는 쌍은 **은(는)·이(가)·을(를) 셋뿐**이라, 그 밖의 조사가
필요하면 문안을 셋 안으로 고쳐 쓰거나 **받침 양쪽에 다 붙는 꼴**로 쓴다(`ALWAYS_OK`).

**③ 고정 명사 뒤 병기(낭비).** ②의 반대다 — 앞말이 **안 변하는데** 병기로 써 둔 자리.
받침이 빌드 시점에 정해져 있으므로 미리 확정해 쓴다(유저 확정 2026-08-17). 병기는 폭을
한 슬롯 더 먹고 런타임 판정까지 도는데 얻는 게 없다. ⚠ **블록 맨 앞의 병기는 정상**이다 —
엔진이 그 앞에 이름을 붙여 넣는다(`을(를) 샀습니다.`). 실측 98자리 중 48 = 변수 뒤,
50 = 블록 선두였고 낭비는 0건이었다. 0을 **유지**하려고 두는 축이다.

⚠ **①은 정발 원문 전량을 본다.** 배정된 문안만 보면 늦다 — 오타는 아직 화면에 안 나온
엔트리에 있다가 **배정이 진행되면서 하나씩 올라온다**(실측: 화면 코퍼스 0건인데 원문 전량엔
3건). 그래서 이 검사는 한 번 훑고 끝낼 일이 아니라 상주 게이트다.

  python3 tools/check_josa_agreement.py        # 세 축 → 어긋나면 종료코드 1
  python3 tools/check_josa_agreement.py -v     # 자리마다 앞뒤 문맥까지
"""

import argparse
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from common import OUT_DIR

# 을/를 를 품은 단일 형태소 — 조사가 아니라 낱말의 일부다.
STOP = ("마을", "가을", "겨을", "서울", "나을", "이을", "그을", "졸을", "잘을")

RX_EULREUL = re.compile(r"([가-힣])(을|를)(?=[\s,.!?」』…”\"'()\\]|$)")

# 이름·수치·아이템 주입 슬롯 + 서식 인자. 뒤에 `(` 가 오면 이미 병기라 통과.
VAR = f"[{R.NAME_SENT}{R.NUM_SENT}{R.ITEM_SENT}]|%[csd]|`[0-9{{]"

# 받침 양쪽에 다 붙는 꼴 — 훅이 없어도 되니 통과시킨다(유저 확정 2026-08-17: `이면` 으로
# 통일. `해독초이면` 이 조금 늘어질 뿐 틀리지 않고, `검이면` 도 맞다). ⚠ **긴 것을 먼저**
# 둬야 한다 — 정규식 교체는 왼쪽 우선이라 `이` 가 앞서면 `이면` 을 못 보고 오탐한다.
ALWAYS_OK = ("이면",)
RX_VAR_JOSA = re.compile(
    f"(?:{VAR})({'|'.join(ALWAYS_OK)}|은|는|이|가|을|를|과|와|으로|로|면)(?!\\()"
)

RX_BYUNGI = re.compile(r"은\(는\)|이\(가\)|을\(를\)")
RX_VAR_TAIL = re.compile(f"(?:{VAR})[^가-힣]*$")


def batchim(ch):
    """종성 인덱스(0 = 받침 없음). 한글 음절이 아니면 None."""
    return (ord(ch) - 0xAC00) % 28 if "가" <= ch <= "힣" else None


def _dos_lines():
    """정발 파생 표 전량 — (표이름, 텍스트)."""
    for p in sorted(glob.glob(os.path.join(OUT_DIR, "dos_kr", "*", "*.json"))):
        game = os.path.basename(os.path.dirname(p))
        name = f"{game}/{os.path.splitext(os.path.basename(p))[0]}"
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        for e in d if isinstance(d, list) else d.get("entries", []):
            t = e.get("text") if isinstance(e, dict) else None
            if isinstance(t, str):
                yield game, name, t


def scan_agreement():
    """① 받침 불일치 — 교정 규칙을 **먹인 뒤** 본다(고친 게 실제로 먹었는지까지 검증)."""
    hits = collections.Counter()
    where = {}
    for game, name, raw in _dos_lines():
        t = R.spell_fix(raw, game)
        for m in RX_EULREUL.finditer(t):
            prev, j = m.group(1), m.group(2)
            b = batchim(prev)
            if b is None:
                continue
            if (b != 0) if j == "을" else (b == 0):
                continue
            w = t[max(0, m.start() - 3) : m.end()]
            if any(s in w for s in STOP):
                continue
            k = prev + j
            hits[k] += 1
            where.setdefault(k, (name, t[max(0, m.start() - 24) : m.end() + 14]))
    return hits, where


def scan_screen():
    """②③ 화면에 실리는 문안만 본다(주입은 배정된 자리에서만 일어난다). 한 번만 훑는다."""
    from spellcheck_render import _scn_layout

    bare, waste = collections.Counter(), collections.Counter()
    bw, ww = {}, {}
    for name, _lba, _size in _scn_layout():
        tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
        for eid, v in sorted(tr.items()):
            if not isinstance(v, tuple) or len(v) < 2 or not isinstance(v[1], list):
                continue
            for _, page in v[1]:
                if not isinstance(page, str):
                    continue
                for m in RX_VAR_JOSA.finditer(page):
                    if m.group(1) in ALWAYS_OK:
                        continue
                    k = (name, m.group(1))
                    bare[k] += 1
                    bw.setdefault(k, (eid, page[max(0, m.start() - 12) : m.end() + 12]))
                for m in RX_BYUNGI.finditer(page):
                    pre = page[: m.start()]
                    # 변수가 앞에 있거나(주입) 블록 맨 앞이면(엔진이 앞에 붙인다) 정상.
                    if not pre.strip() or RX_VAR_TAIL.search(pre):
                        continue
                    k = (name, pre[-1:], m.group(0))
                    waste[k] += 1
                    ww.setdefault(k, (eid, page[max(0, m.start() - 14) : m.end() + 8]))
    return (bare, bw), (waste, ww)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    bad = 0
    hits, where = scan_agreement()
    n = sum(hits.values())
    if n:
        bad += 1
        print(f"  ❌ 받침 불일치 {n}건 — dos_spelling_fixes 에 교정 쌍을 넣는다")
        for k, c in hits.most_common():
            name, ctx = where[k]
            print(f"     {k} ×{c}  {name}" + (f"  {ctx!r}" if a.verbose else ""))
    else:
        print("  ✅ 받침 불일치 없음 (을/를 축)")

    (hits, where), (waste, ww) = scan_screen()
    n = sum(hits.values())
    if n:
        bad += 1
        print(f"  ❌ 변수 뒤 고정 조사 {n}건 — 병기로 쓰거나 훅이 아는 쌍으로 고쳐 쓴다")
        for (name, j), c in hits.most_common():
            eid, ctx = where[(name, j)]
            print(f"     {name}:{eid} …{j!r} ×{c}" + (f"  {ctx!r}" if a.verbose else ""))
    else:
        print("  ✅ 변수 뒤 고정 조사 없음")

    n = sum(waste.values())
    if n:
        bad += 1
        print(f"  ❌ 고정 명사 뒤 병기 {n}건 — 받침이 안 변하니 미리 확정해 쓴다")
        for (name, last, j), c in waste.most_common():
            eid, ctx = ww[(name, last, j)]
            print(f"     {name}:{eid} {last!r}+{j} ×{c}" + (f"  {ctx!r}" if a.verbose else ""))
    else:
        print("  ✅ 고정 명사 뒤 병기 없음")

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
