"""sfc-ed1 배치기 — 대본 본체를 확장 뱅크로 옮겨 쓰고 2MB 롬을 만든다.

지금은 **원문을 글자 하나 안 바꾸고** 옮긴다. 목적은 재삽입의 뼈대 검증이다:
  · 롬 2MB 확장(LoROM 뱅크 $20~$3F)을 게임이 읽는가
  · 포인터 표 4벌 · $F9 절대 호출을 되쓴 자리를 게임이 따라오는가
  · 원래 자리($07:A721~$0B:FE75)를 $FF 로 지워도 사는가 — 숨은 독자(코드가 직접 읽는 문안)가 없다는 증거
원본 뱅크 k 의 문안은 새 뱅크 $20+k 의 **같은 뱅크 안 주소**에 놓는다 — rel16 은 뱅크를 못 넘고,
한 뱅크 안에서 균일하게 옮기면 상대 오프셋이 변하지 않아 옮기기 자체가 안전하다(절대 참조만 바뀐다).

규율(루트 CLAUDE.md 「빌드 규율」):
  · 원본은 `common.rom_bytes()` 로만 읽는다(지문 검사 포함) — 제자리 갱신 없음
  · 무변경 구간을 선언하고 출력과 원본을 byte 대조한다(IMMUTABLE)
  · 되읽기: 출력 롬을 다시 파싱해 디코드가 원본과 같아야 한다(check)
  · 실패하면 산출물을 `*.failed` 로 돌린다
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001  (common 보다 먼저 — shared/text 와 이름이 겹친다)
import battle_ui
import common
import dicts
import hook
import script

OUT_NAME = {  # 경로별로 갈라 쓴다(patcher-checklist.md 3-B ② — 「어느 경로가 만들었나」를 파일명에도)
    "kr": "Dragon Slayer - Eiyuu Densetsu (KR).sfc",  # build_kr() — 이게 굴리는 이미지
    "poc": "Dragon Slayer - Eiyuu Densetsu (POC).sfc",  # build() — 구조 재배치 + 메뉴 PoC, 배포 대상 아님
}
NEW_SIZE = 2 * 1024 * 1024
BANK_SHIFT = 0x20  # 원본 뱅크 $07~$0B → $27~$2B
LAYOUT_BANK = 0x2C8000  # 넓힌 창 배치 항목을 두는 자리(확장 뱅크)

# ── D2 「메뉴 폭」= (b) 창 넓히기(유저 2026-09-05) ──────────────────────────────────────────
# 7타일 창(커맨드 A01 · 시스템 A06)은 라벨 칸이 4라 한글 2자까지다 — 상자를 2타일 넓혀 6칸으로 만든다.
# 상자 = [왼틀][안쪽 5][오른틀]. 오른틀 앞에 안쪽 타일 둘을 끼운다(틀 행은 $29/$8029, 본문 행은 빈 $108).
# B0A/B0C/C0A 는 같은 커맨드 창을 **부분 갱신**하는 항목(w 는 크고 오른쪽이 0)이라 상자만 같이 넓힌다
# (크기 그대로, 뒤의 0 둘을 밀어낸다). A06 은 A01 오른쪽에 뜨므로 col 도 2 민다(겹침 방지 — 인게임 확인).
# ⚠ 창은 **그리는 기록과 지우는 기록이 짝**이다(실기 잔상으로 드러났다 — 유저 2026-09-06).
#   표 A = 틀+내용, 표 B·C = 같은 좌표의 **전부 0 기록**(닫을 때 그 영역을 되돌린다).
#   A 만 넓히면 오른쪽 2칸이 안 지워져 **맵 위에 창 조각이 남는다.** 짝을 같이 넓힌다.
#   B0A(=C0A)·B0C 는 0 기록이 아니라 커맨드 창을 **부분 갱신**하는 기록이라 상자만 넓힌다.
# ── D2 「메뉴 폭」— 🟢 **넓힐 필요가 없어졌다**(2026-09-06, D1=B 채택) ──────────────────────
# 한글 한 자가 **한 칸**이 되면서 커맨드 창의 4칸에 3음절(`버린다`)이 그대로 든다.
# 시스템 창도 4칸에 `시스템`(3)이 든다. ⇒ 창을 안 건드린다.
# 🔴 넓히기를 걷은 이유는 그것만이 아니다 — **창을 옆으로 옮기면 커서가 안 따라온다**
#   (status 13.1, 유저 제보 2026-09-06). 커서 열은 창 배치 기록의 `col` 에서 오지 않는다.
#   넓히기가 필요해지면 그 코드부터 찾아야 한다.
WIDEN: dict[tuple[str, int], tuple[int, int]] = {}
BOX_W = 7

# ── 메뉴 한글 PoC(코드 수정 없음) ───────────────────────────────────────────────────────────
# 글꼴 업로드($00:9177~$00:9198)는 1bpp 시트의 타일 $000~$17F 여섯 청크만 VRAM 에 올린다. 그 안에 빈 타일이 없어
# **탁음·반탁음 가타카나 두 행**(타일 $140~$14F·$160~$16F 와 그 아래 반쪽 $150/$170 행 = 코드 $A4~$C2)을 빌려
# 한글 16자(글자 = 위 타일 t,t+1 · 아래 t+$10,t+$11)를 심고, 커맨드 창(A01, 부분 갱신 B0A/B0C/C0A 포함)의 라벨
# 워드를 그 타일 번호로 다시 굽는다. ⚠ PoC 롬의 일본어 대사에서 ガ~ポ 자리에 한글 조각이 보이는 건 이 때문이다.
# 검증 대상: 시트 편집 → 기존 업로드 → 정적 타일맵 라벨의 경로가 산다(코드 한 줄 안 건드리고).
# 한 자 = 타일 **t(위) + t+$10(아래)** 두 장뿐이라(D1=B) 한 행을 통째로 쓸 수 있다.
# 빌린 행: $140/$150 · $160/$170 · $120/$130 (가나 세 행) = 48자리.
# 🔴 예전엔 가나 세 행(48자리)을 통째로 빌렸다. 그러면 **쓰지도 않는 26자리가 묶여** 대사 슬롯이
# 굶는다 — 상주와 동적이 같은 웅덩이를 나눠 쓰기 때문이다(`tools/tiles.py`). 이제 필요한 만큼만
# 앞에서 가져가고, 남은 것이 전부 동적 슬롯이 된다.
BODY = (text.TEXT_START, 0x0BFE76)  # 옮기는 구간(절반 열림)
HEADER_ROM_SIZE_OFF = common.HEADER_OFF + 0x17
CHECKSUM_OFF = common.HEADER_OFF + 0x1C  # cmpl(2) + chk(2)


def relocation_plan(items: list[script.Item]) -> dict[int, int]:
    """원문 오프셋 → 새 오프셋. 뱅크 번호에 BANK_SHIFT 를 더한 같은 자리."""
    return {it.off: it.off + BANK_SHIFT * 0x8000 for it in items}


def body_items(rom: bytes) -> list[script.Item]:
    return script.parse_region(
        rom, common.snes2off(BODY[0]), common.snes2off(BODY[1]), script.pointer_anchors(rom)
    )


def rewrite_tables(out: bytearray, place: dict[int, int], rom: bytes) -> int:
    n = 0
    for addr, count in text.MSG_TABLES.values():
        base = common.snes2off(addr)
        for i in range(count):
            p = rom[base + 3 * i] | (rom[base + 3 * i + 1] << 8) | (rom[base + 3 * i + 2] << 16)
            off = common.snes2off(p)
            if off in place:
                out[base + 3 * i : base + 3 * i + 3] = common.off2snes(place[off]).to_bytes(
                    3, "little"
                )
                n += 1
    return n


def _widen_row(row: list[int], extra: int) -> list[int]:
    """상자 7칸짜리 한 행에 안쪽 타일 extra 개를 오른틀 앞에 끼운다. 틀 행이면 틀 타일을, 아니면 빈 타일을."""
    first = row[0] & 0x3FF
    fill = (
        row[1] if first in (0x28, 0x2A) and (row[1] & 0x3FF) in (0x29, 0x8029 & 0x3FF) else 0x0108
    )
    if first == 0x28 or (row[0] & 0x8000 and first == 0x28):
        fill = row[1]
    return row[: BOX_W - 1] + [fill] * extra + row[BOX_W - 1 :]


def widen_windows(out: bytearray, rom: bytes) -> list[dict]:
    """창 배치 항목을 넓힌다. 크기가 늘면 확장 뱅크에 새로 쓰고 포인터를 돌리고, 부분 갱신 항목은 제자리."""
    import menus

    done = []
    cursor = common.snes2off(LAYOUT_BANK)
    for (table, wid), (extra, dcol) in WIDEN.items():
        base = common.snes2off(menus.LAYOUT_TABLES[table])
        p = rom[base + 3 * wid] | (rom[base + 3 * wid + 1] << 8) | (rom[base + 3 * wid + 2] << 16)
        o = common.snes2off(p)
        row, col, w, h = rom[o : o + 4]
        words = [rom[o + 4 + 2 * i] | (rom[o + 5 + 2 * i] << 8) for i in range(w * h)]
        rows = [words[r * w : (r + 1) * w] for r in range(h)]
        new_rows = []
        for rw in rows:
            if (rw[0] & 0x3FF) in (0x28, 0x2A) and (rw[BOX_W - 1] & 0x3FF) in (0x28, 0x2A):
                nr = _widen_row(rw, extra)
            else:
                nr = rw + [0] * extra  # 상자가 없는 행(0 채움)
            new_rows.append(nr)
        if w >= BOX_W + extra:  # 부분 갱신 항목 — 폭 그대로, 오른쪽 0 을 밀어낸다
            new_w = w
            new_rows = [nr[:w] for nr in new_rows]
            dst = o
        else:
            new_w = w + extra
            dst = cursor
        blob = bytes([row, col + dcol, new_w, h]) + b"".join(
            x.to_bytes(2, "little") for nr in new_rows for x in nr
        )
        out[dst : dst + len(blob)] = blob
        if dst != o:
            out[base + 3 * wid : base + 3 * wid + 3] = common.off2snes(dst).to_bytes(3, "little")
            cursor += len(blob)
        # 같은 항목 주소를 쓰는 다른 표(C0A = B0A)는 자동으로 따라온다(제자리) — 새 자리로 옮긴 건 포인터도 같이
        for t2, a2 in menus.LAYOUT_TABLES.items():
            b2 = common.snes2off(a2)
            for k in range(menus.LAYOUT_COUNT):
                if (
                    (t2, k) != (table, wid)
                    and rom[b2 + 3 * k : b2 + 3 * k + 3] == rom[base + 3 * wid : base + 3 * wid + 3]
                    and dst != o
                ):
                    out[b2 + 3 * k : b2 + 3 * k + 3] = common.off2snes(dst).to_bytes(3, "little")
        done.append(
            {
                "win": f"{table}{wid:02X}",
                "w": f"{w}→{new_w}",
                "col": f"{col}→{col + dcol}",
                "at": common.fmt(common.off2snes(dst)),
                "orig": (row, col, w, h),
                "grew": new_w > w,
            }
        )
    return done


def bake_glyph(out: bytearray, sheet: int, t: int, rows: list[int], half: bool) -> None:
    """글리프 한 자를 시트에 굽는다 — 반각이면 타일 t·t+$10 둘, 전각이면 t·t+1·t+$10·t+$11 넷."""
    for r in range(8):
        if half:
            out[sheet + 8 * t + r] = rows[r]
            out[sheet + 8 * (t + 0x10) + r] = rows[8 + r]
        else:
            out[sheet + 8 * t + r] = rows[r] >> 8
            out[sheet + 8 * (t + 1) + r] = rows[r] & 0xFF
            out[sheet + 8 * (t + 0x10) + r] = rows[8 + r] >> 8
            out[sheet + 8 * (t + 0x11) + r] = rows[8 + r] & 0xFF


# ── 파티 이름 상자 — **문이 아니라 구워진 타일맵**이다 (2026-09-07 실측) ─────────────────
# 상태 창 왼쪽 위의 이름 상자는 글자 코드를 안 거친다(코드→타일 표 `$03:F484` 에 읽기 BP 를 걸어도
# 안 걸린다). VRAM 에서 읽은 워드열을 롬에서 역으로 찾아 자리를 잡았다:
#   `$03:F5B4` 부터 **간격 28바이트**(2줄 × 7워드) × **다섯 이름**
#   한 줄 = `[틀 $002A][공백 $0108][이름 넉 칸][틀 $402A]`, 아랫줄은 같은 자리의 **타일 +$10**
# ⇒ 메뉴 라벨과 같은 부류라 **타일 워드를 다시 굽는다**(훅이 아니다).
# ⚠ 차례가 `textmap/battle_ui.json` 과 다르다(여긴 …ソニア·ゲイル·ロー) — **색인이 아니라 원문으로 짝짓는다.**
NAME_BOX = 0x03F5B4
NAME_STRIDE = 28
NAME_COUNT = 5
NAME_AT = 2  # 워드 색인 — 이름은 2~5번 칸
NAME_CELLS = 4


def _name_box_rows(rom: bytes) -> list[str]:
    """구워진 타일을 코드로 되짚어 원문 이름 다섯을 읽는다(짝짓기 열쇠)."""
    import tiles

    inv: dict[int, int] = {}
    for c, t in tiles.code_tile(rom).items():
        inv.setdefault(t, c)
    out = []
    for n in range(NAME_COUNT):
        o = common.snes2off(NAME_BOX + n * NAME_STRIDE)
        name = ""
        for i in range(NAME_AT, NAME_AT + NAME_CELLS):
            w = rom[o + 2 * i] | (rom[o + 2 * i + 1] << 8)
            c = inv.get(w & 0x3FF)
            ch = text.TABLE.get(c, "") if c is not None else ""
            name += ch
        out.append(name.replace("　", "").strip())
    return out


def bake_name_box(out: bytearray, rom: bytes, slot, code_tile: dict[int, int]) -> list[str]:
    """이름 상자 다섯을 한글 타일로 다시 굽는다. `slot(ch)` 은 메뉴와 **같은 배정기**를 쓴다."""
    names = json.loads(
        (common.GAME_DIR / "textmap" / "battle_ui.json").read_text(encoding="utf-8")
    )["names"]
    by_jp = {n["jp"]: n["kr"] for n in names}
    done = []
    for n, jp in enumerate(_name_box_rows(rom)):
        kr = by_jp.get(jp)
        if not kr:
            raise SystemExit(f"이름 상자 {n} 의 원문 {jp!r} 이 battle_ui.json 에 없다")
        if len(kr) > NAME_CELLS:
            raise SystemExit(f"이름 {kr!r} 이 {NAME_CELLS}칸을 넘는다")
        o = common.snes2off(NAME_BOX + n * NAME_STRIDE)
        cells = list(kr) + [" "] * (NAME_CELLS - len(kr))
        for i, ch in enumerate(cells):
            top = o + 2 * (NAME_AT + i)
            bot = o + 14 + 2 * (NAME_AT + i)
            if ch == " ":
                w_t = w_b = 0x0108  # 빈 칸은 위·아래 같은 타일(원본 규약)
            else:
                t = slot(ch)
                w_t, w_b = t, t + 0x10
            out[top : top + 2] = w_t.to_bytes(2, "little")
            out[bot : bot + 2] = w_b.to_bytes(2, "little")
        done.append(kr)
    return done


# ── 창 표 밖의 머리 상자 ────────────────────────────────────────────────────────────────
# 🔴 `menus.py` 의 창 표(27×3)가 **못 잡는 조각**이 있다. 「데이터를 지운다」의 머리 상자가
#    그것이다 — A06(`$03:C817`, 7×10) 바로 뒤 `$03:C8A7` 에 7워드 두 줄이 더 붙어 있는데
#    표의 어느 항목도 그 자리를 안 가리킨다(전수 확인). 그래서 `menu_bake` 가 안 굽고 화면엔
#    원문 「けす」 가 남았다(유저 제보 ⑵ — 뺏긴 타일이라 「문다」로 보였다).
# 🔑 **찾은 길** — 코드→타일 표(`$03:F3EC`)의 `け` 자리에 **읽기 BP 를 걸어도 안 걸린다**
#    ⇒ 코드가 아니라 **구워진 타일**이다. 그래서 VRAM 워드를 롬에서 되짚어 자리를 찾았다
#    (이름 상자 `$03:F5B4` 를 찾은 그 수법 그대로).
# ⚠ 조각이라 **위·아래 두 줄**만 있다(아래 = 위 + $10). 칸 수는 둘이다.
LOOSE_BOXES = [
    {"key": "けす", "addr": 0x03C8A7, "at": 2, "cells": 2, "stride": 14},
]


def bake_loose_boxes(out: bytearray, rom: bytes, slot, code_tile: dict[int, int]) -> list[str]:
    """창 표가 못 잡는 머리 상자를 한글 타일로 다시 굽는다. `slot` 은 메뉴와 **같은 배정기**."""
    import tiles

    inv: dict[int, int] = {}
    for c, t in tiles.code_tile(rom).items():
        inv.setdefault(t, c)
    # ⚠ `menus.json` 은 열쇠가 `원문@창id` 라 **표 밖 조각을 담을 자리가 없다** — `battle_ui.json`
    #   의 `loose` 에 둔다(거기가 이미 창 아닌 고정 문자열의 자리다)
    src = json.loads(
        (common.GAME_DIR / "textmap" / "battle_ui.json").read_text(encoding="utf-8")
    )["loose"]
    by_jp = {x["jp"]: x["kr"] for x in src}
    done = []
    for box in LOOSE_BOXES:
        o = common.snes2off(box["addr"])
        # ⚠ **원문을 되읽어 확인한다** — 자리를 손으로 적었으므로 그 자리가 맞는지 값으로 본다
        got = ""
        for i in range(box["at"], box["at"] + box["cells"]):
            w = rom[o + 2 * i] | (rom[o + 2 * i + 1] << 8)
            c = inv.get(w & 0x3FF)
            got += text.TABLE.get(c, "") if c is not None else ""
        if got != box["key"]:
            raise SystemExit(f"머리 상자 {common.fmt(box['addr'])} 의 원문이 {got!r} — {box['key']!r} 이어야 한다")
        kr = by_jp.get(box["key"])
        if not kr:
            raise SystemExit(f"머리 상자 원문 {box['key']!r} 이 battle_ui.json 의 loose 에 없다")
        if len(kr) > box["cells"]:
            raise SystemExit(f"머리 상자 {kr!r} 이 {box['cells']}칸을 넘는다")
        cells = list(kr) + [" "] * (box["cells"] - len(kr))
        for i, ch in enumerate(cells):
            top = o + 2 * (box["at"] + i)
            bot = o + box["stride"] + 2 * (box["at"] + i)
            w_t, w_b = (0x0108, 0x0108) if ch == " " else (slot(ch), slot(ch) + 0x10)
            out[top : top + 2] = w_t.to_bytes(2, "little")
            out[bot : bot + 2] = w_b.to_bytes(2, "little")
        done.append(kr)
    return done


def menu_windows() -> list[tuple[str, int]]:
    """라벨이 있는 창 전부 — `menus.json` 의 키 꼬리(`…@A01`)에서 유도한다(목록을 손으로 안 든다)."""
    labels = json.loads((common.GAME_DIR / "textmap" / "menus.json").read_text(encoding="utf-8"))
    ws = {(k.split("@")[1][0], int(k.split("@")[1][1:], 16)) for k in labels}
    return sorted(ws)


def menu_bake(out: bytearray, rom: bytes) -> dict:
    """메뉴 라벨을 한글로 — 상주 글리프를 시트에 굽고, 창 배치 워드를 그 타일로 바꾼다.

    ⚠ 라벨은 **정적 타일맵**이라 창이 열려 있는 내내 그 타일이 VRAM 에 있어야 한다 ⇒ 여기서 잡은
    자리는 대사 슬롯이 쓸 수 없다. 그래서 배정을 `tools/tiles.py` 한 곳에서 한다."""
    import hangul_font
    import menus
    import tiles

    labels = json.loads((common.GAME_DIR / "textmap" / "menus.json").read_text(encoding="utf-8"))
    font = hangul_font.load_font()
    inv = menus.inverse_tile_table(rom)
    sheet = common.snes2off(text.FONT_SHEET)
    import encode

    pool = tiles.overwritable(rom, tiles.layout_tiles(rom), keep_codes(rom))
    code_tile = tiles.code_tile(rom)
    half = {ch: c for ch, c in encode.KR_TABLE.items() if ch not in " \n"}
    slot_of: dict[str, int] = {}
    used_codes: list[int] = []
    too_long: list[str] = []

    def slot(ch: str) -> int:
        if ch not in slot_of:
            if len(used_codes) >= len(pool):
                raise SystemExit(f"메뉴 상주 글리프 자리가 모자란다: {''.join(slot_of)} + {ch}")
            c = pool[len(used_codes)]
            used_codes.append(c)
            t = code_tile[c]
            bake_glyph(out, sheet, t, hangul_font.render(ch, font), hangul_font.CELL_W == 8)
            slot_of[ch] = t
        return slot_of[ch]

    done = []
    for table, wid in menu_windows():
        base = common.snes2off(menus.LAYOUT_TABLES[table])
        p = out[base + 3 * wid] | (out[base + 3 * wid + 1] << 8) | (out[base + 3 * wid + 2] << 16)
        o = common.snes2off(p)  # ⚠ 넓힌 뒤의 자리(out 의 포인터)
        _row, _col, w, h = out[o : o + 4]
        for r in range(h - 1):
            top = [
                out[o + 4 + 2 * (r * w + i)] | (out[o + 5 + 2 * (r * w + i)] << 8) for i in range(w)
            ]
            line = menus._line(top, inv)
            m = next(
                (
                    lab
                    for lab in labels.items()
                    if lab[0].endswith(f"@{table}{wid:02X}")
                    and lab[0].split("@")[0] == line.strip("· ")
                ),
                None,
            )
            if not m or not m[1]["kr"]:
                continue
            kr = m[1]["kr"]
            x0 = next(i for i, ch in enumerate(line) if ch not in "· ")
            attr = top[x0] & 0xFC00
            words_top, words_bot = [], []
            for ch in kr:
                if "가" <= ch <= "힣":
                    t = slot(ch)
                    if hangul_font.CELL_W == 8:  # 한 자 = 한 칸
                        words_top.append(attr | t)
                        words_bot.append(attr | (t + 0x10))
                    else:
                        words_top += [attr | t, attr | (t + 1)]
                        words_bot += [attr | (t + 0x10), attr | (t + 0x11)]
                elif ch == " ":
                    words_top.append(0x0108)
                    words_bot.append(0x0108)
                elif ch in half:
                    # 반각(숫자·영문·부호)은 **원본 타일을 그대로 가리킨다** — 구울 게 없다.
                    # ⚠ 대사 경로의 공백 특례(`CMP #$10` → 아래도 같은 타일)는 정적 타일맵엔 없다.
                    t = code_tile[half[ch]]
                    words_top.append(attr | t)
                    words_bot.append(attr | (t + 0x10))
                else:
                    raise SystemExit(f"메뉴 라벨에 못 넣는 글자: {ch!r} in {kr!r}")
            # ⚠ 칸 예산은 **지금 기록에서 잰다** — menus.json 의 값은 원본 폭에서 잰 것이라
            #   창을 안 넓히면 오른쪽 틀과 다음 줄 첫 칸까지 덮어썼다(실기 2026-09-06: 틀이 통째로 사라졌다).
            x1 = next((i for i in range(x0, w) if line[i] == menus.FRAME), w)
            budget = x1 - x0
            if len(words_top) > budget:
                too_long.append(f"{m[0]} {kr!r} {len(words_top)}>{budget}")
                continue
            words_top += [0x0108] * (budget - len(words_top))
            words_bot += [0x0108] * (budget - len(words_bot))
            for i, (wt, wb) in enumerate(zip(words_top, words_bot, strict=True)):
                a = o + 4 + 2 * (r * w + x0 + i)
                b = o + 4 + 2 * ((r + 1) * w + x0 + i)
                out[a : a + 2] = wt.to_bytes(2, "little")
                out[b : b + 2] = wb.to_bytes(2, "little")
            done.append((m[0], kr))
    if too_long:
        raise SystemExit("라벨이 칸을 넘는다:\n  " + "\n  ".join(too_long))
    # 파티 이름 상자도 **같은 배정기**로 굽는다 — 상주 글리프는 한 웅덩이에서 나와야 한다
    names = bake_name_box(out, rom, slot, code_tile)
    loose = bake_loose_boxes(out, rom, slot, code_tile)
    return {
        "glyphs": "".join(slot_of),
        "labels": len(done),
        "names": names,
        "loose_boxes": loose,
        "resident_codes": used_codes,
        "windows": len(menu_windows()),
    }


def keep_codes(rom: bytes) -> set[int]:
    """타일을 지켜야 하는 코드 — 우리가 반각으로 쓰는 것 + 2바이트 선두(렌더러에 안 닿는다)."""
    import encode

    return set(encode.KR_TABLE.values()) | set(encode.LEADS)


def dynamic_slots(out: bytearray, rom: bytes, resident: list[int]) -> list[int]:
    """대사 훅이 빌릴 코드 — **라벨을 다시 구운 뒤의 롬**으로 잰다(일본어 라벨이 놓아 준 타일이 는다)."""
    import tiles

    return tiles.overwritable(rom, tiles.layout_tiles(out), keep_codes(rom) | set(resident))


def check_widen_pairs(rom: bytes, out: bytearray, originals: list) -> list:
    """넓힌 기록과 **원래 크기가 똑같던 기록**이 안 넓혀진 채 남아 있으면 실패로 친다.

    이 게임은 창마다 **그리는 기록(표 A)과 지우는 기록(표 B·C, 전부 0)이 짝**이고 좌표·크기가 같다.
    그리는 쪽만 넓히면 닫을 때 오른쪽 몇 칸이 안 지워져 **맵 위에 창 조각이 남는다**(유저 실기 제보 2026-09-06).
    ⚠ 「같은 좌표」로만 보면 안 된다 — 같은 모서리에 크기가 다른 **다른 창**(A07·A0D)이 있다.
    """
    import menus

    want = set(originals)  # (row, col, w, h) — 넓히기 전 모습
    bad = []
    for name, addr in menus.LAYOUT_TABLES.items():
        base = common.snes2off(addr)
        for wid in range(menus.LAYOUT_COUNT):
            p = (
                out[base + 3 * wid]
                | (out[base + 3 * wid + 1] << 8)
                | (out[base + 3 * wid + 2] << 16)
            )
            try:
                o = common.snes2off(p)
            except ValueError:
                continue
            geom = tuple(out[o : o + 4])
            if geom in want:
                bad.append((f"{name}{wid:02X}", f"r{geom[0]} c{geom[1]} {geom[2]}x{geom[3]}"))
    return bad


def fix_checksum(out: bytearray) -> None:
    """chk + cmpl 은 언제나 $FFFF 라 그 4바이트의 합은 $1FE 로 고정이다 — 값과 무관하게 계산한다."""
    s = (sum(out) - sum(out[CHECKSUM_OFF : CHECKSUM_OFF + 4]) + 0x1FE) & 0xFFFF
    out[CHECKSUM_OFF : CHECKSUM_OFF + 2] = (s ^ 0xFFFF).to_bytes(2, "little")
    out[CHECKSUM_OFF + 2 : CHECKSUM_OFF + 4] = s.to_bytes(2, "little")


def verify_header_checksum(out: bytes) -> None:
    """확장 산출물의 헤더 계약 — 2026-09-15 관리자 지적(빌드 칸이 2배로 커진 걸 보고).
    ⚠ **조용히 틀리는 자리다** — 체크섬이 안 맞아도 대부분의 에뮬레이터는 그냥 돈다. 실기·일부
    에뮬에서만 걸린다. `fix_checksum()` 직후라 사실상 항상 참이어야 하지만, 그 계산 자체가
    깨지거나 나중에 누가 그 뒤에 바이트를 더 건드리면 여기서 잡는다(회귀 방지)."""
    if len(out) != NEW_SIZE:
        raise SystemExit(f"산출물 크기가 {NEW_SIZE:,}B 가 아니다: {len(out):,}B")
    if out[HEADER_ROM_SIZE_OFF] != 0x0B:
        raise SystemExit(f"헤더 ROM 크기 필드가 0x0B(2048KB) 가 아니다: {out[HEADER_ROM_SIZE_OFF]:#04x}")
    cmpl = int.from_bytes(out[CHECKSUM_OFF : CHECKSUM_OFF + 2], "little")
    chk = int.from_bytes(out[CHECKSUM_OFF + 2 : CHECKSUM_OFF + 4], "little")
    if cmpl ^ chk != 0xFFFF:
        raise SystemExit(f"체크섬·보수가 안 맞물린다: chk={chk:#06x} cmpl={cmpl:#06x}")
    want = (sum(out) - sum(out[CHECKSUM_OFF : CHECKSUM_OFF + 4]) + 0x1FE) & 0xFFFF
    if want != chk:
        raise SystemExit(f"체크섬이 실제 바이트합과 다르다: 기록 {chk:#06x} 실측 {want:#06x}")


def build(rom: bytes) -> tuple[bytes, dict]:
    items = body_items(rom)
    place = relocation_plan(items)
    body = script.emit(items, place)
    out = bytearray(rom) + bytearray(b"\xff" * (NEW_SIZE - len(rom)))
    s, e = common.snes2off(BODY[0]), common.snes2off(BODY[1])
    out[s:e] = b"\xff" * (e - s)  # 원래 자리를 비운다 — 숨은 독자 검출
    ns = place[items[0].off]
    out[ns : ns + len(body)] = body
    n_ptr = rewrite_tables(out, place, rom)
    widened = widen_windows(out, rom)
    poc = menu_bake(out, rom)
    import chapters

    chap = chapters.bake(out, rom)
    # ⚠ 제자리로 넓힌 기록(부분 갱신)은 크기가 그대로라 「원래 모습」이 서명이 못 된다 — 자리를 옮긴 것만 본다
    pair_bad = check_widen_pairs(rom, out, [w["orig"] for w in widened if w["grew"]])
    if pair_bad:
        raise SystemExit(
            f"넓힌 창의 짝(지우는 기록)이 안 넓혀졌다 — 닫으면 잔상이 남는다: {pair_bad}"
        )
    out[HEADER_ROM_SIZE_OFF] = 0x0B  # 2048KB
    fix_checksum(out)
    verify_header_checksum(out)
    info = {
        "items": len(items),
        "body_bytes": len(body),
        "body_new": common.fmt(common.off2snes(ns)),
        "pointers_rewritten": n_ptr,
        "widened": widened,
        "menu_bake": {k: v for k, v in poc.items() if k != "resident_codes"},
        "chapters": len(chap["titles"]),
        "size": len(out),
    }
    return bytes(out), info


# 무변경 구간 — 이 밖은 전부 「의도한 변경」이어야 한다. 벗어난 차이는 사고다.
def mutable_ranges() -> list[tuple[int, int]]:
    r = [
        (common.snes2off(BODY[0]), common.snes2off(BODY[1])),
        (HEADER_ROM_SIZE_OFF, HEADER_ROM_SIZE_OFF + 1),
        (CHECKSUM_OFF, CHECKSUM_OFF + 4),
    ]
    for addr, count in text.MSG_TABLES.values():
        b = common.snes2off(addr)
        r.append((b, b + 3 * count))
    import menus

    for a in menus.LAYOUT_TABLES.values():
        b = common.snes2off(a)
        r.append((b, b + 3 * menus.LAYOUT_COUNT))
    rom = common.rom_bytes()
    for table, wid in WIDEN:
        base = common.snes2off(menus.LAYOUT_TABLES[table])
        p = rom[base + 3 * wid] | (rom[base + 3 * wid + 1] << 8) | (rom[base + 3 * wid + 2] << 16)
        o = common.snes2off(p)
        w, h = rom[o + 2], rom[o + 3]
        r.append((o, o + 4 + 2 * w * h))  # 제자리 넓힘(부분 갱신 항목)만 실제로 바뀐다
    for table, wid in menu_windows():  # 라벨을 제자리에 다시 굽는 창
        base = common.snes2off(menus.LAYOUT_TABLES[table])
        p2 = rom[base + 3 * wid] | (rom[base + 3 * wid + 1] << 8) | (rom[base + 3 * wid + 2] << 16)
        o2 = common.snes2off(p2)
        r.append((o2, o2 + 4 + 2 * rom[o2 + 2] * rom[o2 + 3]))
    for box in LOOSE_BOXES:  # 창 표가 못 잡는 머리 상자 — 두 줄만 바뀐다
        o3 = common.snes2off(box["addr"])
        r.append((o3, o3 + box["stride"] + 2 * (box["at"] + box["cells"])))
    import chapters  # 챕터 조립 표(장 6 × 17 롱 주소)

    b = common.snes2off(chapters.TABLE)
    r.append((b, b + chapters.STRIDE * 6))
    for a in chapters.pool(rom):  # 한글 제목 조각이 들어갈 자리(원본 자리 재활용 + 빈 자리)
        o = common.snes2off(a)
        r.append((o, o + 16))
        o2 = common.snes2off(a + 0x100)
        r.append((o2, o2 + 16))
    r += hook.patch_ranges()
    b = common.snes2off(NAME_BOX)  # 파티 이름 상자(구워진 타일맵)
    r.append((b, b + NAME_STRIDE * NAME_COUNT))
    r += dicts.patch_ranges()
    r += battle_ui.patch_ranges()
    r += battle_ui.patch_ranges_a3()
    sheet = common.snes2off(text.FONT_SHEET)
    import tiles  # 상주 글리프를 구울 수 있는 자리 전부(실제로 구운 것은 그 부분집합이다)

    ct = tiles.code_tile(rom)
    for c in tiles.overwritable(rom, tiles.layout_tiles(rom), keep_codes(rom)):
        for t0 in (ct[c], ct[c] + 0x10):
            r.append((sheet + 8 * t0, sheet + 8 * (t0 + 1)))
    return r


def lead_collisions(rom: bytes) -> dict[int, int]:
    """🔴 **한글 선두 코드를 원본이 글자로 쓰면 안 된다.** 쓰면 **안 옮긴 문안이 일본어로 남는 게
    아니라 엉뚱한 한글로 깨진다** — 그 코드를 선두로 읽고 다음 바이트를 색인으로 삼기 때문이다.
    전량(`kind == "char"`)으로 세어 0 이어야 한다(2026-09-06 에 실제로 셋이 걸렸다)."""
    import encode

    n: dict[int, int] = {}
    for it in body_items(rom):
        if it.kind == "char" and it.code in encode.LEADS:
            n[it.code] = n.get(it.code, 0) + 1
    return n


def immutable_diffs(rom: bytes, out: bytes, show: int = 5) -> int:
    """선언한 자리 밖이 바뀌었나 — 벗어난 차이는 사고다(루트 CLAUDE.md 「빌드 규율」)."""
    mut = sorted(mutable_ranges())
    diffs = 0
    lo = 0
    for i in range(len(rom)):
        if rom[i] == out[i]:
            continue
        while lo < len(mut) and mut[lo][1] <= i:
            lo += 1
        if any(a <= i < b for a, b in mut[lo : lo + 400]):
            continue
        diffs += 1
        if diffs <= show:
            print(
                f"  ⚠ 무변경 구간 차이 {common.fmt(common.off2snes(i))}: {rom[i]:02X}→{out[i]:02X}"
            )
    return diffs


def verify(rom: bytes, out: bytes, place: dict[int, int]) -> dict:
    # 1. 무변경 구간 byte 대조
    diffs = immutable_diffs(rom, out)

    # 2. 되읽기 — 새 표를 따라 새 자리의 첫 조각을 읽어 원본 조각과 **바이트** 대조. 옮긴 뒤 달라져야
    #    하는 건 $F9 의 절대 주소뿐이니 그것만 원래 뱅크로 되돌려 비교한다(디코드 비교는 그 인자를 못 가른다).
    def unshift_f9(raw: bytes) -> bytes:
        b = bytearray(raw)
        i = 0
        while i < len(b):
            c = b[i]
            if c < 0xD0:
                i += 1
            elif c < 0xE0:
                i += 2 if c in text.DICT_TABLES else 1
            else:
                if c == 0xF9 and i + 3 < len(b) and b[i + 3] >= BANK_SHIFT:
                    b[i + 3] -= BANK_SHIFT
                i += 1 + text.ARGLEN.get(c, 0)
        return bytes(b)

    mism = 0
    total = 0
    for name in text.MSG_TABLES:
        po = text.msg_pointers(name, rom)
        pn = text.msg_pointers(name, out)
        for a, b in zip(po, pn, strict=True):
            if a == b and common.snes2off(a) not in place:
                continue  # 안 옮긴 항목(표 자신을 가리키는 더미 · 뱅크 $05/$1E) — 비교 대상이 아니다
            so = text.parse_span(rom, common.snes2off(a), None)[0][1]
            sn = text.parse_span(out, common.snes2off(b), None)[0][1]
            total += 1
            if so != unshift_f9(sn):
                mism += 1
    # 3. 옮긴 본체를 라벨 모델로 다시 풀어 원본 항목 열과 같은가(참조 재계산의 역검증)
    items_o = body_items(rom)
    ns = common.snes2off(BODY[0]) + BANK_SHIFT * 0x8000
    items_n = script.parse_region(
        out, ns, ns + sum(it.size for it in items_o), script.pointer_anchors(out)
    )
    back = {it.off: it.off - BANK_SHIFT * 0x8000 for it in items_n}
    same_back = (
        script.emit(items_n, back) == rom[common.snes2off(BODY[0]) : common.snes2off(BODY[1])]
    )
    return {
        "lead_collisions": len(lead_collisions(rom)),
        "immutable_diffs": diffs,
        "readback_msgs": total,
        "readback_mismatch": mism,
        "reverse_roundtrip": same_back,
    }


# ── 한글 경로: 번역된 조각을 인코딩해 rel16 군집 단위로 32KB 뱅크에 담는다 ───────────────────────
# $2C = 창 배치 항목(넓힐 때) · $2E = 한글 챕터 제목 조각 · $3D = 글리프 · $3E = 사전 · $3F = 렌더러 훅
KR_BANKS = [
    b
    for b in range(0x27, 0x40)
    if b not in (0x2C, 0x2E, hook.GLYPH_BANK, dicts.BANK, hook.HOOK_BANK)
]
BANK_CAP = 0x8000


def segment_slices(items: list[script.Item]) -> list[tuple[str, int, int]]:
    """(조각 id, 시작 인덱스, 끝 인덱스(열림)) — units.segments 와 같은 id(원문 바이트 sha1)."""
    import hashlib

    out = []
    start = 0
    for k, it in enumerate(items):
        # 🔴 **뱅크 경계에서도 끊는다** — 조각은 「이어서 실행되는 한 덩이」인데 `$02:E784` 는
        #    16비트만 올려 `$xx:FFFF` 다음이 `$xx:0000`(램)이다. 곧 뱅크를 걸친 한 덩이는
        #    원판에서도 **이어서 실행될 수 없다.** 안 끊으면 그 조각이 두 뱅크의 rel16 을 동시에
        #    받는 **경첩**이 되어(실측: 조각 2905 가 $0A 에서 `$FA` 를 받고 $0B 로 `$FC` 를 쏜다)
        #    군집이 41,767B 로 부풀어 한 뱅크에 못 들어간다. 넷뿐이고 전부 미번역이다.
        if k > start and common.off2snes(it.off) >> 16 != common.off2snes(items[k - 1].off) >> 16:
            raw = b"".join(bytes([x.code]) + x.args for x in items[start:k])
            out.append((hashlib.sha1(raw).hexdigest()[:12], start, k))
            start = k
        if it.kind == "ctrl" and it.code in (0xE0, 0xE4):
            raw = b"".join(bytes([x.code]) + x.args for x in items[start : k + 1])
            out.append((hashlib.sha1(raw).hexdigest()[:12], start, k + 1))
            start = k + 1
    return out


def fallthrough_pairs(
    items: list[script.Item], slices: list[tuple[str, int, int]], rom: bytes
) -> list[int]:
    """`si` → `si+1` 로 **흘러내려야만** 닿는 짝(= si 의 끝이 `$E0` 이고 si+1 이 무참조).

    돌려주는 것은 si 목록이다. 판정 근거는 `kr_items` 의 군집 주석."""
    refs = set(script.pointer_anchors(rom))
    for it in items:
        refs.update(t for t in it.targets)

    # ⚠ 원문 **뱅크가 갈리면 흘러내림이 아니다** — `$02:E784` 는 `$003F/$0040`(16비트)만 올리고
    #   `$0041`(뱅크)은 안 건드린다. 곧 `$xx:FFFF` 다음은 `$xx:0000`(램)이지 다음 뱅크가 아니다.
    #   파일에서 이어져 보여도 원판이 **실행할 수 없는 이음**이라 묶으면 안 된다(묶었더니 군집
    #   하나가 49,895B 로 부풀어 뱅크를 넘었다 — 2026-09-08 실측).
    #   ⚠ **조각 시작끼리** 견준다 — 경계를 걸친 조각이 실재한다($09:FE49~$0A:8038, 조각 하나).
    #   끝 주소로 견주면 그 조각이 다음 뱅크에 속한 것처럼 보여 경계가 안 잘린다.
    def bank(off: int) -> int:
        return common.off2snes(off) >> 16

    def spans(si: int) -> bool:
        """조각 하나가 뱅크 경계를 걸친다 — 넷 있다(예: $0A:FE6A~$0B:8005). 사슬에 넣지 않는다."""
        a, e = slices[si][1], slices[si][2]
        return bank(items[a].off) != bank(items[e - 1].off + items[e - 1].size - 1)

    return [
        si
        for si in range(len(slices) - 1)
        if items[slices[si][2] - 1].code == 0xE0
        and items[slices[si + 1][1]].off not in refs
        and bank(items[slices[si][1]].off) == bank(items[slices[si + 1][1]].off)
        and not spans(si)
        and not spans(si + 1)
    ]


def kr_items(
    rom: bytes,
    states=("reviewed", "draft", "tm-draft"),
    only: set[str] | None = None,
    enc_override=None,
) -> dict:
    """원문 항목 열에 번역을 끼운 새 항목 열 + 라벨 매핑 + 통계.

    `only` 를 주면 그 조각만 번역하고 나머지는 원문을 남긴다. `enc_override(sid, entry)` 는
    인코더를 갈아 끼운다 — 오프닝 PoC 가 **1바이트 빌린 코드**로 굽는 데 쓴다."""
    import encode
    import units

    items = body_items(rom)
    slices = segment_slices(items)
    tmap = json.loads((common.GAME_DIR / "textmap" / "segments.json").read_text(encoding="utf-8"))
    dmap = json.loads((common.GAME_DIR / "textmap" / "dict.json").read_text(encoding="utf-8"))
    dict_kr = {k: v["kr"] for k, v in dmap.items() if v.get("kr")}
    texts = [v["kr"] for v in tmap.values() if v.get("kr")] + list(dict_kr.values())
    mmap = json.loads((common.GAME_DIR / "textmap" / "menus.json").read_text(encoding="utf-8"))
    texts += [v["kr"] for v in mmap.values() if v.get("kr")]
    # ⚠ `battle_ui.json` 도 **화면에 나가는 문안**이다 — 고정 칸 문자열·이름 상자·머리 상자.
    #   여기 안 넣으면 그 파일에만 있는 음절이 `rep_index` 에 없어 `encode_rows` 가 KeyError 로
    #   죽는다. 지금은 0건이지만 **다른 파일에 같은 글자가 있어서 우연히 사는 것**이라(실측
    #   2026-09-08: 51자 전부 다른 데서 왔다) 낱말 하나만 바꿔도 깨진다. 원천으로 못 박는다.
    bmap = json.loads((common.GAME_DIR / "textmap" / "battle_ui.json").read_text(encoding="utf-8"))
    for key in ("title", "speed", "yesno", "loose", "names"):
        texts += [x["kr"] for x in bmap.get(key, [])]
    texts += [c["kr"] for g in bmap.get("grid", []) for c in g["cols"]]
    texts.append(
        hook.josa_chars()
    )  # 런타임 조사 16형태 — 훅이 색인으로 집는다(문안에 없어도 필요하다)
    rep = encode.repertoire(texts)
    rep_index = encode.index_map(rep)
    new: list[script.Item] = []
    seg_of: dict[int, int] = {}  # 새 항목 인덱스 → 조각 번호
    label_map: dict[int, int] = {}  # 원문 런 한복판 목표 오프셋 → 그 자리에 놓인 새 항목 인덱스
    start_of: dict[int, int] = {}  # 원문 조각 시작 오프셋 → 새 항목 인덱스
    stats = {
        "translated": 0,
        "kept": 0,
        "runtime_josa": 0,
        "jp_bytes": 0,
        "kr_bytes": 0,
        "errors": [],
    }
    targets_all = {t for it in items for t in it.targets}
    fake_off = -1
    for si, (sid, a, e) in enumerate(slices):
        seg = items[a:e]
        start_of[seg[0].off] = len(new)
        entry = tmap.get(sid)
        if only is not None and sid not in only:
            entry = None
        if not (entry and entry.get("kr") and entry.get("state") in states):
            for it in seg:
                seg_of[len(new)] = si
                new.append(it)
            stats["kept"] += 1
            continue
        try:
            enc = (
                enc_override(sid, entry)
                if enc_override is not None
                else encode.encode(entry["kr"], rep_index, dict_kr)
            )
        except ValueError as ex:
            stats["errors"].append((sid, str(ex)))
            for it in seg:
                seg_of[len(new)] = si
                new.append(it)
            continue
        ctrls = [it for it in seg if it.kind == "ctrl"]
        mids = [
            it.off
            for j, it in enumerate(seg)
            if it.kind == "char" and it.off in targets_all and j > 0 and seg[j - 1].kind == "char"
        ]
        # 사전·치환 항목은 (토큰값, 몇 번째) 로 원문 항목과 짝지어 **원문 오프셋을 이어받는다**(분기 목표일 수 있다)
        dict_pool: dict[str, list[script.Item]] = {}
        for it in seg:
            if it.kind in ("dict", "subst"):
                dict_pool.setdefault(units.token_of(it), []).append(it)
        ci = 0
        li = 0
        seg_new_start = len(new)
        for kind, *v in enc.parts:
            if kind == "bytes":
                seg_of[len(new)] = si
                new.append(script.Item(fake_off, "raw", -1, v[0]))
                fake_off -= 1
            elif kind == "dict":
                tok, bts = v
                src = dict_pool.get(tok)
                it = src.pop(0) if src else None
                seg_of[len(new)] = si
                new.append(script.Item(it.off if it else fake_off, "raw", -1, bts))
                if not it:
                    fake_off -= 1
            elif kind == "ctrl":
                it = ctrls[ci]
                ci += 1
                seg_of[len(new)] = si
                new.append(it)
            else:  # label
                label_map[mids[li]] = len(new)
                li += 1
        # 원문에서 「제어 바로 뒤 글자」를 가리키던 목표 → 그 제어의 새 자리 다음 항목
        seg_new = new[seg_new_start:]
        for j, it in enumerate(seg):
            if it.kind == "char" and it.off in targets_all and j > 0 and seg[j - 1].kind == "ctrl":
                prev = seg[j - 1]
                kidx = next((seg_new_start + m for m, x in enumerate(seg_new) if x is prev), None)
                if kidx is not None and kidx + 1 < len(new):
                    label_map[it.off] = kidx + 1
            elif (
                it.kind == "char"
                and it.off in targets_all
                and j > 0
                and seg[j - 1].kind in ("dict", "subst")
            ):
                stats["errors"].append(
                    (
                        sid,
                        f"사전 토큰 바로 뒤가 분기 목표 — <@> 필요 ({units.token_of(seg[j - 1])})",
                    )
                )
        for tok, rest in dict_pool.items():
            for it in rest:
                if it.off in targets_all:
                    stats["errors"].append((sid, f"분기 목표인 사전 토큰 {tok} 이 번역문에 없다"))
        assert ci == len(ctrls) and li == len(mids), sid
        stats["translated"] += 1
        stats["runtime_josa"] += enc.runtime_josa
        stats["jp_bytes"] += sum(it.size for it in seg)
        stats["kr_bytes"] += sum(it.size for it in new[start_of[seg[0].off] :])
    # 군집: rel16(FA/FC/FB/FD)으로 이어진 조각은 같은 뱅크에 있어야 한다
    parent = list(range(len(slices)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    off_seg = {}
    for si, (_, a, e) in enumerate(slices):
        for it in items[a:e]:
            off_seg[it.off] = si
    for k, it in enumerate(new):
        if it.kind == "ctrl" and it.code in (0xFA, 0xFC, 0xFB, 0xFD):
            for t in it.targets:
                if t in off_seg:
                    ra, rb = find(seg_of[k]), find(off_seg[t])
                    if ra != rb:
                        parent[rb] = ra
    # 🔴 **흘러내림도 참조다** — `$E0` 은 「끝」이 아니라 **쪽 넘김**이다(2026-09-08 실측).
    #   `$02:DCC0` 경로(메뉴·시스템 메시지)는 `$1779=$177A=0` 으로 들어와 END 핸들러가
    #   `$02:E30C`(키 대기 → 창 비움 → rts)로 빠지고, 디스패치는 `$173A` 가 `$E4`/`$FF` 가
    #   아니므로 **`$02:DDDD` 로 돌아가 다음 바이트를 계속 읽는다.** 곧 **`$E0` 다음 바이트가
    #   실행된다** — 원판의 물리적 이웃이 곧 의미다. 우리는 조각을 다시 담으므로 그 이웃이
    #   깨졌다(저장 확인 소프트락: `alt1[$4D]` 의 `<E0>` 뒤 `<E4>` 가 사라져 삭제 문안으로
    #   흘러 들어갔다 — `docs/devlog.md`).
    #   ⚠ 어디까지 묶나 — **다음 조각이 아무 데서도 참조되지 않을 때만**이다. 참조가 있으면
    #   그 조각은 제 포인터로 닿는 별개 메시지이고, 전부 묶으면 사슬이 79KB 가 되어 뱅크를
    #   넘는다(실측). 참조 없는 조각은 **흘러내림 말고는 닿을 길이 없다** ⇒ 반드시 이웃이다.
    fall = fallthrough_pairs(items, slices, rom)
    for si in fall:
        ra, rb = find(si), find(si + 1)
        if ra != rb:
            parent[rb] = ra
    comp_of = [find(i) for i in range(len(slices))]
    return {
        "items": new,
        "slices": slices,
        "seg_of": seg_of,
        "comp_of": comp_of,
        "fallthrough": fall,
        "label_map": label_map,
        "start_of": start_of,
        "rep": rep,
        "stats": stats,
        "orig_items": items,
    }


def pack_banks(k: dict) -> dict:
    """군집을 원문 순서대로 first-fit 으로 뱅크에 담아 place(원문 오프셋 → 새 오프셋)를 만든다."""
    new, slices, seg_of, comp_of = k["items"], k["slices"], k["seg_of"], k["comp_of"]
    # 조각별 새 항목 범위와 크기
    seg_items: dict[int, list[int]] = {}
    for idx, si in seg_of.items():
        seg_items.setdefault(si, []).append(idx)
    comp_segs: dict[int, list[int]] = {}
    for si in range(len(slices)):
        comp_segs.setdefault(comp_of[si], []).append(si)
    comp_size = {
        c: sum(new[i].size for si in segs for i in seg_items.get(si, []))
        for c, segs in comp_segs.items()
    }
    banks = []  # [bank, used]
    where: dict[int, tuple[int, int]] = {}  # comp → (bank, offset-in-bank)
    for c in sorted(comp_segs):
        size = comp_size[c]
        if size > BANK_CAP:
            raise SystemExit(f"군집 {c} 가 한 뱅크를 넘는다: {size:,}B")
        for bk in banks:
            if bk[1] + size <= BANK_CAP:
                where[c] = (bk[0], bk[1])
                bk[1] += size
                break
        else:
            bank = KR_BANKS[len(banks)]
            banks.append([bank, size])
            where[c] = (bank, 0)
    # 새 오프셋 배정: 군집 안에서 조각 순서대로, 조각 안에서 항목 순서대로
    new_off: dict[int, int] = {}
    cursor = {c: common.snes2off((bank << 16) | 0x8000) + o for c, (bank, o) in where.items()}
    for si in range(len(slices)):
        c = comp_of[si]
        for i in sorted(seg_items.get(si, [])):
            new_off[i] = cursor[c]
            cursor[c] += new[i].size
    place: dict[int, int] = {}
    for i, it in enumerate(new):
        if it.off >= 0:
            place[it.off] = new_off[i]
    for orig_start, idx in k["start_of"].items():
        place[orig_start] = new_off[idx] if idx in new_off else place.get(orig_start, orig_start)
    for orig_target, idx in k["label_map"].items():
        place[orig_target] = new_off[idx]
    # 🔴 게이트 — 흘러내림 이웃이 진짜 이웃인가. 군집만 믿지 않는다(같은 군집이어도 배치 차례가
    #    어긋나면 사이에 남이 낀다). 여기서 **바이트 자리로** 확인한다.
    for si in k["fallthrough"]:
        cur = seg_items.get(si)
        nxt = seg_items.get(si + 1)
        if not cur or not nxt:
            continue
        last = max(cur)
        first = min(nxt)
        if new_off[last] + new[last].size != new_off[first]:
            raise SystemExit(
                f"흘러내림이 끊겼다: 조각 {si} 끝 {new_off[last] + new[last].size:#08x} "
                f"≠ 조각 {si + 1} 시작 {new_off[first]:#08x} "
                f"(`$E0` 다음 바이트가 원판과 달라진다 — 저장 소프트락의 원인)"
            )
    return {
        "place": place,
        "new_off": new_off,
        "banks": banks,
        "comp_size": comp_size,
        "n_comp": len(comp_segs),
    }


# ── 단계끼리 같은 바이트를 쓰는지 본다 (2026-09-07, ss-ed1+2 사고 중계) ─────────────────────
# 🔴 **뒤 단계가 앞 단계의 자리를 덮어도 게이트 셋이 다 초록이었다**(다른 트랙 실측):
#   되읽기는 *자기가 쓴 직후*를 · 라운드트립은 *덤프↔원본*을 · 무변경 구간은 *안 여는 파일*을 본다.
#   셋 다 「다른 단계가 내 자리를 덮었나」를 안 본다. 그래서 **쓴 자리를 단계마다 적어 두고 겹치면 운다.**
# ⚠ 특히 **빈 자리를 원본 롬에서 고르는 단계**(챕터 조각·글꼴 시트)가 위험하다 — 원본이 비었어도
#   앞 단계가 이미 깔아 놨을 수 있다. 여기서는 「원본과 다른가」가 아니라 **「누가 썼나」**로 센다.
def _written(prev: bytes, cur: bytes) -> set[int]:
    """두 스냅숏 사이에 바뀐 바이트 오프셋 — 4KB 덩이로 먼저 걸러 빠르게 훑는다."""
    out: set[int] = set()
    n = len(prev)
    for b in range(0, n, 4096):
        e = min(b + 4096, n)
        if prev[b:e] != cur[b:e]:
            out.update(i for i in range(b, e) if prev[i] != cur[i])
    return out


class Ledger:
    """단계마다 `snap()` 을 부르면 그 단계가 쓴 자리를 적고, 앞 단계와 겹치면 그 자리에서 운다."""

    def __init__(self, out: bytearray):
        self.prev = bytes(out)
        self.by_stage: dict[str, set[int]] = {}

    def snap(self, out: bytearray, stage: str) -> None:
        cur = bytes(out)
        w = _written(self.prev, cur)
        for other, ow in self.by_stage.items():
            hit = w & ow
            if hit:
                a = min(hit)
                raise SystemExit(
                    f"단계 겹침: '{stage}' 가 '{other}' 의 자리를 {len(hit)}바이트 덮었다 "
                    f"(처음 {common.fmt(common.off2snes(a))})"
                )
        self.by_stage[stage] = w
        self.prev = cur

    def report(self) -> dict:
        return {k: len(v) for k, v in self.by_stage.items()}


def verify_terminators(rom: bytes, out: bytes) -> int:
    """메시지마다 **첫 종료 코드의 꼴**이 원판과 같은가 — 화면을 보는 게이트.

    🔴 왜 필요한가: `$E0` 은 「끝」이 아니라 **쪽 넘김**이다. `$02:DCC0` 로 들어온 메시지
    (메뉴·시스템)는 `$1779=$177A=0` 이라 END 핸들러가 `$02:E30C`(키 대기 → 창 비움 → rts)로
    빠지고, 디스패치(`$02:E216`)는 `$173A` 가 `$E4`/`$FF` 가 아니므로 **`$02:DDDD` 로 돌아가
    다음 바이트를 계속 읽는다.** 그래서 `<E0>` **다음 바이트가 원판과 같아야** 한다 —
    `<E0><E4>` 로 닫히던 문안의 `<E4>` 가 사라지면 엔진이 옆 문안으로 흘러 들어가고, 화면은
    살아 있는데 **저장이 끝나지 않는다**(2026-09-08 소프트락의 정체).
    ⚠ 되읽기·라운드트립·무변경 구간 셋 다 이걸 못 본다 — **조각 하나하나는 다 맞았다.**
    """
    import encode as _enc

    leads = set(_enc.LEADS)

    def first_end(img: bytes, snes: int, kr: bool) -> tuple[int | None, int | None]:
        o = common.snes2off(snes)
        for _ in range(600):
            c = img[o]
            if kr and c in leads:
                o += 2
                continue
            if c < 0xD0:
                o += 1
            elif c in text.DICT_TABLES:
                o += 2
            elif c < 0xE0:
                o += 1
            elif c in (0xE0, 0xE4, 0xFE, 0xFF):
                # `$FE`(RETURN)·`$FF`(PAGE, 여백 채움 바이트이기도 하다)에서도 멈춘다 —
                # 그 뒤를 선형으로 읽는 건 뜻이 없다(원판은 이웃 문안을, 우리는 $FF 여백을 읽어
                # 서로 다른 자리에서 종료 코드를 만난다). 재는 것은 **첫 종료 코드의 꼴**뿐이다.
                return c, img[o + 1]
            else:
                o += 1 + text.ARGLEN.get(c, 0)
        return None, None

    bad, seen = [], 0
    for name in text.MSG_TABLES:
        try:
            po, pn = text.msg_pointers(name, rom), text.msg_pointers(name, out)
        except SystemExit:  # alt3 끝의 $FFFFFF — 포인터가 아니다(원판부터 그렇다)
            continue
        for i, (a, b) in enumerate(zip(po, pn, strict=False)):
            if common.snes2off(a) < common.snes2off(text.TEXT_START):
                continue  # 표 구간을 가리키는 항목(alt1[0] 등) — 문안이 아니다
            seen += 1
            wa, wb = first_end(rom, a, False), first_end(out, b, True)
            # 종료 코드와 「그 다음이 $E4 인가」만 본다 — 그 뒤 바이트는 번역으로 달라진다
            if (wa[0], wa[1] == 0xE4) != (wb[0], wb[1] == 0xE4):
                bad.append(f"{name}[{i:#06x}] 원판 {wa} 우리 {wb}")
    if bad:
        raise SystemExit(
            f"종료 꼴이 갈린 메시지 {len(bad)}건 — `$E0` 다음 바이트가 원판과 다르다\n  "
            + "\n  ".join(bad[:8])
        )
    return seen


def build_kr(
    rom: bytes,
    states=("reviewed", "draft", "tm-draft"),
    only: set[str] | None = None,
    enc_override=None,
    after=None,
    with_hook: bool = True,
) -> tuple[bytes, dict]:
    k = kr_items(rom, states, only, enc_override)
    pk = pack_banks(k)
    new, place = k["items"], pk["place"]
    out = bytearray(rom) + bytearray(b"\xff" * (NEW_SIZE - len(rom)))
    led = Ledger(out)  # ⚠ **첫 쓰기 전에** 연다 — 본체 이관도 원장에 들어가야 한다
    s, e = common.snes2off(BODY[0]), common.snes2off(BODY[1])
    out[s:e] = b"\xff" * (e - s)
    # 뱅크별로 이어 쓴다 — 항목마다 자기 새 오프셋에
    full_place = place | {it.off: pk["new_off"][i] for i, it in enumerate(new) if it.off < 0}
    unresolved = sorted(
        {
            t
            for it in new
            for t in it.targets
            if t >= 0
            and t not in full_place
            and common.snes2off(BODY[0]) <= t < common.snes2off(BODY[1])
        }
    )
    if unresolved:
        k["stats"]["errors"].append(
            (
                "targets",
                f"새 자리를 못 찾은 분기 목표 {len(unresolved)}건 예 {[common.fmt(common.off2snes(t)) for t in unresolved[:5]]}",
            )
        )
        for t in unresolved:  # 보고를 위해 임시로 제자리(원문) — 실패로 친다
            full_place[t] = t
    body = script.emit(new, full_place, strict=not unresolved)
    pos = 0
    for i, it in enumerate(new):
        n = it.size
        out[pk["new_off"][i] : pk["new_off"][i] + n] = body[pos : pos + n]
        pos += n
    n_ptr = rewrite_tables(out, place, rom)
    # ⚠ 본체를 $FF 로 비운 뒤 그 안의 표(alt3 는 본체 구간 안에 있다)를 다시 쓴다 —
    #   **한 덩이**라 한 단계로 센다. 원장이 잡아야 할 것은 「지웠다 다시 쓰기」가 아니라
    #   **다른 단계가 남의 자리를 먹는 것**이다(2026-09-07 원장을 켜자마자 이 둘이 먼저 걸렸다).
    led.snap(out, "본체·포인터 표 이관")
    widened = widen_windows(out, rom)
    poc = menu_bake(out, rom)
    led.snap(out, "메뉴 라벨·상주 글리프")
    import chapters

    chapters.bake(out, rom)
    led.snap(out, "챕터 제목")
    extra = after(out, rom) if after is not None else None
    # 🔴 렌더러 훅은 **메뉴를 구운 뒤**에 얹는다 — 슬롯은 「라벨을 다시 구운 롬」으로 재야 한다
    hk = dk = None
    if with_hook:
        led.snap(out, "오프닝 PoC")
        # ⚠ **사전을 먼저** 놓는다 — 메뉴 이름 훅이 아이템 표의 **새 주소**를 알아야 한다
        import encode as _enc

        _idx = _enc.index_map(k["rep"])
        dk = dicts.bake(out, rom, _idx)
        bu = battle_ui.bake(out, rom, _idx, dk["next"])  # 사전 바로 뒤에 이어 놓는다
        dk["전투 UI"] = bu
        a3 = battle_ui.bake_a3_values(out, rom, _idx, bu["next"])  # 그 뒤에 이어 놓는다
        dk["A3 값"] = a3
        led.snap(out, "사전·전투 UI 이관")
        hk = hook.apply(
            out,
            rom,
            k["rep"],
            dynamic_slots(out, rom, poc["resident_codes"]),
            item_table=dk["tables"][0xD2],
        )
        led.snap(out, "렌더러 훅")

    if with_hook:
        dicts.verify(out, k["rep"])  # 🔑 **체인이 다 끝난 롬**에서 게임의 포인터를 따라 되읽는다
        battle_ui.verify(out, k["rep"])
        battle_ui.verify_a3_values(out, k["rep"])
    n_term = verify_terminators(rom, out)
    out[HEADER_ROM_SIZE_OFF] = 0x0B
    fix_checksum(out)
    verify_header_checksum(out)
    imm = immutable_diffs(rom, out)
    st = k["stats"]
    # 원문 뱅크별 JP → KR 투영
    per_bank = {}
    for si, (_sid, a, e_) in enumerate(k["slices"]):
        bank = k["orig_items"][a].off // 0x8000
        jp = sum(it.size for it in k["orig_items"][a:e_])
        kr = sum(new[i].size for i, s_ in k["seg_of"].items() if s_ == si)
        d = per_bank.setdefault(f"${bank:02X}", [0, 0])
        d[0] += jp
        d[1] += kr
    info = {
        "translated_segments": st["translated"],
        "kept_segments": st["kept"],
        "ok": not st["errors"],
        "errors": len(st["errors"]),
        "error_sample": st["errors"][:6],
        "glyphs": len(k["rep"]),
        "runtime_josa_codes": st["runtime_josa"],
        "translated_jp_bytes": st["jp_bytes"],
        "translated_kr_bytes": st["kr_bytes"],
        "per_orig_bank_jp_kr": per_bank,
        "components": pk["n_comp"],
        "max_component": max(pk["comp_size"].values()),
        "banks_used": [(f"${b:02X}", used) for b, used in pk["banks"]],
        "pointers_rewritten": n_ptr,
        "terminators_checked": n_term,
        "widened": widened,
        "menu_bake": {k2: v2 for k2, v2 in poc.items() if k2 != "resident_codes"},
        "immutable_diffs": imm,
        "hook": hk,
        "dicts": dk,
        "written_by_stage": led.report(),
    }
    if extra is not None:
        info["opening_poc"] = extra
    if imm:
        raise SystemExit(f"무변경 구간이 {imm}곳 바뀌었다 — 의도한 자리만 건드려야 한다")
    return bytes(out), info


# ── 오프닝 한글 PoC(코드 수정 없음) ─────────────────────────────────────────────────────────
# 오프닝 첫 화면(alt3 $0B:E96F) 한 조각만 한글로 굽는다. 인게임 메뉴 PoC 와 같은 수법이되
# **소비 경로가 다르다** — 메뉴는 정적 타일맵이고 이쪽은 **대사 엔진**이라, 글자→타일 표($03:F3EC)를
# 거친다. 그래서 빌린 코드의 표 항목을 한글 반쪽 타일로 **돌려 놓는다**:
#   코드 왼쪽 → 타일 t (엔진이 아래를 t+$10 로 그린다 = 글자 왼쪽 반)
#   코드 오른쪽 → 타일 t+1 (아래 t+$11 = 오른쪽 반)
# 오프닝은 뱅크 $1E 가 **같은 시트의 타일 $000~$17F 384개**를 워드 $3000 에 올린다(실측: $1E:E6B4·
# $1E:F168 의 루프가 소스 $18:E02C 에서 3,072B 를 읽는다) — 인게임과 같은 범위라 시트만 고치면 닿는다.
# ⚠ 빌린 코드·타일 자리의 가나는 이 롬 전체에서 깨져 보인다. **A/B 캡처용 롬**이지 배포물이 아니다.
# 굽을 조각은 고를 수 있다 — 기본은 오프닝 첫 화면. 인게임 대사창을 보려면 그쪽 조각 주소를 준다
# (엔진은 같고 **VRAM 자리만 다르다** — 오프닝 워드 $3000 · 인게임 $1000).
OPENING_POC_ADDR = os.environ.get("SFC_POC_SEG", "0BE96F")
OPENING_POC_WIDTH = int(
    os.environ.get("SFC_OPENING_POC_WIDTH", "24")
)  # 반칸 — 원문 최대 줄 길이가 24
# ⚠ 좁게 주면 같은 글자로 줄 수만 늘릴 수 있다 — **화면이 몇 줄까지 받나**를 재는 데 쓴다(글리프 비용 0).
OPENING_POC_ROWS = [
    18,
    16,
    14,
    12,
    10,
    8,
    6,
    4,
]  # 빌릴 시트 행 쌍(위 행 번호) — 20·22 는 메뉴 PoC 몫
OPENING_POC_CODE_TOP = 0xCE  # 빌릴 글자 코드는 여기서부터 내려간다


def _kr_wrap(kr: str, width: int) -> str:
    """어절 단위 그리디 줄바꿈. 한 자의 칸 수는 **글꼴이 정한다**(D1=B 반각이면 1 · 전각이면 2)."""
    import hangul_font

    hw = 1 if hangul_font.CELL_W == 8 else 2

    def w(t: str) -> int:
        return sum(hw if "가" <= c <= "힣" else 1 for c in t)

    lines, cur = [], ""
    for word in kr.replace("\n", " ").split(" "):
        if not word:
            continue
        cand = word if not cur else f"{cur} {word}"
        if w(cand) > width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def opening_poc(rom: bytes) -> tuple[str, callable, callable]:
    """(조각 id, kr_items 용 인코더, out 에 글리프·표를 굽는 함수)를 돌려준다."""
    import types

    import hangul_font

    tmap = json.loads((common.GAME_DIR / "textmap" / "segments.json").read_text(encoding="utf-8"))
    addrs = [a.strip() for a in OPENING_POC_ADDR.split(",") if a.strip()]
    sids = [next(k for k, v in tmap.items() if v.get("addr") == a) for a in addrs]
    krs = {i: _kr_wrap(tmap[i]["kr"].split("<")[0].rstrip(), OPENING_POC_WIDTH) for i in sids}
    kr = "\n".join(krs.values())  # 자리 배정은 전부 합쳐서 한 번에

    # 자리 배정 — 결정적으로(등장 순서 아닌 코드포인트 순서)
    syls = sorted({c for c in kr if "가" <= c <= "힣"})
    puncts = sorted({c for c in kr if c not in " \n" and not ("가" <= c <= "힣")})
    # ⚠ 안 빌린 코드가 쓰는 타일은 덮으면 안 된다 — 공백(코드 $10)이 타일 $108 이라 실제로 깨졌다
    # (오프닝 실기, 2026-09-06: 어절 사이에 한글 조각이 끼어 보였다).
    tab0 = common.snes2off(text.TILE_TABLE)
    keep = {0x000}
    for c in (text.SPACE, 0xCF & 0xFF):
        if c < 0xD0:
            t0 = rom[tab0 + 2 * c] | ((rom[tab0 + 2 * c + 1] & 3) << 8)
            keep |= {t0, t0 + 0x10}
    half = hangul_font.CELL_W == 8
    step = 1 if half else 2
    quads = [
        16 * r + c
        for r in OPENING_POC_ROWS
        for c in range(0, 16, step)
        if not (
            (
                {16 * r + c, 16 * r + c + 0x10}
                if half
                else {16 * r + c, 16 * r + c + 1, 16 * r + c + 0x10, 16 * r + c + 0x11}
            )
            & keep
        )
    ]
    need = len(syls) + (len(puncts) if half else (len(puncts) + 1) // 2)
    if need > len(quads):
        raise SystemExit(f"오프닝 PoC 글리프 자리가 모자란다: {need} > {len(quads)}")
    codes = [c for c in range(OPENING_POC_CODE_TOP, -1, -1) if c != text.SPACE]
    per = 1 if half else 2  # 한 자에 드는 코드 수 = 칸 수
    if per * len(syls) + len(puncts) > len(codes):
        raise SystemExit("PoC 코드가 모자란다")

    tile_of: dict[str, int] = {}
    code_of: dict[str, tuple[int, ...]] = {}
    ci = 0
    for i, ch in enumerate(syls):
        tile_of[ch] = quads[i]
        code_of[ch] = tuple(codes[ci : ci + per])
        ci += per
    for j, ch in enumerate(puncts):  # 반각 — 한 자리만 쓴다
        tile_of[ch] = quads[len(syls) + (j if half else j // 2)] + (0 if half else j % 2)
        code_of[ch] = (codes[ci],)
        ci += 1

    def enc_override(sid_, entry):
        b = bytearray()
        for ch in krs[sid_]:
            if ch == "\n":
                b.append(0xCF)
            elif ch == " ":
                b.append(text.SPACE)
            else:
                b += bytes(code_of[ch])
        return types.SimpleNamespace(parts=[("bytes", bytes(b)), ("ctrl",)], runtime_josa=0)

    def bake(out: bytearray, src: bytes) -> dict:
        font = hangul_font.load_font()
        sheet = common.snes2off(text.FONT_SHEET)
        tab = common.snes2off(text.TILE_TABLE)
        for ch, t in tile_of.items():
            rows = hangul_font.render(ch, font)
            wide = not half and len(code_of[ch]) == 2  # 전각 글꼴의 한글만 네 타일을 쓴다
            if not wide and not half and any(r & 0x00FF for r in rows):
                raise SystemExit(f"반각으로 넣을 글자가 8칸을 넘는다: {ch!r}")
            bake_glyph(out, sheet, t, rows, half=not wide)
            for k, code in enumerate(code_of[ch]):  # 글자→타일 표를 반쪽 타일로 돌린다
                attr = src[tab + 2 * code + 1] & 0xFC  # 그 코드가 쓰던 속성은 그대로
                out[tab + 2 * code] = (t + k) & 0xFF
                out[tab + 2 * code + 1] = attr | (((t + k) >> 8) & 3)
        return {
            "segs": {i: krs[i].split("\n") for i in sids},
            "syllables": len(syls),
            "puncts": "".join(puncts),
            "cell": f"{hangul_font.CELL_W}x{hangul_font.CELL}",
            "tiles": (len(syls) + len(puncts)) * (2 if half else 4),
            "codes": per * len(syls) + len(puncts),
            "font": hangul_font.FONT_NAME,
        }

    return set(sids), enc_override, bake


def write_image(out: bytes, info: dict, build_path: str) -> None:
    """빌드 칸에 이미지 하나만 남긴다(낡은 것을 정상으로 오해하는 사고를 막는다).

    ⚠ `build_path` 는 "kr"(`build_kr()`, 실제 굽는 이미지) 아니면 "poc"(`build()`, 구조 재배치 +
    메뉴 PoC) — 2026-09-15 빌드 지문 소동(patcher-checklist.md 3-B)의 재발 방지책. 파일명 접미
    + manifest 의 `build_path` 칸, **둘 다** 남긴다 — 지문을 옮겨 적을 때 무엇을 쟀는지가
    값으로 같이 남게."""
    d = common.BUILD_DIR / common.BUILD_TAG
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.sfc*"):
        old.unlink()
    dst = d / OUT_NAME[build_path]
    dst.write_bytes(out)
    sha = hashlib.sha1(out).hexdigest()
    (d / "manifest.json").write_text(
        json.dumps(
            {"build_path": build_path, "source_sha1": common.ROM_SHA1, "output_sha1": sha, **info},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"→ {dst}  sha1 {sha}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="빌드하고 검증만(파일은 안 남긴다)")
    ap.add_argument(
        "--project",
        action="store_true",
        help="한글 경로 투영 — 번역된 조각을 인코딩해 뱅크에 담아 보고만 한다",
    )
    ap.add_argument(
        "--opening-poc",
        action="store_true",
        help="오프닝 첫 화면만 한글로 구운 A/B 롬을 work/derived/ 에 쓴다(코드 수정 없음)",
    )
    ap.add_argument(
        "--kr",
        action="store_true",
        help="한글 롬(렌더러 훅 포함)을 빌드 칸에 쓴다 — 이게 굴리는 이미지다",
    )
    ap.add_argument(
        "--no-hook", action="store_true", help="훅 없이 한글 데이터만(대조군 — 깨져 보이는 게 정상)"
    )
    a = ap.parse_args()
    if a.opening_poc:
        import hangul_font

        rom = common.rom_bytes()
        sids, enc_override, bake = opening_poc(rom)
        out, info = build_kr(rom, only=sids, enc_override=enc_override, after=bake)
        print(json.dumps(info["opening_poc"], ensure_ascii=False, indent=1))
        dst = common.OUT_DIR / f"poc_{hangul_font.FONT_NAME}.sfc"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(out)
        print("→", dst, hashlib.sha1(out).hexdigest())
        return
    if a.project or a.kr:
        rom = common.rom_bytes()
        out, info = build_kr(rom, with_hook=not a.no_hook)
        print(json.dumps(info, ensure_ascii=False, indent=1))
        if a.kr:
            write_image(out, info, "kr")
        return
    rom = common.rom_bytes()
    out, info = build(rom)
    v = verify(rom, out, relocation_plan(body_items(rom)))
    ok = (
        v["immutable_diffs"] == 0
        and v["readback_mismatch"] == 0
        and v["reverse_roundtrip"]
        and v["lead_collisions"] == 0
    )
    print(info, v)
    if not ok:
        raise SystemExit("빌드 검증 실패")
    if a.check:
        print("검증 OK")
        return
    write_image(out, info | v, "poc")


if __name__ == "__main__":
    main()
