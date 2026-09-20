#!/usr/bin/env python3
"""조판 지문 — 이 게임 몫 (`scripts/check/typeset_fingerprint.py` 가 부른다).

## 왜 이 파일이 게임 아래 있나

공용 도구는 「지문을 대조하고 얼린다」만 알고, **「이 게임의 화면 문안을 어떻게 만드나」**는
게임마다 다르다(루트 `CLAUDE.md` 「게임 얘기를 이 파일에 쓰지 않는다」).

🔴 **우리는 지금까지 이 지문이 없었다**(2026-09-15 — 아홉 중 이걸 든 건 둘뿐이라는 점검에서
드러났다). 그런데 `tools/typeset.py` 는 **`shared/text/krwrap.py` 를 직접 쓴다**
(`from shared.text import krwrap` → `typeset.wrap` 이 `krwrap.wrap` 을 그대로 부른다) — 같은
PS1 플랫폼이라 ps1-ed1+2 를 흔든 공용 변경(`c3ec16af`, 보조용언·속격 덩어리)이 **우리 이미지의
줄바꿈도 흔들 수 있다.** 아무것도 안 울리는 건 「안전하다」가 아니라 **장치가 없던 것**이었다.

## 무엇을 재나 — build.py 가 실제로 굽는 것 그대로

`build.py:reinsert_script` 는 `typeset.wrap(row["kr"], disc, jp=jp)` 를 그대로 화면에 쓴다
(⚠ `floor` 는 **안 넘긴다** — `floor` 는 `script.py --check`·`--review` 의 예산 판정에만 쓰이고,
실제로 이미지에 박히는 줄바꿈은 `jp` 만으로 정해진다). 지문도 똑같이 `jp=jp` 만 준다 — 그래야
**빌드가 실제로 쓰는 값**을 잰다(체크리스트 4-B: 검사기가 재는 자가 빌드가 쓰는 자와 달라지면
초록불이 거짓말한다).

- **대사** — `script.load(disc)` 의 전 조각을 `jp=원문` 으로 조판해 **아카이브!멤버** 단위로 묶는다.
- **UI** — `uitext.load(disc)` 의 전 항목을 조판해(창 폭 상한, `jp` 없이) 한 구역으로 묶는다.
  ⚠ UI 는 원문 폭을 floor 로 안 받는다(`uitext.apply` 확인) — 상한만 적용된다.

디스크(ed3·ed4)마다 구역을 가른다 — `ed3:...` · `ed4:...`.

⚠ **자리 배정(hangul_map)은 안 잰다** — 그건 빌드가 매번 다시 재고 게이트(`hangul_map --check`)가
따로 잡는다. 여기서 코드까지 재면 자리 하나만 밀려도 지문이 울어 아무도 안 보는 알림이 된다.
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import script as script_canon
import typeset
import uitext


def _h(parts):
    h = hashlib.sha1()
    for p in parts:
        h.update((p if isinstance(p, str) else repr(p)).encode())
        h.update(b"\x01")
    return h.hexdigest()[:12]


def fingerprint():
    """{구역: sha1} — `ed3:아카이브!멤버` · `ed3:ui` 등."""
    out = {}
    for disc in common.DISC_NAMES:
        for archive, member, segs in script_canon.members(disc):
            jp_by_idx = dict(segs)
            lines = script_canon.load(disc).get((archive, member))
            if not lines:
                continue
            parts = []
            for i, row in sorted(lines.items()):
                jp = jp_by_idx.get(i, "")
                wrapped = typeset.wrap(row["kr"], disc, jp=jp)
                parts.append(f"{i}\x00{wrapped}")
            region = f"{disc}:{archive}!{member}"
            out[region] = _h(parts)

        ui_parts = []
        for key, row in sorted(uitext.load(disc).items()):
            wrapped = typeset.wrap(row["kr"], disc)
            ui_parts.append(f"{key}\x00{wrapped}")
        if ui_parts:
            out[f"{disc}:ui"] = _h(ui_parts)
    return out


if __name__ == "__main__":
    import json

    print(json.dumps(fingerprint(), ensure_ascii=False, indent=1))
