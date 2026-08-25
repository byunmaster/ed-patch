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
        head = t.startswith(INDENT) or t.startswith("＜")
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


def split_to(text, widths):
    """번역문을 **원문 각 줄의 폭**(`widths`)에 맞춰 나눈다 → 줄 목록.

    🔴 줄마다 칸이 다르다 — 문단 끝 줄은 짧고, 드물게 13 자짜리도 있다. 균등하게 12 자로
    나누면 **짧은 줄에서 넘친다**(실측: 8B 칸에 18B 를 넣으려 했다). 그래서 원문 줄 폭을
    그대로 따라간다.

    ⚠ 어절 경계를 지키되, 어절이 그 줄 폭보다 길면 잘라 넣는다(안 그러면 줄이 사라진다).
    """

    # 🔴 재는 단위는 **칸이 아니라 바이트**다. 전각 2B · 반각 1B 이고 폭은 언제나
    #    `바이트/2` 칸이므로, 바이트만 맞추면 화면 폭도 저절로 맞는다. 한국어 어절 공백은
    #    반각(1B)이라 칸으로 세면 과대 계산이 된다(실측: 11 칸 줄에 들어갈 문안을 퇴짜 놓았다).
    def nb(s):
        return sum(1 if ord(c) < 0x80 else 2 for c in s)

    # ⚠ `|` 로 **줄을 직접 가를 수 있다.** 자동 배분은 어절 경계만 보므로 원문 줄 폭이
    #   들쭉날쭉하면(예: 22B·8B·12B) 첫 줄에 8B 만 들어가는 식으로 낭비된다. 그럴 때
    #   번역자가 `|` 로 끊는다.
    if "|" in text:
        parts = [x.strip() for x in text.split("|")]
        parts += [""] * (len(widths) - len(parts))
        fits = len(parts) <= len(widths) and all(
            sum(1 if ord(c) < 0x80 else 2 for c in r) <= w for r, w in zip(parts, widths)
        )
        return parts[: len(widths)], fits

    rows, i = [], 0
    words = text.split(" ")
    for w_i, room in enumerate(widths):
        cur = ""
        last = w_i == len(widths) - 1
        while i < len(words):
            w = words[i]
            cand = w if not cur else cur + " " + w
            if nb(cand) <= room:
                cur = cand
                i += 1
                continue
            if not cur:  # 한 어절이 줄보다 길다 — 잘라 넣는다
                k = 0
                while k < len(w) and nb(w[: k + 1]) <= room:
                    k += 1
                if k:
                    cur, words[i] = w[:k], w[k:]
            break
        rows.append(cur)
        if i >= len(words) and not last:
            rows += [""] * (len(widths) - len(rows))
            break
    return rows, i >= len(words)


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
