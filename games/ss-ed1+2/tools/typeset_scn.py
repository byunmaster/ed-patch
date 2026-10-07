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
- 창 총량(전각 14자 × 5행)을 넘으면 버린다 — 넘치면 뒷줄이 잘린다.
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

# 🔴 **반각 꼬리 부호는 29열(14.5)에 앉는다** — 드로어 훅(`patch_msgwrap.hang_stub`, 마스터 판정
#    2026-09-27 · PS1 `patch_hang_punct` 와 같다). 그 부호를 그린 뒤 엔진이 **스스로 줄을 넘기므로**
#    그 줄 뒤엔 우리 개행을 넣지 않는다(넣으면 빈 줄 — `wrap` 주석, PS1 도 같은 규칙 2026-08-30).
HANG_TAIL = set(".,!?)\"'")

# 🔴 줄머리에 오면 안 되는 글자(금칙) — 한국어 조판의 관례다.
HEAD_BAN = set("。、．，.,!?！？」』）)]〕》〉…‥·:;~")


def lines(seg):
    """엔진이 접은 뒤의 줄들 — 글자 단위, 누적 폭이 `COLS`(14전각)를 **넘으면** 넘긴다.

    ⚠ **「넘으면」이 아니라 「커서가 줄 밖이면」이다**(2026-09-03 정정 — `wrap` 의 주석).

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
            # 🔴 **넘친 줄 뒤의 개행은 빈 줄을 하나 더 만든다**(2026-09-27 실기). 엔진은 줄이
            #    14.0 을 **넘는** 순간(13.5 에서 전각이 시작해 14.5 가 되면) 곧바로 줄을 넘기고,
            #    거기에 명시 개행이 오면 또 넘긴다 — 교회 신부 창에서 「…아론님을 뵙게」(29B)
            #    다음에 빈 줄이 떴다(`r6-scene-wrap-blankline-BUG.png`). ⚠ **14.0 딱은 괜찮다** —
            #    원문에 「14.0 + 개행」이 665줄 있다(빈 줄이 났다면 원판이 못 넘겼을 수).
            if w > COLS:
                out.append(("", -1))  # 시작 자리 -1 = 이 빈 줄은 원문에 없다(엔진이 만든다)
            cur, w, start = "", 0.0, i + 1
            continue
        cw = width(ch)
        # 🔴 **판정은 「끝」이 아니라 「시작」이다**(2026-09-03 정정). 엔진은 글자를 그리기
        #    전에 **커서가 아직 줄 안인가**만 본다 — 그래서 커서가 13.5 면 전각 한 글자가
        #    더 들어가 그 줄이 **14.5 전각(= 29 반각)**이 된다. 눈금자 둘(전각 14 · 반각
        #    28)은 두 규칙이 **같은 값**을 내서 이 차이를 못 가른다(둘 다 0.5 눈금에
        #    안 걸린다). 반각이 섞인 실기 화면 넷이 갈랐다(devlog):
        #      「…지난번에 부탁해」 / 「 둔 개구멍은…」   ← `해` 가 13.5 에서 시작한다
        #      「…왕자님. 라」      / 「이아스…」
        #      「…남짓 남았사옵」   / 「니다.」
        #      「…뒀습니다」        / 「요.」            ← 14.0 에서 끊기는 쪽도 맞다
        #    💡 조사 훅의 한 줄 예산이 **29B** 인 것과도 맞는다(루트 CLAUDE.md) — 줄 버퍼가
        #       29 반각 칸이다. 우리 모델만 28 이었다.
        if w >= COLS and not (w == COLS and ch in HANG_TAIL):
            out.append((cur, start))
            cur, w, start = ch, cw, i
        else:
            cur += ch
            w += cw
    out.append((cur, start))
    return out


# 🔴 **밀어낼 때 내려 보는 글자 수** — 위 표가 정본이다. 늘리면 오히려 나빠진다.
NUDGE_BACK = (1, 2)


def _log(why, reason, line):
    """왜 못 밀었나 — ⚠ **계측용이다.** `why` 가 None 이면 아무 일도 안 한다."""
    if why is not None:
        why.append((reason, line[:16]))


def nudge(seg, why=None):
    """줄머리에 올 부호를 **앞 글자와 함께** 내린다 — 개행을 넣어 미리 끊는다.

    엔진에는 금칙 처리가 없어 「…불러들였다 / .」처럼 부호만 다음 줄로 떨어진다
    (실측 2026-08-30: 조판된 13,733블록에 **491곳**).

    🔴 **몇 글자를 내리나 — 하나로 안 되면 둘**(2026-09-03). 전량 실측(13,822블록):

        최대 1글자        줄머리 부호 37 · 고아 158 · 창 초과 0
        최대 2글자        줄머리 부호 21 · 고아 158 · 창 초과 0
        최대 3글자        줄머리 부호 22 · 고아 158 · 창 초과 0
        고아 허용         줄머리 부호 25 · 고아 **182** · 창 초과 0   ← 손해
        **꼬리 어절 우선** 줄머리 부호 **0** · 고아 **162** · 창 초과 0   ← 이것 (2026-09-06)

    🔴 **글자 수를 늘리는 게 답이 아니었다**(2026-09-06). 위 넷은 전부 「몇 글자를 깎나」를
       바꾼 것인데, 남은 21건은 **밀어내기가 스스로 만든 위반**이었다:

           엔진 접기   `…꼴찌가 됐잖아!` / `! 이 굼벵이 자식!!`   ← `!` 둘 사이에서 접힌다
           1글자 깎기  `…꼴찌가 됐잖아`  / `!! 이 굼벵이 자식!!`  ← **부호 뭉치를 갈라 놓고**
                                                                    「고아는 안 늘었다」로 통과
           또 깎기     `…꼴찌가 됐` / `잖아` / `!! 이 굼벵이…`   ← 여기서 포기

       고친 것 둘이다. ⑴ **꼬리 어절을 통째로 내리는 후보를 먼저** 본다.
       ⑵ **위반이 남는 후보는 안 받는다** — 이게 없어서 갉아먹기가 「진전」으로 보였다.

           결과  `…꼴찌가` / `됐잖아!! 이 굼벵이 자식!!`

    💡 판단 기준이 틀렸던 것이다 — 「고아를 안 늘렸나」만 보고 **「고치려던 걸 고쳤나」를
       안 봤다.** 검사기가 자기 목적을 안 보면 갉아먹기가 통과한다.

    ⚠ **고아 제한을 푸는 건 손해다**(위 넷째 줄) — 08-30 의 판단이 접기 모델을 고친
      뒤에도 그대로 맞다. 이득은 「제한을 푸는 것」이 아니라 **「더 내릴 수 있게 하는 것」**에
      있었다. 셋 이상은 오히려 나빠진다(내린 글자가 다음 줄머리에 새 부호를 만든다).

    🔴 **막는 것은 「줄이 느는 것」이 아니라 「고아 줄」과 「창 초과」다**(2026-08-30 정정).
       무조건 밀면 창이 넘치고(잘린다), 반대로 「줄이 한 줄이라도 늘면 금지」로 조이면
       밀 수 있는 자리까지 놓친다. 실측 — 부호 **28 → 21**, 창 초과는 둘 다 0:

           줄이 늘면 금지      부호 28
           고아를 늘리면 금지   부호 21   ← 이것

    ⚠ **고아 줄**(글자 하나만 있는 줄)을 막는 게 핵심이다. 안 막았을 때 밀어내기가
      스스로 고아를 만들었다(19건) — 그러고도 부호는 여전히 줄머리에 있어 **순손실**이었다:

          …………………(14자)        ………………(13자)
          !! 이 굼벵이 자식!!   →   아               ← 고아
                                    !! 이 굼벵이 자식!!
    🔴 우리가 넣는 개행은 **엔진 접기 지점보다 앞**이라 「엔진 개행 + 내 개행 = 빈 줄」
       함정(PS1 세션 실측 2026-08-30)이 구조적으로 안 난다.
    ⚠ 개행만 넣으므로 **구조 계약**(`%c`·`%s`·`%d` 의 개수와 순서)은 안 바뀐다.
    """
    out = seg
    for _ in range(40):  # 한 번 내리면 뒤가 밀려 새 위반이 날 수 있다
        ws = wrap(out)
        inner = _mark_inner(out)
        base = _orphans([ln for ln, _a in ws])
        for i, (ln, _at) in enumerate(ws[1:], 1):
            prev, pat = ws[i - 1]
            if not (ln and ln[0] in HEAD_BAN and prev):
                continue
            # 🔴 **한 글자로 안 되면 두 글자를 내린다**(2026-09-03). 한 글자만 내리면 앞
            #    줄이 고아가 되어 포기하던 자리가 많았다 — 실측으로 그게 **포기 사유의
            #    전부**(37건 100%)였다. 두 글자면 앞 줄이 두 글자로 남아 고아가 아니다.
            reason = "앞 줄이 짧다"
            # 🔴 **꼬리 어절을 통째로 내리는 후보를 먼저 본다**(2026-09-06).
            #    글자 단위(1~2)만 보면 `!!` 같은 **부호 뭉치를 갈라** 놓고 만족한다 —
            #    갈린 조각이 다시 줄머리에 오지만 「고아는 안 늘었다」로 통과한다.
            backs = list(NUDGE_BACK)
            sp = prev.rstrip().rfind(" ")
            if sp > 0:
                backs.insert(0, len(prev) - sp - 1)
            for back in backs:
                if len(prev) < back + 1:
                    continue
                at = pat + len(prev) - back  # 앞 줄 **꼬리 글자들** — 부호와 함께 내린다
                # 🔴 **마크업 한복판에서 자르면 계약이 깨진다** — `%s` 를 `%`/`\n`/`s` 로
                #    가르면 소프트락이다(실측 2026-08-30: 건너뛴 블록이 38 늘었다).
                if at in inner or not 0 < at < len(out) or out[at - 1] == "\n":
                    reason = "마크업 한복판이라 못 자른다"
                    continue
                cand = lines(out[:at] + "\n" + out[at:])
                # 🔴 창을 넘기거나 **고아를 늘리면** 안 민다 — 안 민 것보다 나빠진다
                if len(cand) > WIN_ROWS:
                    reason = "밀면 창이 넘친다"
                    continue
                if _orphans(cand) > base:
                    reason = "밀면 고아가 는다"
                    continue
                # 🔴 **위반이 남는 후보는 안 받는다**(2026-09-06). 이게 없어서 밀어내기가
                #    앞 줄을 한 글자씩 갉아먹으며 **부호를 통째로 줄머리에 내려놓고** 멈췄다
                #    (실측: 남은 21건이 전부 그 꼴이었다 — 밀어내기가 만든 위반이다).
                if any(b and b[0] in HEAD_BAN and a for a, b in itertools.pairwise(cand)):
                    reason = "밀어도 부호가 줄머리에 남는다"
                    continue
                out = out[:at] + "\n" + out[at:]
                break
            else:
                _log(why, reason, ln)
                continue
            break
        else:
            return out
    return out


def _orphans(ls):
    """글자 하나만 있는 줄의 수 — 밀어내기가 이걸 **늘리면** 안 된다."""
    return sum(1 for x in ls if len(x.strip()) == 1)


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
            # 🔴 **저본이 이름을 명시한 자리**는 이미 놓인 것이다(2026-08-30). 한 블록에
            #    화자가 둘인 꼴(`%c란도%c대사1%c아트라스%c대사2%c`)에서 저본도 그 이름을
            #    품는다 — `…영감탱이가…{p}아트라스{p}란도!!`. 원문 자리가 정본으로 번역돼
            #    `free` 가 비는데 조각은 남으니 예전엔 여기서 버렸다(실측 4블록).
            #    ⚠ **같은 이름일 때만** 통과시킨다 — 다르면 우리가 모르는 구조다.
            if piece.strip():
                if piece.strip() in {out[i].strip() for i in g}:
                    continue
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
    # 🔴 **PS1 의 붙임 공백**(`reinsert_kr_pilot.NOBREAK_SP`) — 블록을 이어 붙일 때 PS1 조판기가
    #    보통 공백을 깎아서 쓰는 표식이다. 새턴엔 그 사정이 없으니 **그냥 공백**이다.
    #    ⚠ 안 바꾸면 cp932 가 사용자 영역(U+E003)을 **`F0 43`** 으로 인코딩한다 — 폰트(4,375자)
    #      한참 밖이라 화면에 엉뚱한 글자가 찍힌다(2026-09-27, 42블록 — 줄바꿈 전수 스캔이 잡았다).
    ("\ue003", " "),
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


def typeset(jp, kr, names, why=None):
    """`(우리 블록, 못 한 이유)` — 원문 마크업을 그대로 두고 텍스트만 간다.

    ⚠ 마지막에 **금칙 밀어내기**를 건다(`nudge`) — 엔진이 접은 뒤 부호가 줄머리에
      떨어지는 자리를 미리 끊는다. 개행만 넣으므로 구조 계약은 그대로다.
    ⚠ `why` 에 리스트를 주면 **밀어내기가 포기한 사유**가 담긴다(계측용 — `check_engine_wrap`).
      실패 사유(둘째 반환값)와는 다른 것이다.
    """
    built, bad = _typeset(jp, space_places(kr), names)
    if built is None:
        return None, bad
    return "%c".join(nudge(seg, why) for seg in wrap_block(built).split("%c")), None


# ── 어절 단위 줄바꿈 (마스터 확정 2026-09-27 — 조판 여섯 규칙은 씬까지 전 영역) ──────────
# 엔진은 글자 단위로 접는다(`wrap`) — 그래서 「알겠/다」처럼 낱말 한가운데서 갈렸다. 빌드 때
# **어절 자리에 개행을 미리 넣어** 엔진이 접을 일이 없게 한다(엔진 쪽 코드는 안 건드린다).
# 🔴 **규칙은 다시 쓰지 않는다** — 메시지 창 기준 구현 `msgwrap.wrap` 을 그대로 쓴다(4-D).
#    문자열을 그 함수가 먹는 바이트로 옮기고(한글 = 전각 2B 자리표), 결과를 되짚어 온다.
# ⚠ 못 하면 **안 한다**(원래 조각 그대로 → 밀어내기만): 창 7행 초과 · `%s`/`%d` 한복판 절단 ·
#   엔진 모델이 여전히 접는 줄이 남는 경우.
# 🔴 **씬 창은 한 칸(1B) 좁게** — 메시지 창 규칙(`LIMIT` 28 = 28B 미만일 때 놓는다)이면 전각이
#    27B 에서 시작해 **29B(14.5)** 줄이 되고, 그 뒤에 우리가 넣은 개행이 오면 엔진이 빈 줄을
#    하나 더 만든다(위 `wrap` 주석). 27 미만일 때만 놓으면 개행으로 끝나는 줄이 늘 **28B 이하**다.
SCN_LIMIT = 27
_HOLE = b"\x88\x9f"  # 한글 한 글자 자리표 — 닫는 부호가 아닌 전각 SJIS
# 🔴 **런타임 이름(`%s`)은 가장 긴 이름으로 잰다** — 아이템이 들어오는 자리가 있다(「보물상자 안에는
#    %s이(가)…」). 짧게 잡으면 긴 이름이 그 줄을 넘치게 하고, 그 뒤 우리 개행이 **빈 줄**을
#    만든다(위 `wrap` 주석). 정본 최장 = 아이템 7.5 칸(`프레이아의 미소`) · 몬스터 7 → 전각 8.
# `%c` 는 **글줄 안 색 쌍**으로만 여기 들어온다(`line_groups`) — 폭 없는 제어(`msgwrap.ZERO_W`).
_TOKENS = {"%s": _HOLE * 8, "%d": b"99999", "%c": b"\x02"}  # 수치는 다섯 자리(`50000 Gold`)


# 🔴 **색 없는 `%s` 뒤에 주어 조사가 오면 파티원이다** — 원문 전량에서 예외가 없다(2026-09-27:
#    보물상자 여는 사람 · 「%s은(는) 포기할 수밖에 없었다」). 파티 기본 이름 최장 = 전각 넷
#    (`세리오스`·`아트라스`). 여기까지 8 칸으로 재면 「%s은(는) / 읽었다.」 처럼 두 어절 문장이
#    괜히 갈린다. ⚠ 나머지 `%s`(색 쌍 안 · 지명 · 주문 · 수치 표)는 그대로 가장 긴 값이다.
_SUBJECT = re.compile(r"(?<!%c)%s(?=은\(는\)|이\(가\))")
_PARTY_W = 4


def _is_subject(seg, i):
    return _SUBJECT.match(seg, i) is not None


def _units(seg, tokens=None):
    """`[(바이트, 원문 조각)]` — `%s`·`%d` 는 한 덩어리."""
    tokens = _TOKENS if tokens is None else tokens
    out, i = [], 0
    while i < len(seg):
        t = seg[i : i + 2]
        if t == "%s" and _is_subject(seg, i):
            out.append((_HOLE * _PARTY_W, t))
            i += 2
            continue
        if t in tokens:
            out.append((tokens[t], t))
            i += 2
            continue
        ch = seg[i]
        try:
            b = ch.encode("cp932")
        except UnicodeEncodeError:
            b = _HOLE
        out.append((b, ch))
        i += 1
    return out


def wordwrap(seg):
    """조각 하나에 어절 단위 개행을 넣는다. 못 하면 원래 조각.

    ⚠ **수치 앞 공백을 풀어 한 번 더 본다** — 규칙 2(공백 뒤 숫자는 안 끊는다)가 끊을 자리를
      전부 막으면 **숫자 한복판**만 남는다(`%s은(는) %d Gold…` — 이름이 길면 그 줄에 다른 공백이
      없다). 숫자를 가르느니 그 공백에서 끊는다 — 둘째 시도에서 `%d` 를 숫자 아닌 자리표로 잰다.
    """
    new = _wordwrap(seg, _TOKENS)
    if new is None and "%d" in seg:
        new = _wordwrap(seg, {**_TOKENS, "%d": b"xxxxx"})
    return seg if new is None else new


def _wordwrap(seg, tokens):
    """한 번의 시도 — 못 하면 `None`."""
    import msgwrap

    units = _units(seg, tokens)
    src = b"".join(b for b, _t in units)
    got = msgwrap.wrap(src, stop=None, limit=SCN_LIMIT, retreat=True)  # 씬·대사는 어절 단위
    if not msgwrap.check_invariant(src, got):
        return None
    body = [u for u in units if u[1] not in (" ", "\n")]
    out, pos, k = [], 0, 0
    while pos < len(got):
        c = got[pos]
        if c in (msgwrap.NL, msgwrap.SP):
            out.append("\n" if c == msgwrap.NL else " ")
            pos += 1
            continue
        b, t = body[k]
        if got[pos : pos + len(b)] != b:
            return None  # 한 덩어리(`%s`·`%d`·한 글자) 한복판에서 끊겼다
        out.append(t)
        pos += len(b)
        k += 1
    new = "".join(out)
    ls = lines(measure(new))
    if len(ls) > WIN_ROWS or len(ls) != new.count("\n") + 1:
        return None  # 창이 넘치거나 엔진이 여전히 접는다
    return new


def measure(t):
    """엔진 접기 모델(`wrap`)에 태울 꼴 — 색 쌍은 폭 0, 런타임 인자는 **가장 긴 값**."""
    t = _SUBJECT.sub("가" * _PARTY_W, t)
    return t.replace("%c", "").replace("%s", "가" * 8).replace("%d", "99999")


def _inline(inner, after):
    """`%c inner %c after` 가 **글줄 안 색 쌍**인가 — 이름을 칠하고 같은 줄이 이어진다.

    🔴 `%c` 는 셋이다(원문 전량 분류 2026-09-27): 화자 명판 `%c화자%c\n` · 창/쪽 넘김
       (대개 개행 뒤) · **글줄 안 이름 색** `…には%c%s%cが…` · `%c密造酒%cを渡しました`.
       셋째를 조각 경계로 보면 한 줄이 둘로 쪼개져 **그 줄 폭을 못 잰다**(「보물상자 안에는
       %c%s%c이(가) 들어 있었다」 19칸이 안 접혔다).
    """
    return (
        "\n" not in inner
        and after != ""
        and not after.startswith("\n")
        and (inner == "%s" or 0 < width(inner) <= 8)
    )


def line_groups(built):
    """`%c` 로 가른 조각을 **글줄 안 색 쌍만 다시 붙여** 묶는다 → `[조각 번호 목록]`."""
    segs = built.split("%c")
    join = [False] * max(0, len(segs) - 1)  # join[b] = b 번째 `%c`(segs[b]|segs[b+1]) 를 잇는다
    k = 1
    while k < len(segs) - 1:
        if _inline(segs[k], segs[k + 1]):
            join[k - 1] = join[k] = True
            k += 2
        else:
            k += 1
    groups, cur = [], [0]
    for b, j in enumerate(join):
        if j:
            cur.append(b + 1)
        else:
            groups.append(cur)
            cur = [b + 1]
    groups.append(cur)
    return segs, groups


def wrap_block(built):
    """블록 전체 줄바꿈 — 글줄 단위(`line_groups`)로 **PS1 과 같은 조판**(`ps1_layout`)을 걸고,
    새턴 제약을 못 지키면 어절 단위 탐욕(`wordwrap`)으로 물러선다."""
    segs, groups = line_groups(built)
    out = []
    for g in groups:
        t = "%c".join(segs[i] for i in g)
        out.append(ps1_layout(t) or wordwrap(t))
    return "%c".join(out)


# ── PS1 과 같은 조판 (마스터 판정 2026-09-27 — 「대사창 사이즈가 같다면 PS1 과 동일하게」) ──
# PS1 은 씬 대사를 공용 `krwrap.wrap_pages`(문장 단위 · 균형 배치 · 고아 방지)로 조판한다
# (`ps1-ed1+2/tools/reinsert_kr_pilot.wrap_page`). 창 폭이 같으므로(14.0 슬롯 · 반각 0.5)
# **같은 함수 · 같은 인자**를 부르면 줄 나눔이 같아진다 — 같은 문안 11,697조각 실측 38.3% → 99.7%.
# 새턴 몫은 셋만 덧댄다: ① 런타임 인자 폭(가장 긴 값 — `_TOKENS` 주석) ② 7행 ③ **개행 앞 줄은
# 14.0 이하 · 엔진이 접는 줄 없음**(넘친 줄 뒤 개행 = 빈 줄, `wrap` 주석). 못 지키면 None.
# ⚠ PS1 의 「14.5 + 끝 부호」 걸침(`_hang_merge`)은 **안 가져온다** — PS1 은 엔진을 고쳐
#   (`patch_hang_punct`) 반각 부호가 29열에서 **시작**하게 열었다. 새턴 엔진은 14.0 에서 시작하는
#   글자를 다음 줄로 꺾으므로 조판만으로는 못 한다(부호만 줄머리로 떨어진다).
# ⚠ 붙임 규칙 둘(`_KEEP`·`_NUM_UNIT`)은 PS1 `keep_together`·`_bind_num_unit` 과 **같은 규칙**이다 —
#   정본이 게임 쪽에 둘로 갈려 있다. `shared/` 로 올릴 후보(관리자에게 넘김, 4-D).
_NB = "\ue014"  # 붙임 공백 자리표 — 조판 뒤 공백으로 되돌린다(화면에 안 나간다)
_SENT = {"%s": "\ue010", "%S": "\ue011", "%d": "\ue012", "%c": "\ue013"}  # %S = 주어 파티원
_SENT_W = {"\ue010": 8.0, "\ue011": float(_PARTY_W), "\ue012": 2.5, "\ue013": 0.0, _NB: 0.5}
_NUM_UNIT = re.compile(r"(?<=[0-9\ue012]) (?=Gold)")  # PS1 `_NUM_UNIT` — 금액과 단위
_KATA = re.compile(r"[ァ-ヴー]{2,}")


def _cell(ch):
    return _SENT_W.get(ch, 0.5 if ch.isascii() else 1.0)


_PLACE_RE = None
_PLACE_FORMS = None
_MARK_TAIL = re.compile(r"[A-JＡ-Ｊ♀♂]$")


def _place_forms():
    """`{문안 속 꼴: 대사 꼴}` — 바뀌는 것만."""
    global _PLACE_FORMS
    if _PLACE_FORMS is None:
        from names import ATTACHED_KINDS, space_place_dialog

        vals = set(table("place").values())
        _PLACE_FORMS = {v: w for v in vals if (w := space_place_dialog(v)) != v}
        # 「성」·「섬」은 붙인다 — 띄어 쓴 꼴(`루디아 성`)이 문안에 있으면 붙인다
        _PLACE_FORMS.update(
            {v[:-1] + " " + v[-1]: v for v in vals if v.endswith(ATTACHED_KINDS) and len(v) > 2}
        )
    return _PLACE_FORMS


def space_places(kr):
    """대사 속 지명을 대사 꼴로 — 🔴 규칙은 `names.space_place_dialog` 가 정본이다.

    ⚠ **지명 한 덩어리 블록은 안 건드린다** — 항로·워프 목록처럼 이름 칸인 자리다(판정 (나)는 붙임).
      개체 표지가 붙은 꼴(`핀요새B`·`핀요새Ｃ` — 몬스터 이름과 같은 글자)도 이름 칸이다.
    """
    global _PLACE_RE
    forms = _place_forms()
    if not kr or _MARK_TAIL.sub("", kr.strip()) in forms:
        return kr
    if _PLACE_RE is None:
        _PLACE_RE = re.compile("|".join(map(re.escape, sorted(forms, key=len, reverse=True))))
    return _PLACE_RE.sub(lambda m: forms[m.group(0)], kr)


def _keep():
    """띄어 쓴 고유명사 — PS1 `keep_together` 와 같은 뜻(인물·지명은 가타카나 원명만)."""
    global _KEEP
    if _KEEP is None:
        names = {"신의 아들"}
        for cat in ("item", "monster"):
            names.update(table(cat).values())
        for cat in ("person", "place"):
            names.update(v for k, v in table(cat).items() if _KATA.search(k))
        # 대사 꼴로 띄운 지명은 **전부** 한 덩어리다(조판 규칙 ④ 묶음 안 끊기 — 관리자 중계
        # 2026-09-27: 가타카나 원명뿐 아니라 `국경의 동굴`·`용의 알` 도. PS1 도 같게 간다)
        names.update(_place_forms().values())
        out = [n for n in names if " " in n.strip() and sum(map(_cell, n)) <= COLS]
        _KEEP = tuple(sorted(out, key=lambda n: (-len(n), n)))
    return _KEEP


_KEEP = None


def ps1_layout(seg):
    """글줄 하나를 PS1 과 같게 조판한다. 새턴 제약을 못 지키면 None."""
    from text import krwrap

    if "\n\n" in seg or "\t" in seg or any("\ue000" <= c <= "\uf8ff" for c in seg):
        return None  # 원문 빈 줄·탭 정렬(장 끝 카드 등)은 원래 조판을 그대로 둔다
    lead = seg[: len(seg) - len(seg.lstrip("\n"))]  # 화자 줄 끝 개행
    body = seg[len(lead) :]
    if not body.strip():
        return None
    t = _SUBJECT.sub("%S", body)
    for k, v in _SENT.items():
        t = t.replace(k, v)
    for n in _keep():
        t = t.replace(n, n.replace(" ", _NB))
    t = _NUM_UNIT.sub(_NB, t)
    pages = krwrap.wrap_pages(
        t,
        float(COLS),
        WIN_ROWS,
        break_char="\n",
        cell_width=_cell,
        strip_before=".,!?",
        strip_after="",
        det_orphan=True,
    )
    ls = _hang_merge([ln for pg in pages for ln in pg])
    hung = [_hung(ln) for ln in ls]
    if len(ls) > WIN_ROWS or any(
        sum(map(_cell, ln)) > COLS and not h for ln, h in zip(ls, hung, strict=True)
    ):
        return None
    # 매단 줄 뒤엔 개행도 공백도 안 넣는다 — 엔진이 부호를 그린 뒤 스스로 넘긴다
    last = len(ls) - 1
    new = "".join(
        ln + ("" if h or i == last else "\n")
        for i, (ln, h) in enumerate(zip(ls, hung, strict=True))
    )
    want = list(ls)
    new = _unsent(new.replace(_NB, " "))
    want = [_unsent(ln.replace(_NB, " ")) for ln in want]
    new = lead + new
    if _strip_ws(new) != _strip_ws(seg):
        return None  # 글 소실 — 절대 안 받는다
    m = lines(measure(new))
    if m[len(lead) :] != [measure(w) for w in want] or len(m) > WIN_ROWS:
        return None  # 엔진이 우리가 뜻한 줄과 다르게 접거나 빈 줄이 난다
    return new


def _unsent(t):
    for k, v in _SENT.items():
        t = t.replace(v, "%s" if k == "%S" else k)
    return t


def _strip_ws(t):
    return "".join(c for c in t if c not in " \n")


def _hung(ln):
    """29열(14.5)을 반각 꼬리 부호로 채운 줄인가."""
    return sum(map(_cell, ln)) == COLS + 0.5 and ln[-1:] in HANG_TAIL


def _hang_merge(ls):
    """PS1 `_hang_merge` 와 같은 뜻 — 꼬리 부호 하나 때문에 갈린 줄을 도로 붙인다(14.5 까지)."""
    out, i = [], 0
    while i < len(ls):
        if i + 1 < len(ls):
            j = f"{ls[i]} {ls[i + 1]}"
            w = sum(map(_cell, j))
            if COLS < w <= COLS + 0.5 and j[-1] in HANG_TAIL and _cell(j[-1]) == 0.5:
                out.append(j)
                i += 2
                continue
        out.append(ls[i])
        i += 1
    return out


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
