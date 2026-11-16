"""화자 호칭 정본(`shared/canon/ed4.json` speaker) ↔ 대본 대조 게이트.

제 줄을 통째로 차지한 화자 조각(원문이 정본 열쇠와 같은 줄)은 우리 줄이 정본 값과 같아야 한다. 값은 정본에서만 읽는다(자기 표 금지).
원본 이미지가 없는 머신에선 「안 쟀다」로 알리고 통과한다(`check_names` 와 같은 처리).
"""

import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "shared"))
import canon
import names_corpus


def main():
    table = canon.table("speaker", "ed4")
    seen, bad = collections.Counter(), []
    for where, jp, kr, _ in names_corpus.pairs() or ():
        want = table.get(jp.strip())
        if want is None:
            continue
        seen[jp.strip()] += 1
        if kr != want:
            bad.append((where, jp.strip(), want, kr))
    if not seen:
        print("  ⚠ 화자 조각을 하나도 못 쟀다(원본 이미지 없음?)")
        return 0
    print("  화자 정본 대조:", ", ".join(f"{k}={v}줄" for k, v in seen.items()))
    for where, jp, want, kr in bad:
        print(f"   🔴 {where} 「{jp}」 정본 「{want}」 ≠ 우리 「{kr}」")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
