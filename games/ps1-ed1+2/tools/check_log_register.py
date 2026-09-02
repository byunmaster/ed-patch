#!/usr/bin/env python3
"""**시스템·행동 로그의 문체**를 부류 단위로 지킨다 — 원문은 이 부류에서 정중이다.

**왜(2026-09-03).** 유저가 빛의 검 창 다섯을 인게임에서 보고 「끼워 넣었다는 정중이
아니네?」로 잡았다. 같은 순간에 뜨는 넷(`받았습니다`·`완성되었습니다`·`넣었습니다`)과
하나만 어긋나 있었다. 원인은 문안이 아니라 **판정을 블록 단위로 한 것**이다 —
원문을 한 블록씩 보면 흔들려 보이는데, **부류로 묶어 세면 규칙이 있다.**

    보물상자 부류   원문 정중 44 · 평서 0   (「평서 6」은 NPC 대사와 `ませんでした`
                                             오분류였다 — 08-31 의 97:11 은 오염된 값)
    획득·건넴 안내  원문 정중 117 · 평서 2  (둘 다 NPC 대사가 걸린 오탐)
    이름 색(참고)   대사 1,012 색 · 로그 117 무색 (무색 117 중 113이 이 부류)

⇒ **부류를 원문에서 읽으면 「원문 충실」과 「일관성」이 대립하지 않는다.** 이 검사기는
그 부류가 다시 흐르는 걸 막는다 — 이 축은 이미 08-29↔09-01 로 한 번 진동했다.

부류는 추측이 아니라 **데이터에 있는 것**으로 가른다 — 런타임 주입 표지(`\\x1a` 이름 ·
`\\x17` 아이템)를 쓰는 블록이 곧 시스템·행동 로그다(화자 이름표가 없다).

⚠ **ED2 는 보고만 한다.** 아직 정발 유래 문안이라 통째로 재작성 대기이고(`docs/status`),
지금 고칠 수 없는 걸 실패로 치면 게이트가 늘 빨간불이 된다.

⚠ 원문이 이 부류에서 평서인 예외 셋(`ED1SCN3:1120` · `ED1SCN4:741·749`)은 **부류 다수에
맞춰 정중으로 올렸다**(유저 확정 2026-09-03). 원문을 따르는 규칙에서 물러선 유일한 자리라
블록 주석에 근거를 남겼다.

  python3 tools/check_log_register.py          # ED1 실패 · ED2 보고
  python3 tools/check_log_register.py --ed2    # ED2 목록까지
"""

import json
import re
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "script"
INJECT = ("\x1a", "\x17")  # 런타임 주입 표지 = 시스템·행동 로그
POLITE = re.compile(r"(습니다|십시오|세요|십니다|습니까)[.!?…]?$")
PLAIN = re.compile(r"(었다|았다|했다|였다|된다|한다|이다)[.!?…]?$")


def scan(track):
    bad, total = [], 0
    for p in sorted(SCRIPT.glob(f"{track}SCN*.json")):
        for k, v in json.loads(p.read_text(encoding="utf-8")).items():
            if not isinstance(v, dict):
                continue
            t = v.get("t") or ""
            if not any(m in t for m in INJECT):
                continue
            total += 1
            tail = t.rstrip().rstrip("}pn{").rstrip()
            if PLAIN.search(tail) and not POLITE.search(tail):
                bad.append((p.stem, k, t[:60]))
    return total, bad


def main():
    t1, bad1 = scan("ED1")
    t2, bad2 = scan("ED2")
    if bad1:
        print(
            f"  ❌ ED1 로그 부류 {t1}블록 중 {len(bad1)}곳이 해라체 — 원문은 이 부류에서 정중이다"
        )
        for s, k, t in bad1:
            print(f"       {s}:{k}  {t!r}")
    else:
        print(f"  ✅ 로그 부류 문체 고름 — ED1 {t1}블록 전부 정중")
    if bad2:
        print(f"     ℹ ED2 {t2}블록 중 {len(bad2)}곳 해라체 — 정발 유래라 재작성 때 같이 («할 일»)")
        if "--ed2" in sys.argv:
            for s, k, t in bad2:
                print(f"       {s}:{k}  {t!r}")
    return 1 if bad1 else 0


if __name__ == "__main__":
    sys.exit(main())
