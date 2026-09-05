#!/usr/bin/env python3
"""**PS1 과 문안이 갈렸나** — 두 판이 따로 쓴 자리를 전수 대조한다(보고 전용).

    python3 tools/check_ps1_parity.py          # 갈린 것만
    python3 tools/check_ps1_parity.py -v       # 못 찾은 원문까지

## 왜 필요한가

씬 대사는 **저본이 같아서 구조적으로 같다**(PS1 의 `line_dict.json` 하나를 읽는다). 갈릴 수
있는 건 양쪽이 **따로 쓴** 시스템·UI·이름 문안이다 — 거기엔 공유 창구가 없다.
실측 2026-08-29: 468쌍 중 **10이 갈려 있었고**, 그중 넷은 PS1 결함(조사를 한 형태로 박음 ·
`遠ぼえ` 오역)이고 다섯은 우리가 맞췄다(`よろしいですか？`).

🔴 **한쪽이 다 이기지 않는다.** 「어느 판이 정본인가」가 아니라 **「이 문장에서 무엇이
맞나」**로 묻는다 — 그래서 이건 **게이트가 아니라 보고**다. 사람이 자리마다 판정한다.

## ⚠ 소비자를 하나라도 빠뜨리면 「없다」가 나온다

우리 쪽 조회는 **다섯 곳**을 다 봐야 한다 — 정본(`glossary`) · **고정폭 UI 표**(`patch_ui.rows`) ·
`script/system.json` · `script/ui.json` · 씬 저본(`script/scn.json` + PS1 사전).
처음에 고정폭 표를 빼먹고 「새턴에 없다 5」를 냈는데 전부 있는 것이었다(상태 약어).
같은 실수를 `owned_elsewhere` 에서도 했다 — **읽는 자리를 세는 것이 이 층의 일이다.**

⚠ PS1 워크트리가 없으면 **건너뛴다**(그 트리를 안 받은 곳에서도 돌아야 한다).
"""

import argparse
import collections
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "shared"),
)

import common
import patch_scn as S
import patch_ui as U
import typeset_scn as T
from text.line_key import key as line_key

# ⚠ 우리는 **워크트리 안**에 있다 — 레포 뿌리는 거기서 셋 더 올라간다
#   (<레포>/.claude/worktrees/<게임>). `patch_scn` 의 저본 경로와 같은 셈법이다.
_WT = os.path.dirname(os.path.dirname(common.GAME_DIR))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_WT)))
PS1 = os.path.join(_REPO, ".claude", "worktrees", "ps1-ed1+2", "games", "ps1-ed1+2")
WS = re.compile(r"\s+")


# 🔴 **그쪽 트리에서 별도 프로세스로 뽑는다.** 같은 프로세스에서 임포트하면 `sys.path` 가
#    겹쳐 `common`·`dump_ui` 가 **우리 것**으로 잡힌다(실측: `textmap/battle.json` 을 우리
#    트리에서 찾다 죽었다). 남의 게임 코드를 우리 인터프리터에 들이지 않는다.
_DUMP = r"""
import glob, json, os, sys
sys.path.insert(0, os.path.join("games", "ps1-ed1+2", "tools"))
sys.path.insert(0, "shared")
os.environ.setdefault("LOCK_BYPASS", "1")
out = {}
def add(d):
    for k, v in d.items():
        if isinstance(k, str) and isinstance(v, str) and k and v and not k.startswith("__"):
            out.setdefault(k, v)
for mod in ("patch_items", "patch_sys_ui"):
    try:
        m = __import__(mod)
    except Exception:
        continue
    for n in dir(m):
        o = getattr(m, n)
        if isinstance(o, dict):
            add(o)
        elif isinstance(o, list) and o and isinstance(o[0], tuple) and len(o[0]) == 2:
            add(dict(x for x in o if all(isinstance(y, str) for y in x)))
for f in glob.glob(os.path.join("games", "ps1-ed1+2", "textmap", "*.json")):
    with open(f, encoding="utf-8") as fh:
        d = json.load(fh)
    if isinstance(d, dict):
        add(d)
print(json.dumps(out, ensure_ascii=False))
"""


def ps1_pairs():
    """PS1 이 **JP→KR 로 들고 있는** 낱말·문구 전부. 그 트리가 없으면 `None`."""
    if not os.path.isdir(PS1):
        return None
    wt = os.path.dirname(os.path.dirname(PS1))  # PS1 워크트리 뿌리
    r = subprocess.run(
        [sys.executable, "-c", _DUMP], cwd=wt, capture_output=True, text=True, check=False
    )
    if r.returncode or not r.stdout.strip():
        print(
            f"  ⏭ PS1 표를 못 뽑았다: {(r.stderr or '').strip().splitlines()[-1:] or '출력 없음'}"
        )
        return None
    return json.loads(r.stdout)


def ours():
    """`원문 → 우리 문안` 을 내는 조회 — ⚠ **소비자 다섯을 다 본다**(모듈 주석)."""
    names = T._names()
    tab = {jp: kr for _k, _n, _i, _a, _s, jp, kr in U.rows() if kr}
    canon = S.load_canon(quiet=True)
    files = {}
    for f in ("system", "ui", "scn"):
        p = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "script", f + ".json"
        )
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
            files[f] = d.get("lines", d)
            # 🔴 `ui.json` 의 **`msgs`** 는 `lines` 가 아니라 `[JP, KR]` 목록이다(2026-09-05).
            #    `sys_key` 로만 찾다가 **통째로 못 보고** 있었다 — 그래서 저장·로드 확인 문구
            #    넷을 `scn.json` 의 **그늘진 사본**으로 대조해 **거짓 갈림**을 냈다.
            for jp2, kr2 in d.get("msgs", []) or []:
                if jp2 and kr2:
                    files[f][U.sys_key(jp2)] = kr2

    def get(jp):
        if jp in names:
            return names[jp], "정본"
        if jp in tab:
            return tab[jp], "UI표"
        k = U.sys_key(jp)
        for f in ("system", "ui"):
            if k in files.get(f, {}):
                return files[f][k], f
        lk = line_key(jp)
        if lk in files.get("scn", {}):
            return files["scn"][lk], "scn"
        if lk in canon:
            return canon[lk], "저본"
        return None, None

    return get


def pending():
    """**PS1 에 맞출 것 — 아직 안 했다.** `script/ps1_pending.json`. 열쇠는 원문 sha1.

    🔴 **정본은 PS1 이다**(유저 확정 2026-09-05) — 이 자리들은 PS1 에서 결정한 표기이고
       **새턴이 따라가야 한다.** 「의도된 갈림」이 아니라 **미룬 할 일**이다.
    ⏳ 시점은 **PS1 이 main 에 머지된 뒤**다 — 그전엔 아직 움직이는 값을 좇게 된다.
    ⚠ 그때까지 「갈렸다」에서 갈라 세는 이유는 하나다 — 목록이 늘 같은 18로 차면
      **새로 갈린 자리가 묻힌다**(늘 빨간불이면 아무도 안 본다 — 루트 CLAUDE.md).
    """
    p = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "script", "ps1_pending.json"
    )
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f).get("pending", {})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    pairs = ps1_pairs()
    if pairs is None:
        print("  ⏭ PS1 워크트리가 없다 — 건너뜀")
        return 0
    get = ours()
    todo = pending()
    same, diff, later, miss = 0, [], [], []
    for jp, theirs in sorted(pairs.items()):
        mine, src = get(jp)
        if mine is None:
            miss.append((jp, theirs))
        elif WS.sub("", theirs) == WS.sub("", mine):
            same += 1
        elif U.sys_key(jp) in todo:
            later.append((jp, todo[U.sys_key(jp)]))
        else:
            diff.append((jp, theirs, mine, src))
    print(
        f"  PS1 표 {len(pairs):,} — 같다 {same:,} · 갈렸다 {len(diff)} · "
        f"PS1 에 맞출 것 {len(later)} · 새턴에 없다 {len(miss)}"
    )
    if later:
        print("  🔵 아래는 **PS1 이 main 에 머지된 뒤** 새턴을 맞춘다 (미룬 할 일)")
        why = collections.Counter(w for _j, w in later)
        for w, n in why.most_common():
            print(f"     ℹ {n:2}  {w}")
    for jp, theirs, mine, src in diff:
        print(f"     {jp[:26]!r}")
        print(f"        PS1  {theirs[:56]!r}")
        print(f"        새턴 {mine[:56]!r}  [{src}]")
    if a.verbose:
        for jp, theirs in miss:
            print(f"     ⏭ {jp[:36]!r} — PS1 {theirs[:36]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
