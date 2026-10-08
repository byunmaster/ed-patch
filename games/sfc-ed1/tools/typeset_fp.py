"""sfc-ed1 조판 지문 — `scripts/check/typeset_fingerprint.py` 가 부르는 게임별 구현.

번역된 화면 문안 전량을 **빌드와 같은 조판기**(`typeset.wrap` 어절 개행 → `layout` 흘리기, 후보 조합 전부)에
태워 구역별(시스템(필드) · 전투·시스템 · 씬) 해시를 낸다. 값에 줄바꿈(`typeset` 열)과 위반 수가 들어가므로
조판 규칙·사전 후보·글꼴 폭이 바뀌면 운다. 가변 폭이 정본이라(2026-10-08 마스터 판정) 켜진 모드로 동결돼 있다 — 지문은 켜진 모드만 잰다.
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import typeset


def fingerprint() -> dict[str, str]:
    hs: dict[str, hashlib._Hash] = {}
    for r in sorted(typeset.check_all(typeset=True), key=lambda r: r["addr"]):
        h = hs.setdefault(r["region"], hashlib.sha1())
        h.update(f"{r['id']}\x00{r['typeset']}\x00{r['combos']}\x00{r['bad']}\x00{r['hard']}\x02".encode())
    return {k: h.hexdigest()[:12] for k, h in sorted(hs.items())}


if __name__ == "__main__":
    print(fingerprint())
