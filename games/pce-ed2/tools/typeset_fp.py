"""pce-ed2 조판 지문 — `scripts/check/typeset_fingerprint.py` 가 부르는 게임별 구현.

롬에 굽는 조판 결과를 구역별 sha1 로 낸다. 대사·틀 줄은 빌드와 같은 조판기(`typeset.pages` — 공용 krwrap 위에 얹혀 있다)에
태우고(`check_linebreak.measure` 와 같은 순회: § 절 · \\f 쪽 구간), 음성 자막은 두 모듈의 `build_pages` 가 낸 쪽(줄·시각)을 해시한다.
구역 = 대사 패키지(rel) 하나씩 + 제어 틀 + 오프닝 자막 + 엔딩 자막. 공용이 줄바꿈을 흔들면 해당 구역 값이 바뀐다.
"""

import hashlib
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_punct
import typeset


def _sub_zone(mod) -> str:
    h = hashlib.sha1()
    pages = mod.build_pages()
    for pg in pages[0] if isinstance(pages, tuple) else pages:
        h.update(f"{round(pg['t0'], 3)}\x00{round(pg['t1'], 3)}\x00{pg.get('y0')}\x00".encode())
        h.update(("\x01".join(pg["lines"]) + "\x02").encode())
    return h.hexdigest()[:12]


def fingerprint() -> dict[str, str]:
    typeset._ensure_phrases()
    hs: dict[str, "hashlib._Hash"] = defaultdict(hashlib.sha1)
    for where, kind, t, _dots in check_punct.corpus():
        if kind == "sub":
            continue
        zone = f"dlg:{where.split(':')[0]}" if kind == "dlg" else "tmpl"
        h = hs[zone]
        for si, seg in enumerate(t.split("§")):
            for ci, ch in enumerate(seg.split("\f")):
                h.update(f"{where}\x00{si}.{ci}\x00".encode())
                for pg in typeset.pages(ch, headed=check_punct.headed(where, si, ci)):
                    h.update(("\x01".join(pg) + "\x02").encode())
    out = {z: h.hexdigest()[:12] for z, h in sorted(hs.items())}
    import ending_sub
    import opening_sub

    out["sub:opening"] = _sub_zone(opening_sub)
    out["sub:ending"] = _sub_zone(ending_sub)
    return out


if __name__ == "__main__":
    fp = fingerprint()
    print(len(fp), "구역")
