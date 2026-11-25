#!/usr/bin/env python3
"""조판 지문 — 이 게임 몫 (`scripts/check/typeset_fingerprint.py` 가 부른다).

`tools/typeset.py` 는 `shared/text/krwrap.py` 를 그대로 쓴다 — 공용 줄바꿈이 바뀌면 이 게임 이미지의 줄도
조용히 바뀐다(10-28 krwrap 보강: 28줄). 락·관측 대장은 조판을 안 보므로 이 지문이 그 구멍을 메운다.

## 무엇을 재나 — 빌드가 실제로 굽는 것 그대로
`script_kr.edits` 가 낸 **조판된 코드열**(줄바꿈·쪽 나눔이 이미 들어간 조각, 24,474개)을 멤버(`아카이브!멤버`)마다 sha1 로 묶는다 —
빌드가 `reinsert.edits_for` 로 이미지에 쓰는 바로 그 값이다.
⚠ UI 낱말은 안 잰다(줄바꿈이 없고 자리 배정은 `hangul_map --check` 몫).
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common


def fingerprint():
    """{`아카이브!멤버`: sha1} — 조판된 대본 조각 전량."""
    common.verify_source()
    import build
    import hangul
    import script_kr

    per, notes = script_kr.edits(build.identity_gate({}), table=hangul.load())
    if notes:
        raise SystemExit("🔴 조판 지문: 못 넣은 쪽이 있다 — " + "; ".join(notes[:3]))
    out = {}
    for (archive, member), segs in sorted(per.items()):
        h = hashlib.sha1()
        for i in sorted(segs):
            h.update(f"{i}\x00".encode())
            h.update(repr(list(segs[i])).encode())
            h.update(b"\x01")
        out[f"{archive}!{member}"] = h.hexdigest()[:12]
    return out
