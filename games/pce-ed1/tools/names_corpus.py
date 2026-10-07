"""공용 이름 검사(`scripts/check/check_names.py`)의 pce-ed1 어댑터 — `(자리, 원문 줄, 우리 줄|None, 갈래)` 를 문안 전체에 대해 낸다.

🔴 이름을 **들지 않는다**(마스터 10-07 「워커는 독자 데이터를 못 갖는다」) — 원문(`work/derived/`)과 우리 문안(`script/`)을
읽어 짝지어 넘길 뿐이다. 미번역 줄은 None 으로 낸다(분모에 든다). 화면에 나가는 값을 그대로 넘기려고, 빌드가 고르는 것과
같은 순서로 우리 줄을 고른다(시스템 고정표 = `names.json` 덮어쓰기 → 사전 · 전투 이름칸 = `battle.kr_names`).

갈래(마스터 10-07 「대사·비대사를 나눠라」): `"dialog"` = 대사 창에 흐르는 글(씬 대사 · 전투 문구 · 시스템 메시지 — 이어 쓰는
문장이라 지명을 띄어 쓴다) · `"slot"` = 칸에 담긴 이름(입장 배너 `scn000` 의 `raw` 항목 · 지명·파일 선택·아이템·주문 고정표 · 메뉴 라벨 ·
부팅 화면 · 전투 이름칸 · HUD 판 — 칸 폭에 맞춰 붙여 쓴다). 오프닝·엔딩 자막은 원문 글이 없어 이 어댑터가 안 낸다(아래).

자리 이름 규약: `scnNNN:<열쇠>` · `battle:<열쇠>` · `battle-name:<rel>:<블록>:<오프셋>` · `sysmsg:<주소>` ·
`fixed:<가족>#<순번>` · `label:<주소>` · `screen:<열쇠>#<줄>` · `extras:<열쇠>#<항목>` · `inline:<열쇠>` · `hud:<원문>`.

⚠ 안 내는 구간 — 원문 **글**이 없는 자리: 오프닝·나레이션 음성 자막(`script/opening_sub.json` · 음성뿐) · 엔딩 자막
(`ending_sub.json`) · 그림 글자(장 제목 띠 `chapter_band.KR_TITLES` · 엔딩 카드 `gfx_text`). 원문 줄이 없어 짝을 못 짓는다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle
import common
import hud_plate
import sysbuild
import sysstrings as S

DERIVED = common.GAME_DIR / "work" / "derived"
SCRIPT = common.GAME_DIR / "script"


def _load(p: Path):
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def _scenes():
    for p in sorted((DERIVED / "messages").glob("scn*.json")):
        kr = _load(SCRIPT / p.name).get("messages", {})
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
                kr = names.get(fam, {}).get(r["jp"], gl.get(r["jp"]))
                yield (f"fixed:{fam}#{r['i']}", r["jp"], kr, "slot")
    labels = _load(SCRIPT / "sys" / "labels.json")
    labels = labels.get("labels", labels)
    for r in S.read_labels():
        kr = labels.get(f"@{r['addr']:04X}", labels.get(r["jp"]))
        yield (f"label:{r['addr']:04X}", r["jp"], kr if isinstance(kr, str) else None, "slot")
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


def pairs():
    """문안 전체 — 원본 파생물(`work/derived/`)이 없으면 빈 목록(이 트리는 못 잰다)."""
    if not (DERIVED / "messages").exists():
        return []
    return [*_scenes(), *_battle(), *_system(), *_hud()]


if __name__ == "__main__":
    ps = pairs()
    print(len(ps), sum(1 for p in ps if p[2] is not None))
