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


def pages(text: str, *, speaker: bool, lead_px: int = 0) -> list[list[str]]:
    """문안 → [[줄…], …]. `\\n` 은 하드 개행, `\\f` 는 강제 페이지.

    `lead_px` — 이 메시지가 **앞 메시지가 찍던 줄 끝에 이어 붙을 때** 그 줄이 이미 쓴 폭(px). 첫 줄은 남은 폭에 맞춰 짜고, 첫 낱말이 안 들어가면 첫 줄을 빈 줄('' = 명시 개행)로 둬
    본문 첫머리에서 줄을 넘긴다(씬 64 「세리/오스」 — 런타임 어절 검사는 앞 메시지가 쓴 폭을 몰라 낱말 가운데서 글자 단위로 끊는다).
    """
    out: list[list[str]] = []
    first_chunk = True
    for chunk in text.split("\f"):
        if first_chunk and lead_px and "\n" not in chunk:
            first_chunk = False
            out.extend(_pages_after_lead(chunk, lead_px))
            speaker = False
            continue
        first_chunk = False
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
        pg = _wrap_chunk(chunk, speaker, WIDTH, FIRST_WITH_SPEAKER)
        if _fused_boundary(pg):
            # 🔴 **줄 끝이 반각 부호로 칸 13 에 딱 닿은 줄 뒤에 다음 줄이 이어지면**(우리는 개행·공백을 안 낸다 — 인터프리터가 스스로 넘기므로) 런타임 어절 검사(`wordck`)가
            #    「부호.다음줄첫말」을 **공백 없는 한 어절**로 보고 통째로 아랫줄로 내려 계획과 다른 줄이 된다(「구원받았습니다.감사드립니다.」「하던데,당신들도」 — 마스터 qa 10-22).
            #    반 칸 좁혀 다시 짠다 — 그러면 그 줄은 칸 12 라 명시 개행이 나가고 어절이 안 붙는다.
            pg = _wrap_chunk(chunk, speaker, WIDTH - 0.5, FIRST_WITH_SPEAKER - 0.5)
        out.extend(pg)
        speaker = False  # 둘째 창부터는 화자 줄이 없다
    for p in out:
        for line in p:
            assert px(line) <= FULL * 12, (line, px(line))
    # 🔴 **글 소실 없음** — 조판 전후 글자(공백·개행·페이지 제외)가 같아야 한다. 폭·위반만 보는 검사는 꼬리 글이
    #    조용히 사라지는 결함을 못 잡는다(PS1·ps1-ed3+4 실측, 관리자 공유 2026-09-27).
    assert ink(text) == ink("".join(l for p in out for l in p)), ("조판이 글을 잃었다", text)
    return out


def _pages_after_lead(chunk: str, lead_px: int) -> list[list[str]]:
    """앞 줄에 `lead_px` 가 이미 찍힌 채 이어 붙는 쪽 — 첫 줄을 남은 폭에, 나머지는 보통 폭에 짠다."""
    rem = FULL * 12 - lead_px - SPACE_PX  # 칸 13 에 닿으면 인터프리터가 스스로 넘기므로 한 눈금(4px) 덜 쓴다
    words = chunk.split()
    first: list[str] = []
    acc = 0
    for w in words:
        add = px(w) + (SPACE_PX if first else 0)
        if acc + add > rem:
            break
        first.append(w)
        acc += add
    rest = " ".join(words[len(first) :])
    flat: list[str] = []
    if rest:
        for p in krwrap.wrap_pages(rest, WIDTH, 1000, cell_width=cell):
            flat += p
    head = " ".join(first)  # 비면 '' — 명시 개행(compose 가 빈 줄 뒤 줄 앞에 개행을 낸다)
    take = LINES - 1
    pages_out = [[head] + flat[:take]]
    flat = flat[take:]
    while flat:
        pages_out.append(flat[:LINES])
        flat = flat[LINES:]
    return pages_out


def _wrap_chunk(chunk: str, speaker: bool, width: float, first: float) -> list[list[str]]:
    pg = krwrap.wrap_pages(chunk, width, LINES, cell_width=cell)
    if speaker and pg and pg[0] and px(pg[0][0]) > first * 12:
        # 첫 줄만 좁히면 되지만 krwrap 엔 줄별 폭이 없다 — 첫 창을 10칸으로 다시 짠다
        fp = krwrap.wrap_pages(chunk, first, LINES, cell_width=cell)
        pg = (
            fp[:1]
            + krwrap.wrap_pages(
                "\n".join(l for p in fp[1:] for l in p),
                width,
                LINES,
                cell_width=cell,
                protect_hard=False,
            )
            if len(fp) > 1
            else fp
        )
    return pg


def _fused_boundary(pg: list[list[str]]) -> bool:
    """뒤에 줄이 이어지는데 반각 부호로 끝나 칸 13 에 닿은 줄이 있나(`translate.compose` 는 꽉 찬 줄 뒤에 개행을 안 낸다)."""
    for p in pg:
        for j, ln in enumerate(p[:-1]):
            if ln and ln[-1] in NARROW and ln[-1] != " " and cols(ln) >= FULL:
                return True
    return False


def ink(s: str) -> str:
    """글자만 — 공백(반각·전각)·개행·페이지를 뺀다."""
    return "".join(c for c in s if c not in " \u3000\n\f")
