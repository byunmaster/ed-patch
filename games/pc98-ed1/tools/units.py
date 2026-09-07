#!/usr/bin/env python3
"""재삽입 단위 — **길이를 바꿔 다시 넣을 수 있는가**를 센다.

`walk_scn.py` 가 「닿나」를 쟀다면 여기는 **「고칠 수 있나」**다. 둘은 다른 질문이다.

## 왜 「포인터를 찾아 고친다」가 그대로는 안 되나

훑기가 83.5% 에 닿는다고 해서 **텍스트가 포인터 대상**인 건 아니다. 포인터는 **이벤트
루틴의 머리**를 가리키고, 텍스트는 그 안을 옵코드로 따라가다 만난다 — 실측: 텍스트 런의
**시작 주소를 값으로 든 워드**가 있는 단위는 5.0% 뿐이었다(2026-08-31).
⇒ 런 길이를 바꾸면 **루틴 내부가 통째로 밀리고**, 그러면 그 안의 절대주소를 전부 다시
계산해야 한다(선행 영문 패치가 `Block`/`Link`/`BlockPool` 로 푼 것이 이것이다).

## 그런데 더 싼 길이 있다 — `0x0F` 는 무조건 점프다

이벤트 옵코드 `0F <주소 2B>` 는 **절대주소 무조건 점프**고, 텍스트와 **같은 스트림**에서
해석된다(그래서 개행 `01`·페이지 `05` 가 문안 한복판에 섞여 있다). 그러면 루틴을 통째로
다시 짜지 않고 **런 하나만 밖으로 뺄 수 있다**:

    원래   … [텍스트 런 N바이트] …
    바꿈   … 0F <새자리> (3B) + 남은 N-3 바이트는 그대로 둔다 …
    새자리 [한글 문안 M바이트] 0F <런이 끝나던 주소>

루틴 길이가 안 변하므로 **다른 주소를 하나도 안 건드린다.**

성립 조건 셋을 여기서 센다:

    ① 런이 3바이트 이상          — 점프를 심을 자리
    ② 런 **안으로** 들어오는 점프가 없다 — 있으면 그 점프가 우리 코드 한복판에 떨어진다
    ③ 빈 자리가 새 문안을 받는다  — 시나리오 꼬리의 free 공간

⚠ 이 스크립트는 **고치지 않는다.** 쓰기 경로는 단위가 선 뒤에(patcher-checklist 2).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import dump_scn
import scn
import walk_scn as W

MIN_RUN = 3  # `0F <주소>` 를 심을 자리
JUMP = 0x0F


def incoming_targets(data: bytes, body: int, entries: set[int]) -> set[int]:
    """이벤트 스트림을 따라가며 **점프·호출의 목적지**를 전부 모은다.

    🔴 도달 못 한 루틴의 분기는 안 보인다 — 그래서 진입점을 **훑기까지 넓혀** 준다
    (과대추정이지만 여기서는 안전한 쪽이다: 목적지를 많이 잡을수록 조건 ② 가 엄해진다).
    """
    targets: set[int] = set(entries)
    todo = [a for a in entries if W._in_range(a, len(data))]
    started: set[int] = set()
    while todo:
        addr = todo.pop()
        if addr in started or not W._in_range(addr, len(data)):
            continue
        started.add(addr)
        while W._in_range(addr, len(data)):
            off = addr - W.BASE
            if off >= body:
                break
            b = data[off]
            if b >= 0x20:
                addr += 1
                continue
            n = W.CODE_LEN.get(b)
            if n is None:
                break
            if b in W.BRANCHES:
                t = int.from_bytes(data[off + 1 : off + 3], "little")
                if W._in_range(t, len(data)):
                    targets.add(t)
                    todo.append(t)
            addr += n
            if b in W.TERMINATORS:
                break
    return targets


def text_runs(data: bytes, body: int, code_seen: set[int]) -> list[dict]:
    """텍스트 런 — `dump_scn` 과 같은 자로 끊는다(x86 이 닿은 바이트는 뺀다)."""
    runs, i = [], 0
    while i < body:
        b = data[i]
        if b < 0x20:
            i += 1
            continue
        text, end, has_kana = dump_scn.decode_run(data, i)
        if end > i and has_kana and i not in code_seen:
            runs.append({"o": i, "n": end - i, "t": text})
        i = max(end, i + 1)
    return runs


def analyse(key, info) -> dict:
    """조건 ② 를 **두 자로** 잰다 — 어느 쪽을 믿을지가 전략을 가른다.

    엄격  x86 이 흐름을 따라가다 만난 진입점만 (실제로 닿은 것)
    훑기  범위 안 워드면 다 진입점으로 (과대 — 목적지를 많이 잡아 조건이 엄해진다)

    ⚠ 참값은 그 사이다. **훑기 쪽으로 짓는다** — 틀렸을 때 「못 고친다」로 끝나지
      「엉뚱한 자리를 덮어쓴다」가 아니기 때문이다.
    """
    data = info["data"]
    body = len(data) - info["tail_free"]
    code_seen, cands = W.walk_x86(data)
    strict = incoming_targets(data, body, set(cands))
    sweep = incoming_targets(data, body, W.pointer_sweep(data, body, cands))
    runs = text_runs(data, body, code_seen)
    out = {"key": scn.format_key(key), "free": info["tail_free"], "runs": []}
    for r in runs:
        a = W.BASE + r["o"]
        out["runs"].append(
            {
                **r,
                "short": r["n"] < MIN_RUN,
                "pierced": any(a < t < a + r["n"] for t in sweep),
                "pierced_strict": any(a < t < a + r["n"] for t in strict),
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", help="단위 대장(⚠ 원문 포함 — work/ 안에만)")
    args = ap.parse_args()
    common.check_originals()
    scenario, _ = scn.load()

    tot = ok = short = pierced = 0
    ok_s = pierced_s = 0
    tb = ok_b = 0
    free = 0
    per = []
    for key, info in scenario.items():
        a = analyse(key, info)
        per.append(a)
        free += a["free"]
        for r in a["runs"]:
            tot += 1
            tb += r["n"]
            if r["short"]:
                short += 1
            else:
                if r["pierced"]:
                    pierced += 1
                else:
                    ok += 1
                    ok_b += r["n"]
                if r["pierced_strict"]:
                    pierced_s += 1
                else:
                    ok_s += 1
    print(f"시나리오 {len(scenario)}건 · 텍스트 런 {tot:,} · 그 바이트 {tb:,}B")
    print(f"  ① 3바이트 미만        {short:6,} = {short / tot:6.1%}  제자리 한정")
    print(f"  ② 안으로 점프가 온다   {pierced:6,} = {pierced / tot:6.1%}  (훑기 · 과대)")
    print(
        f"                        {pierced_s:6,} = {pierced_s / tot:6.1%}  (엄격 · 실제로 닿은 것만)"
    )
    print(
        f"  ✅ 뺄 수 있다          {ok:6,} = {ok / tot:6.1%}  · 그 텍스트 {ok_b:,}B  ← 이걸 믿는다"
    )
    print(f"                        {ok_s:6,} = {ok_s / tot:6.1%}  (엄격 기준이면 여기까지)")
    print(f"  ③ 시나리오 꼬리 빈 자리 합계 {free:,}B")
    if args.json:
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(per, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  대장 → {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
