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


#   ⚠ **닫는 부호를 빠뜨리면 멀쩡한 자리가 갈림으로 잡힌다** — `＞`·`】`·`〜`·`’` 가
#     빠져 있어서 표제(`＜…＞`·`【…】`) 끝에서 끊긴 줄이 전부 걸렸다(2026-09-03 실측:
#     남은 갈림의 3 할이 이것이었다). 본문에 실제로 쓰이는 부호를 눈으로 세어 채웠다.
PUNCT = "，．？！、。」』）〉》＞】…・：；〜’"  # 뒤에서 끊겨도 읽히는 부호
OPEN = "「『（〈《＜【"  # 앞에서 끊겨도 읽히는 부호


def _breaks_word(text, k):
    """`k` 자리에서 줄을 끊으면 **낱말이 갈리나**.

    🔴 `|` 는 **번역자가 일부러 가른 자리**다 — 공백과 같이 본다. 안 그러면 의도한 개행이
      전부 「낱말이 갈렸다」로 세어져, 문안을 아무리 줄여도 안 없어지는 유령이 남는다.
    """
    if k <= 0 or k >= len(text):
        return False
    if text[k] in "　|" or text[k - 1] in "　|":
        return False
    return not (text[k - 1] in PUNCT or text[k] in PUNCT or text[k - 1] in OPEN)


def word_cuts(text, rows):
    """`split_to` 가 낸 줄들 중 **낱말 한복판에서 끊긴 이음매** 수.

    ⚠ 「줄 끝 글자 + 다음 줄 첫 글자」를 원문에서 `find` 로 찾으면 **같은 두 글자가 앞에
      또 있으면 엉뚱한 자리를 잰다**. 그래서 줄을 원문에 대고 **차례로 물려 가며** 센다.
    """
    i, n = 0, 0
    for r in rows[:-1]:
        if not r:
            continue
        while i < len(text) and not text.startswith(r, i):
            i += 1
        if i >= len(text):
            break
        i += len(r)
        n += _breaks_word(text, i)
    return n


def split_to(text, widths):
    """번역문을 **원문 각 줄의 폭**(`widths`)에 맞춰 나눈다 → `(줄 목록, 들어갔나)`.

    🔴 줄마다 칸이 다르다 — 문단 끝 줄은 짧고, 드물게 13 자짜리도 있다. 균등하게 12 자로
    나누면 **짧은 줄에서 넘친다**(실측: 8B 칸에 18B 를 넣으려 했다). 그래서 원문 줄 폭을
    그대로 따라간다. 재는 단위는 **칸이 아니라 바이트**다(전각 2B · 반각 1B).

    ⚠ `|` 로 줄을 직접 가를 수 있다 — 표제와 본문을 안 붙이려는 자리에 쓴다.

    🔴 **줄마다 최적을 찾는다**(2026-09-01). 예전엔 「어절 모드로 해 보고 안 되면 문단 전체를
      글자 단위로」였는데, 둘 다 **한 줄만 보고 욕심껏 채우는** 방식이라 손해가 컸다 —
      어절 모드 안에도 「물리면 줄이 3/4 밑으로 짧아지니 그냥 끊자」는 규칙이 있어,
      들어가는 문단에서도 낱말이 갈렸다(실측: 「무너지│지」).
      ⇒ **낱말이 갈리는 자리 수를 최소로** 하는 배분을 DP 로 고른다. 한 줄을 덜 채워서라도
      뒤가 좋아지면 그쪽을 고른다. 실측 2026-09-01: 낱말 갈림 **362 → 279**(-23%),
      나빠진 문단 0. 남은 279 는 **문안이 칸보다 길어** 조판으로는 못 푸는 자리다.
    ⓘ 부호 앞뒤(「，．」·여는 괄호)는 갈려도 읽히므로 **낱말 갈림 비용**을 안 매긴다.
    🔴 다만 **비용이 낱말 갈림 하나뿐이면 조판이 이상해진다**(2026-09-03 인게임 실측).
      문안을 줄여 여유가 생기자 DP 가 남는 자리를 아무 데나 흘려, `．` 만 홀로 선 줄과
      두 글자짜리 줄이 나왔다. ⇒ 값이 낮은 벌점 둘을 더한다:
        · **줄 첫 글자가 닫는 부호**(`．，」…`) — 앞 줄에 붙는 게 읽힌다
        · **줄 끝 글자가 여는 부호**(`「（＜`) — 뒷 줄에 붙는 게 읽힌다(대칭)
        · **절반도 못 채운 줄**(마지막 줄은 뺀다) — 앞뒤가 들쭉날쭉해 보인다
      ⚠ 낱말 갈림보다 **싸게** 매긴다(10 : 5 : 2) — 미관 때문에 갈림을 늘리면 본말전도다.
    """
    CUT, ORPHAN, SHORT = 10, 5, 2
    n, ln = len(text), len(widths)
    INF = 1 << 20
    memo = {}

    def f(i, j):
        while j < n and text[j] == "　" and not (i == 0 and j == 0):
            j += 1
        while j < n and text[j] == "|":
            j += 1
        if j >= n:
            return 0, ()
        if i >= ln:
            return INF, ()
        key = (i, j)
        if key in memo:
            return memo[key]
        best = (INF, ())
        used, k = 0, j
        while k < n:
            if text[k] == "|":  # 번역자가 직접 가른 자리 — 여기서 줄을 닫는다
                sub, rows = f(i + 1, k + 1)
                if sub < best[0]:
                    best = (sub, (text[j:k],) + rows)
                break
            w = _nb(text[k])
            if used + w > widths[i]:
                break
            used += w
            k += 1
            sub, rows = f(i + 1, k)
            #   다음 줄이 실제로 어디서 시작하나 — 공백·`|` 는 건너뛴다
            k2 = k
            while k2 < n and (text[k2] == "　" or text[k2] == "|"):
                k2 += 1
            cost = sub + CUT * _breaks_word(text, k)
            if k2 < n and text[k2] in PUNCT:
                cost += ORPHAN
            #   🔴 **여는 부호가 줄 끝에 홀로 남는 것**도 같은 벌점이다 — 닫는 부호가 줄
            #     첫머리에 오는 것만 막고 이쪽을 안 막으면 대칭이 안 맞아,
            #     `…떠오른다．「` 처럼 낫표만 떨어져 나온 줄이 남는다(2026-09-03 실측 10 줄
            #     → 5 줄, 갈림은 그대로). 남은 5 는 줄이 꽉 차서 물리적으로 못 옮긴다.
            if text[k - 1] in OPEN:
                cost += ORPHAN
            if k2 < n and used * 2 < widths[i]:
                cost += SHORT
            if cost < best[0]:
                best = (cost, (text[j:k],) + rows)
        memo[key] = best
        return best

    cost, rows = f(0, 0)
    rows = list(rows)
    if cost >= INF:
        #   못 들어간다 — 앞에서부터 최대한 채워 **어디서 넘치는지** 보이게 돌려준다.
        out, i, j = [], 0, 0
        while i < ln and j < n:
            used, k = 0, j
            while k < n and text[k] != "|" and used + _nb(text[k]) <= widths[i]:
                used += _nb(text[k])
                k += 1
            out.append(text[j:k])
            j = k + (1 if k < n and text[k] == "|" else 0)
            while j < n and text[j] == "　":
                j += 1
            i += 1
        return out + [""] * (ln - len(out)), False
    return rows + [""] * (ln - len(rows)), True


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
