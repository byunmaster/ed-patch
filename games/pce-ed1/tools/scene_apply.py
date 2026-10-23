#!/usr/bin/env python3
"""씬 번역 반영 — `{열쇠: 문안}` JSON 을 검증한 뒤 `script/scnNNN.json` 에 합친다(이미 있는 열쇠는 `--replace` 때만 덮는다).

  python3 tools/scene_apply.py 19 work/review/tr19.json [--replace] [--dry]

검증(하나라도 걸리면 아무것도 안 쓴다): 열쇠가 원문 대조표에 있다 · 문안이 비지 않았다 · 가나·한자 없음(🔴 4-7 일본어 0) ·
우리 글리프로 그릴 수 있다 · 조판기가 글을 잃지 않는다 · 줄 위반(고아 부호·줄 첫 공백·낱말 가운데 끊김) 없음.
문안은 산문이다 — `\\f` = 강제 페이지, `\\n` 은 쓰지 않는다(조판기가 줄을 정한다).
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import font
import typeset
import typeset_check as T

JP = re.compile("[ぁ-ヺー-ヿ㐀-鿿ｦ-ﾟ]")
SCRIPT = common.GAME_DIR / "script"


def validate(n: int, new: dict[str, str]) -> list[str]:
    known = {m["key"]: m for m in json.loads((common.GAME_DIR / "work/derived/messages" / f"scn{n:03d}.json").read_text("utf-8"))}
    errs = []
    for k, t in new.items():
        if k not in known:
            errs.append(f"{k}: 원문 대조표에 없는 열쇠")
            continue
        if not isinstance(t, str) or not t.strip():
            errs.append(f"{k}: 빈 문안")
            continue
        if JP.search(t):
            errs.append(f"{k}: 일본어가 남았다 {JP.search(t).group()!r}")
        if "\n" in t and known[k]["speaker"] is not None:
            errs.append(f"{k}: 하드 개행 `\\n` 금지(조판기가 정한다)")
        try:
            src = font.expand_packed(t)
            for ch in set(src):
                if font.needs_glyph(ch):
                    font.glyph(ch)
            # 장 끝 카드(화자 없고 하드 개행이 든 문안)는 줄을 그대로 쓴다(`translate.compose` 의 verbatim) — 전각 공백으로 맞춘 줄이라
            # 조판기의 「낱말 가운데 끊김」(④)을 대지 않는다. 5장·종장 포함 여섯 장 카드가 이 오탐으로 걸렸다(10-18).
            verbatim = "\n" in t and known[k]["speaker"] is None and known[k]["common"] is None
            for pg in typeset.pages(src, speaker=known[k]["speaker"] is not None):
                for p in T.problems(pg, T.scene_cuts(src, pg)):
                    if verbatim and p.startswith("④"):
                        continue
                    if not p.startswith("②") and not (p.startswith("①") and len(pg) == 1):  # 한 줄짜리 침묵 창은 정상
                        errs.append(f"{k}: {p}")
        except Exception as e:  # noqa: BLE001 — 글리프 없음·조판 실패를 한 줄로 알린다
            errs.append(f"{k}: {type(e).__name__} {str(e)[:80]}")
    return errs


def main() -> int:
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    n, src = int(a[0]), Path(a[1])
    new = json.loads(src.read_text("utf-8"))
    if "--skip-unknown" in sys.argv:  # 여러 씬이 공유하는 열쇠 묶음(상점 문구 등)을 한 번에 넘길 때
        known = {m["key"] for m in json.loads((common.GAME_DIR / "work/derived/messages" / f"scn{n:03d}.json").read_text("utf-8"))}
        new = {k: v for k, v in new.items() if k in known}
    errs = validate(n, new)
    if errs:
        print("\n".join("  ✗ " + e for e in errs))
        print(f"반영 안 함 — 위반 {len(errs)}")
        return 1
    p = SCRIPT / f"scn{n:03d}.json"
    doc = (
        json.loads(p.read_text("utf-8"))
        if p.exists()
        else {"_doc": f"scn {n} 번역 정본 — 열쇠는 messages.py key, 원문 대조는 work/derived/messages/scn{n:03d}.json", "messages": {}}
    )
    msgs = doc["messages"]
    added = replaced = 0
    for k, t in new.items():
        if k in msgs and "--replace" not in sys.argv:
            continue
        added += k not in msgs
        replaced += k in msgs
        msgs[k] = {"t": t}
    if "--dry" not in sys.argv:
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"scn{n:03d}: 추가 {added} · 덮어씀 {replaced} · 건너뜀 {len(new) - added - replaced}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
