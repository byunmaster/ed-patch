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

import itertools
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
COLS = 14  # 창 한 줄 = **전각 14자** (RAM 눈금자 실측 2026-08-30, status 6-0절)
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
    """창 총량 안에 드나. ⚠ 엔진이 글자 단위로 접으므로 **총량만** 본다(status 6절).

    🔴 **창마다 잰다**(2026-08-29). 예전엔 블록 하나를 창 하나로 보고 통째로 쟀는데, 저본이
       `%c`(창 넘김)를 품는 여러 창짜리 블록이 있다 — **원문 자신이 266슬롯**인 자리도 있다.
       통째로 재면 그런 블록이 전부 「창을 넘는다」로 버려진다(실측 13블록, 창별로는 최대
       61/75 로 넉넉했다). 「문안을 줄여야 한다」로 보였지만 **검사가 틀린 것**이었다.
    ⚠ `%c` 는 창 넘김이자 이름칸 구분이라 조각이 잘게 갈린다. 그래도 **한 조각이 창을 넘을
      수는 없으므로** 조각마다 재면 진짜 초과는 그대로 잡힌다(`check_text` ④ 와 같은 규약).
    """
    return all(width(seg.replace("\n", "")) <= COLS * ROWS for seg in body.split("%c"))


# 🔴 **창은 7행까지 간다** — 원문 실측(2026-08-30). 위 `ROWS`(=5)는 「본문 5행」이라
#    뜻이 다르다. 화면 행을 세는 자리에서는 **화자 줄까지 포함한** 값이 한계다
#    (본문 자리가 `\n` 으로 시작하는 꼴 `%c화자%c\n본문` 에서 그 앞 개행은 빈 줄이 아니라
#    화자 줄의 끝이라 줄 세기에 이미 들어간다).
#
#    원문 전량을 이 접기 규칙에 태운 분포 — **8행이 하나도 없다**:
#
#        1행 10,681 · 2행 3,798 · 3행 3,968 · 4행 3,043 · 5행 1,129 · 6행 145 · 7행 3
#
#    ⚠ 처음엔 6 으로 뒀는데 **근거가 없었다**. 폭을 14 로 고치자 우리 문안 4건이 7행이 되어
#      「잘린다」로 잡혔는데, 그중 하나는 **원문도 7행**이었다(ED1SCN14). 원저작자가 쓰는
#      값을 우리가 못 쓸 이유가 없다.
#    ⚠ 이건 **하한**이다 — 「원문이 안 넘긴 값이 곧 엔진 한계」는 아니다
#      (`docs/reference/our-findings.md` 「창 폭·줄 수는 RAM 에 「눈금자」를 심어 잰다」).
#      8행을 쓰고 싶어지면 그때 눈금자로 재라. 지금은 **원문 이내**라 안전하다.
WIN_ROWS = 7

# 🔴 줄머리에 오면 안 되는 글자(금칙) — 한국어 조판의 관례다.
HEAD_BAN = set("。、．，.,!?！？」』）)]〕》〉…‥·:;~")


def lines(seg):
    """엔진이 접은 뒤의 줄들 — 글자 단위, 누적 폭이 `COLS`(14전각)를 **넘으면** 넘긴다.

    🔴 **RAM 눈금자로 확정했다**(2026-08-30). 대사 블록을 바이트 길이를 유지한 채 눈금자로
       덮어쓰고 화면을 읽는다(`docs/reference/our-findings.md` 「창 폭·줄 수는 RAM 에
       「눈금자」를 심어 잰다」). 두 극단이 **같은 값**을 낸다:

        전각 `１２３４５６７８９０…`  →  **14자 / 줄**   (= 14.0)
        반각 `1234567890…`          →  **28자 / 줄**   (= 14.0)

    ⚠ **전각만 보면 틀린 규칙도 맞아떨어진다.** 처음엔 인게임 표본 넷을 역산해
      「`COLS`(15) **이상**이면 넘김」으로 뒀는데, 그러면 반각이 **29자**여야 한다.
      반각 눈금자가 28을 내면서 드러났다 — 한계는 **14.0 이하**이고 비교는 `>` 다.
    ⚠ 08-18 정찰의 「원문 전량을 폭 15 로 접으면 초과 0」은 **원문 JP** 기준이라 하한만
      말한다(일본어엔 낱말 사이 공백이 없어 반 칸이 안 흐른다).
    """
    return [ln for ln, _at in wrap(seg)]


def wrap(seg):
    """`(줄, 그 줄이 시작하는 인덱스)` 들 — 접기의 **정본**.

    ⚠ 인덱스를 같이 내는 이유: 자동 접기 자리엔 **개행 문자가 없다.** 줄 길이만으로
      원문 위치를 되짚으면 어긋난다(실측 2026-08-30 — `nudge` 가 엉뚱한 자리를 잘랐다).
    """
    out, cur, w, start = [], "", 0.0, 0
    for i, ch in enumerate(seg):
        if ch == "\n":
            out.append((cur, start))
            cur, w, start = "", 0.0, i + 1
            continue
        cw = width(ch)
        if w + cw > COLS:  # 🔴 «초과» — 14.0 까지는 들어간다(전각 14 = 반각 28)
            out.append((cur, start))
            cur, w, start = ch, cw, i
        else:
            cur += ch
            w += cw
    out.append((cur, start))
    return out


def nudge(seg):
    """줄머리에 올 부호를 **앞 글자와 함께** 내린다 — 개행을 넣어 미리 끊는다.

    엔진에는 금칙 처리가 없어 「…불러들였다 / .」처럼 부호만 다음 줄로 떨어진다
    (실측 2026-08-30: 조판된 13,733블록에 **491곳**).

    🔴 **줄 수가 늘면 안 민다.** 무조건 밀면 부호는 491→43 으로 줄지만 **6행을 넘는 창이
       0→33** 이 된다 — 미관을 고치려다 화면이 잘린다. 조건을 걸면 43 · 0 이다.
    🔴 우리가 넣는 개행은 **엔진 접기 지점보다 앞**이라 「엔진 개행 + 내 개행 = 빈 줄」
       함정(PS1 세션 실측 2026-08-30)이 구조적으로 안 난다.
    ⚠ 개행만 넣으므로 **구조 계약**(`%c`·`%s`·`%d` 의 개수와 순서)은 안 바뀐다.
    """
    out, rows0 = seg, len(lines(seg))
    for _ in range(40):  # 한 번 내리면 뒤가 밀려 새 위반이 날 수 있다
        ws = wrap(out)
        inner = _mark_inner(out)
        for i, (ln, _at) in enumerate(ws[1:], 1):
            prev, pat = ws[i - 1]
            if not (ln and ln[0] in HEAD_BAN and prev):
                continue
            if len(prev) < 2:
                continue
            at = pat + len(prev) - 1  # 앞 줄 **마지막 글자**의 자리 — 부호와 함께 내린다
            # 🔴 **마크업 한복판에서 자르면 계약이 깨진다** — `%s` 를 `%`/`\n`/`s` 로 가르면
            #    소프트락이다(실측 2026-08-30: 안 막았더니 건너뛴 블록이 38 늘었다).
            if at in inner or not 0 < at < len(out) or out[at - 1] == "\n":
                continue
            cand = out[:at] + "\n" + out[at:]
            if len(lines(cand)) > max(rows0, WIN_ROWS):
                continue  # 줄이 는다 — 이 자리는 그냥 둔다
            out = cand
            break
        else:
            return out
    return out


def _mark_inner(t):
    """마크업(`%c`·`%s`·`%d`) **내부**의 자리들 — 여기서 자르면 계약이 깨진다."""
    return {i for m in MARK.finditer(t) for i in range(m.start() + 1, m.end())}


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


MARKS_ONLY = re.compile(r"%([csd])")


def place_by_marks(texts, marks, kr, names, sp):
    """**마크업이 문장을 슬롯 여럿으로 가른 블록** — 저본을 마크업에서 잘라 나눠 담는다.

    본문 자리 하나에 통째로 넣는 길이 안 통하는 꼴이 있다. 실측 표본:

        JP  ['', ' は 宝箱を開けました。\n宝箱の中には', '', '', 'が入っていました。']
            marks ['s','c','s','c']
        KR  `%s은(는) 보물상자를 열었다.\n보물상자 안에는 %s이(가) 들어 있었다.`

    저본이 **블록 전체**를 담고 마크업이 그 사이에 낀다. 통째로 한 자리에 넣으면 남은
    자리의 일본어 조각(`が入っていました。`)이 화면에 같이 뜨고, 그렇다고 비우면 마크업
    개수가 어긋나 **계약이 깨진다**(소프트락).

    ⇒ 마크업을 **경계**로 본다. 저본을 그 자리에서 자르면 조각 수가 슬롯 묶음 수와 같아지고,
      묶음마다 「글이 든 자리 하나」에 그 조각을 넣으면 구조가 그대로 남는다.

    ⚠ 한 묶음에 글이 **둘 이상**이면 버린다. 이름은 정본으로 갈아 끼우고 세지 않는다.
    """
    kr_marks = MARKS_ONLY.findall(kr)
    pieces = MARKS_ONLY.split(kr)[0::2]  # 마크업 사이의 글 조각
    # 🔴 **맞춤을 하나로 못 고르면 배치로 고른다**(2026-08-29). 저본이 `%c` 를 품고 원문에
    #    `%c` 가 여럿이면 왼쪽·오른쪽 greedy 가 갈린다(`뭐냐 너희들은?%c썩 저리 물러가라!!`
    #    에 원문 `cccc`). 예전엔 거기서 버렸는데 91블록 중 77이 **배치까지 보면 답이 하나**다 —
    #    묶음마다 「글이 든 자리」가 하나여야 한다는 조건이 대부분의 맞춤을 떨어뜨린다.
    #    ⚠ **둘 이상 살아남으면 여전히 버린다** — 근거가 없다. 다만 조각 순서가 보존되므로
    #      대개 하나로 수렴한다(회귀로 못 만들어 봤다) — **방어용 갈래**로 남긴다.
    done = []
    for at in itertools.combinations(range(len(marks)), len(kr_marks)):
        if [marks[j] for j in at] != kr_marks:
            continue
        got = _lay(texts, marks, pieces, at, names, sp)
        if got is not None and _join(got, marks) not in done:
            done.append(_join(got, marks))
        if len(done) > 1:
            return None
    return None if len(done) != 1 else list(MARK.split(done[0]))[0::2]


def _lay(texts, marks, pieces, at, names, sp):
    """맞춤 하나(`at`)로 조각을 깐다 — 묶음마다 글이 든 자리 하나. 안 되면 None."""
    groups, prev = [], -1
    for j in list(at) + [len(marks)]:
        groups.append(list(range(prev + 1, j + 1)))
        prev = j
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
        # 🔴 **빈 조각으로 글이 든 자리를 지우지 않는다**(2026-08-29). 저본이 원문의 일부만
        #    덮을 때 맞춤을 넓히면 「빈 조각을 일본어 자리에 깔아 지우는」 배치가 유효해
        #    보인다 — 계약도 맞고 창에도 든다. 그런데 그건 **원문을 소리 없이 버리는 것**이다.
        if not piece.strip() and texts[free[0]].strip():
            return None
        out[free[0]] = _lead_nl(texts[free[0]]) + piece
    return out


def _join(out, marks):
    return "".join(a + ("%" + m if m else "") for a, m in zip(out, marks + [""], strict=True))


def contract(t):
    """구조 계약 지문 — `%c%s%d` 의 순서열. 어긋나면 소프트락이다(모듈 주석)."""
    return "".join(m.group(0)[1] for m in MARK.finditer(t))


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
    """`(우리 블록, 못 한 이유)` — 원문 마크업을 그대로 두고 텍스트만 간다.

    ⚠ 마지막에 **금칙 밀어내기**를 건다(`nudge`) — 엔진이 접은 뒤 부호가 줄머리에
      떨어지는 자리를 미리 끊는다. 개행만 넣으므로 구조 계약은 그대로다.
    """
    built, why = _typeset(jp, kr, names)
    if built is None:
        return None, why
    return "%c".join(nudge(seg) for seg in built.split("%c")), None


def _typeset(jp, kr, names):
    """조판 본체 — 밀어내기 전."""
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
        out = place_by_marks(texts, marks, kr, names, sp)
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
            out = place_by_marks(texts, marks, whole, names, sp)
            return (_join(out, marks), None) if out else (None, "정본에 없는 이름 자리가 있다")
    built = _join(out, marks)
    # 🔴 **조판기가 자기 계약을 본다.** 본문 자리에 통째로 넣었더니 계약이 깨지는 꼴이 있다 —
    #    `%c%s%c\n본문` 처럼 **런타임 화자**가 앞에 붙는 블록에서, 저본이 그 인자를 문장
    #    안에 품고 있으면 `%s` 가 둘이 된다(파일럿 6줄 실측 2026-08-29). 바로 위의 겹침
    #    제거는 **바로 앞 마크업**만 보므로 빈 자리가 끼면 안 걸린다(`%c%s%c` 는 빈 자리 셋).
    # ⇒ 그럴 땐 **인자를 경계로 나눠 담는 길**로 간다. 그쪽은 인자를 구조에서 내보내므로
    #   저본이 인자를 품고 있어도 개수가 안 는다.
    # ⚠ 계약이 맞는 블록은 손대지 않는다 — 이 갈래는 **이미 버려질 블록**만 건진다.
    if contract(built) != contract(jp):
        alt = place_by_marks(texts, marks, whole, names, sp)
        if alt is not None and contract(_join(alt, marks)) == contract(jp):
            return _join(alt, marks), None
    return built, None


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
