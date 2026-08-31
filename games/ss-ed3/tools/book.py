"""`/SYSTEM/BOOK00~39.BIN` — 게임 안에서 읽는 **읽을거리**(소설·메모·해설).

유저 확정 2026-08-25: 「BOOK 은 그냥 스토리와 상관없는 소설이라 번역해도 된다」.

🔴 **줄이 미리 잘려 있다.** 한 줄이 곧 한 문자열이고 오프셋이 고정이라, 문장이 줄 경계에서
끊긴다. 그래서 번역은 **줄이 아니라 문단**에 대고 해야 한다:

    원문 줄들 → 문단 복원 → 번역 → 12 전각으로 다시 나눔 → 줄마다 되끼움

⚠ **줄 수를 원문과 같게** 맞춰야 한다 — 줄이 독립 문자열이라 하나라도 남거나 모자라면
그 뒤가 통째로 어긋난다(설명문에서 배운 것과 같은 함정).

실측(2026-08-25): 줄 폭은 **12 전각**이 압도적이고(BOOK27 은 251 줄 중 167 줄) 13 자가
드물게 있다 — 그 줄은 할당도 한 칸 넓다(간격 27B vs 25B). 문단 시작은 전각 공백이다.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import common as C

COLS = 12  # 한 줄 전각 수 (실측)
INDENT = "　"  # 문단 시작 표식

# 🔴 **읽을거리는 전각만 쓴다 — 반각이 하나라도 끼면 그 줄 뒤가 통째로 뭉갠다.**
#    책 화면(`/BOOKPRG.BIN`)은 텍스트를 **2 바이트씩 고정으로** 읽는다. 원문 38 권에는
#    반각이 **하나도 없어서**(실측) 그 전제가 성립했는데, 우리 한글은 어절 공백이 반각(1B)
#    이라 그 뒤로 정렬이 한 바이트 밀린다. 유저 스크린샷 3 장이 **전부 첫 공백에서** 깨졌다
#    (`＜순례자의` 까지 멀쩡 → 그 뒤 잡음). 대사창은 반각을 처리하므로 이 함정은 책에만 있다.
FULLWIDTH = {
    " ": "　",
    "!": "！",
    '"': "”",
    "'": "’",
    "(": "（",
    ")": "）",
    ",": "，",
    "-": "−",
    ".": "．",
    "/": "／",
    ":": "：",
    ";": "；",
    "<": "＜",
    ">": "＞",
    "?": "？",
    "~": "〜",
    **{chr(0x30 + i): chr(0xFF10 + i) for i in range(10)},  # ０-９
    **{chr(0x41 + i): chr(0xFF21 + i) for i in range(26)},  # Ａ-Ｚ
    **{chr(0x61 + i): chr(0xFF41 + i) for i in range(26)},  # ａ-ｚ
}
# 전각 부호 뒤(앞)의 공백은 뺀다 — 부호에 여백이 붙어 있어 한글 조판에서도 안 넣는 자리다.
_SP_AFTER = set("．，！？』）〟”〜−…。、")
_SP_BEFORE = set("『（“〝")


def to_fullwidth(text):
    """반각을 전각으로 — 남는 반각이 있으면 **실패시킨다**(조용히 깨지느니 멈춘다)."""
    #   ⓘ `|` 는 번역자가 줄을 직접 가르는 표식이라 남긴다(`split_to` 가 걷어낸다).
    out = "".join(c if c == "|" else FULLWIDTH.get(c, c) for c in text)
    bad = {c for c in out if ord(c) < 0x80 and c != "|"}
    if bad:
        raise SystemExit(f"읽을거리에 옮길 수 없는 반각 글자: {sorted(bad)} — {text[:30]!r}")
    return out


def tidy_spaces(text):
    """전각 부호에 붙는 공백을 뺀다 — 조판 관례이자 칸을 아끼는 자리다."""
    out = []
    for i, c in enumerate(text):
        if c == "　":
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if (out and out[-1] in _SP_AFTER) or nxt in _SP_BEFORE:
                continue
        out.append(c)
    return "".join(out)


def load_lines(stem):
    """`work/derived/sys_jp/SYSTEM_<stem>.json` → 줄 목록."""
    p = os.path.join(C.OUT_DIR, "sys_jp", f"SYSTEM_{stem}.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)["strings"]


def paragraphs(lines):
    """줄 목록 → `[(시작줄 색인, [줄...])]`. 문단은 **전각 공백**이나 `＜…＞` 로 시작한다.

    ⚠ 문단을 못 가르면 번역이 줄 경계에 묶여 버린다 — 그게 이 파일의 존재 이유다.
    """
    out = []
    cur = []
    start = 0
    for i, s in enumerate(lines):
        t = s["text"]
        head = t.startswith((INDENT, "＜"))
        if head and cur:
            out.append((start, cur))
            cur, start = [], i
        if not cur:
            start = i
        cur.append(t)
    if cur:
        out.append((start, cur))
    return out


def join_text(rows):
    """문단의 줄들을 한 문장으로 — 들여쓰기는 살리고 줄바꿈만 없앤다."""
    body = "".join(r.lstrip(INDENT) if i else r for i, r in enumerate(rows))
    return body


def _nb(t):
    """바이트 폭 — 전각 2B · 반각 1B."""
    return sum(1 if ord(c) < 0x80 else 2 for c in t)


def _split(text, widths, words):
    """`split_to` 의 알맹이 — `words` 면 **어절 경계**에서만 꺾는다."""
    rows = []
    wi = 0
    for si, seg in enumerate(text.split("|")):
        #   🔴 **앞의 전각 공백을 지우지 않는다.** `strip()` 은 `　`(U+3000)까지 먹는데,
        #     읽을거리에서 그건 **가운데 맞춤**이다(`　　　＜검사교본＞`). 지웠더니 제목이
        #     통째로 왼쪽에 붙었다(유저 스크린샷 2026-08-31).
        seg = seg.rstrip() if si == 0 else seg.strip()
        i = 0
        first = True
        while i < len(seg) or first:
            if wi >= len(widths):
                return rows, False
            while i < len(seg) and seg[i] == "　" and not (first and not rows):
                i += 1  # 줄머리 공백 버리기 (맨 첫 줄의 들여쓰기·가운데 맞춤은 남긴다)
            room = widths[wi]
            cur, used = "", 0
            while i < len(seg) and used + _nb(seg[i]) <= room:
                cur += seg[i]
                used += _nb(seg[i])
                i += 1
            #   🔴 **어절 한복판에서 끊겼으면 마지막 공백까지 물린다 — 단 여유가 있을 때만.**
            #     「어절 모드/글자 모드」를 통째로 가르면 한 줄이 빠듯한 문단은 **전부**
            #     글자 단위로 떨어진다(실측: 「무너지/지」 한 자 때문에 문단 전체가 갈렸다).
            #     그래서 물릴 때마다 **남은 칸에 나머지가 들어가는지** 재고 결정한다.
            if words and i < len(seg) and seg[i] != "　" and cur and cur[-1] != "　":
                back = cur.rfind("　")
                #   ⚠ **줄이 확 짧아지면 안 물린다** — 낱말 하나를 살리려다 줄 절반이
                #     비면 그게 더 안 읽힌다(실측: 「　『필살의」 한 줄이 났다).
                if back > 0 and _nb(cur[:back]) * 4 >= room * 3:
                    rest = _nb(seg[i - (len(cur) - back) :].lstrip("　"))
                    if rest <= sum(widths[wi + 1 :]):
                        i -= len(cur) - back
                        cur = cur[:back]
            rows.append(cur)
            wi += 1
            first = False
            if not cur and i < len(seg):
                return rows, False  # 한 글자도 못 넣는 칸 — 못 들어간다
    rows += [""] * (len(widths) - len(rows))
    return rows[: len(widths)], True


def split_to(text, widths):
    """번역문을 **원문 각 줄의 폭**(`widths`)에 맞춰 나눈다 → `(줄 목록, 들어갔나)`.

    🔴 줄마다 칸이 다르다 — 문단 끝 줄은 짧고, 드물게 13 자짜리도 있다. 균등하게 12 자로
    나누면 **짧은 줄에서 넘친다**(실측: 8B 칸에 18B 를 넣으려 했다). 그래서 원문 줄 폭을
    그대로 따라간다. 재는 단위는 **칸이 아니라 바이트**다(전각 2B · 반각 1B).

    ⚠ `|` 로 줄을 직접 가를 수 있다 — 표제와 본문을 안 붙이려는 자리에 쓴다.

    🔴 **어절 경계를 먼저 시도하고, 안 들어가면 글자 단위로 떨어진다**(2026-08-31 유저 지적).
      · 글자 단위로만 채웠더니 「그때까지 각/자 정진하도록」·「그럼『검/사교본」처럼
        낱말이 갈려 안 읽혔다.
      · 그렇다고 어절 단위만 쓰면 줄 끝마다 칸이 남아 **129 문단이 넘친다**(그래서 한때
        글자 단위로 돌렸었다). ⇒ 줄마다 **남은 칸을 재서** 여유가 있을 때만 어절로 물리고,
        그래도 안 들어가면 문단 전체를 글자 단위로 다시 떨어뜨린다(마지막 보루).
    """
    rows, ok = _split(text, widths, words=True)
    if ok:
        return rows, ok
    return _split(text, widths, words=False)


def fit_spaces(text, widths):
    """칸에 안 들어가면 **띄어쓰기를 필요한 만큼만** 줄인다 → `(문안, 뺀 개수)`.

    🔴 원문 일본어엔 띄어쓰기가 아예 없다 — 한 칸이 곧 한 글자다. 우리 한글은 어절 공백이
    칸을 먹으므로 같은 내용이 원문보다 길어진다. 문안을 줄이는 대신 **공백부터** 줄인다.
    ⓘ 빼는 차례는 **뒤에 오는 낱말이 짧은 자리부터**다(「감춘 지」→「감춘지」처럼 붙여도
      읽히는 자리). 같은 길이면 뒤쪽부터 — 앞머리 조판을 덜 흔든다.
    ⚠ 그래도 안 들어가면 그대로 돌려준다. 문안을 줄여야 하는 자리라 **게이트가 잡아야 한다.**
    """
    if split_to(text, widths)[1]:
        return text, 0
    ch = list(text)
    cand = []
    for i, c in enumerate(ch):
        if c != "　":
            continue
        j = i + 1
        while j < len(ch) and ch[j] not in ("　", "|"):
            j += 1
        cand.append((j - i - 1, -i, i))  # 뒤 낱말이 짧은 것 · 뒤쪽 먼저
    for _, _, i in sorted(cand):
        ch[i] = ""
        t = "".join(ch)
        if split_to(t, widths)[1]:
            return t, sum(1 for x in ch if x == "")
    return "".join(ch), sum(1 for x in ch if x == "")


def split_cols(text, cols=COLS):
    """번역문을 `cols` 전각으로 나눈다 — **어절 경계**를 지킨다.

    ⚠ 한국어는 글자 단위로 끊으면 안 읽힌다. 다만 줄 수를 맞춰야 하므로, 어절이 폭보다
    길면 그 어절만 자른다.
    """
    rows, cur = [], ""
    for w in text.split(" "):
        while len(w) > cols:
            if cur:
                rows.append(cur)
                cur = ""
            rows.append(w[:cols])
            w = w[cols:]
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= cols:
            cur += " " + w
        else:
            rows.append(cur)
            cur = w
    if cur:
        rows.append(cur)
    return rows


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("stem", nargs="?", default="BOOK27")
    a = ap.parse_args()
    lines = load_lines(a.stem)
    if not lines:
        raise SystemExit(f"덤프가 없다: SYSTEM_{a.stem}.json")
    ps = paragraphs(lines)
    print(f"{a.stem}: {len(lines)} 줄 · 문단 {len(ps)}")
    for i, (at, rows) in enumerate(ps[:8]):
        print(f"  [{i}] 줄 {at}~{at + len(rows) - 1} ({len(rows)} 줄)  {join_text(rows)}")


if __name__ == "__main__":
    main()
