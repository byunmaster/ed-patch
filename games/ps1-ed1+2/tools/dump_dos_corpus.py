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

# ⚠ 제어코드 일부는 **인자를 감싼다** — `\x0F$\x0D`, `\x10d\x11`. 양끝만 지우면 가운데
# 인자($ X d)가 본문으로 남아, 외부 맞춤법 검사기가 그걸 낱말로 오해하고 조사까지 붙인다
# (`` `1 무찌를 `` → `1을 무찌를` 실측 2026-08-02). 감싼 채로 통째로 걷어낸다.
INJECT = re.compile(r"\\x0F.{0,2}?\\x0D|\\x10.{0,4}?\\x11|`[0-9{]")
# 그 밖의 마크업: {n} {p} {spk} … 와 단독 \xNN 이스케이프.
MARKUP = re.compile(r"\{[^}]*\}|\\x[0-9A-Fa-f]{2}")
# 마크업을 걷어내도 **인자 한 글자가 남는** 코드가 있다(`\xEB&`, `\x0FP`). 홀로 선 ASCII
# 한 글자는 한국어 대사에 나올 일이 없으니 잔재로 본다 — 줄머리(`( 비 빌어먹을`)와
# 줄중간(`남자 Q 병사`) 둘 다. `.`(말줄임)와 한글·숫자는 건드리지 않는다.
RESIDUE = re.compile(r"^[^\s.가-힣0-9]\s+|^[&|}⒳]\s*|(?<=\s)[A-Za-z⒳](?=\s|$)")
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
    """정규화된 엔트리 텍스트 → [(문장, 주입코드였음)] 목록.

    두 번째 값이 참이면 그 문장에는 런타임 주입 자리(이름·낱말)가 있었다 — 검사기
    제안을 그대로 믿으면 안 된다(사라진 자리의 조사·띄어쓰기를 검사기가 재구성한다)."""
    out = []
    for page in t.split("{p}"):
        page = page.replace(HARD_NL, " ")
        inj = bool(INJECT.search(page))
        page = MARKUP.sub(" ", INJECT.sub(" ", page))
        page = re.sub(r"\s+", " ", page).strip()
        if not HANGUL.search(page):
            continue  # 값 테이블·라벨 조각 — 검수 대상 아님
        for s in SENT_END.split(page):
            # ⚠ RESIDUE 는 `^` 앵커를 쓰므로 **먼저 strip** 해야 한다(split 조각엔 선행
            # 공백이 남는다). 연속 잔재(`남자 Q 병사 P`)를 위해 2패스.
            s = re.sub(r"\s+", " ", RESIDUE.sub(" ", RESIDUE.sub(" ", s.strip()).strip())).strip()
            if s and HANGUL.search(s):
                out.append((s, inj))
    return out


def entries(game):
    """(표 id, 엔트리 id, [(문장, 주입)]) 순회 — `collect`·`dump` 의 **공통 원천**.

    둘이 같은 순회를 따로 갖고 있었다. 한쪽만 고치면 검사 대상과 검토표가 어긋난다."""
    for f in sorted(glob.glob(os.path.join(DOS_KR_DIR, game, "*.json"))):
        if os.path.basename(f).startswith(("_", ".")):
            continue
        doc = json.load(open(f, encoding="utf-8"))
        for e in doc["entries"]:
            if e["kind"] != "block":
                continue
            lines = to_lines(normalize(e["text"]))
            if lines:
                yield doc["table_id"], e["entry_id"], lines


def collect(game):
    """{문장: {"at": [표#엔트리…], "inject": bool}} — 검사 대상 정본."""
    uniq = {}
    for tid, eid, lines in entries(game):
        for s, inj in lines:
            r = uniq.setdefault(s, {"at": [], "inject": False})
            r["at"].append(f"{tid}#{eid}")
            r["inject"] |= inj
    return uniq


def dump(game, chunk):
    os.makedirs(os.path.join(OUT, "paste"), exist_ok=True)
    tables, uniq, n_entry = [], {}, 0
    for tid, eid, lines in entries(game):
        n_entry += 1
        txt = [s for s, _ in lines]
        if tables and tables[-1][0] == tid:
            tables[-1][1].append((eid, txt))
        else:
            tables.append((tid, [(eid, txt)]))
        for s in txt:
            uniq.setdefault(s, []).append(f"{tid}#{eid}")

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
