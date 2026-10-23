"""이름 검사 어댑터가 이어진 문장(블록 둘 이상)을 한 줄로 내는지 — 합성 행으로 못 박는다."""

import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import names_corpus as N


def test_open_blocks_join_into_one_line():
    rows = [
        (10, "AAA その力を", "그 힘을", "dialog"),
        (11, "手に入れる。", "손에 넣는다.", "dialog"),
        (12, "BBB。", "다음 문장.", "dialog"),
    ]
    got = list(N._chain_pairs("ED1SCN9", rows))
    assert got == [("ED1SCN9:10~11", "AAA その力を手に入れる。", "그 힘을 손에 넣는다.", "dialog")]


def test_closed_blocks_do_not_join():
    rows = [(1, "終わり。", "끝났다.", "dialog"), (2, "次。", "다음.", "dialog")]
    assert list(N._chain_pairs("ED1SCN9", rows)) == []


def test_gap_in_ids_breaks_chain():
    rows = [(1, "途中で", "중간에", "dialog"), (5, "続く。", "이어진다.", "dialog")]
    assert list(N._chain_pairs("ED1SCN9", rows)) == []


def test_untranslated_block_breaks_chain():
    rows = [(1, "途中で", None, "dialog"), (2, "続く。", "이어진다.", "dialog")]
    assert list(N._chain_pairs("ED1SCN9", rows)) == []


if __name__ == "__main__":
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            v()
            print(f"  ok  {k}")
