"""`PARAM.BIN` 의 **이름 표**를 한글로 — 아이템 · 적 · 마법.

🔴 **이게 빠져 있었다**(2026-08-27, 유저 스크린샷으로 잡혔다). 설명문(`reinsert_desc`)은
넣고 있었는데 **이름은 아무도 안 썼다** — 장비창에 `短剣`·`布の服`·`木の盾`·`グローブ` 가
그대로 떴다. 정본(공용 사전)에 번역이 다 있었는데 **화면까지 갈 길이 없었다.**
⚠ 「표를 닫았다」와 「화면에 나온다」는 다른 말이다 — 이 레포가 또 물린 자리다.

이름은 레코드 **앞머리의 NUL 종료 문자열**이고, 뒤가 0 으로 채워져 있어 그만큼이 칸이다.
실측: 아이템 20B · 적 22B · 마법 21B(가장 긴 일본어 이름이 16B). 정본 전량이 들어간다.

    python3 tools/reinsert_param.py        # 넣을 수 있나 본다
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import glossary_src as GS
import hangul_map as H
import param as P

AREAS = (("아이템", P.ITEM), ("적", P.ENEMY), ("마법", P.SPELL))


#   🔴 이름은 **스탯·장비 창**에 나간다 — 그 창은 글리프의 0 행을 버려서(`build_font.DY`)
#     기본 글리프(원판 자리)로 넣으면 초성 윗 가로획이 날아간다. ⇒ **한 행 내린 판**으로.
_LOW = None


def low_table():
    """기본 배정 + 내린 판을 얹은 표(한 번만 읽는다)."""
    global _LOW
    if _LOW is None:
        _LOW = {**H.load(), **H.load_low()}
    return _LOW


def table():
    """`{JP 이름: 우리 표기}` — 공용 사전 전부를 한 사전으로."""
    return GS.table()


def room(rec):
    """이름 칸 — 이름 + 뒤에 이어지는 0 까지. 그 뒤는 수치라 못 건드린다."""
    z = rec.find(b"\x00")
    if z <= 0:
        return 0
    k = z
    while k < len(rec) and rec[k] == 0:
        k += 1
    return k


def patch(b, tbl, table_kr):
    """`(새 bytes, 넣은 수, [(JP, 사유)])` — **길이 불변**."""
    out = bytearray(b)
    done, bad = 0, []
    for name, (off, st, n) in AREAS:
        for i in range(n):
            s = off + i * st
            rec = bytes(b[s : s + st])
            jp = P.records(b, (off, st, n))[i] if False else None
            z = rec.find(b"\x00")
            if z <= 0:
                continue
            try:
                jp = rec[:z].decode("shift_jis")
            except UnicodeDecodeError:
                continue
            if jp in P.MARKS:
                continue
            kr = table_kr.get(jp)
            if not kr:
                continue
            try:
                raw = H.encode_kr(kr, low_table())
            except KeyError as e:
                bad.append((jp, f"{name}: {e}"))
                continue
            cap = room(rec)
            if len(raw) + 1 > cap:
                bad.append((jp, f"{name}: 칸 {cap}B 에 {len(raw) + 1}B"))
                continue
            out[s : s + cap] = raw + b"\x00" * (cap - len(raw))
            done += 1
    return bytes(out), done, bad


def main():
    tbl = table()
    with C.open_disc(1) as d:
        fs = {n: (lba, size) for n, lba, size in d.files()}
        lba, size = fs[P.PATH]
        b = d.read_extent(lba, size)
    new, done, bad = patch(b, None, tbl)
    assert len(new) == len(b), (len(new), len(b))
    print(f"이름 {done} 개를 넣는다 · 실패 {len(bad)}")
    for jp, why in bad[:10]:
        print(f"  ❌ {jp} — {why}")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
