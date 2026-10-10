"""`MAP*.BIN` 의 장 시작·완료 화면을 번역해 `script/<맵>.json` 에 박는다.

    python3 games/ss-ed3/tools/gen_chapter_lines.py --check
    python3 games/ss-ed3/tools/gen_chapter_lines.py --write

이 화면은 **가운데 정렬**이다 — 들여쓰기 = `(화면 24칸 − 제목칸) ÷ 2`. 21 블록 중 19 가
그 규칙에 맞았다(실측). 그래서 번역 길이가 달라져도 **들여쓰기를 다시 계산**하면 원문과
같은 자리에 놓인다.

🔴 **생성물을 빌드가 직접 만들지 않는다.** `--write` 로 `script/` 에 **박아 두고** 커밋한다 —
   빌드는 정본만 읽어야 결정적이다(루트 `CLAUDE.md` 「제1 원칙」).

⚠ **장 표시 줄만 있는 블록**만 자동으로 만든다. 나레이션이 섞인 블록(예 `MAP070`)은
   대사 번역이라 사람 몫이다 — 조용히 반쪽만 옮기면 뒤가 원문으로 남는다.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import typeset as T
import center_narration as CN

SCRIPT_DIR = os.path.join(C.GAME_DIR, "script")
LINE = re.compile(r"^(　*)((?:序章|第[０-９]章|最終章)　[^　\n]+)(　完)?$")


def tables():
    import system_src as SYS

    d = SYS.sections()
    return d["chapter_line"], d["word"]["完"]


def center(title):
    """가운데 정렬 들여쓰기 — 정본은 `center_narration` 하나다(화면 중심 · 반 칸 단위).

    ⚠ `--write` 뒤엔 `center_narration.py` 를 한 번 돌린다 — 예산이 빠듯한 카드는
      거기서 블록째 반 칸씩 옮겨 맞춘다(게이트가 그걸 본다).
    """
    return CN.lead_for(title)


def translate(text, tbl, fin_kr, shift=0):
    """블록 전체를 번역 — **장 표시 줄만** 있을 때만. 아니면 `None`.

    `shift` 만큼 들여쓰기를 줄인다 — 번역이 원문보다 길어 예산을 넘을 때 쓴다.
    ⚠ 빈 줄은 그대로 둔다. 원문이 `…巡礼者\n` 처럼 개행으로 끝나서, 이걸 안 봐주면
      **멀쩡한 블록이 「나레이션 섞임」으로 오판**된다(실측 10건).
    """
    out = []
    for line in text.split(T.NL):
        vis = T.visible(line)
        if not vis.strip():
            out.append(line)
            continue
        m = LINE.match(vis)
        if not m:
            return None
        kr = tbl.get(m.group(2))
        if kr is None:
            return None
        if m.group(3):
            kr += "　" + fin_kr
        ind = center(kr)
        out.append(ind[: max(0, len(ind) - shift)] + kr)
    return T.NL.join(out)


def fit(text, tbl, fin_kr, budget):
    """예산에 맞는 번역 — 넘치면 **들여쓰기를 한 칸씩 줄여** 흡수한다.

    ⚠ 반각 공백 한 자(1B)만으로도 예산을 넘길 수 있다 — 가운데 정렬은 0.5칸 단위라
      바이트가 홀수로 떨어진다(실측 7건이 1B 초과였다).
    """
    for shift in range(4):
        kr = translate(text, tbl, fin_kr, shift)
        if kr is None:
            return None, None
        got = T.pad_to_budget(kr, budget, width=T.SCREEN_COLS, keep_last=False)
        if got is not None:
            return kr, got
    return kr, None


def scan():
    """`[(맵, 블록번호, JP, KR, 예산, 맞춘 것 또는 None)]`."""
    tbl, fin = tables()
    rows = []
    for path in sorted(os.listdir(os.path.join(C.OUT_DIR, "map_jp"))):
        stem = path[:-5]
        with open(os.path.join(C.OUT_DIR, "map_jp", path), encoding="utf-8") as f:
            blocks = json.load(f)["blocks"]
        for i, b in enumerate(blocks):
            if not any(LINE.match(x) for x in T.lines(b["text"])):
                continue
            budget = T.body_bytes(b["text"])
            kr, fitted = fit(b["text"], tbl, fin, budget)
            rows.append((stem, i, b["text"], kr, budget, fitted))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="script/<맵>.json 에 박는다")
    ap.parse_args()
    rows = scan()
    ok = [r for r in rows if r[5] is not None]
    mixed = [r for r in rows if r[3] is None]
    over = [r for r in rows if r[3] is not None and r[5] is None]
    print(
        f"장 표시 블록 {len(rows)}  자동 {len(ok)}  섞인 블록 {len(mixed)}  예산 초과 {len(over)}"
    )
    for stem, i, jp, kr, bud, fit in rows:
        tag = "✅" if fit else ("… 나레이션 섞임(사람 몫)" if kr is None else "❌ 예산 초과")
        first = T.lines(jp)[0] if T.lines(jp) else ""
        print(f"  {stem} [{i:>3}] {bud:>4}B  {first.strip()[:26]:<28}{tag}")
    if not sys.argv[1:] or not any(a == "--write" for a in sys.argv[1:]):
        return
    by = {}
    for stem, i, _, _, _, fit in ok:
        by.setdefault(stem, {})[str(i)] = fit
    for stem, add in by.items():
        p = os.path.join(SCRIPT_DIR, f"{stem}.json")
        doc = {}
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                doc = json.load(f)
        doc.setdefault(
            "_doc", "번역 정본 — 키는 MAP 블록 색인. 장 표시 줄은 `gen_chapter_lines.py` 가 박는다."
        )
        #   🔴 `_wide` 블록(맵 꼬리에서 그리는 카드 — `choice_tail.py`)의 정본 값은 사람이 박은 진짜 문안이다 — 예산에 맞춘 값으로 덮지 않는다
        add = {k: v for k, v in add.items() if k not in doc.get("_wide", {})}
        doc.update(add)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
            f.write("\n")
    print(f"\n✅ {len(by)} 파일에 {len(ok)} 블록 박았다")


if __name__ == "__main__":
    main()
