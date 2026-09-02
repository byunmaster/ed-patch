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
        ("③ 고정 명사 뒤 병기", axis_waste(rows)),
        ("④ 부호·표기 규약", axis_style(rows)),
    ):
        if not hits:
            print(f"  ✅ {title}: 0건")
            continue
        fail += len(hits)
        print(f"  ❌ {title}: {len(hits)}건")
        for row in hits[: (None if a.verbose else 8)]:
            print("     " + " · ".join(str(x) for x in row[2:]) + f"  ({row[0]} 0x{row[1]:X})")

    miss = axis_names(rows)
    print(f"  ℹ ⑤ 고유명사 정본 후보 {sum(miss.values())}건 / {len(miss)}종 (판정은 사람)")
    for (j, k), v in miss.most_common(None if a.verbose else 10):
        print(f"     {v:4}  {j!r} → {k!r}")

    if fail:
        raise SystemExit(f"문안 검사 {fail}건 — 위를 고친다")


if __name__ == "__main__":
    main()
