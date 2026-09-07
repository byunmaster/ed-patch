"""고정 폭 문안 표 — 아이템·주문·지명·메뉴/설정/상태 라벨. **제자리, 같은 폭**으로 다시 쓴다.

    python3 tools/tables.py --check   # 표 분모(개수·폭) 재현
    python3 tools/tables.py --seed    # textmap/names.json 초안 — glossary 로 채울 수 있는 건 채운다

레코드 = `폭 B 본문 + 구분자(06 또는 00)`. 본문은 공백 패딩(아이템은 오른쪽 정렬). 한글은 2B/칸이라
폭 W 바이트 = W/2 칸 — 넘치면 **빌드 실패**(폭 게이트). 낱말 수준 명칭이라 원문(JP)을 정본에 담아도
된다(루트 「저작권」).
"""

import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

# 고정 폭 표: (이름, 시작, 폭, 구분자, 개수, 정렬) — 실측 2026-09-05 (docs/status.md 3b 절)
TABLES = [
    ("item", 0x338BE, 14, 0x06, 118, "right"),
    ("spell", 0x33FF8, 8, 0x06, 30, "right"),
    ("place_a", 0x3419F, 12, 0x06, 6, "center"),
    ("place_b", 0x341EE, 12, 0x06, 44, "center"),
    (
        "chapter",
        0x33132,
        30,
        0x00,
        1,
        "center",
    ),  # 「第１章　王子の旅立ち」(HUD 상단) — 다른 장은 아직 못 찾았다
]
# `00` 종결 문자열 묶음(메뉴·설정·상태 라벨): (이름, 첫 문자열 자리, 개수). 항목마다 **원래 바이트 길이를
# 폭으로** 지킨다 — 뒤에 수치 열(0000 · ＯＮ)이 고정 열에 겹쳐 찍히므로 자리가 밀리면 안 된다.
# 빈 문자열(00 만)은 항목으로 세지 않고 건너뛴다.
ZGROUPS = [
    (
        "menu_cmd",
        0x286A8,
        25,
    ),  # ⚠ 22 로 끊으면 「ｽﾃｰﾀｽ なし/ｵｰﾄ/固定」 셋이 빠진다(2026-09-06 실측)  # 呪文 使う 装備 捨てる 強さ その他 リーダー … 逃げる 武器 ｽﾃｰﾀｽ なし/ｵｰﾄ …
    (
        "battle_cmd",
        0x2179A,
        2,
    ),  # 전투 커맨드 두 줄 — 공백으로 칸을 맞춘 위치 고정 문자열(戦う 使う 守る オート / 呪文 武器 強さ 逃げる)
    ("status_label", 0x28976, 7),  # 強さ 0000 … 呪文能力 0000 (수치는 런타임이 덮는다)
    ("config_a", 0x28B18, 9),
    ("config_b", 0x28C3A, 6),
    (
        "config_val",
        0x28EA6,
        17,
    ),  # ＯＦＦ ＯＮ ＥＰ あと 速い 普通 遅い 止まる オート ﾏﾆｭｱﾙ 使う 使わない 同じに 別々に なし オート 固定
    (
        "defeat_menu",
        0x2A062,
        3,
    ),  # 패배 메뉴 — 最後に出た町に戻る / 戦いの直前に戻る / 冒険の続きをする
    ("yesno", 0x29EF8, 2),  # は　い / いいえ
    ("shop", 0x2B44C, 2),  # 買いたい / 売りたい
    ("battle_sub", 0x28554, 2),  # 전투 하위 메뉴 — 呪文\x06 / 使う\x06 (06 이 본문에 든다)
    (
        "mini_label",
        0x31DC4,
        5,
    ),  # 미니게임(100점 배분) 능력치 라벨 — <fe0e>ＨＰ<fe10>000 …  # 전투 하위 메뉴 — 呪文\x06 / 使う\x06 (06 이 본문에 든다)
    (
        "party_name",
        0x28E36,
        5,
    ),  # HUD 이름칸 — `FE 0C 이름 FE 10 공백…`(피치 12→16). 태그는 ours 에 그대로
    (
        "title",
        0x13658,
        4,
    ),  # 타이틀: 세이브 슬롯 줄 「L00 ―――――――」×3 + 「はじめから」 (FE 10/FE 0C 피치 태그)
]
NAMES_JSON = common.GAME_DIR / "textmap" / "names.json"


# 06 종결 이름 칸 — (이름, 첫 자리, 레코드 간격, 개수, 상한) — 게임 상태 블록의 파티 레코드(+0x30, 새 게임 때 RAM 으로
# 복사 → HUD 이름). 빌드는 이름+06 만 쓰고 나머지는 원본 그대로 둔다.
SLOTS = [
    ("party_rec", 0x333E2, 0x40, 4, 15),
    # 미니게임 대전 이름 — 06 뒤가 곧 코드라 **이름+06 만** 쓴다(칸을 통째로 채우면 jsr 이 깨진다)
    ("mini_name", 0x321B5, 0x10, 2, 8),
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


def seed(d: bytes) -> None:
    g = json.loads(
        (common.ROOT / "shared" / "glossary" / "eiyuu.json").read_text(encoding="utf-8")
    )["categories"]
    lookup = {}
    for cat in ("item", "place", "person", "monster"):
        lookup.update(g[cat])
    cur = json.loads(NAMES_JSON.read_text(encoding="utf-8")) if NAMES_JSON.exists() else {}
    filled = 0
    for name, recs in records(d).items():
        tbl = cur.setdefault(name, {})
        for i, (_, raw) in enumerate(recs):
            jp = decode(raw).strip()
            ent = tbl.setdefault(str(i), {"jp": jp, "ours": ""})
            key = unicodedata.normalize("NFKC", jp)
            if not ent["ours"] and key in lookup:
                ent["ours"] = lookup[key]
                ent["src"] = "glossary"
                filled += 1
    NAMES_JSON.parent.mkdir(exist_ok=True)
    NAMES_JSON.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    tot = sum(len(t) for t in cur.values())
    done = sum(1 for t in cur.values() for e in t.values() if e["ours"])
    print(f"  {NAMES_JSON}: {done}/{tot} 채움 (이번 {filled})")


if __name__ == "__main__":
    d = common.rom()
    if "--seed" in sys.argv:
        seed(d)
    else:
        check(d)
