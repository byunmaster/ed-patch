#!/usr/bin/env python3
"""**도구가 임포트조차 안 되는 상태**를 잡는다 — 한 달을 그렇게 있었다.

`gen_textmap` 과 `past_battle_jeongbal` 이 `derive_text.DOS_ED1` 을 임포트하는데, 그 상수는
ED2 착수(`f095d7a3`)로 원본이 게임별로 갈리면서 사라졌다. 둘 다 게이트·빌드가 안 부르는
도구라 **아무도 몰랐다**(2026-09-04 발견). 「검사기 자신의 커버리지」(patcher-checklist 5).

⚠ **깨진 참조만 실패로 친다** — `ImportError`·`AttributeError`·`NameError`.
`FileNotFoundError`·`SystemExit`·`IndexError` 는 **환경·CLI** 몫이라 통과시킨다:
`once_*` 는 임포트 시점에 원본을 읽고 `rewrite_*` 는 argv 를 기대한다. 그걸 실패로 치면
**원본을 안 링크한 워크트리에서 늘 빨간불**이 되고, 늘 빨간불인 검사는 아무도 안 본다.
"""

import contextlib
import importlib
import io
import os
import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
os.environ.setdefault("LOCK_BYPASS", "1")

BROKEN = (ImportError, AttributeError, NameError)


def test_every_tool_imports_without_broken_references():
    bad = []
    for p in sorted(TOOLS.glob("*.py")):
        try:
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                importlib.import_module(p.stem)
        except BROKEN as e:
            bad.append(f"{p.stem}: {type(e).__name__}: {e}")
        except Exception:  # noqa: BLE001, S110 — 환경·CLI 몫이라 **일부러 삼킨다**(위 도크스트링)
            pass
    assert not bad, "참조가 끊긴 도구:\n  " + "\n  ".join(bad)


if __name__ == "__main__":
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            v()
            print(f"  ok  {k}")
