"""sfc-ed1 번역 정본(textmap) — 조각 id(sha1) → 한국어 번역문 + 상태. **커밋되는 파일**이다.

원문은 여기 없다(루트 「저작권」) — 원문·토큰은 `units.py --dump` 가 work/derived/units/segments.json 에 낸다.
번역문 규칙:
  · 조각의 `tokens`(사전 `{D3:08}` · 치환 `{D6}` · 제어 `<FF>`)를 **전부, 같은 순서로** 품는다. 사전 토큰끼리는
    순서를 바꿔도 된다(어순). 없으면 검사기가 운다 — 토큰이 빠지면 분기·페이지가 사라진다(구조 계약).
  · 개행은 조판기가 넣는다(8자/줄 · 4줄, D1=A). 번역문에 `\\n` 을 쓰면 강제 개행이다.
상태(state):
  tm-draft   PS1 번역본에서 유사도로 끌어온 초안 — 토큰 자리·어미를 사람이 봐야 한다
  draft      새로 쓴 초안
  reviewed   사람이 확정 — 빌드 입력 자격(개발 빌드는 draft 도 넣되 릴리스 후보는 reviewed 만)
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001
import common

PATH = common.GAME_DIR / "textmap" / "segments.json"
DICT_PATH = common.GAME_DIR / "textmap" / "dict.json"  # 사전 6벌: "D2:0A" → {kr, state, jp_len}
MENUS_PATH = (
    common.GAME_DIR / "textmap" / "menus.json"
)  # 메뉴 라벨: "じゅもん@A01" → {kr, state, budget_tiles, …}

# 메뉴 라벨 초안 — **PS1 트랙에서 유저가 확정한 표기**(games/ps1-ed1+2/tools/patch_sys_ui.py, 2026-08-13~17)를
# 그대로 물려받는다. 같은 원문이 자리에 따라 갈리는 건 PS1 도 그랬다(強さ: 파티 메뉴 `상태` · 능력치 창 `힘`).
MENU_KR = {
    "じゅもん": ("주문", "ps1"),
    "つかう": ("사용", "ps1"),
    "そうび": ("장비", "ps1"),
    "すてる": ("버린다", "ps1"),
    "つよさ@A01": ("상태", "ps1"),
    "つよさ@A05": ("힘", "ps1"),
    "つよさ": ("상태", "ps1"),
    "そのた": ("그외", "ps1"),
    "リーダー": ("리더", "ps1"),
    "かしこさ": ("지혜", "ps1"),
    "すばやさ": ("민첩성", "ps1"),
    "うん": ("행운", "ps1"),
    "こうげき": ("공격력", "ps1"),
    "ぼうぎょ": ("방어력", "ps1"),
    "ロード": ("로드", "ps1"),
    "セーブ": ("저장", "ps1"),
    "システム": ("시스템", "ps1"),
    "せってい": ("설정", "draft"),
    "レベルアップ": ("레벨업", "ps1"),
    "EPひょうじ": ("EP표시", "draft"),
    "いどう": ("이동", "ps1"),
    "メッセージ": ("메시지", "ps1"),
    "オートバトル": ("자동전투", "ps1"),
    "オートかいふく": ("자동회복", "ps1"),
    "たたかいのじゅもん": ("전투주문", "ps1"),
    "かいふくのじゅもん": ("회복주문", "ps1"),
    "かいふくのアイテム": ("회복아이템", "ps1"),
    "ぜんいんのせってい": ("전원의 설정", "ps1"),
    "かいたい": ("사기", "draft"),
    "うりたい": ("팔기", "draft"),
    "あと": ("남다", "ps1"),  # PS1 은 정발 「남다」(설정 「EP 남다」·HUD) — 공용 정본 `あと@경험치표시` 와 같다(09-26 정정)
}
TOKEN_RE = re.compile(r"\{[0-9A-F]{2}(?::[0-9A-F]{2})?\}|<[0-9A-F]{2}(?::[0-9A-F]+)?>|<@>")
JOSA_RE = re.compile(
    r"\{(은/는|이/가|을/를|와/과|으로/로|이라/라|이다/다|이/)\}"
)  # 조사 자리표시자 — 토큰이 아니다


def load() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}


def save(tm: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(
        json.dumps(dict(sorted(tm.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def tokens_in(kr: str) -> list[str]:
    return TOKEN_RE.findall(kr)


# 사전 여섯 벌이 공용 정본의 어느 부류인가 — `init_dict`(채우기)와 `check_glossary`(갈림 검사)가 나눠 쓴다
DICT_CATEGORY = {
    0xD0: "person",
    0xD1: "place",
    0xD2: "item",
    0xD3: "monster",
    0xD4: "item",
    0xD5: None,
}


def check_tokens(kr: str, tokens: list[str]) -> str | None:
    """번역문의 토큰 계약. **제어 토큰(`<..>`, `<@>` 포함)은 전부 같은 순서로** 있어야 한다 — 빠지면 분기·페이지가
    사라진다. **사전·치환 토큰(`{..}`)은 빼도 되고 어순을 바꿔도 된다**(글자만 찍는다 — 「キャリオンク{ロー}ラー」처럼
    이름 조각을 재활용한 자리는 번역문이 통째로 쓰는 게 맞다). 원문에 없는 토큰을 더하면 안 된다."""
    got = tokens_in(kr)
    ctrl_got = [t for t in got if t.startswith("<")]
    ctrl_exp = [t for t in tokens if t.startswith("<")]
    if ctrl_got != ctrl_exp:
        return f"제어 토큰이 다르다: 기대 {ctrl_exp} 실제 {ctrl_got}"
    dict_exp = [t for t in tokens if t.startswith("{")]
    for t in (t for t in got if t.startswith("{")):
        if t in dict_exp:
            dict_exp.remove(t)
        else:
            return f"원문에 없는 사전 토큰: {t}"
    return None


def init_from_tm(min_ratio: float) -> dict:
    segs = {
        s["seg"]: s
        for s in json.loads(
            (common.OUT_DIR / "units" / "segments.json").read_text(encoding="utf-8")
        )
    }
    by = json.loads((common.OUT_DIR / "tm" / "by_reading.json").read_text(encoding="utf-8"))
    tm = load()
    added = 0
    for r in by:
        if not r["ratio"] or r["ratio"] < min_ratio or not r["kr"]:
            continue
        s = segs[r["seg"]]
        if s["id"] in tm and tm[s["id"]].get("state") != "tm-draft":
            continue  # 사람이 손댄 항목은 덮지 않는다
        # 토큰은 뒤에 이어 붙여 둔다 — 자리는 사람이 옮긴다(초안 표시)
        kr = r["kr"].strip()
        tail = "".join(t for t in s["tokens"])
        tm[s["id"]] = {
            "addr": s["addr"],
            "kr": kr + tail,
            "state": "tm-draft",
            "tm": {"ps1": r["ps1"], "ratio": r["ratio"]},
        }
        added += 1
    save(tm)
    return {"entries": len(tm), "added_or_refreshed": added}


def init_dict() -> dict:
    """사전 6벌을 glossary(공용 고유명사 정본)로 채운다 — 읽기(pykakasi)로 맞춘다. 상태 `glossary`.
    못 맞춘 항목은 `kr: null · state: todo` 로 남겨 사람이 채운다. 시스템 문장($D5)은 전부 todo."""
    import pykakasi
    import tm

    rom = common.rom_bytes()
    res = text.resolver(rom)
    g = json.loads(tm.GLOSSARY.read_text(encoding="utf-8"))["categories"]
    kk = pykakasi.kakasi()

    def hira(s: str) -> str:
        return (
            tm.to_hira("".join(x["hira"] for x in kk.convert(s)))
            .replace("・", "")
            .replace("　", "")
            .replace(" ", "")
        )

    idx: dict[tuple[str, str], str] = {}
    for cat, d in g.items():
        for k, v in d.items():
            idx.setdefault((cat, hira(k)), v)
    cat_of = DICT_CATEGORY
    cur = json.loads(DICT_PATH.read_text(encoding="utf-8")) if DICT_PATH.exists() else {}
    n_hit = 0
    for code in text.DICT_TABLES:
        for i, e in enumerate(text.dict_entries(code, rom)):
            key = f"{code:02X}:{i:02X}"
            if key in cur and cur[key].get("state") not in ("glossary", "todo"):
                continue  # 사람이 손댄 것은 두 번 안 건드린다
            jp = text.decode(e, res)
            k = tm.to_hira(jp.strip().replace("・", "").replace("　", "").replace("＝", ""))
            kr = None
            cats = (
                [cat_of[code]]
                + [c for c in ("person", "place", "item", "monster") if c != cat_of[code]]
                if cat_of[code]
                else []
            )
            for c in cats:
                if (c, k) in idx:
                    kr = idx[(c, k)]
                    break
            n_hit += bool(kr)
            cur[key] = {"jp_len": len(jp.strip()), "kr": kr, "state": "glossary" if kr else "todo"}
    DICT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DICT_PATH.write_text(
        json.dumps(dict(sorted(cur.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return {
        "entries": len(cur),
        "glossary": n_hit,
        "todo": sum(1 for v in cur.values() if v["state"] == "todo"),
    }


def render_width(kr: str) -> int:
    """칸(8px) 단위 폭. **D1=B**(유저 2026-09-06) 로 한글도 **한 칸**이다 — `Galmuri11-Condensed`
    가 완성형 전부 폭 7px 라 반각에 든다. `…` 만 전각 두 칸(원본 글꼴을 그대로 쓴다)."""
    import hangul_font

    hw = 1 if hangul_font.CELL_W == 8 else 2
    return sum(hw if "가" <= c <= "힣" else (2 if c == "…" else 1) for c in kr)


def init_menus() -> dict:
    """menus.py 덤프에서 메뉴 라벨 정본을 만든다. 키 = `원문@표id`(단어 수준이라 커밋해도 된다)."""
    # 예산은 **넓힌 뒤**(build.py WIDEN, D2=(b)) 의 창에서 잰다 — 빌드 출력 롬을 되읽는다
    import build
    import menus

    out, _ = build.build(common.rom_bytes())
    ls = menus.layouts(out)
    cur = json.loads(MENUS_PATH.read_text(encoding="utf-8")) if MENUS_PATH.exists() else {}
    over = []
    for x in ls:
        for lab in x["labels"]:
            key = f"{lab['jp']}@{x['table']}{x['id']:02X}"
            if key in cur and cur[key].get("state") not in ("ps1", "draft", "todo"):
                continue
            kr, st = MENU_KR.get(key) or MENU_KR.get(lab["jp"]) or (None, "todo")
            w = render_width(kr) if kr else 0
            cur[key] = {
                "kr": kr,
                "state": st,
                "budget_tiles": lab["budget_tiles"],
                "width_tiles": w,
                "fits": bool(kr) and w <= lab["budget_tiles"],
                "row": lab["row"],
                "x0": lab["x0"],
            }
            if kr and w > lab["budget_tiles"]:
                over.append((key, kr, w, lab["budget_tiles"]))
    MENUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    MENUS_PATH.write_text(
        json.dumps(dict(sorted(cur.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return {
        "entries": len(cur),
        "todo": sum(1 for v in cur.values() if v["state"] == "todo"),
        "over_budget": over,
    }


def check_glossary() -> list[tuple[str, str, str, str]]:
    """사전(`dict.json`)의 `glossary` 항목이 **공용 정본과 같은가.** 갈리면 그 자리를 돌려준다.

    ⚠ 정본은 다른 게임의 브랜치에서도 고쳐진다(루트 CLAUDE.md) — 실제로 PS1 의 1회차 QA 가 머지되며
    몬스터 이름 여섯이 바뀌었고(`살쾡이`→`산고양이` 등) 우리 사전만 옛 표기로 남아 있었다(2026-09-06).
    표기가 갈리면 **인게임에서만 드러나므로** 게이트가 본다. 원문(JP)은 커밋 안 하니 롬에서 얻는다."""
    import tm as tm_mod

    rom = common.rom_bytes()
    g = json.loads(tm_mod.GLOSSARY.read_text(encoding="utf-8"))["categories"]
    # ⚠ **부류를 갈라 본다** — 같은 원문이 부류마다 다른 표기다(`カース` = 아이템 `커스` · 몬스터 `카스`).
    #   납작하게 펴면 몬스터를 아이템 표기로 잡는 오탐이 난다(실측 2026-09-06). 순서는 `init_dict` 와 같다.
    cur = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    out = []
    for code in text.DICT_TABLES:
        cats = [DICT_CATEGORY[code]] + [
            c for c in ("person", "place", "item", "monster") if c != DICT_CATEGORY[code]
        ]
        for i, b in enumerate(text.dict_entries(code, rom)):
            key = f"{code:02X}:{i:02X}"
            v = cur.get(key, {})
            kr = v.get("kr")
            if not kr or v.get("state") != "glossary":
                continue
            jp = text.decode(b).strip()
            for c in cats:
                d = g.get(c, {})
                # 성별 표식이 붙은 변종으로만 정본에 있는 것이 있다(スティングビートル♀ 등)
                cand = d.get(jp) or d.get(f"{jp}♀") or d.get(f"{jp}♂")
                if cand:
                    if cand.rstrip("♀♂") != kr:
                        out.append((key, jp, kr, cand.rstrip("♀♂")))
                    break
    return out


# 「가타카나 한 덩어리인데 우리 표기에 공백」 — `docs/naming.md` 의 음차+음차 규칙. 정당한 예외는
# 원문에 번역한 보통명사가 섞인 자리뿐이고(`レストナキノコ` → 레스토나 버섯), 그건 원문이 한 덩어리가
# 아니라 여기 안 걸린다. 정본 쪽은 `shared/glossary/tests/test_glossary.py` 가 같은 걸 본다.
_KATAKANA_RUN = re.compile(r"^[゠-ヿー・]+$")


def check_naming() -> list[tuple[str, str, str]]:
    """우리 초벌이 음차+음차를 띄어 쓰고 있나 — 정본이 안 든 낱말은 이쪽이 유일한 그물이다."""
    rom = common.rom_bytes()
    cur = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    out = []
    for code in text.DICT_TABLES:
        for i, b in enumerate(text.dict_entries(code, rom)):
            key = f"{code:02X}:{i:02X}"
            kr = cur.get(key, {}).get("kr")
            jp = text.decode(b).strip()
            if kr and " " in kr and _KATAKANA_RUN.match(jp):
                out.append((key, jp, kr))
    return out


# PS1 정본과 갈리면 안 되는 어휘 — (쓰면 안 되는 말, 써야 하는 말, 근거).
# **왜 목록인가**: 같은 개념을 두 트랙이 다르게 옮기면 한 시리즈가 두 말을 한다. PS1 은 1회차
# 인게임 QA 를 닫았으니 그쪽이 정본이고, 우리는 **플랫폼 제약으로만** 갈릴 수 있다(docs/deviations.md).
# ⚠ 낱말만 본다 — 문장 구조는 원문이 다르면 갈리는 게 맞다.
PS1_TERMS = [
    ("대미지", "피해", "PS1 `%d의 피해!!`(textmap/battle.json)"),
    ("데미지", "피해", "〃"),
    ("싸움에서 패", "전투에서 패", "PS1 `은(는) 전투에서 패했습니다.`"),
    ("가지고 있었다", "갖고 있었다", "PS1 `을(를) 갖고 있었다.`"),
    ("쓰러뜨렸다", "해치웠다", "PS1 `을(를) 해치웠다.`"),
]


def check_terms() -> list[tuple[str, str, str]]:
    """번역 정본 셋(조각·사전·메뉴)에 PS1 과 갈린 낱말이 있나."""
    out = []
    for name in ("segments.json", "dict.json", "menus.json"):
        data = json.loads((PATH.parent / name).read_text(encoding="utf-8"))
        for k, v in data.items():
            kr = v.get("kr") if isinstance(v, dict) else None
            if not kr:
                continue
            for bad, good, _why in PS1_TERMS:
                if bad in kr:
                    out.append((f"{name}:{k}", bad, good))
    return out


# ── UI 라벨 정본 대조 ────────────────────────────────────────────────────────────────────
# 🔴 **이 게임은 가나 전용이라 정본의 한자 열쇠가 안 맞는다.** 공용 `diff_labels` 가
#    `_aliases` 로 이어 주지만 아직 다 없어서, **못 견준 수를 같이 본다** — 「갈린 데 없다」는
#    **몇 개를 견줬는지를 봐야** 값이 있다(2026-09-08 실측: 44 중 6 만 견주고 초록이었다).
# ⚠ 한 원문이 자리마다 다른 말인 열쇠(`強さ@능력치`)가 있어 **창에 자리를 적는다**
#    (`menus.json` 의 `canon_site`). 자리를 안 대면 셋이 한 말로 뭉개진다.
MENUS_PATH = common.GAME_DIR / "textmap" / "menus.json"


def check_ui_labels() -> dict:
    """{다름, 못 견춘 것, 견준 수} — 게이트는 **다름만** 실패로 친다(못 견춘 건 할 일이다)."""
    sys.path.insert(0, str(common.ROOT / "shared"))
    import glossary

    menus = json.loads(MENUS_PATH.read_text(encoding="utf-8"))
    mine = {}
    for k, v in menus.items():
        if not v.get("kr"):
            continue
        jp = k.split("@")[0]
        site = v.get("canon_site")
        mine[f"{jp}@{site}" if site else jp] = v["kr"]
    out = glossary.diff_labels(mine)
    return {
        "diff": out.diff,
        "unmatched": sorted(set(out.unmatched)),
        "compared": len(mine) - len(out.unmatched),
        "total": len(mine),
    }


def check() -> dict:
    tm = load()
    segs = {
        s["id"]: s
        for s in json.loads(
            (common.OUT_DIR / "units" / "segments.json").read_text(encoding="utf-8")
        )
    }
    bad = []
    unknown = 0
    for k, v in tm.items():
        s = segs.get(k)
        if not s:
            unknown += 1
            continue
        err = check_tokens(v["kr"], s["tokens"])
        if err:
            bad.append((k, err))
    gl = check_glossary()
    nm = check_naming()
    tr = check_terms()
    ui = check_ui_labels()
    return {
        "ui_labels": f"{ui['compared']}/{ui['total']} 견줌 · 다름 {len(ui['diff'])}"
        f" · 못 견줌 {len(ui['unmatched'])}",
        "ui_diff": ui["diff"],
        "ui_unmatched": ui["unmatched"],
        "entries": len(tm),
        "unknown_id": unknown,
        "token_errors": len(bad),
        "sample": bad[:3],
        "glossary_drift": len(gl),
        "glossary_sample": gl[:5],
        "naming_space": len(nm),
        "naming_sample": nm[:5],
        "ps1_terms": len(tr),
        "ps1_term_sample": tr[:5],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--init-from-tm",
        type=float,
        metavar="RATIO",
        help="유사도 ≥RATIO 인 조각을 tm-draft 로 넣는다",
    )
    ap.add_argument("--check", action="store_true", help="토큰 계약 검사(원문 덤프 필요)")
    ap.add_argument(
        "--init-dict", action="store_true", help="사전 6벌을 glossary 로 채운다(textmap/dict.json)"
    )
    ap.add_argument(
        "--init-menus",
        action="store_true",
        help="메뉴 라벨을 PS1 확정 표기로 채운다(textmap/menus.json)",
    )
    a = ap.parse_args()
    if a.init_dict:
        print(init_dict())
    if a.init_menus:
        print(init_menus())
    if a.init_from_tm is not None:
        print(init_from_tm(a.init_from_tm))
    if a.check:
        r = check()
        print(r)
        if (
            r["token_errors"]
            or r["unknown_id"]
            or r["glossary_drift"]
            or r["naming_space"]
            or r["ps1_terms"]
            or r["ui_diff"]  # ⚠ `ui_unmatched` 는 실패가 아니다 — 정본에 없는 열쇠는 할 일이다
        ):
            raise SystemExit(1)
