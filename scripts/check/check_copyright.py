#!/usr/bin/env python3
"""저작권 게이트 — 커밋되는 글에 **긴 일본어 문장**(팔콤 원문 등)이 늘지 않게 막는다.

    python3 scripts/check/check_copyright.py --game ps1-ed1+2     # 그 게임 폴더
    python3 scripts/check/check_copyright.py --common             # 공용(shared · scripts · docs · CLAUDE.md · .claude · patcher)
    … --list                                                      # 파일별 건수와 첫 위치(앞 12자만)
    … --freeze                                                    # 기준선을 지금 값으로(줄어든 것만 — 늘리려면 --force)

이 레포는 공개다(CLAUDE.md 「저작권」). 원문 문장은 문서·주석·테스트·메모에 통째로 두지 않는다 — 예시는 가짜 문장,
출처는 좌표(`ED1SCN3#665`)나 링크로. 낱말·라벨(아이템·몬스터·지명·메뉴)은 대상이 아니다.

잣대: 가나·한자가 **20자 이상 이어진 덩이**(부호·전각 공백은 이어 준다). 짧은 라벨·정본의 메뉴 문구는 안 걸린다.
🔴 **래칫**이다 — 파일마다 기준선(`copyright_baseline.json`)보다 **늘면 실패**, 줄면 `--freeze` 로 내린다. 처음부터
0 을 요구하면 늘 빨간불이라 아무도 안 본다(라운드마다 내려 0 으로 간다). 새 파일은 기준선이 0 이다.
정발(국내판) 한글 문장 대조는 원문 코퍼스가 있는 게임 게이트 몫이다(PS1 `check_forbidden` — 코퍼스가 없으면
통과가 아니라 「안 쟀다」로 실패해야 한다, 10-09 감사).
"""

import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEXT_EXT = {".md", ".py", ".json", ".txt", ".sh", ".toml", ".yml", ".yaml", ".html", ".tsv", ".csv", ".tmpl"}
COMMON = ("shared/", "scripts/", "docs/", "patcher/", ".claude/", "CLAUDE.md", "README.md")
MIN_RUN = 20
_JP = r"ぁ-ヿ一-鿿々〆"
_GLUE = r"・･、。！？!?「」『』…　 "
RUN = re.compile(f"[{_JP}{_GLUE}]{{{MIN_RUN},}}")
LETTER = re.compile(f"[{_JP}]")


def _tracked(prefixes):
    out = subprocess.run(["git", "-C", ROOT, "ls-files"], capture_output=True, text=True, check=True).stdout
    for p in out.splitlines():
        if any(p == x or p.startswith(x) for x in prefixes) and os.path.splitext(p)[1] in TEXT_EXT:
            if "/_inventory/" in p:
                continue
            yield p


def scan(prefixes):
    """{경로: [(줄 번호, 덩이 앞 12자)]} — 가나·한자 20자 이상 덩이."""
    hits = {}
    for p in _tracked(prefixes):
        try:
            with open(os.path.join(ROOT, p), encoding="utf-8") as f:
                text = f.read()
        except (UnicodeDecodeError, OSError):
            continue
        found = runs(text)
        if found:
            hits[p] = found
    return hits


def runs(text):
    """[(줄 번호, 덩이 앞 12자)] — 가나·한자 MIN_RUN 자 이상 덩이. `copyright:ok` 가 든 줄은 건너뛴다."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if "copyright:ok" in line:  # 문자표 등 문장이 아닌 줄(사유를 같은 줄 주석에)
            continue
        for m in RUN.finditer(line):
            if len(LETTER.findall(m.group(0))) >= MIN_RUN:
                out.append((n, m.group(0)[:12]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--game")
    g.add_argument("--common", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--force", action="store_true", help="--freeze 가 기준선을 늘리는 것도 허용")
    a = ap.parse_args(argv)

    if a.common:
        prefixes, base_path, label = COMMON, os.path.join(ROOT, "scripts/check/copyright_baseline.json"), "공용"
    else:
        prefixes = (f"games/{a.game}/",)
        base_path, label = os.path.join(ROOT, "games", a.game, "copyright_baseline.json"), a.game
    hits = scan(prefixes)
    counts = {p: len(v) for p, v in sorted(hits.items())}
    base = {}
    if os.path.exists(base_path):
        with open(base_path, encoding="utf-8") as f:
            base = json.load(f)
    base = {k: v for k, v in base.items() if not k.startswith("_")}

    if a.freeze:
        grew = {p: (base.get(p, 0), c) for p, c in counts.items() if c > base.get(p, 0)}
        if grew and not a.force and base:
            print(f"⛔ 기준선을 늘리려 한다(--force 로만): {grew}")
            return 1
        doc = {"_doc": "check_copyright 래칫 — 파일별 긴 일본어 덩이 수. 늘면 실패, 줄면 --freeze."}
        doc.update(counts)
        with open(base_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"저작권 기준선 [{label}] 동결 — 파일 {len(counts)} · 덩이 {sum(counts.values())}")
        return 0

    grew = {p: (base.get(p, 0), c) for p, c in counts.items() if c > base.get(p, 0)}
    total, btotal = sum(counts.values()), sum(base.values())
    print(f"저작권 검사 [{label}] — 긴 일본어 덩이 {total} (기준선 {btotal}) · 파일 {len(counts)}")
    if a.list:
        for p, c in counts.items():
            print(f"  {c:4d}  {p}  예: {hits[p][0][0]}행 「{hits[p][0][1]}…」")
    if grew:
        for p, (b, c) in grew.items():
            first = hits[p][0]
            print(f"  ✗ {p}: {b} → {c}  (예: {first[0]}행 「{first[1]}…」) — 원문 문장은 좌표·가짜 문장·요약으로")
        return 1
    if total < btotal:
        print(f"  ↓ 기준선보다 줄었다 — `--freeze` 로 내린다({btotal} → {total})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
