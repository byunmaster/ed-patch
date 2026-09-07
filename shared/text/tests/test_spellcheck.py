#!/usr/bin/env python3
"""바깥 검사기가 막을 때 회차가 버티는지 — 청크 하나가 죽어도 나머지는 산다."""

import os
import sys
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from text import spellcheck as sc  # noqa: E402

_real_sleep = sc.time.sleep


def _fake(fail_on):
    """`fail_on` 에 든 원문은 HTTP 400 을 낸다."""

    def call(text, backend=None, tone="proof", retry=3, timeout=90):
        if text in fail_on:
            raise urllib.error.HTTPError("u", 400, "throttled", {}, None)
        return text.upper()

    return call


def test_400은_되풀이해도_되는_쪽이다():
    """🔴 이 백엔드는 400 을 「너무 빠르다」로 준다 — 「요청이 잘못됐다」가 아니다.

    ss-ed3 실측(2026-09-03): 같은 문장을 5초 간격으로 다섯 번 보내면 3회차부터 400.
    """
    assert 400 in sc._SOFT


def test_청크_하나가_죽어도_나머지는_산다(monkeypatch=None):
    """🔴 종전엔 `ex.map` 이 첫 예외에서 터져 **받은 것까지 통째로** 날아갔다."""
    orig, sc.call = sc.call, _fake({"나쁜 것"})
    try:
        cache = {}
        done, fail = sc.fetch([["좋은 것"], ["나쁜 것"], ["또 좋은 것"]], cache, jobs=1, gap=0)
    finally:
        sc.call = orig
    assert (done, fail) == (2, 1), (done, fail)
    assert cache == {"좋은 것": "좋은 것".upper(), "또 좋은 것": "또 좋은 것".upper()}


def test_캐시에_있는_것은_안_부른다():
    orig, sc.call = sc.call, _fake({"무엇이든"})  # 부르면 죽는다
    try:
        assert sc.fetch([["이미 있다"]], {"이미 있다": "값"}, jobs=1, gap=0) == (0, 0)
    finally:
        sc.call = orig


def test_fetch_slow_도_포기하고_다음으로_간다():
    # ⚠ 잠은 갈아 끼운다 — 이 함수는 일부러 수십 초를 쉬므로 실제로 자면 테스트가 못 쓴다.
    orig, sc.call = sc.call, _fake({"나쁜 것"})
    slept, sc.time.sleep = [], lambda t: slept.append(t)
    try:
        cache = {}
        done, gave = sc.fetch_slow(
            [["좋은 것"], ["나쁜 것"]], cache, delay=0.0, retry=1
        )
    finally:
        sc.call, sc.time.sleep = orig, _real_sleep
    assert (done, gave) == (1, 1), (done, gave)
    assert "좋은 것" in cache and "나쁜 것" not in cache
    # 막힌 뒤 간격이 늘어야 한다 — 그게 이 함수의 존재 이유다
    assert slept and max(slept) > min(slept), slept


# ⚠ 새 테스트는 이 줄 위에.
if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for f in fns:
        try:
            f()
        except Exception as e:  # noqa: BLE001
            bad += 1
            print(f"  FAIL {f.__name__}: {e}")
    print(f"{len(fns) - bad}/{len(fns)} passed")
    sys.exit(1 if bad else 0)
