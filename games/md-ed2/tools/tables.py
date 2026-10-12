"""고정 폭 문안 표 — 아이템·주문·지명·메뉴/설정/상태 라벨. **제자리, 같은 폭**으로 다시 쓴다.

    python3 tools/tables.py --check   # 표 분모(개수·폭) 재현

레코드 = `폭 B 본문 + 구분자(06 또는 00)`. 본문은 공백 패딩(아이템은 오른쪽 정렬). 한글은 2B/칸이라
폭 W 바이트 = W/2 칸 — 넘치면 **빌드 실패**(폭 게이트). 낱말 수준 명칭이라 원문(JP)을 정본에 담아도
된다(루트 「저작권」).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

# 고정 폭 표: (이름, 시작, 폭, 구분자, 개수, 정렬) — ED2 실측 2026-10-12(ED1 표와 같은 꼴, 주소·개수만 다르다)
TABLES = [
    (
        "item",
        0x3A890,
        14,
        0x06,
        139,
        "right",
    ),  # 마지막 둘은 빈 칸(ED1 118 → ED2 139, 「？？？？？７１」 같은 자리표시 포함)
    ("spell", 0x3B104, 8, 0x06, 33, "right"),  # 마지막은 빈 칸
    (
        "place_a",
        0x3B2F4,
        9,
        0x06,
        5,
        "center",
    ),  # 도시 다섯 — 뒤의 지명 표(0x3B326~)는 폭이 레코드마다 다르다(미이식, status.md)
]
# `00` 종결 문자열 묶음(메뉴·설정·상태 라벨): (이름, 첫 문자열 자리, 개수). 내용은 ED1 과 **같다**(25·2·7·9·6·17·3·2·2·2·4 전부 일치).
ZGROUPS = [
    ("menu_cmd", 0x2EC8C, 25),
    ("battle_cmd", 0x2628E, 2),
    ("status_label", 0x2EF5A, 7),
    ("config_a", 0x2F0FC, 9),
    ("config_b", 0x2F21E, 6),
    ("config_val", 0x2F48A, 17),
    ("defeat_menu", 0x30682, 3),
    ("yesno", 0x30518, 2),
    ("shop", 0x3196E, 2),
    ("battle_sub", 0x2EB38, 2),
    (
        "party_name",
        0x2F41C,
        5,
    ),  # HUD 이름칸 — `FE 0C 이름 FE 10 공백…`(아트라스·랜도·플로라·신디·소니아)
    ("title", 0x164D2, 4),
]

# 06 종결 이름 칸 — (이름, 첫 자리, 레코드 간격, 개수, 상한). 파티 레코드(+0x30). 소니아(다섯째)는 이벤트가 이름을 넣는다.
SLOTS = [
    ("party_rec", 0x3A444, 0x40, 4, 15),
]
SLOT_CAP = {t[0]: t[4] for t in SLOTS}


def records(d: bytes) -> dict[str, list[tuple[int, bytes]]]:
    """표 이름 → [(자리, 원본 본문)]. 본문 길이가 곧 그 항목의 폭이다."""
    out = {}
    for name, start, w, sep, n, _ in TABLES:
        recs = []
        p = start
        for i in range(n):
            if d[p + w] != sep:
                raise SystemExit(f"{name}[{i}] @{p:#x}: 구분자가 {d[p + w]:02x} (기대 {sep:02x})")
            recs.append((p, d[p : p + w]))
            p += w + 1
        out[name] = recs
    for name, start, stride, n, _cap in SLOTS:
        out[name] = [
            (start + i * stride, d[start + i * stride : d.index(6, start + i * stride)])
            for i in range(n)
        ]
    for name, start, n in ZGROUPS:
        recs = []
        p = start
        while len(recs) < n:
            q = d.index(b"\x00", p)
            if q == p:  # 빈 문자열/정렬 패딩
                p += 1
                continue
            recs.append((p, d[p:q]))
            p = q + 1
        out[name] = recs
    return out


def align_of(name: str) -> str:
    for t in TABLES:
        if t[0] == name:
            return t[5]
    return "left"


def decode(raw: bytes) -> str:
    return raw.replace(b"\x00", b" ").decode("cp932", "replace")


def check(d: bytes) -> None:
    for name, recs in records(d).items():
        ws = sorted({len(r[1]) for r in recs})
        w = f"{ws[0]:2d}B" if len(ws) == 1 else f"{ws[0]}~{ws[-1]}B"
        print(
            f"  {name:12s} {recs[0][0]:#x} {w:>6s} × {len(recs):3d}  "
            f"{decode(recs[0][1]).strip()!r} … {decode(recs[-1][1]).strip()!r}"
        )


if __name__ == "__main__":
    check(common.rom())
