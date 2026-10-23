"""구운 글리프 동일 비트맵 게이트(check_glyph_pairs)의 묶음 계산을 합성 표로 못 박는다."""

import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import check_glyph_pairs as G


def test_groups_finds_identical_bitmaps_only():
    t = {b"\x01\x02": ["a"], b"\x03\x04": ["b", "c"]}
    t[b"\x01\x02"].append("d")
    gs = G.groups(t)
    assert gs == [("a", "d"), ("b", "c")]


def test_groups_ignores_unique():
    assert G.groups({b"\x01": ["a"], b"\x02": ["b"]}) == []


if __name__ == "__main__":
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            v()
            print(f"  ok  {k}")
