#!/usr/bin/env python3
"""같은 열쇠(화자+원문이 같음)가 이미 다른 씬 정본에 번역돼 있으면 그 항목을 그대로 복사한다 — 「같은 원문 = 같은 문안」.

  python3 tools/scene_reuse.py [씬…] [--dry]      # 씬을 안 주면 전 씬
입장 배너(`raw`) 항목도 그대로 옮긴다. 이미 있는 열쇠는 건드리지 않는다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

SCRIPT = common.GAME_DIR / "script"
DERIVED = common.GAME_DIR / "work" / "derived" / "messages"


def sync(n: int) -> None:
    """씬 n 의 번역을 같은 열쇠가 든 **다른 모든 씬**에 덮어 쓴다 — 한 곳을 고친 뒤 같은 원문의 다른 자리를 맞출 때."""
    src = json.loads((SCRIPT / f"scn{n:03d}.json").read_text("utf-8"))["messages"]
    for p in sorted(SCRIPT.glob("scn*.json")):
        if p.stem == f"scn{n:03d}":
            continue
        doc = json.loads(p.read_text("utf-8"))
        ch = 0
        for k, v in doc["messages"].items():
            if k in src and v != src[k]:
                doc["messages"][k] = src[k]
                ch += 1
        if ch:
            p.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
            print(f"{p.stem}: {ch}줄 맞춤")


def main() -> int:
    if "--sync" in sys.argv:  # python3 tools/scene_reuse.py --sync 13
        sync(int(sys.argv[sys.argv.index("--sync") + 1]))
        return 0
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    pool: dict[str, dict] = {}
    for p in sorted(SCRIPT.glob("scn*.json")):
        pool.update(json.loads(p.read_text("utf-8"))["messages"])
    todo = [int(x) for x in a] or sorted(int(p.stem[3:]) for p in DERIVED.glob("scn*.json"))
    tot = 0
    for n in todo:
        p = SCRIPT / f"scn{n:03d}.json"
        doc = json.loads(p.read_text("utf-8")) if p.exists() else {"_doc": f"scn {n} 번역 정본 — 열쇠는 messages.py key, 원문 대조는 work/derived/messages/scn{n:03d}.json", "messages": {}}
        got = 0
        for m in json.loads((DERIVED / f"scn{n:03d}.json").read_text("utf-8")):
            k = m["key"]
            if k not in doc["messages"] and k in pool:
                doc["messages"][k] = pool[k]
                got += 1
        if got:
            tot += got
            print(f"scn{n:03d}: 같은 열쇠 {got}줄 복사")
            if "--dry" not in sys.argv:
                p.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"합계 {tot}줄")
    return 0


if __name__ == "__main__":
    sys.exit(main())
