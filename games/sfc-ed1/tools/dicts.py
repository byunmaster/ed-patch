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
    dm = json.loads((common.GAME_DIR / "textmap" / "dict.json").read_text(encoding="utf-8"))
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
    info["tables"] = tables
    return info


def patch_ranges() -> list[tuple[int, int]]:
    """원본 1MB 안에서 바꾸는 자리 — 설정 루틴 여섯의 즉치뿐이다."""
    r = []
    for addr in SETUP.values():
        o = common.snes2off(addr)
        r += [(o + i, o + i + 1) for i in IMM]
    return r


def verify(out: bytes, slots: list) -> dict:
    """🔑 **체인이 다 끝난 롬**에서 게임이 하는 그대로 되읽는다 — 설정 루틴의 즉치 셋 → 표 → 문자열.

    앞 단계가 깔아 둔 것을 뒤 단계가 덮어도 「자기가 쓴 직후」를 보는 되읽기는 초록이다
    (다른 트랙 실측, 관리자 중계 2026-09-07). 그래서 **마지막에 한 번 더** 본다.
    ⚠ 우리가 적어 둔 주소가 아니라 **롬에 박힌 즉치**를 따라간다 — 그래야 덮인 걸 잡는다."""
    dm = json.loads((common.GAME_DIR / "textmap" / "dict.json").read_text(encoding="utf-8"))
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
