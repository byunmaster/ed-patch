"""**화면에 나가는 우리 문장**을 훑는다 — 구조가 아니라 「한국어가 맞나」를 보는 층.

    python3 tools/check_text.py          # 축마다 요약, 실패면 종료코드 1
    python3 tools/check_text.py -v       # 자리마다 문맥까지

## 왜 필요한가

체인의 검사는 전부 **구조**다(되읽기 · 포인터 · 칸 · 계약 · 디스어셈블). 바이트가 제자리에
들어갔는지는 보는데 **그 바이트가 읽을 만한 한국어인지는 아무도 안 봤다.** 씬 대사가
12,000블록 들어온 뒤로는 그 구멍이 제일 크다.

## 축 다섯

① **을/를 받침** — `카드을` 처럼 조사가 앞 음절과 안 맞는 자리.
  ⚠ **은/는·이/가·과/와는 안 본다** — 관형사형 어미와 조사를 어휘만으로 못 가른다
    (`있는`·`없는`·`사과`). PS1 실측으로 645건이 전부 오탐이었다. `을/를` 만 규칙과
    안 부딪히고, 남는 오탐은 **단일 형태소·관형사형**(`마을`·`나을`·`이을`)뿐이라 STOP 으로 끊는다.
② **변수 뒤 고정 조사** — `%s은` 처럼 주입 자리 뒤에 조사가 한 형태로 박힌 자리.
  주입값의 받침이 매번 달라지므로 **병기**(`은(는)`)로 써야 런타임 훅이 푼다.
③ **고정 명사 뒤 병기** — ②의 반대. 앞말이 안 변하는데 병기면 폭만 먹는다.
④ **부호·표기 규약** — 전각 영숫자(메시지 창은 반각) · 반각 가나 잔존 · 창 총량 초과.
⑤ **고유명사 정본** — 원문에 있는 이름이 우리 문안에 대응 표기로 들어갔나.
  ⚠ **게이트가 아니다**(후보만 낸다). 부분 인용(`クルスの村`→`크루즈`)과 보통명사가 섞인다.

🔴 **①~④만 실패로 친다.** ⑤ 는 사람이 판정할 후보다 — 늘 빨간불인 게이트는 아무도 안 본다.
"""

import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ),
        "shared",
    ),
)

import common
import patch_scn
import typeset_scn
from text.josa import batchim

# 단일 형태소·관형사형이라 「받침 + 을」이 정상인 낱말들 — 오탐을 끊는다.
STOP = ("마을", "가을", "서울", "나을", "이을", "겨울", "구을")
EUL = re.compile(r"([가-힣])(을|를)(?![가-힣])")
VAR = re.compile(r"%[sd]\s*(은|는|이|가|을|를)(?![가-힣(])")
DUP = re.compile(r"([가-힣])(은\(는\)|이\(가\)|을\(를\))")
FULLW = re.compile(r"[Ａ-Ｚａ-ｚ０-９]")
HALFKANA = re.compile(r"[ｦ-ﾟ]")
MARKUP = re.compile(r"%[csd]")
WS = re.compile(r"\s+")


def corpus():
    """`[(파일, 오프셋, 우리 문안)]` — **실제로 넣는 것만.**

    ⚠ 계약이 어긋나거나 다른 패처가 주인인 자리는 안 들어가므로 세지 않는다 —
      안 나가는 문장을 검사하면 늘 빨간불이 된다.
    """
    canon = patch_scn.load_canon(quiet=True)
    out = []
    _f, mm = common.open_image()
    for path, _lba, _size in common.iso_files(mm):
        if not patch_scn.SCN_RE.match(path):
            continue
        got = patch_scn.load(path)
        if not got:
            continue
        mine = patch_scn.owned_elsewhere(path)
        sites = patch_scn.sites_for(path)
        for e in got[1]:
            jp, off = e.get("text", ""), int(e["file_offset"], 16)
            if off in mine:
                continue
            kr = patch_scn.canon_of(canon, jp, sites.get(off))
            if kr and patch_scn.contract(kr) == patch_scn.contract(jp):
                out.append((path, off, jp, kr))
    mm.close()
    _f.close()
    return out


def axis_josa(rows):
    """① 을/를 받침 불일치."""
    bad = []
    for path, off, _jp, kr in rows:
        for m in EUL.finditer(kr):
            ch, j = m.group(1), m.group(2)
            if any(kr.startswith(s, m.start()) for s in STOP):
                continue
            if bool(batchim(ch)) != (j == "을"):
                bad.append((path, off, kr[max(0, m.start() - 12) : m.end() + 12]))
    return bad


_JOSA_PAIR = {
    "은": ("은", "는"),
    "는": ("은", "는"),
    "이": ("이", "가"),
    "가": ("이", "가"),
    "을": ("을", "를"),
    "를": ("을", "를"),
    "과": ("과", "와"),
    "와": ("과", "와"),
    "으로": ("으로", "로"),
    "로": ("으로", "로"),
}
_NAME_JOSA = None


def _name_josa_re():
    """고유명사(사전: 사람·몬스터·지명·아이템) 바로 뒤 조사 — **명사라 오탐이 없다**(일반 낱말 뒤 `는`·`이` 는 안 본다)."""
    global _NAME_JOSA
    if _NAME_JOSA is None:
        import canon

        names = set()
        from names import person_table

        for cat in ("person", "monster", "place", "item"):
            for v in (person_table() if cat == "person" else canon.table(cat, "eiyuu")).values():
                v = v.strip()
                if len(v) >= 2 and "가" <= v[-1] <= "힣" and " " not in v:
                    names.add(v)
        alt = "|".join(map(re.escape, sorted(names, key=len, reverse=True)))
        _NAME_JOSA = re.compile(
            r"(?<![가-힣])(" + alt + r")(은|는|이|가|을|를|과|와|으로|로)(?![가-힣(])"
        )
    return _NAME_JOSA


def axis_name_josa(rows):
    """⑨ 고유명사 뒤 조사 받침 일치 — 은/는 · 이/가 · 을/를 · 과/와 · 으로/로(ㄹ 받침은 `로`).

    ① 은 을/를 만 봤다(F8, 기반 대조표 10-08). 일반 낱말 뒤 조사는 어미와 구분이 안 돼 오탐이 많아
    **이름 뒤만** 잰다 — 이름 칸 516·지명·인명 522종. 전각 숫자·영문 꼬리는 받침을 몰라 건너뛴다.
    """
    bad = []
    pat = _name_josa_re()
    for path, off, _jp, kr in rows:
        for m in pat.finditer(kr):
            name, j = m.group(1), m.group(2)
            a, b = _JOSA_PAIR[j]
            f = batchim(name[-1])
            want = b if not f else a
            if a == "으로" and f == 8:
                want = "로"
            if j != want:
                bad.append((path, off, kr[max(0, m.start() - 8) : m.end() + 8].replace("\n", "/")))
    return bad


_SPEAKER = re.compile(r"\s*%c([^%\n]*)%c\n")


def axis_speaker_width(rows):
    """⑩ 화자 이름 칸 — 이름이 한 줄(전각 14칸)에 드나. 넘으면 이름 칸에서 잘리거나 본문 첫 줄을 민다.

    이름칸은 `%c이름%c\n본문` 꼴의 **블록 머리**만 센다(문장 속 `%c…%c` 는 주입 자리 — 이름칸이 아니다).
    변수 이름(`%s`)은 건너뛴다 — 길이를 모른다. 실측 최장 11.5(2026-10-08).
    """
    bad = []
    for path, off, _jp, kr in rows:
        m = _SPEAKER.match(kr)
        if not m or m.group(1).startswith("%"):
            continue
        w = typeset_scn.width(m.group(1))
        if w > typeset_scn.COLS:
            bad.append((path, off, m.group(1), w))
    return bad


def axis_var_josa(rows):
    """② 주입 자리 뒤에 조사가 한 형태로 박혔나."""
    return [(p, o, m.group(0)) for p, o, _jp, kr in rows for m in VAR.finditer(kr)]


def axis_waste(rows):
    """③ 안 변하는 앞말 뒤의 병기.

    ⚠ **블록 맨 앞의 병기는 정상**이다 — 엔진이 그 앞에 이름을 붙여 넣는다.
    """
    return [(p, o, m.group(0)) for p, o, _jp, kr in rows for m in DUP.finditer(kr)]


def axis_style(rows):
    """④ 부호·표기 규약."""
    bad = []
    for path, off, _jp, kr in rows:
        body = MARKUP.sub("", kr)
        if FULLW.search(body):
            bad.append((path, off, "전각 영숫자", body[:40]))
        if HALFKANA.search(body):
            bad.append((path, off, "반각 가나", body[:40]))
        # 🔴 **창마다 잰다**(2026-08-29). 예전엔 블록 하나를 창 하나로 보고 통째로 쟀는데,
        #    조판기가 **창 여럿에 나눠 담게** 되면서 그 전제가 깨졌다 — 세 창짜리 대사가
        #    합쳐서 75슬롯을 넘었다고 울었다(실측: 라이아스↔세리오스 3창, 창마다 21.5·11·32.5).
        #    ⚠ `%c` 는 창 넘김이자 이름칸 구분이라 조각이 잘게 갈리지만, **한 조각이 창을
        #      넘을 수는 없으므로** 조각마다 재면 진짜 초과는 그대로 잡힌다.
        over = max((typeset_scn.width(seg.replace("\n", "")) for seg in kr.split("%c")), default=0)
        if over > typeset_scn.COLS * typeset_scn.ROWS:
            bad.append((path, off, "창 총량 초과", body[:40]))
    return bad


def axis_joint():
    """⑥ **조각이 이어 붙는 자리의 공백** — 조사로 끝나는데 꼬리 공백이 없는 정본.

    🔴 이 게임의 시스템 문구는 **조각을 이어 붙여** 한 줄을 만든다(`最大HPが` + `%d` +
       `ポイントあがった`). 일본어는 전각이라 공백이 없어도 붙는데, 한국어는 붙으면
       **「최대 HP가56포인트」**가 된다 — 실측 2026-09-04 레벨업 화면에서 봤다.
       ⚠ 바로 아랫줄 `최대 MP가 ` 는 공백이 있어 **짝이 어긋나 있었다.**

    ⚠ **게이트가 아니라 보고**다 — 조각이 무엇과 이어 붙는지는 코드가 정하므로 여기서
      단정할 수 없다(문장 끝인 조각도 있다). 사람이 화면에서 보고 정한다.
    """
    import json

    p = os.path.join(common.GAME_DIR, "script", "system.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    lines = d.get("lines", d)
    out = [
        (k, v)
        for k, v in lines.items()
        if isinstance(v, str) and v and v[-1] in "은는이가을를" and not v.endswith(" ")
    ]
    return sorted(out, key=lambda x: x[1])


def axis_names(rows):
    """⑤ 고유명사 정본 — **후보만** 낸다(게이트 아님)."""
    names = typeset_scn._names()
    ordered = sorted(((j, k) for j, k in names.items() if len(j) >= 3), key=lambda x: -len(x[0]))
    miss = collections.Counter()
    for _path, _off, jp, kr in rows:
        flat = WS.sub("", kr)
        left = jp
        for j, k in ordered:
            if j not in left:
                continue
            left = left.replace(j, "\x00" * len(j))  # 긴 이름이 이긴다 — 자리를 덮는다
            core = WS.sub("", k)
            if core and core not in flat:
                miss[(j, k)] += 1
    return miss


_NAME_HEAD = re.compile(r"^%c([^%]+)%c")

# 🔴 **부호 앞 공백** — 한국어는 `. , ! ?` 앞에 공백을 쓰지 않는다.
#    규칙도 구현도 **공용에 이미 있었다**(`shared/text/krwrap._strip_before`). 그런데
#    22줄이 그 꼴로 남아 있었다 — 까닭은 규칙 부재가 아니라 **조판기를 거치는 문안만
#    걸리기 때문**이다. 시스템·전투·UI 도구는 `krwrap` 을 임포트하지 않는다(2026-09-07).
#    ⚠ 원문(JP)이 `輝いた !!` 처럼 공백을 쓰므로 **그대로 옮기면 저절로 생긴다.**
#    ⚠ `check_ps1_parity` 는 공백을 무시하고 견주므로(`WS.sub`) 이 갈림을 **못 본다** —
#      「갈렸다 0」이 참인데도 화면은 달랐다.
# ⚠ `…` 를 더했다(2026-09-08) — 공용 규칙 문구는 `. , ! ?` 지만 말줄임표도 같은 자리다.
#   PS1 도 붙여 쓴다(`그리고…` · `나의 소임…`). 말줄임표를 `…` 한 글자로 모으자 그 앞
#   공백이 드러났다(`…것을 …`).
_STRIP_BEFORE = ".,!?…"


def axis_space_before_punct():
    """⑧ **부호 앞 공백** → `[(파일, 열쇠, 지금, 규칙대로)]`. 판정 정본은 공용 함수다.

    🔴 여기서 규칙을 **다시 쓰지 않는다** — `krwrap._strip_before` 를 그대로 부른다
       (체크리스트 4-D: 같은 지식이 두 곳에 있으면 갈린다).
    """
    from text.krwrap import _strip_before

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = []
    for fn in ("system.json", "scn.json", "ui.json"):
        fp = os.path.join(base, "script", fn)
        if not os.path.exists(fp):
            continue
        with open(fp, encoding="utf-8") as f:
            d = json.load(f)
        for k, v in (d.get("lines") or {}).items():
            if isinstance(v, str) and _strip_before(v, _STRIP_BEFORE) != v:
                out.append((fn, k, v[:34], _strip_before(v, _STRIP_BEFORE)[:34]))
        for h, kr in (d.get("msgs") or {}).items():  # `{JP sha1: KR}`
            if _strip_before(kr, _STRIP_BEFORE) != kr:
                out.append((fn, f"msgs[{h}]", kr[:34], _strip_before(kr, _STRIP_BEFORE)[:34]))
    return out


def axis_hardcoded_names(_rows=None):
    """⑦ **손으로 박은 이름 자리가 정본과 갈렸나** → `[(파일, 오프셋, 지금, 정본)]`.

    🔴 `%c<이름>%c…` 꼴은 **이름 정본**(`shared/glossary`)이 대야 하는데, 그 블록 전체를
       `script/system.json`·`ui.json` 에 손으로 적어 두면 **정본을 가린다.** 정본을 고쳐도
       그 자리만 옛 표기로 남는다.
    ⚠ 실측 2026-09-06: 일곱이 갈려 있었다 — `카자줌`(정본 카자즘) 넷 · 전각 `Ａ`/`Ｂ`
      (우리는 반각) 둘 · `고드윈2세 황제`(정본 「황제 고드윈 2세」) 하나. 같은 인물이
      **화면마다 다른 이름**으로 나오고 있었다.

    🔴 **`corpus()` 로는 못 본다** — 거기서 「다른 패처가 주인인 자리」를 빼는데 이 일곱이
       정확히 거기다. 그래서 여기서는 **원문 쪽에서 훑고 `system.json`·`ui.json` 을 직접
       조회한다.** (붙였다가 0건이 떠서 알았다 — 검사기의 모집단을 먼저 본다.)
    ⇒ 실패로 친다. 이름은 판단이 아니라 정본이다.
    """
    import patch_ui

    sysd, uim = {}, {}
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for fn, into in (("system.json", sysd), ("ui.json", uim)):
        fp = os.path.join(base, "script", fn)
        if not os.path.exists(fp):
            continue
        with open(fp, encoding="utf-8") as f:
            d = json.load(f)
        into.update(d.get("lines", {}))
        into.update(d.get("msgs", {}) or {})  # `ui.json` msgs = `{JP sha1: KR}`

    out, seen = [], set()
    _f, mm = common.open_image()
    try:
        for path, _lba, _size in common.iso_files(mm):
            if not patch_scn.SCN_RE.match(path):
                continue
            got = patch_scn.load(path)
            if not got:
                continue
            for e in got[1]:
                jp = e.get("text")
                if not jp or not e.get("ptr_at") or jp in seen:
                    continue
                m = _NAME_HEAD.match(jp)
                if not m:
                    continue
                seen.add(jp)
                k = patch_ui.sys_key(jp)
                kr = sysd.get(k) or uim.get(k)
                want = patch_scn.name_for(m.group(1))
                got_name = _NAME_HEAD.match(kr) if isinstance(kr, str) else None
                if want and got_name and got_name.group(1) != want:
                    out.append((path, int(e["file_offset"], 16), got_name.group(1), want))
    finally:
        mm.close()
        _f.close()
    return out


def axis_chapter_cards():
    """⑪ **장 끝 카드 제목이 정본(`chapter`)과 같은가** — `script/scn.json` 의 `제N장  제목 … 끝` 꼴.

    🔴 이름·정본 검사(`check_canon`)는 chapter 를 **줄 전체**로 재서, 카드처럼 한 블록 안에 든 제목은 분모 밖이다
       (2026-10-10 — 「왕자의 여행길」·「열린 나락」·「홀려 버린 국왕」이 정본과 달랐는데 못 잡았다). 번호도 정본대로 `제１장`(전각 숫자).
    """
    import patch_ui

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "script", "scn.json"), encoding="utf-8") as f:
        lines = json.load(f)["lines"]
    titles, nums = set(), set()
    for ed in ("ed1", "ed2"):
        for k, v in patch_ui.shared_canon.table("chapter", ed).items():
            (nums if "@번호" in k or k.startswith("第") else titles).add(v)
    out = []
    for k, v in lines.items():
        m = re.match(r"^(제[０-９]장|종장)  (.+?)\n\n +끝$", v)
        if not v.endswith("끝") or "\n\n" not in v:
            continue
        if not m:
            out.append(("scn.json", k, repr(v), "꼴이 다르다(「제１장  제목」 + 전각 숫자)"))
        elif m.group(2) not in titles:
            out.append(("scn.json", k, m.group(2), "정본 장 제목이 아니다"))
        elif m.group(1) not in nums:
            out.append(("scn.json", k, m.group(1), "정본 장 번호가 아니다"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    common.verify_source()
    rows = corpus()
    print(f"  화면 코퍼스 {len(rows):,}블록")

    fail = 0
    for title, hits in (
        ("① 을/를 받침", axis_josa(rows)),
        ("② 변수 뒤 고정 조사", axis_var_josa(rows)),
        ("⑨ 고유명사 뒤 조사 받침", axis_name_josa(rows)),
        ("⑩ 화자 이름 칸 폭", axis_speaker_width(rows)),
        ("③ 고정 명사 뒤 병기", axis_waste(rows)),
        ("④ 부호·표기 규약", axis_style(rows)),
        ("⑦ 손으로 박은 이름이 정본과 갈렸다", axis_hardcoded_names()),
        ("⑧ 부호 앞 공백", axis_space_before_punct()),
        ("⑪ 장 끝 카드 제목이 정본과 갈렸다", axis_chapter_cards()),
    ):
        if not hits:
            print(f"  ✅ {title}: 0건")
            continue
        fail += len(hits)
        print(f"  ❌ {title}: {len(hits)}건")
        for row in hits[: (None if a.verbose else 8)]:
            # ⚠ 축마다 둘째 칸이 **오프셋(int)** 이거나 **열쇠(str)** 다 — 한 꼴로 찍으면
            #   축 하나가 통째로 죽는다(⑧을 붙이고 그 자리에서 밟았다, 2026-09-07).
            where = f"0x{row[1]:X}" if isinstance(row[1], int) else str(row[1])
            print("     " + " · ".join(str(x) for x in row[2:]) + f"  ({row[0]} {where})")

    joints = axis_joint()
    print(f"  ℹ ⑥ 조사로 끝나는 조각의 꼬리 공백 {len(joints)}건 (판정은 사람)")
    for k, v in joints[: (None if a.verbose else 10)]:
        print(f"     {k}  {v!r}")

    miss = axis_names(rows)
    print(f"  ℹ ⑤ 고유명사 정본 후보 {sum(miss.values())}건 / {len(miss)}종 (판정은 사람)")
    for (j, k), v in miss.most_common(None if a.verbose else 10):
        print(f"     {v:4}  {j!r} → {k!r}")

    if fail:
        raise SystemExit(f"문안 검사 {fail}건 — 위를 고친다")


if __name__ == "__main__":
    main()
