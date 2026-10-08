"""공용 이름 검사 어댑터 — **문안 전체**를 `(자리, 원문 줄, 우리 줄|None, 갈래)` 로 낸다.

    python3 ../../scripts/check/check_names.py --game ss-ed1+2

🔴 **이름을 안 든다**(마스터 2026-10-07). 사전은 `shared/glossary/names.py` 한 곳이 보고,
여기는 **원문을 읽어 우리 줄과 짝짓기만** 한다 — 아이템·몬스터·지명 표를 복사해 두지 않는다.

## 네 층

- **씬 대사** (`script/scn.json` + PS1 `line_dict.json` 저본) — `patch_scn.all_texts()` 와
  같은 길(`load_canon` → `canon_of`)을 걷되 KR 뿐 아니라 **JP 도** 같이 낸다. 미번역은 None.
- **시스템·전투 메시지**(`script/system.json`, `ED.BIN`·`ED2.BIN`·`ED2MON01~10.BIN`) —
  `patch_ui.sys_rows()` 가 이미 JP(9번째 값)·KR 을 짝지어 돌려준다(`check_prose_glossary.py`
  가 같은 길을 쓴다). 매칭된 자리만 있어 None 은 없다 — 이 게임은 "남은 일본어 0" 라
  시스템 메시지 쪽 미번역 잔존이 따로 없다(`check.sh` 가 그 축을 이미 전수로 본다).
- **씬 지명 헤더**(`scn_header`, 498곳) — `patch_ui.scn_rows()`.
- **챕터 카드·시스템 UI 문구**(`cards`·`msgs`, `script/ui.json`) — `patch_ui.card_rows()` ·
  `ui.json` 의 `msgs`(해시 열쇠 — JP 는 디스크에서).

⚠ **원본 이미지만 있으면 된다**(빌드 불필요) — JP 는 디스크(또는 `work/derived/scn_jp` 덤프)
에서, KR 은 전부 커밋된 JSON 정본(`script/*.json`)에서 온다. `check_prose_glossary.py` 가
이미 증명한 패턴이다.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import patch_scn as S
import patch_ui as U

# 제어부호·공백만 있고 **번역할 글자가 없는** 블록 — 분모에서 뺀다(둘 다 아니면 오탐만 는다).
_BARE = re.compile(r"(%[csd]|[\s　])+$")


def _has_text(jp):
    return not _BARE.match(jp)


# 🔴 **갈래**(마스터 10-07 「대사·비대사를 나눠라」) — `"dialog"`(대사: 이야기 씬 `ED1SCN*`·`ED2SCN*` 의
#    대사창) · `"slot"`(그 밖 — HUD·워프·배너·메뉴·표·이름 칸·씬 머리말·시스템/전투 메시지·몬스터 파일).
#    대사 속 지명은 공용 검사가 띄어쓰기까지 잰다. ⚠ 씬 파일 안에도 **지명 한 칸짜리 블록**(선택지·목록
#    항목처럼 줄 전체가 사전 지명 하나)이 있다 — 그건 대사가 아니라 칸이다(`_slot_block`).
_DIALOG_FILE = re.compile(r"^/BIN/ED[12]SCN\d+\.BIN$")


def _slot_block(jp):
    """줄 전체가 사전 지명(place) 하나뿐인 씬 블록 — 칸이다."""
    from canon import table

    global _PLACES
    if _PLACES is None:
        _PLACES = set(table("place", "eiyuu"))
    return jp.replace("\u3000", " ").strip() in _PLACES


_PLACES = None


## `/ED.BIN`·`/ED2.BIN`·`/BIN/ED2MON*.BIN` 은 **씬 덤프와 시스템 덤프가 겹친다** — 같은
## 파일이 `patch_scn`(씬 길, SCN_RE 가 통짜·몬스터 파일도 문다) 과 `patch_ui.sys_rows()`
## (시스템 길) 양쪽에서 읽힌다. 씬 정본(`load_canon`)엔 없고 시스템 정본(`system.json`)
## 에만 있는 조각이 섞여 있어 씬 길에서만 찾으면 **가짜 미번역**이 된다(실측: 두 통짜
## 파일만 빼도 None 1,664→346, 몬스터 파일 10개는 여전히 자리당 25~30% 가 이 겹침이다).
## ⇒ 씬 길이 None 을 내면 **시스템 길이 같은 원문을 이미 번역했는지** 먼저 본다(아래
## `pairs()`). 두 길 다 없을 때만 진짜 미번역이다.
_SCN_BODY_SKIP = {"/ED.BIN", "/ED2.BIN"}


def _scn_pairs(mm):
    canon = S.load_canon(quiet=True)
    if not canon:
        return
    canon = S.augment_names(canon, mm)
    for path, _lba, _size in common.iso_files(mm):
        if not S.SCN_RE.match(path) or path in _SCN_BODY_SKIP:
            continue
        got = S.load(path)
        if not got:
            continue
        sites = S.sites_for(path)
        for e in got[1]:
            jp = e.get("text", "")
            if not jp:
                continue
            eid = e.get("entry_id", e.get("file_offset"))
            where = f"scn:{path}#{eid}"
            site = sites.get(int(e["file_offset"], 16))
            kr = S.canon_of(canon, jp, site)
            yield where, jp, kr


def _sys_pairs(mm):
    for path, _lba, _size, base, _span, _pre, kr, _ptrs, jp in U.sys_rows(mm):
        if not jp:
            continue
        yield f"sys:{path}@0x{base:X}", jp, kr


def _hdr_pairs(mm):
    for path, _lba, _size, base, _fl, jp, kr, _tail in U.scn_rows(mm):
        if not jp:
            continue
        yield f"hdr:{path}@0x{base:X}", jp, kr


def _card_pairs(mm):
    cards, _pad_to_jp, _msgs = U.load_canon()
    if not cards:
        return
    for i, (path, _lba, _size, base, _span, jp, kr) in enumerate(U.card_rows(mm, cards)):
        yield f"card:{path}@0x{base:X}", jp, kr


def _msg_pairs(mm):
    """저장/로드·본체 RAM 안내문 — 새턴 고유 문안(script)이라 JP 는 디스크에서 읽는다(`patch_ui.msg_scan`)."""
    _cards, _pad_to_jp, msgs = U.load_canon()
    for path, _l, _s, at, _sp, _pre, kr, jp in U.msg_scan(mm, msgs):
        yield f"msg:{path}@0x{at:X}", jp, kr


def _item_name_pairs(mm):
    """아이템·주문·몬스터 고유명사 표(516칸, `ED`·`ED2` 본체) — `patch_ui.name_rows()`.

    ⚠ **ED2MON01~10.BIN 의 몬스터 이름 칸(171, `patch_mon_names.py`)은 아직 안 낸다** —
    다른 자리(off·anchor)로 집는 별도 패처라 이번 범위에 못 넣었다. 안 본 구간에 적는다.
    """
    for t in U.name_rows(mm):
        for off, jp, kr, _ptrs in t["recs"]:
            if not jp:
                continue
            yield f"name:{t['path']}@0x{off:X}", jp, kr


def _ui_table_pairs():
    """UI 표 칸(`patch_ui.rows()` — 필드 메뉴·전투 명령·환경설정·**지명 표 셋**…, 본체 둘).

    🔴 **포인터 없는 고정 폭 칸이라 「남은 일본어」 게이트(포인터 대상만 훑는다)가 못 본다**(2026-10-08
       전 세션 점검 — ps1-ed3 월드맵 지명 목록이 같은 구멍으로 일본어로 남았다). 이름 검사에라도 들여
       「정본에 없는 지명」·「원문이 갈린 칸」을 잡는다. KR 이 없는 칸(`kr is None`)은 미번역으로 센다.
    """
    for key, name, i, at, _stride, jp, kr in U.rows():
        if not jp:
            continue
        yield f"ui:{key}/{name}[{i}]@0x{at:X}", jp, kr


def _title_pairs(mm):
    """`TITLE.BIN` 오프닝·엔딩·스태프롤 자막(`script/title.json`) — 구간 안 저장 순서는 화면의 역순."""
    import json

    from dump_title import LABELS, _load, runs

    with open(os.path.join(common.GAME_DIR, "script", "title.json"), encoding="utf-8") as fh:
        kr = json.load(fh)
    for off, recs in runs(_load(mm)):
        name = LABELS[off]
        # 🔴 스태프롤은 정본 대상이 아니다(마스터 2026-10-08 — 제작진은 게임마다 다르다). 「엔딩·스태프롤」 구간은 통째로 뺀다
        #    (엔딩 낭독과 한 구간에 섞여 있어 가를 수 없다). 화면 일본어 게이트(`scan_untranslated.title_left`)엔 남아 있다.
        if "스태프롤" in name:
            continue
        lines = kr.get(name, [])
        for i, (t, p, _n) in enumerate(recs):
            jp = t.strip("\u3000")
            if not jp:
                continue
            j = len(lines) - 1 - i
            yield f"title:{name}#{i}@0x{p:X}", jp, (lines[j] if 0 <= j < len(lines) else None)


def _mon_name_pairs():
    """ED2MON01~10 몬스터 이름 칸 171 — `patch_mon_names.slots()` (사전 `monster` 에서 읽는다)."""
    from glossary import table

    import patch_mon_names as M

    mon = table("monster")
    for path in M.FILES:
        for t, jp, kr in M.slots(path, mon):
            yield f"monname:{path}@0x{t:X}", jp, kr


def pairs():
    f, mm = common.open_image()
    try:
        sys_pairs = list(_sys_pairs(mm))
        sys_jp = {jp for _w, jp, kr in sys_pairs if kr}  # 이미 쟀다 — 원문 기준

        for where, jp, kr in _scn_pairs(mm):
            if not _has_text(jp):
                continue
            # 🔴 **원문이 시스템 길에도 있으면 거기 맡기고 여기선 안 낸다**(2026-10-07,
            #    관리자 지적 — scn·sys 두 길이 같은 물리 자리를 각자 세어 분모가 부풀었다:
            #    ED2MON 몬스터 메시지 350자리가 두 번 잡혔다). 이름 칸(木人Ａ 등, 시스템 길이
            #    안 보는 자리)은 `sys_jp` 에 없으니 그대로 남는다 — 안 사라진다.
            if jp in sys_jp:
                continue
            path = where[len("scn:") :].split("#")[0]
            dialog = _DIALOG_FILE.match(path) and not _slot_block(jp)
            yield where, jp, kr, "dialog" if dialog else "slot"

        for it in sys_pairs:
            yield (*it, "slot")
        for fn in (_hdr_pairs, _card_pairs, _item_name_pairs, _title_pairs, _msg_pairs):
            for it in fn(mm):
                yield (*it, "slot")
        for fn in (_ui_table_pairs, _mon_name_pairs):
            for it in fn():
                yield (*it, "slot")
    finally:
        mm.close()
        f.close()

