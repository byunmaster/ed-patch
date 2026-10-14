"""sfc-ed2 이름 검사 어댑터 — 원문 줄만 내고 번역 줄은 전부 None(번역 전 단계).

🔴 이름 표를 **들지 않는다**(마스터 2026-10-07). 원문은 롬에서 글리프표(`glyphmap`)로 읽어 낸다.
**번역 전 단계라 우리 줄이 전부 None — 이름 검사 초록은 통과가 아니라 안 잰 것이다**(분모는 원문 줄 수). 번역 문안이 서면
`None` 자리를 우리 줄로 채운다.

자리 표기: 대사 `$C21C62#줄번호` · 사전 `E0:번호`(이름 — 갈래 slot) · `E1:번호`(문구 — dialog).
사전 참조(`〈E0:nn〉`)는 문안이 아니라 표식으로 남는다.
"""

import script

import common

TITLE = "eiyuu"


def pairs():
    d = common.rom_bytes()
    out = []
    for tbl, n, text in script.dict_entries(d):
        out.append((f"{tbl}:{n}", text, None, "slot" if tbl == "E0" else "dialog"))
    units, _bad = script.units(d)
    for s, _e in units:
        for k, line in enumerate(script.decode(d, s)):
            out.append((f"${common.off2snes(s):06X}#{k}", line, None, "dialog"))
    return out
