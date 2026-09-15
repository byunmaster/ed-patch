#!/usr/bin/env python3
"""⚠ **게이트 밖 · 정발 배정 시대 진단기**(2026-09-13 실측 — 자체 번역 전환 이후 재검토
없이 남았다). 손으로 돌리는 용도로만 쓴다.

배정된 정발 문안이 **JP 원문과 크기가 맞는가** — 꼬리 잘림·오배정의 구조적 신호.

**왜.** 오배정은 **화면만 봐선 못 잡는다**(유저 지적 2026-08-11) — `세리오스 왕자 전하.
이번에는 정말로 감사했습니다` 는 병사 대사로 전혀 어색하지 않다. 그래서 사람이 두 게임을
나란히 놓고 대조하는 수밖에 없었는데, **글자 수 비**만으로도 상당수가 드러난다.

한국어는 일본어보다 대체로 조금 짧거나 비슷하다(가나가 음절을 늘린다). 그 비가 크게
벗어나면 둘 중 하나다:

- **꼬리 잘림** — 정발이 한 문장을 여러 엔트리로 갈라 뒀는데 앞부분만 물었다.
  `jp726` 은 `#30`+`#31`+`#32p0` 이 한 문장인데 `30` 만 물어 `…엄청나게 높으신` 에서
  끊겨 있었다(실측 2026-08-11).
- **오배정** — 아예 다른 대사를 물었다. `jp728` 은 위 꼬리 조각을 물고 있었다.

⚠ **문형(의문/평서) 대조는 버렸다.** SCN3 에서 76건이 떴는데 대부분 번역 관용 차이였다
(JP 평서 `酒でも 持っていってやらねーか` → `술이나 보내주도록 할까`). 길이 비는 같은 씬에서
6건만 뜨고 둘이 진짜였다 — **정밀도가 훨씬 높다.**

⚠ 문장 슬라이스(`chain: ["4#0.1"]`)는 원래 조각이라 짧다. 그 자체로는 결함이 아니니
**판정은 JP 원문을 읽고** 한다. 이 도구는 볼 자리를 좁혀 줄 뿐이다.

⚠ **`subs` 가 걸린 자리는 사람이 이미 손댄 배정이다** — 정발 이스터에그(불법 복제 경고)를
살리려고 문안을 줄인 `ED1SCN2 jp26` 이 크기 어긋남 ×2.08 로 뜬다. 고치면 **의도한 배정을
되돌리는 것**이다. 오버라이드의 `note` 를 먼저 읽는다.

  python3 tools/check_align_fit.py            # 전 씬
  python3 tools/check_align_fit.py ED1SCN3    # 한 씬
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R

HI, LO = 1.9, 0.55  # 이 밖이면 후보 — SCN3 실측에서 6/996 만 걸린다
MIN_JP, MIN_KR = 10, 8  # 짧은 블록은 비가 요동쳐 못 쓴다


def jp_text(b):
    """JP raw → 문자열(제어·인자 제거)."""
    out, i = [], 0
    while i < len(b):
        c = b[i]
        if c == 0x25 and i + 1 < len(b) and b[i + 1] in b"csd":
            i += 2
        elif c < 0x20:
            out.append(" ")
            i += 1
        elif c >= 0x81:
            out.append(b[i : i + 2].decode("cp932", "replace"))
            i += 2
        else:
            out.append(chr(c))
            i += 1
    return re.sub(r"\s+", " ", "".join(out)).strip()


def scan(scenes=None):
    tot = 0
    for scn, eid, jp, cand, _t in R.iter_candidates(scenes):
        j = re.sub(r"\s", "", jp_text(jp))
        kr = re.sub(r"\s+", " ", R.render_bytes(cand, ctrl=False))
        k = re.sub(r"\s", "", kr)
        if len(j) < MIN_JP or len(k) < MIN_KR:
            continue
        r = len(k) / len(j)
        if LO <= r <= HI:
            continue
        tot += 1
        print(f"  ⚠ {scn} jp{eid}  ×{r:.2f}")
        print(f"       JP {jp_text(jp)[:66]}")
        print(f"       KR {kr.strip()[:66]}")
    print(
        f"\n{'✅ 크기 어긋남 없음' if not tot else f'⚠ 크기 어긋남 {tot}건'}"
        "\n  ⚠ 어긋남이 곧 오배정은 아니다 — 문장 슬라이스는 원래 짧다."
        "\n     JP 원문을 읽고 판정한다(꼬리 잘림인지 · 다른 대사인지)."
    )
    return tot


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    sys.exit(1 if scan(tuple(args) if args else None) else 0)
