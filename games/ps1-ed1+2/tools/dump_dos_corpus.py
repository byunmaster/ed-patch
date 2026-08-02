#!/usr/bin/env python3
"""정발(만트라 DOS) 대사 전문을 문법·띄어쓰기 검수용으로 뽑는다.

빌드에 들어가는 **파이프라인 통과 후** 문안을 낸다 — 원문 그대로가 아니라
`spell_fix`(dos_spelling_fixes.json) + `resolve_dos_breaks`(표시 개행 해소)를
거친, 실제로 화면에 나갈 문자열이다. 검사기가 잡은 걸 고치면 그대로
`dos_spelling_fixes.json` 의 `replace` 로 반영하면 된다.

⚠ 산출물은 정발 문안 전량이라 **저작권상 커밋 금지** — REVIEW_DIR(work/review,
gitignore) 로만 나간다. 경로를 옮기지 말 것.

출력
  review/corpus/<GAME>_corpus.md        표 단위 전문(엔트리 번호 병기 — 역추적용)
  review/corpus/<GAME>_uniq.txt         중복 제거 문장 목록(검사 대상 정본)
  review/corpus/paste/<GAME>_NNN.txt    검사 사이트 붙여넣기용 청크

사용
  python3 tools/dump_dos_corpus.py              # ED1 ED2 둘 다
  python3 tools/dump_dos_corpus.py ED1 --chunk 900
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from align_jp_kr import DOS_KR_DIR  # noqa: E402
from common import REVIEW_DIR  # noqa: E402
from reinsert_kr_pilot import HARD_NL, resolve_dos_breaks, spell_fix  # noqa: E402

OUT = os.path.join(REVIEW_DIR, "corpus")

# 제어 마크업: {n} {p} {spk} … 와 \xNN 이스케이프. 문장 판정 전에 걷어낸다.
MARKUP = re.compile(r"\{[^}]*\}|\\x[0-9A-Fa-f]{2}")
HANGUL = re.compile(r"[가-힣]")
# 문장 끝 — 종결부호 뒤. 정발은 ` !!` 처럼 부호 앞을 띄우므로 부호를 다 삼킨다.
SENT_END = re.compile(r"(?<=[.!?…])(?=\s)|(?<=[.!?…])$")


def normalize(text):
    """빌드와 같은 순서로 정규화한다 — 검사 대상 = 실제 출력 문자열."""
    t = text.replace("엘아스터", "엘아스타").replace("크루즈의 마을", "크루즈 마을")
    t = spell_fix(t)
    t = resolve_dos_breaks(t)  # {n} 표시 개행 해소 (line_overrides 는 HARD_NL 로)
    return t


def to_lines(t):
    """정규화된 엔트리 텍스트 → 검수 단위 문장 목록."""
    out = []
    for page in t.split("{p}"):
        page = MARKUP.sub(" ", page.replace(HARD_NL, " "))
        page = re.sub(r"\s+", " ", page).strip()
        if not HANGUL.search(page):
            continue  # 값 테이블·라벨 조각 — 검수 대상 아님
        for s in SENT_END.split(page):
            s = s.strip()
            if s and HANGUL.search(s):
                out.append(s)
    return out


def dump(game, chunk):
    os.makedirs(os.path.join(OUT, "paste"), exist_ok=True)
    tables, uniq, n_entry = [], {}, 0
    for f in sorted(glob.glob(os.path.join(DOS_KR_DIR, game, "*.json"))):
        if os.path.basename(f).startswith(("_", ".")):
            continue
        doc = json.load(open(f, encoding="utf-8"))
        rows = []
        for e in doc["entries"]:
            if e["kind"] != "block":
                continue
            lines = to_lines(normalize(e["text"]))
            if not lines:
                continue
            n_entry += 1
            rows.append((e["entry_id"], lines))
            for s in lines:
                uniq.setdefault(s, []).append(f"{doc['table_id']}#{e['entry_id']}")
        if rows:
            tables.append((doc["table_id"], rows))

    md = [
        f"# {game} 정발 대사 전문 (검수용)",
        "",
        "⚠ 정발 문안 — **커밋 금지**. `tools/dump_dos_corpus.py` 생성물.",
        "빌드 파이프라인(spell_fix + resolve_dos_breaks) 통과 후 문자열이라 "
        "여기서 잡힌 건 `dos_spelling_fixes.json` 의 `replace` 로 바로 반영된다.",
        "",
        f"- 표 {len(tables)} · 엔트리 {n_entry} · 문장 {sum(len(v) for v in uniq.values())} "
        f"(중복 제거 {len(uniq)})",
        "",
    ]
    for tid, rows in tables:
        md.append(f"## {tid}")
        md.append("")
        for eid, lines in rows:
            md.append(f"- **{eid}** " + " / ".join(lines))
        md.append("")
    p_md = os.path.join(OUT, f"{game}_corpus.md")
    open(p_md, "w", encoding="utf-8").write("\n".join(md))

    keys = sorted(uniq)
    p_uq = os.path.join(OUT, f"{game}_uniq.txt")
    open(p_uq, "w", encoding="utf-8").write("\n".join(keys) + "\n")

    # 붙여넣기 청크 — 검사 사이트 입력 한계(보통 수백~수천 자)에 맞춰 문장 경계로만 자른다
    parts, cur, n = [], [], 0
    for s in keys:
        if cur and n + len(s) + 1 > chunk:
            parts.append(cur)
            cur, n = [], 0
        cur.append(s)
        n += len(s) + 1
    if cur:
        parts.append(cur)
    for old in glob.glob(os.path.join(OUT, "paste", f"{game}_*.txt")):
        os.remove(old)
    for i, part in enumerate(parts, 1):
        open(os.path.join(OUT, "paste", f"{game}_{i:03d}.txt"), "w", encoding="utf-8").write(
            "\n".join(part) + "\n"
        )

    print(
        f"  {game}: 표 {len(tables)} · 엔트리 {n_entry} · 문장 {len(keys)}종 · 청크 {len(parts)}개"
    )
    return p_md, p_uq, len(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("games", nargs="*", default=["ED1", "ED2"])
    ap.add_argument("--chunk", type=int, default=900, help="청크 파일 최대 글자 수")
    a = ap.parse_args()
    print(f"정발 대사 덤프 → {OUT}")
    for g in a.games or ["ED1", "ED2"]:
        dump(g, a.chunk)


if __name__ == "__main__":
    main()
