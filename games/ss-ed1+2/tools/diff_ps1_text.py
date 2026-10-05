#!/usr/bin/env python3
"""**새턴 문안 ↔ PS1 사전 차이** — 편(ED1/ED2)별로 블록 단위로 센다(보고 전용, 아무것도 안 쓴다).

    python3 tools/diff_ps1_text.py [--ref origin/game/ps1-ed1+2] [--ed 1|2] [--show N]

## 왜 있나 (2026-09-27)

「PS1 문안을 새턴에 그대로」는 대사 라운드에 PS1 이 main 에 머지되면 rebase 로 저절로 온다. 그 전에
**얼마나 달라지나**, 받은 뒤 **무엇이 남나**(새턴 전용 · 이름 칸 · ED1/ED2 공유 열쇠)를 값으로 보려고 둔다.
⚠ 한때 이 자리에 「ED1 스냅숏을 main 사전보다 먼저 읽는」 장치를 만들었다가 지시 취소로 걷었다
  (devlog 09-27) — 여기는 **계측만** 한다.

- 새턴 쪽 = `patch_scn.load_canon()`(지금 빌드가 읽는 저본, 조판 전).
- 대사 지명 띄어쓰기만 다른 줄은 따로 센다 — 빌드가 양쪽을 같은 규칙(`space_places`)으로 맞춘다.
- PS1 쪽 = `--ref` 커밋의 `games/ps1-ed1+2/line_dict.json`(git 에서 읽는다 — 워크트리를 안 건드린다).
- 🔴 **공유 열쇠** — 두 편이 같이 쓰는 열쇠는 한쪽만 받으면 다른 편이 따라 흔들린다. 따로 센다.
"""

import argparse
import collections
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import patch_scn as P
import typeset_scn as T
from text.line_key import key as line_key

DICT_PATH = "games/ps1-ed1+2/line_dict.json"


def edition(path):
    return 1 if (path == "/ED.BIN" or "/ED1SCN" in path) else 2


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=P._ROOT, capture_output=True, text=True, check=True
    ).stdout


def ps1_lines(ref):
    sha = _git("rev-parse", ref).strip()
    raw = json.loads(_git("show", f"{sha}:{DICT_PATH}"))["lines"]
    return sha, {k: v["t"] for k, v in raw.items() if isinstance(v, dict) and v.get("t")}


def blocks(mm):
    """`{편: {열쇠: (경로, JP)}}` — 원본 덤프에서, 열쇠당 첫 자리."""
    out = {1: {}, 2: {}}
    for path, _l, _s in common.iso_files(mm):
        if not P.SCN_RE.match(path):
            continue
        got = P.load(path)
        if not got:
            continue
        for e in got[1]:
            if e.get("text"):
                out[edition(path)].setdefault(line_key(e["text"]), (path, e["text"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="origin/game/ps1-ed1+2")
    ap.add_argument("--ed", type=int, choices=(1, 2), default=1)
    ap.add_argument("--show", type=int, default=10)
    a = ap.parse_args()
    sha, ps1 = ps1_lines(a.ref)
    canon = P.load_canon(quiet=True)
    ours = P.load_ours()
    f, mm = common.open_image()
    try:
        canon = P.augment_names(canon, mm)
        bl = blocks(mm)
    finally:
        mm.close()
        f.close()
    mine, other = bl[a.ed], bl[3 - a.ed]
    same, diff, shared, missing = 0, [], [], collections.Counter()
    place_only = 0  # 대사 지명 규칙(`typeset_scn.space_places`)이 맞추는 차이 — 빌드에선 같아진다
    for k, (path, jp) in mine.items():
        ss = canon.get(k)
        if k not in ps1:
            if k in ours:
                why = "새턴 전용"
            elif P.name_for(jp):
                why = "이름 칸"
            elif ss is None:
                why = "씬 문안 아님"  # 시스템 문구(patch_ui 몫)·파일명 등 — 이 사전을 안 탄다
            else:
                why = "저본 없음"
            missing[why] += 1
        elif ss == ps1[k]:
            same += 1
        elif ss and T.space_places(ss) == T.space_places(ps1[k]):
            place_only += 1
        elif k in other:
            shared.append((path, k, ss, ps1[k]))
        else:
            diff.append((path, k, ss, ps1[k]))
    print(f"  PS1 {a.ref} = {sha[:12]} · ED{a.ed} 원문 {len(mine):,}")
    print(
        f"  같음 {same:,} · 지명 띄어쓰기만 {place_only} · 다름 {len(diff)} · 다름(ED{3 - a.ed} 와 공유 열쇠) {len(shared)}"
        f" · PS1 에 없음 {sum(missing.values())} {dict(missing)}"
    )
    for tag, rows in (("다름", diff), ("공유", shared)):
        for path, k, ss, p in rows[: a.show]:
            print(f"    [{tag}] {path} {k}\n        새턴 {ss!r}\n        PS1  {p!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
