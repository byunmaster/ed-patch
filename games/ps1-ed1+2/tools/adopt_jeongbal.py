#!/usr/bin/env python3
"""**정발이 이기는 자리를 기계로 골라 포인터로 되돌린다** — 전수 대조의 기계 몫.

판정 규칙은 `docs/policy.md` 「정발 전수 대조」다. 그중 **읽지 않아도 규칙이 자동으로
적용되는 구간**만 여기서 처리한다 — 뜻이 같고(어간이 겹치고) 길이가 1:1 이면 규칙 ①이
그대로 성립한다. 나머지(뜻이 갈리는 구간·정발 한 엔트리가 여러 블록에 걸치는 구간)는
사람이 읽어야 한다.

**정발 채택 = `script/` 의 `t` 삭제**다. 그러면 배정(정발 포인터)이 살아나고, 문안은
리포에 안 남는다 — 저작권 체계와 같은 방향이다(`t` 에 베껴 적으면 정반대가 된다).

## 🔴 후보는 **장소·시기·화자**를 다 통과해야 한다 (유저 확정 2026-08-17, 재확인)

    장소·시기   그 블록이 쓰는 정발 표. 표가 곧 시점이다(T_011 루디아#2 vs T_013 루디아#4)
    화자        JP 헤더 전파 ↔ 정발 엔트리의 `{spk}이름{/spk}`
    의미        **JP 원문을 읽어서** 판정한다 — 유사도는 후보를 줄이는 데만 쓴다

⚠ **이건 습관이 아니라 코드가 강제한다.** 규칙은 방침 문서에도 메모리에도 있었는데, 새
도구를 짤 때마다 유사도만 재고 화자를 빠뜨렸다(2026-08-17 하루에 두 번). 그래서 후보를
내는 문을 `match()` 하나로 좁히고 `axes_ok()` 를 그 앞에 세웠다. **저수준 `best_slice` 를
채택 경로에서 직접 부르지 말 것** — 게이트가 없어 표 전체를 훑는다.

## 왜 문자열 유사도가 아니라 어간인가

`외출하십니까` vs `외출하시나요` 는 뜻이 같은데 문자열로 재면 어미 때문에 점수가 깎인다.
어절 앞 2음절만 보면(조사·어미를 버리면) 이런 짝이 제대로 붙는다 — 사전 없이 쓰는 근사지만
「내용어가 같은가」라는 물음에는 충분하다. ⚠ 반대로 **어간이 갈리면 뜻이 갈린 것**이므로
자동 채택에서 뺀다.

## 자동으로 빼는 것

- **용어 정본의 금지어가 정발에 있는 자리**(`용자`·`마법`·`체력` …) — 규칙 ④(일관성)와
  부딪힌다. 정발을 받아들이면 `check_terms` 가 실패한다.
- **락이 걸린 블록** — 인게임 확인분이라 사람이 판단한다.
- **길이가 1:1 이 아닌 자리** — 정발 한 엔트리가 PS1 여러 블록에 걸치는 꼴이라
  `t` 삭제만으로는 안 되고 조각내기(`chain`/`subs`)가 필요하다.

## 넣어 보고 깨지면 되돌린다

정발 문안이 우리 것보다 길면 **슬롯을 넘거나 씬이 부풀어 다른 블록이 앵커를 침범**한다
(실측: ED2SCN1 은 총 +26자만으로 4블록이 밀렸다). 그래서 적용 → 빌드 → **이번에 넣은 것
중 탈락한 자리만 되돌림** → 재빌드까지가 한 벌이다. 사람이 하면 매번 샌다.

  python3 tools/adopt_jeongbal.py --dry            # 후보만 센다
  python3 tools/adopt_jeongbal.py                  # 적용 + 되돌림까지
  python3 tools/adopt_jeongbal.py --sim 0.6        # 문턱을 낮춘다(⚠ 확인 필요해진다)
"""

import argparse
import collections
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from align_map import scene_map
from check_terms import TERMS
from common import OUT_DIR, ROOT

BAD_TERMS = [b for _c, bad, _w in TERMS.values() for b in bad]

_HDR = re.compile(r"\{c\}([^{]+)\{c\}")
_SPK = re.compile(r"^\{spk\}([^{]+)\{/spk\}")


def own_table(scn, eid, ignore=None):
    """🔴 **장소·시기** — 그 블록이 쓰는 정발 표. 없으면 `(None, None)`.

    ⚠ `ignore` 는 **믿으면 안 되는 배정**을 거르는 술어다(note 를 받아 True 면 무시).
    폐기된 규칙이 박아 둔 좌표를 되돌릴 때 이게 없으면 **순환**한다 — 그 블록의 잘못된
    배정을 「자기 표」로 읽어 제자리를 맴돈다(실측: 같은 가게의 이웃 블록이 `T_333` 과
    `T_011` 로 갈렸다). 앞 헤더를 거슬러 갈 때도 같은 술어를 태운다 — 이웃도 오염돼 있다.

    표가 곧 시점이다(`T_011` 루디아#2 vs `T_013` 루디아#4 — 1장엔 왕자를 못 알아보고
    2장부터 알아본다). 그래서 표만 맞추면 장소와 시기가 같이 맞는다.

    배정이 없으면 **바로 앞 화자 헤더 블록**의 배정을 쓴다 — 대사는 `{c}이름{c}` 인사
    뒤에 붙으므로 이게 가장 국소적이고 확실하다(실측 2026-08-17: 369블록 중 244를 이걸로
    잡았다). ⚠ 시점을 넓게 추정하지 말 것 — `ed1-scene-map.md` 의 시점 열은 54%만 맞고,
    이웃 배정은 그 이웃이 다른 표를 가리키고 있으면 통째로 오염된다.
    """
    ov = _overrides()
    e = (ov.get(scn) or {}).get(str(eid))
    if isinstance(e, dict) and e.get("table") and not (ignore and ignore(e.get("note") or "")):
        return e["table"], "자기배정"
    # ⚠ `scene_map` 은 **int 키**다 — `str(eid)` 로만 찾으면 배정이 있는데도 「표 없음」이
    # 된다(2026-08-18 실측: 그래서 게이트가 조용히 후보를 안 냈다). 둘 다 본다.
    pin = scene_map(scn) or {}
    m = pin.get(eid) or pin.get(str(eid))
    if isinstance(m, dict) and m.get("table"):
        return m["table"], "자기배정"
    jp = _jp(scn)
    for d in range(1, 40):
        if _HDR.match(jp.get(eid - d, "")):
            t, _ = own_table(scn, eid - d, ignore)
            return (t, "앞 헤더") if t else (None, None)
    return None, None


def axes_ok(scn, eid, table, entry_id, page=0, ours=None, dos=None):
    """🔴 **장소·시기·화자가 다 맞아야 후보다** (유저 재확인 2026-08-17).

    ⚠ **이 문을 거치지 않는 매칭을 만들지 말 것.** 규칙은 방침 문서에도 메모리에도 있는데,
    도구를 새로 짤 때마다 유사도만 재고 화자를 빠뜨렸다(2026-08-17 두 번). 기억에 맡기면
    반복되므로 **코드가 강제**한다 — 후보 생성기는 전부 여기를 통과시킨다.

    유사도는 **후보를 줄이는 데만** 쓴다. 판정 기준은 JP 원문이다(우리 문안은 기준이 아니라
    결과물이라, 같은 뜻이어도 안 닮는다).

    돌려주는 값: (통과 여부, 사유).
    """
    if not table:
        return False, "장소 없음(표를 못 찾음)"
    own, _how = own_table(scn, eid)
    if own and table != own:
        return False, f"장소·시기 어긋남(자기 표 {own} ≠ {table})"
    if dos and ours and verbatim(dos, ours):
        return True, "축자 동일(1급 규칙 — 화자 불일치를 덮는다)"
    jp_spk = _jp_speaker(scn, eid)
    dos_spk = dos_speaker(table, entry_id)
    if page or not jp_spk or not dos_spk:
        return True, "화자 판정 불가(없는 것과 다른 것은 다르다)"
    if not speaker_ok(jp_spk, dos_spk):
        return False, f"화자 다름(JP {jp_spk} ≠ 정발 {dos_spk})"
    return True, "장소·시기·화자 일치"


def dos_speaker(table, eid):
    """정발 엔트리의 화자 — **헤더가 없으면 앞 엔트리에서 잇는다**(JP 쪽과 같은 꼴).

    ⚠ 헤더(`{spk}이름{/spk}`)는 대화의 **첫 엔트리에만** 붙는다. 이어지는 엔트리를 헤더로만
    보면 화자가 없어 보여서, 화자 축이 대부분 「판정 불가」로 빠져 버린다(실측 2026-08-17:
    후보의 8할이 그랬다) — 그럼 축을 세워 둔 의미가 없다.

    ⚠ 그래도 **추정이다.** 정발도 한 엔트리에 여러 사람 대사를 담고(그래서 `page` 가 0 이
    아니면 판정을 접는다), 대사가 오가는 장면에서는 전파가 틀린다. 후보를 줄이는 데 쓰고
    최종 판정은 JP 원문으로 한다.
    """
    key = ("spk", table)
    if key not in _CACHE:
        cur, out = None, {}
        for e in range(200):
            t = dos_text(table, e)
            if t is None:
                continue
            m = _SPK.match(t)
            if m:
                cur = m.group(1)
            out[e] = cur
        _CACHE[key] = out
    return _CACHE[key].get(eid)


_OVC, _JPC, _SPC = {}, {}, {}


def _overrides():
    if "d" not in _OVC:
        _OVC["d"] = json.load(open(os.path.join(ROOT, "align_overrides.json"), encoding="utf-8"))
    return _OVC["d"]


def _jp(scn):
    if scn not in _JPC:
        p = os.path.join(OUT_DIR, "scn_jp", f"{scn}.json")
        d = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"entries": []}
        _JPC[scn] = {e["entry_id"]: (e.get("text") or "") for e in d["entries"]}
    return _JPC[scn]


def _jp_speaker(scn, eid):
    """JP 쪽 화자 — 헤더 전파(`jp_speaker`). ⚠ 추정이라 **후보 좁히기용**이다."""
    if scn not in _SPC:
        from jp_speaker import speakers

        _SPC[scn] = speakers(scn)
    return (_SPC[scn].get(eid) or (None, None, 0))[0]


def verbatim(a, b):
    """정발과 우리 문안이 **축자 동일**인가 — 다른 모든 판정을 덮는 1급 규칙.

    ⚠ 축자 동일이면 두 가지가 동시에 참이다. ① **짝이 맞다** — 우연히 같아질 문장이 아니다.
    ② **베낀 자리다** — 정발 후보를 옆에 놓고 그대로 옮겨 적었다는 뜻이라, 리포에 정발
    문안이 남는 저작권 문제이기도 하다. 그래서 무조건 포인터로 되돌린다.

    ⚠ **화자 불일치보다 우선한다.** 정발 엔트리 헤더의 화자는 첫 페이지의 것이라 뒤 페이지엔
    안 맞고, 정발이 화자를 다르게 적어 둔 자리도 있다 — 실측(2026-08-17)에서 `セリオス`
    자리에 정발 화자가 `라이아스`·`베라미스`·`도둑` 인데 **문안은 글자까지 같았다**.
    문안이 같은데 화자가 다르다고 버리면 멀쩡한 짝을 잃는다.

    ⚠ **공백은 무시한다.** 정발은 `{n}` 줄바꿈 자리에 공백을 안 넣는데(`부상자는대체 어디에
    있는거야?`) 우리는 띄어 쓴다 — 그 차이만으로 축자 판정이 빗나가면, **베껴 적고 띄어쓰기만
    다듬은 자리**가 통째로 「짝 없음」으로 빠진다(실측 2026-08-18: 53건 중 대부분이 이것이었다).
    저작권에서도 표현이 문제지 공백이 문제가 아니다.
    """
    return bool(a) and _nows(clean(a)) == _nows(clean(b))


def _nows(s):
    return re.sub(r"\s+", "", str(s))


def speaker_ok(jp_spk, kr_spk, page=0):
    """정발 짝의 **화자가 같은 사람인가** — 어간만 보면 남의 대사를 물어 온다.

    ⚠ 실측(2026-08-17): 어간 유사도만으로 52건을 채택했더니 **6건이 다른 인물**이었다 —
    `セリオス`(세리오스) 자리에 정발 `라이아스`·`베라미스`·`도둑` 대사가 들어왔다.
    정발엔 **같은 상황을 여러 인물이 말하는 자리**가 있어 낱말이 겹치고, 어간 필터는
    그걸 못 가른다. 장소(씬↔표 매핑)와 시기(정렬 순서)는 정렬기가 보지만 **화자는
    채택 단계에서 다시 봐야 한다.**

    ⚠ 접미(`~の手下`)를 안 태우면 멀쩡한 짝을 자른다(`ゴードンの手下` → `고돈` 으로 읽혀
    정발 `고든의 부하` 와 어긋나 보였다). `SUFFIX_RULES` 를 먼저 적용한다.

    한쪽에 화자 정보가 없으면 **판정하지 않는다**(True) — 없는 것과 다른 것은 다르다.

    ⚠ **정발 엔트리 하나에 여러 사람 대사가 들어 있다.** 헤더 화자는 **첫 페이지의 것**이라,
    뒤 페이지를 집어 쓸 때 대면 멀쩡한 짝이 어긋나 보인다(실측: `セリオス` 자리에 정발 화자가
    `라이아스`·`도둑` 인데 **문안은 축자 동일**이었다). 그래서 부르는 쪽이 `page` 를 준다 —
    0 이 아니면 헤더 화자로 판정하지 않는다.
    """
    from align_jp_kr import SPEAKER_DICT, SUFFIX_RULES, kana_to_hangul, name_sim

    if not jp_spk or not kr_spk or page:
        return True
    for jp_suf, kr_suf in SUFFIX_RULES:
        if jp_spk.endswith(jp_suf):
            base = jp_spk[: -len(jp_suf)]
            head = SPEAKER_DICT.get(base) or kana_to_hangul(base)
            return bool(head) and name_sim(head + kr_suf, kr_spk) >= 0.6
    ours = SPEAKER_DICT.get(jp_spk) or kana_to_hangul(jp_spk)
    return not ours or ours == kr_spk or name_sim(ours, kr_spk) >= 0.6


LEN_LO, LEN_HI = 0.7, 1.4  # 1:1 로 볼 길이비
_CACHE = {}


def dos_text(table, eid):
    """정발 엔트리 문안 — `work/derived/dos_kr/<표>.json` 에서."""
    if table not in _CACHE:
        p = os.path.join(OUT_DIR, "dos_kr", *table.split("/")) + ".json"
        _CACHE[table] = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
    d = _CACHE[table]
    if d is None:
        return None
    for e in d if isinstance(d, list) else d.get("entries", []):
        if e.get("entry_id") == eid or e.get("id") == eid:
            return e.get("text")
    return None


def slices(table, eid):
    """정발 엔트리를 **파이프라인과 같은 방식으로** 쪼갠다 — [(page, sent, 문안)].

    ⚠ 1:1 은 **엔트리가 아니라 문장 단위**로 성립한다(2026-08-17 실측). 정발은 한 화면에
    몰아 넣고 리메이크가 여러 블록으로 나눈 자리가 많다 — 여관주인 `T_040#24` 하나에
    인사·요금·확인·작별이 다 들어 있고 PS1 은 여섯 블록이다. 엔트리째 대면 어느 것도 안 붙는다.

    ⚠ **쪼개는 규칙을 직접 짜지 않는다.** `reinsert_kr_pilot._sentences` 가 정본이고,
    `chain: '<eid>#<page>.<sent>'` 이 그걸로 잘라 낸다 — 여기서 다르게 쪼개면 제안한 좌표와
    실제로 나가는 문안이 어긋난다. (직접 짰다가 `{n}` 을 문장 경계로 써서 `그래서 이 코로가
    자식을 대신` 에서 잘렸다. `{n}` 은 줄바꿈이지 문장 끝이 아니다.)
    """
    import reinsert_kr_pilot as R

    raw = dos_text(table, eid)
    if not raw:
        return []
    out = []
    for pi, page in enumerate(str(raw).removesuffix("{end}").split("{p}")):
        for si, sent in enumerate(R._sentences(page)):
            t = clean(sent)
            if t:
                out.append((pi, si, t))
    return out


def match(scn, eid, ours, tables=None):
    """🔴 **후보를 내는 유일한 문**이다 — 장소·시기·화자를 통과한 것만 돌려준다.

    돌려주는 값: [{score, coord, dos, table, ok, why}] — 통과한 것이 먼저, 그 안에서 점수순.

    ⚠ **잘린 것도 같이 돌려준다**(`ok=False`). 화자 축은 정발 쪽 전파가 틀릴 수 있어 오탐이
    있다(실측: `セリオス` 자리를 정발이 `소니아` 로 이어받아 문안은 같은데 잘렸다). 잘린 건
    **버리는 게 아니라 사람이 읽을 줄**로 보낸다 — 조용히 없애면 「다 봤다」로 읽힌다.

    ⚠ **`best_slice` 를 직접 부르지 말 것.** 그건 게이트가 없는 저수준 탐색이라, 표 전체를
    훑어 남의 화자 대사를 물어 온다. 2026-08-17 에 두 번 그렇게 했다 — 규칙은 방침 문서에도
    메모리에도 있었는데 도구를 새로 짤 때마다 유사도만 쟀다. 그래서 문을 하나로 좁혔다.

    ⚠ 점수는 **후보를 줄이는 데만** 쓴다. 최종 판정은 **JP 원문을 읽어서** 한다 — 우리 문안은
    기준이 아니라 결과물이라 같은 뜻이어도 안 닮는다.
    """
    if tables is None:
        t, _how = own_table(scn, eid)
        tables = [t] if t else []
    out = []
    for tbl in tables:
        if not tbl:
            continue
        for e in range(120):
            if dos_text(tbl, e) is None:
                continue
            sc, coord, dos = best_slice(tbl, e, ours)
            if not coord or sc <= 0:
                continue
            page = int(str(coord).partition("#")[2].partition(".")[0] or 0)
            ok, why = axes_ok(scn, eid, tbl, e, page=page, ours=ours, dos=dos)
            out.append(dict(score=round(sc, 3), coord=coord, dos=dos, table=tbl, ok=ok, why=why))
    return sorted(out, key=lambda c: (c["ok"], c["score"]), reverse=True)


def best_slice(table, eid, ours):
    """엔트리 안에서 우리 문안에 가장 잘 붙는 **문장 구간**을 찾는다 — (chain 좌표, 정발문안, 점수).

    ⚠ **저수준이다 — 채택 경로에서 직접 부르지 말 것.** 게이트(`axes_ok`)가 없어 표 전체를
    훑는다. 후보가 필요하면 `match()` 를 쓴다.

    ⚠ 한 문장만 보면 안 된다. 정발이 `그렇습니까.` / `그럼 다음에 또 들러 주시기를.` 로
    끊어 둔 것을 PS1 이 한 블록에 담는 자리가 있다 — `chain` 이 `0.3-4` 로 **구간**을
    받으므로 이웃 문장을 이어 붙인 후보도 같이 잰다(같은 페이지 안에서만).
    """
    sl = slices(table, eid)
    best = (0.0, None, "")
    for i, (pi, si, _t) in enumerate(sl):
        buf = []
        for j in range(i, min(i + 4, len(sl))):
            if sl[j][0] != pi:
                break
            buf.append(sl[j][2])
            txt = " ".join(buf)
            sc = stem_sim(txt, ours)
            if verbatim(txt, ours):
                sc = 1.0
            if sc > best[0]:
                span = f"{si}" if j == i else f"{si}-{sl[j][1]}"
                best = (sc, f"{eid}#{pi}.{span}", txt)
    return best


def clean(t):
    """비교용 정규화 — 제어·마크업을 걷어낸다.

    ⚠ **화자 마크업을 반드시 먼저 뗀다.** 정발은 `신부{/spk}곤란한 일이…` 처럼 이름을
    본문 앞에 얹어 두는데, 안 떼면 그 이름이 길이와 어간에 섞여 멀쩡한 짝이 문턱 아래로
    떨어진다 — 실측(2026-08-17): 신부 대사 27블록이 이것 때문에 자동 채택에서 빠졌다.
    """
    t = str(t)
    t = re.sub(r"\{spk\}.*?\{/spk\}", "", t)  # {spk}이름{/spk}
    t = re.sub(r"^[^{]*\{/spk\}", "", t)  # 이름{/spk} (여는 태그가 없는 꼴)
    t = re.sub(r"\\x[0-9a-fA-F]{2}|\{/?[a-z]+\}", "", t)
    return re.sub(r"\s+", " ", t).strip()


def stems(t):
    """어절 앞 2음절 — 조사·어미 차이를 지운다(사전 없이 쓰는 근사)."""
    out = []
    for w in re.sub(r"[^\w가-힣%\s]", " ", t).split():
        w = re.sub(r"[^가-힣A-Za-z0-9%]", "", w)
        if w:
            out.append(w[:2])
    return out


def stem_sim(a, b):
    A, B = collections.Counter(stems(a)), collections.Counter(stems(b))
    if not A or not B:
        return 0.0
    return 2 * sum((A & B).values()) / (sum(A.values()) + sum(B.values()))


def candidates(threshold, games=("ED1",)):
    """[(씬, eid, 정발, 우리)] — 자동 채택해도 되는 자리."""
    locks = json.load(open(os.path.join(ROOT, "locked_lines.json"), encoding="utf-8"))["_settled"]
    out, skipped = [], collections.Counter()
    for p in sorted(glob.glob(os.path.join(ROOT, "script", "*SCN*.json"))):
        scn = os.path.basename(p)[:-5]
        if not any(scn.startswith(g) for g in games):
            continue
        canon = json.load(open(p, encoding="utf-8"))
        pin = scene_map(scn) or {}
        lk = locks.get(scn, {})
        for k, v in canon.items():
            t = (v.get("t") or "").strip()
            m = pin.get(str(int(k))) or pin.get(int(k))
            if not t or not m:
                continue
            d = clean(dos_text(m["table"], m["entry_id"]))
            if not d:
                continue
            if not (LEN_LO <= len(d) / max(len(t), 1) <= LEN_HI):
                skipped["길이 다름(조각내기 필요)"] += 1
                continue
            if stem_sim(d, t) < threshold:
                skipped["어간이 갈린다(사람이 읽는다)"] += 1
                continue
            if any(b in d for b in BAD_TERMS):
                skipped["용어 정본과 충돌"] += 1
                continue
            if k in lk:
                skipped["락(인게임 확인분)"] += 1
                continue
            # 🔴 장소·시기·화자 — 유사도를 통과해도 이 문을 못 넘으면 후보가 아니다
            ok, why = axes_ok(scn, int(k), m["table"], m["entry_id"], ours=t, dos=d)
            if not ok:
                skipped[why.split("(")[0]] += 1
                continue
            out.append((scn, k, d, t))
    return out, skipped


def _write(scn, mutate):
    p = os.path.join(ROOT, "script", f"{scn}.json")
    d = json.load(open(p, encoding="utf-8"))
    mutate(d)
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def build_drops():
    """빌드하고 **화면에 일본어가 남는** 탈락 자리를 돌려준다 — {(씬, eid): 사유}."""
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "build.py")],
        capture_output=True,
        text=True,
        cwd=os.path.join(ROOT, "tools"),
        check=False,  # 실패도 결과다 — 탈락 목록을 읽으려고 부른다
    )
    drops = {}
    # ⚠ 빌드는 탈락 목록을 **stderr 로도** 낸다 — stdout 만 보면 되돌림이 조용히 안 걸린다
    # (실측 2026-08-17: 「최종 채택 91건」이라 해 놓고 두 블록이 일본어로 남아 있었다).
    for m in re.finditer(r"^\s+(ED[12]SCN\d+) jp(\d+): (\w+)$", r.stdout + r.stderr, re.MULTILINE):
        if m.group(3) in ("anchor_overlap", "mid_block_ref", "anchor_tail_size"):
            continue  # 배치 사유라 문안과 무관하다
        drops[(m.group(1), m.group(2))] = m.group(3)
    return r.returncode, drops


def flip_all(games, scenes=None):
    """**배정이 있는 블록은 전부 정발로 둔다** — 08-12 방침의 기본값 복원.

    ⚠ 방침은 처음부터 「정발 퍼스트」였는데(policy.md), 배정에서 평탄한 문안 테이블로 옮기며
    **기본값이 조용히 뒤집혔다** — `script/` 에 `t` 를 적어야 문안이 나가고, 적는 순간 정발보다
    우선한다. 규칙이 바뀐 게 아니라 구조가 바꿔 놓은 것이다(2026-08-17 규명).

    기본값이 정발이면 **미판정 = 방침 준수**가 된다. 안 본 자리가 있어도 규칙이 안 깨지므로,
    「전수를 다 봤는가」가 신뢰의 조건에서 빠진다 — 이게 전수조사보다 근본적인 교정이다.
    """
    locks = json.load(open(os.path.join(ROOT, "locked_lines.json"), encoding="utf-8"))["_settled"]
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "script", "*SCN*.json"))):
        scn = os.path.basename(p)[:-5]
        if not any(scn.startswith(g) for g in games):
            continue
        if scenes and scn not in scenes:
            continue
        canon = json.load(open(p, encoding="utf-8"))
        pin = scene_map(scn) or {}
        lk = locks.get(scn, {})
        for k, v in canon.items():
            t = (v.get("t") or "").strip()
            m = pin.get(str(int(k))) or pin.get(int(k))
            if not t or not m or k in lk:
                continue
            if not clean(dos_text(m["table"], m["entry_id"])):
                continue
            out.append((scn, k, "", t))
    return out


def apply_and_heal(cand, rounds=3):
    """넣고 → 깨진 것만 되돌리고 → 다시. 배치가 밀려 **연쇄로 깨지므로** 한 번으론 안 끝난다."""
    keep = {(s, k): t for s, k, _d, t in cand}
    todo = list(keep)
    for scn in {s for s, _k in todo}:
        ids = [k for s, k in todo if s == scn]

        def drop_t(d, ids=ids):
            for k in ids:
                if k in d:
                    d[k].pop("t", None)
                    if not d[k]:
                        del d[k]

        _write(scn, drop_t)
    reverted = []
    for i in range(rounds):
        rc, drops = build_drops()
        bad = [(s, k) for (s, k) in drops if (s, k) in keep and (s, k) not in reverted]
        if not bad:
            return rc, reverted
        print(f"  라운드 {i + 1}: 탈락 {len(bad)}건 되돌림")
        for scn in {s for s, _k in bad}:
            ids = [k for s, k in bad if s == scn]

            def put_back(d, scn=scn, ids=ids):
                for k in ids:
                    d.setdefault(k, {})["t"] = keep[(scn, k)]

            _write(scn, put_back)
        reverted += bad
    rc, _ = build_drops()
    return rc, reverted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", type=float, default=0.70)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--games", default="ED1")
    ap.add_argument("--flip", action="store_true", help="배정 있는 블록을 전부 정발로")
    ap.add_argument("--scenes", default="")
    a = ap.parse_args()

    if a.flip:
        scenes = set(a.scenes.split(",")) if a.scenes else None
        cand = flip_all(tuple(a.games.split(",")), scenes)
        print(f"  정발로 되돌릴 블록 {len(cand)}건")
        if a.dry or not cand:
            return 0
        rc, rev = apply_and_heal(cand)
        print(
            f"  최종 정발 {len(cand) - len(rev)}건 · 자체번역 유지 {len(rev)}건 · 빌드 {'✅' if rc == 0 else '❌'}"
        )
        for s, k in rev[:20]:
            print(f"     유지 {s} jp{k}")
        return 0

    cand, skipped = candidates(a.sim, tuple(a.games.split(",")))
    by_scn = collections.Counter(s for s, _k, _d, _t in cand)
    print(f"  자동 채택 후보 {len(cand)}건 (어간 {a.sim}+ · 1:1)")
    for s, n in sorted(by_scn.items()):
        print(f"     {s} {n}")
    for why, n in skipped.most_common():
        print(f"  – 뺀 것: {why} {n}")
    if a.dry or not cand:
        return 0

    keep = {(s, k): t for s, k, _d, t in cand}
    for scn in by_scn:
        ids = [k for s, k, _d, _t in cand if s == scn]

        def drop_t(d, ids=ids):
            for k in ids:
                d[k].pop("t", None)
                if not d[k]:
                    del d[k]

        _write(scn, drop_t)
    print(f"\n  {len(cand)}건 적용 — 빌드로 검증한다")

    rc, drops = build_drops()
    bad = [(s, k) for (s, k) in drops if (s, k) in keep]
    if bad:
        print(f"  ⚠ 넣었더니 탈락한 자리 {len(bad)}건 — 우리 문안으로 되돌린다")
        for s, k in bad:
            print(f"     {s} jp{k}: {drops[(s, k)]}")
        for scn in {s for s, _k in bad}:
            ids = [k for s, k in bad if s == scn]

            def put_back(d, scn=scn, ids=ids):
                for k in ids:
                    d.setdefault(k, {})["t"] = keep[(scn, k)]

            _write(scn, put_back)
        rc, _ = build_drops()
    print(
        f"  최종 채택 {len(cand) - len(bad)}건 · 빌드 {'✅' if rc == 0 else '❌ 남은 실패는 사람이 본다'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
