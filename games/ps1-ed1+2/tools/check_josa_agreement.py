#!/usr/bin/env python3
"""조사가 앞 낱말의 **받침과 맞는지** 훑는다 — 받침 오류와 병기 누락을 잡는다.

세 축이다. 전부 「게임을 몰지 않고」 검출되고, 전부 **0건 유지**가 목표다.

**① 받침 불일치.** `여러분를` · `카드을` 처럼 조사가 앞 음절의 받침과 안 맞는 자리.

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

⚠ **①이 보는 것은 「우리 문안 전량」이다 — 2026-08-19 에 갈아탔다.** 그전엔 **정발 파생 표
전량**(`work/derived/dos_kr`)을 봤다. 그때는 그게 맞았다 — 문안이 정발에서 오니 오타도 정발에
있었고, 아직 배정 안 된 엔트리의 오타가 배정이 진행되며 하나씩 올라왔다(실측: 화면 코퍼스
0건인데 원문 전량엔 3건). **자체 번역으로 바뀌면서 그 전제가 무너졌다** — 오타는 이제 우리가
쓴 문안에 있고, 정발 표는 우리 문안의 원천이 아니다. 계속 정발을 보고 있었으면 **우리 문안
4,933블록의 조사 오류를 하나도 못 잡는다**(남의 문서를 검사하는 셈이다).

⚠ ②③(화면 코퍼스)과 ①(정본 전량)을 **여전히 가른다.** ①이 더 넓다 — ED2 처럼 아직 재삽입
체인 밖인 씬은 화면 코퍼스에 안 잡히지만 정본엔 이미 있다.

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
from common import ROOT

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
# textmap 전용 — 주입은 `%s`·`%d` 와 센티널뿐이다(`%c` 는 창·색 표식이라 뺀다).
RX_VAR_JOSA_TM = re.compile(
    f"(?:[{R.NAME_SENT}{R.NUM_SENT}{R.ITEM_SENT}]|%[sd])"
    rf"(?:%c)?({'|'.join(ALWAYS_OK)}|은|는|이|가|을|를|과|와|으로|로|면)(?!\()"
)
RX_VAR_TAIL = re.compile(f"(?:{VAR})[^가-힣]*$")


def batchim(ch):
    """종성 인덱스(0 = 받침 없음). 한글 음절이 아니면 None."""
    return (ord(ch) - 0xAC00) % 28 if "가" <= ch <= "힣" else None


# 마크업·센티널은 조회 전에 지운다 — 안 지우면 `\u2026을{p}` 이 한 낱말로 잡혀 오탐이 된다.
RX_MARKUP = re.compile(r"\{[^}]*\}|\\x[0-9A-Fa-f]{2}|[\x00-\x1f\ue000-\uf8ff]")


_JP_KEY = re.compile(r"[ぁ-んァ-ヶ一-龥]")  # 평탄 사전의 키 = JP 원문


def _walk_ours(o, name, game):
    """textmap 은 중첩이라 재귀로 `ours` 를 다 긁는다.

    🔴 **평탄한 `{JP: KR}` 사전도 본다**(2026-08-29). `monster_lines_ed2.json`(34) ·
    `monsters_ed2.json`(118)은 `ours` 키가 없는 평탄 사전이라 **파일이 통째로 안 보였다** —
    새턴 세션이 그 안에서 「변수 뒤 고정 조사」 둘을 찾아 줬는데 우리 게이트는 내내 ✅였다.
    ⚠ **로더가 못 보는 자료는 검사기가 아무리 많아도 안 걸린다.** 축을 늘리기 전에
    「그 축이 무엇을 읽는가」를 먼저 본다.
    """
    if isinstance(o, dict):
        t = o.get("ours")
        if isinstance(t, str) and t:
            yield game, name, RX_MARKUP.sub(" ", t)
        for k, v in o.items():
            # 평탄 사전: 키가 일본어(원문)이고 값이 문자열이면 그 값이 우리 문안이다.
            # ⚠ `_`·`_doc` 같은 머리말과 `sha`·`k` 같은 메타는 뺀다.
            if (
                k not in ("ours", "_", "_doc", "note", "sha", "k", "class")
                and isinstance(v, str)
                and v
                and _JP_KEY.search(k)
            ):
                yield game, name, RX_MARKUP.sub(" ", v)
            else:
                yield from _walk_ours(v, name, game)
    elif isinstance(o, list):
        for v in o:
            yield from _walk_ours(v, name, game)


def _ours_raw():
    """textmap 문안을 **마크업을 지우지 않고** 준다 — 축 ②는 `%s` 표식으로 판정한다.

    🔴 축 ②③(`scan_screen`)은 `_scn_layout()`(씬 파일)만 돌아서 **`textmap/` 을 아예 안
    봤다**(2026-08-29). ED2 몬스터 전투 대사(`monster_lines_ed2`)가 그 사각에 있었고,
    새턴 세션이 거기서 「변수 뒤 고정 조사」 둘을 찾아 줬는데 우리 게이트는 내내 ✅였다.
    ⚠ **축을 늘리기 전에 「그 축이 무엇을 읽는가」를 먼저 본다.**
    """
    for p in sorted(glob.glob(os.path.join(ROOT, "textmap", "*.json"))):
        name = os.path.splitext(os.path.basename(p))[0]
        from derive_text import materialize

        with open(p, encoding="utf-8") as f:
            d = materialize(json.load(f), name)

        def walk(o):
            if isinstance(o, dict):
                t = o.get("ours")
                if isinstance(t, str) and t:
                    yield t
                for k, v in o.items():
                    if (
                        k not in ("ours", "_", "_doc", "note", "sha", "k", "class")
                        and isinstance(v, str)
                        and v
                        and _JP_KEY.search(k)
                    ):
                        yield v
                    else:
                        yield from walk(v)
            elif isinstance(o, list):
                for v in o:
                    yield from walk(v)

        for t in walk(d):
            yield name, t


def _ours_lines():
    """**우리 문안 전량** — (게임, 출처, 텍스트).

    \u26a0 원천이 둘이다. `script/` 만 보면 시스템\u00b7전투\u00b7오프닝을 통째로 놓친다.
    """
    for p in sorted(glob.glob(os.path.join(ROOT, "script", "ED*SCN*.json"))):
        scn = os.path.splitext(os.path.basename(p))[0]
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        for eid, v in d.items():
            t = (v or {}).get("t")
            if isinstance(t, str) and t:
                yield scn[:3], f"{scn}:{eid}", RX_MARKUP.sub(" ", t)
    for p in sorted(glob.glob(os.path.join(ROOT, "textmap", "*.json"))):
        name = os.path.splitext(os.path.basename(p))[0]
        game = "ED2" if name.endswith("_ed2") else "ED1"
        from derive_text import materialize

        with open(p, encoding="utf-8") as f:
            yield from _walk_ours(materialize(json.load(f), name), name, game)


def scan_agreement():
    """\u2460 받침 불일치 — **우리 문안 전량**을 본다.

    \u26a0 `spell_fix` 를 안 먹인다 \u2014 그건 정발 파생 텍스트를 고치는 층이고, 우리 정본은 이미
    최종 문안이다. 먹이면 「검사기가 고쳐서 통과」가 되어 오류를 숨긴다.
    """
    hits = collections.Counter()
    where = {}
    for _game, name, t in _ours_lines():
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
    # 🔴 **textmap 도 본다** — 위 루프는 씬 파일만 돈다(2026-08-29 구멍).
    # ⚠ 여기서는 **`%c` 를 변수로 치지 않는다.** 씬 경로는 `load_translations` 가 `%c` 를
    #   창·색 표식으로 풀어 주지만 textmap 원문에는 글자 그대로 남아, `%c레이시아%c가`
    #   처럼 **리터럴 이름**까지 주입으로 오인한다(실측 22건 중 20이 그 꼴이었다).
    #   진짜 주입은 `%s`·`%d` 다.
    for name, t in _ours_raw():
        for m in RX_VAR_JOSA_TM.finditer(t):
            if m.group(1) in ALWAYS_OK:
                continue
            k = (name, m.group(1))
            bare[k] += 1
            bw.setdefault(k, ("-", t[max(0, m.start() - 12) : m.end() + 12]))
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
