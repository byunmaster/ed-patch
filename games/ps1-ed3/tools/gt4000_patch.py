"""개발실 GT4000 안 2 시험 — 없는 스프라이트 시트(`C_330~332`)를 같은 팩(SC600)에 있는 NPC 시트로 바꿔 가리킨다. `ED_GT4000=1` + 꼬리표 `test-*` 에서만.

🔴 시험 빌드 전용 — 스위치 없이 구운 이미지는 이 모듈을 안 지나 바이트 불변이다. 입구(어디서 들어가나)는 만들지 않는다(마스터 결정 대기) — 시험은 맵 이동 버퍼(`14 <방향> 06 GT4000`)로 들어간다.

`..\\DATA\\GT4000.BIN`(9,424B, 길이 불변) 머리에 개체 표가 두 번 있다 — 정의 표(`id 종류 스프라이트u16`, 오프셋 62·66·70)와 배치 표(`x y 스프라이트u16`, 84·88·92).
스프라이트 번호 0x14A~0x14C(=`C_330~332`) 는 디스크에 없다 → 팩에 있는 0x208(`C_520`)·0x20C(`C_524`)·0x20F(`C_527`) 로 바꾼다(ST1005 가 여섯 시트를 한 번에 쓰는 같은 팩이라 VRAM 부담은 같다).
"""

import os

import common

PACK = "/SCE6/SC600.DAT"
MEMBER = "..\\DATA\\GT4000.BIN"
SLOTS = (62, 66, 70, 84, 88, 92)
OLD = (0x14A, 0x14B, 0x14C, 0x14A, 0x14B, 0x14C)
NEW = (0x208, 0x20C, 0x20F, 0x208, 0x20C, 0x20F)


TILE_AT = 16  # 머리의 타일 시트 번호 u16(`ee 02` = 750 → `B_750.TI3`, 디스크에 없다 — 뒤 u16 은 `P_750.AP3`, 그건 팩에 있다)
TILE_OLD = 750


def enabled():
    return os.environ.get("ED_GT4000") == "1"


def apply(disc, arcs):
    """arcs({경로: 바이트}) 의 SC600 사본에서 GT4000 멤버만 고친다(제자리, 길이 불변). 반환 = 설명."""
    assert disc == "ed3"
    if not common.BUILD_TAG.startswith("test-"):
        raise SystemExit("🔴 ED_GT4000=1 은 시험 빌드 전용이다 — 꼬리표는 test-* 여야 한다")
    if PACK not in arcs:
        lba, size = common.iso_files(disc)[PACK]
        arcs[PACK] = common.read_lba(disc, lba, size)
    data = bytearray(arcs[PACK])
    _, ents = common.arc_parse(bytes(data))
    off = {nm: (o, sz) for nm, o, sz in ents}[MEMBER][0]
    for at, old, new in zip(SLOTS, OLD, NEW):
        cur = int.from_bytes(data[off + at : off + at + 2], "little")
        if cur != old:
            raise SystemExit(f"🔴 GT4000 +{at}: 스프라이트 {cur:#x} (기대 {old:#x}) — 원본이 아니다")
        data[off + at : off + at + 2] = new.to_bytes(2, "little")
    tile = os.environ.get("ED_GT4000_TILE")  # 시험: 없는 타일 시트(750) 대신 팩에 있는 시트(190·850)를 가리킨다
    note = "GT4000 스프라이트 0x14A~C → 0x208·0x20C·0x20F"
    if tile:
        cur = int.from_bytes(data[off + TILE_AT : off + TILE_AT + 2], "little")
        if cur != TILE_OLD:
            raise SystemExit(f"🔴 GT4000 +{TILE_AT}: 타일 시트 {cur} (기대 {TILE_OLD})")
        data[off + TILE_AT : off + TILE_AT + 2] = int(tile).to_bytes(2, "little")
        note += f" · 타일 시트 750 → {int(tile)}"
    arcs[PACK] = bytes(data)
    return note
