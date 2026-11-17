"""공용 이름·정본 검사 어댑터 — **ED4 문안 전체**를 `(자리, 원문 줄, 우리 줄|None, 갈래)` 로 낸다.

    python3 scripts/check/check_names.py --game ps1-ed4 --list

🔴 이름을 안 든다(마스터 10-07) — 정본은 `shared/canon`(고유명사 `nouns/ed4.json`), 여기는 **원문을 읽어 우리 줄과 짝짓기만** 한다.
우리 줄은 커밋된 번역 정본(`script/*.json` — `script_kr.load_all`)에서 채운다. 번역이 없는 조각은 `None`(분모에만 든다).
🔴 11-05 이전엔 모든 조각이 `None` 이라 이름·정본 검사가 **0줄을 재고도 초록**이었다(0.1.0 준비에서 발견).

⚠ 원본 이미지가 있어야 돈다(없으면 빈 목록 — 「안 쟀다」는 `check_names` 가 분모 0 으로 드러낸다).
🔴 안 보는 구간: 그림 속 글(오프닝·엔딩·크레딧·로고) · 실행파일 낱말/UI 표.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import dump
import script_kr
import textenc
import uitext

from shared.ps1 import gmf_script as scriptmap

TITLE = "ed4"  # 작품 정본 — shared/canon/nouns/ed4.json
DIALOG = "dialog"
SLOT = "slot"


def pairs():
    if not os.path.exists(common.orig_bin()):
        return
    kr_all = script_kr.load_all()
    for path, nm, data, off, sz in dump.script_members():
        kr_rows = kr_all.get((path, nm), {})
        info = scriptmap.parse(data[off : off + sz])
        key = f"{path.strip('/').replace('/', '_')}!{os.path.basename(nm.replace(chr(92), '/'))}"
        for i, (_, codes) in enumerate(info["segments"]):
            jp = textenc.decode(codes)
            if jp.strip():
                yield f"scn:{key}[{i}]", jp, kr_rows.get(i, {}).get("kr"), DIALOG
    # 실행파일 속 UI·시스템·전투·메뉴 글(고정 칸 문안) — `uitext.sites` 가 원문을, `rows_for` 가 우리 줄(정본 이름 + 우리가 쓴 문안)을 준다
    exe = bytes(common.read_file(common.EXE_PATH))
    ss = uitext.sites(exe)
    kr_ui = uitext.rows_for(ss)
    for off, s in sorted(ss.items()):
        if s["jp"].strip():
            yield f"ui:0x{off:06X}", s["jp"], kr_ui.get(off, {}).get("kr"), SLOT
    for off, v in sorted(uitext.frags().items()):  # 표에 안 잡히는 조각 — 원문 열쇠(canon)가 있는 것만 원문을 안다
        if v.get("canon"):
            yield f"frag:0x{off:06X}", v["canon"], v.get("kr"), SLOT
