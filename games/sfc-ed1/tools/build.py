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
import common
import script

OUT_NAME = "Dragon Slayer - Eiyuu Densetsu (KR).sfc"
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
MENU_POC_SLOTS = list(range(0x140, 0x150)) + list(range(0x160, 0x170)) + list(range(0x120, 0x130))
MENU_POC_WINDOWS = [
    ("A", 0x01),
    ("A", 0x06),  # 시스템 창(제자리 확장) — 로드·저장·시스템·설정
    ("B", 0x0A),
    ("B", 0x0C),
]  # 순서 고정(결정성) — C0A 는 B0A 와 같은 항목
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


def menu_poc(out: bytearray, rom: bytes) -> dict:
    """커맨드 창 라벨을 한글로 — 시트의 빌린 타일에 글리프를 굽고, 창 배치 워드를 그 타일로 바꾼다."""
    import hangul_font
    import menus

    labels = json.loads((common.GAME_DIR / "textmap" / "menus.json").read_text(encoding="utf-8"))
    font = hangul_font.load_font()
    inv = menus.inverse_tile_table(rom)
    sheet = common.snes2off(text.FONT_SHEET)
    slot_of: dict[str, int] = {}

    def slot(ch: str) -> int:
        if ch not in slot_of:
            if len(slot_of) >= len(MENU_POC_SLOTS):
                raise SystemExit(f"메뉴 PoC 글리프 자리가 모자란다: {''.join(slot_of)} + {ch}")
            t = MENU_POC_SLOTS[len(slot_of)]
            bake_glyph(out, sheet, t, hangul_font.render(ch, font), hangul_font.CELL_W == 8)
            slot_of[ch] = t
        return slot_of[ch]

    done = []
    for table, wid in MENU_POC_WINDOWS:
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
                else:
                    raise SystemExit(f"메뉴 PoC 는 한글·공백만: {kr!r}")
            # ⚠ 칸 예산은 **지금 기록에서 잰다** — menus.json 의 값은 원본 폭에서 잰 것이라
            #   창을 안 넓히면 오른쪽 틀과 다음 줄 첫 칸까지 덮어썼다(실기 2026-09-06: 틀이 통째로 사라졌다).
            x1 = next((i for i in range(x0, w) if line[i] == menus.FRAME), w)
            budget = x1 - x0
            if len(words_top) > budget:
                raise SystemExit(f"{m[0]} {kr!r} 가 {budget}칸을 넘는다")
            words_top += [0x0108] * (budget - len(words_top))
            words_bot += [0x0108] * (budget - len(words_bot))
            for i, (wt, wb) in enumerate(zip(words_top, words_bot, strict=True)):
                a = o + 4 + 2 * (r * w + x0 + i)
                b = o + 4 + 2 * ((r + 1) * w + x0 + i)
                out[a : a + 2] = wt.to_bytes(2, "little")
                out[b : b + 2] = wb.to_bytes(2, "little")
            done.append((m[0], kr))
    return {"glyphs": "".join(slot_of), "labels": len(done)}


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
    poc = menu_poc(out, rom)
    # ⚠ 제자리로 넓힌 기록(부분 갱신)은 크기가 그대로라 「원래 모습」이 서명이 못 된다 — 자리를 옮긴 것만 본다
    pair_bad = check_widen_pairs(rom, out, [w["orig"] for w in widened if w["grew"]])
    if pair_bad:
        raise SystemExit(
            f"넓힌 창의 짝(지우는 기록)이 안 넓혀졌다 — 닫으면 잔상이 남는다: {pair_bad}"
        )
    out[HEADER_ROM_SIZE_OFF] = 0x0B  # 2048KB
    fix_checksum(out)
    info = {
        "items": len(items),
        "body_bytes": len(body),
        "body_new": common.fmt(common.off2snes(ns)),
        "pointers_rewritten": n_ptr,
        "widened": widened,
        "menu_poc": poc,
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
    for table, wid in MENU_POC_WINDOWS:  # 라벨을 제자리에 다시 굽는 창(넓히지 않은 것도 있다)
        base = common.snes2off(menus.LAYOUT_TABLES[table])
        p2 = rom[base + 3 * wid] | (rom[base + 3 * wid + 1] << 8) | (rom[base + 3 * wid + 2] << 16)
        o2 = common.snes2off(p2)
        r.append((o2, o2 + 4 + 2 * rom[o2 + 2] * rom[o2 + 3]))
    sheet = common.snes2off(text.FONT_SHEET)
    for t0 in (0x120, 0x140, 0x160):  # 메뉴 PoC 가 빌린 시트 행(위 16 + 아래 16 타일)
        r.append((sheet + 8 * t0, sheet + 8 * (t0 + 0x20)))
    return r


def verify(rom: bytes, out: bytes, place: dict[int, int]) -> dict:
    # 1. 무변경 구간 byte 대조
    mut = mutable_ranges()
    diffs = 0
    for i in range(len(rom)):
        if rom[i] != out[i] and not any(a <= i < b for a, b in mut):
            diffs += 1
            if diffs <= 5:
                print(
                    f"  ⚠ 무변경 구간 차이 {common.fmt(common.off2snes(i))}: {rom[i]:02X}→{out[i]:02X}"
                )

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
        "immutable_diffs": diffs,
        "readback_msgs": total,
        "readback_mismatch": mism,
        "reverse_roundtrip": same_back,
    }


# ── 한글 경로: 번역된 조각을 인코딩해 rel16 군집 단위로 32KB 뱅크에 담는다 ───────────────────────
KR_BANKS = [b for b in range(0x27, 0x40) if b != 0x2C]  # $2C 는 넓힌 창 배치 항목 자리
BANK_CAP = 0x8000


def segment_slices(items: list[script.Item]) -> list[tuple[str, int, int]]:
    """(조각 id, 시작 인덱스, 끝 인덱스(열림)) — units.segments 와 같은 id(원문 바이트 sha1)."""
    import hashlib

    out = []
    start = 0
    for k, it in enumerate(items):
        if it.kind == "ctrl" and it.code in (0xE0, 0xE4):
            raw = b"".join(bytes([x.code]) + x.args for x in items[start : k + 1])
            out.append((hashlib.sha1(raw).hexdigest()[:12], start, k + 1))
            start = k + 1
    return out


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
    rep = encode.repertoire(texts)
    rep_index = {ch: i for i, ch in enumerate(rep)}
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
    comp_of = [find(i) for i in range(len(slices))]
    return {
        "items": new,
        "slices": slices,
        "seg_of": seg_of,
        "comp_of": comp_of,
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
    return {
        "place": place,
        "new_off": new_off,
        "banks": banks,
        "comp_size": comp_size,
        "n_comp": len(comp_segs),
    }


def build_kr(
    rom: bytes,
    states=("reviewed", "draft", "tm-draft"),
    only: set[str] | None = None,
    enc_override=None,
    after=None,
) -> tuple[bytes, dict]:
    k = kr_items(rom, states, only, enc_override)
    pk = pack_banks(k)
    new, place = k["items"], pk["place"]
    out = bytearray(rom) + bytearray(b"\xff" * (NEW_SIZE - len(rom)))
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
    widened = widen_windows(out, rom)
    poc = menu_poc(out, rom)
    extra = after(out, rom) if after is not None else None
    out[HEADER_ROM_SIZE_OFF] = 0x0B
    fix_checksum(out)
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
        "widened": widened,
        "menu_poc": poc,
    }
    if extra is not None:
        info["opening_poc"] = extra
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
    sid = next(k for k, v in tmap.items() if v.get("addr") == OPENING_POC_ADDR)
    kr = _kr_wrap(tmap[sid]["kr"].split("<")[0].rstrip(), OPENING_POC_WIDTH)

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

    def enc_override(_sid, entry):
        b = bytearray()
        for ch in kr:
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
            "seg": sid,
            "lines": kr.split("\n"),
            "syllables": len(syls),
            "puncts": "".join(puncts),
            "cell": f"{hangul_font.CELL_W}x{hangul_font.CELL}",
            "tiles": (len(syls) + len(puncts)) * (2 if half else 4),
            "codes": per * len(syls) + len(puncts),
            "font": hangul_font.FONT_NAME,
        }

    return sid, enc_override, bake


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
        help="한글 데이터 롬을 work/derived/kr_probe.sfc 에 쓴다(렌더러 훅 없음 — 구조 검증용)",
    )
    a = ap.parse_args()
    if a.opening_poc:
        import hangul_font

        rom = common.rom_bytes()
        sid, enc_override, bake = opening_poc(rom)
        out, info = build_kr(rom, only={sid}, enc_override=enc_override, after=bake)
        print(json.dumps(info["opening_poc"], ensure_ascii=False, indent=1))
        dst = common.OUT_DIR / f"poc_{OPENING_POC_ADDR}_{hangul_font.FONT_NAME}.sfc"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(out)
        print("→", dst, hashlib.sha1(out).hexdigest())
        return
    if a.project or a.kr:
        rom = common.rom_bytes()
        out, info = build_kr(rom)
        print(json.dumps(info, ensure_ascii=False, indent=1))
        if a.kr:
            dst = common.OUT_DIR / "kr_probe.sfc"
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(out)
            print("→", dst, hashlib.sha1(out).hexdigest())
        return
    rom = common.rom_bytes()
    out, info = build(rom)
    v = verify(rom, out, relocation_plan(body_items(rom)))
    ok = v["immutable_diffs"] == 0 and v["readback_mismatch"] == 0 and v["reverse_roundtrip"]
    print(info, v)
    if not ok:
        raise SystemExit("빌드 검증 실패")
    if a.check:
        print("검증 OK")
        return
    d = common.BUILD_DIR / common.BUILD_TAG
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.sfc*"):  # 한 칸에 하나만
        old.unlink()
    dst = d / OUT_NAME
    dst.write_bytes(out)
    sha = hashlib.sha1(out).hexdigest()
    (d / "manifest.json").write_text(
        json.dumps(
            {"source_sha1": common.ROM_SHA1, "output_sha1": sha, **info, **v},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"→ {dst}  sha1 {sha}")


if __name__ == "__main__":
    main()
