"""sfc-ed1 사전 여섯 벌을 확장 뱅크로 옮긴다 — 이름·아이템·몬스터·시스템 문장이 한글로 나온다.

**왜 옮겨야 하나** — 한글은 한 자가 2바이트라 사전이 제자리에 안 든다(뱅크 `$02` 는 1,916B →
2,531B 로 615B 모자라고 그 뱅크의 빈 자리는 425B 뿐이다). 그런데 **뱅크를 갈아 끼울 수 있다**:

```
$02:DF77  ; $173A($D0~$D5) 로 갈래를 잡아 아래 여섯 중 하나를 부른다
$02:DFC2  LDA #$02 / STA $0006   ; ┐ 표 주소 하위
          LDA #$E9 / STA $0007   ; ├ 상위
          LDA #$02 / STA $0008   ; ┘ **뱅크** ← 여기 한 바이트
$02:E047  ASL A / TAY            ; 색인 ×2
          LDA [$06],Y → $1E      ; 표에서 16비트 포인터를 읽어
          ...      → $1F
          LDA $1E → $06          ; **$06/$07 만 덮어쓴다 — $08(뱅크)은 그대로**
          LDA #$FF / TAY / TAX
   loop:  INY / INX / LDA [$06],Y / STA $174C,X / CMP #$FF / BNE loop
```

⇒ 표와 문자열이 **같은 뱅크**에 있기만 하면 되고, 그 뱅크는 **설정 루틴의 즉치 셋**이 정한다.
그래서 `[2B × n 포인터 표][문자열들]` 을 확장 뱅크에 통째로 놓고 즉치 셋만 고친다.
🔴 **문자열은 `$FF` 로 끝난다** — 그래서 글리프 색인 하위가 `$FF` 인 자리를 인코더가 비워 둔다
(`encode.bad_index`). 안 그러면 그 글자가 든 이름이 **거기서 잘린다**.
⚠ 표 색인은 `ASL A`(8비트)라 항목이 128을 넘으면 안 된다 — 제일 큰 게 아이템 119다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001
import common
import encode
import namesrc

BANK = 0x3E  # 사전 전용 확장 뱅크(표 + 문자열)
ORG = 0x8000
TERM = 0xFF
# 🔴 **문자열은 버퍼로 복사된다** — `$02:E066` 이 `$174C,X` 에 한 바이트씩 옮긴다.
# `$176A`·`$176B` 는 다른 코드가 참조하므로 버퍼는 `$174C~$1769` = **30B**(종단자 포함)로 본다.
# 넘치면 `$176C`(칸 속성) 부터를 덮어써 **창이 검게 죽는다**(2026-09-07 실측: 33B 짜리 한 줄에
# 인트로가 멈췄다). 원문 최장은 16B 라 원본은 안 걸린다 — **한글로 늘어나면서 생긴 제약**이다.
MAX_LEN = 28  # 종단자 빼고. 30B 버퍼에 안전 여유 하나
# 사전 코드 → 설정 루틴 주소(뱅크 $02). 각 루틴은 `A9 lo · A9 hi · A9 bank` 를 DP $06/$07/$08 에 넣는다.
SETUP = {
    0xD0: 0x02DFC2,
    0xD1: 0x02DFD2,
    0xD2: 0x02DFE2,
    0xD3: 0x02DFF2,
    0xD4: 0x02E002,
    0xD5: 0x02E012,
}
IMM = (1, 6, 11)  # 루틴 안에서 lo · hi · bank 즉치의 자리


def _check_setup(rom: bytes) -> None:
    """설정 루틴이 예상한 모양인지 — 원본 표 주소를 그대로 되짚는다(엉뚱한 자리를 고치지 않게)."""
    for code, addr in SETUP.items():
        o = common.snes2off(addr)
        want = text.DICT_TABLES[code][0]
        got = rom[o + IMM[0]] | (rom[o + IMM[1]] << 8) | (rom[o + IMM[2]] << 16)
        if got != want or rom[o] != 0xA9 or rom[o + 5] != 0xA9 or rom[o + 10] != 0xA9:
            raise SystemExit(
                f"사전 ${code:02X} 설정 루틴이 예상과 다르다 @{common.fmt(addr)}: {got:06X}"
            )


def encode_all(rep_index: dict[str, int]) -> dict[int, list[bytes]]:
    """`textmap/dict.json` → 사전별 문자열 바이트열. 번역이 없거나 인코딩이 안 되면 **운다**."""
    dm = namesrc.dict_map()
    out: dict[int, list[bytes]] = {}
    errs = []
    for code, (_addr, n, name) in text.DICT_TABLES.items():
        rows = []
        for i in range(n):
            e = dm.get(f"{code:02X}:{i:02X}")
            kr = (e or {}).get("kr")
            if not kr:
                errs.append(f"${code:02X}[{i:02X}] {name} 번역 없음")
                rows.append(b"")
                continue
            try:
                enc = encode.encode(kr, rep_index)
            except ValueError as ex:
                errs.append(f"${code:02X}[{i:02X}] {kr!r}: {ex}")
                rows.append(b"")
                continue
            b = b"".join(v[0] if k == "bytes" else v[1] for k, *v in enc.parts)
            if TERM in b:
                errs.append(f"${code:02X}[{i:02X}] {kr!r} 안에 $FF — 문자열이 잘린다")
            if len(b) > MAX_LEN:
                errs.append(f"${code:02X}[{i:02X}] {kr!r} 가 {len(b)}B — 버퍼 {MAX_LEN}B 를 넘는다")
            rows.append(b)
        out[code] = rows
    if errs:
        raise SystemExit(f"사전 인코딩 실패 {len(errs)}건:\n  " + "\n  ".join(errs[:12]))
    return out


def bake(out: bytearray, rom: bytes, rep_index: dict[str, int]) -> dict:
    """확장 뱅크에 [표][문자열] 을 놓고 설정 루틴의 즉치 셋을 우리 것으로 바꾼다."""
    _check_setup(rom)
    rows = encode_all(rep_index)
    cur = ORG
    info = {}
    tables: dict[int, int] = {}
    for code, (_addr, n, name) in text.DICT_TABLES.items():
        strs = rows[code]
        table = cur
        cur += 2 * n
        ptr = []
        for b in strs:
            ptr.append(cur)
            blob = b + bytes([TERM])
            o = common.snes2off((BANK << 16) | cur)
            out[o : o + len(blob)] = blob
            cur += len(blob)
        if cur > 0x10000:
            raise SystemExit(f"사전 뱅크가 넘친다: {cur:#x}")
        t = common.snes2off((BANK << 16) | table)
        for i, p in enumerate(ptr):
            out[t + 2 * i : t + 2 * i + 2] = p.to_bytes(2, "little")
        s = common.snes2off(SETUP[code])
        out[s + IMM[0]] = table & 0xFF
        out[s + IMM[1]] = table >> 8
        out[s + IMM[2]] = BANK
        tables[code] = (BANK << 16) | table
        info[f"${code:02X} {name}"] = {
            "n": n,
            "table": common.fmt((BANK << 16) | table),
            "bytes": cur - table,
        }
    info["끝"] = common.fmt((BANK << 16) | cur)
    info["next"] = cur  # 뒤에 오는 것(전투 UI 표)이 이어 쓴다
    info["tables"] = tables
    return info


# 🔴 **런타임 치환(`$D6~$DF`)도 같은 표를 따로 가리킨다**(2026-09-26 실기 — B1 「해독초를 사용했다」의
# 아이템 이름이 원문 가나로 깨졌다). 핸들러(`$02:E0CE~`)가 **자기 즉치 셋**으로 `$06~$08` 에 표를 넣고
# 같은 버퍼 복사(`$02:E047`)로 간다 — 사전 코드의 설정 루틴과 모양이 같아(`IMM`) 즉치만 바꾸면 된다.
# 롬 전체에서 `LDA #lo/STA $06 · #hi/$07 · #bank/$08` 을 훑어 원본 표를 가리키는 건 이 넷 + 아래 둘이 전부다.
RUNTIME_SITES = {0x02E0F5: 0xD0, 0x02E106: 0xD3, 0x02E119: 0xD2, 0x02E134: 0xD3}
# 주문 이름 — `$03:EEDD`(32칸, 색인 & $1F)는 `$D4` 사전(21)과 **다른 배열**이다(빈 칸은 `$03:EF72` 의
# 쓰레기를 가리킨다 — 원본도 안 쓰는 자리). 같은 문자열 바이트로 `$D4` 항목에 이어 붙인다.
SPELL_SITE = 0x02E14F
SPELL_TABLE = 0x03EEDD
SPELL_N = 32
# 지명 — `$02:A793`(HUD 지명 표, `places.TABLES["a"]`)을 그대로 가리킨다. 한글 표는 `places.bake` 가 만든다.
PLACE_SITE = 0x02E0D2
PLACE_ORIG = 0x02A793
RUNTIME_ALL = [*RUNTIME_SITES, SPELL_SITE, PLACE_SITE]


def _imm(buf, site: int) -> int:
    o = common.snes2off(site)
    if buf[o] != 0xA9 or buf[o + 5] != 0xA9 or buf[o + 10] != 0xA9:
        raise SystemExit(f"런타임 치환 설정 자리가 예상과 다르다 @{common.fmt(site)}")
    return buf[o + IMM[0]] | (buf[o + IMM[1]] << 8) | (buf[o + IMM[2]] << 16)


def _set_imm(out: bytearray, site: int, addr: int) -> None:
    o = common.snes2off(site)
    out[o + IMM[0]] = addr & 0xFF
    out[o + IMM[1]] = (addr >> 8) & 0xFF
    out[o + IMM[2]] = addr >> 16


def bake_runtime(
    out: bytearray, rom: bytes, tables: dict[int, int], place_a: int, org: int
) -> dict:
    """런타임 치환 여섯 자리를 한글 표로 돌린다. 주문 표(32칸)만 새로 `org` 에 굽는다."""
    want = {**{s: text.DICT_TABLES[c][0] for s, c in RUNTIME_SITES.items()}}
    want[SPELL_SITE] = SPELL_TABLE
    want[PLACE_SITE] = PLACE_ORIG
    for s, w in want.items():
        if _imm(rom, s) != w:
            raise SystemExit(f"런타임 치환 {common.fmt(s)} 이 {w:06X} 를 안 가리킨다")
    for s, c in RUNTIME_SITES.items():
        _set_imm(out, s, tables[c])
    _set_imm(out, PLACE_SITE, place_a)
    # 주문: 원본 `$03:EEDD[i]` 문자열 == `$D4[j]` 문자열이면 우리 `$D4` 표의 j 번 포인터를 쓴다
    d4 = {bytes(b): j for j, b in enumerate(text.dict_entries(0xD4))}
    d4_table = common.snes2off(tables[0xD4])
    empty = org + 2 * SPELL_N  # 빈 칸용 종단자 하나
    out[common.snes2off((BANK << 16) | empty)] = TERM
    base = common.snes2off(SPELL_TABLE)
    hit = 0
    for i in range(SPELL_N):
        p = rom[base + 2 * i] | (rom[base + 2 * i + 1] << 8)
        j = None
        if p >= 0x8000:  # 끝 두 칸(30·31)은 표 밖 값이다 — 원본도 안 쓴다
            so = common.snes2off((SPELL_TABLE & 0xFF0000) | p)
            j = d4.get(bytes(rom[so : rom.index(b"\xff", so)]))
        if j is None:
            q = empty
        else:
            q = out[d4_table + 2 * j] | (out[d4_table + 2 * j + 1] << 8)
            hit += 1
        t = common.snes2off((BANK << 16) | org) + 2 * i
        out[t : t + 2] = q.to_bytes(2, "little")
    if hit != 21:
        raise SystemExit(f"주문 표 {SPELL_N}칸 중 `$D4` 와 이어진 게 {hit} 이다(21 이어야 한다)")
    _set_imm(out, SPELL_SITE, (BANK << 16) | org)
    return {
        "주문 표": common.fmt((BANK << 16) | org),
        "주문 표 주소": (BANK << 16) | org,  # 필드 주문 목록 훅(`hook.spellcopy`)도 이걸 읽는다
        "next": empty + 1,
    }


def patch_ranges() -> list[tuple[int, int]]:
    """원본 1MB 안에서 바꾸는 자리 — 설정 루틴 여섯 + 런타임 치환 여섯의 즉치뿐이다."""
    r = []
    for addr in [*SETUP.values(), *RUNTIME_ALL]:
        o = common.snes2off(addr)
        r += [(o + i, o + i + 1) for i in IMM]
    return r


def verify(out: bytes, slots: list) -> dict:
    """🔑 **체인이 다 끝난 롬**에서 게임이 하는 그대로 되읽는다 — 설정 루틴의 즉치 셋 → 표 → 문자열.

    앞 단계가 깔아 둔 것을 뒤 단계가 덮어도 「자기가 쓴 직후」를 보는 되읽기는 초록이다
    (다른 트랙 실측, 관리자 중계 2026-09-07). 그래서 **마지막에 한 번 더** 본다.
    ⚠ 우리가 적어 둔 주소가 아니라 **롬에 박힌 즉치**를 따라간다 — 그래야 덮인 걸 잡는다."""
    dm = namesrc.dict_map()
    bad = []
    n_ok = 0
    for code, addr in SETUP.items():
        o = common.snes2off(addr)
        table = (out[o + IMM[2]] << 16) | (out[o + IMM[1]] << 8) | out[o + IMM[0]]
        bank = table & 0xFF0000
        n = text.DICT_TABLES[code][1]
        t = common.snes2off(table)
        for i in range(n):
            p = out[t + 2 * i] | (out[t + 2 * i + 1] << 8)
            so = common.snes2off(bank | p)
            end = out.find(bytes([TERM]), so)
            if end < 0 or end - so > MAX_LEN:
                bad.append(f"${code:02X}[{i:02X}] 종단자를 못 찾거나 너무 길다")
                continue
            got = encode.decode_kr(out[so:end], slots)
            want = dm[f"{code:02X}:{i:02X}"]["kr"]
            if got != want:
                bad.append(f"${code:02X}[{i:02X}] {got!r} ≠ {want!r}")
            else:
                n_ok += 1
    if bad:
        raise SystemExit(f"사전 되읽기 실패 {len(bad)}건:\n  " + "\n  ".join(bad[:10]))
    return {"읽은 항목": n_ok}
