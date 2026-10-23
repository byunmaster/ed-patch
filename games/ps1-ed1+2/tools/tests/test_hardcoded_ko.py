"""check_hardcoded_ko — 굳은 한글 문안 검출(AST)과 상점 가격 프롬프트 줄 가져오기를 못 박는다."""

import pathlib
import sys
import tempfile

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import check_hardcoded_ko as G
import reinsert_kr_pilot as R


def test_literal_in_encoder_call_is_found():
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "patch_x.py"
        p.write_text('x = encode_ext("괜찮으시겠습니까?")\ny = encode_ext(name)\nz = print("로그")\n', encoding="utf-8")
        got = G.hardcoded_literals(str(p))
    assert [(ln, lit) for ln, _n, lit in got] == [(1, "괜찮으시겠습니까?")]


def test_allowlist_has_no_sentence():
    # 허용 목록은 조사 조각·이름 한 낱말·셀프테스트뿐 — 가게 말투가 갈릴 수 있는 종결 문장은 없다
    assert not [lit for _f, lit in G.ALLOWED if lit.endswith(("?", "다.", "요."))
                and lit != "야, 안녕하세요."]


def test_shop_price_lines_follow_script_and_split_on_n():
    lines = R.shop_price_lines("\ue003값은{n}\x1b Gold가 되는뎁쇼{n}그래도 괜찮겠수?")
    assert lines == [" 값은", "\x1b Gold가 되는뎁쇼", "그래도 괜찮겠수?"]


def test_shop_price_two_line_script_has_no_third_line():
    b = R.shop_price_build(b"", "\ue003값은{n}\x1b Gold가 되는데?")
    assert b.count(b"\x0a") == 2 and b.endswith(b"\x0a" + R.MC)  # 줄 사이 1 + 끝 1 — 3째 줄(고정 문구)이 없다


def test_shop_price_fallback_only_without_script():
    assert R.shop_price_lines(None)[-1] == "괜찮으시겠습니까?"
    assert R.shop_price_lines("a{n}b{n}c")[-1] == "c"


if __name__ == "__main__":
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            v()
            print(f"  ok  {k}")
