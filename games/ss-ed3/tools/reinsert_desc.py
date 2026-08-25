"""`PARAM.BIN` 의 설명문 두 영역을 우리 문안으로 다시 채운다.

🔴 **조각마다 시작 오프셋을 지켜야 한다.** 엔진은 NUL 을 세어 찾는 게 아니라 **오프셋으로
바로 간다** — 앞 조각이 짧아지면 뒤가 통째로 어긋난다. 실측으로 데였다(2026-08-25):
영역 총량만 맞추고 재삽입했더니 약초 설명 자리에 **`Sentinel` 의 꼬리(`el`)** 가 떴다.
우리 문안이 원문보다 124B 짧아 뒤쪽 조각이 그만큼 앞당겨졌기 때문이다.

⚠ RAM 실험이 이걸 못 잡았던 이유: 그때는 **한 조각만** 고치고 **시작 오프셋을 그대로 뒀다**.
   조각을 늘려 뒤를 먹어도 그 조각은 멀쩡했다 — 「길이가 자유롭다」로 잘못 읽은 근거다.
   **하나를 바꿔 되는 것이 전부를 바꿔도 된다는 뜻은 아니다.**

그래서 규칙은 **조각별 길이 보존**이다 — `번역 + NUL + 0 패딩`으로 **원문 조각과 같은 칸**을
차지한다. 번역이 원문 바이트를 넘으면 **그 조각은 못 넣는다**(줄이거나 포기).
⚠ **끝의 ASCII 더미(`quux`·`Sentinel`)는 건드리지 않는다** — 표의 끝 표식이다.

조판은 `typeset.wrap_desc`(9 자 × 4 행)가 정본이고, 화면 개행은 `＄`(전각 문자)다.
🔴 엔진은 16 자에서 접지만 창은 10 자쯤만 보여 준다 — 그 사이는 **그려지고도 안 보인다**.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import common as C
import hangul_map as H
import param as P
import typeset as T

AREAS = (("desc_item", P.DESC_ITEM), ("desc_spell", P.DESC_SPELL))


def table():
    """`{영역이름: {색인: 우리 문안}}`. 없으면 빈 dict."""
    out = {}
    for name, _ in AREAS:
        p = os.path.join(C.ROOT, "games", "ss-ed3", "script", f"{name}.json")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        out[name] = {k: v for k, v in d.items() if k != "_doc"}
    return out


def _area(b, area, kr, tbl):
    """한 영역을 다시 채운다 → `(bytes, 바꾼 수, 문제, 예산초과)`. 길이는 원래 그대로.

    🔴 **빈 조각(연속 NUL)까지 그대로 옮긴다.** `param.descs` 는 빈 것을 버리는데(읽기용
    이라 그게 맞다) 그 목록으로 재구성하면 **버린 NUL 만큼 뒤가 앞당겨진다** — 실측
    2026-08-25: 15B 가 사라져 약초 설명 자리에 「복하는 약」(우리 문안의 뒷부분)이 떴다.
    ⚠ **읽기용 파서를 쓰기에 그대로 쓰지 않는다.**
    """
    size = area[1] - area[0]
    parts = b[area[0] : area[1]].split(b"\x00")
    tail = parts[-1]  # 마지막 NUL 뒤의 여백
    out = bytearray()
    bad, over = [], []
    n = idx = 0
    for raw in parts[:-1]:  # 각 조각 뒤에 NUL 이 하나씩 있었다
        if not raw:  # 빈 조각 — NUL 만 되돌려 놓는다
            out += b"\x00"
            continue
        try:
            txt = raw.decode("shift_jis")
        except UnicodeDecodeError:
            out += raw + b"\x00"
            continue
        if txt.isascii():  # 표 끝 더미 — 그대로
            out += raw + b"\x00"
            continue
        s = kr.get(str(idx))
        idx += 1
        if s is None:
            out += raw + b"\x00"
            continue
        rows = T.wrap_desc(s)
        if len(rows) > T.DESC_ROWS:
            bad.append(f"{idx - 1}: {len(rows)}행 > {T.DESC_ROWS} — {s}")
        enc = H.encode_kr(T.DESC_NL.join(rows), tbl)
        if len(enc) > len(raw):
            # ⚠ **실패가 아니라 「할 일」이다** — 원문을 그대로 두고 넘어간다.
            over.append((idx - 1, len(enc), len(raw), s))
            out += raw + b"\x00"
        else:
            # 🔴 남는 자리는 **반각 공백**으로 메운다 — NUL 로 채우면 그것도 구분자로
            #    세어져 뒤가 밀린다. 화면 끝이라 공백은 보이지 않는다.
            out += enc.ljust(len(raw), b" ") + b"\x00"
            n += 1
    out += tail
    assert len(out) == size, (len(out), size)
    return bytes(out), n, bad, over


def patch(b, tbl, kr_tables=None, want_over=False):
    """`PARAM.BIN` 전체 → 같은 크기의 새 바이트. `(new, 바꾼 수, 문제[, 예산초과])`.

    ⚠ **예산 초과는 `문제`가 아니다** — 그 조각만 원문으로 두고 넘어간다. 빌드를 세우면
    나머지 문안까지 화면에서 못 보게 된다. 초과 목록은 `desc_budget.py` 가 따로 센다.
    """
    kr_tables = table() if kr_tables is None else kr_tables
    if not kr_tables:
        return (b, 0, [], []) if want_over else (b, 0, [])
    new = bytearray(b)
    total = 0
    bad = []
    over = []
    for name, area in AREAS:
        kr = kr_tables.get(name)
        if not kr:
            continue
        seg, n, e, o = _area(b, area, kr, tbl)
        bad += e
        over += [(name, *x) for x in o]
        if seg is None:
            continue
        new[area[0] : area[1]] = seg
        total += n
    return (bytes(new), total, bad, over) if want_over else (bytes(new), total, bad)


def main():
    b = P.load()
    tbl = H.load()
    new, n, bad, over = patch(b, tbl, want_over=True)
    print(f"설명문 {n} 건 재삽입 · 크기 {len(new):,}B (원본 {len(b):,}B)")
    for name, area in AREAS:
        used = len(bytes(new[area[0] : area[1]]).rstrip(b"\x00"))
        print(f"  {name:<11}{used:>5,} / {area[1] - area[0]:>5,}B  여유 {area[1] - area[0] - used:>4,}B")
    for e in bad:
        print(f"  ❌ {e}")
    if over:
        print(f"\n  ⚠ 예산 초과 {len(over)} 건 — 그 조각은 **원문을 그대로 뒀다**. 문안을 줄여야 한다:")
        for name, idx, got, bud, s in over[:12]:
            print(f"     {name} {idx:>4}  {got:>3}B > {bud:>3}B   {s}")
        if len(over) > 12:
            print(f"     … 외 {len(over) - 12}")
    assert len(new) == len(b)
    print("\n✅ 길이 보존" if not bad else "\n⚠ 위 문제를 보라")


if __name__ == "__main__":
    main()
