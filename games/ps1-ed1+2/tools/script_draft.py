#!/usr/bin/env python3
"""**번역 초안**을 뽑는다 — 배정 시대의 산출물을 정본 포맷으로 옮기는 다리.

**왜.** 방침이 「정발을 그대로 옮긴다」에서 「정발을 살리되 오역·개성 소실·어색함은
고친다」로 바뀌었고(2026-08-12, `docs/policy.md`), 구조도 배정(`chain`·`subs`)에서
**평탄한 문안 테이블**(`script/ED1SCN*.json`)로 간다. 5,029블록을 백지에서 쓸 수는 없으니
지금 화면에 나가는 문안을 초안으로 깔고 거기서 고쳐 나간다.

⚠ **초안은 커밋하지 않는다.** 아직 정발 문안이라 저작권 규칙에 걸린다 — `work/review/`
(gitignore) 에 떨어뜨리고, **사람이 고쳐 통과시킨 블록만** `script/` 로 올린다.
그래서 이 도구는 `script/` 에 직접 쓰지 않는다.

⚠ **개행을 담지 않는다.** 페이지 문자열은 조판(krwrap) 전이라 줄 나눔이 없고, 정본도
그대로 둔다 — 줄은 도구가 접는다. 강제로 끊고 싶을 때만 `{n}` 을 쓴다. 창 나눔은 `{p}`.

⚠ **정형 블록은 뺀다.** 보물상자·상점 가격·아이템 장비처럼 인자(`%s`)를 끼워 빌더가
만드는 블록은 문안이 아니라 서식이다(`inline` 자리가 있는 페이지로 가른다).

  python3 tools/script_draft.py                 # 전 씬 → work/review/draft_*.json
  python3 tools/script_draft.py ED1SCN1         # 한 씬
  python3 tools/script_draft.py --verify ED1SCN1  # 정본이 초안과 같은 바이트를 내는지
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R  # noqa: E402
from common import REVIEW_DIR  # noqa: E402
from patch_sys_ui import SCN_FILES  # noqa: E402


def draft(scn):
    """{블록: {"t":…, "s":…}} — 지금 화면에 나가는 문안을 정본 포맷으로."""
    out = {}
    for _s, eid, _jp, _cand, t in R.iter_candidates((scn,)):
        if not isinstance(t, tuple) or len(t) < 2:
            continue
        spk, pages = t[0], t[1]
        if any(p[0] for p in pages):  # 인자 주입 자리가 있으면 정형 블록 — 빌더 관할
            continue
        body = "{p}".join(p[1] for p in pages)
        if not body.strip():
            continue
        # ⚠ 꼬리 개행(`TRAIL_NL`)은 여기서 손대지 않는다. 문안에 `{n}` 으로 박아 봤더니
        # 조판기가 그 자리를 다시 접어 **불일치가 21 → 40 으로 늘었다**(2026-08-12).
        # 정본은 문장만 담고 줄 나눔은 도구에 맡긴다는 원칙이 여기서도 맞다.
        out[str(eid)] = {"t": body, **({"s": spk} if spk else {})}
    return out


def verify(scn):
    """초안을 정본으로 넣었을 때 **같은 바이트**가 나오는지 — 전환의 안전판.

    다르면 그 블록은 파이프라인이 정발 문안에만 맞춰 두었던 자리라, 옮기기 전에 원인을
    봐야 한다. 실측으로 셋이 나왔다 — 온점 보정 중복 · 창 앞 개행 소실 · `%s` 센티널 유실.
    """
    before = {}
    for _s, eid, _jp, cand, _t in R.iter_candidates((scn,)):
        before[eid] = R.render_bytes(cand)
    d = draft(scn)
    path = os.path.join(R.SCRIPT_DIR, f"{scn}.json")
    os.makedirs(R.SCRIPT_DIR, exist_ok=True)
    keep = open(path, encoding="utf-8").read() if os.path.exists(path) else None
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    try:
        R._SCRIPT_CACHE = None
        bad = []
        for _s, eid, _jp, cand, _t in R.iter_candidates((scn,)):
            if str(eid) in d and R.render_bytes(cand) != before.get(eid):
                bad.append(eid)
    finally:
        if keep is None:
            os.remove(path)
        else:
            open(path, "w", encoding="utf-8").write(keep)
    return d, bad


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    scenes = [s for s, _l, _z in SCN_FILES if not args or s in args]
    if "--verify" in sys.argv:
        for scn in scenes:
            d, bad = verify(scn)
            mark = "✅" if not bad else "⚠"
            tail = f" {bad[:8]}" if bad else ""
            print(f"  {mark} {scn}: {len(d)}블록 중 왕복 불일치 {len(bad)}건{tail}")
        return
    os.makedirs(REVIEW_DIR, exist_ok=True)
    for scn in scenes:
        d = draft(scn)
        p = os.path.join(REVIEW_DIR, f"draft_{scn}.json")
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  {scn}: {len(d)}블록 → {p}")
    print("\n⚠ 초안은 아직 정발 문안이다 — **커밋 금지**(work/review). 고쳐서 script/ 로 올린다.")


if __name__ == "__main__":
    main()
