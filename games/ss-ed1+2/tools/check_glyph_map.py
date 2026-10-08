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
2. **원본이 쓰는 슬롯을 차지하지 않았나** — 차지하면 그 글자는 **원본 문안이 안 옮겨진
   자리에서 우리 한글로 깨져 보인다.** 「일본어가 남았나」로는 안 잡힌다(한자가 아니라
   한글로 보이니까). pc98-ed1 이 그 꼴로 원판 세이브의 장 제목이 `L 1 ▨▨▨` 가 됐다.
   ⚠ 실측 2026-09-06: 우리 정본에 **하나 있었다** — `쩔` 이 `族`(슬롯 3119)를 차지했다.
   지금 배정기(`font.free_slots`)는 그 슬롯을 안 주는데, **낡은 배정이 덧붙이기 규칙으로
   계속 살아남고 있었다.**
3. **HEAD 대비 덧붙이기만** — 커밋된 정본에서 글자가 **사라지거나 슬롯이 바뀌면** 실패.
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
MAPS = ("hangul_map_11kanji.json", "hangul_map.json", "hangul_tiles.json")


def _syl(text):
    d = json.loads(text)
    return d.get("syllables", d)


def head_version(rel):
    """HEAD 의 그 파일 — 없으면 None(새로 생긴 정본이다)."""
    r = subprocess.run(
        ["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return _syl(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


FONTKEY = {"hangul_map_11kanji.json": "11kanji", "hangul_map.json": "kanji", "hangul_tiles.json": "kanji"}


def stolen(name, now):
    """원본 문안이 쓰는 슬롯을 차지한 글자들 — `[(글자, 슬롯)]`."""
    import font

    key = FONTKEY.get(name)
    if not key:
        return []
    try:
        used = font.used_indices(key)
    except SystemExit:
        return []  # 덤프가 아직 없다 — 그 폰트는 건너뛴다
    return sorted((c, i) for c, i in now.items() if i in used)


def check(name):
    """`(사라진 글자, 슬롯이 바뀐 글자, 슬롯 중복, 빼앗은 슬롯)`."""
    path = os.path.join(GAME, name)
    if not os.path.exists(path):
        return [], [], [], []
    with open(path, encoding="utf-8") as f:
        now = _syl(f.read())
    vals = list(now.values())
    dup = sorted({v for v in vals if vals.count(v) > 1})
    rel = os.path.relpath(path, ROOT)
    took = stolen(name, now)
    was = head_version(rel)
    if was is None:
        return [], [], dup, took
    gone = sorted(c for c in was if c not in now)
    moved = sorted(f"{c} {was[c]}→{now[c]}" for c in was if c in now and was[c] != now[c])
    return gone, moved, dup, took


def main():
    bad = 0
    for name in MAPS:
        gone, moved, dup, took = check(name)
        n = len(gone) + len(moved) + len(dup) + len(took)
        bad += n
        if not n:
            path = os.path.join(GAME, name)
            cnt = 0
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    cnt = len(_syl(f.read()))
            print(f"     ✅ {name} — {cnt}자 · 덧붙이기만 · 중복 0 · 원본 슬롯 침범 0")
            continue
        print(f"     ❌ {name}")
        if gone:
            print(f"        사라진 글자 {len(gone)} — {''.join(gone[:20])}")
        if moved:
            print(f"        슬롯이 바뀐 글자 {len(moved)} — {' · '.join(moved[:8])}")
        if dup:
            print(f"        슬롯 중복 {len(dup)} — {dup[:8]}")
        if took:
            print(
                f"        🔴 **원본이 쓰는 슬롯을 차지했다** {len(took)} — "
                + " · ".join(f"{c}→{i}" for c, i in took[:8])
            )
    # 🔴 자막 폰트(`KANJI.FON`)는 슬롯 정본이 **둘**이다(글자 `hangul_map.json` · 합성 조각 `hangul_tiles.json`) — 서로 슬롯을 겹치면
    #    한쪽이 화면에서 사라진다. 파일 안 중복은 위에서 봤고 **파일 사이**는 여기서 본다.
    ca, cb = (json.load(open(os.path.join(GAME, n), encoding="utf-8")) for n in ("hangul_map.json", "hangul_tiles.json"))
    both = sorted(set(_syl(json.dumps(ca)).values()) & set(_syl(json.dumps(cb)).values()))
    if both:
        bad += len(both)
        print(f"     ❌ 글자 정본과 조각 정본이 같은 슬롯을 가졌다 {len(both)} — {both[:8]}")
    if bad:
        raise SystemExit(
            "글리프 배정이 흔들렸다 — **옛 세이브의 이름이 깨지거나 원본 글자가 한글로 뜬다.**\n"
            "     되돌리거나, 정말 바꿀 것이면 커밋 메시지에 사유를 적는다."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
