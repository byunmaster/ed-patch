"""sfc-ed2 UI 창 블록 — 시작 메뉴·상점·상태 같은 **좌표 고정 칸**의 문자열(출력기 `$C0:9395`).

창 정의 블록(`$C0:D6A7` 이 `[$A3~$A5]` 24비트 포인터로 읽어 WRAM `$7F:D428` 로 복사, 2026-10-12 디스어셈블):
    +0 x · +1 y · +2 w(가로 칸, 8px 단위 − 1 로 추정) · +3 rows(줄 수) · +4 stride(줄당 바이트) · +5~ rows × stride 바이트
  줄 하나 = 제어($18+ 색 등)·반각($20 공백)·전각(2바이트)·`$00` 종료, 남는 칸은 공백으로 채운다. 줄 길이는 stride 고정이다.
블록은 `$C0:D6A7` 호출 직전의 즉치 `A9 lo 8D A3 00 A9 hi 8D A4 00 A9 bank 8D A5 00` 로 가리킨다 — 이 즉치 3바이트만 고치면
블록을 **다른 곳(확장 뱅크)으로 옮기며 stride·w 를 넓힐 수 있다**(`ptr_sites`).

    python3 games/sfc-ed2/tools/ui.py          # 블록 목록과 줄 원문
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import script

PTR = re.compile(rb"\xa9(.)\x8d\xa3\x00\xa9(.)\x8d\xa4\x00\xa9(.)\x8d\xa5\x00", re.S)


def ptr_sites(d: bytes) -> list[tuple[int, int]]:
    """즉치로 창 블록을 가리키는 자리 → [(코드 오프셋, 블록 주소)]. 코드 오프셋은 첫 `A9` 의 파일 위치."""
    out = []
    for m in PTR.finditer(d[:0x20000]):
        addr = m.group(3)[0] << 16 | m.group(2)[0] << 8 | m.group(1)[0]
        if addr >> 16 >= 0xC0:
            out.append((m.start(), addr))
    return out


def blocks(d: bytes) -> list[int]:
    return sorted({a for _o, a in ptr_sites(d)})


def parse(d: bytes, addr: int) -> dict:
    o = common.snes2off(addr)
    x, y, w, rows, stride = d[o : o + 5]
    return {
        "addr": addr,
        "x": x,
        "y": y,
        "w": w,
        "rows": rows,
        "stride": stride,
        "raw": [d[o + 5 + i * stride : o + 5 + (i + 1) * stride] for i in range(rows)],
    }


def row_text(d: bytes, raw: bytes) -> str:
    """줄 → 글자(공백 포함, 제어 생략)."""
    buf = bytearray(d[:0])  # 빈 bytes
    buf = raw + b"\x00"
    out = []
    i = 0
    while i < len(buf):
        b = buf[i]
        if b == 0:
            break
        ln = script.token_len(buf, i)
        if ln is None:
            out.append("？")
            break
        if 0x80 <= b < 0x88 or 0xE2 <= b < 0xF0:
            out.append(script.glyph_char((b << 8) | buf[i + 1]))
        elif 0x20 <= b < 0x80:
            out.append(chr(b))
        elif 0x88 <= b < 0xE0:
            import glyphmap

            out.append(glyphmap.HALF_TABLE[b - 0x88])
        i += ln
    return "".join(out)


def px_width(row: bytes) -> int:
    """줄의 화면 가로(px): 전각 12 · 반각 8 · 제어 0."""
    i, w = 0, 0
    while i < len(row) and row[i] != 0:
        ln = script.token_len(row, i) or 1
        w += 12 if (0x80 <= row[i] < 0x88 or 0xE2 <= row[i] < 0xF0) else (8 if 0x20 <= row[i] < 0xE0 else 0)
        i += ln
    return w


def put_rows(rom: bytearray, addr: int, rows: list[bytes], writes: list) -> None:
    """창 블록의 줄을 **제자리**에서 바꾼다(줄 수·stride 고정). 줄 = 제어·글자 바이트(종료 `$00`·공백 채움은 여기서).
    한 줄이 stride−1 바이트를 넘으면 죽는다 — 그땐 `move_block` 으로 블록을 옮겨 stride 를 넓힌다."""
    o = common.snes2off(addr)
    x, y, w, n, stride = rom[o : o + 5]
    if len(rows) != n:
        raise SystemExit(f"{common.fmt(addr)}: 줄 수 {len(rows)} ≠ {n}")
    for i, r in enumerate(rows):
        if len(r) > stride - 1:
            raise SystemExit(f"{common.fmt(addr)} 줄 {i}: {len(r)}B > stride−1={stride - 1} — 블록을 옮겨 넓혀야 한다")
        if px_width(r) > (w + 1) * 8:
            raise SystemExit(f"{common.fmt(addr)} 줄 {i}: {px_width(r)}px > 창 {(w + 1) * 8}px — w 를 넓혀야 한다")
        rom[o + 5 + i * stride : o + 5 + (i + 1) * stride] = r + b"\x20" * (stride - 1 - len(r)) + b"\x00"
    writes.append((o + 5, o + 5 + n * stride))


def move_block(rom: bytearray, src: bytes, addr: int, new_addr: int, rows: list[bytes], writes: list, w: int | None = None) -> int:
    """창 블록을 `new_addr`(확장 뱅크)로 옮기며 stride·w 를 줄 내용에 맞춰 넓힌다. 창 폭은 줄 **전체**(앞뒤 공백 포함) px 로 잡는다 —
    원본도 앞뒤에 반각 공백 1~2 개를 두어 글자가 테두리에 안 닿게 한다(공백 없이 넘기면 마지막 글자가 잘린다, 2026-10-12 에뮬 실측). 이 블록을 가리키는 즉치 포인터를 전부 고친다.
    반환 = 다음 빈 주소(`new_addr` + 블록 길이)."""
    o = common.snes2off(addr)
    x, y, w0, n, _stride = src[o : o + 5]
    if len(rows) != n:
        raise SystemExit(f"{common.fmt(addr)}: 줄 수 {len(rows)} ≠ {n}")
    stride = max(len(r) for r in rows) + 1
    w1 = max(w0, w if w is not None else 0, -(-max(px_width(r) for r in rows) // 8) - 1)
    blk = bytes([x, y, w1, n, stride]) + b"".join(r + b"\x20" * (stride - 1 - len(r)) + b"\x00" for r in rows)
    no = common.snes2off(new_addr)
    rom[no : no + len(blk)] = blk
    writes.append((no, no + len(blk)))
    hit = 0
    for co, a in ptr_sites(src):
        if a == addr:
            rom[co + 1], rom[co + 6], rom[co + 11] = new_addr & 0xFF, (new_addr >> 8) & 0xFF, new_addr >> 16
            writes += [(co + 1, co + 2), (co + 6, co + 7), (co + 11, co + 12)]
            hit += 1
    if not hit:
        raise SystemExit(f"{common.fmt(addr)}: 이 블록을 가리키는 즉치가 없다")
    return new_addr + len(blk)


if __name__ == "__main__":
    common.verify_originals()
    d = common.rom_bytes()
    for a in blocks(d):
        b = parse(d, a)
        if not (1 <= b["rows"] <= 30 and 1 <= b["stride"] <= 80):
            print(f"{common.fmt(a)}  (창 블록 아님 — {b['rows']}×{b['stride']})")
            continue
        print(f"{common.fmt(a)}  x={b['x']} y={b['y']} w={b['w']} {b['rows']}줄×{b['stride']}B")
        for r in b["raw"]:
            print("    |" + row_text(d, r) + "|")
