#!/usr/bin/env python3
"""**표기가 화면에서 갈리는가** — 편차 대장의 판정을 실제 문안으로 검사한다.

**왜.** 표기 통일은 [jeongbal-deviations.md](../docs/jeongbal-deviations.md) 가 정본인데
그건 **문서라 사람만 읽는다.** 정발이 같은 대상을 여러 표기로 쓰고(`젤만`/`제르만`),
우리가 시점 사본을 옮기다 다시 갈라 놓기도 한다(`안력마` 를 `마력 안` 으로 뒤집어 쓴 자리가
실측으로 있었다, 2026-08-12). **화면에 나가는 바이트로 세지 않으면 안 잡힌다.**

⚠ **비슷해 보여도 별개인 것이 있다.** `ワプの羽`(워프의 깃털) 와 `ワプの翼`(워프의 날개) 는
**효과가 다른 물건**이다 — 깃털은 직전 마을, 날개는 방문한 모든 마을로 간다(주문으로 치면
워프1·워프2, 유저 확인 2026-08-12). 그래서 이 도구는 **대상별로 쌍을 손으로 적는다** —
자동 유사도로 묶으면 그런 자리를 오탐으로 만든다.

⚠ **화자 이름은 다른 층이다.** 본문은 `PLACE_CANON`·`spell_fix` 를 지나지만 화자는
블록 헤더에서 와서 그 층을 **하나도 안 지난다** — 본문이 `라누라` 로 고쳐진 자리에서
이름창만 `라느라의 소녀` 로 남아 있었다(2026-08-12). 화자는 `align_overrides.json` 의
`_speakers` 또는 정본의 `s` 로 고친다.

  python3 tools/check_spellings.py
"""

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R  # noqa: E402
from patch_sys_ui import SCN_FILES  # noqa: E402

# (정본 표기, 쓰면 안 되는 표기 …) — 판정 근거는 편차 대장에 있다. 여기는 **검사기**다.
PAIRS = (
    ("안력마", "마력 안", "마력안"),  # 眼力魔 — 시점 사본에서 뒤집혀 있었다
    ("제르만", "젤만"),  # ジェルマン — 정발이 갈려 씀(유저 확정 2026-08-11)
    ("프레이아", "후레이아"),  # フレイア
    ("온리크", "웬리크", "폰리그"),  # ウォンリーク — ED1 정발이 가타카나를 오독했다
    ("랄파 요새", "랄파 성채"),  # ラルファの砦
    ("엘아스타", "엘아스터"),
    ("라누라", "라느라"),
    ("크루즈 마을", "크루즈의 마을"),
)


def scan():
    hit = collections.Counter()
    where = collections.defaultdict(list)
    for scn, _lba, _size in SCN_FILES:
        for _s, eid, _jp, cand, _t in R.iter_candidates((scn,)):
            kr = R.render_bytes(cand, ctrl=False)
            for row in PAIRS:
                for w in row:
                    if w in kr:
                        hit[w] += 1
                        if w != row[0]:
                            where[w].append(f"{scn} jp{eid}")
    bad = 0
    for row in PAIRS:
        wrong = [(w, hit[w]) for w in row[1:] if hit[w]]
        mark = "⚠" if wrong else ("✅" if hit[row[0]] else "  ")
        detail = " · ".join(f"{w} {n}" for w, n in wrong) or "-"
        print(f"  {mark} {row[0]}: {hit[row[0]]}곳   어긋남: {detail}")
        for w, _n in wrong:
            bad += 1
            print(f"        {w} → {' '.join(where[w][:6])}")
    print(
        f"\n{'✅ 표기 어긋남 없음' if not bad else f'⚠ 표기 어긋남 {bad}종'}"
        "\n  ⚠ 판정 근거는 docs/jeongbal-deviations.md 다 — 표기를 바꿀 때 그 문서에 함께 적는다."
    )
    return bad


if __name__ == "__main__":
    sys.exit(1 if scan() else 0)
