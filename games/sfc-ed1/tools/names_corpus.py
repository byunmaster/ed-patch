"""sfc-ed1 이름 검사 어댑터 — `pairs()` 가 `(자리, 원문 줄, 우리 줄|None)` 을 문안 전체에 대해 낸다.

🔴 이름 표를 **들지 않는다**(마스터 2026-10-07 — 워커는 독자 데이터를 못 갖는다). 원문·문안을
읽어 넘길 뿐이고, 잣대는 공용 `shared/canon/names.py` 하나다.

- **대사·전투·시스템** — `units.segments()`(END 로 끝나는 조각, `textmap/segments.json` 의 키와
  같다)를 그대로 돈다. 사전 치환(`{D3:08}` 등)은 `text.decode()` 가 이미 그 자리의 **원문을
  풀어 중괄호로 박아 두므로**(히라가나 표기까지 그대로) 따로 더 풀 필요가 없다 — 이게 바로
  `ほのおのつるぎ` 를 찾아낸 자리다(07C441, status.md 참조).
- **칸** — 갈래 `slot`: 사전 항목 · `places.json`(HUD·슬롯 지명) · `menus.json`(메뉴 라벨). 문장은 `dialog`.
- **사전 D0~D5 항목 자체** — `textmap/dict.json` 의 각 칸도 원문·문안 쌍이다(사전 항목도
  화면에 그대로 나간다).

미번역(`kr` 이 없는) 자리는 `None` 으로 낸다 — 분모(`units`)에는 들지만 이름 비교는 안 한다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001  (common 보다 먼저)
import common
import textmap
import namesrc
import units

CANON = "ed1"  # 공통 문안 정본 — PS1 기반(마스터 10-08)
CANON_GATE = True  # 전환을 마쳤다 — check_canon.py 가 어긋남을 실패로 친다(마스터 10-08)

# 우리 문안은 사전 치환 자리를 **토큰으로 품는다**(`{D0:80}` 등, 화면에선 런타임에 사전 칸의
# 한국어로 풀린다 — `units.py:token_of`). 원문 쪽은 `text.decode()` 가 이미 그 자리를 풀어
# 문자 그대로 박아 두므로, 우리 쪽도 같은 자리에서 **사전 문안의 번역**으로 풀어야 둘이
# 같은 말을 비교한다 — 안 풀면 「세리오스」 같은 이름이 전부 「우리 줄에 없다」로 오탐 난다.
_DICT_TOKEN = re.compile(r"\{([0-9A-F]{2}):([0-9A-F]{2})\}")


def _resolve_tokens(kr, dict_cur):
    """`text.decode()` 와 같은 규칙 — `$D0 8x` 는 강조색 표시고 실제 항목은 `x&$7F`
    (`text.py:decode`). 안 맞추면 `{D0:80}` 이 D0 표 0x80 번(표 밖)을 찾다 늘 빈다."""

    def repl(m):
        code, idx = m.group(1), int(m.group(2), 16)
        if code == "D0":
            idx &= 0x7F
        v = dict_cur.get(f"{code}:{idx:02X}", {})
        return v.get("kr") or m.group(0)

    return _DICT_TOKEN.sub(repl, kr)


def _bare(jp):
    """`text.decode()` 가 사전 치환 자리에 박은 `{…}` 를 벗긴 원문 글자 그대로 — 중괄호가
    가타카나 낱말(`キャリオンク{ロー}ラー`)을 끊으면 낱말 경계 검사가 무력해진다."""
    return jp.replace("{", "").replace("}", "")


# 🔴 줄 끝·자리 제어 태그를 걷는다 — 정본 검사(`canon.audit`)는 **줄 전체**(`^…$`)로 대조하는데 어댑터가 `<END>`·`<CLEAR>`·
#   `<COLOR_C>…` 를 그대로 내면 전투·시스템 문구가 **하나도 안 잰다**(md 실측 10-08: 어긋남 0 인데 실제론 129).
#   원문 쪽 이름 자리(`<COLOR_C><D6><COLOR_POP>`)는 `{name}`, 수치(`<DC>`)는 `{n}`, 우리 쪽 `<E3>{D6}<E1>` 도 같다.
_JP_NAME = re.compile(r"<COLOR_C><D[0-9A-F]><COLOR_POP>")
_JP_NUM = re.compile(r"<D[0-9A-F]>")
_KR_NAME = re.compile(r"<E3>\{D[0-9A-F]\}<E1>")
_KR_NUM = re.compile(r"\{D[0-9A-F]\}")
_KR_JOSA = re.compile(r"\{(은|이|을|과|와|으로)/(는|가|를|와|과|로)\}")
# 강조색 태그(`<COLOR_C>…<COLOR_POP>` · `<E3>…<E1>`)는 **리터럴 이름 둘레에 남긴다** — 이름 검사가 이름과 옆 가타카나 낱말을 가르는 경계로 쓴다
#   (`アクダム\nウググ` 처럼 붙으면 한 낱말로 읽혀 이름 출현 27건이 사라졌다). 이름·수치 자리(`<COLOR_C><D6><COLOR_POP>`)는 위에서 이미 자리표가 됐다.
#   그 밖의 제어 태그(`<END>`·`<CLEAR>`·`<JUMP …>`·`<EF>`·`<E0>` …)는 경계 글자로 바꾸고 양끝은 뗀다.
_KEEP = r"COLOR_C|COLOR_POP|COLOR_4|E1|E3"
_TAG = re.compile(rf"<(?!(?:{_KEEP})>)[^<>]*>")
_SEP = "|"


def norm_jp(jp):
    """원문 줄 → 정본 열쇠 꼴(자리표 `{name}`·`{n}`, 태그 없음)."""
    return _TAG.sub(_SEP, _JP_NUM.sub("{n}", _JP_NAME.sub("{name}", jp))).strip(_SEP + " \n")


def norm_kr(kr):
    """우리 줄 → 정본 값 꼴(`{은/는}` → `은(는)`, 이름·수치 자리표, 태그 없음)."""
    kr = _KR_JOSA.sub(lambda m: f"{m.group(1)}({m.group(2)})", _KR_NAME.sub("{name}", kr))
    return _TAG.sub(_SEP, _KR_NUM.sub("{n}", kr)).strip(_SEP + " \n")


def _segment_pairs(rom, dict_cur, raw=False):
    items, _ = units.extract(rom)
    res = text.resolver(rom)
    tm = textmap.load()
    for s in units.segments(items, res):
        v = tm.get(s["id"])
        kr = v.get("kr") if v else None
        yield (
            f"seg:{s['id']}@{s['addr']}",
            _bare(s["jp"]) if raw else norm_jp(_bare(s["jp"])),
            (_resolve_tokens(kr, dict_cur) if raw else norm_kr(_resolve_tokens(kr, dict_cur))) if kr else None,
            "dialog",
        )


def _dict_pairs(rom, dict_cur):
    for code in text.DICT_TABLES:
        for i, b in enumerate(text.dict_entries(code, rom)):
            key = f"{code:02X}:{i:02X}"
            jp = text.decode(b).strip()
            kr = dict_cur.get(key, {}).get("kr")
            yield f"dict:{key}", jp, kr or None, "slot"


def _slot_pairs():
    """HUD·슬롯 지명(`places.json`)과 메뉴 라벨(`menus.json`) — 고정 폭 칸이다."""
    tdir = common.GAME_DIR / "textmap"
    for jp, kr in namesrc.places_map()["names"].items():
        yield f"place:{jp}", jp, kr or None, "slot"
    for key, v in namesrc.menus().items():
        yield f"menu:{key}", key.split("@")[0], v.get("kr") or None, "slot"


def _extra_pairs(rom):
    """빌드가 화면에 내는데 위 셋(대사·사전·칸) 밖에 있던 출처 — 전투 UI 라벨 · 장 제목 · 스태프롤(2026-10-08 커버리지 점검).
    PS1 월드맵 지명이 검사기 분모 밖이라 일본어로 남았던 것과 같은 구멍을 막는다."""
    bu = namesrc.battle_ui()
    for g in bu.get("grid", []):
        for c in g["cols"]:
            yield f"ui:grid@{g['addr']}+{c['at']}", c["jp"], c.get("kr") or None, "slot"
    for key in ("names", "title"):
        for x in bu.get(key, []):
            yield f"ui:{key}@{x['addr']}", x["jp"], x.get("kr") or None, "slot"
    for key in ("speed", "yesno", "flee", "retry", "loose", "a4_labels", "a3_values", "a4_values"):
        for i, x in enumerate(bu.get(key, [])):
            yield f"ui:{key}[{i}]", x["jp"], x.get("kr") or None, "slot"
    for i, x in enumerate(namesrc.chapters()["titles"]):
        yield f"chapter:{i + 1}", x["jp"], x.get("kr") or None, "slot"
    import hud_names

    for jp, kr in zip(hud_names.JP_NAMES, hud_names.NAMES, strict=True):
        yield f"hud:{jp}", jp, kr, "slot"  # HUD 인물 이름 8×8 타일(`hud_names.NAMES` — 사전과 어긋나면 여기서 잡는다)
    import credits


def credits_pairs(rom):
    """스태프롤 — **정본 대상이 아니다**(마스터 10-08: 제작진은 게임마다 다르다). 이름·정본 검사 분모엔 안 넣고 화면 일본어(F7) 분모에만 든다."""
    import credits

    # 빈 줄(원문·번역 둘 다 비었다)은 건너뛰고, 번역이 비었는데 원문이 있는 줄은 **앞 줄에 합쳐 쓴 것**이다
    # (「けんきゅうかいはつ / センター」 → 「연구개발 센터」 한 줄, devlog 09-26) — 앞 줄 원문에 붙인다.
    o = common.snes2off(credits.ORIG)
    acc: list[list] = []
    for i, kr in enumerate(credits.rows()):
        jp = text.decode(rom[o + i * credits.ROW_CELLS : o + (i + 1) * credits.ROW_CELLS]).strip()
        if not jp and not kr.strip():
            continue
        if jp and not kr.strip() and acc:
            acc[-1][1] += jp
            continue
        acc.append([f"credits:{i}", jp, kr.strip() or None])
    for where, jp, kr in acc:
        yield where, jp, kr, "slot"


def pairs(raw=False):
    """`raw=True` 는 태그·조사 훅 표기를 그대로 둔다(조사 검사·화면 일본어 검사가 쓴다) — 기본은 정본 대조 꼴."""
    rom = common.rom_bytes()
    dict_cur = namesrc.dict_map(rom)
    yield from _segment_pairs(rom, dict_cur, raw)
    yield from _dict_pairs(rom, dict_cur)
    yield from _slot_pairs()
    yield from _extra_pairs(rom)


def screen_pairs():
    """화면에 나가는 칸 전부 — 이름·정본 검사 분모(`pairs`) + 스태프롤(정본 대상은 아니지만 일본어가 남으면 결함이다)."""
    rom = common.rom_bytes()
    yield from pairs()
    yield from credits_pairs(rom)


if __name__ == "__main__":
    n = sum(1 for _ in pairs())
    print(f"자리 {n:,}")
