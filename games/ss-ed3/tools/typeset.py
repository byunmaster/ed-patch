"""조판 계약 정본 — **원본 44.2만 자가 스스로 답을 냈다**(2026-08-24 실측).

    python3 games/ss-ed3/tools/typeset.py     # 아래 수치를 그 자리에서 다시 잰다

## 계약

| 무엇          | 값        | 어떻게 알았나                                          |
| ------------- | --------- | ------------------------------------------------------ |
| 대화창 폭     | **17 전각** | 정적 절벽 + **실기 확정**(아래)                        |
| 대화창 줄 수  | **3 줄**    | 페이지당 줄이 3 에서 절벽(1,961 → 4줄 4건) · 실기 확인 |
| 글리프 피치   | **12 px**   | 실기 픽셀 실측 — 셀 경계에 잉크 0                      |
| 화면 폭       | **24 전각** | 나레이션 최대 관측 24 · 320px ÷ 12px = 26.7 과 정합    |
| 반각          | **안 쓴다** | 본편 대사 419,066자 **전부 전각**(반각 0자)            |

정적으로는 **하한만** 나왔다 — 줄을 폭 W 로 접어 3줄에 드는지 재면 `16 → 99.75%` ·
`17 → 99.98%` 이고 18 이상은 차이가 없다(저자가 17 을 안 넘겼으니 당연). 넘침이 **12배**
(63 → 5) 벌어지는 자리가 16/17 사이다.

🔬 **상한은 실기로 닫았다**(2026-08-24, emucap/mednafen). LWRAM 은 MAP 파일을 `0x00200000`
   에 그대로 올리므로(`workraml` 오프셋 = 파일 오프셋, 실측 확인) **대사 한 블록을 눈금자로
   덮어썼다** — `MAP001` 블록 178(97B)을 전각 숫자 48자로. 화면에 나온 결과:

       １２３４５６７８９０１２３４５６７   ← 17
       ８９０１２３４５６７８９０１２３４   ← 17
       ５６７８９０１２３４５６７８▼      ← 14

   **17 에서 접힌다.** 픽셀로도 확인 — 잉크가 x 92~289 에 걸치고 **pitch 12 에서만 셀
   경계 잉크가 0**(11·13 은 글자를 자른다). 정적 추정과 정확히 맞았다.

⚠ **화자는 그 3줄 중 한 줄을 쓴다** — 창이 따로 있는 게 아니라 첫 줄에 노란색으로 찍히고,
   본문이 이어지면 **위로 스크롤**돼 밀려난다. 즉 화자가 있는 첫 페이지는 본문이 2줄이다.

⚠ **창 배치가 여럿이다**(아래 / 위 / 초상화 붙은 것). 폭은 다 17 로 맞춰져 있다 —
   저자 분포에 무릎이 하나뿐인 것이 그 방증이다.

## ⚠ 엔진이 접는다 — 개행이 전부가 아니다

`0D` 는 **강제 개행**이고, 저자가 안 접은 줄은 엔진이 접는다. 대화 39,825줄 중 **566줄이
24자 이상**이다(최대 48). 그래서 「원문에 개행이 있으니 그 자리를 지키면 된다」가 아니라,
**우리 문안도 17자로 접히는 걸 전제**해야 한다.

## 🔴 `0F` 는 「페이지」가 아니라 **대기점**이다 (2026-08-25 실기 확정)

덤프에서 `\f` 로 적는 `0F` 를 오래 「페이지 넘김」이라 불렀는데, 실기에 눈금자를 심어 보니
**창을 비우지 않는다.** 앞 내용이 그대로 남고 **한 줄씩 위로 스크롤**하며 뒤가 이어 붙는다.

    1 페이지 51 자(17×3) 를 채운 뒤 `0F` + 15 자 → 화면:
        ８９Ｂ…      ← 앞 페이지 2 줄째가 그대로
        ５６７８９Ｄ… ← 앞 페이지 3 줄째
        ２３４５６…   ← `0F` 뒤의 새 내용이 **맨 아래 한 줄**로

그래서 계약이 둘로 갈린다:

- **한 `0F` 구간은 3 줄 이하** — 넘으면 사용자가 읽기 전에 위로 밀린다(`overflows` 가 본다).
- **`0F` 는 창을 안 비우므로** 앞뒤 구간이 화면에서 섞여 보인다. 원문의 `0F` 자리를 옮기면
  **읽는 순서가 바뀐다** — 우리 문안은 원문의 `0D`·`0F` 배치를 따르는 것이 기본이다.

⚠ **빈 줄로 끝나는 구간 뒤는 잘린다**(실측). `…24자\n` + `0F` + 32 자를 넣었더니 뒤 구간이
   23 자에서 끊기고 `▼` 도 없이 블록이 끝났다. 원문에 없는 빈 줄을 만들지 않으면 안 만난다.

🔬 재현: `ED_RULER=1 python3 tools/build.py` 로 빌드하면 `reinsert.fit()` 이 **창 계약 검사를
   건너뛴다** — 일부러 긴 줄을 넣어 창에 물어보는 용도다. 평소에는 켜지 않는다.

## ⚠ 나레이션은 다른 물건이다

전각 공백으로 가운데 정렬한 **전체화면 연출**이라 계약이 다르다 — 줄이 17~24자에 몰리고
한 페이지가 **8~11줄**까지 간다. 대화창 기준으로 재면 「넘친다」가 잔뜩 나오는데 전부 오탐이다.
`is_narration()` 이 가른다(대화 17,550 블록 · 나레이션 54 블록).
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

WIN_COLS = 17  # 대화창 폭 (전각)
WIN_ROWS = 3  # 대화창 줄 수
SCREEN_COLS = 24  # 화면 폭 (나레이션 상한)

NL = "\n"  # 덤프에서의 `0D`
PAGE = "\f"  # 덤프에서의 `0F`

_CTRL = re.compile(r"<[0-9A-F]{2}>")
NARR_INDENT = "　"  # 전각 공백 — 나레이션의 표식
NARR_RATIO = 0.5


def visible(s):
    """제어 표기(`<XX>`)를 걷어낸 보이는 글자."""
    return _CTRL.sub("", s)


#   🔴 **숫자는 반각으로 써도 전각으로 그려진다**(2026-09-01 실측 — 화면의 `１` 이 전각
#     글리프였고 칸 간격이 12px 였다. devlog 「숫자가 한글보다 높다」). 그래서 폭을 셀 때
#     ASCII 숫자만 1.0 이다. 나머지 반각(부호·로마자)은 그대로 0.5 다.
def char_cols(c):
    """그 글자가 먹는 슬롯 — 반각 0.5 · 전각 1.0 · **ASCII 숫자는 1.0**."""
    return 0.5 if ord(c) < 0x80 and not c.isdigit() else 1.0


def cols(s):
    """전각 슬롯 폭. 반각은 0.5 로 세지만 **본편 대사엔 반각이 없다**(실측)."""
    return sum(char_cols(c) for c in visible(s))


def lines(text):
    """블록 텍스트 → 빈 줄을 뺀 줄 목록."""
    return [x for x in (visible(l) for pg in text.split(PAGE) for l in pg.split(NL)) if x]


def pages(text):
    """블록 텍스트 → 페이지별 줄 목록."""
    out = []
    for pg in text.split(PAGE):
        ls = [x for x in (visible(l) for l in pg.split(NL)) if x]
        if ls:
            out.append(ls)
    return out


def is_narration(text):
    """전체화면 나레이션인가 — 전각 공백으로 들여쓴 줄이 절반 이상."""
    ls = lines(text)
    return bool(ls) and sum(1 for l in ls if l.startswith(NARR_INDENT)) / len(ls) >= NARR_RATIO


def wrapped_rows(line, width=WIN_COLS):
    """엔진이 접었을 때 이 줄이 차지하는 줄 수."""
    c = cols(line)
    return max(1, -(-int(c * 2) // (width * 2)))  # ceil, 0.5 슬롯까지 정수로


def overflows(text, width=WIN_COLS, rows=WIN_ROWS):
    """대화창 계약을 넘는 페이지 `[(페이지번호, 접힌 줄 수)]`. 나레이션은 재지 않는다."""
    if is_narration(text):
        return []
    bad = []
    for i, ls in enumerate(pages(text)):
        n = sum(wrapped_rows(l, width) for l in ls)
        if n > rows:
            bad.append((i, n))
    return bad


# ── 부호 고아 ────────────────────────────────────────────────────────────────
#   🔴 **엔진은 어절을 안 본다** — 폭이 차면 글자 한복판에서 자른다. 그래서 「전각 17 자 +
#     반각 부호」(17.5 슬롯)인 줄은 **부호 하나만 다음 줄로 밀린다**(유저 실측 2026-08-30).
#     넘겨서 붙일 방법은 없다(폭은 엔진 것이다). 대신 **마지막 공백을 개행으로 바꾸면**
#     어절 경계에서 접혀 부호가 제 낱말과 함께 남는다 — 공백 1B → 개행 1B 라 **길이가 안 변해서**
#     길이 보존 재삽입(`reinsert.fit`)을 안 깨뜨린다.
ORPHAN_PUNCT = "、。，．,.!?！？…」』）)·:;：；~〜"


def fold(line, width=WIN_COLS):
    """엔진이 접는 대로 — **글자 단위**로 자른 줄 목록."""
    out, cur, c = [], "", 0.0
    for ch in visible(line):
        cw = char_cols(ch)
        if c + cw > width:
            out.append(cur)
            cur, c = "", 0.0
        cur += ch
        c += cw
    if cur:
        out.append(cur)
    return out


def rewrap(line, width=WIN_COLS):
    """공백을 개행으로 바꿔 **어절 경계에서** 접은 줄 — 줄 수가 늘면 `None`.

    ⓘ 길이는 안 변한다(공백 ↔ 개행). 줄 수가 늘면 창 계약(3 줄)을 깨뜨릴 수 있어 거른다.
    """
    words = visible(line).split(" ")
    if any(cols(w) > width for w in words):
        return None
    out, cur = [], ""
    for w in words:
        t = w if not cur else cur + " " + w
        if cols(t) > width:
            out.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        out.append(cur)
    return None if len(out) > len(fold(line, width)) else "\n".join(out)


def orphans(text, width=WIN_COLS):
    """부호만 남은 줄이 생기는 줄 `[(줄, 접힌 결과)]`. 나레이션은 재지 않는다."""
    if is_narration(text):
        return []
    out = []
    for ln in lines(text):
        rows = fold(ln, width)
        if any(r.strip() and all(c in ORPHAN_PUNCT for c in r.strip()) for r in rows[1:]):
            out.append((ln, rows))
    return out


def measure(pattern=None):
    """덤프에서 계약 수치를 **다시 잰다** — 문서의 숫자가 코드로 재현돼야 한다."""
    import collections
    import glob
    import json

    pattern = pattern or os.path.join(C.OUT_DIR, "map_jp", "*.json")
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise SystemExit("덤프가 없다 — 먼저 dump_map.py 를 돌린다")
    d_line, n_line = collections.Counter(), collections.Counter()
    d_page, n_page = collections.Counter(), collections.Counter()
    half = 0
    total = 0
    for path in paths:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        for b in rec["blocks"]:
            ls = lines(b["text"])
            if not ls:
                continue
            narr = is_narration(b["text"])
            lc, pc = (n_line, n_page) if narr else (d_line, d_page)
            for l in ls:
                lc[len(l)] += 1
                total += len(l)
                half += sum(1 for c in l if ord(c) < 0x80)
            for pg in pages(b["text"]):
                pc[len(pg)] += 1
    return {
        "dialog_lines": d_line,
        "narr_lines": n_line,
        "dialog_pages": d_page,
        "narr_pages": n_page,
        "chars": total,
        "halfwidth": half,
    }


def _cume(c, upto):
    tot = sum(c.values())
    acc = 0
    out = []
    for k in sorted(c):
        acc += c[k]
        if k in upto:
            out.append((k, c[k], acc / tot * 100))
    return out


def main():
    m = measure()
    print(f"본편 대사 {m['chars']:,}자 · 반각 {m['halfwidth']}자 → 전각 전용 계약")
    print(f"\n대화 줄 길이 (계약 폭 {WIN_COLS})")
    for k, v, p in _cume(m["dialog_lines"], range(WIN_COLS - 2, WIN_COLS + 3)):
        print(f"  {k:>3}자 {v:>6}  누적 {p:6.2f}%")
    print(f"\n대화 페이지당 줄 (계약 {WIN_ROWS}줄)")
    for k in sorted(m["dialog_pages"])[:5]:
        print(f"  {k}줄 {m['dialog_pages'][k]:>6}")
    print(f"\n나레이션 — 블록은 적지만 계약이 다르다 (최대 {max(m['narr_lines'])}자 = 화면 폭)")
    print(f"  줄 {sum(m['narr_lines'].values()):>5} · 페이지당 최대 {max(m['narr_pages'])}줄")
    # 폭을 바꿔 가며 3줄에 드는 비율 — 하한이 어디서 단단해지나
    print("\n폭을 바꿔 접어 보면 (대화 페이지가 3줄에 드는 비율)")
    import glob
    import json

    pgs = []
    for path in sorted(glob.glob(os.path.join(C.OUT_DIR, "map_jp", "*.json"))):
        with open(path, encoding="utf-8") as f:
            for b in json.load(f)["blocks"]:
                if not is_narration(b["text"]):
                    pgs.extend(pages(b["text"]))
    for w in (15, 16, 17, 18, 20):
        ok = sum(1 for ls in pgs if sum(wrapped_rows(l, w) for l in ls) <= WIN_ROWS)
        print(f"  폭 {w}: {ok / len(pgs) * 100:6.2f}%  (넘침 {len(pgs) - ok})")


if __name__ == "__main__":
    main()


# ── 길이 보존 패딩 ────────────────────────────────────────────────────────────
# 재삽입은 **블록 바이트 길이를 안 바꾼다**(대사가 스크립트에 인라인이라 길이를 바꾸면
# 뒤가 전부 밀린다 — `docs/status.md` 5절). 한국어가 일본어보다 짧으니(실측 중앙 0.730)
# 모자란 바이트는 **줄 끝 전각 공백**으로 채운다.
#
# 실기로 확인한 것 셋 (2026-08-24, 눈금자 수법):
#   · 전각 공백은 **접힘에 그대로 세어진다** — 9자 + 8공백 뒤 문자가 다음 줄로 갔다
#   · 줄 끝·줄 전체 공백은 **화면에 흔적이 없다**
#   · 🔴 **`▼` 대기 표시는 텍스트 맨 끝에 붙는다** — 마지막 줄을 채우면 ▼ 가 한 줄
#     밀려 혼자 뜬다(무해하지만 보기 나쁘다). 그래서 **마지막 줄은 안 채운다.**
#
# 반각 공백(`0x20`, 1B)도 확인했다 — **정확히 0.5칸**(6px)이고 접힘에 그대로 세어진다.
# 본편이 반각을 한 자도 안 쓰지만 렌더는 멀쩡하다. 값은 **1바이트 눈금**이다:
# 전각만 쓰면 2B 단위라 예산이 홀수일 때 못 맞춘다(실측 1.8%).
# ⚠ 폭 예산은 안 늘어난다 — 17칸 = 전각 17개 = 반각 34개 = **둘 다 34B** 다.

# ── 아이템·마법 설명 창 ────────────────────────────────────────────────────────
# 대사창(17×3) 과 **다른 창**이고, 🔴 **엔진이 접는 폭과 창이 보여 주는 폭이 다르다**
# (2026-08-25 실기 실측 — 눈금자를 LWRAM 에 심어 쟀다).
#
#   엔진 자동 개행 … **16 자**   17 자를 넣으면 16+1 로 접힌다(전각숫자·한자 두 번 확인)
#   창이 보여 주는 폭 … **약 10 자**   그 뒤는 창 밖이라 **그려지고도 안 보인다**
#   원문 최장 … **9 자**   ← 원문이 16 이 아니라 9 에서 자제한 이유가 이것이다
#
# 🔴 **그래서 10~16 자는 조용히 잘린다.** 엔진은 접지 않고(16 미만이므로) 한 줄로 그리는데
#   창 밖이라 안 보인다. **빌드도 통과하고 길이 검사도 통과한다** — 화면에서만 사라진다.
#   이 레포가 반복해서 물린 「검사를 통과하는데 화면에서만 틀린」 부류다.
# ⚠ 그러니 **엔진 상한(16)을 믿지 않고 원문이 지킨 9 를 쓴다.**
#
# 행은 반대로 넉넉하다 — 창 높이가 167px(≈13 줄)이고 5 줄까지 그려지는 걸 봤다.
# 원문 최다 4 행은 상한이 아니라 여유였다. 일단 4 로 두되 필요하면 늘릴 수 있다.
DESC_COLS = 9
DESC_ROWS = 4
DESC_ENGINE_WRAP = 16  # 엔진이 실제로 접는 자리 — **넘으면 잘린다는 걸 아는 용도**다
DESC_NL = "＄"  # 화면 개행 — 제어코드가 아니라 **전각 문자**다
# 🔴 **어절 공백은 전각이다.** 반각 공백(0x20)을 섞으면 **개행 파싱이 깨진다** — `＄` 가
#    개행되지 않고 `$` 글자로 찍히고 줄이 통째로 어긋난다(2026-08-25 실기 실측).
#    원문 설명문에 반각이 **한 자도 없는** 이유이기도 하다.
DESC_SPACE = "　"


def wrap_desc(text, width=DESC_COLS):
    """한국어를 설명 창 폭으로 접는다 — **어절 단위**.

    일본어 원문은 공백이 없어 손으로 `＄` 를 넣었지만, 한국어는 어절로 끊어야 읽힌다.
    ⚠ 한 어절이 폭보다 길면 그 어절만 강제로 자른다 — 안 그러면 줄이 통째로 사라진다.
    """
    rows, cur = [], ""
    for w in text.split():
        while cols(w) > width:  # 폭보다 긴 어절 — 잘라 넣는다
            if cur:
                rows.append(cur)
                cur = ""
            rows.append(w[: int(width)])
            w = w[int(width) :]
        if not cur:
            cur = w
        elif cols(cur + DESC_SPACE + w) <= width:
            cur += DESC_SPACE + w
        else:
            rows.append(cur)
            cur = w
    if cur:
        rows.append(cur)
    return rows


def desc_overflows(text, width=DESC_COLS, rows=DESC_ROWS):
    """설명 문안이 창을 넘치나 → `(넘침, 행수, 최장폭)`."""
    rs = wrap_desc(text, width)
    wide = max((cols(r) for r in rs), default=0)
    return (len(rs) > rows or wide > width), len(rs), wide


PAD = "\u3000"  # 전각 공백 — 1칸 · 2B
PAD_HALF = " "  # 반각 공백 — 0.5칸 · 1B (홀수 눈금용)


def body_bytes(text):
    """블록 본문의 바이트 수 — 전각 2B · 제어(`\n`·`\f`·`<XX>`) 1B."""
    n = 0
    i = 0
    while i < len(text):
        if text[i] == "<" and i + 3 < len(text) and text[i + 3] == ">":
            n += 1
            i += 4
        elif text[i] in (NL, PAGE):
            n += 1
            i += 1
        else:
            n += 1 if ord(text[i]) < 0x80 else 2
            i += 1
    return n


def pad_to_budget(text, budget, width=WIN_COLS, keep_last=True):
    """본문을 `budget` 바이트에 **정확히** 맞춘다. 못 맞추면 `None`.

    채우는 자리는 각 줄의 끝이고 줄당 `width` 를 안 넘긴다.
    `keep_last` 면 **마지막 줄은 비워 둔다** — `▼` 가 텍스트 끝에 붙어 한 줄 밀리기 때문이다.
    자리가 모자라면 부르는 쪽이 `keep_last=False` 로 한 번 더 시도한다(▼ 위치를 내주고
    길이를 맞추는 쪽이 낫다 — 실측 부족분은 중앙 2자라 대개 마지막 줄로 메워진다).

    `None` 이 나오면 문안이 너무 길거나 자리가 모자라다 — 둘 다 **조판·번역으로 풀 문제**다.
    """
    have = body_bytes(text)
    if have == budget:
        return text
    if have > budget:
        return None  # 문안이 예산보다 길다 — 줄여야 한다
    need = budget - have  # 채워야 할 바이트
    pages = [pg.split(NL) for pg in text.split(PAGE)]
    # ⚠ **반칸 단위로 센다.** 반각이 0.5칸이라 칸을 정수로 반올림하면 자리를 한 칸 더
    #   있다고 착각하고, 그만큼 밀려 **다음 줄 첫 글자가 0.5칸 들여쓰기 된다**(실측).
    #   반칸 하나 = 1바이트라 자리 예산이 곧 바이트 예산이다.
    slots = []
    for pi, pg in enumerate(pages):
        for li in range(len(pg)):
            # 마지막 페이지의 마지막 줄은 ▼ 가 붙는 자리다
            if keep_last and pi == len(pages) - 1 and li == len(pg) - 1:
                continue
            # 🔴 **한 반칸을 남긴다.** 줄을 `width` 칸까지 꽉 채우면 엔진이 **자동으로**
            #    줄을 넘기고, 그 뒤의 `0D` 가 **빈 줄을 하나 더** 만든다. 그러면 페이지가
            #    한 줄 늘어 3줄을 넘고, **화자 줄이 스크롤로 밀려 사라진다**(실기 실측
            #    2026-08-24: 첫 줄을 17칸으로 채웠더니 「クリスの母」가 없어졌다).
            #    ⚠ 경계는 **넘을 때**다(2026-09-27 주입 실측): 17.0 칸 딱 맞음 + `0D` 는
            #      빈 줄이 안 생기고 18 칸 + `0D` 는 생긴다. 반칸 유보는 패딩이 넘치지 않게 하는
            #      안전폭이지, 「17 칸 문안 = 결함」이 아니다(devlog 09-27).
            #    ⚠ 단 **뒤에 `0D` 가 없는 줄**(그 페이지의 마지막 줄)은 그 사고가 없다 —
            #    거기까지 반칸을 유보하면 채울 자리가 모자라 재삽입이 통째로 거부된다.
            room = int(width * 2 - cols(pg[li]) * 2) - (0 if li == len(pg) - 1 else 1)
            if room > 0:
                slots.append((pi, li, room))
    if sum(r for _, _, r in slots) < need:
        return None
    for pi, li, room in slots:
        if need <= 0:
            break
        take = min(room, need)
        # 홀수 바이트는 반각 하나로 맞춘다(0.5칸)
        pages[pi][li] += PAD * (take // 2) + (PAD_HALF if take % 2 else "")
        need -= take
    out = PAGE.join(NL.join(pg) for pg in pages)
    assert body_bytes(out) == budget, (body_bytes(out), budget)
    return out
