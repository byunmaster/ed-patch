"""호출 끝 개행 대조 — 원판 조각의 `<RETURN>` 앞 개행이 우리 조각의 `<FE>` 앞에도 있나.

    .venv/bin/python games/sfc-ed1/tools/check_call_newline.py

🔴 이유(마스터 10-30 띄어쓰기 개행 점검): 사전 문장 토큰(`{D5:xx}`)은 끝 개행이 없어, 호출이 돌아온 뒤 이어지는 글이
**같은 줄에 붙어** 나갔다(205번 전/후 촬영 확정 — 95자리). 원판은 `\\n<RETURN>` 으로 줄을 바꾼다. 이 검사는 조각마다
`<RETURN>`(원판)·`<FE>`(우리) 조각을 같은 차례끼리 맞춰 「앞이 개행으로 끝나나」를 대조한다. 조각 수가 다르거나 한쪽만
개행이면 실패(예외 없음 — 원판이 복귀 뒤 개행으로 시작하는 조각은 조판 게이트가 `typeset.return_newlines` 로 쪽 첫머리 개행에서 뺀다).
"""

import json
import sys

import common
import typeset


def compare(jp: str, kr: str) -> list[tuple[int, str]]:
    """(차례, 사유) 목록 — 조각 수 어긋남은 차례 -1."""
    J, K = jp.split("<RETURN>"), kr.split("<FE>")
    if len(J) != len(K):
        return [(-1, f"원판 {len(J)} 조각 ↔ 우리 {len(K)} 조각")]
    return [
        (i, "원판은 개행 끝, 우리는 아님" if J[i].endswith("\n") else "우리만 개행 끝")
        for i in range(len(J) - 1)
        if J[i].endswith("\n") != K[i].endswith("\n")
    ]


def main() -> int:
    segs = json.loads((common.GAME_DIR / "textmap" / "segments.json").read_text(encoding="utf-8"))
    n = 0
    bad = []
    for u in typeset._units():
        v = segs.get(u["id"])
        if v is None or "<RETURN>" not in u["jp"]:
            continue
        n += 1
        for i, why in compare(u["jp"], v["kr"]):
            bad.append(f"{u['id']} 호출 {i}: {why}")
    print(f"  호출 끝 개행 대조 — 호출 조각 {n} · 위반 {len(bad)}")
    for m in bad[:20]:
        print(f"    ✗ {m}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
