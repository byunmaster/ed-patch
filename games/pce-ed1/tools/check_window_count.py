#!/usr/bin/env python3
"""우리 창 수 < 원문 창 수 — 번역이 원문 두 창을 한 창에 합친 곳을 센다(번역 규칙 2-17: 원문 창 구조를 줄이지 않는다, 마스터 11-05).

기존 게이트는 「우리 > 원문」(원문 한 창이 둘로 갈린 것 — `fit_one_scan`)만 셌다. 이 검사는 반대쪽이다.
원문 창 수 = 메시지 토큰의 쪽 넘김(`05`·`03`) 수 + 1 (마지막 글자 뒤의 쪽 넘김·옵코드·종료는 안 센다). 우리 창 수 = `translate` 가 쓰는 것과 같은 입력(앞 공백만 뗀 문안)을
`typeset.pages` 로 짠 쪽 수 — 끝 `\\f` 는 빈 쪽 하나로 센다(다음 메시지로 이어지는 조각의 창 구조, 인터프리터가 그 쪽 옵코드를 낸다).
양성 대조: 합친 문안(쪽 나눔을 지운 것)이 실제로 걸리고 원문 구조대로 나눈 것은 안 걸리는지 먼저 돈다 — 검출기가 죽어서 0 이 나오는 것을 막는다.

    python3 games/pce-ed1/tools/check_window_count.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import font
import messages as M
import typeset

PAGE_OPS = (0x05, 0x03)
SHORT_OK: dict[tuple[int, str], str] = {}  # (씬, 열쇠) → 사유 — 정말 못 맞추는 자리만(판정 대기)


def orig_windows(m) -> int:
    """글자가 하나라도 뒤따르는 쪽 넘김만 센다 — 끝의 쪽 넘김·색 되돌림(`04`)·다음 색 켜기(`1D`)·종료는 창이 아니다."""
    toks = list(m.tokens)
    last = max((i for i, t in enumerate(toks) if isinstance(t, str)), default=-1)
    return 1 + sum(1 for t in toks[:last] if isinstance(t, tuple) and t[0] == "op" and t[1] in PAGE_OPS)


def our_windows(t: str, sid: int, speaker) -> int:
    typeset.set_scene(sid)
    return len(typeset.pages(font.expand_packed(t.lstrip(" ")), speaker=speaker, four=True, keep_windows=typeset.keep_windows(sid)))


def scan() -> tuple[int, list[tuple[int, str, int, int, str]]]:
    n, bad = 0, []
    for p in sorted(common.OUT_DIR.glob("text/*.bin")):
        tail = p.stem.split("_")[-1]
        if not tail.isdigit():
            continue
        sid = int(tail)
        try:
            trs = M.load_translations(sid)
        except Exception:
            continue
        for m in M.parse(p.read_bytes()):
            tr = trs.get(m.key)
            if not tr or tr.get("raw") or not tr.get("t"):
                continue
            n += 1
            ow, ours = orig_windows(m), our_windows(tr["t"], sid, M.speaker_kind(m, sid))
            if ours < ow and (sid, m.key) not in SHORT_OK:
                bad.append((sid, m.key, ow, ours, tr["t"]))
    return n, bad


def positive_control() -> None:
    """합친 문안은 걸리고 원문대로 나눈 문안은 안 걸린다 — 실제 메시지(원문 두 창)로 확인."""
    for p in sorted(common.OUT_DIR.glob("text/*.bin")):
        tail = p.stem.split("_")[-1]
        if not tail.isdigit():
            continue
        sid = int(tail)
        for m in M.parse(p.read_bytes()):
            if orig_windows(m) != 2 or m.speaker is None:
                continue
            sp = M.speaker_kind(m, sid)
            two = "첫 번째 말입니다.\f두 번째 말입니다."
            one = "첫 번째 말입니다. 두 번째 말입니다."
            if our_windows(two, sid, sp) == 2 and our_windows(one, sid, sp) == 1:
                return
    raise SystemExit("양성 대조 실패 — 원문 두 창 메시지에서 합친 문안이 1창으로 안 나온다(검출기 점검)")


if __name__ == "__main__":
    positive_control()
    n, bad = scan()
    print(f"창 수 「적음」 검사 — 번역 {n}개 · 우리 < 원문 {len(bad)} · 예외 {len(SHORT_OK)} (양성 대조 통과)")
    for sid, k, ow, ours, t in bad:
        print(f"  ✗ scn{sid:03d} {k}: 원문 {ow}창 → 우리 {ours}창 — 쪽 나눔(\\f)을 원문 창대로 ({t[:30]!r})")
    sys.exit(1 if bad else 0)
