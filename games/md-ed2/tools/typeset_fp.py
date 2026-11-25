"""md-ed2 조판 지문 — `scripts/check/typeset_fingerprint.py` 가 부르는 게임별 구현.

이 게임에서 줄바꿈이 **공용 krwrap** 을 타는 자리는 `build.typeset()`(→ `layout.wrap_pages` = krwrap + 2-16 다듬기
`fix_clauses`·`fix_phrases`…)이다. 공용이 줄바꿈 알고리즘을 바꾸면 이미지가 조용히 달라지는데 락·관측 대장은 조판을 안 보므로,
**실제 롬에 굽는 조판**을 덩이별로 다시 태워 해시한다.

덩이 목록은 빌드가 남긴 `work/build/<꼬리표>/layout_metrics.json` 의 호출 기록(원문 · 앞 공백 · 앞 폭 · 정본 열쇠)이다 —
그 입력을 **지금의 코드**(공용 krwrap + 게임 layout.py)로 다시 `build.typeset()` 에 태우므로, 기록의 조판 결과가 아니라
지금 코드의 조판 결과가 값이다. 문안이 바뀌면 호출 기록이 바뀌어 값도 바뀐다(문안 작업 중에는 `--freeze` 로 갱신).
빌드가 먼저 돌아야 한다(`check.sh` 가 빌드 뒤에 부른다). 기록이 없으면 조용히 통과하지 않고 멈춘다.

구역 = 대본 블록 번호(`BBB`). 같은 호출이 반복돼도 기록 순서대로 이어 해시한다.
"""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build
import common
import layout


def fingerprint() -> dict[str, str]:
    p = common.BUILD_DIR / common.BUILD_TAG.replace("/", "_") / "layout_metrics.json"
    if not p.exists():
        raise SystemExit(f"조판 지문: 호출 기록이 없다({p}) — 빌드를 먼저 돌린다")
    calls = json.loads(p.read_text(encoding="utf-8"))["pages"]
    hs: dict[str, hashlib._Hash] = {}
    for raw, lead, pw, _pages, ctx in calls:
        zone = ctx.split("-", 1)[0] or "?"
        h = hs.setdefault(zone, hashlib.sha1())
        h.update(f"{ctx}\x00".encode())
        for pg in build.typeset(raw, lead, pw):
            h.update(("\x01".join(pg) + "\x02").encode())
    layout.CALLS.clear()  # 다시 태우며 쌓인 기록은 버린다
    return {z: h.hexdigest()[:12] for z, h in sorted(hs.items())}


if __name__ == "__main__":
    print(json.dumps(fingerprint(), ensure_ascii=False, indent=1))
