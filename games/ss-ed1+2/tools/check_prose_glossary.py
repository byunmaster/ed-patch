"""시스템 메시지 **본문 속**에 적힌 고유명사가 정본과 갈렸나 — 표가 아니라 산문을 본다.

    python3 tools/check_prose_glossary.py

## 왜 있나 (라운드⑥ 착수, 2026-10-07)

`check_glossary.py`(「정본」)는 **표 레코드**(이름 칸 하나 = 값 하나)만 본다. 그런데
`script/system.json`의 전투 로그는 **손으로 쓴 문장**이라 아이템·주문 이름이 **산문 속에**
박혀 있다 — `"%c헤르닐드%c은(는) 불꽃의 지팡이를 ...치켜들었다"` 처럼. 글로서리가
`炎の杖`→`불의 지팡이`로 확정돼도 이 문장은 **자동으로 안 따라온다** — 손으로 그 문장을
다시 쳐야 한다. 실측(2026-10-07): 「불꽃의 지팡이」(정본 「불의 지팡이」) · 「인퍼스」
(정본 「인파스」) 둘이 산문 속에 남아 있었다. 표 검사(`check_glossary.py`)는 둘 다
통과했다 — 표가 아니라 산문이라 안 걸렸다.

## 방법

`patch_ui.sys_rows()`가 이미 **원본 이미지에서 JP 원문**과 **우리 KR**(`script/system.json`)을
짝지어 돌려준다(시스템 메시지 재배치용). 그 JP 원문에 글로서리 아이템·몬스터·인명 용어가
**부분 문자열로** 나오면, 같은 자리의 KR 에도 **그 용어의 지금 정본 번역**이 부분 문자열로
있어야 한다 — 없으면 그 문장이 옛 표기를 그대로 쓰고 있다는 뜻이다.

⚠ **부분 문자열 대조라 오탐이 있을 수 있다** — 짧은 용어가 다른 낱말 안에 우연히 끼면
  걸릴 수 있다. 지금까지는 실제로 걸린 적이 없다(0건). 걸리면 그 줄을 눈으로 본다.
"""

import os
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
import glossary
import patch_ui as U

CATEGORIES = ("item", "monster", "person")


def terms():
    """{JP 용어: 지금 정본 KR} — 셋 다 합친다(먼저 온 카테고리가 이긴다)."""
    out = {}
    for cat in CATEGORIES:
        for jp, kr in glossary.table(cat).items():
            if kr:
                out.setdefault(jp, kr)
    return out


def check():
    t = terms()
    f0, mm0 = common.open_image()
    try:
        sysm = U.sys_rows(mm0)
    finally:
        mm0.close()
        f0.close()
    bad = []
    for path, _lba, _size, base, _span, pre, kr, _ptrs in sysm:
        jp_pre = pre.decode("cp932", errors="ignore")
        for jp, canon_kr in t.items():
            if jp in jp_pre and canon_kr not in kr:
                bad.append((path, base, jp, canon_kr, kr))
    return len(sysm), len(t), bad


def main():
    n, nterms, bad = check()
    mark = "✅" if not bad else "❌"
    print(f"     {mark} 시스템 메시지 산문 사전 대조 {n:,}자리 × 용어 {nterms:,}개 — 잔존 {len(bad)}건")
    for path, base, jp, canon_kr, kr in bad[:10]:
        print(f"        🔴 {path} 0x{base:X}: {jp!r}→{canon_kr!r} 인데 {kr!r}")
    if bad:
        raise SystemExit(f"산문 속 고유명사 {len(bad)}건이 정본과 갈렸다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
