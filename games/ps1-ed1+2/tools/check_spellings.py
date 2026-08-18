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

import reinsert_kr_pilot as R
from check_align_fit import jp_text as _jp_text
from check_proper_nouns import _name_in
from patch_sys_ui import SCN_FILES

# (정본 표기, 쓰면 안 되는 표기 …) — 판정 근거는 편차 대장에 있다. 여기는 **검사기**다.
PAIRS = (
    ("안력마", "마력 안", "마력안"),  # 眼力魔 — 시점 사본에서 뒤집혀 있었다
    # ⚠ `ジェルマン` 은 **ED1·ED2 양쪽 다 내부가 갈렸다**(ED1 `젤만`/`제르만`, ED2 `제만`/
    # `젤만`). ED2 우선이 방침이지만 그 ED2 가 갈렸으니 타이브레이커인 원음으로 판정한다.
    # ⚠ ED2 의 `제만` 은 **쌍에 넣지 않는다** — 두 글자라 `복제만큼은` 같은 데 걸린다(실측).
    ("제르만", "젤만"),  # ジェルマン — 유저 확정 2026-08-11 · 재확인 2026-08-12
    ("프라토", "브라도"),  # フラート — ED1 `브라도` vs ED2 `프라토` → ED2 우선(유저 확정)
    ("프레이아", "후레이아", "후레이야", "프레이야"),  # フレイア
    ("온리크", "웬리크", "폰리그"),  # ウォンリーク — ED1 정발이 가타카나를 오독했다
    ("랄파 요새", "랄파 성채"),  # ラルファの砦
    ("엘아스타", "엘아스터"),
    ("라누라", "라느라"),
    # ⚠ 우리 문안 쪽 오표기다(정발 원문이 아니라 `battle_ed2.json` 의 `ours`). 그래서
    # `spell_fix` 가 안 잡았고, **ED2.EXE 국가명 표에 `파레인` 으로 구워졌다**
    # (2026-08-16 실측 — 전투 패치가 시스템 패치보다 나중이라 그쪽이 이긴다).
    ("파렌", "파레인"),  # ファーレーン
    ("크루즈 마을", "크루즈의 마을"),
    # ⚠ `リーゼル`(리젤) 과 `リシェール`(리셸) 은 **다른 지명**이다 — 정발이 리셸을
    # 리젤로 옮긴 자리가 있었다(SCN3 jp67 실측 2026-08-12). 쌍이 아니라 각자 센다.
    ("리셸", "리셀"),  # ⚠ `리셀` 은 ED2 표기다 — 이 자리는 원음이 가까운 ED1 을 쓴다(유저 확정)
    ("요르도", "욜드"),  # ヨルド — 한 씬 안에서 `욜드 항구` 로 갈려 있었다(SCN3 jp1138)
    # ⚠ 아래 둘은 **원음이 아니라 정발 표기**다 — 고유명사는 정발을 따른다(policy.md 표기 방침).
    ("아그니쟈", "아그니자"),  # アグニージャ — 유저 확정 2026-08-12
    ("아토스", "아도스"),  # アートス — ED1 정발 `아도스` vs ED2 `아토스` → ED2 우선(유저 확정)
    # ⚠ `銀の笛`(은의 피리) 와 `銀の筒`(은대롱) 은 **다른 물건**이다 — 전자가 정식 아이템명
    # (`patch_items.ITEM_NAMES` 가 정본), 후자는 고문서에 나오는 이름이다(유저 확정 2026-08-12).
    # 그래서 쌍이 아니라 **각자** 센다. `은의 피리` 를 `은피리` 로 붙여 쓰면 아이템명과 어긋난다.
    ("은의 피리", "은피리", "은 피리"),
    ("성 아랫마을", "지하 마을"),  # 城下町 — `城` 을 `地` 로 읽은 자리가 둘(SCN3 jp523·jp556)
)


# 원문 인명 → 우리 표기. **원문에 이름이 있는데 우리 문안에 없으면** 표기가 갈렸다는 뜻이다.
# ⚠ 조사 `로` 와 겹치는 `로우` 처럼 **본문 검색으로는 못 세는 이름**을 잡으려고 방향을
# 뒤집었다(전투 시스템에서 `ロー` 가 `로` 로 나가던 자리가 실제로 있었다 — 유저가 잡았다).
# 셋째 항목은 **제외할 낱말** — `ローブ`(로브, 옷) 는 인명이 아니다.
NAME_PAIRS = (
    ("ロー", "로우", ("ローブ",)),
    ("セリオス", "세리오스", ()),
    ("リュナン", "류난", ()),
    ("ゲイル", "게일", ()),
    ("ソニア", "소니아", ()),
    ("ジェルマン", "제르만", ()),
    ("フレイア", "프레이아", ()),
    ("アクダム", "아크담", ()),
)


def scan_names():
    """원문에 인명이 있는데 우리 문안에 그 표기가 없는 블록."""
    bad = 0
    for scn, _lba, _size in SCN_FILES:
        # ⚠ **블록 경계가 원문과 우리가 다르게 갈린다** — 이름이 원문에선 이 블록에 있는데
        # 우리 문안에선 **다음 블록**으로 넘어간 자리가 있다(`check_proper_nouns` 가 같은
        # 부류를 이미 그렇게 푼다). 한 블록만 보면 `아트라스!`·`병사` 같은 조각이 통째로
        # 오탐이 된다 — **다음 블록 문안까지 합쳐** 찾는다.
        blocks = [
            (eid, _jp_text(jp), R.render_bytes(cand, ctrl=False))
            for _s, eid, jp, cand, _t in R.iter_candidates((scn,))
        ]
        for bi, (eid, j, kr0) in enumerate(blocks):
            kr = kr0 + ("\n" + blocks[bi + 1][2] if bi + 1 < len(blocks) else "")
            cand = None  # (아래 출력은 이 블록 문안만 보여 준다)
            kr_show = kr0
            for name, ours, skip in NAME_PAIRS:
                # ⚠ **낱말 경계를 봐야 한다.** `ロー`(로우)가 `フローラ`(플로라) 안에
                # 걸려 「문안에 로우 없음」이 쏟아졌다(ED2 를 체인에 올린 2026-08-16).
                # `check_proper_nouns._name_in` 이 같은 부류를 이미 푼다 — 규칙을 빌린다.
                if not _name_in(j, name) or ours in kr:
                    continue
                if any(x in j for x in skip):
                    continue
                bad += 1
                print(f"      ⚠ {scn} jp{eid}  원문 [{name}] 인데 문안에 [{ours}] 없음")
                print(f"           {kr_show.splitlines()[0][:56] if kr_show else ''}")
    return bad


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
    # ⚠ **게이트는 표기 어긋남뿐이다.** 인명 축(`scan_names`)은 「원문에 이름이 있는데
    # 문안에 없다」라 옛 번역자의 의역(`ジェルマン` → `그분`)도 함께 걸린다 — 판정이
    # 필요한 **후보**지 실패가 아니다. 늘 빨간불이면 아무도 안 본다.
    bad = scan()
    print("\n  인명 표기 후보 — (게이트 아님, 판정용)")
    scan_names()
    sys.exit(1 if bad else 0)
