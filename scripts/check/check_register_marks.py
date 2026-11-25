#!/usr/bin/env python3
"""말투 흔적 검사 — 「요」만 떼어 낸 치환 사고와 높임·낮춤이 한 문장에 섞인 꼴을 우리 문안에서 찾는다.

    python3 scripts/check/check_register_marks.py --game sfc-ed1          # 요약
    python3 scripts/check/check_register_marks.py --game sfc-ed1 --list   # 자리 전부
    python3 scripts/check/check_register_marks.py --game sfc-ed1 --strict # 「결함」 부류가 있으면 rc 1

왜: 11-11~13 말투 원문 등급 작업이 존댓말에서 「요」만 떼어 「저+반말」·「여러분+반말」·「죄송해.」 같은
꼴을 남겼고, 게임 게이트는 마지막 어절만 봐서 놓쳤다(Fable 검수 11-14 — 10게임 1,137행 중 말투 809).
글자만 보는 검사라 화자·듣는 이는 모른다 — 그래서 둘로 가른다:

- **결함**(문장 안에서 스스로 모순, 화자를 몰라도 틀림): R1 「저/제가…」+반말 · R2 「여러분」+반말 ·
  R3 「요」만 뗀 틀린 꼴(죄송해 · 안녕히 계셔 · ~습지 · Gold이야 …).
- **후보**(사람이 봐야 함): R4 반말 끝에 「-시-」(듣는 이 높임일 수도, 제3자 높임일 수도 — 4-16③).

문안은 이름 검사와 같은 어댑터(`games/<게임>/tools/names_corpus.py` 의 `pairs()`)에서 「dialog」 갈래만 받는다 —
게임이 따로 낼 것이 없다. 어댑터가 없으면 「안 쟀다」(rc 2).
종료 코드: 0 = 결함 없음 또는 알림 모드 · 1 = --strict 이고 결함 있음 · 2 = 어댑터 없음.
"""

import argparse
import importlib.util
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 문장을 끊는 부호 — 줄바꿈은 창 안 접힘이라 문장 경계가 아니다.
SPLIT = re.compile(r"(?<=[.!?…])\s+|(?<=[.!?])(?=[^.!?…\s])")
# 「|」·「<..>」 제어 부호는 줄·화자 경계라 빈칸으로 — 지우면 다음 화자 줄이 앞 문장에 붙는다(sfc-ed2 「|09」 · md-ed2 「<01><1e>병사<04>」 거짓 양성 11-14)
NOISE = re.compile(r"\{[^}]*\}|%[0-9]*[a-zA-Z]|\[[^\]]*\]")
PIPE = re.compile(r"\|+|<[^>]*>")
TAIL = re.compile(r"[\s.!?…～〜~♪」』）)\"'”’,]+$")

POLITE_END = re.compile(r"(요|니다|니까|시오|소서|죠|오|소|옵니다|사옵니다)$")
BANMAL_END = set("어아야지해냐니래자군걸데다렴게네까라대돼줘봐와워써")

FIRST_HUMBLE = re.compile(
    r"(?:^|[\s,「『(])(저는|저도|저를|저와|저랑|저한테|저에게|저만|저까지|저부터|제가|저희)(?=[\s,.!?…]|$)"
)
YEOREOBUN = re.compile(r"여러분(?!께)")

BROKEN = [
    (re.compile(r"죄송해(?=[\s.!?…]|$)"), "죄송해(요 뗌)"),
    (re.compile(r"안녕히 계셔(?![요서])"), "안녕히 계셔(요 뗌)"),
    (re.compile(r"안녕히 가(?=[.!?…]|$)"), "안녕히 가(요 뗌)"),
    (re.compile(r"습지(?=[\s.!?,…]|$)"), "~습지(없는 말 — 습죠/습지요)"),
    (re.compile(r"[A-Za-z]이(?=야|다|에요|었)"), "영문 낱말+이(읽는 소리로 — Gold야)"),
    (re.compile(r"감사해(?=[.!?…]|$)"), "감사해(요 뗌?)"),
]
HON_BANMAL = re.compile(r"(?:으?시|셨|셔)(?:어|지|잖아|냐|니|네|군|야|다)$")


def _adapter(game, root):
    path = os.path.join(root, "games", game, "tools", "names_corpus.py")
    if not os.path.exists(path):
        return None
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location(f"names_corpus_{game}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sentences(text):
    flat = PIPE.sub(" ", NOISE.sub("", text)).replace("\n", " ")
    flat = re.sub(r"\s+", " ", flat).strip()
    return [s for s in SPLIT.split(flat) if s.strip()]


def ending(sent):
    """문장 끝 한 덩이(부호 뗀 마지막 어절)."""
    core = TAIL.sub("", sent).strip()
    return core.split(" ")[-1] if core else ""


def _jong_b(ch):
    """받침이 ㅂ 인 한글 음절인가 — 「합시다·갑시다」(ㅂ시다 청유)를 가른다."""
    o = ord(ch) - 0xAC00
    return 0 <= o < 11172 and o % 28 == 17


def is_upsida(word):
    return len(word) >= 3 and word.endswith("시다") and _jong_b(word[-3])


def is_banmal(word):
    if len(word) < 2 or POLITE_END.search(word) or is_upsida(word):
        return False
    return word[-1] in BANMAL_END


def audit_line(kr):
    hits = []
    for s in sentences(kr):
        end = ending(s)
        # 끝맺은 문장만 — 쉼표·말줄임으로 끊긴 조각(「…모아 봐야」「…만들 테니,」)은 다음 블록에서 이어진다
        closed = bool(re.search(r"[.!?～〜][」』）)\"'”’]*$", s.strip()))
        ban = closed and is_banmal(end)
        m = FIRST_HUMBLE.search(s)
        if ban and m and m.group(1) != end:
            hits.append(("결함", "R1 저/제가+반말", s))
        if ban and YEOREOBUN.search(s):
            hits.append(("결함", "R2 여러분+반말", s))
        for rx, why in BROKEN:
            if rx.search(s):
                hits.append(("결함", f"R3 {why}", s))
        if HON_BANMAL.search(end) and not is_upsida(end):
            hits.append(("후보", "R4 반말+-시-", s))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--root", default=ROOT, help="게임 트리 뿌리(관리자가 워크트리를 잴 때)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    mod = _adapter(a.game, a.root)
    if mod is None:
        print(f"  ⚠ [{a.game}] 말투 흔적 — 어댑터 없음(안 쟀다)")
        return 2
    rows = [(w, kr) for (w, _jp, kr, kind) in mod.pairs() if kr and kind == "dialog"]
    found = []
    for where, kr in rows:
        for level, rule, s in audit_line(kr):
            found.append((level, rule, where, s))
    bad = [f for f in found if f[0] == "결함"]
    cand = [f for f in found if f[0] == "후보"]
    by = {}
    for lv, rule, _, _ in found:
        by[(lv, rule)] = by.get((lv, rule), 0) + 1
    print(f"  말투 흔적 [{a.game}] — 대사 {len(rows)}줄 · 결함 {len(bad)} · 후보 {len(cand)}")
    for (lv, rule), n in sorted(by.items()):
        print(f"     {lv} {rule}: {n}")
    if a.list:
        for lv, rule, where, s in found:
            print(f"{lv}\t{rule}\t{where}\t{s}")
    return 1 if (a.strict and bad) else 0


if __name__ == "__main__":
    sys.exit(main())
