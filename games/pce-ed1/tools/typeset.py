"""대사 조판 — 공용 krwrap 을 이 창 규격(status.md 3·4절)에 맞춰 부른다.

폭 13칸(글자 = 12px 한 칸 · **공백 = 반각 4px = 1/3 칸**, 마스터 10-07) · 한 창 3줄(화자가 행 0) · 페이지는 `05`
🔴 화자가 있으면 **첫 줄 ≤ 10칸** — 넘은 만큼 화자 이름이 밀린다(실측). 기전을 풀면 넓힌다.

칸 수 = `px // 12`(런타임 `$38BB` + `hook._entry_asm` 의 나머지)다. 줄은 칸이 13 에 닿으면 인터프리터가 스스로 넘긴다 —
그래서 **한 줄은 156px(13.0칸) 이하**로 짠다(그 안에선 칸이 13 에 닿는 건 마지막 글자뿐이라 계획한 줄 = 런타임 줄이다).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from text import krwrap

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font

FULL = 13  # 칸이 이 수에 닿으면 인터프리터가 자동으로 넘긴다
WIDTH = 13.0001  # 칸 단위 폭(px/12) — 156px. 부동소수 오차를 위 한 눈금(4px = 1/3 칸)보다 훨씬 작게 얹는다
FIRST_WITH_SPEAKER = 10.0001
LINES = 3
SPACE_PX = 4  # 대사창 공백은 반각(`font.HALF_SPACE`) — 12px 글자 사이에서 4px 만 간다
NARROW = (
    " " + font.NARROW_PUNCT
)  # 반각 폭(4px) — 공백과 반각 부호(`. , ! ?`, 렌더러가 12px 에 그린 뒤 8px 되감는다)


class Card(list):
    """장 끝 카드 쪽 — 줄을 그대로(빈 줄·앞 공백 포함) 내는 쪽. 일반 쪽은 그냥 list."""


def cell(ch: str) -> float:
    return SPACE_PX / 12 if ch in NARROW else 1.0


def px(line: str) -> int:
    """줄 폭(px) — 글자 12 · 공백·반각 부호 4."""
    return sum(SPACE_PX if c in NARROW else 12 for c in line)


def cols(line: str) -> int:
    """줄이 닿은 칸 수(`px // 12`) — 13 이면 인터프리터가 스스로 넘긴다(그 뒤 명시 줄바꿈은 빈 줄)."""
    return px(line) // 12


def pages(text: str, *, speaker: bool) -> list[list[str]]:
    """문안 → [[줄…], …]. `\\n` 은 하드 개행, `\\f` 는 강제 페이지."""
    out: list[list[str]] = []
    for chunk in text.split("\f"):
        if "\n" in chunk and not speaker:
            # 🔴 **하드 개행이 든 창은 줄을 그대로 둔다**(빈 줄·앞 공백 포함) — krwrap 은
            #    protect_hard 여도 빈 줄과 줄머리 공백을 지워 장 끝 「완」 카드가 「…여행 완」 한 줄로
            #    붙었다(2026-09-24, 여섯 장 모두). 원문도 전각 공백으로 가운데를 맞춘 카드다.
            #    정본에서 `\n` 을 쓰는 건 그 카드뿐이라 대사 조판은 안 바뀐다.
            lines = chunk.split("\n")
            # ⚠ 창은 세 줄이다. 그리고 **빈 줄은 전각 공백 하나를 넣어 적는다** — 개행(`01`)은 「다음 글자 전에
            #   줄 바꿈」 표시라 둘을 잇달아 써도 한 줄만 넘어간다(종장 카드 화면 2026-09-25)
            #   줄 폭은 **px 로** 잰다(전각 공백 12px · ASCII 공백 4px) — 칸 수(글자 수)로 재면 반 칸 공백으로 가운데를 맞춘 카드가 막힌다
            assert len(lines) <= LINES and all(px(x) <= FULL * 12 for x in lines), chunk
            # 장 끝 카드는 빈 줄·앞 공백이 든다 → 개행을 그대로 낸다(`Card`). 그 밖은 정본이 줄을 직접 짠 **줄 계획**(띄어 쓴 아이템 이름을
            # 줄 사이에서 안 갈리게)이라 일반 줄처럼 다룬다 — 꽉 찬 줄 뒤엔 개행을 안 낸다(`translate`).
            card = any(not x or x[0] in " \u3000" for x in lines)
            out.append(Card(lines) if card else lines)
            speaker = False
            continue
        if "\n" in chunk and speaker:
            # 🔴 **화자 창의 하드 개행은 의도적 줄 지정이다**(재검 11, 10-21 — 「길모아의 / 별이라는 건가?」처럼 띄어 쓴 아이템 이름이
            #    줄 사이에서 갈릴 때 정본에서 `\n` 으로 이름 뒤에서 끊는다). krwrap 의 균형 짜기가 지워 버리므로 줄을 그대로 둔다 —
            #    첫 줄은 화자 이름 곁이라 10칸, 나머지는 13칸, 창은 세 줄.
            lines = chunk.split("\n")
            if len(lines) <= LINES and px(lines[0]) <= FIRST_WITH_SPEAKER * 12 and all(px(x) <= FULL * 12 for x in lines[1:]):
                out.append(lines)
                speaker = False
                continue
            # 줄 계획이 창에 안 맞으면(편집기가 여러 메시지를 `\n` 으로 이어 보여 줄 때 등) 종전대로 조판기에 맡긴다.
        pg = krwrap.wrap_pages(chunk, WIDTH, LINES, cell_width=cell)
        if speaker and pg and pg[0] and px(pg[0][0]) > FIRST_WITH_SPEAKER * 12:
            # 첫 줄만 좁히면 되지만 krwrap 엔 줄별 폭이 없다 — 첫 창을 10칸으로 다시 짠다
            first = krwrap.wrap_pages(chunk, FIRST_WITH_SPEAKER, LINES, cell_width=cell)
            pg = (
                first[:1]
                + krwrap.wrap_pages(
                    "\n".join(l for p in first[1:] for l in p),
                    WIDTH,
                    LINES,
                    cell_width=cell,
                    protect_hard=False,
                )
                if len(first) > 1
                else first
            )
        out.extend(pg)
        speaker = False  # 둘째 창부터는 화자 줄이 없다
    for p in out:
        for line in p:
            assert px(line) <= FULL * 12, (line, px(line))
    # 🔴 **글 소실 없음** — 조판 전후 글자(공백·개행·페이지 제외)가 같아야 한다. 폭·위반만 보는 검사는 꼬리 글이
    #    조용히 사라지는 결함을 못 잡는다(PS1·ps1-ed3+4 실측, 관리자 공유 2026-09-27).
    assert ink(text) == ink("".join(l for p in out for l in p)), ("조판이 글을 잃었다", text)
    return out


def ink(s: str) -> str:
    """글자만 — 공백(반각·전각)·개행·페이지를 뺀다."""
    return "".join(c for c in s if c not in " \u3000\n\f")
