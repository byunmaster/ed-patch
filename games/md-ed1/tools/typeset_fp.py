"""md-ed1 조판 지문 — `scripts/check/typeset_fingerprint.py` 가 부르는 게임별 구현.

이 게임에서 **자동 줄바꿈**(`shared/text/krwrap.wrap_pages`)을 타는 자리는 대사 스트림
(`script/*.json` → `tools/build.py:typeset()`) **하나뿐**이다 — 실측: `battle.py`·`tables.py`·
`sysmsg.py`·`captions.py` 는 krwrap 을 안 쓴다(고정 폭 raw · 자막은 번역자가 `\\n` 을 직접 박고
렌더러 칸 규칙 `captions.cells` 로 검증만 한다). 그래서 `shared/` 가
줄바꿈 **알고리즘**을 바꿔도 조용히 화면을 바꿀 수 있는 자리는 대사뿐이고, 여기만 잰다.

`build.py` 의 `build_stream()` 과 같은 방식으로 `ours` 를 조각내(`textmap.parse_ours`) 제어
태그 사이 텍스트만 모아 `typeset()`(=krwrap.wrap_pages)에 태운다 — 실제 재삽입과 같은
경로를 태워야 조판 변화를 놓치지 않는다. `raw: true` 항목은 조판기를 안 타므로(build.py 의
`raw_text` 분기와 동일) 원문 그대로 해시한다.

구역 = **블록 번호**(`script/NNN.json` 하나당 하나) — 지금은 9블록뿐이라도 P4 로 늘면 그대로
따라온다(파일을 훑으므로 목록을 손으로 안 든다).
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build
import textmap


def _pages_hash(ours: str) -> str:
    h = hashlib.sha1()
    pending: list[str] = []

    def flush():
        if not pending:
            return
        body = "".join(pending)
        pending.clear()
        lead = " " if body[:1] == " " else ""
        for pg in build.typeset(body, lead):
            h.update(("\x01".join(pg) + "\x02").encode())

    for kind, val in textmap.parse_ours(ours):
        if kind == "text":
            pending.append(val)
        elif kind == "page":
            flush()
            h.update(b"\x03")
    flush()
    return h.hexdigest()


def _raw_hash(ours: str) -> str:
    return hashlib.sha1(ours.encode()).hexdigest()


def fingerprint() -> dict[str, str]:
    out: dict[str, str] = {}
    for block, doc in sorted(textmap.load_all().items()):
        h = hashlib.sha1()
        for k, ent in sorted(doc.get("streams", {}).items()):
            ours = ent.get("ours", "")
            if not ours:
                continue
            sub = _raw_hash(ours) if ent.get("raw") else _pages_hash(ours)
            h.update(f"{k}\x00{sub}\x00".encode())
        out[f"{block:03d}"] = h.hexdigest()[:12]
    return out


if __name__ == "__main__":
    import json

    print(json.dumps(fingerprint(), ensure_ascii=False, indent=1))
