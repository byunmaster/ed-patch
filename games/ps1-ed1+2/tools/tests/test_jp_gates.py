"""잔존 일본어 게이트가 **알려진(번역된) 구간 옆의 짧은 일본어**를 놓치지 않는가(합성 데이터).

sfc-ed2 가 「일본어 런이 번역된 구간과 겹치기만 하면 통과」라는 구멍을 찾았다(10-18). 우리 게이트는
겹침 판정이 아니지만, 같은 부류의 구멍이 없다는 걸 합성 입력으로 못 박는다.
"""

import os
import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map as H


def _hangul(s):
    return b"".join(H.encode_kr(c) for c in s)


def test_exe_kana_run_before_translated_segment_is_caught():
    from check_exe_kana_left import kana_runs

    # 번역된 한글 슬롯 앞에 일본어(가나 셋)가 붙은 문자열 — 겹침 판정이면 통과하던 꼴
    buf = b"\x00" + "ですよ".encode("cp932") + _hangul("용사") + b"\x00"
    assert kana_runs(buf), "번역 구간 앞의 가나가 안 걸렸다"


def test_exe_kana_short_two_kana_sentence_is_caught():
    from check_exe_kana_left import kana_runs

    buf = b"\x00" + "です".encode("cp932") + b"\x00"
    assert kana_runs(buf), "가나 두 자짜리 문장이 안 걸렸다"


def test_exe_pure_hangul_is_clean():
    from check_exe_kana_left import kana_runs

    assert not kana_runs(b"\x00" + _hangul("용사가 나타났다") + b"\x00")


def test_mon_dialog_with_newline_is_caught_by_gate_mode():
    from patch_ed2_monster_lines import is_dialog

    s = "は倒れた。\n"
    assert not is_dialog(s)  # 계획 경로는 옛 동작 그대로
    assert is_dialog(s, allow_nl=True), "줄바꿈 든 일본어 대사가 게이트에 안 걸린다"


def test_mon_short_three_char_sentence_is_caught():
    from patch_ed2_monster_lines import is_dialog

    assert is_dialog("ですよ", allow_nl=True)
    assert is_dialog("倒れた", allow_nl=True)


def test_ptr_target_outside_unit_spans_is_caught():
    from check_ptr_target_coverage import outside_spans

    spans = [(0x100, 0x140), (0x140, 0x180)]
    assert outside_spans([0x100, 0x13F, 0x17F], spans) == []
    # 번역 단위 구간 밖(0x1A0)을 가리키는 포인터 — 합성 데이터가 실패해야 한다
    assert outside_spans([0x100, 0x1A0], spans) == [0x1A0]


if __name__ == "__main__":
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            v()
            print(f"  ok  {k}")
