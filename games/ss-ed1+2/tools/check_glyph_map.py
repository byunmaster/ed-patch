#!/usr/bin/env python3
"""글리프 배정 정본이 **덧붙이기만** 했나 — 세이브 호환의 뿌리다.

    python3 tools/check_glyph_map.py

## 왜 게이트인가

🔴 **세이브가 우리 글리프 코드를 그대로 담는다.** 새턴 백업 RAM 세이브를 열어 보면 파티원
이름이 우리 한글 슬롯 코드로 적혀 있다(실측 2026-09-06, 유저 세이브 32KB 안 **16곳** —
세리오스·류난·로우·게일·아트라스·란도·플로라·신디). 그래서 **한 글자라도 슬롯이 바뀌면
옛 세이브의 이름이 엉뚱한 글자로 뜬다.**

pce-ed1 이 실제로 물렸다(2026-09-06 중계) — 거기선 배정이 「문안이 쓰는 글자 정렬」이라
문안이 한 글자 늘 때마다 전부 밀렸다. 우리는 **글자→슬롯을 명시로 들고** 있어 그보다
안전했지만 구멍이 둘 있었다:

    patch_ui.slot_plan     안 쓰이게 된 글자를 **잘라내** 슬롯을 풀에 돌려줬다
    patch_title.slot_plan  `--refresh` 때 `enumerate(need)` 로 **통째 재배정**했다

둘 다 덧붙이기만 하게 고쳤고, 이 검사기가 그 규칙을 지킨다.

## 무엇을 보나

1. **슬롯 중복 0** — 두 글자가 같은 슬롯이면 하나는 화면에서 사라진다.
2. **HEAD 대비 덧붙이기만** — 커밋된 정본에서 글자가 **사라지거나 슬롯이 바뀌면** 실패.
   ⚠ 워킹트리를 HEAD 와 견주므로, **고치려면 이유를 커밋 메시지에 적고 넘어가는 수밖에**
   없다. 그게 맞다 — 배정을 바꾸는 건 옛 세이브를 버리는 결정이라 사람이 해야 한다.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(GAME))
MAPS = ("hangul_map_11kanji.json", "hangul_map.json")


def _syl(text):
    d = json.loads(text)
    return d.get("syllables", d)


def head_version(rel):
    """HEAD 의 그 파일 — 없으면 None(새로 생긴 정본이다)."""
    r = subprocess.run(
        ["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return _syl(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def check(name):
    """`(사라진 글자, 슬롯이 바뀐 글자, 슬롯 중복)`."""
    path = os.path.join(GAME, name)
    if not os.path.exists(path):
        return [], [], []
    with open(path, encoding="utf-8") as f:
        now = _syl(f.read())
    vals = list(now.values())
    dup = sorted({v for v in vals if vals.count(v) > 1})
    rel = os.path.relpath(path, ROOT)
    was = head_version(rel)
    if was is None:
        return [], [], dup
    gone = sorted(c for c in was if c not in now)
    moved = sorted(f"{c} {was[c]}→{now[c]}" for c in was if c in now and was[c] != now[c])
    return gone, moved, dup


def main():
    bad = 0
    for name in MAPS:
        gone, moved, dup = check(name)
        n = len(gone) + len(moved) + len(dup)
        bad += n
        if not n:
            path = os.path.join(GAME, name)
            cnt = 0
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    cnt = len(_syl(f.read()))
            print(f"     ✅ {name} — {cnt}자 · 덧붙이기만 · 슬롯 중복 0")
            continue
        print(f"     ❌ {name}")
        if gone:
            print(f"        사라진 글자 {len(gone)} — {''.join(gone[:20])}")
        if moved:
            print(f"        슬롯이 바뀐 글자 {len(moved)} — {' · '.join(moved[:8])}")
        if dup:
            print(f"        슬롯 중복 {len(dup)} — {dup[:8]}")
    if bad:
        raise SystemExit(
            "글리프 배정이 흔들렸다 — **옛 세이브의 이름이 깨진다.**\n"
            "     되돌리거나, 정말 바꿀 것이면 커밋 메시지에 사유를 적는다."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
