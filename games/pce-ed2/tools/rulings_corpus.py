"""마스터 판정 문안 잠금의 말뭉치 어댑터 — 공용 판정기(`scripts/check/master_rulings.py`)가 부른다.

읽는 것은 정본 텍스트가 아니라 **게이트용 trim 이미지에 구운 바이트를 디코드한 한글 줄**이다(`pairs.py` — 대사 덩이 `rel:메시지:줄` ·
본 프로그램 문자열 `S…` · 표 `T…`). 같은 덩이를 가리키는 메시지 번호(`a=b`)는 각자 한 행으로 편다.
글은 줄바꿈·쪽 넘김 표지를 공백 하나씩으로 바꾼 꼴이고 제어 표지 `{…}` 는 남긴다(`master_rulings.json` 이 그 꼴로 적혀 있다).
갈래: 대사 덩이 = "script", 본 프로그램 문자열·표 = "ui".
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
import pairs


def iso_path() -> Path:
    """게이트가 굽는 trim 이미지 — 칸 이름 규칙은 `build.py` 와 같다(`test-<꼬리표>-trim`)."""
    tag = common.BUILD_TAG
    if not tag.startswith("test-"):
        tag = "test-" + tag
    return common.BUILD_DIR / f"{tag}-trim" / f"{common.ROM_STEM}.iso"


def plain(s: str) -> str:
    """줄바꿈(`↵`)·쪽 넘김(`⏎`) 덩어리(`⏎↵` 처럼 이어진 것 포함)를 공백 하나로 — 판정의 `has`·`is` 가 이 꼴로 적혀 있다.
    쪽 가름이 원판 창 경계로 옮겨져도(2-17) 같은 문장이 같은 글로 읽힌다."""
    return re.sub(r"[↵⏎]+", " ", s)


def corpus() -> list[tuple[str, str, str]]:
    iso = str(iso_path())
    kg = pairs.KoGlyphs(iso)
    out: list[tuple[str, str, str]] = []
    for fn, cat in ((pairs.package_rows, "script"), (pairs.literal_rows, "ui"), (pairs.table_rows, "ui")):
        for key, _o, k, _sh in fn(iso, kg):
            if fn is pairs.package_rows:
                rel, ms, line = key.split(":")
                for m in ms.split("="):
                    out.append((f"{rel}:{m}:{line}", cat, plain(k)))
            else:
                out.append((key, cat, plain(k)))
    return out
