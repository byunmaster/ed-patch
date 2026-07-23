"""josa 단위 테스트. 실행: `.venv/bin/python shared/text/tests/test_josa.py`"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from text.josa import attach, batchim, josa  # noqa: E402


def test_batchim():
    assert batchim("칼") == 8 and batchim("검") == 16 and batchim("가") == 0 and batchim("A") is None


def test_basic_pairs():
    assert attach("세리오스", "은/는") == "세리오스는"
    assert attach("검", "은/는") == "검은"
    assert attach("세리오스", "이/가") == "세리오스가"
    assert attach("슬라임", "이/가") == "슬라임이"
    assert attach("나이프", "을/를") == "나이프를"
    assert attach("검", "을/를") == "검을"
    assert attach("소니아", "과/와") == "소니아와"
    assert attach("게일", "과/와") == "게일과"


def test_euro_rieul_exception():
    assert attach("칼", "으로/로") == "칼로"  # ㄹ 받침 → 로
    assert attach("손", "으로/로") == "손으로"
    assert attach("배", "으로/로") == "배로"


def test_non_hangul_fallback():
    assert josa("Gold", "은/는") == "은(는)"
    assert josa("EP", "이/가") == "이(가)"
    assert josa("", "은/는") == "은(는)"


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
            print(f"  ok  {fn.__name__}")
        except AssertionError as e:
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")
    return passed == len(fns)


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
