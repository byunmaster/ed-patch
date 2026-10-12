"""공용 이름 검사 어댑터(`scripts/check/check_names.py`) — md-ed2 **착수 단계 최소판**.

`pairs()` = `[(자리, 원문 줄, 우리 줄 또는 None, 갈래)]`. 아직 번역이 없어 우리 줄은 전부 None 이다
(분모에만 든다). 대본 씬 모듈 356의 문안 스트림만 낸다 — 전투·시스템 메시지·표는 파이프라인이 서면
ED1 어댑터(`games/md-ed1/tools/names_corpus.py`)를 따라 더한다. 이름을 들지 않는다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import scene

CANON = "ed2"
CANON_GATE = False  # 번역 전 — 정본 어긋남을 실패로 치지 않는다(전환 시 켠다)
CANON_SKIP = r"^script:"
DIALOG = "dialog"


def pairs():
    out = []
    for blk, k, b in archives.modules(common.rom()):
        mod = scene.parse_module(b)
        for off in sorted(mod.streams):
            st = mod.streams[off]
            src = "".join(t.raw.decode("cp932", "replace") for t in st.tokens if t.kind == "text")
            if src:
                out.append((f"script:{blk}.{k}@{off:#x}", src, None, DIALOG))
    return out


if __name__ == "__main__":
    p = pairs()
    print(f"  names_corpus — 문안 스트림 {len(p)} (전부 미번역)")
