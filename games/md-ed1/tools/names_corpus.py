"""공용 이름 검사 어댑터(`scripts/check/check_names.py`) — **이름을 안 든다**, 원문·문안을 읽어 넘길 뿐이다.

    python3 tools/names_corpus.py --check   # 분모만(블록·스트림 수) 찍는다

`pairs()` = `[(자리, 원문 줄, 우리 줄 또는 None, 갈래)]` (갈래 "dialog" = 메시지 창에 나가는 문장 — script·battle·sysmsg·captions · "slot" = 이름 칸·표 — monsters·names) — **문안 전체**(script 225블록 · battle 110블록 ·
sysmsg · captions · monsters.json · names.json, 압축 해제 기준)에 대해 낸다. 미번역은 None 으로
내서 분모에 들게 한다(마스터 10-07 — 「9/225 만 보고 0건」이 이 구멍이었다).

⚠ **gfx_a/b/c/d 는 뺐다** — 그래픽 카드라 이름 문안이 없다(블록91 지명 표는 script 아카이브
안이라 이미 돈다). sys 아카이브(6블록)는 sysmsg.py 가 코드 참조로 따로 찾아 들어가므로 여기선
블록 단위로 또 돌지 않는다(중복 집계 방지) — `sysmsg.streams()` 가 이미 그 영역을 포함한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import battle
import captions
import common
import dict_names
import field_names
import halfspace
import scene
import sysmsg

CANON = "ed1"  # 공통 문안 정본(shared/canon) — 한 편짜리 게임 어댑터 값
CANON_GATE = True  # 정본 어긋남을 실패로 친다(사전 적용 2단계 전환 끝, 2026-10-08)
DIALOG, SLOT = "dialog", "slot"  # 갈래 — 메시지 창 문장(대사·전투 로그·시스템 메시지·캡션)은 지명 띄어쓰기까지 잰다, 칸·표·로그는 무시(마스터 10-07)


def _script_pairs(rom: bytes):
    import json

    base = archives.ARCHIVES["script"][0]
    bl = archives.blocks(rom, base)
    n_streams = 0
    for n, (_s, data, _e) in enumerate(bl):
        mod = scene.parse_module(data)
        p = common.GAME_DIR / "script" / f"{n:03d}.json"
        kr_map = {}
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            kr_map = d.get("streams", {})
        for off, st in sorted(mod.streams.items()):
            n_streams += 1
            jp = st.text()
            ours = kr_map.get(f"{off:04x}", {}).get("ours") or None
            yield f"script:{n:03d}:{off:04x}", jp, ours, DIALOG


def _battle_pairs(rom: bytes):
    import json

    _names, strs = battle.survey(rom)
    p = common.GAME_DIR / "textmap" / "battle.json"
    kr_map = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    monsters = battle.monsters(rom)
    for k, e in strs.items():
        blk, tgt = e["where"][0][0], e["where"][0][1]
        ent = kr_map.get(k)
        if ent is None:
            # 가려야 하는 자리는 pos_key(블록:대상)로 따로 들어간다(battle.pos_key)
            ent = kr_map.get(battle.pos_key(e["where"][0][3]["stream"], blk, tgt))
        ours = ent.get("ours") if ent else None
        # {JP} 는 몬스터 이름 자리표시자다(재삽입 때 battle.expand_names 가 채운다) — 그대로 두면
        # 「{アクダム}」가 문자 그대로 비교돼 항상 어긋난 것으로 보인다.
        if ours:
            ours = battle.expand_names(ours, monsters)
        yield f"battle:{blk:03d}:{k}", e["text"], ours or None, DIALOG


def _sysmsg_pairs(rom: bytes):
    import json

    strs = sysmsg.streams(rom)
    p = common.GAME_DIR / "textmap" / "sysmsg.json"
    kr_map = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    for addr, e in strs.items():
        jp = sysmsg.render(e["stream"])
        ours = kr_map.get(f"{addr:06x}", {}).get("ours") or None
        yield f"sysmsg:{addr:06x}", jp, ours, DIALOG


def _captions_pairs(rom: bytes):
    import json

    strs = captions.streams(rom)
    p = common.GAME_DIR / "textmap" / "captions.json"
    kr_map = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    for addr, e in strs.items():
        jp = e["stream"].text()
        ours = kr_map.get(f"{addr:06x}", {}).get("ours") or None
        yield f"captions:{addr:06x}", jp, ours, DIALOG


def _monsters_pairs():
    d = battle.monsters(common.rom())
    for jp, v in d.items():
        yield f"monsters:{jp}", jp, (v.get("ours") or None), SLOT


def _names_pairs():
    d = dict_names.names()
    for cat, tbl in d.items():
        if not isinstance(tbl, dict):
            continue
        for idx, ent in tbl.items():
            if not isinstance(ent, dict):
                continue
            jp = ent.get("jp")
            if not jp:
                continue
            yield f"names:{cat}[{idx}]", jp, (halfspace.plain(ent.get("ours") or "") or None), SLOT


def _banner_pairs():
    """입장 배너 지명 46칸(블록 91 표) — 사전·접미 규칙에서 읽은 값(`field_names.banner_kr`)을 잰다."""
    for i, kr, _extra, jp in field_names.ENTRIES:
        yield f"banner:{i:02d}", jp, kr, SLOT


def pairs():
    rom = common.rom()
    yield from _script_pairs(rom)
    yield from _battle_pairs(rom)
    yield from _sysmsg_pairs(rom)
    yield from _captions_pairs(rom)
    yield from _monsters_pairs()
    yield from _names_pairs()
    yield from _banner_pairs()


if __name__ == "__main__":
    n = 0
    for _where, _jp, _ours, _kind in pairs():
        n += 1
    print(f"  names_corpus: 줄 {n}")
