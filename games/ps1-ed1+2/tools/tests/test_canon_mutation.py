"""정본 검사가 **눈멀지 않았는가** — 돌연변이 시험(관리자 10-08: md 는 줄 끝 제어 태그 때문에 정본 검사가 전투·시스템 문구를
하나도 못 쟀는데 어긋남 0 으로 초록이었다).

정본 문구 하나의 우리 줄을 일부러 틀리게 바꿨을 때 `canon.audit` 이 **실패해야** 한다. 두 층으로 본다:
① 합성 — 어댑터의 줄 정리(`_jp`·`_ours`)를 거친 제어 태그 붙은 줄이 정본 대조에 걸리는가(원본 없이 돈다)
② 실제 어댑터 — 원본이 있으면 `_battle_ed1_pairs()`·`_battle_ed2_pairs()` 가 낸 줄에서 같은 돌연변이를 건다.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.dirname(_HERE)
sys.path.insert(0, _TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(_TOOLS)), "..", "shared"))
os.environ.setdefault("LOCK_BYPASS", "1")

import canon
import names_corpus as N


def _measured_battle(title):
    """정본 검사가 실제로 재는 정본 battle 문구 하나 — (열쇠, 값). 이름 자리로 시작하는 조각(「は戦いに…」)은
    앞에 이름이 있어야 재므로 맨 줄로는 안 걸린다 — 맨 줄로 걸리는 것만 고른다."""
    for k, v in canon.table("battle", title).items():
        if "{" in k or "@" in k or len(k) < 8 or "{" in v:
            continue
        if canon.audit([("T:1", k, v, "dialog")], title).hits:
            return k, v
    raise AssertionError("재는 문구가 하나도 없다")


def _mutate(kr):
    # 마지막 글자를 다른 글자로 — 정본 값과 안 맞게 한다
    return kr[:-1] + ("뷁" if kr[-1] != "뷁" else "뷂")


def test_synthetic_tagged_lines_are_measured():
    for title in ("ed1", "ed2"):
        k, v = _measured_battle(title)
        # 엔진이 줄 끝에 붙이는 제어(`%c`·개행)를 어댑터 정리(`_jp`·`_ours`)에 통과시킨다
        good = [("T:1", N._jp(k + "\n%c"), N._ours(v + "\n%c"), "dialog")]
        r = canon.audit(good, title)
        assert r.hits and not r.mismatches, f"{title}: 정상 줄이 안 재졌다 {r.hits[:1]}"
        bad = [("T:1", N._jp(k + "\n%c"), N._ours(_mutate(v) + "\n%c"), "dialog")]
        r = canon.audit(bad, title)
        assert r.mismatches, f"{title}: 틀린 줄을 못 잡았다 — 정본 검사가 눈멀었다(제어 태그?)"


def test_real_adapter_lines_are_measured():
    from common import ORIG_BIN

    if not os.path.exists(ORIG_BIN):
        return  # 원본 없는 머신 — 합성 시험만
    for title, gen in (("ed1", N._battle_ed1_pairs), ("ed2", N._battle_ed2_pairs)):
        pairs = [p for p in gen() if p[2] is not None]
        base = canon.audit(pairs, title)
        assert len(base.hits) >= 20, f"{title}: 정본 문안 출현 {len(base.hits)} — 실제보다 너무 적다(눈멂 의심)"
        assert not base.mismatches, f"{title}: 기준이 이미 빨갛다 {base.mismatches[:1]}"
        hit_where = {h.where for h in base.hits}
        # 맞은 줄 하나의 우리 줄을 틀리게 바꾼다
        idx = next(i for i, p in enumerate(pairs) if p[0] in hit_where and p[2].strip())
        w, jp, kr, kind = pairs[idx]
        mutated = list(pairs)
        mutated[idx] = (w, jp, _mutate(kr), kind)
        r = canon.audit(mutated, title)
        assert any(h.where == w for h in r.mismatches), f"{title}: {w} 돌연변이를 못 잡았다"


if __name__ == "__main__":
    test_synthetic_tagged_lines_are_measured()
    test_real_adapter_lines_are_measured()
    print("ok")
