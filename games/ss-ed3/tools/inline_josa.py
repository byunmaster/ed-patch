"""인라인 아이템 코드(`<01><번호>`) 뒤 병기 조사를 **빌드 때** 하나로 줄인다.

🔴 이 코드의 번호는 **PARAM 아이템 표 색인 그대로**다(`0x87`=金貨 — 38 곳 전부 확인). 아이템 이름은 우리가 PARAM 에
굽는 값이라 **빌드 때 이미 정해져 있다** — 종전엔 「이름이 런타임에 꽂히니 조사를 못 고른다」고 보고 조사를 피해 썼다
(`쥬리오는 <아이템> 샀습니다`). `%s` 와 달리 이쪽은 **런타임 훅이 필요 없다**: 문안에 `<01><19>을(를)` 로 쓰면
(정본 system·battle 「{item}을(를) 샀다」와 같은 꼴) `reinsert.load_script`/`patch_blocks` 가 이름의 마지막 소리로 하나를 고른다.

숫자 끝은 **읽는 소리대로**(마스터 09-26): 0 영·1 일·3 삼·6 육·7 칠·8 팔 은 받침이 있고 2·4·5·9 는 없다.
⚠ 받침을 못 정하는 끝(영문·기호)은 병기를 그대로 둔다 — 틀린 조사보다 병기가 안전하다.
"""

import functools
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "shared")
)
import glossary_src as GS
import param as P
from text.josa import PAIRS, batchim

_PAIR_OF = {f"{a}({b})": key for key, (a, b) in PAIRS.items() if key in ("은/는", "이/가", "을/를", "과/와", "으로/로")}
_RE = re.compile(r"(<01><([0-9A-Fa-f]{2})>)(" + "|".join(re.escape(k) for k in _PAIR_OF) + ")")
_DIGIT_BATCHIM = set("013678")  # 영 일 삼 육 칠 팔


@functools.lru_cache(maxsize=1)
def item_names():
    """`{색인: 우리 표기}` — PARAM 아이템 표의 JP 이름을 공용 사전으로 옮긴다(사전에 없으면 빠진다)."""
    recs = P.records(P.load(), P.ITEM)
    kr = GS.table()
    return {i: kr[jp] for i, jp in enumerate(recs) if jp and jp in kr}


def _pick(name, pair):
    a, b = PAIRS[pair]
    tail = name.rstrip()[-1:]
    if tail.isdigit():
        f = 1 if tail in _DIGIT_BATCHIM else 0
    else:
        f = batchim(tail)
        if f is None:
            return None
    if pair == "으로/로" and f == 8:
        return b
    return a if f else b


def resolve(text):
    """`<01><xx>을(를)` → `<01><xx>를` — 이름을 못 찾거나 받침을 못 정하면 그대로 둔다."""
    if "<01>" not in text:
        return text
    names = item_names()

    def sub(m):
        name = names.get(int(m.group(2), 16))
        picked = _pick(name, _PAIR_OF[m.group(3)]) if name else None
        return m.group(1) + (picked if picked else m.group(3))

    return _RE.sub(sub, text)
