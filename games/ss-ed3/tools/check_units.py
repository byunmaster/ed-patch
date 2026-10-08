"""숫자에 붙는 **단위 표기**를 한 규칙으로 지킨다.

    python3 games/ss-ed3/tools/check_units.py            # 어긋난 자리 보기
    python3 games/ss-ed3/tools/check_units.py --apply    # 정본을 고친다

🔴 **숫자 + 화폐 단위는 붙여 쓴다** — 「10피아」·「7고아」(유저 확정 2026-09-01).

   원문이 근거가 못 되는 자리다 — 일본어엔 **띄어쓰기가 아예 없어**(`%dピア`) 어느 쪽이
   원본에 맞는지 물을 수가 없다. 그래서 **우리 문안의 다수결**로 정했다: 세어 보니
   47 건이 이미 붙임이고 시스템 문자열 둘만 띄어져 있었다 — 규칙이 없어서가 아니라
   **그 둘이 흘러 나간 것**이었다.

⚠ **UI 는 이 규칙 밖이다.** HUD 의 `70 Pia / 0 Goa` 와 상점 가격 상자 `18 pia × 1` 은
  게임이 자기 ASCII 로 직접 그린다 — 우리 문안이 아니라서 여기 안 걸린다.

⚠ 한글 맞춤법 제43 항은 단위 명사를 띄어 쓰라고 하지만, 같은 항이 **숫자와 어울려 쓰는
  경우 붙여 쓸 수 있다**고 열어 둔다. 화면 폭이 빠듯한 이 게임에서는 붙임이 이득이다
  (띄우면 51 자리에서 반 칸씩 더 먹는다).
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

SCRIPT_DIR = os.path.join(C.GAME_DIR, "script")
UNITS = ("피아", "고아")  # 이 게임의 화폐. 늘어나면 여기 더한다
BAD = re.compile(r"(%d|\d)[ 　]+(" + "|".join(UNITS) + r")")


def files():
    yield from sorted(glob.glob(os.path.join(SCRIPT_DIR, "MAP*.json")))
    yield from sorted(glob.glob(os.path.join(SCRIPT_DIR, "book", "BOOK*.json")))


def walk(o, path=()):
    """`(경로, 문자열)` 을 죄다 내놓는다 — 갈래 구조가 파일마다 달라서 통째로 훑는다."""
    if isinstance(o, str):
        yield path, o
    elif isinstance(o, dict):
        for k, v in o.items():
            if not str(k).startswith("_"):
                yield from walk(v, (*path, str(k)))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, (*path, str(i)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="정본을 고친다")
    a = ap.parse_args()

    bad = 0
    import system_src as SYS

    #   시스템 표는 파일이 아니라 정본·사전에서 읽은 값이다 — 고칠 곳이 이쪽에 없으니 보기만 한다
    for k, s in walk(SYS.sections()):
        if BAD.search(s):
            bad += 1
            print(f"  ❌ 시스템:{'/'.join(k)}  {s!r} — 정본에서 고쳐야 한다(관리자에게)")
    for p in files():
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        hits = [(k, s) for k, s in walk(doc) if BAD.search(s)]
        if not hits:
            continue
        bad += len(hits)
        for k, s in hits:
            m = BAD.search(s)
            print(
                f"  ❌ {os.path.basename(p)}:{'/'.join(k)}  …{s[max(0, m.start() - 8) : m.end() + 8]!r}…"
            )
        if a.apply:

            def fix(o):
                if isinstance(o, str):
                    return BAD.sub(r"\1\2", o)
                if isinstance(o, dict):
                    return {k: (v if str(k).startswith("_") else fix(v)) for k, v in o.items()}
                if isinstance(o, list):
                    return [fix(v) for v in o]
                return o

            with open(p, "w", encoding="utf-8") as f:
                json.dump(fix(doc), f, ensure_ascii=False, indent=1)
                f.write("\n")

    if bad and a.apply:
        print(f"→ {bad} 자리를 붙여 썼다")
        return 0
    if bad:
        print(f"→ 띄어 쓴 자리 {bad} — `--apply` 로 고친다 (숫자 + 화폐 단위는 붙여 쓴다)")
        return 1
    print("✅ 숫자 + 단위 표기가 한 규칙이다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
