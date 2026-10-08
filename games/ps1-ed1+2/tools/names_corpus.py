"""이름 검사 어댑터 — `scripts/check/check_names.py --game ps1-ed1+2` 가 부른다.

🔴 **이름을 들지 않는다.** 화면에 나가는 문안을 **「원문 줄 · 우리 줄」 쌍**으로 읽어 넘길 뿐이고,
어느 이름이 맞는지는 공용 사전(`shared/glossary`)이 정한다(마스터 2026-10-07 — 독자 데이터 금지).
미번역 줄은 `None` 으로 낸다(분모가 거짓말을 안 하게).

읽는 곳(자리 표기가 곧 출처다):

- `ED1SCN<n>:<eid>` · `ED2SCN<n>:<eid>` — 장면 대사. 원문은 장면 파일의 블록, 우리 줄은 `script/<씬>.json` 의 `t`.
  우리 줄은 **재조립 바이트를 되읽은 것**(`render_bytes(build_candidate(...))` — 이름이 방출 바이트에 박히는 꼴까지 화면 그대로)이고,
  못 그린 블록은 script `t` 로 대신 재며 수를 센다(`UNRENDERED`, stderr 로 알린다).
  `#이름창n` 은 블록 안 창마다 하나 — 우리 쪽도 방출 바이트의 `%c이름%c` 에서 읽는다.
- `ED1전투:<오프셋>` — ED1 전투 문자열(`patch_items.corpus_strings` ↔ `battle_kr`: battle.json · items_battle.json · 표).
- `ED2전투:<오프셋>` — ED2 전투 문자열(`patch_ed2_battle.plan()`: battle_ed2.json · 공용 표). 번역 없는 것은 None.
- `ED2몬스터대사:<n>` — `textmap/monster_lines_ed2.json`.
- `ED1UI:<오프셋>` · `ED2UI:<오프셋>` — EXE 시스템 문자열(메뉴·상태창·전투 라벨·지명 목록·워프).
- `표:<이름>` — 도구의 JP→KR 표(아이템·몬스터·인물·지명) 항목. **표를 새로 들지 않는다** — 이미 있는 번역 쌍을 줄로 읽는다.

⚠ **안 보는 구간**(분모에 안 든다 — 보고에 적는다): 오프닝·엔딩 내레이션(`textmap/opening*`·`ending*` 은 원문이 해시 키라
원문 줄이 없다) · ED2MON 몬스터 대사(`script/ED2MON_LINES.json`, 같은 이유) · 그림으로 된 글자(HUD 이름표 TIM) ·
ED.EXE·ED2.EXE 시스템 문자열 중 `patch_sys_ui`·`patch_ed2_sys` 가 전용 경로로 쓰는 것.
"""

import contextlib
import io
import json
import os
import re
import sys

_TOOLS = os.path.dirname(os.path.abspath(__file__))
_GAME = os.path.dirname(_TOOLS)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
os.environ.setdefault("LOCK_BYPASS", "1")

TITLE = "eiyuu"
# 정본(`shared/canon`)은 메뉴·호칭·시스템·전투 문구 — 장면 대사(`ED1SCN…`·`ED2SCN…`)는 범위 밖이다(마스터 10-08).
# 같은 원문이라도 장면 대사는 장면 문체(정중체 「건넸습니다」 등)로 옮긴다.
CANON_SKIP = r"SCN\d"
CANON_GATE = True

ED1_SCENES = [f"ED1SCN{i}" for i in range(1, 7)]
ED2_SCENES = [f"ED2SCN{i}" for i in range(1, 14)]

_CTRL = re.compile(r"%[cdsx]|\{p\}|[-\x00-\x1f]")
_WS = re.compile(r"\s+")
_PLATE = re.compile(r"%c([^%\n]{1,24})%c\n")
# 우리 쪽 이름창은 **창 머리**(블록 처음 · 앞 창의 `%c` 바로 뒤 · 개행 뒤)에서만 친다 — 본문 끝의 색 칠한 이름
# (`아,%c아트라스 왕자님.%c\n`)을 이름창으로 읽으면 본문에서 이름이 빠진다. 원문 쪽은 명령 바이트가 앞에 붙을 수 있어 느슨하다.
_PLATE_OURS = re.compile(r"(?:^|(?<=%c)|(?<=\n))%c([^%\n]{1,24})%c\n")


def _ours(text):
    """우리 줄에서 제어를 걷는다. **띄어쓰기는 남긴다**(대사 속 지명은 띄어쓰기까지 잰다 — 마스터 10-07).
    줄바꿈·하드 개행·붙임 공백(`\ue003`)은 공백 하나로 — 이름이 줄 끝에서 갈려도 띄어쓰기 자리에서 난다."""
    t = (text or "").replace("\ue003", " ").replace("\ue000", " ").replace("\n", " ")
    return _WS.sub(" ", _CTRL.sub("", t)).strip()


def _jp(text):
    return _CTRL.sub("", text)


def _quiet():
    return contextlib.redirect_stdout(io.StringIO())


UNRENDERED = []  # 우리 줄을 「화면 바이트」로 못 그린 블록 — 대신 script 문안을 넘기고 수만 센다


def _blocks(R, scn):
    """`(eid, JP raw, 재조립 바이트 | None)` — `R.iter_candidates` 와 같은 순회인데 **못 만든 블록도 낸다**
    (공용 순회는 조용히 건너뛰어 몇 개를 못 그렸는지 알 수 없다)."""
    with open(os.path.join(R.OUT_DIR, "scn_jp", f"{scn}.json"), encoding="utf-8") as f:
        doc = json.load(f)
    raw = {e["entry_id"]: bytes.fromhex(e["raw_hex"]) for e in doc["entries"] if e.get("raw_hex")}
    with _quiet(), R.overlay_for(scn):
        tr, _, _ = R.load_translations(scn.replace("SCN", "_SCN"), scn)
        for eid, t in sorted(tr.items()):
            if eid not in raw:
                continue
            try:
                cand, _why = R.build_candidate(raw[eid], t, eid)
            except Exception:  # noqa: BLE001 — 검사기는 빌드를 안 세운다
                cand = None
            yield eid, raw[eid], cand


def _scene_pairs():
    with _quiet():
        import reinsert_kr_pilot as R
    smap = R._speaker_map()
    for scn in ED1_SCENES + ED2_SCENES:
        path = os.path.join(_GAME, "script", f"{scn}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            script = json.load(f)
        for eid, jp, cand in _blocks(R, scn):
            text = jp.decode("cp932", errors="replace")
            # 이름창 = `%c이름%c` 바로 뒤에 개행이 오는 것 — 창마다 하나씩 있고 블록 한복판에도 나온다(화자가 바뀐다).
            # 줄 속 색 칠함(`%c이름%c을 …`)은 개행이 안 따라와 본문으로 남는다. 우리 쪽 이름창도 같은 꼴로 떼어
            # 본문과 따로 잰다 — 안 떼면 화자 이름이 「본문에 이름이 없다」로 어긋남으로 잡힌다.
            jp_plates = _PLATE.findall(text)
            jp_body = _PLATE.sub("", text)
            ent = script.get(str(eid))
            t = ent.get("t") if isinstance(ent, dict) else None
            if t is None:
                ours_body, our_plates = None, []  # 번역 없는 블록(표·제어) — 분모에만 든다
            elif cand is not None:
                # 🔴 화면에 나가는 바이트가 기준이다 — 이름이 런타임 인자가 아니라 **방출 바이트에 박히는**
                #   꼴(`%c윌 통행증%c을 받았습니다`)은 script 의 `t` 에 이름이 없어서 `t` 만 보면 빠진다.
                shown = R.render_bytes(cand)
                our_plates = _PLATE_OURS.findall(shown)
                ours_body = _ours(_PLATE_OURS.sub("", shown))
            else:
                UNRENDERED.append(f"{scn}:{eid}")
                our_plates, ours_body = [], _ours(t)
            for n, name in enumerate(jp_plates):
                shown_name = our_plates[n] if len(our_plates) == len(jp_plates) else smap.get(name)
                yield f"{scn}:{eid}#이름창{n}", name, shown_name, "slot"
            jb = _jp(jp_body)
            # 본문이 **이름 하나뿐**(짧고 문장부호·공백 없음)이면 HUD·입장 배너 칸이다 — 대사가 아니다(칸 꼴로 잰다).
            kind = (
                "slot"
                if 0 < len(jb.strip()) <= 12 and not re.search(r"[。、！？!?…･ 　]", jb.strip())
                else "dialog"
            )
            yield f"{scn}:{eid}", jb, ours_body, kind
    if UNRENDERED:
        print(
            f"names_corpus: 화면 바이트로 못 그린 장면 블록 {len(UNRENDERED)} (script 문안으로 대신 잼)",
            file=sys.stderr,
        )


def _battle_ed1_pairs():
    import patch_items as P

    orig = P.extract(P.ED_LBA, P.ED_SIZE)
    for off, _end, jp in P.corpus_strings(orig):
        kr = P.battle_kr(jp)
        yield f"ED1전투:{off:#x}", _jp(jp), _ours(kr) if kr is not None else None, "dialog"


def _battle_ed2_pairs():
    import patch_ed2_battle as B2

    fit, over, none = B2.plan()
    for fo, jp, kr, _slot in fit + over:
        yield f"ED2전투:{fo:#x}", _jp(jp), _ours(kr), "dialog"
    for fo, jp in none:
        yield f"ED2전투:{fo:#x}", _jp(jp), None, "dialog"


def _monster_line_pairs():
    with open(os.path.join(_GAME, "textmap", "monster_lines_ed2.json"), encoding="utf-8") as f:
        lines = json.load(f)
    for i, (jp, kr) in enumerate(lines.items()):
        if jp == "_":
            continue
        yield f"ED2몬스터대사:{i}", _jp(jp), _ours(kr), "dialog"


def _table_pairs():
    with _quiet():
        import align_jp_kr
        import patch_items
        import patch_sys_ui
    tables = {
        "NAMES": patch_items.NAMES,
        "MONSTERS": patch_items.MONSTERS,
        "SPEAKER_DICT": align_jp_kr.SPEAKER_DICT,
        "PLACES": dict(patch_sys_ui.PLACES),
    }
    with open(os.path.join(_GAME, "textmap", "monsters_ed2.json"), encoding="utf-8") as f:
        tables["monsters_ed2"] = json.load(f)
    for name, tbl in tables.items():
        for jp, kr in tbl.items():
            yield f"표:{name}|{jp}", jp, _ours(kr), "slot"


def _ui_pairs():
    """EXE 시스템 문자열 — ED.EXE `patch_sys_ui.UI`(메뉴·상태창·전투커맨드·전투설정) · ED2.EXE `patch_ed2_sys.plan()`(UI·지명·워프 16B·전투 라벨).

    ⚠ 지금까지 이름·정본 검사는 이 표들을 **안 쟀다** — 표 5개(`표:`)만 쟀고, UI 문자열은 정본 ui 와 대조하는 곳이 없었다
    (10-08 전 세션 점검). 원문은 원본 EXE 의 그 오프셋 문자열, 우리 줄은 표(ED2 는 쓸 바이트 `plan()` 의 KR)다.
    """
    with _quiet():
        import patch_ed2_sys as E
        import patch_items as P
        import patch_sys_ui as U

    ed = P.extract(P.ED_LBA, P.ED_SIZE)
    for off, kr in sorted(U.UI.items()):
        jp = E._jp_at(ed, off)
        if jp:
            yield f"ED1UI:{off:#x}", jp, _ours(kr), "slot"
    with _quiet():
        rows, over = E.plan()
    for off, jp, kr, _slot, _enc in rows + over:
        # ⚠ `スロット１·２` 는 정본 ed2 안에서 ui(`슬롯1`)와 system(`슬롯１` 전각)이 **서로 다른 값**이다(같은 원문 두 값) —
        #   관리자가 한 값으로 정하기 전까지 비교에서 뺀다(10-08 후보로 올렸다). 정해지면 이 줄을 지운다.
        if jp in ("スロット１", "スロット２"):
            continue
        # ⚠ ED2.EXE HUD 판(0x9A1F0)·워프 사본(0x9A478)의 狼の口 는 빌드 맨 끝 `restore_full_place_names` 가 「늑대의입」으로
        #   되돌린다(칸이 넉넉한 자리) — `plan()` 은 그 전의 짧은 꼴(늑대입)이라 최종 바이트를 따라 읽는다.
        if jp == "狼の口" and off in (0x9A1F0, 0x9A478):
            kr = "늑대의입"
        yield f"ED2UI:{off:#x}", jp, _ours(kr), "slot"


def pairs():
    """`(자리, 원문 줄, 우리 줄 | None, 갈래)` — 갈래는 "dialog"(대사·전투 문장) · "slot"(이름창·도구 표) — 화면에 나가는 문안 전체(위 모듈 설명의 「안 보는 구간」 제외)."""
    yield from _scene_pairs()
    yield from _battle_ed1_pairs()
    yield from _battle_ed2_pairs()
    yield from _monster_line_pairs()
    yield from _table_pairs()
    yield from _ui_pairs()
