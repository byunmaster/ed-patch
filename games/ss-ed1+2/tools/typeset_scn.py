"""저본의 **순수 문안**에 원문의 마크업을 다시 입힌다 — 조판기.

    python3 tools/typeset_scn.py          # 얼마나 조판되는지 센다
    python3 tools/typeset_scn.py --show 8 # 표본을 보여 준다

## 왜 필요한가

사전(`line_dict.json`)은 **문안만** 담는다 — 화자도 창 전환도 개행도 없다:

    JP  `%cライアス%c\\n王子、ちゃんと いすに 座って\\n…%c`
    KR  `왕자님, 의자에 얌전히 앉아 기다리고 계시옵소서. …`

그대로 넣으면 **구조 계약**(`%c`·`%s`·`%d` 의 개수와 순서)이 깨져 소프트락이 난다
(`docs/reference/our-findings.md`). 그래서 **원문의 마크업을 그대로 두고 텍스트 자리만**
우리 문안으로 갈아 끼운다.

## 어떻게 가르나 — 마크업으로 쪼개면 자리가 드러난다

원문을 `%c`/`%s`/`%d` 로 쪼개면 `[텍스트][마크업][텍스트]…` 가 번갈아 나온다.

    `%cライアス%c\\n본문%c`  →  텍스트 ['', 'ライアス', '\\n본문', '']  ·  마크업 ['c','c','c']

- **본문** — 텍스트 자리 중 **가장 긴 것**. 여기에 우리 문안을 넣는다.
- **나머지 자리는 이름이다** — `shared/glossary`(person·monster·place·**item**)로 번역한다.
  ⚠ `%c%s%c` 는 런타임 이름이라 그대로 둔다.
- 🔴 **비우지 않는다**(2026-08-27 정정). 「나머지는 대개 비어 있다」로 비웠더니 이름이
  둘 이상인 블록 176 곳에서 **이름이 화면에서 사라졌다**(`%cゲイル%cは%c目玉の付いた靴%c…`).
  정본에 없는 이름이 남으면 **그 블록을 통째로 버린다** — 우리 문안이 이미 그 이름을
  품고 있으면 두 번 나오기 때문이다. 다만 **화자 자리만은 원문을 남긴다**(뒤에 이유).

## 🔴 저본은 **PS1 표기**로 마크업을 품고 있다

「순수 문안」이 아니다(2026-08-27 실측 — 사전 18,146 중 308). 그대로 넣으면 화면에
`{p}` 가 글자로 찍힌다(실제로 89블록이 그랬다). 새턴 표기로 옮긴다:

    {n} · \x0a  →  개행        \x1a · \x17  →  %s (이름·아이템 주입)
    {p}         →  %c (창 넘김)  \x1b         →  %d (수치 주입)

옮기고 나면 개수가 달라지는 블록이 나오는데, 그건 **계약 검사가 걸러 낸다**(우리가 판단
하지 않는다). 남는 제어문자가 하나라도 있으면 **버린다** — 화면에 그대로 나가기 때문이다.

## 🔴 화자와 본문 사이의 개행을 지운다 = 본문이 화자 줄에 붙는다

원문은 `%c화자%c\n본문` 이고, **화자 블록 5,576 중 5,461(97.9%)** 이 그 개행을 갖는다.
반대로 화자 없는 블록은 5,766/6,352 가 개행 없이 시작한다 — 즉 그 개행은 조판이 아니라
**화자와 본문을 가르는 구분자**다. 초판이 이걸 버려 8,657 블록이 원문과 달라져 있었다.
⇒ 본문 자리의 **앞 개행은 원문 그대로 살린다**(2026-08-27).

실측(저본이 붙는 12,091 블록): `c` 5,013 · `ccc` 4,961 · 없음 755 · `cscc` 704 · `cc` 402
— **상위 다섯이 97.9%** 다.

## 🔴 조판은 못 하면 **안 한다**

- 마크업 개수·순서가 하나라도 달라지면 버린다(계약).
- 본문 자리를 못 고르면 버린다(자리가 둘 이상 크면 어디에 넣을지 근거가 없다).
- 창 총량(전각 15자 × 5행)을 넘으면 버린다 — 넘치면 뒷줄이 잘린다.
⚠ 「대충 넣고 나중에 고친다」가 안 되는 층이다. 계약 위반은 **오타가 아니라 소프트락**이다.
"""

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
from glossary import table
from text.line_key import key as line_key

MARK = re.compile(r"(%[csd])")
COLS = 15  # 창 한 줄 = 전각 15자 (status 6절, 실측)
ROWS = 5  # 본문 5행 (창 6행 중 화자가 1행)


def _names():
    """이름 정본 하나로 합친 것 — 이름 자리는 사람·몬스터·지명·**아이템** 어디서든 온다.

    ⚠ `item` 을 빠뜨렸더니 `%cナイフ%c을(를) 장비했다.` 처럼 **아이템 이름만 일본어**로
      남았다(2026-08-27). 216칸이 이미 정본에 있는데 안 읽고 있었다.
    """
    out = {}
    for cat in ("person", "monster", "place", "item"):
        out.update(table(cat))
    return out


def width(s):
    """전각 칸 수 — 반각은 0.5 로 센다(엔진이 그렇게 접는다)."""
    return sum(0.5 if c.isascii() else 1 for c in s)


def fits(body):
    """창 총량 안에 드나. ⚠ 엔진이 글자 단위로 접으므로 **총량만** 본다(status 6절)."""
    return width(body.replace("\n", "")) <= COLS * ROWS


def split(jp):
    """`(텍스트 자리들, 마크업들)` — 번갈아 나온다."""
    parts = MARK.split(jp)
    return parts[0::2], [p[1] for p in parts[1::2]]


def speaker_slot(texts, marks):
    """화자가 든 텍스트 자리의 번호. 없으면 None.

    🔴 **`%c…%c` 꼴만으로는 부족하다.** `%cソニア%cが 仲間になりました。` 처럼 **문장 속
       이름**도 같은 꼴이라, 개수만 보면 본문을 화자로 오인한다(203블록이 그래서 조용히
       탈락했다). 진짜 화자는 **바로 뒤가 개행**이다 — 실측 5,461/5,576.
    ⚠ `%c%s%c`(런타임 이름)는 **화자 자리가 아니다** — 인자라 우리가 손댈 게 없다.
    """
    if marks[:2] != ["c", "c"] or len(texts) < 3:
        return None
    return 1 if texts[2].startswith("\n") else None


def body_slot(texts, skip):
    """본문이 든 자리 — 화자를 뺀 것 중 **가장 긴** 하나. 애매하면 None."""
    cand = [(len(t), i) for i, t in enumerate(texts) if i != skip and t.strip()]
    if not cand:
        return None
    cand.sort(reverse=True)
    if len(cand) > 1 and cand[0][0] == cand[1][0]:
        return None  # 어디에 넣을지 근거가 없다
    return cand[0][1]


def _looks_like_name(t):
    """화자 자리에 든 게 **이름꼴**인가 — 정본에 없을 때 원문을 남길지 가른다.

    🔴 길이를 안 보면 **문장이 두 번 나온다.** `%c『두 번 다시 …』%c\n…라고 말씀하셨습니다%c`
       처럼 인용문이 그 자리에 드는 블록이 있는데, 우리 본문이 이미 그 인용을 품고 있어
       원문을 남기면 일본어 인용 + 한국어 인용이 나란히 뜬다(실측 2026-08-27).
    """
    return "\n" not in t and len(t) <= 12


def _lead_nl(t):
    """앞 개행 묶음 — 화자와 본문을 가르는 구분자다(모듈 주석)."""
    i = 0
    while i < len(t) and t[i] == "\n":
        i += 1
    return t[:i]


ARGS = re.compile(r"%[sd]")


def arg_groups(texts, marks):
    """인자(`%s`·`%d`)를 경계로 슬롯을 묶는다 — `[[슬롯 번호…], …]`."""
    groups, cur = [], []
    for i in range(len(texts)):
        cur.append(i)
        if i < len(marks) and marks[i] in "sd":
            groups.append(cur)
            cur = []
    groups.append(cur)
    return groups


def place_by_args(texts, marks, kr, names, sp):
    """**인자가 문장을 슬롯 여럿으로 가른 블록** — 저본을 인자에서 잘라 나눠 담는다.

    본문 자리 하나에 통째로 넣는 길이 안 통하는 꼴이 있다(184블록 중 100). 실측 표본:

        JP  ['', ' は 宝箱を開けました。\n宝箱の中には', '', '', 'が入っていました。']
            marks ['s','c','s','c']
        KR  `%s은(는) 보물상자를 열었다.\n보물상자 안에는 %s이(가) 들어 있었다.`

    저본이 **블록 전체**를 담고 있고 인자가 그 사이에 낀다. 통째로 한 자리에 넣으면
    남은 자리의 일본어 조각(`が入っていました。`)이 화면에 같이 뜨고, 그렇다고 비우면
    인자 개수가 어긋나 **계약이 깨진다**(소프트락).

    ⇒ 인자를 **경계**로 본다. 저본을 인자에서 자르면 조각 수가 슬롯 묶음 수와 같아지고,
      묶음마다 「글이 든 자리 하나」에 그 조각을 넣으면 구조가 그대로 남는다.

    ⚠ **인자 열이 저본과 원문에서 같아야 한다**(개수도 종류도). 다르면 어느 조각이 어느
      자리인지 근거가 없으므로 손대지 않는다 — 이 층은 「대충 넣고 나중에」가 안 된다.
    ⚠ 한 묶음에 글이 **둘 이상**이면 버린다(7블록). 이름은 정본으로 갈아 끼우고 세지 않는다.
    """
    jp_args = ["%" + m for m in marks if m in "sd"]
    if not jp_args or ARGS.findall(kr) != jp_args:
        return None
    pieces = ARGS.split(kr)
    groups = arg_groups(texts, marks)
    if len(pieces) != len(groups):
        return None
    out = list(texts)
    for g, piece in zip(groups, pieces, strict=True):
        free = []
        for i in g:
            t = texts[i]
            if not t.strip():
                continue  # 🔴 공백만 든 자리는 그대로 — 그게 구분자다(`typeset` 주석)
            if t in names:
                out[i] = names[t]
            elif i == sp and _looks_like_name(t):
                out[i] = t
            else:
                free.append(i)
        if len(free) > 1:
            return None
        if not free:
            # 자리가 없는데 넣을 글이 있으면 그건 우리가 모르는 구조다
            if piece.strip():
                return None
            continue
        out[free[0]] = _lead_nl(texts[free[0]]) + piece
    return out


def _join(out, marks):
    return "".join(a + ("%" + m if m else "") for a, m in zip(out, marks + [""], strict=True))


# PS1 표기 → 새턴 표기. ⚠ **하나라도 남기면 화면에 글자로 찍힌다**(모듈 주석).
_PS1_MARKUP = [
    ("{n}", "\n"),
    ("\x0a", "\n"),
    ("{p}", "%c"),
    ("\x1a", "%s"),
    ("\x17", "%s"),
    ("\x1b", "%d"),
]
_HALFW = {
    c: c - 0xFEE0
    for c in list(range(0xFF21, 0xFF3B)) + list(range(0xFF41, 0xFF5B)) + list(range(0xFF10, 0xFF1A))
}
_LEFTOVER = re.compile(r"\{[a-z]+\}|[\x00-\x09\x0b-\x1f\x7f]")


def to_saturn(kr):
    """저본 마크업을 새턴 표기로. 남는 게 있으면 `None`(그 블록은 버린다).

    ⚠ **전각 영숫자는 반각으로** — 메시지 창의 알파벳은 전부 반각이 이 게임의 방침이다
      (`patch_mon_names` 도 개체 접미를 그렇게 깐다). 저본은 PS1 표기라 전각이 섞여 들어와
      **같은 몬스터가 대사에선 `카자즘Ｂ`, 전투에선 `카자즘B`** 로 갈렸다(19건 실측).
    """
    for a, b in _PS1_MARKUP:
        kr = kr.replace(a, b)
    kr = kr.translate(_HALFW)
    return None if _LEFTOVER.search(kr) else kr


def typeset(jp, kr, names):
    """`(우리 블록, 못 한 이유)` — 원문 마크업을 그대로 두고 텍스트만 간다."""
    kr = to_saturn(kr)
    if kr is None:
        return None, "저본 마크업이 남는다"
    texts, marks = split(jp)
    if not marks:
        return kr, None  # 마크업이 없다 — 그대로 쓴다
    sp = speaker_slot(texts, marks)
    bi = body_slot(texts, sp)
    if not fits(kr):
        return None, "창을 넘는다"
    if bi is None:
        # 본문 자리가 하나로 안 잡히는 꼴 — 인자가 문장을 가른 블록일 수 있다
        out = place_by_args(texts, marks, kr, names, sp)
        return (_join(out, marks), None) if out else (None, "본문 자리를 못 고른다")
    whole = kr  # ⚠ 아래에서 겹치는 인자를 떼기 **전** — 조각 배치는 온전한 저본이 필요하다
    # 🔴 **인자가 겹치는 자리** — 원문이 `%s は …` 이고 저본이 `\x1a은(는) …` 이면 옮긴 뒤
    #    `%s%s` 가 된다(18블록 실측). 앞 마크업과 같은 인자면 저본 쪽을 뗀다.
    if bi > 0 and kr[:2] in ("%s", "%d") and kr[1] == marks[bi - 1]:
        kr = kr[2:]
    out = list(texts)
    for i, t in enumerate(out):
        if i == bi:
            # 🔴 앞 개행은 원문 그대로 — 화자와 본문을 가르는 구분자다(모듈 주석)
            out[i] = _lead_nl(t) + kr
        elif not t.strip():
            # 🔴 **공백만 든 자리도 비우지 않는다** — 그 공백이 개행 하나면 그게 화자와
            #    본문을 가르는 구분자다(`%cリュナン%c\n%cロー%c…`). 비웠더니 붙었다.
            out[i] = t
        elif t in names:
            out[i] = names[t]  # 이름 — 정본 표기로
        elif i == sp and _looks_like_name(t):
            out[i] = t  # 화자만은 정본에 없어도 원문을 남긴다(빈 이름표보다 낫다)
        else:
            # 🔴 이름인지 문장인지 모르는 자리다. 우리 문안이 이미 그걸 품고 있으면
            #    두 번 나온다. 다만 **인자가 문장을 가른 꼴**이면 조각을 나눠 담을 수 있다 —
            #    ⚠ 저본은 **손대기 전 것**을 준다(위에서 겹치는 인자를 뗐다).
            out = place_by_args(texts, marks, whole, names, sp)
            return (_join(out, marks), None) if out else (None, "정본에 없는 이름 자리가 있다")
    return _join(out, marks), None


def main():
    import patch_scn as P

    common.verify_source()
    names = _names()
    canon = P.load_canon()
    _f, mm = common.open_image()
    ok = 0
    why = {}
    show, shown = ("--show" in sys.argv and int(sys.argv[sys.argv.index("--show") + 1])), 0
    for path, _lba, _size in common.iso_files(mm):
        if not P.SCN_RE.match(path):
            continue
        got = P.load(path)
        if not got:
            continue
        for e in got[1]:
            jp = e.get("text", "")
            # ⚠ **`_canon_get` 을 쓰면 안 된다** — 그건 이미 조판된 것을 준다. 여기서 다시
            #   태우면 조판된 블록이 통째로 본문 자리에 들어가 계약이 터진다(실측 11,127).
            kr = canon.get(line_key(jp))
            if not kr:
                continue
            built, bad = typeset(jp, kr, names)
            if bad or P.contract(built) != P.contract(jp):
                why[bad or "계약이 달라졌다"] = why.get(bad or "계약이 달라졌다", 0) + 1
                continue
            ok += 1
            if show and shown < show:
                shown += 1
                print(f"  JP {jp[:56]!r}\n  KR {built[:56]!r}\n")
    print(f"조판 성공 {ok:,}")
    for k, v in sorted(why.items(), key=lambda x: -x[1]):
        print(f"  ⏭ {k}: {v:,}")
    mm.close()
    _f.close()


if __name__ == "__main__":
    main()
