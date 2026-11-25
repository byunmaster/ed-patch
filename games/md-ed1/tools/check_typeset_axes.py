"""조판 축 전수 게이트 — **실제로 굽는 바이트**(빌드가 만드는 토큰)를 전 대사·전 전투 스트림에서 줄·쪽으로 풀어 센다.

    python3 tools/check_typeset_axes.py        # 축별 건수 + 위반 목록, 위반이 기준선보다 늘면 rc 1
    python3 tools/check_typeset_axes.py -v     # 위반 전부

마스터 10-31 「조판검사할 때 첫칸공백, 고아부호, 빈줄개행, 여러창일 때 균등한 문장 분배(마지막 창에 한 어절만 남으면 안 됨) 등등」.
`check_linebreak.py` 는 조판기 출력(`build.typeset`)을, `check_layout.py` 는 조립형 시스템·전투 메시지를 **모형**으로 센다 —
여기는 `build.build_stream`·`battle.plan_block` 이 낸 **최종 토큰**을 직접 푼다(`<03>`·`<05>`·참조·이음새 공백 처리까지 거친 뒤의 모습).
축(규칙 번호는 `docs/translation-rules.md`):
  첫칸공백 2-5 · 고아부호 2-3 · 빈줄개행 2-4 · 첫쪽빈줄 2-18(첫 쪽 머리 빈 줄 0, 면제 없음) · 부호뒤공백 2-1 · 낱말속접힘 2-6 · 넘침(줄 폭·5줄 쪽) ·
  끝창한어절(2-16 ③·2-17: 마지막 창이 한 어절 — 앞 창이 문장 중간에서 끊겼을 때, **실패**) · 쪽끝고아·창치우침(알림만 — 2-17 은 창 사이로
  문장을 옮겨 고르게 맞추지 않는다고 했다) ·
  쉼표뺄것 2-13(뺀다 부류인데 앞 절 11음절 이하) · 한줄문장쪼갬 2-10(쪽에 빈 줄이 있는데 한 줄에 드는 문장을 쪼갬; 쪽이 꽉 찼거나 `<03>` 이음이면
  `한줄문장쪼갬허용` 알림 — 2-17) · 가운데어긋남 2-8(손으로 가운데 맞춘 장 카드·가운데 정렬 표가 원판 중심과 1px 넘게 다름, 실제 픽셀 폭).
  허용분은 `typeset_axes_baseline.json`(사유 포함) — 이 파일에 없는 위반은 실패.
`<03>`(키 대기)은 창을 안 지우고 이어 쓰므로 쪽 경계가 아니다 — 쪽은 `<05>` 로만 나뉜다.
"""

import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle
import build
import common
import hangul
import linebreak
import scene

BASE = Path(__file__).resolve().parent.parent / "typeset_axes_baseline.json"
PUNCT_ONLY = set(".,!?…」』)~。、！？")
KAGI_MAP = str.maketrans(
    {"{": "「", "}": "」", "\\": "『", "^": "』", "`": "“", "~": "”"}
)  # 글꼴 반각 따옴표 코드 → 폭 계산용
SENT_END = re.compile(r"[.!?…」』\"')~]$")
CODE = re.compile(r"<[0-9a-f]{2,}>")
INFO_AXES = {
    "쪽끝고아",
    "창치우침",
    "한줄문장쪼갬허용",
}  # 알림만 — 규칙 2-17(마스터 10-31): 창 사이로 문장을 옮겨 고르게 맞추지 않는다 · 막는 건 마지막 창 한 어절(끝창한어절)뿐
AXES = (
    "첫칸공백", "고아부호", "빈줄개행", "빈줄머리", "첫쪽빈줄", "부호뒤공백", "낱말속접힘", "줄폭넘침", "줄수넘침",
    "끝창한어절", "쪽끝고아", "창치우침", "색범위낱말", "부호앞공백", "말줄임뒤공백", "부호순서",
    "쉼표뺄것", "한줄문장쪼갬", "한줄문장쪼갬허용", "가운데어긋남", "창적음", "창많음",
)  # fmt: skip


def _rev() -> dict[int, str]:
    codes = json.loads(
        (common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")
    )
    return {v: k for k, v in codes.items()}


REV = _rev()


def dec(raw: bytes) -> str:
    out, i = "", 0
    while i < len(raw):
        if i + 1 < len(raw) and ((raw[i] << 8) | raw[i + 1]) in REV:
            out += REV[(raw[i] << 8) | raw[i + 1]]
            i += 2
            continue
        if 0x81 <= raw[i] <= 0x9F or 0xE0 <= raw[i] <= 0xEF:
            try:
                out += raw[i : i + 2].decode("cp932")
                i += 2
                continue
            except UnicodeDecodeError:
                pass
        out += raw[i : i + 1].decode("cp932", "replace") if raw[i] >= 0x20 else f"<{raw[i]:02x}>"
        i += 1
    return out


def split_pages(tokens) -> list[list[list[tuple]]]:
    """토큰 → 쪽(`<05>` 로 나뉨) → 줄(`<01>` 로 나뉨) → 항목 [('t', 글) | ('c', 코드)]. `<03>` 은 코드로 줄 안에 남긴다."""
    pages: list[list[list[tuple]]] = [[[]]]
    for t in tokens:
        if t.kind == "text":
            pages[-1][-1].append(("t", dec(t.raw)))
        elif t.kind == "ctl" and t.raw[:1] == b"\x01":
            pages[-1].append([])
        elif t.kind == "ctl" and t.raw[:1] == b"\x05":
            pages.append([[]])
        else:
            pages[-1][-1].append(("c", t.raw[:1].hex()))
    return pages


def line_text(line) -> str:
    return "".join(x[1] for x in line if x[0] == "t")


def has_slot(line) -> bool:
    return any(x[0] == "c" and x[1] not in ("03", "0c", "00", "06", "07", "0a", "0d") for x in line)


def stutter_chain(body: str, at: int) -> bool:
    """`body[at]`(「…」)이 낱말 한 개를 음절마다 끊어 말하는 사슬 속인가 — 규칙 2-11 예외.
    사슬 = 공백·다른 부호 없이 「…」 로만 이어진 조각들. 끊긴 조각이 모두 한 음절이고(마지막 조각만 예외) 「…」 가 둘 이상이거나
    (`세…리…오…스…` · `불…가…능…하다…` · `없…다…`), 같은 소리를 되풀이하는 의성어(`흑…흑…흑…`)이면 붙인다. `아…그래` 처럼 말이 바뀌는 건 띄운다."""
    lo = at
    while lo > 0 and (body[lo - 1].isalnum() or body[lo - 1] == "…"):
        lo -= 1
    hi = at
    while hi < len(body) and (body[hi].isalnum() or body[hi] == "…"):
        hi += 1
    chain = body[lo:hi]
    frags = [f for f in chain.split("…") if f]
    if len(frags) < 2:
        return False
    return len(set(frags)) == 1 or (all(len(f) == 1 for f in frags[:-1]) and chain.count("…") >= 2)


COLOR_OPEN = {
    0x18,
    0x19,
    0x1A,
    0x1B,
    0x1C,
    0x1D,
    0x1F,
}  # 1E 는 화자 이름표 색(이름표 안 글자는 04 로 닫힌다 — 같은 식으로 센다)


def color_spans(tokens) -> list[tuple[str, str]]:
    """색 코드(18~1F)가 여는 글 범위가 낱말과 어긋나지 않는가 — 범위 머리·끝에 공백이 칠해지거나, 한 낱말 한가운데서 색이 바뀐다.
    닫는 코드(04) 누락은 원판 대비 개수·자리 대조(`check_structure`)가 막는다."""
    out = []
    items = []
    for t in tokens:
        if t.kind == "text":
            items.append(("t", dec(t.raw)))
        elif t.kind == "ctl" and t.raw[:1] in (b"\x01", b"\x05"):
            items.append(("n", ""))
        elif t.kind == "ctl":
            items.append(("c", t.raw[0]))
    for i, it in enumerate(items):
        if it[0] != "c" or (it[1] not in COLOR_OPEN and it[1] != 0x1E):
            continue
        j = i + 1
        seg = ""
        while j < len(items) and items[j][0] == "t":
            seg += items[j][1]
            j += 1
            break
        if not seg:
            continue
        closed = j < len(items) and items[j] == ("c", 0x04)
        if seg != seg.strip() and closed:
            out.append(("색범위낱말", f"색{it[1]:02x} 범위 {seg!r} 에 공백이 칠해진다"))
        prev = next((x for x in reversed(items[:i]) if x[0] != "c"), None)
        if (
            prev
            and prev[0] == "t"
            and prev[1]
            and not prev[1].endswith((" ", "「"))
            and seg[:1].isalpha()
            and prev[1][-1].isalpha()
            and closed
            and it[1] != 0x1E
        ):
            out.append(
                (
                    "색범위낱말",
                    f"색{it[1]:02x} 가 낱말 한가운데서 시작 {prev[1][-3:]!r}|{seg[:4]!r}",
                )
            )
    return out


def analyze(
    tokens, ours: str = "", *, scene_mode: bool = True, cap: int = 4, ret_end: bool = False
) -> list[tuple[str, str]]:
    """한 스트림 → [(축, 설명)]. `cap` = 이 창 종류의 원판 최대 줄 수 · `ret_end` = 되돌림 끝(06) 조각(호출한 쪽 글과 이어진다)."""
    out: list[tuple[str, str]] = []
    pages = split_pages(tokens)
    oc = (
        re.sub(
            r"\s+",
            " ",
            re.sub(r"<[0-9a-f]+(?::[0-9a-f]+)?>", "", ours.replace("\f", " ").replace("\n", " ")),
        )
        if ours
        else ""
    )
    for pi, pg in enumerate(pages):
        body = [
            ln
            for ln in pg
            if line_text(ln).strip() and not any(i[0] == "c" and i[1] in ("1e", "04") for i in ln)
        ]
        page_has_text = bool(body)  # 이름표(1e…04)만 있는 쪽은 원판도 빈 줄 구조다
        shown = [ln for ln in pg if line_text(ln).strip() or has_slot(ln)]
        if len(shown) > cap:
            out.append(("줄수넘침", f"쪽{pi + 1} {len(shown)}줄(창 한도 {cap})"))
        for li, ln in enumerate(pg):
            txt = line_text(ln)
            first = next(
                (x for x in ln if x[0] == "t" or (x[0] == "c" and x[1] not in ("03", "0c"))), None
            )
            if first and first[0] == "t" and first[1].startswith(" ") and txt.strip():
                frag_head = (
                    li == 0 and pi == 0 and ours[:1] == " "
                )  # 되돌림 조각 머리 공백 — 호출한 쪽 글과의 이음새
                authored = (
                    "<01>" + txt[:6]
                ) in ours  # 문안에 박은 들여쓰기(서명 줄 — 원판도 전각 공백 들여쓰기)
                if not (frag_head or authored):
                    out.append(("첫칸공백", f"쪽{pi + 1} 줄{li + 1} {txt[:20]!r}"))
            prev_ln = next((x for x in reversed(pg[:li]) if line_text(x).strip()), [])
            prev = (
                ""
                if any(i[0] == "c" and i[1] in ("1e", "04", "09") for i in prev_ln)
                else line_text(prev_ln).strip()
            )
            if (
                txt.strip()
                and not has_slot(ln)
                and set(txt.strip()) <= PUNCT_ONLY
                and prev
                and not SENT_END.search(prev)
            ):
                out.append(("고아부호", f"쪽{pi + 1} 줄{li + 1} {txt.strip()!r} ← {prev[-8:]!r}"))
            empty = not txt.strip() and not has_slot(ln)
            if empty and 0 < li < len(pg) - 1 and page_has_text:
                out.append(("빈줄개행", f"쪽{pi + 1} 줄{li + 1}"))
            if empty and li == 0 and len(pg) > 1 and page_has_text:
                # 규칙 2-18(마스터 11-08 「빈줄 개행은 금지」): 첫 쪽의 머리 빈 줄은 원판과 같은 구조여도 면제 없이 0.
                # 둘째 쪽부터의 머리 빈 줄(`<05><01>글` — 이름 줄 자리를 비운 원판 구조)은 씬별 원판 수까지만 면제(`빈줄머리`)
                out.append(("첫쪽빈줄" if pi == 0 else "빈줄머리", f"쪽{pi + 1} 머리 빈 줄"))
            for seg in (x[1] for x in ln if x[0] == "t"):
                m = re.search(r"(?<![0-9])[.,!?](?=[가-힣A-Za-z])", seg)
                if m:
                    out.append(
                        (
                            "부호뒤공백",
                            f"쪽{pi + 1} 줄{li + 1} {seg[max(0, m.start() - 6) : m.end() + 6]!r}",
                        )
                    )
            runs, cur = (
                [],
                "",
            )  # 슬롯·호출 코드로 끊기지 않고 이어 찍히는 글만 한 덩이로 본다(`아, <호출>!` 의 쉼표와 느낌표는 이어지지 않는다)
            for x in ln:
                if x[0] == "t":
                    cur += x[1]
                elif cur:
                    runs.append(cur)
                    cur = ""
            runs.append(cur)
            for body in runs:
                m = re.search(r" [.,!?]", body)
                if m:  # 2-2 부호 앞 공백은 언제나 뗀다
                    out.append(
                        (
                            "부호앞공백",
                            f"쪽{pi + 1} 줄{li + 1} {body[max(0, m.start() - 6) : m.end() + 4]!r}",
                        )
                    )
                for m in re.finditer(r"(?<=[가-힣A-Za-z0-9.,!?])…+(?=[가-힣A-Za-z0-9])", body):
                    if stutter_chain(body, m.start()):
                        continue  # 2-11 예외(마스터 10-12·13): 한 낱말을 음절마다 끊어 말함 · 같은 소리 되풀이 의성어는 붙인다
                    # 2-11 말이 이어지면 「…」 뒤를 띄운다(문장 맨 앞 「…」 는 붙인다)
                    out.append(
                        (
                            "말줄임뒤공백",
                            f"쪽{pi + 1} 줄{li + 1} {body[max(0, m.start() - 6) : m.end() + 4]!r}",
                        )
                    )
                    break
                m = re.search(r"[?!]…", body)
                if m:  # 2-12 물음표·느낌표와 「…」 가 겹치면 「…」 를 앞에
                    out.append(
                        (
                            "부호순서",
                            f"쪽{pi + 1} 줄{li + 1} {body[max(0, m.start() - 6) : m.end() + 4]!r}",
                        )
                    )
            w = linebreak._width(txt.rstrip().translate(KAGI_MAP))
            if scene_mode and txt.strip() and not has_slot(ln) and w > build.WIDTH + 0.01:
                out.append(("줄폭넘침", f"쪽{pi + 1} 줄{li + 1} {w:.1f}칸"))
            if oc and li + 1 < len(pg):
                nx = pg[li + 1]
                ta, tb = line_text(ln).rstrip(), line_text(nx).lstrip()
                if ta and tb and ln[-1][0] == "t" and nx[0][0] == "t" and not SENT_END.search(ta):
                    wa, wb = ta.split(" ")[-1], tb.split(" ")[0]
                    if wa and wb and (wa + wb) in oc and (wa + " " + wb) not in oc:
                        out.append(("낱말속접힘", f"쪽{pi + 1} 줄{li + 1}→{li + 2} {wa}|{wb}"))
    out += color_spans(tokens)
    out += comma_axis(tokens)
    out += oneline_axis(tokens, scene_mode, ret_end)
    if scene_mode and not ret_end:
        texts = []
        for pg in pages:
            ls = [line_text(ln).strip() for ln in pg if line_text(ln).strip()]
            texts.append(ls)
        for pi in range(len(texts) - 1):
            cur, nxt = texts[pi], texts[pi + 1]
            if not cur or not nxt or SENT_END.search(cur[-1]):
                continue  # 문장이 끝난 쪽 — 이어지는 창이 아니다
            lastw = cur[-1].split(" ")[-1]
            if ours and (lastw + "\f") in ours.replace(" \f", "\f"):
                continue  # 문안에 박은 쪽 나눔 — 쪽 넘김 자리는 원문을 따른다(2-6)
            if " " not in cur[-1] and len(cur) > 1:
                out.append(("쪽끝고아", f"쪽{pi + 1} 끝 줄 {cur[-1]!r}"))
            if pi + 1 == len(texts) - 1:  # 끊긴 문장의 마지막 창
                joined = " ".join(nxt)
                if " " not in joined:
                    out.append(("끝창한어절", f"쪽{pi + 2} {joined!r}"))
                elif (
                    len(nxt) == 1
                    and len(cur) >= 3
                    and linebreak._width(nxt[0].translate(KAGI_MAP)) < build.WIDTH * 0.3
                ):
                    out.append(("창치우침", f"쪽{pi + 1}={len(cur)}줄 → 쪽{pi + 2}=1줄 {nxt[0]!r}"))
    return out


# ── 2-13 쉼표 · 2-10 한 줄 문장 · 2-8 가운데 정렬 (마스터 11-02 「1번도 같이」 — 화면 몫으로 남겼던 셋을 정적으로 센다) ──
COMMA_NINE = re.compile(
    r"(는데|은데|인데|던데|지만|네만|다만|니다만|만)$"
)  # 2-13 ⑨ — 앞 절 11음절 이하면 뺀다
COMMA_CONN = re.compile(
    r"(했고|았고|었고|하고|이고|으며|하며|이며|면서|해서|아서|어서|다가|고|며|서)$"
)  # 짧은 연결 어미
COMMA_QUOTE = re.compile(
    r"(라고|보자고|아이고|하자고|라며|다니|던가|다면서|가만)$"
)  # 인용·감탄·군말은 남기는 부류
COMMA_TOPIC = re.compile(
    r"(?:[가-힣]{2,}(?:은|는)|에서는|에는|으로는|로는)$"
)  # 주어·주제·부사어 뒤
COMMA_JUDGED = {  # 눈으로 판정한 남김 — 앞 절 글 → 사유
    "뭐냐 네놈은": "도치(서술어가 앞) — 부르는 말 성격(2-13 경계 ⑧)",
    "{마시려면 들지 말고": "짝을 이룬 두 구(2-13 경계 ⑤) — 팻말",
}
COMMA_BOUND = re.compile(r"[.!?…,]\s*")


def _syl(s: str) -> int:
    """읽는 소리 음절 수 — 한글 음절 + 숫자·영문 낱자(규칙 2-13 ⑨ 의 잣대, 어림)."""
    return len(re.findall(r"[가-힣]", s)) + len(re.findall(r"\d+|[A-Za-z]+", s))


def comma_axis(tokens) -> list[tuple[str, str]]:
    """쉼표뺄것(2-13) — **뺀다** 부류(주어·주제 뒤 · 짧은 연결 어미 뒤 · `~는데,`/`~지만,`/`~만,` 뒤)인데 **앞 절이 11음절 이하**인 쉼표.
    남기는 부류(부르는 말·감탄·나열·인용 `~라고,`)와 앞 절이 12음절 이상인 것은 세지 않는다(규칙 행: 앞 절이 길면 쉼이 꼭 필요)."""
    out = []
    for pi, pg in enumerate(split_pages(tokens)):
        flat = " ".join(
            line_text(ln).strip()
            for ln in pg
            if line_text(ln).strip() and not any(i[0] == "c" and i[1] in ("1e", "04") for i in ln)
        )
        for m in re.finditer(r"([^\s,]+),", flat):
            w = m.group(1)
            if COMMA_QUOTE.search(w) or len(re.findall(r"[가-힣]", w)) < 2:
                continue
            if not (COMMA_NINE.search(w) or COMMA_CONN.search(w) or COMMA_TOPIC.search(w)):
                continue
            clause = COMMA_BOUND.split(flat[: m.end() - 1])[-1]
            if clause in COMMA_JUDGED:
                continue
            if 3 <= _syl(clause) <= 11:
                out.append(("쉼표뺄것", f"쪽{pi + 1} {clause!r}, ({_syl(clause)}음절)"))
        # 2-13 ⑩ 문장 앞 접속 「그럼,」 — 부르는 말 앞(「그럼, 왕자님.」)·작별(「그럼, 몸조리…」)은 남김
        for m in re.finditer(r"(?:^|[.!?…] |자 )그럼, ([^.!?…]*)", flat):
            rest = m.group(1)
            if rest.endswith("님") or rest.startswith("몸조리"):
                continue
            out.append(("쉼표뺄것", f"쪽{pi + 1} '그럼, {rest}' (문장 앞 접속)"))
    return out


SLOT_PX = 72  # 이름 칸(`<02>`)은 전각 6자로 어림 — 이보다 짧아야만 한 줄에 든다고 본다(넉넉한 쪽)
SLOT_CODES = {"02", "eb", "ec"}


def oneline_axis(tokens, scene_mode: bool, ret_end: bool = False) -> list[tuple[str, str]]:
    """한줄문장쪼갬(2-10) — 창 한 줄(씬 210px · 전투 288px)에 들어가는 문장이 두 줄로 쪼개졌다.
    쪽에 빈 줄이 있어 새 줄로 시작할 수 있으면 **실패**(`한줄문장쪼갬`), 쪽이 꽉 찼거나 `<03>` 이음 뒤라 옮길 수 없으면 알림(`한줄문장쪼갬허용` — 규칙 2-17 이 허용한다)."""
    if ret_end:
        return []  # 되돌림 끝(06) 조각은 호출한 쪽 글과 한 줄에 이어 찍힌다 — 첫 줄 폭을 모른다
    out = []
    pages = split_pages(tokens)
    tagged = any(
        i[0] == "c" and i[1] == "1e" for pg in pages for ln in pg for i in ln
    )  # 스트림에 이름표가 있으면 대사창
    for pi, pg in enumerate(pages):
        lim = (
            210 if scene_mode or tagged else 288
        )  # 전투 메시지 창 288px · 보스 대사(이름표)는 대사창 210px
        unk_lines: set[int] = set()  # 호출·분기가 앞서 찍는 글(폭을 모른다)이 있는 줄
        if pi == 0 and pg and pg[0] and pg[0][0][0] == "t" and pg[0][0][1][:1] == " ":
            unk_lines.add(0)  # 머리 공백 = 앞 글에 이어 찍는 조각(값 칸 뒤 등)
        text_lines = sum(
            1
            for ln in pg
            if (line_text(ln).strip() or has_slot(ln))
            and not any(i[0] == "c" and i[1] in ("1e", "04") for i in ln)
        )
        cells: list[tuple[int, str, bool]] = []  # (줄 번호, 글, 이 글 앞에 `<03>` 이음이 있나)
        intag = False
        after03 = False
        for li, ln in enumerate(pg):
            for x in ln:
                if x[0] == "c":
                    if x[1] == "1e":
                        intag = True
                    elif x[1] == "04":
                        intag = False
                        cells.append((li, "\n", False))
                    elif x[1] == "03":
                        after03 = True
                    elif x[1] in SLOT_CODES:
                        cells.append(
                            (li, "\x00", after03)
                        )  # 이름·값 칸 — 폭이 런타임이라 아래서 이 문장은 건너뛴다(조립형은 check_layout 몫)
                    elif x[1] not in ("0c", "00", "06", "07", "0a", "0d", "09"):
                        cells.append((li, "\n", False))  # 호출·분기·색 등 — 문장 경계로 보고 거른다
                        if x[1] in (
                            "10",
                            "11",
                            "12",
                            "13",
                            "14",
                            "15",
                            "16",
                            "0f",
                            "0e",
                            "0b",
                            "08",
                        ):
                            unk_lines.add(li)
                    continue
                if intag:
                    continue
                cells.append((li, x[1], after03))
                after03 = False if x[1].strip() else after03
            cells.append((li, " ", False))
        s = "".join(c[1] for c in cells)
        li_of = [c[0] for c in cells for _ in c[1]]
        c03 = [c[2] for c in cells for _ in c[1]]
        for sm in re.finditer(r"[^\n]+", s):
            for m in re.finditer(r".*?[.!?…」』]+(?:\s+|$)|.+$", sm.group(0)):
                seg = m.group(0)
                a, b = sm.start() + m.start(), sm.start() + m.end()
                lines = {li_of[i] for i in range(a, b) if s[i].strip()}
                txt = seg.strip()
                if len(lines) < 2 or not txt or "\x00" in txt or min(lines) in unk_lines:
                    continue
                w = linebreak._width(
                    txt.replace("\x00", "").translate(KAGI_MAP)
                ) * 12 + SLOT_PX * txt.count("\x00")
                if w > lim:
                    continue
                head = a + (len(seg) - len(seg.lstrip()))
                joined03 = any(c03[i] for i in range(head, b))
                axis = (
                    "한줄문장쪼갬허용"
                    if (text_lines >= build.LINES or joined03)
                    else "한줄문장쪼갬"
                )
                out.append(
                    (axis, f"쪽{pi + 1} {txt[:30]!r} ({w:.0f}px/{lim}px · 본문 {text_lines}줄)")
                )
    return out


def _lead_px(t: str) -> int:
    n = 0
    for ch in t:
        if ch == " ":
            n += 6
        elif ch == "\u3000":
            n += 12
        else:
            break
    return n


CENTER_LEFT_MAX = (
    6  # 마스터 11-09: 딱 가운데가 안 되면 왼쪽으로 — 원판 중심보다 반각 한 칸(6px)까지 왼쪽은 허용
)
CENTER_DIFF_MAX = 6  # 단일 카드 줄 좌−우 차: 반각 한 칸(6px)까지만 왼쪽
CARD_CENTER = 103.5  # 장 카드 창 안 중심(실측: 좌−우 차 0 인 줄의 중심)
CENTER_RIGHT_MAX = 1  # 오른쪽 쏠림은 측정 오차(1px)만
CARD_WRAP_B = 34  # 원판 문안
CARD_WRAP_B_KR = 35  # 우리 문안 — 화면 실측(둘째 제목 앞 공백 칸 수)이 원판보다 1B 늦게 꺾인다(원인 미상: 같은 바이트 수인데 원판 줄은 34B 에서, 우리 줄은 35B 에서 꺾임). 이유를 찾으면 합친다


def _center_lines(txt: str, wrap: int = CARD_WRAP_B) -> list[tuple[float, str]]:
    """줄마다 (가운데 x px, 글) — 앞 공백 6px(전각 12px) + 글 폭의 절반. 글 폭은 공백 0.5칸·한글 1칸(`linebreak._width`)."""
    out = []
    pieces = []
    for ln in re.split(r"\n|<01>", txt):
        # 엔진은 장 카드 줄을 34바이트(공백 1B·한글/전각 2B)에서 꺾는다 — 한 줄에 제목 둘을 이어 쓴 줄(「제３장 … 제２장 …」)은 화면에선 두 줄이다
        # (11-08 실측: 원판·한글 모두 둘째 제목이 34B 뒤에서 시작, `center-all/cardnpc`).
        t0 = re.sub(r"<[^>]*>", "", ln)
        nb = 0
        for i, ch in enumerate(t0):
            nb += 1 if ord(ch) < 0x80 else 2
            if nb > wrap:
                pieces += [t0[:i], t0[i:]]
                break
        else:
            pieces.append(t0)
    for ln in pieces:
        t = re.sub(r"<[^>]*>", "", ln)
        if not t.strip(" \u3000"):
            continue
        body = t.strip(" \u3000")
        w = linebreak._width(body.replace("\u3000", "  ").translate(KAGI_MAP)) * 12
        out.append((_lead_px(t) + w / 2, body))
    return out


BANNER_TOL = 4.25  # 배너 칸 최소 단위 1B=7.5px → 가장 가까운 위치와의 거리 ≤ 3.75px(+틀 중심 8px 대 7.5px 반올림 0.5)
CENTER_TOL = 3  # 2-8 — 반각 6px 단위 탓에 반 칸(3px) 이하 쏠림은 허용(마스터 11-03 장 제목: 사이 반각 2칸 고정, 가운데는 줄 시작 위치로만)
CENTER_REF = 102  # 가운데 맞춘 장 카드의 중심 — 「끝」 줄(앞 공백 16칸 + 글 12px)과 원판 장 제목이 모두 여기다


def banner_center_items(entries, ink_px: float) -> list[tuple[str, str]]:
    """가운데어긋남(2-8) — 입장 배너·목적지 칸(14B, 바이트당 7.5px, 틀 위치는 원판 그대로)의 글 중심이 틀 중심에서 벗어난 px.
    `ink_px` = 칸 중심 대비 보이는 파란 상자 안쪽 중심의 편향(블록 91 `BANNER_INK_PX`·92/93 `DEST_INK_PX`).
    `entries` = (이름, 한글, 꼬리 바이트 수). 쏠림 = |(왼쪽 공백 − 오른쪽 공백) × 3.75 − ink_px| 가 BANNER_TOL 을 넘으면 걸린다."""
    import field_names as fn

    out = []
    for name, kr, _extra in entries:
        pad = fn.ENTRY_LEN - fn._body_len(
            kr
        )  # 꼬리(extra)는 안 그려지는 글리프라 보이는 글만으로 가운데. 띄운 낱말 사이 공백은 1B
        pl = fn._left_pad_px(fn.ENTRY_LEN - pad, fn.ENTRY_LEN, ink_px)  # 보이는 상자 안쪽 중심 대비 잉크 최근접(편향 `ink_px`)
        pr = pad - pl
        off = abs((pl - pr) * 3.75 - ink_px)
        # 2-8 개정(마스터 11-09 「최대한 가운데」): 가능한 위치 중 가장 가까운 것 — 바이트 단위(7.5px)라 홀수 여백이면 반 바이트(3.75px)가 남는다
        if off > BANNER_TOL:
            out.append(
                ("가운데어긋남", f"배너 {name} {kr!r} 좌 {pl}B · 우 {pr}B → 쏠림 {off:.1f}px")
            )
    return out


def center_axis() -> list[tuple[str, str]]:
    """가운데어긋남(2-8) — 손으로 가운데 맞춘 장 카드(`raw` 스트림)의 줄마다 **실제 픽셀 폭**으로 잰 중심이 원판 같은 줄의 중심과 3px(반 칸) 넘게 다른가
    (원판 줄이 없거나 줄 수가 다르면 `CENTER_REF`). + 가운데 정렬 고정 폭 표(지명·장 제목)의 좌우 여백 차(반각 6px 단위) — 문안을 칸에 넣는 자리라 글 폭이 홀수 칸이면 6px 어긋난다."""
    import archives

    out = []
    orig = common.rom()
    bl = archives.blocks(orig, archives.ARCHIVES["script"][0])
    for p in sorted((common.GAME_DIR / "script").glob("*.json")):
        n = int(p.stem)
        streams = json.loads(p.read_text(encoding="utf-8")).get("streams", {})
        for k, ent in streams.items():
            if not (isinstance(ent, dict) and ent.get("raw") and ent.get("ours")):
                continue
            st = scene.parse_module(bl[n][1]).streams.get(int(k, 16))
            jp = _center_lines(st.text()) if st else []
            kr = _center_lines(ent["ours"], CARD_WRAP_B_KR)
            for i, (cx, body) in enumerate(kr):
                ref = jp[i][0] if len(jp) == len(kr) else CENTER_REF
                two = (
                    ent["ours"].split("\n", 1)[0].count("장") >= 2
                )  # 두 제목 한 줄 카드 = 원판 구조라 원판 중심 기준 유지
                if two:
                    bad = not (-CENTER_LEFT_MAX <= cx - ref <= CENTER_RIGHT_MAX)
                else:  # 단일 제목·끝 줄: 앞 공백(6px 단위) 중 창 중심에 가장 가까운 위치, 동점은 왼쪽 (2-8 — 반각 2칸 고정 뒤 홀수 폭이면 ±3px 중 왼쪽, 11-10)
                    half = linebreak._width(body.replace("\u3000", "  ").translate(KAGI_MAP)) * 6
                    best = min(range(40), key=lambda L: (abs(6 * L + half - CARD_CENTER), L))
                    bad = abs(cx - (6 * best + half)) > 0.5
                if bad:
                    out.append(
                        (
                            "가운데어긋남",
                            f"씬 {n:03d}:{k} 줄{i + 1} 중심 {cx:.0f}px ≠ {ref:.0f}px {body[:14]!r}",
                        )
                    )
    import tables

    tm = build.load_textmaps()
    cs = hangul.Charset(orig, build.collect_chars(tm))
    align = {name: a for name, _s, _w, _sep, _n, a in tables.TABLES}
    for lab, pos, body in build.build_tables(orig, tm["names"], cs):
        name = lab.split(":", 1)[1]
        if align.get(name) != "center":
            continue
        left = len(body) - len(body.lstrip(b" "))
        right = len(body) - len(body.rstrip(b" "))
        exp = (
            build.PLACE_SHIFT_B * 2 if name in ("place_a", "place_b") else 0
        )  # 지명 칸은 박스보다 5.5px 왼쪽이라 한 바이트 민다
        if abs(left - right - exp) * 6 > 2 * CENTER_TOL:  # 좌우 차의 절반이 중심 쏠림
            out.append(("가운데어긋남", f"표 {name}@{pos:#x} 좌 {left * 6}px · 우 {right * 6}px"))
    import field_names as fn

    out += banner_center_items(
        [(f"91:{i:02d}", kr, len(extra)) for i, kr, extra, _jp in fn.ENTRIES],
        ink_px=fn.BANNER_INK_PX,
    )
    out += banner_center_items(
        [
            (f"{blk}:{i:02d}", kr, 0)
            for blk, tbl in fn.DEST.items()
            for i, (_jp, kr) in enumerate(tbl)
        ],
        ink_px=fn.DEST_INK_PX,
    )
    return out


DEFAULT_A5 = 0x85E3


def a5_by_target(b: bytes) -> dict[int, int]:
    """`lea x(pc),a1 [46df] movea.w #MSG,a5` — 스트림 시작 → 창 종류(gpgx_msgview 와 같은 식, 에뮬 모듈을 안 불러오려고 따로)."""
    import struct

    out = {}
    for m in re.finditer(rb"\x43\xfa(..)(?:\x46\xdf)?\x3a\x7c(..)", b, re.DOTALL):
        tg = m.start() + 2 + struct.unpack(">h", m.group(1))[0]
        out.setdefault(tg, struct.unpack(">H", m.group(2))[0])
    return out


def shown_max(tokens) -> int:
    return max(
        (
            sum(1 for ln in pg if line_text(ln).strip() or has_slot(ln))
            for pg in split_pages(tokens)
        ),
        default=0,
    )


def bake():
    """정본 → 굽는 토큰(씬 스트림 · 전투 블록 스트림). 롬을 안 쓴다(build.main 의 check_only 와 같은 경로).
    → (갈래, 자리, 토큰, 정본 문안, 창 종류별 원판 최대 줄 수, 되돌림 끝 조각인가)."""
    import archives

    orig = common.rom()
    tm = build.load_textmaps()
    cs = hangul.Charset(orig, build.collect_chars(tm))
    bl = archives.blocks(orig, archives.ARCHIVES["script"][0])
    caps: dict[int, int] = {}
    mods = {}
    for n in range(len(bl)):
        mods[n] = scene.parse_module(bl[n][1])
        a5 = a5_by_target(bl[n][1])
        for off, st in mods[n].streams.items():
            k = a5.get(off, DEFAULT_A5)
            caps[k] = max(caps.get(k, 0), shown_max(st.tokens))
    for n, m in sorted(tm["maps"].items()):
        a5 = a5_by_target(bl[n][1])
        for k, ent in m["streams"].items():
            if not ent.get("ours") or ent.get("raw"):
                continue
            st = mods[n].streams.get(int(k, 16))
            if st is None:
                continue
            build.WHERE = f"{n:03d}:{k}"
            toks = build.build_stream(st, ent["ours"], cs)
            end = next((x for x in toks if x.kind == "end"), None)
            yield (
                "씬",
                f"{n:03d}:{k}",
                toks,
                ent["ours"],
                caps.get(a5.get(int(k, 16), DEFAULT_A5), 4),
                bool(end and end.code == 0x06),
            )
    bmap = {k: dict(v, ours=build.normalize(v.get("ours", ""))) for k, v in tm["bmap"].items()}
    for n, (_s, bb, _e) in enumerate(battle.blocks(orig)):
        nb = battle.plan_block(bb, n, bmap, tm["monsters"], cs.encode)
        if nb is None:
            continue
        for tgt, ent in battle.refs(nb).items():
            yield ("전투", f"{n:03d}:{tgt:04x}", ent["stream"].tokens, "", 4, False)


def head_blank_pages(tokens) -> int:
    """글이 있는데 머리가 빈 줄인 쪽 수 — 원판도 같은 구조(`<05><01>` 글)가 있어 씬마다 원판 수와 대조한다."""
    n = 0
    for pi, pg in enumerate(split_pages(tokens)):
        if pi and len(pg) > 1 and not pg[0] and any(line_text(ln).strip() for ln in pg):
            n += 1
    return n


def orig_head_blanks() -> dict[int, int]:
    import archives

    orig = common.rom()
    bl = archives.blocks(orig, archives.ARCHIVES["script"][0])
    out: dict[int, int] = {}
    for n in range(len(bl)):
        mod = scene.parse_module(bl[n][1])
        out[n] = sum(head_blank_pages(st.tokens) for st in mod.streams.values())
    return out


def orig_color_spans() -> dict[tuple[str, int], int]:
    """원판 블록별 색 범위 어긋남 수 — 같은 꼴을 우리가 늘리지 않았는지 대조하는 분모."""
    import archives

    orig = common.rom()
    out: dict[tuple[str, int], int] = {}
    bl = archives.blocks(orig, archives.ARCHIVES["script"][0])
    for n in range(len(bl)):
        mod = scene.parse_module(bl[n][1])
        out[("씬", n)] = sum(len(color_spans(st.tokens)) for st in mod.streams.values())
    for n, (_s, bb, _e) in enumerate(battle.blocks(orig)):
        out[("전투", n)] = sum(
            len(color_spans(e["stream"].tokens)) for e in battle.refs(bb).values()
        )
    return out


def orig_page_counts() -> dict[tuple[str, str], int]:
    """원판 스트림별 쪽(`<05>` 로 나뉜 창) 수 — 우리 쪽 수가 이보다 **적은** 곳을 잡는 분모(규칙 2-17: 원문 창을 줄이지 않는다)."""
    import archives

    orig = common.rom()
    out: dict[tuple[str, str], int] = {}
    bl = archives.blocks(orig, archives.ARCHIVES["script"][0])
    for n in range(len(bl)):
        mod = scene.parse_module(bl[n][1])
        for off, st in mod.streams.items():
            out[("씬", f"{n:03d}:{off:04x}")] = len(split_pages(st.tokens))
    for n, (_s, bb, _e) in enumerate(battle.blocks(orig)):
        for tgt, e in battle.refs(bb).items():
            out[("전투", f"{n:03d}:{tgt:04x}")] = len(split_pages(e["stream"].tokens))
    return out


def win_count(tokens) -> int:
    """창 수 = 쪽(`<05>`) 수 + 중간의 `<0a>`(대기 뒤 이어 쓰는 창 — 전투 메시지는 한 스트림에 둘 이상이 이어진다)."""
    toks = list(tokens)
    mid = sum(
        1
        for i, t in enumerate(toks)
        if t.kind != "text" and t.raw[:1] == b"\x0a" and i < len(toks) - 1
    )
    return len(split_pages(toks)) + mid


def _lea_streams(b: bytes) -> dict[int, object]:
    """전투 블록에서 `lea` 가 가리키는 문안 스트림(`battle.refs` 의 `_textlike` 걸름 없이 — 우리 짧은 한글 조각을 놓치지 않는다).
    글이 3글자 미만이고 06 으로 끝나는 연결 조각(「は」+06)은 창이 아니라 뺀다."""
    out: dict[int, object] = {}
    for m in battle.LEA.finditer(b, battle.sections(b)[3]):
        tgt = m.start() + 2 + struct.unpack(">h", m.group(2))[0]
        if not 0 <= tgt < len(b) or tgt in out:
            continue
        try:
            st = scene.parse_stream(b, tgt)
        except (ValueError, IndexError):
            continue
        txt = [t for t in st.tokens if t.kind == "text"]
        if not txt:
            continue
        end = st.tokens[-1]
        if end.kind == "end" and end.code == 0x06 and sum(len(t.raw) for t in txt) < 6:
            continue
        out[tgt] = st
    return out


def window_axis() -> tuple[list[str], list[str], int, int]:
    """창적음(2-17) — 우리 창 수가 원판보다 **적은** 곳. 씬은 스트림별(원판 번지 그대로), 전투는 블록 합(재배치로 번지가 바뀐다).
    → (위반, 잰 스트림·블록 수, 못 잰 수). 못 잰 수가 0 이 아니면 「안 쟀다」다(0 건이 아니다)."""
    import archives

    orig = common.rom()
    tm = build.load_textmaps()
    cs = hangul.Charset(orig, build.collect_chars(tm))
    bad: list[str] = []
    more: list[
        str
    ] = []  # 창많음(2-17) — 우리 창이 원판보다 **많은** 곳. 기준선 래칫(창 수가 늘면 실패)
    measured = skipped = 0
    bl = archives.blocks(orig, archives.ARCHIVES["script"][0])
    for n, m in sorted(tm["maps"].items()):
        mod = scene.parse_module(bl[n][1])
        for k, ent in m["streams"].items():
            if not ent.get("ours") or ent.get("raw"):
                continue
            st = mod.streams.get(int(k, 16))
            if st is None:
                skipped += 1
                continue
            build.WHERE = f"{n:03d}:{k}"
            toks = build.build_stream(st, ent["ours"], cs)
            measured += 1
            if win_count(toks) < win_count(st.tokens):
                bad.append(
                    f"씬 {n:03d}:{k} 원판 {win_count(st.tokens)}창 → 우리 {win_count(toks)}창"
                )
            elif win_count(toks) > win_count(st.tokens):
                more.append(
                    f"씬 {n:03d}:{k} 원판 {win_count(st.tokens)}창 → 우리 {win_count(toks)}창"
                )
    bmap = {k: dict(v, ours=build.normalize(v.get("ours", ""))) for k, v in tm["bmap"].items()}
    for n, (_s, bb, _e) in enumerate(battle.blocks(orig)):
        nb = battle.plan_block(bb, n, bmap, tm["monsters"], cs.encode)
        if nb is None:
            skipped += 1
            continue
        measured += 1
        so = sum(win_count(s.tokens) for s in _lea_streams(bb).values())
        sn = sum(win_count(s.tokens) for s in _lea_streams(nb).values())
        if sn < so:
            bad.append(f"전투 {n:03d} 블록 합 원판 {so}창 → 우리 {sn}창")
        elif sn > so:
            more.append(f"전투 {n:03d} 블록 합 원판 {so}창 → 우리 {sn}창")
    return bad, more, measured, skipped


def measure():
    found: dict[str, list[str]] = {a: [] for a in AXES}
    opc = orig_page_counts()
    total = {"씬": 0, "전투": 0}
    same_as_orig = 0
    per_scene: dict[int, list[str]] = {}
    for kind, where, tokens, ours, cap, ret_end in bake():
        total[kind] += 1
        oc_pages = opc.get((kind, where))
        if oc_pages is not None and len(split_pages(tokens)) < oc_pages:
            found["창적음"].append(
                f"{kind} {where} 원판 {oc_pages}창 → 우리 {len(split_pages(tokens))}창"
            )
        for axis, desc in analyze(tokens, ours, scene_mode=kind == "씬", cap=cap, ret_end=ret_end):
            item = f"{kind} {where} {desc}"
            if axis == "빈줄머리":
                per_scene.setdefault(int(where[:3]), []).append(item)
            else:
                found[axis].append(item)
    oc = orig_color_spans()
    by_block: dict[tuple[str, int], list[str]] = {}
    for it in found["색범위낱말"]:
        by_block.setdefault((it[:2], int(it.split()[1][:3])), []).append(it)
    found["색범위낱말"] = []
    for key, items in sorted(by_block.items()):
        keep = oc.get(key, 0)
        same_as_orig += min(len(items), keep)
        found["색범위낱말"] += items[
            keep:
        ]  # 원판에도 같은 어긋남이 있는 것(「 10 Gold 」 공백 칠)은 원판 수만큼 뺀다
    ob = orig_head_blanks()
    for n, items in sorted(per_scene.items()):
        keep = ob.get(n, 0)
        same_as_orig += min(len(items), keep)
        found["빈줄머리"] += (
            items  # 규칙 2-18(마스터 11-08 「이유 없이 비운 빈 줄은 없앤다」) — 원판과 같은 구조도 면제하지 않는다(11곳을 모두 고침)
        )
    for axis, desc in center_axis():
        found[axis].append(desc)
    found["창적음"], found["창많음"], total["창잼"], total["창못잼"] = window_axis()
    total["원판동일"] = same_as_orig
    return found, total


def _within_base(item: str, base_items: list[str]) -> bool:
    """`창많음` 항목(`씬 NNN:off 원판 B창 → 우리 A창`)이 기준선에 있고 우리 창 수가 기준선 이하인가."""
    key, _, ours = item.rpartition(" → 우리 ")
    for b in base_items:
        bk, _, bo = b.rpartition(" → 우리 ")
        if bk == key:
            return int(ours.rstrip("창")) <= int(bo.rstrip("창"))
    return False


def main() -> int:
    found, total = measure()
    base = json.loads(BASE.read_text(encoding="utf-8")) if BASE.exists() else {a: [] for a in AXES}
    new_total = 0
    print(
        f"조판 축 전수 — 씬 스트림 {total['씬']} · 전투 스트림 {total['전투']}(굽는 토큰) · 머리 빈 줄 중 원판과 같은 구조 {total['원판동일']} · 창 수 잰 {total['창잼']} · 못 잰 {total['창못잼']}"
    )
    for a in AXES:
        new = [x for x in found[a] if x not in base.get(a, [])]
        if (
            a == "창많음"
        ):  # 래칫 — 기준선 항목은 창 수가 같거나 줄면 통과(늘면 실패), 기준선에 없으면 실패
            new = [x for x in found[a] if not _within_base(x, base.get(a, []))]
        new_total += 0 if a in INFO_AXES else len(new)
        print(
            f"  {a}: {len(found[a])}건"
            + (f" (기준선 {len(base.get(a, []))} · 새 {len(new)})" if base.get(a) else "")
        )
        for x in (found[a] if "-v" in sys.argv else new)[:30]:
            print("    ✗" if x in new else "    ·", x)
    if "--freeze" in sys.argv:
        BASE.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
        print("  기준선 갱신")
    if total["창못잼"]:
        print(f"  ✗ 창 수를 못 잰 스트림·블록 {total['창못잼']} — 「안 쟀다」는 0건이 아니다")
        return 1
    return 1 if new_total else 0


if __name__ == "__main__":
    raise SystemExit(main())
