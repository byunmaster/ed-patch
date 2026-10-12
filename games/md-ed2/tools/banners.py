"""입장 배너 지명 사전 — 필드 씬 모듈 안의 14B 고정 칸 표(항목 사이 `07`). `collect_chars()` 가 안 보는 자리.

    python3 tools/banners.py        # 표 위치·항목·우리 표기 점검

월드맵에서 마을에 다가갈 때 뜨는 큰 틀은 이 표를 읽는다. 표는 **씬 모듈의 데이터**라(문안 스트림 경계 밖) 스트림 재삽입이
안 건드리고, 일본어 가나가 한글 글리프로 갈린 뒤라 그대로 두면 깨진 글자가 뜬다(md-ed1 `field_names.py` 와 같은 사건).
ED2 는 **블록 37~39 의 모듈 8곳**에 있다 — 큰 사전 셋(30·27·26항목)과 항구 일곱 개짜리 작은 표 다섯.

고치는 법(md-ed1 `field_names` 와 같다): 항목마다 **같은 14B 칸에** 우리 표기를 가운데 맞춰 넣는다(앞뒤 반각 공백, 길이 불변).
모듈 길이가 그대로라 재조립·분할 표에 영향이 없다. 표기는 사전(고유명사 `place`) + 정본의 지명 접미 규칙(「の町」→「마을」 …, ED1 정본
`ui` 의 `@지명칸` 열쇠)에서 읽는다 — **배너는 원문에 접미가 있는 꼴 그대로**(`docs/naming.md` 「지명 칸」: 배너는 접미를 붙인다, 붙여 쓴다).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import archives
import common
import dict_names

from shared import canon

ENTRY = 14  # 칸 폭(B)
STRIDE = ENTRY + 1  # + 구분자 07
# (블록, 모듈, 모듈 안 오프셋, 항목 수) — 2026-10-12 전수 탐색(07 간격 15B 반복 ≥3). 오프셋은 모듈 바이트 기준
TABLES = [
    (37, 1, 7828, 30),
    (37, 2, 1712, 7),
    (38, 0, 7124, 27),
    (38, 1, 1470, 7),
    (38, 3, 2588, 26),
    (39, 0, 1478, 7),
    (39, 2, 2576, 26),
    (39, 3, 3750, 7),
]
BY_MODULE: dict[tuple[int, int], list[tuple[int, int]]] = {}
for _b, _k, _o, _n in TABLES:
    BY_MODULE.setdefault((_b, _k), []).append((_o, _n))


def _suffix() -> dict[str, str]:
    return {
        k.split("@")[0]: v for k, v in canon.table("ui", "ed1").items() if k.endswith("@지명칸")
    }


def kr(jp: str) -> str | None:
    """배너 원문 → 우리 표기(없으면 None)."""
    v = dict_names.from_dict(jp, ("place",)) or dict_names.from_canon(jp, "place")
    if v is not None:
        return v
    suf = _suffix()
    m = re.match("^(.+?)(" + "|".join(map(re.escape, suf)) + ")$", jp)
    if not m:
        return None
    base = dict_names.from_dict(m.group(1), ("place",)) or dict_names.from_canon(
        m.group(1), "place"
    )
    return base + suf[m.group(2)] if base else None


def entries(mod: bytes, off: int, n: int) -> list[str]:
    return [
        mod[off + STRIDE * i : off + STRIDE * i + ENTRY].decode("cp932").strip() for i in range(n)
    ]


def check_shape(mod: bytes, off: int, n: int) -> None:
    for i in range(n):
        if mod[off + STRIDE * i + ENTRY] != 7:
            raise SystemExit(f"배너 표 {off:#x}[{i}]: 구분자가 07 이 아니다")


def patch(key: tuple[int, int], mod: bytes, encode) -> bytes:
    """모듈 바이트 → 배너 표를 우리 표기로 바꾼 같은 길이의 바이트. 못 채운 항목은 원문 그대로 둔다."""
    spots = BY_MODULE.get(key)
    if not spots:
        return mod
    out = bytearray(mod)
    over = []
    for off, n in spots:
        check_shape(mod, off, n)
        for i, jp in enumerate(entries(mod, off, n)):
            v = kr(jp)
            if not v:
                continue
            enc = encode(v)
            if len(enc) > ENTRY:
                over.append(f"{key}@{off:#x}[{i}] {v!r} {len(enc)}B > {ENTRY}B")
                continue
            pad = ENTRY - len(enc)
            body = b" " * (pad // 2) + enc + b" " * (pad - pad // 2)
            at = off + STRIDE * i
            out[at : at + ENTRY] = body
    if over:
        raise SystemExit("배너 칸 넘침:\n    " + "\n    ".join(over))
    return bytes(out)


def verify(key: tuple[int, int], new: bytes, orig: bytes, encode) -> int:
    """🔴 최종 모듈 바이트의 배너 표가 의도(원본 모듈에 `patch` 한 것)와 같은지 — 재조립이 데이터 오프셋을 옮겼다면 여기서 걸린다."""
    want = patch(key, orig, encode)
    n = 0
    for off, cnt in BY_MODULE[key]:
        a, b = off, off + STRIDE * cnt
        if new[a:b] != want[a:b]:
            raise SystemExit(f"배너 표 {key}@{off:#x}: 최종 모듈의 표가 의도와 다르다")
        n += cnt
    return n


def chars(d: bytes | None = None) -> set[str]:
    """배너가 쓰는 글자 — `collect_chars()` 가 늘 굽는다."""
    d = d if d is not None else common.rom()
    mods = {(b, k): m for b, k, m in archives.modules(d)}
    out: set[str] = set()
    for (b, k), spots in BY_MODULE.items():
        for off, n in spots:
            for jp in entries(mods[(b, k)], off, n):
                v = kr(jp)
                if v:
                    out.update(v)
    return out


if __name__ == "__main__":
    d = common.rom()
    mods = {(b, k): m for b, k, m in archives.modules(d)}
    miss = set()
    for (b, k), spots in BY_MODULE.items():
        for off, n in spots:
            check_shape(mods[(b, k)], off, n)
            miss.update(jp for jp in entries(mods[(b, k)], off, n) if not kr(jp))
    print(
        f"  배너 표 {len(TABLES)}곳 · 항목 {sum(t[3] for t in TABLES)} · 우리 표기 없음 {sorted(miss)}"
    )
