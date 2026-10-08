#!/usr/bin/env python3
"""저작권 게이트의 잣대 — 가짜 문장으로 잰다(원문을 테스트에 옮기지 않는다)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import check_copyright as C


def test_long_japanese_run_is_caught():
    fake = "アイウエオカキクケコ、サシスセソタチツテトナニヌネノ。"  # copyright:ok 가짜 — 가나 25자
    assert len(C.runs(fake)) == 1


def test_short_labels_and_korean_pass():
    assert C.runs("道具 · 魔法 · 装備\n이건 우리 말이다 — 얼마든지 길어도 된다.") == []


def test_marker_skips_char_tables():
    assert C.runs("アイウエオカキクケコサシスセソタチツテトナニヌネノ  # copyright:ok 문자표") == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for f in fns:
        f()
    print(f"{len(fns)}/{len(fns)} passed")
