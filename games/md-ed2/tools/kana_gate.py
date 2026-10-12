"""화면 일본어 게이트 — **분모는 파서가 아니라 최종 디코드 바이트의 가나 글줄 전수 스캔**이다.

    python3 tools/build.py --check          # 빌드 중 이 게이트가 돈다
    python3 tools/build.py --freeze-kana    # 남은 것을 기준선으로 박는다(사람이 보고 나서만)

🔴 왜 파서 출력이 분모면 안 되나(2026-10-13): 번역 도구는 `scene.parse_module` 이 찾은 스트림만 센다. 파서가 스트림을 못 찾으면
「번역 대상 0건 · 남은 일본어 0건」이 되어 게이트가 초록이다 — 실제로 가나 글줄이 **약 3,300줄** 빠져 있었다(화자 이름에 공백 ·
F6/F8 조건 사슬 · lea a3/a6 · 머리 표 레코드 · 절대 워드 표 · 제자리 고정 가나 글줄). 그래서 이 게이트는 **빌드된 모듈 바이트**
에서 가나(히라가나 `82 9F~F1` · 가타카나 `83 40~96`) 두 글자 이상 이어진 글줄과 `<1e>이름<04>` 화자 머리(한자 이름)를 직접 센다.

- 기준선(`textmap/kana_baseline.json`) = 번역 대상이 아닌 것으로 **사람이 확인한** 글줄(코드 바이트가 우연히 가나 꼴 · 지명 배너 표의
  못 채운 칸 · 쓰레기 스트림). 모듈별 「글줄 해시 → 개수」 — 오프셋이 아니라 해시라 모듈 안에서 자리가 옮겨져도 안 흔들린다.
- 기준선보다 **늘면 실패**한다. 줄면 알린다(`--freeze-kana` 로 내린다 — 래칫).
"""

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

KANA = re.compile(rb"(?:\x82[\x9f-\xf1]|\x83[\x40-\x96]){2,}")
SPEAKER = re.compile(rb"\x1e((?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]|\x20){1,12})\x04")
BASELINE = Path(__file__).resolve().parents[1] / "textmap" / "kana_baseline.json"
HANGUL_CODES = Path(__file__).resolve().parents[1] / "textmap" / "hangul_codes.json"


def _hangul_pairs() -> set[bytes]:
    d = json.loads(HANGUL_CODES.read_text(encoding="utf-8"))
    return {v.to_bytes(2, "big") for v in d.values() if isinstance(v, int)}


def _is_korean(name: bytes, pairs: set[bytes]) -> bool:
    """화자 이름 바이트가 전부 우리 한글 코드(+ 반각 공백)인가 — 한글 코드는 SJIS 한자 선두 범위(0x8A~)에 앉아 정규식만으론 못 가른다."""
    i = 0
    while i < len(name):
        if name[i] == 0x20:
            i += 1
        elif name[i : i + 2] in pairs:
            i += 2
        else:
            return False
    return True


def _h(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()[:10]


def scan(blocks: list[bytes], sizes: list[list[int]]) -> dict[str, Counter]:
    """{"블록-모듈": Counter({해시: 개수})} — 가나 글줄 + 한자 화자 머리. 해시 앞 `k:`(가나) · `s:`(화자)."""
    out: dict[str, Counter] = {}
    pairs = _hangul_pairs()
    for i, sz in enumerate(sizes):
        if i >= len(blocks):
            break
        at = 0
        for k, n in enumerate(sz):
            mod = blocks[i][at : at + n]
            at += n
            c: Counter = Counter()
            for m in KANA.finditer(mod):
                c["k:" + _h(m.group())] += 1
            for m in SPEAKER.finditer(mod):
                if not _is_korean(m.group(1), pairs):
                    c["s:" + _h(m.group())] += 1
            if c:
                out[f"{i}-{k}"] = c
    return out


def sample(blocks, sizes, key: str, h: str) -> str:
    i, k = map(int, key.split("-"))
    at = sum(sizes[i][:k])
    mod = blocks[i][at : at + sizes[i][k]]
    rx = KANA if h.startswith("k:") else SPEAKER
    for m in rx.finditer(mod):
        if _h(m.group()) == h[2:]:
            lo = max(0, m.start() - 4)
            return f"@{m.start():#x} " + mod[lo : m.end() + 6].decode("cp932", "replace")
    return "?"


def load_baseline() -> dict[str, dict[str, int]]:
    return json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}


def check(blocks, sizes, *, freeze: bool = False) -> None:
    left = scan(blocks, sizes)
    total = sum(sum(c.values()) for c in left.values())
    if freeze:
        BASELINE.write_text(
            json.dumps(
                {k: dict(sorted(c.items())) for k, c in sorted(left.items())},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"  가나 기준선 박음: 모듈 {len(left)}곳 · 글줄 {total}")
        return
    base = load_baseline()
    new: list[str] = []
    shrunk = 0
    for key, c in left.items():
        b = base.get(key, {})
        for h, n in c.items():
            if n > b.get(h, 0):
                new.append(f"블록 {key} {h} ×{n - b.get(h, 0)}: {sample(blocks, sizes, key, h)}")
    for key, b in base.items():
        for h, n in b.items():
            if left.get(key, Counter()).get(h, 0) < n:
                shrunk += n - left.get(key, Counter()).get(h, 0)
    print(
        f"  화면 일본어(가나 글줄·한자 화자) 전수 스캔 — 남은 {total}줄 · 기준선 밖 {len(new)}줄"
        + (f" · 기준선보다 줄어든 것 {shrunk}줄(--freeze-kana 로 내린다)" if shrunk else "")
    )
    if new:
        raise SystemExit(
            "❌ 기준선 밖의 일본어가 화면에 남는다 — 파서가 못 본 대본이거나 번역 누락이다:\n    "
            + "\n    ".join(new[:60])
            + (f"\n    … 외 {len(new) - 60}줄" if len(new) > 60 else "")
        )
