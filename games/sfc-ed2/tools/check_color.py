"""색 제어 코드 점검(규칙 4-6 — 색·연출 코드는 원판 그대로, 바꾸는 건 글자뿐) — 문안 지도의 한글 구간을 원판 구간과 맞댄다.

① 색 열기(`<18>`~`<1d>`) 개수가 원판과 같다 · 닫기(`<04>`) 개수가 원판과 같다(닫는 코드가 빠지면 뒤 대사까지 색이 번진다)
② 색 열기→닫기 순서(열기·닫기 나열)가 원판과 같다
③ 색 범위가 비지 않았다(열고 곧장 닫음) · 원판에 없던 쪽 넘김(`<05>`)을 색 범위가 가로지르지 않는다
④ 색 범위가 낱말 가운데서 열리지 않는다(열기 바로 앞이 한글·영숫자)

  python3 check_color.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build
import common
import segs

OPEN = re.compile(r"<1[89a-d]>")
TOK = re.compile(r"<(?:1[89a-d]|04)>")
SPAN = re.compile(r"(<1[89a-d]>)(.*?)(?=<04>|$)", re.DOTALL)


def check(jp: str, kr: str) -> list[str]:
    """원판 표기·한글 표기 한 쌍 → 위반 설명 목록(테스트가 양성 대조로 부른다)."""
    bad = []
    tj, tk = TOK.findall(jp), TOK.findall(kr)
    if len(OPEN.findall(jp)) != len(OPEN.findall(kr)):
        bad.append("① 색 열기 개수")
    if tj.count("<04>") != tk.count("<04>"):
        bad.append("① 닫기 개수(번짐)")
    if [t == "<04>" for t in tj] != [t == "<04>" for t in tk]:
        bad.append("② 열기·닫기 순서")
    sj = [m.group(2) for m in SPAN.finditer(jp)]
    for i, m in enumerate(SPAN.finditer(kr)):
        body = m.group(2)
        if not re.sub(r"<[^>]*>|\s", "", body):
            bad.append("③ 빈 색 범위")
        if "<05>" in body and not (i < len(sj) and "<05>" in sj[i]):
            bad.append("③ 색 범위가 쪽 넘김을 가로지름")
        p = kr[m.start() - 1] if m.start() else ""
        jm = list(SPAN.finditer(jp))
        jpp = jp[jm[i].start() - 1] if i < len(jm) and jm[i].start() else ""
        if (
            p and ("가" <= p <= "힣" or p.isalnum()) and not jpp.isalnum()
        ):  # 원판도 글자 코드(`Q<1b>Q`) 뒤에서 열면 같은 꼴
            bad.append("④ 낱말 가운데서 열림")
    return bad


def main() -> None:
    src = common.rom_bytes()
    sm, _, _ = build.collect_texts(src)
    sg = {segs.seg_id(a): (a, b) for a, b in segs.segments(src)}
    n, bad = 0, []
    for k, v in sorted(sm.items()):
        jp = segs.notation(src, *sg[k])
        if not OPEN.search(jp) and not OPEN.search(v["kr"]):
            continue
        n += 1
        bad += [f"{k} {x}" for x in check(jp, v["kr"])]
    for b in bad[:20]:
        print("  " + b)
    print(f"색 코드 점검 — 색이 든 구간 {n} · 위반 {len(bad)}")
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
