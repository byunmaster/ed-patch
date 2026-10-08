"""이름 검사 어댑터 — `scripts/check/check_names.py --game ss-ed3` 에게 「원문 줄 · 우리 줄」 쌍을 낸다.

    python3 scripts/check/check_names.py --game ss-ed3 --list

🔴 **이 어댑터는 이름을 들지 않는다**(독자 데이터 금지, 마스터 10-07) — 원문과 문안을 읽어 넘길 뿐이고, 이름 표(사전 `shared/glossary/ed3.json`)와의 대조는
공용 `shared/glossary/names.py` 가 한다. 갈래(`dialog`/`slot`)는 대사 속 지명의 띄어쓰기를 볼지 가른다(마스터 10-07). 미번역 줄도 `None` 으로 낸다(분모가 거짓말을 안 하게).

낸 것(자리 = 맵 블록 `MAPnnn#블록` · 읽을거리 `BOOKnn#문단` · 시스템 `SYS:범주:원문`):
  ① 맵 대사 전량(`work/derived/map_jp` 의 원문 블록 ↔ `script/MAPnnn.json`) ② 읽을거리 문단(`sys_jp/SYSTEM_BOOKnn` 문단 ↔ `script/book/BOOKnn.json`)
  ③ 시스템 표(`script/system.json` — 키가 원문)
**안 낸 것**(보고서의 「안 본 구간」): 아이템·주문 설명문(`desc_*`) · 음성 자막(`voice.json`·`voice_credits.json`, 원문이 `work/review` 받아쓰기라 어댑터가 읽기엔 불안정) · 무비 자막 ·
전투 문구. 원문 열은 `work/derived/`(원문 덤프, 커밋 금지)에서 읽으므로 `dump_map.py`·`dump_sys.py` 를 먼저 돌려야 한다.
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

TITLE = "ed3"  # 작품 사전 — shared/glossary/ed3.json
CANON_GATE = False  # 정본 검사(check_canon)는 아직 숫자만 본다 — 인라인 아이템 코드 줄 5곳이 승인 안 된 예외 후보(`canon_exceptions.json`)라 조사 훅 뒤에 켠다


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _map_pairs():
    for jp_path in sorted(glob.glob(os.path.join(C.OUT_DIR, "map_jp", "MAP*.json"))):
        stem = os.path.basename(jp_path)[:-5]
        blocks = _load(jp_path)["blocks"]
        kr_path = os.path.join(C.GAME_DIR, "script", f"{stem}.json")
        kr = _load(kr_path) if os.path.exists(kr_path) else {}
        for i, b in enumerate(blocks):
            v = kr.get(str(i))
            #   갈래: 대사 머리는 `02xx`(화자) · `42xx` · `ff00`(나레이션) 뿐이다 — 그 밖(`00xx` 이름 칸·선택지 · 맵 이름 라벨의 임의 머리)은 비대사
            kind = "dialog" if b["head"][:2] in ("02", "42", "ff") else "slot"
            yield f"{stem}#{i}", b["text"], v if isinstance(v, str) else None, kind


def _book_pairs():
    import book as B  # 문단 복원은 책 도구가 정본이다

    for kr_path in sorted(glob.glob(os.path.join(C.GAME_DIR, "script", "book", "BOOK*.json"))):
        stem = os.path.basename(kr_path)[:-5]
        jp_path = os.path.join(C.OUT_DIR, "sys_jp", f"SYSTEM_{stem}.json")
        if not os.path.exists(jp_path):
            continue
        kr = _load(kr_path)
        par = B.paragraphs(_load(jp_path)["strings"])
        for i, (_, rows) in enumerate(par):
            v = kr.get(str(i))
            yield f"{stem}#{i}", B.join_text(rows), v if isinstance(v, str) else None, "dialog"


def _system_pairs():
    doc = _load(os.path.join(C.GAME_DIR, "script", "system.json"))
    for cat, tab in doc.items():
        if cat.startswith("_") or not isinstance(tab, dict):
            continue
        for jp, kr in tab.items():
            yield f"SYS:{cat}:{jp}", jp, kr if isinstance(kr, str) else None, "slot"


def pairs():
    """`(자리, 원문 줄, 우리 줄 | None, 갈래)` — 문안 전체. 갈래 = `dialog`(맵 대사·읽을거리 문단) · `slot`(시스템 표·이름 칸·선택지·맵 이름 라벨)."""
    yield from _map_pairs()
    yield from _book_pairs()
    yield from _system_pairs()
