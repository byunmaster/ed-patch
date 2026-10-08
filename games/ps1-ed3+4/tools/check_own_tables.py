#!/usr/bin/env python3
"""「자기 표 0」 검사 — 게임 폴더에 **가나·한자 열쇠 → 한글 값** 표가 남았나 (마스터 10-08 「모든 워커는 자기사전을 들고 있으면 안돼」).

    python3 tools/check_own_tables.py

🔴 이름·라벨·호칭·지명·아이템·몬스터의 JP→KR 값은 **정본(`shared/canon` — 고유명사는 `nouns/`)에서만** 읽는다. 게임 폴더(코드의 dict·튜플 상수, json)에 든 표는
   한쪽만 고쳐져 어긋난다(PS1 v1.0.0 배포판에 옛 몬스터 이름 15종이 나간 사고). 값 없는 열쇠 목록(`glossary_keys_ed3.json` — 읽을 낱말만 고르는 열쇠)은 표가 아니다.

잡는 꼴: ① 같은 줄에 `"가나/한자…" : "…한글…"` / `("가나/한자…", "…한글…")` ② json 의 키가 가나/한자이고 값(또는 값 안의 `kr`)이 한글.
예외(명시): ① **스태프롤 이름 표** — 게임마다 제작진이 달라 게임이 갖는 게 맞다(마스터 10-08). ② `PENDING` — 관리자가 옮기는 중인 표(끝나면 비운다).
⚠ `tools/tests/`(합성 입력)·주석은 안 본다.
"""

import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JP = r"[぀-ヿ一-鿿]"
HG = r"[가-힣]"
PAIR = re.compile(rf"""["'][^"'\n]*{JP}[^"'\n]*["']\s*[:,]\s*["'][^"'\n]*{HG}""")

# 스태프롤(제작진 이름)은 게임마다 달라 게임 폴더에 둔다 — 지금 ED3 는 그림(TIM)이라 표가 없다. 생기면 여기 파일명을 올린다.
STAFFROLL = set()
# 관리자가 정본으로 옮기는 중인 표 — 끝나면 비운다(마스터 10-08).
PENDING = {}  # (비었다 — `glossary_ed4.json` 은 정본 `nouns/ed4.json` 으로 옮겨 지웠다, 10-08)


def py_hits():
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "tools", "*.py"))):
        name = os.path.basename(f)
        if name in STAFFROLL or name == os.path.basename(__file__):
            continue
        with open(f, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                code = line.split("#")[0] if "#" in line and not re.search(r"""["'][^"']*#""", line) else line
                if PAIR.search(code):
                    out.append(f"{name}:{i}: {line.strip()[:70]}")
    return out


def json_hits():
    out = []

    def walk(o, path, rel):
        if isinstance(o, dict):
            for k, v in o.items():
                if re.search(JP, str(k)):
                    val = v.get("kr") if isinstance(v, dict) else v
                    if isinstance(val, str) and re.search(HG, val):
                        out.append(f"{rel}: {path}/{k[:12]}")
                        return
                walk(v, f"{path}/{k}", rel)
        elif isinstance(o, list):
            for v in o:
                walk(v, path, rel)

    for f in sorted(glob.glob(os.path.join(ROOT, "*.json")) + glob.glob(os.path.join(ROOT, "textmap", "*.json"))):
        rel = os.path.relpath(f, ROOT)
        if rel in STAFFROLL:
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        n0 = len(out)
        walk(d, "", rel)
        if len(out) > n0 and rel in PENDING:
            out[n0:] = [f"(대기) {rel}: {PENDING[rel]}"]
    return out


def main():
    hits = py_hits() + json_hits()
    pending = [h for h in hits if h.startswith("(대기)")]
    bad = [h for h in hits if not h.startswith("(대기)")]
    print(f"자기 표 검사 — 코드·json 에 든 JP→KR 표 {len(bad)} (대기 {len(pending)})")
    for h in bad[:20]:
        print(f"  🔴 {h}")
    for h in pending:
        print(f"  ⏳ {h}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
