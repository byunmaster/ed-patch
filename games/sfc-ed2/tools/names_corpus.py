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
    return out
