#!/usr/bin/env python3
"""`mednafen.cfg` 의 설정 줄을 **정본 값으로 되돌린다** — 키·영상 공용 기전.

왜 필요한가 — mednafen 은 **종료할 때 cfg 를 통째로 다시 쓴다.** 그래서 켜 둔 채 고친 값도,
게임 안 메뉴에서 한 번 건드린 값도 다음 실행에 되살아나거나 날아간다. 판단(어떤 값이
정본인가)을 커밋되는 파일에 두고 **실행 직전에** 되돌리는 게 이 레포의 답이다.

소비자가 둘이라 여기로 뺐다(레포 원칙: 둘째 소비자가 실재할 때 추상화한다) —
`mednafen_keys.py`(키 배치) · `mednafen_video.py`(영상 규격). 둘 다 하는 일은 같다:
「이름 → 값」 사전을 주면 없는 줄은 알리고, 다른 줄만 고치고, 몇 개를 고쳤는지 돌려준다.

⚠ 줄을 **새로 만들지 않는다.** 없다는 건 대개 설정 이름이 바뀐 것이라, 조용히 덧붙이면
  틀린 이름이 cfg 에 쌓이고 mednafen 은 그걸 「unknown setting」으로 무시한다 —
  아무도 모르는 채 안 듣는 설정이 된다. 그래서 없으면 **말한다**.
"""

import os
import pathlib
import re


def cfg_path() -> pathlib.Path:
    base = os.environ.get("MEDNAFEN_HOME") or (pathlib.Path.home() / ".mednafen")
    return pathlib.Path(base) / "mednafen.cfg"


def apply(text: str, settings: dict, *, verbose: bool = False):
    """`settings` 를 cfg 본문에 반영한 결과를 돌려준다.

    반환: (새 본문, 바꿈, 이미 맞음, 없음). `verbose` 면 바뀌는 줄을 찍는다(--check).
    """
    changed = same = missing = 0
    for name, value in settings.items():
        want = f"{name} {value}"
        m = re.search(rf"^{re.escape(name)} .*$", text, re.M)
        if not m:
            print(f"⚠ 설정이 없다: {name}")
            missing += 1
        elif m.group(0) == want:
            same += 1
        else:
            if verbose:
                print(f"  {name}: {m.group(0)[len(name) + 1 :]} → {value}")
            else:
                text = text[: m.start()] + want + text[m.end() :]
            changed += 1
    return text, changed, same, missing


def run(settings: dict, *, label: str, check: bool = False, quiet: bool = False) -> int:
    """cfg 를 읽어 반영하고 결과를 한 줄로 알린다. 스크립트 둘의 `main()` 이 이걸 부른다."""
    p = cfg_path()
    if not p.exists():
        print(f"⛔ cfg 가 없다: {p} — mednafen 을 한 번 실행하면 생긴다")
        return 1

    text, changed, same, missing = apply(p.read_text(), settings, verbose=check)
    if check:
        print(f"\n맞음 {same} · 다름 {changed} · 없음 {missing}")
        return 0
    if changed:
        p.write_text(text)
    # ⚠ 조용히 되돌리지 않는다 — 일부러 바꿔 둔 걸 덮었을 수도 있으니 **덮었으면 말한다.**
    #   바뀐 게 없으면 --quiet 로 입을 다문다(매 실행 붙는 줄이라 시끄럽다).
    if changed or not quiet:
        print(
            f"{label}: 바꿈 {changed} · 이미 맞음 {same}"
            + (f" · 없음 {missing}" if missing else "")
        )
    return 0
