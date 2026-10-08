"""공용 이름 검사(`scripts/check/check_names.py`)의 pce-ed1 어댑터 — `(자리, 원문 줄, 우리 줄|None, 갈래)` 를 문안 전체에 대해 낸다.

🔴 이름을 **들지 않는다**(마스터 10-07 「워커는 독자 데이터를 못 갖는다」) — 원문(`work/derived/`)과 우리 문안(`script/`)을
읽어 짝지어 넘길 뿐이다. 미번역 줄은 None 으로 낸다(분모에 든다). 화면에 나가는 값을 그대로 넘기려고, 빌드가 고르는 것과
같은 순서로 우리 줄을 고른다(시스템 고정표 = `names.json` 덮어쓰기 → 사전 · 전투 이름칸 = `battle.kr_names`).

갈래(마스터 10-07 「대사·비대사를 나눠라」): `"dialog"` = 대사 창에 흐르는 글(씬 대사 · 전투 문구 · 시스템 메시지 — 이어 쓰는
문장이라 지명을 띄어 쓴다) · `"slot"` = 칸에 담긴 이름(입장 배너 `scn000` 의 `raw` 항목 · 지명·파일 선택·아이템·주문 고정표 · 메뉴 라벨 ·
부팅 화면 · 전투 이름칸 · HUD 판 — 칸 폭에 맞춰 붙여 쓴다). 오프닝·엔딩 자막은 원문 글이 없어 이 어댑터가 안 낸다(아래).

자리 이름 규약: `scnNNN:<열쇠>` · `battle:<열쇠>` · `battle-name:<rel>:<블록>:<오프셋>` · `sysmsg:<주소>` ·
`fixed:<가족>#<순번>` · `label:<주소>` · `screen:<열쇠>#<줄>` · `extras:<열쇠>#<항목>` · `inline:<열쇠>` · `hud:<원문>`.

원문 **글**이 없는 자리(오프닝·엔딩 음성 자막 · 장 제목 띠 · 엔딩 카드 · 오마케 간판)는 `jp` 를 빈 줄로 **우리 줄만** 낸다(`_subs`) —
이름 검사는 못 하지만(짝이 없다) 화면 일본어 게이트는 우리 줄의 가나·한자를 잡는다. 도감(rel 459~463)은 `_dex` — 미착수라 우리 줄 None.
⚠ 스태프롤(`staffroll.py`)은 안 낸다 — 사람 이름만 원문이 남는 게 확정이라 일본어 게이트가 늘 울리고, 이름 표는 게임 폴더에 두는 예외(마스터 10-08).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle
import common
import hud_plate
import messages as M
import sysbuild
import sysstrings as S

CANON = "ed1"  # 공통 문안 정본(`shared/canon/ed1.json` — PS1 씨앗, 마스터 10-08) — `check_canon.py` 가 읽는다
CANON_GATE = True  # 어긋남 0(승인 예외 제외)이면 켠다 — 켜면 `check_canon` 어긋남이 실패다

DERIVED = common.GAME_DIR / "work" / "derived"
SCRIPT = common.GAME_DIR / "script"


def _load(p: Path):
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def _scenes():
    for p in sorted((DERIVED / "messages").glob("scn*.json")):
        kr = M.load_translations(int(p.stem[3:]))  # 입장 배너(scn000)는 사전에서 풀린 문안
        for r in json.loads(p.read_text("utf-8")):
            e = kr.get(r["key"]) or {}
            # `raw` = 씬 0 의 입장 배너 표(원판이 가운데맞춤 공백을 구워 낸 고정폭 칸) — 비대사
            yield (
                f"{p.stem}:{r['key']}",
                r["jp"],
                e.get("t") or None,
                "slot" if e.get("raw") else "dialog",
            )


def _battle():
    kr = _load(SCRIPT / "sys" / "battle.json").get("messages", {})
    for k, r in _load(DERIVED / "battle" / "messages.json").items():
        yield (f"battle:{k}", r["tokens"], kr.get(k), "dialog")
    names, _missing = battle.kr_names()
    for jp, spots in battle.names().items():
        for rel, blk, off in spots:
            yield (f"battle-name:{rel}:{blk}:{off:04X}", jp, names.get(jp), "slot")


def _system():
    msgs = _load(SCRIPT / "sys" / "sysmsg.json").get("messages", {})
    for r in S.read_sysmsg():
        yield (f"sysmsg:{r['addr']:04X}", r["jp"], msgs.get(r["key"]), "dialog")
    names = _load(SCRIPT / "sys" / "names.json")
    gl = sysbuild.glossary()
    for fam in S.FIXED:
        for r in S.read_fixed(fam):
            if r["jp"]:
                kr = sysbuild.fixed_kr(fam, r["jp"], names, gl)
                yield (f"fixed:{fam}#{r['i']}", r["jp"], kr, "slot")
    for r in S.read_labels():
        yield (
            f"label:{r['addr']:04X}",
            r["jp"],
            sysbuild.label_kr(r),
            "slot",
        )  # 정본 ui 에서 읽은 라벨(+ labels.json 잔여)
    screens = _load(SCRIPT / "sys" / "screens.json")
    for sc in S.read_screens():
        kr = screens.get(sc["key"])
        for i, ln in enumerate(sc["lines"]):
            yield (
                f"screen:{sc['key']}#{i}",
                ln["jp"],
                kr[i] if kr and i < len(kr) else None,
                "slot",
            )
    extras = _load(SCRIPT / "sys" / "extras.json")
    for ex in S.read_extras():
        kr = extras.get(ex["key"])
        for i, jp in enumerate(ex["items"]):
            yield (f"extras:{ex['key']}#{i}", jp, kr[i] if kr and i < len(kr) else None, "slot")
    inline = _load(SCRIPT / "sys" / "inline.json")
    for r in S.read_inline():
        yield (f"inline:{r['key']}", r["jp"], inline.get(r["key"]), "slot")


def _hud():
    for _off, jp, kr in hud_plate.PLATES:
        yield (f"hud:{jp}", jp, kr, "slot")
    for _tiles, jp, kr in hud_plate.STATUS:
        yield (f"hud:{jp}", jp, kr, "slot")


DEX_REL, DEX_SPAN = (
    459,
    (0x300, 4 * 2048 + 0x200),
)  # 몬스터 도감(rel 459~463) — 원문 평문. 번역 미착수(status 「남은 일」)


def _dex():
    """도감 원문 줄(우리 줄 None — 미착수). 검사기 분모에 들이고, 화면 일본어 게이트는 **알림으로만** 센다(`check_jp_left.DEFERRED`)."""
    import coverage_scan as C

    d = common.track_data(DEX_REL, 5)
    for off, text in C.runs(d[DEX_SPAN[0] : DEX_SPAN[1]], min_chars=2):
        yield (f"dex:{DEX_REL}:{DEX_SPAN[0] + off:04X}", text, None, "dialog")


def _subs():
    """원문 글이 없는 출처(음성 자막 · 그림 글자) — `jp` 는 빈 줄. 우리 줄만 낸다 → 화면 일본어 게이트가 우리 줄의 가나·한자를 잡는다."""
    import chapter_band
    import gfx_text

    for name in ("opening_sub", "ending_sub"):
        for i, ln in enumerate(_load(SCRIPT / f"{name}.json").get("lines", [])):
            yield (f"{name}:{i}", "", ln[2], "dialog")
    for i, t in enumerate(chapter_band.KR_TITLES):
        yield (f"chapter-band:{i}", "", t, "slot")
    for i, (t, *_rest) in enumerate(gfx_text.CARD_LINES):
        yield (f"gfx-card:{i}", "", t, "slot")
    yield ("gfx-banner:0", "", gfx_text.BANNER_TEXT, "slot")


def pairs():
    """문안 전체 — 원본 파생물(`work/derived/`)이 없으면 빈 목록(이 트리는 못 잰다)."""
    if not (DERIVED / "messages").exists():
        return []
    return [*_scenes(), *_battle(), *_system(), *_hud(), *_dex(), *_subs()]


if __name__ == "__main__":
    ps = pairs()
    print(len(ps), sum(1 for p in ps if p[2] is not None))
