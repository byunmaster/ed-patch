"""화면 일본어 0 — 메뉴·시스템·전투·HUD·배너(대사가 아닌 모든 자리)에 일본어가 남지 않았나(F7).

`names_corpus.pairs()`(이름 검사와 같은 문안 전체)에서 **씬 대사(`scnNNN`)가 아닌** 항목을 본다.
- 우리 줄(ours)에 가나·한자가 있으면 실패 — 번역하다 만 글.
- 우리 줄이 없는(None) 항목의 원문에 가나·한자가 있으면 실패 — 원문이 그대로 화면에 뜬다.
  (영문 전각 `ＯＮ` 같은 비일본어·빈 칸은 가나·한자가 아니라 통과.)
씬 대사의 미번역: 일본어가 든 줄은 **정적 근거 목록**(`script/broken_fragments.json` — 대본이 아니라 6502 기계어·주소 표를 잘못
줍은 조각)에 있으면 경고로 세고 통과, **목록 밖이면 실패**다(마스터 10-11). 글이 없는 빈 메시지는 센 줄에만 든다.
가운뎃점 `・`(U+30FB)은 부호라 가나로 안 센다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import names_corpus

DEFERRED = ("dex:",)  # 미착수 출처(도감) — 숫자만 알린다. 번역이 들어가면 접두어를 뺀다
JP = re.compile("[ぁ-ヺー-ヿ㐀-鿿ｦ-ﾟ]")


FRAGMENTS = Path(__file__).resolve().parents[1] / "script" / "broken_fragments.json"


def known_fragments() -> dict[str, str]:
    return json.loads(FRAGMENTS.read_text("utf-8"))["fragments"] if FRAGMENTS.exists() else {}


def main() -> int:
    bad, scene_left, total, deferred = [], 0, 0, 0
    known = known_fragments()
    warned: set[str] = set()
    for where, jp, ours, *_ in names_corpus.pairs():
        if where.startswith("scn"):
            if ours is not None:
                continue
            if not JP.search(jp):
                scene_left += 1  # 글 없는 메시지(화자 이름만 · 줄바꿈만)
            elif where in known:
                warned.add(where)
            else:
                bad.append((where, "미번역(원문이 뜬다 · 깨진 조각 목록에도 없다)", jp))
            continue
        if where.startswith(DEFERRED):
            deferred += ours is None
            continue
        total += 1
        if ours is not None and JP.search(ours):
            bad.append((where, "우리 줄에 일본어", ours))
        elif ours is None and JP.search(jp):
            bad.append((where, "미번역(원문이 뜬다)", jp))
    print(
        f"화면 일본어 검사 — 대사 외 {total}줄 · 어긋남 {len(bad)} · (씬: 글 없는 메시지 {scene_left}줄 · "
        f"⚠ 깨진 조각 경고 {len(warned)}줄(정적 근거 목록 {len(known)}) · 도감 미착수 {deferred}줄)"
    )
    stale = sorted(set(known) - warned)
    if stale:
        print(f"  ℹ 목록에 있으나 이제 안 나오는 조각 {len(stale)}건 — 정리해라: {stale[:3]}…")
    for w, why, s in bad[:20]:
        print(f"  ✗ {w}  {why}: {s[:30]!r}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
