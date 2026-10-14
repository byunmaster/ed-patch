#!/usr/bin/env python3
"""음성이 **읽는 메시지**를 골라 시각 초안을 만든다 — 씬의 모든 메시지를 인식 결과(`voice_words.py`)와 맞춰 음성 안에서 일치하는 것만 시간 순으로 낸다.

    python3 tools/voice_pick.py <씬> <음성 rel> [--min 0.5] [--json]

메시지마다 인식 글자열 위를 훑어 가장 비슷한 구간(길이 ≈ 메시지 × 1.5)을 찾고, 비슷한 정도(원문 글자 중 맞은 비율)가 `--min` 이상이면 「읽힌 메시지」로 친다.
출력 = 시간 순 [메시지 주소 · 열쇠 · 일치율 · 시작~끝 초 · 쪽 끝 초안]. 사람이 보고 고른다(순서·누락·같은 대사 중복) — 자동 확정이 아니라 초안이다.
"""

import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import messages as M
import voice_align as A
import voice_sched as VS


def pick(sid: int, rel: int, thr: float = 0.5) -> list[dict]:
    words = json.loads((A.REVIEW / f"words_r{rel}.json").read_text("utf-8"))
    rc = A.rec_chars(words)
    rec = "".join(c for c, _ in rc)
    msgs = M.parse(A.load_block(sid))
    out = []
    for m in msgs:
        txt = A.fold(m.jp)
        if len(txt) < 4:
            continue
        w = max(len(txt) * 3 // 2, len(txt) + 4)
        step = max(1, len(txt) // 4)
        best = (0.0, 0, 0)
        for s in range(0, max(1, len(rec) - len(txt) // 2), step):
            seg = rec[s : s + w]
            sm = difflib.SequenceMatcher(None, txt, seg, autojunk=False)
            n = sum(b.size for b in sm.get_matching_blocks())
            r = n / len(txt)
            if r > best[0]:
                blocks = [b for b in sm.get_matching_blocks() if b.size]
                best = (r, s + blocks[0].b, s + blocks[-1].b + blocks[-1].size - 1)
        r, a, b = best
        if r >= thr:
            out.append(
                {
                    "start": m.start,
                    "key": m.key,
                    "ratio": round(r, 2),
                    "t": [round(rc[a][1], 1), round(rc[min(b, len(rc) - 1)][1], 1)],
                    "pages": len([p for p in m.jp.split("\f") if p.strip()]) or 1,
                    "jp": m.jp.replace("\n", "").replace("\f", "¶")[:36],
                }
            )
    out.sort(key=lambda x: x["t"][0])
    return out


def main() -> int:
    sid, rel = int(sys.argv[1]), int(sys.argv[2])
    thr = float(sys.argv[sys.argv.index("--min") + 1]) if "--min" in sys.argv else 0.5
    rows = pick(sid, rel, thr)
    if "--json" in sys.argv:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    for r in rows:
        print(f"{r['t'][0]:6.1f}-{r['t'][1]:6.1f}  {r['ratio']:.2f}  A{0xA000 + r['start']:04X} {r['key']}  {r['pages']}쪽  {r['jp']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
