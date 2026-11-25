"""런타임 변수(이름·아이템·주문·숫자)가 든 줄 — 가장 긴 값으로 접어 낱말 갈림·한 음절 꼬리를 찾는다(정적).

    python3 tools/check_var_wrap.py        # 위반 목록(없으면 ✅)

빌드는 변수 토큰을 **폭 0** 으로 두고 조각마다 짠다. 런타임엔 이름·아이템이 끼어 줄이 넘치고, 엔진이 접는다(어절 단위
`wordwrap.py`, 어절이 줄보다 길면 글자 단위). 그래서 굽힌 토큰의 줄마다 변수 자리에 **가장 긴 값**을 넣고 `check_layout.wrap_ex`
(엔진과 같은 모형)로 접어 ① 낱말 한가운데서 접힘(공백 없는 어절이 줄을 넘어 글자 단위로 잘림) ② 접힌 꼬리가 한 음절(+부호)
③ 접혀서 쪽이 창 줄 수를 넘음을 센다. 문안은 건드리지 않는다(2-19) — 걸리면 배치·어절 경계로 푼다.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_layout as cl
import check_typeset_axes as ax
import dict_names

LINES = 3  # 대사창 줄 수
PUNCT_TAIL = set(".,!?…」)~～ ")


def fold_issues(text: str, limit: int):
    """text 한 줄 → (접힌 줄들, 낱말갈림 여부, 꼬리 한 음절 여부)."""
    out = cl.wrap_ex(text, limit)
    if len(out) == 1:
        return out, False, False
    split_mid = False
    for a, b in zip(out, out[1:]):
        # 공백으로 접힌 건 wrap_ex 가 공백을 버려 a 끝·b 머리가 이어진다 — 원문 공백 위치로 가른다
        pass
    joined = "".join(out)
    # 원문에서 접힌 지점이 공백 자리인가: 원문 글자열에서 각 줄 길이 누적 위치 앞뒤 확인
    pos = 0
    src = text
    for ln in out[:-1]:
        pos += len(ln)
        if pos < len(src) and src[pos] == " ":
            pos += 1  # 버려진 공백
        elif pos < len(src):
            split_mid = True
    tail = out[-1].strip()
    one = len([c for c in tail if c not in PUNCT_TAIL]) <= 1
    return out, split_mid, one


PARTY = [re.sub(r"<[0-9a-f]+>", "", o["ours"]).strip() for k, o in sorted(dict_names.names()["party_name"].items())]


def split_raw(tokens):
    """ax.split_pages 와 같되 코드 항목에 원본 바이트를 남긴다(`<09nn>` 의 nn = 파티 번호)."""
    pages = [[[]]]
    for t in tokens:
        if t.kind == "text":
            pages[-1][-1].append(("t", ax.dec(t.raw)))
        elif t.kind == "ctl" and t.raw[:1] == b"\x01":
            pages[-1].append([])
        elif t.kind == "ctl" and t.raw[:1] == b"\x05":
            pages.append([[]])
        else:
            pages[-1][-1].append(("c", t.raw[:1].hex(), t.raw))
    return pages


def main() -> int:
    f = cl.fillers()
    name, item = f["name"], f["item"]
    bad: list[str] = []
    n_var = 0
    for kind, where, toks, ours, _cap, _tail in ax.bake():
        if kind != "씬":
            continue
        for i, t_ in enumerate(toks[:-1]):  # ⑤ 변수 앞 띄어쓰기 소실 — 정본엔 공백이 있는데 굽힌 글이 공백 없이 변수에 붙는다
            nx = toks[i + 1]
            if t_.kind == "text" and nx.kind == "ctl" and nx.raw[:1] in (b"\x09", b"\x02", b"\x0e"):
                s_ = ax.dec(t_.raw)
                if not s_.endswith(" ") and re.search(re.escape(s_[-3:]) + r" <(09|02|0e)", ours):
                    bad.append(f"scene {where}: ⑤ 변수 앞 공백 소실 — …{s_[-8:]!r}")
        pages = split_raw(toks)
        for pi, pg in enumerate(pages):
            shown = base = 0
            for li, ln in enumerate(pg):
                if ln and all(x[0] == "c" for x in ln) and ln[0][1] in ("09", "13", "14"):  # `<0900>` 화자 접두 줄 — 이름줄이다
                    continue
                if ln and ln[0][:2] == ("c", "1e"):  # 화자 이름줄(`<1e>이름<04>`)은 대사 줄 수에 안 든다
                    continue
                # 03(키 대기)·04(이름줄 끝) 바로 뒤 `09nn` 은 **다음 화자 접두**다 — 문장 속 이름이 아니다
                ln = [x for k, x in enumerate(ln) if not (x[:2] == ("c", "09") and k and ln[k - 1][:2] in (("c", "03"), ("c", "04")))] if ln else ln
                menu = sum(1 for x in ln if x[:2] == ("c", "09")) >= 2  # `<090f><092a>…` = 메뉴 자리(파티 목록), 문장 속 이름이 아니다
                if menu or not any(x[0] == "c" and x[1] in ("02", "0e", "0b", "09") for x in ln):
                    shown += 1 if ax.line_text(ln).strip() else 0
                    base += 1 if ax.line_text(ln).strip() else 0
                    continue
                n_var += 1
                s = ""
                for x in ln:
                    if x[0] == "t":
                        s += x[1]
                    elif x[1] == "09" and len(x[2]) > 1 and x[2][1] < len(PARTY):
                        s += PARTY[x[2][1]]  # `<09nn>` 은 nn 번째 파티원 이름 그대로
                    elif x[1] in ("02", "0b", "09"):
                        s += name
                    elif x[1] == "0e":
                        s += item
                    elif x[1] in ("eb", "ec"):
                        s += "을"
                out, mid, one = fold_issues(s, cl.DIALOG_LIMIT)
                shown += len(out)
                base += 1
                tag = f"scene {where} 쪽{pi + 1} 줄{li + 1}"
                if mid:
                    bad.append(f"{tag}: ① 낱말 한가운데 접힘 — {out}")
                elif one:
                    bad.append(f"{tag}: ② 한 음절 꼬리 — {out}")
            if shown > LINES >= base:  # 접히기 전엔 창에 들었는데 접혀서 넘친 것만(애초에 여러 번 기다리는 쪽은 제외)
                bad.append(f"scene {where} 쪽{pi + 1}: ③ 접혀서 {shown}줄(창 {LINES}줄)")
    # 시스템·전투 — 조립 결과를 같은 잣대로
    for label, text in cl.battle_texts():
        for ln in text.split("\n"):
            out, mid, one = fold_issues(ln, cl.BATTLE_LIMIT)
            if mid:
                bad.append(f"{label}: ① 낱말 한가운데 접힘 — {out}")
            elif one:
                bad.append(f"{label}: ② 한 음절 꼬리 — {out}")
    import json

    sm = json.loads((cl.T / "sysmsg.json").read_text(encoding="utf-8"))
    cases = []
    for label, parts in cl.CHAINS:  # 조립형 시스템 메시지(상자·도구·주문·회복…) — 가장 긴 값으로
        cases.append((label, cl.expand("".join(f[p[1:-1]] if p.startswith("{") else sm[p]["ours"] for p in parts), f)))
    for k, o in sm.items():
        s_ = o.get("ours") or ""
        if s_ and not (cl.BATTLE_CODE[0] <= int(k, 16) < cl.BATTLE_CODE[1]):
            cases.append((f"sysmsg {k}", cl.expand(s_ + ("{num}" if s_.endswith("<06>") else ""), f).replace("{num}", f["num"])))
    for label, text in cases:
        for ln in text.split("\n"):
            out, mid, one = fold_issues(ln, cl.LIMIT)
            if mid:
                bad.append(f"{label}: ① 낱말 한가운데 접힘 — {out}")
            elif one:
                bad.append(f"{label}: ② 한 음절 꼬리 — {out}")
    for b in dict.fromkeys(bad):
        print("  ❌", b)
    print(f"  변수 줄 조판 검사 — 변수 든 줄 {n_var} · 위반 {len(set(bad))}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
