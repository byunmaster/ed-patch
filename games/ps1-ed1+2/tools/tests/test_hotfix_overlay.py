#!/usr/bin/env python3
"""핫픽스 시험 경로(`hotfix/`) 정합 — **원본 없이** 돈다.

제품 롬은 `hotfix/` 를 안 읽는다(`ED_HOTFIX=1` 일 때만). 그래서 이 파일들이 조용히 낡아도 제품은 멀쩡해 아무도 모른다 —
여기서 ① 덮는 블록이 제품 정본(`script/`)에 실제로 있고 ② 문안이 정말 다르며(헛 덮어쓰기 방지) ③ 값 모양이 맞는지 본다.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
HOT = os.path.join(ROOT, "hotfix")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_hotfix_script_blocks_exist_and_differ():
    hdir = os.path.join(HOT, "script")
    for name in sorted(os.listdir(hdir)):
        if not name.endswith(".json"):
            continue
        hot = _load(os.path.join(hdir, name))
        base = _load(os.path.join(ROOT, "script", name))
        for eid, v in hot.items():
            if eid.startswith("_"):
                continue
            assert eid in base, f"{name}:{eid} — 제품 정본에 없는 블록을 덮는다"
            assert isinstance(v, dict) and v.get("t"), f"{name}:{eid} — 값은 {{t, s?}} 꼴이어야 한다"
            old = base[eid] if isinstance(base[eid], dict) else {"t": base[eid]}
            assert (v["t"], v.get("s")) != (old.get("t"), old.get("s")), f"{name}:{eid} — 제품과 같다(헛 덮어쓰기)"


def test_hotfix_textmap_values_are_strings():
    hdir = os.path.join(HOT, "textmap")
    for name in sorted(os.listdir(hdir)):
        if not name.endswith(".json"):
            continue
        for k, v in _load(os.path.join(hdir, name)).items():
            if k.startswith("_"):
                continue
            assert isinstance(v, str) and v, f"{name}:{k}"
            if name == "monster_lines_ed2.json":  # 원문 키 손표 — 제품 표에 있고 값이 달라야 한다
                base = _load(os.path.join(ROOT, "textmap", name))
                assert k in base and base[k] != v, f"{name}:{k} — 제품 표에 없거나 같다(헛 덮어쓰기)"
                continue
            assert len(k) == 10 or k.startswith("0x"), f"{name}:{k} — textmap 키(sha 앞 10자 · 엔딩류는 0x오프셋)가 아니다"


if __name__ == "__main__":
    for fn in (test_hotfix_script_blocks_exist_and_differ, test_hotfix_textmap_values_are_strings):
        fn()
        print(f"  ok  {fn.__name__}")
