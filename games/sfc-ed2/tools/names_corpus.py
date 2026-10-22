"""sfc-ed2 이름 검사 어댑터 — `pairs()` 가 `(자리, 원문 줄, 우리 줄|None, 갈래)` 를 문안 전체에 대해 낸다.

🔴 이름 표를 **들지 않는다**(마스터 2026-10-07). 원문은 롬에서 글리프표로 읽고, 우리 줄은 `textmap/segments.json` 에서 읽을 뿐이다.
사전 참조(`<E0:n>`·`<E1:n>`)는 양쪽 다 **그 자리에 풀어** 낸다 — 원문은 롬 사전의 글자, 우리 쪽은 정본(`build.dict_names`)의 한국어.
안 풀면 이름이 사전 안에 있는 문장이 전부 「우리 줄에 없다」로 오탐 난다(sfc-ed1 어댑터와 같은 규칙).
조사 `{은/는}`·`{*은/는}` 는 정본 꼴 `은(는)` 으로, 그 밖의 제어 토큰은 경계 글자 `|` 로 바꾼다.

자리 표기: 대사 구간 `$C21C62` · 사전 `E0:번호`(이름 — 갈래 slot) · `E1:번호`(문구 — dialog).
"""

import re

import build
import common
import kr
import script
import segs

TITLE = "eiyuu"
CANON = "ed2"  # 공통 문안 정본 — PS1 ED2 기반(마스터 10-08)
CANON_GATE = True  # 전환을 마쳤다 — check_canon.py 가 어긋남을 실패로 친다(2026-10-13)

_E = re.compile(r"<E([01]):(\d+)>")
_JOSA = re.compile(r"\{\*?([^{}/]+)/([^{}/]+)\}")
_TAG = re.compile(r"<[^<>]*>")


def _norm(t: str) -> str:
    t = _JOSA.sub(lambda m: f"{m.group(1)}({m.group(2)})", t)
    return _TAG.sub("|", t).strip("| \n")


def pairs():
    d = common.rom_bytes()
    jp_dict = {f"E{t[1]}:{n}": text for t, n, text in ((e[0], e[1], e[2]) for e in script.dict_entries(d))}
    # 위 키는 `E0:12` 꼴이 아니라 (표, 번호) 라 아래서 다시 만든다
    jp_dict = {f"{t}:{n}": text for t, n, text in script.dict_entries(d)}
    kr_dict = build.dict_names(d, kr.load("dict"))
    out = []
    for t, n, text in script.dict_entries(d):
        out.append((f"{t}:{n}", text, kr_dict.get(f"{t}:{n}"), "slot" if t == "E0" else "dialog"))
    tm = kr.load("segments")
    keep = set(kr.load("keep").get("ids", []))
    for a, b in segs.segments(d):
        sid = segs.seg_id(a)
        if sid in keep:
            continue
        jp = _E.sub(lambda m: jp_dict.get(f"E{m.group(1)}:{m.group(2)}", ""), segs.notation(d, a, b))
        v = tm.get(sid)
        ko = None
        if v:
            ko = _E.sub(lambda m: kr_dict.get(f"E{m.group(1)}:{m.group(2)}", ""), v["kr"])
        out.append((sid, _norm(jp), _norm(ko) if ko is not None else None, "dialog"))
    out += _unit_rows(d, jp_dict, kr_dict)
    return out


def _unit_rows(d, jp_dict, kr_dict):
    """구간이 둘 이상이거나 호출 조각(`$10`)을 끼는 대사 단위는 **이어 붙인 한 줄**로도 낸다 — 구간 단위로만 보면 「이거」+호출 「왕자님」 같은 이음새 인사가 안 보인다(10-20 style: 병사 인사 「이거 왕자님」이 통과했다).
    구운 롬이 있을 때만 낸다(한국어 쪽을 롬에서 읽는다 — 정리는 check.sh 가 빌드 뒤에 돌리므로 항상 있다)."""
    built = common.BUILD_DIR / "sfc-ed2" / "Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"
    if not built.exists():
        return []
    import bisect

    import romdump

    kb = built.read_bytes()
    dj, dk = romdump.Dec(d, False), romdump.Dec(kb, True, romdump.kr_glyph_map(kb))
    starts = sorted(a for a, _b in segs.segments(d))
    rows = []
    for s, e in script.all_units(d):
        i, j = bisect.bisect_left(starts, s), bisect.bisect_left(starts, e)
        has_call = any(d[p] == 0x10 for p, _ln in script.tokens(d, s, e))
        if j - i < 2 and not has_call:
            continue
        o = s + 4 if d[s : s + 4] == b"\x5c\x0b\x8f\xc1" else s
        try:
            tj, tk = dj.walk(o), dk.walk(o)
        except Exception:
            continue
        rows.append((f"U{common.off2snes(o):06X}", _unit_norm(tj), _unit_norm(tk), "dialog"))
    return rows


def _unit_norm(t: str) -> str:
    t = t.replace("↵", " ").replace("⏎", "|").replace("〔", "|").replace("〕", "|").replace("{", "").replace("}", "")
    return _norm(t)
