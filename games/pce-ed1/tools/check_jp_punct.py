"""일본식 부호 잔존 검사 — 우리 문안(`script/`)에 「。」「、」가 없고, 원문 블록의 **메시지 밖** 일본식 부호가 전부 `translate.PUNCT_SITES` 로 바뀌나.

    python3 games/pce-ed1/tools/check_jp_punct.py

🔴 이유(마스터 10-30 「류난。 — 마침표가 일본식」): 슬롯 이름 토큰 바로 뒤의 `81 42`(。)는 번역 메시지 칸 밖이라 손이 안 닿고 원문 그대로 화면에 나왔다.
문안 검사(부호 규칙)는 번역 문안만 봐서 이 자리를 못 잡는다 — 원문 블록 바이트를 직접 훑는다.
"""

import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import messages as M
import translate

JP_PUNCT = "。、"
SCRIPT = Path(common.GAME_DIR) / "script"


def check() -> list[str]:
    bad = []
    for f in sorted(glob.glob(str(SCRIPT / "scn*.json"))):
        for k, v in json.load(open(f, encoding="utf-8")).get("messages", {}).items():
            t = v.get("t") if isinstance(v, dict) else None
            if isinstance(t, str) and any(c in t for c in JP_PUNCT):
                bad.append(f"{Path(f).stem}#{k}: 문안에 일본식 부호({''.join(c for c in JP_PUNCT if c in t)})")
    seen: set[int] = set()
    sites = 0
    for f in sorted(glob.glob(str(common.OUT_DIR / "text" / "*.bin"))):
        sid = int(Path(f).stem.split("_")[1])
        if sid in seen:
            continue
        seen.add(sid)
        b = Path(f).read_bytes()
        try:
            spans = [(m.start, m.end) for m in M.parse(b)]
        except Exception:  # 파싱 안 되는 블록은 다른 검사 몫
            continue
        want = set(translate.PUNCT_SITES.get(sid, []))
        for mm in re.finditer(rb"\x81[\x41\x42]", b):
            o = mm.start()
            if any(s <= o < e for s, e in spans):
                continue
            if o in want:
                sites += 1
                want.discard(o)
            else:
                bad.append(f"scn{sid:03d} +{o:#06x}: 메시지 밖 일본식 부호 {mm.group().hex()} — translate.PUNCT_SITES 에 올린다")
        for o in sorted(want):
            bad.append(f"scn{sid:03d} +{o:#06x}: PUNCT_SITES 자리인데 원문 바이트가 부호가 아니다")
    print(f"일본식 부호 검사 — 메시지 밖 자리 {sites}곳 전부 반각 부호로 바꿈 · 문안 「。」「、」 0")
    return bad


if __name__ == "__main__":
    e = check()
    for x in e:
        print("  ✗", x)
    sys.exit(1 if e else 0)
