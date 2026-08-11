#!/usr/bin/env python3
"""화면에 **나가면 안 되는 바이트열**을 센다 — 마크업 유출·조사 병기 노출.

**왜.** 다른 검출기들은 「있어야 할 것이 있는가」(창 수·인자·일본어 잔존)를 보는데, 이건
**「없어야 할 것이 없는가」**를 본다. mcpads 패처의 `validate_translations` 가 *"a small set of
forbidden Korean strings must never appear"* 로 같은 자리를 지킨다(2026-08-11 흡수).

⚠ **반드시 바이트 층에서 본다.** 페이지 문자열에는 센티널(`\\ue000` 개행 마커 · `\\x1b` 수치
주입 · `은(는)` 병기)이 **정상적으로** 들어 있다 — 거기서 세면 98건이 나오는데 전부 오탐이다
(실측 2026-08-11). 인코딩을 지나 실제로 블록에 실리는 바이트만이 화면이다.

검사 항목:

- **마크업 유출**(`{n}`·`{p}`·`{spk}`) — 정발 마크업이 안 걷힌 채 나갔다
- **이스케이프 리터럴**(`\\xNN`) — 제어코드가 글자로 나갔다
- **조사 병기**(`(는)`·`(가)`) — ⚠ 이건 **전부 오류가 아니다**. 런타임 조사 훅이 표시 직전에
  줄이므로 대사 렌더러 위에서는 정상이다. 문제는 **훅이 안 타는 자리**다 — 상점 프롬프트에서
  실제로 새어 나왔고(2026-07-27 유저 QA `해독초은 (는)`), 그래서 종류를 갈라 보고한다.

  python3 tools/check_forbidden.py         # 요약
  python3 tools/check_forbidden.py -v      # 자리마다
"""

import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map  # noqa: E402
import reinsert_kr_pilot as R  # noqa: E402


def _josa_re():
    """`(는)`·`(가)` 를 게임 인코딩 바이트로 — 병기는 이 두 꼴만 쓴다."""
    alt = b"|".join(re.escape(hangul_map.syllable_sjis(c).to_bytes(2, "big")) for c in ("는", "가"))
    return re.compile(rb"\((?:" + alt + rb")\)")


BAN = {
    "마크업 유출": re.compile(rb"\{(n|p|/?spk)\}"),
    "이스케이프 리터럴": re.compile(rb"\\x[0-9A-Fa-f]{2}"),
}


def scan(verbose=False):
    josa = _josa_re()
    bad = collections.defaultdict(list)
    kinds = collections.Counter()
    n = 0
    for name, eid, _jp, cand, t in R.iter_candidates():
        n += 1
        for k, rx in BAN.items():
            if m := rx.search(cand):
                bad[k].append((name, eid, m.group(0)))
        if josa.search(cand):
            stock = isinstance(t, tuple) and t and t[0] == "__stock__"
            kinds["정형 블록(훅 대상 — 정상)" if stock else "대사(훅 확인 필요)"] += 1
            if not stock:
                bad["조사 병기 — 대사"].append(
                    (name, eid, R.render_bytes(cand, ctrl=False)[:48].replace("\n", " "))
                )
    print(f"화면 바이트 검사 — 재삽입 블록 {n}개")
    for k in BAN:
        v = bad.get(k, [])
        print(f"  {'⚠' if v else '✅'} {k:<16} {len(v)}건")
        for nm, e, g in v[: (None if verbose else 3)]:
            print(f"        {nm} jp{e}: {g!r}")
    print(f"  · 조사 병기 방출 {sum(kinds.values())}건 — {dict(kinds)}")
    for nm, e, g in bad.get("조사 병기 — 대사", [])[: (None if verbose else 6)]:
        print(f"        {nm} jp{e}: {g!r}")
    print(
        "\n⚠ 조사 병기는 **훅이 타면 정상**이다 — 정형 블록은 1·2장 QA 로 확인됐다."
        "\n  대사 쪽은 인게임에서 병기가 그대로 보이는지 확인할 것(상점 프롬프트에서 실제로 샜다)."
    )
    return sum(len(v) for k, v in bad.items() if k in BAN)


if __name__ == "__main__":
    sys.exit(1 if scan("-v" in sys.argv) else 0)
