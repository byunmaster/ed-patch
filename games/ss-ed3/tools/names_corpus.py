"""이름 검사 어댑터 — `scripts/check/check_names.py --game ss-ed3` 에게 「원문 줄 · 우리 줄」 쌍을 낸다.

    python3 scripts/check/check_names.py --game ss-ed3 --list

🔴 **이 어댑터는 이름을 들지 않는다**(독자 데이터 금지, 마스터 10-07) — 원문과 문안을 읽어 넘길 뿐이고, 이름 표(사전 `shared/canon/nouns/ed3.json`)와의 대조는
공용 `shared/canon/names.py` 가 한다. 갈래(`dialog`/`slot`)는 대사 속 지명의 띄어쓰기를 볼지 가른다(마스터 10-07). 미번역 줄도 `None` 으로 낸다(분모가 거짓말을 안 하게).

낸 것(자리 = 맵 블록 `MAPnnn#블록` · 읽을거리 `BOOKnn#문단` · 시스템 `SYS:범주:원문`):
  ① 맵 대사 전량(`work/derived/map_jp` 의 원문 블록 ↔ `script/MAPnnn.json`) ② 읽을거리 문단(`sys_jp/SYSTEM_BOOKnn` 문단 ↔ `script/book/BOOKnn.json`)
  ③ 시스템 표(`system_src.sections()` — 정본·사전에서 읽은 값, 키가 원문)
  ④ `PARAM.BIN` 이름 표(아이템·적·마법 — 자리 `PARAM:<범주>:<원문>`, 우리 줄은 사전에서 읽는다. **사전에 없으면 None** — 일본어가 남는 길이다)
  ⑤ `PARAM.BIN` 설명문(`desc_item.json`·`desc_spell.json`, 색인 = `param.descs` 순번) ⑥ HP 창 이름판(`reinsert_battle` — 파티 14명)
**안 낸 것**(보고서의 「안 본 구간」): 음성 자막(`voice.json`·`voice_credits.json`)·무비 자막(`movie.json`) — 원문이 `work/review` 받아쓰기(커밋 금지)라 어댑터가 읽기엔 불안정하다 ·
책 표지(그림, `covers.json`) · 화면 그림(`reinsert_gfx`). 원문 열은 `work/derived/`(원문 덤프, 커밋 금지)에서 읽으므로 `dump_map.py`·`dump_sys.py` 를 먼저 돌려야 한다.
"""

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

TITLE = "ed3"  # 작품 사전 — shared/canon/nouns/ed3.json
CANON_GATE = True  # 정본 검사 상주 — 어긋남(승인 예외 제외)이 있으면 실패한다(10-08 사전 적용 2단계)


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


_CTL = re.compile(r"[\x00-\x09\x0b\x0c\x0e-\x1f]")  # \r\n 은 남긴다(공백류로 벗겨진다)


def _system_pairs():
    import system_src as SYS

    for cat, tab in SYS.sections().items():
        for jp, kr in tab.items():
            #   🔴 엔진 종결·제어 바이트(`\x0f \x10 \x00 \x0e\x07`)를 줄에서 뗀다 — 정본의 줄 전체 대조(`^…$`)는 공백류만 벗겨서,
            #     제어 바이트가 붙은 줄 30/74 를 못 쟀다(md 실측 10-08: 정본 검사가 전투·시스템 문구를 하나도 못 쟀다)
            yield f"SYS:{cat}:{jp}", _CTL.sub("", jp), _CTL.sub("", kr) if isinstance(kr, str) else None, "slot"


#   개발자 시험용 이름 — 영문 자리표시·「零號」는 화면에 나가지 않는다(마법 표 앞쪽과 `Item…`·`…Special` 자리)
_DEV_NAMES = ("僕は魔法の零號さ",)


def _param_pairs():
    import glossary_src as GS
    import param as P
    import reinsert_param as RP

    tbl = GS.table()
    b = P.load()
    for label, area in RP.AREAS:
        for jp in P.names(b, area):
            if jp.isascii() or jp in _DEV_NAMES:
                continue
            kr = tbl.get(jp)
            yield f"PARAM:{label}:{jp}", jp, kr if isinstance(kr, str) else None, "slot"
    for key, area in (("desc_item", P.DESC_ITEM), ("desc_spell", P.DESC_SPELL)):
        kr = _load(os.path.join(C.GAME_DIR, "script", f"{key}.json"))
        for i, jp in enumerate(P.descs(b, area)):
            if i == 0:  # 0 번은 화면 자료(한자 숫자표)·더미 — 번역하지 않는다
                continue
            v = kr.get(str(i))
            yield f"PARAM:{key}#{i}", jp.replace("＄", "\n"), v if isinstance(v, str) else None, "dialog"


def _plate_pairs():
    import glossary_src as GS
    import reinsert_battle as RBT

    jps = RBT._PARTY_JP
    for jp, kr in zip(jps, GS.party(*jps)):
        yield f"BATTLE:plate:{jp}", jp, kr if isinstance(kr, str) else None, "slot"


def pairs():
    """`(자리, 원문 줄, 우리 줄 | None, 갈래)` — 문안 전체. 갈래 = `dialog`(맵 대사·읽을거리 문단) · `slot`(시스템 표·이름 칸·선택지·맵 이름 라벨)."""
    yield from _map_pairs()
    yield from _book_pairs()
    yield from _system_pairs()
    yield from _param_pairs()
    yield from _plate_pairs()
