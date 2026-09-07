#!/usr/bin/env python3
"""문안 표기 꼴 검사기 — **한 문안 안에서 갈리는 것**만 본다.

`rpg-translate` §4-② 「일본식 부호 → 한국식」과 같은 축인데, 판정 대신 **일관성**을 본다.
어느 꼴이 옳은지는 게임마다 갈려도, **한 게임 안에서 두 꼴이 섞이는 건 무조건 결함**이다.

실측(2026-09-06, PS1 사전에서 씨앗을 받은 뒤):

  · 같은 「2층」이 어떤 줄은 전각 `２층`, 어떤 줄은 반각 `2층` (4:1)
  · 곱은따옴표 `”…”` — 여는 꼴과 닫는 꼴이 같아 인용으로 못 쓴다
  · 일본식 마침표 `。`·쉼표 `、` 가 남아 있나

⚠ 마커(`\\n` `<PAGE>` `<WAIT>`)는 세지 않는다 — 그 계약은 `translate.py apply` 가 본다.

## 부호 앞 공백 — **조판을 안 거치는 자리**를 여기서 본다

`shared/text/krwrap.strip_before` 가 이미 같은 규칙을 들지만, 그건 **조판기를 타는 문안**만
본다. 이 게임의 전투·시스템·고정폭 표는 조판을 안 거치므로 **거기서만 새 나간다**
(md-ed1 실측 중계 2026-09-07). 원문 `･ ･ ･` 을 그대로 옮기면 `말이다 …` 가 남는다.

⚠ **공백이 뜻인 자리가 있다** — 끊어 말하는 연출(`못 … 한 … 다 ….`)·줄 첫머리 들여쓰기.
   그 자리는 정본에 `"space_ok": true` 를 적어 뺀다(판정을 코드가 아니라 정본에 남긴다).
🔴 **전투 칸을 공백으로 메우는 데 쓰지 않는다.** 바이트가 모자라면 낱말로 채운다 —
   실측 `d9053e1e` 가 그 자리였다(`치켜들었다 !!` → `크게 휘둘렀다!!`, 둘 다 32B).
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import translate

MARK = re.compile(r"\\n|<PAGE>|<WAIT>")
AXES = {
    "전각 숫자": re.compile(r"[０-９]"),
    "곱은따옴표": re.compile(r"[“”„‟]"),
    "일본식 마침표·쉼표": re.compile(r"[。、]"),
    "일본식 물결·중점": re.compile(r"[～・]"),
}
# 마커를 지우기 **전**의 원문으로 본다 — `\n` 뒤의 `…` 를 오탐하지 않기 위해서다
FLOW = re.compile(r"<PAGE>|<WAIT>")
SPACE_BEFORE = re.compile(r"[가-힣A-Za-z0-9\]\)] +[!?.,…]")


def flow_marker_audit(script: dict) -> list:
    """🔴 **흐름 마커(`<PAGE>`·`<WAIT>`) 수는 원문과 같아야 한다.**

    개행(`\\n`)은 조판이라 우리가 정한다. 그런데 `<PAGE>`(0x05)·`<WAIT>`(0x03)는
    **진행**이다 — 빠뜨리면 게임이 멈추거나 같은 대사를 되풀이한다.
    실측(2026-09-08): 정본 2,483줄 중 마커가 원문과 다른 것이 578인데 **577은 개행뿐**이고,
    흐름 마커가 다른 것은 **딱 하나**였다. 그 하나가 유저가 물린 **아크담 무한루프**다.
    ⇒ 개행은 세지 않고 **흐름 마커만** 게이트로 잡는다(그래야 늘 빨간불이 안 된다).
    """
    import collections

    bad = []
    for k, b in translate.keyed(translate.blocks()):
        v = script.get(k)
        if not v or "t" not in v:
            continue
        a = collections.Counter(FLOW.findall(b["t"]))
        c = collections.Counter(FLOW.findall(v["t"]))
        if a != c:
            bad.append((k, dict(a), dict(c), v["t"][:40]))
    return bad


def main() -> int:
    script = json.loads(translate.SCRIPT.read_text(encoding="utf-8"))
    bad = {}
    for k, v in script.items():
        if not v.get("space_ok") and SPACE_BEFORE.search(v["t"]):
            m = SPACE_BEFORE.search(v["t"])
            bad.setdefault("부호 앞 공백", []).append((k, m.group(0), v["t"]))
        t = MARK.sub(" ", v["t"])
        for name, rx in AXES.items():
            hit = rx.findall(t)
            if hit:
                bad.setdefault(name, []).append((k, "".join(sorted(set(hit))), t))
    half = sum(1 for v in script.values() if re.search(r"[0-9]", MARK.sub(" ", v["t"])))
    print(f"문안 {len(script):,}줄 · 반각 숫자를 쓴 줄 {half:,}")
    flow = flow_marker_audit(script)
    if not bad and not flow:
        print("  ✅ 섞인 꼴 없음 · 흐름 마커도 원문과 같다")
        return 0
    for k, a, c, t in flow[:8]:
        print(f"  🔴 흐름 마커가 원문과 다르다 [{k[:8]}] 원문 {a} → 우리 {c}")
        print(f"     {t!r}")
    if flow:
        print(
            "     ⚠ `<PAGE>`·`<WAIT>` 는 조판이 아니라 **진행**이다 — 빠뜨리면 대사가 멈추거나 되풀이한다"
        )
    if not bad:
        return 1
    for name, rows in bad.items():
        print(f"  🔴 {name} {len(rows)}줄 — {''.join(sorted({r[1] for r in rows}))}")
        for k, _h, t in rows[:4]:
            print(f"     [{k[:8]}] {t[:52]}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
