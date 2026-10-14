"""sfc-ed2 몬스터 이름 풀 — `$CB:8B92` 의 16비트 포인터 표(군 99개) → 각 군은 **길이 접두 문자열**(`[len][글자…]`) 여럿(보통 4마리 A~D).

코드 `$C1:6570` 이 군 포인터(`$3D~$3F` = `$CB:xxxx`)에서 앞의 n 개 문자열을 건너뛰고(`len+1` 씩) n 번째를 `$053B` 버퍼에 복사한다(길이 접두라 길이 제한이 없다).
번역은 군 통째로 다시 만들어(뱅크 빈 자리) 포인터만 고친다. 이름은 정본(`canon.lookup(.., 'monster')`) — 접미 A~D 는 반각 영문으로 붙인다(번역 규칙 1-6: 「슬라임C」).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import glyphmap
import script

TABLE = 0xCB8B92
GROUPS = 99


def groups(d: bytes) -> list[tuple[int, list[bytes]]]:
    """[(포인터 값(16비트), [문자열 바이트…])] — 군이 풀을 빈틈없이 덮는지 검사한다."""
    t = common.snes2off(TABLE)
    ws = [d[t + 2 * i] | d[t + 2 * i + 1] << 8 for i in range(GROUPS)]
    starts = sorted(set(ws))
    out = []
    for w in ws:
        nxt = [s for s in starts if s > w]
        end = nxt[0] if nxt else None
        i = common.snes2off(0xCB0000 | w)
        strs = []
        while True:
            if end is not None and (0xCB0000 | (common.off2snes(i) & 0xFFFF)) >= (0xCB0000 | end):
                break
            L = d[i]
            if L == 0 or L > 40:
                break
            strs.append(d[i + 1 : i + 1 + L])
            i += 1 + L
        out.append((w, strs))
    return out


def decode(b: bytes, d: bytes | None = None) -> str:
    """바이트 → 일본어. `d` 가 있으면 사전 참조(`$E0 nn`)를 그 이름으로 펼친다(「グロッグ」+「ガード」 같은 합성 이름)."""
    import script as _s

    ent = {}
    if d is not None:
        ent = {(t, n): j for t, n, j in _s.dict_entries(d)}
    out, i = [], 0
    while i < len(b):
        x = b[i]
        if 0x80 <= x < 0x88 and i + 1 < len(b):
            out.append(script.glyph_char(x << 8 | b[i + 1]))
            i += 2
        elif 0x88 <= x < 0xE0:
            out.append(glyphmap.HALF_TABLE[x - 0x88])
            i += 1
        elif 0x20 <= x < 0x80:
            out.append(chr(x))
            i += 1
        elif x in (0xE0, 0xE1) and d is not None and i + 1 < len(b) and (f"E{x - 0xE0}", b[i + 1]) in ent:
            out.append(ent[(f"E{x - 0xE0}", b[i + 1])])
            i += 2
        else:
            out.append(f"<{x:02x}>")
            i += 1
    return "".join(out).replace("-", "ー")


_SUFFIX = re.compile(r"^(.*?)([A-DＡ-Ｄ])([゛゜]?)$")


def split_name(jp: str) -> tuple[str, str]:
    """`スライムC` → (`スライム`, `C`). 접미가 없으면 (이름, "")."""
    m = _SUFFIX.match(jp)
    if m:
        return m.group(1), chr(ord(m.group(2)) - (0xFF21 - 0x41) if ord(m.group(2)) >= 0xFF21 else ord(m.group(2)))
    return jp, ""


if __name__ == "__main__":
    common.verify_originals()
    d = common.rom_bytes()
    g = groups(d)
    tot = sum(len(s) for _w, s in g)
    print(f"군 {len(g)} · 문자열 {tot}")
    import canon

    miss = set()
    for _w, ss in g:
        for s in ss:
            base, _suf = split_name(decode(s, d))
            if not canon.lookup(base, "monster", "ed2"):
                miss.add(base)
    print("정본에 없는 몬스터 이름:", sorted(miss))
