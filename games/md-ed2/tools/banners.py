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
import hangul

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


# 성·섬은 앞말에 붙인다(마스터 11-09 「성은 보통 붙여써도」) — 나머지 접미는 띄운다
GLUED = {"성", "섬"}


def kr_general(jp: str) -> str | None:
    """배너 원문 → **일반 꼴**(낱말 경계마다 한 칸, 마스터 11-09 「입장배너도 가능하다면 띄어쓰기」). 정본 `canon.place_general`
    (전체 원문 → 없으면 앞말 일반 꼴 + 접미). HUD·워프 꼴(`kr`, 붙임)은 그대로다."""
    g = canon.place_general(jp, "ed2")
    if g:
        return g
    suf = _suffix()
    m = re.match("^(.+?)(" + "|".join(map(re.escape, suf)) + ")$", jp)
    if not m:
        return kr(jp)
    base = canon.place_general(m.group(1), "ed2") or dict_names.from_dict(m.group(1), ("place",))
    if not base:
        return kr(jp)
    s = suf[m.group(2)]
    return base + ("" if s in GLUED else " ") + s


# ── 갈무리14 합성 글자(MD I 배너와 같은 방식, 마스터 11-09 「md2입장배너가 md1입장배너보다 폰트도 작은것 같고」) ──
# 표 0 한글(갈무리11 잉크 11행)로 그리면 16px 피치 안에서 작고 성기게 보인다. 배너 음절만 갈무리14(14×14 칸을 꽉 채움)로 구운 합성 글자(PUA U+E200~)로 쓴다 —
# 대사창·HUD 는 원래 코드를 그대로 써서 영향이 없고, 배너 레코드에 들어가는 **코드값만** 바뀐다(음절당 2B 그대로라 칸 계산·가운데 정렬 불변).
GALMURI14 = common.ROOT / "shared" / "fonts" / "Galmuri14.bdf"
_PUA_BASE = 0xE200
_pua_for: dict[str, str] | None = None


def _all_names() -> list[str]:
    d = common.rom()
    mods = {(b, k): m for b, k, m in archives.modules(d)}
    out = []
    for (b, k), spots in BY_MODULE.items():
        for off, n in spots:
            out += [v for jp in entries(mods[(b, k)], off, n) if (v := kr_general(jp))]
    return out


def _pua_map() -> dict[str, str]:
    global _pua_for
    if _pua_for is None:
        uniq = sorted({c for v in _all_names() for c in v if c != " "})
        _pua_for = {c: chr(_PUA_BASE + i) for i, c in enumerate(uniq)}
    return _pua_for


def pua_text(v: str) -> str:
    m = _pua_map()
    return "".join(m.get(c, c) for c in v)


def _ensure_custom_glyphs() -> None:
    # top=0 — 갈무리14 는 이미 14행을 꽉 채운다(top=1 을 얹으면 바닥 행이 칸 밖으로 잘린다, MD I 실측)
    bdf = hangul._load_bdf(GALMURI14, hangul.CELL, top=0, left=0)
    for ch, pua in _pua_map().items():
        if pua in hangul.CUSTOM_GLYPHS:
            continue
        g = bdf.get(ch)
        if g is None:
            raise SystemExit(f"갈무리14 에 없는 글자: {ch!r}")
        hangul.CUSTOM_GLYPHS[pua] = hangul.extend_jamo_arms(g)


def entries(mod: bytes, off: int, n: int) -> list[str]:
    return [
        mod[off + STRIDE * i : off + STRIDE * i + ENTRY].decode("cp932").strip() for i in range(n)
    ]


def check_shape(mod: bytes, off: int, n: int) -> None:
    for i in range(n):
        if mod[off + STRIDE * i + ENTRY] != 7:
            raise SystemExit(f"배너 표 {off:#x}[{i}]: 구분자가 07 이 아니다")


# 홀수 칸에서 오른쪽을 한 칸 더 두는 이름 — 11-09 갈무리14 배너 실측(`center-all/banner-all.tsv`)에서 왼쪽 올림이 좌−우 +11px(오른쪽 올림 −5px 가 가깝다)였던 둘. 나머지 홀수 칸은 +7(반대쪽은 −9)이라 왼쪽 올림 그대로.
RIGHT_HEAVY = frozenset({"베르가 광산", "왕가의 묘"})


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
            v = kr_general(jp)
            if not v:
                continue
            enc = encode(pua_text(v))
            if len(enc) > ENTRY:
                over.append(f"{key}@{off:#x}[{i}] {v!r} {len(enc)}B > {ENTRY}B")
                continue
            pad = ENTRY - len(enc)
            # 🔴 「최대한 가운데」(마스터 11-09): 홀수 칸이면 가운데에 **가까운** 쪽 — 반각 한 칸 ≈ 8px, 글자 바탕 여백으로 좌−우가 평균 −3px 라
            # 왼쪽을 한 칸 더 두면 +5 · 오른쪽을 더 두면 −11 이다(갈무리11 실측 — 갈무리14 로 바꾼 뒤 +7 · −9) → 왼쪽 올림. 짝수 칸은 그대로 대칭.
            if v in RIGHT_HEAVY:  # 갈무리14 로 바꾼 뒤 실측: 왼쪽 올림이 +11 이라 오른쪽 올림(−5)이 더 가깝다
                body = b" " * (pad // 2) + enc + b" " * ((pad + 1) // 2)
            else:
                body = b" " * ((pad + 1) // 2) + enc + b" " * (pad // 2)
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
    """배너가 쓰는 글자 — `collect_chars()` 가 늘 굽는다(갈무리14 합성 글자 + 표기 원문 한글: 같은 글자를 HUD 지명도 쓴다)."""
    _ensure_custom_glyphs()
    return set(_pua_map().values())


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
