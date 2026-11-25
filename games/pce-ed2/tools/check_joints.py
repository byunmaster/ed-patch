"""이음 대조 — 원판과 **구운 이미지 바이트**에서 줄·쪽·변수 자리의 이음새가 깨진 곳을 셋으로 센다(마스터 10-30 「보물상자처럼 띄어쓰기 개행 제대로 안 된 게 꽤 있을 것 같은데」 — pce-ed1 에서 같은 부류 셋이 나왔다).

  ① 변수 자리 앞 공백 — 엔진이 끼워 넣는 칸(`{name}`=`07`·`1A`·`1B` · `1C nn` 이름 · `1D nn` 아이템 · `1E nn` · `13 nn` 수)의 **바로 앞이 한글**이면 어절이 붙는다
     (「보물상자에는{아이템}이」). 토큰 뒤 조사는 붙는 게 맞으니 앞만 본다. 화자 머리(`16 … 14`)의 이름 자리와 숫자 사이 단위(`시간{수}분`)는 대상이 아니다.
  ② 끝 개행 — 원판 메시지가 줄바꿈(`↵`)·쪽 넘김(`⏎`)으로 끝나는데 한글이 아니면 다음 메시지가 같은 줄에 붙는다(pce-ed1 「왕자!?자, 잠시」 48곳).
  ③ 쪽 넘침(대사 덩이만) — 한글 쪽(쪽 가름 `⏎`·`{12}` 사이)이 대사창에 담기는 줄 수(원판 최대 4줄)를 넘기면 잘린다. 화자 머리줄은 세지 않는다.
  ④ 낱말 속 접힘(대사 덩이만) — 조판기가 낱말을 줄·쪽 사이로 쪼갠 곳. 번역할 줄의 **문안**을 조판기에 다시 태워 어절 열을 맞대 본다(구운 바이트가 아니라 조판 결과라, 조판을 건너뛰는 잠금 줄은 못 본다).

쪽을 합친 것(원판 쪽 수 > 한글 쪽 수)은 번역 규칙 2-16 이 정한 재조판이라 결함이 아니다 — 위 ③ 이 창에 담기는지만 본다.

    python3 check_joints.py [--iso <이미지>] [--gate]
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
import dialog
import dialogue
import package
import pairs
import typeset

HANGUL = re.compile("[가-힣]")
VAR = re.compile(r"\{(?:name|1[CDE] [0-9A-F]{2}|13 [0-9A-F]{2})\}")
HEAD = re.compile(r"\{16\}[^{↵⏎]*(?:\{name\}|\{14\})?")
CTRL_TAIL = re.compile(r"\{[0-9A-F]{2}(?: [0-9A-F]{2})*\}$")
PAGE_MAX = 4
FOLD_N = 0  # ④ 이 훑은 문안 조각 수
# 대상 밖(이유가 있는 자리) — 열쇠: 이유
ALLOW = {"S6A:13E9": "타임 시·분 자리 사이 단위(「시간{수}분」)"}


def glued_var(ko: str) -> bool:
    """변수 자리 바로 앞이 한글인가(화자 머리 제외)."""
    t = HEAD.sub("", ko)
    return any(m.start() > 0 and HANGUL.match(t[m.start() - 1]) for m in VAR.finditer(t))


def end_mark(s: str) -> str:
    """끝의 제어(`{HH …}`)를 벗긴 마지막 글자."""
    s = s.rstrip()
    while True:
        t = CTRL_TAIL.sub("", s).rstrip()
        if t == s:
            return s[-1:]
        s = t


def lost_end(orig: str, ko: str) -> bool:
    """원판은 `↵`·`⏎` 로 끝나는데 한글은 아닌가."""
    eo = end_mark(orig)
    return eo in ("↵", "⏎") and end_mark(ko) != eo


def over_pages(ko: str) -> list[int]:
    """한글 쪽 중 줄 수가 창을 넘는 쪽의 줄 수들."""
    out = []
    for p in re.split(r"⏎|\{12\}", ko):
        p = HEAD.sub("", p)
        n = len([x for x in p.split("↵") if re.sub(r"\{[^}]*\}", "", x).strip()])
        if n > PAGE_MAX:
            out.append(n)
    return out


def word_split(txt: str, pgs: list[list[str]]) -> bool:
    """조판 결과(`pgs`)가 문안(`txt`)의 낱말을 쪼갰나 — 줄·쪽을 어절로 풀어 문안 어절 열과 다르면 참(어절 사이에서만 줄이 꺾였다면 같다)."""
    words = typeset.spaced(txt.replace("~", "～")).replace("\f", " ").replace("\n", " ").split()
    return [t for p in pgs for ln in p for t in ln.split()] != words


def folded_words() -> tuple[int, list[str]]:
    """대사 덩이마다 번역할 줄의 문안을 조판기에 다시 태워 낱말 속 접힘을 센다 — (훑은 문안 수, 걸린 열쇠 `rel:덩이:줄`)."""
    n, bad = 0, []
    for rel, start in dialogue._chunks_with_work():
        orig = common.track_data(rel, 128)
        end = next(e for s, e in package.chunks(orig) if s == start)
        raw, _ = package.decode_chunk(orig, start, end)
        for li, _p, _spk, txt in dialogue.candidates(rel, start, raw):
            for piece in txt.split("§"):
                piece = piece.replace("¶", "\f").lstrip(" ")
                if not piece.strip():
                    continue
                n += 1
                if word_split(piece, typeset.pages(piece, headed=bool(_spk) or isinstance(_p, dialog.Seg))):
                    bad.append(f"{rel}:{start}:{li}: {piece[:40]}")
    return n, bad


def analyze(iso: str) -> tuple[int, dict[str, list[str]]]:
    kg = pairs.KoGlyphs(iso)
    fails: dict[str, list[str]] = {"변수 앞 붙음": [], "끝 개행 누락": [], "쪽 넘침": [], "낱말 속 접힘": []}
    rows = 0
    for fn in (pairs.package_rows, pairs.literal_rows, pairs.table_rows, pairs.code_rows):
        for key, o, k, _sh in fn(iso, kg):
            if not k.strip() or not o.strip() or key in ALLOW:
                continue
            rows += 1
            if glued_var(k):
                fails["변수 앞 붙음"].append(f"{key}: {k[:60]}")
            if lost_end(o, k):
                fails["끝 개행 누락"].append(f"{key}: …{k[-24:]}")
            if key[0].isdigit() and over_pages(k):  # 대사창은 장면 패키지 덩이만 — 본 프로그램 메뉴·표는 창 모양이 다르다
                fails["쪽 넘침"].append(f"{key}: {over_pages(k)}줄")
    n, bad = folded_words()
    fails["낱말 속 접힘"] = bad
    global FOLD_N
    FOLD_N = n
    return rows, fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", default=str(common.BUILD_DIR / "pce-ed2" / "ed2.iso"))
    ap.add_argument("--gate", action="store_true")
    a = ap.parse_args()
    rows, fails = analyze(a.iso)
    n = sum(len(v) for v in fails.values())
    print(f"  이음 대조 [pce-ed2] — 양쪽에 글이 있는 {rows}행 · 낱말 접힘은 문안 {FOLD_N}조각 · " + " · ".join(f"{k} {len(v)}" for k, v in fails.items()))
    for k, v in fails.items():
        for f in v[:20]:
            print(f"  ✖ {k} {f}")
    return 1 if (a.gate and n) else 0


if __name__ == "__main__":
    sys.exit(main())
