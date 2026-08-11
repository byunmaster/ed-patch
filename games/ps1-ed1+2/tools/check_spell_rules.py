#!/usr/bin/env python3
"""`dos_spelling_fixes.json` 의 치환 중 **한 번도 안 걸리는 규칙**을 센다.

치환은 목록 **순서대로** 걸린다. 그래서 규칙 하나가 죽는 길이 여럿 있고 **전부 조용하다**:

1. **상류가 이미 고쳤다** — `fix_spacing` 이 `할때`→`할 때` 를 먼저 처리하면
   `처단할때까지는` 규칙은 영영 사냥감을 못 만난다(무해하지만 목록만 부푼다).
2. **겨냥한 표기가 그 시점엔 없다** — 검사기는 교정된 문안(`라누라왕국은`)을 보고 규칙을
   만드는데 `spell_fix` 가 보는 건 아직 `라느라왕국은` 이었다. 실측 5건이 그렇게 죽어 있었다
   (2026-08-10). 지명 정본 교정을 `spell_fix` 앞으로 옮겨 고쳤다.
3. **`subs`/`pre_subs` 가 그 자리를 먼저 잘라냈다** — 블록이 정발 문장의 앞뒤를 떼고 쓰면
   앵커가 통째로 사라진다(jp85 `사냥꾼인가 이곳의` 실측 2026-08-11).
4. **그 엔트리를 아무 블록도 안 쓴다** — 코퍼스엔 있지만 화면엔 안 나온다.

⚠ **옛 판은 코퍼스만 통과시켜서 3·4 를 못 봤다** — 사문 271건이라 보고했는데 실제로는
**1,396건**이었다(2026-08-11 실측, 5배 과소보고). 그래서 지금은 **`spell_fix` 를 계측해
실제 배정 경로(`load_translations` 전 씬)를 돌린다** — 이게 화면에 나가는 진짜 발화 횟수다.
mcpads 패처들의 "fail-closed coverage audit" 과 같은 계열이다.

  python3 tools/check_spell_rules.py          # 요약
  python3 tools/check_spell_rules.py -v       # 안 걸린 규칙 전부
  python3 tools/check_spell_rules.py --new    # HEAD 이후 **새로 넣은** 규칙만 (반영 검산)
"""

import collections
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R  # noqa: E402
from common import ROOT  # noqa: E402
from patch_sys_ui import _scn_layout  # noqa: E402

SPELL_JSON = os.path.join(ROOT, "dos_spelling_fixes.json")


def fired():
    """{(a, b): 발화 횟수} — **실제 배정 경로**에서 치환이 몇 번 걸렸는지.

    `spell_fix` 를 계측판으로 바꿔 끼우고 전 씬을 로드한다. 재현하지 않고 **본물을 세는**
    이유는 3·4 부류(위 도크스트링) 때문이다 — 그건 재현으로는 영영 안 보인다.
    """
    hits = collections.Counter()
    orig = R.spell_fix

    def traced(t):
        rx, space, replace = R._spell_rules()
        if rx:
            t = rx.sub(r"\1 \2", t)
        for a, b in space:
            t = t.replace(a + b, a + " " + b)
        for a, b in replace:
            if a in t:
                hits[(a, b)] += t.count(a)
            t = t.replace(a, b)
        return t

    R.spell_fix = traced
    try:
        for name, _lba, _size in _scn_layout():
            R.load_translations(name.replace("SCN", "_SCN"), name)
    finally:
        R.spell_fix = orig
    return hits


def added_since(ref="d7922af"):
    """[(a, b)] — 기준 커밋 이후 새로 들어온 치환쌍(없으면 빈 목록)."""
    p = subprocess.run(
        ["git", "show", f"{ref}:games/ps1-ed1+2/dos_spelling_fixes.json"],
        capture_output=True,
        text=True,
        check=False,
        cwd=os.path.dirname(ROOT),
    )
    if p.returncode:
        return []
    old = {(a, b) for a, b in json.loads(p.stdout)["replace"]}
    now = json.load(open(SPELL_JSON, encoding="utf-8"))["replace"]
    return [(a, b) for a, b in now if (a, b) not in old]


def main(argv):
    verbose, only_new = "-v" in argv, "--new" in argv
    rep = [tuple(r) for r in json.load(open(SPELL_JSON, encoding="utf-8"))["replace"]]
    hits = fired()
    target = added_since() if only_new else rep
    if only_new and not target:
        print("기준 커밋을 못 찾았다 — 전체로 돈다")
        target = rep
    dead = [(a, b) for a, b in target if (a, b) not in hits]
    kind = "새로 넣은 규칙" if only_new else "replace 규칙"
    print(f"{kind} {len(target)} · 실제로 걸림 {len(target) - len(dead)} · **안 걸림 {len(dead)}**")
    for a, b in dead[: (None if verbose else 12)]:
        print(f"  ❌ {a!r} → {b!r}")
    if not verbose and len(dead) > 12:
        print(f"  … 그 밖 {len(dead) - 12}건 (-v 로 전부)")
    if only_new and dead:
        print("\n⚠ **손으로 넣은 규칙이 여기 뜨면 반영이 안 된 것이다** — 앵커가 `subs`/`pre_subs`")
        print(
            "  뒤라 못 닿거나, 앞선 규칙이 이미 그 표기를 바꿨을 수 있다. 그 블록의 렌더를 찍어 볼 것."
        )
        print("  (A급 일괄 채택분은 안 쓰는 엔트리를 겨냥하는 게 정상이라 여기 섞인다)")
    # ⚠ **실패시키지 않는다.** 사문 대부분은 안 쓰는 엔트리를 겨냥한 것이라 무해하고,
    # 게이트로 만들면 A급 일괄 채택 때마다 빌드가 막힌다 — 판단은 사람이 한다.
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
