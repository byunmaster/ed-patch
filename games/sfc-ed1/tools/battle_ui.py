"""sfc-ed1 전투 UI·파티 이름 — 13칸 고정 문자열 여덟을 한글로.

**다섯째 문**이다. 이 여덟은 대사도 사전도 메뉴 이름도 아닌 **또 다른 경로**로 그려진다:

```
$02:A2C8  LDA $02A30A,X → $06 / LDA $02A30B,X → $07   ; 포인터 표
$02:A2D9  REP #$30
$02:A2DB  LDX $0006 / LDY #$0305 / LDA #$000C
$02:A2E4  MVN $02,$00        ; ← **블록 전송** 13바이트를 칸 배열로 통째로
$02:A2E9  JSL $02B07B        ; 타일 변환
```

🔴 `MVN` 은 **한 바이트 = 한 칸**을 전제한다 — 두 바이트 한글은 여기서 절대 못 산다.
바이트를 훑는 자리가 아예 없어서 「훅을 건다」가 성립하지 않는다 ⇒ **전송 자체를 우리 루프로 갈아 끼운다**
(`hook.name13`). 그러면 소스 길이와 칸 수가 갈라져도 된다.

⚠ 표 색인은 `ASL A` 뒤 `TAX` 이고 항목이 여덟이라 8비트로 충분하다.
⚠ 끝나고 **DB = $00** 이어야 한다 — 원본 `MVN` 이 목적지 뱅크를 DB 에 남기고, 뒤 코드가 그걸 쓴다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: F401, I001
import common
import dicts
import encode

TABLE = 0x02A30A  # 원본 포인터 표(2B × 8)
COUNT = 8
CELLS = 13
SETUP = (0x02A2C8, 0x02A2CF)  # `LDA $02A30A,X` · `LDA $02A30B,X` — 피연산자를 우리 표로


def rows() -> list[list[str]]:
    """여덟 줄을 **칸 단위 글자 목록**으로 — 격자 셋(칸 시작 0·5·10)과 이름 다섯."""
    d = json.loads((common.GAME_DIR / "textmap" / "battle_ui.json").read_text(encoding="utf-8"))
    out = []
    for g in d["grid"]:
        cells = [" "] * CELLS
        for col in g["cols"]:
            for i, ch in enumerate(col["kr"]):
                cells[col["at"] + i] = ch
        out.append(cells)
    for n in d["names"]:
        cells = [" "] * CELLS
        for i, ch in enumerate(n["kr"]):
            cells[i] = ch
        out.append(cells)
    if len(out) != COUNT:
        raise SystemExit(f"전투 UI 줄이 {len(out)} — {COUNT} 이어야 한다")
    return out


def encode_rows(rep_index: dict[str, int]) -> list[bytes]:
    out = []
    for cells in rows():
        b = bytearray()
        for ch in cells:
            if encode.is_glyph(ch):
                b += encode.glyph_code(rep_index[ch])
            elif ch in encode.KR_TABLE:
                b.append(encode.KR_TABLE[ch])
            else:
                raise SystemExit(f"전투 UI 에 못 넣는 글자: {ch!r}")
        if dicts.TERM in b:
            raise SystemExit("전투 UI 문자열 안에 $FF")
        out.append(bytes(b))
    return out


def bake(out: bytearray, rom: bytes, rep_index: dict[str, int], org: int) -> dict:
    """[포인터 표][문자열] 을 사전 뒤에 이어 놓고 `$02:A2C8`·`$02:A2CF` 의 피연산자를 바꾼다."""
    for addr in SETUP:
        o = common.snes2off(addr)
        if rom[o] != 0xBF:
            raise SystemExit(f"전투 UI 표 참조가 예상과 다르다 {common.fmt(addr)}")
    strs = encode_rows(rep_index)
    table = org
    cur = org + 2 * COUNT
    ptr = []
    for b in strs:
        ptr.append(cur)
        blob = b + bytes([dicts.TERM])
        so = common.snes2off((dicts.BANK << 16) | cur)
        out[so : so + len(blob)] = blob
        cur += len(blob)
    if cur > 0x10000:
        raise SystemExit(f"사전 뱅크가 넘친다: {cur:#x}")
    t = common.snes2off((dicts.BANK << 16) | table)
    for i, p in enumerate(ptr):
        out[t + 2 * i : t + 2 * i + 2] = p.to_bytes(2, "little")
    for k, addr in enumerate(SETUP):  # 두 참조는 표의 lo·hi 를 각각 집는다
        o = common.snes2off(addr)
        out[o + 1] = (table + k) & 0xFF
        out[o + 2] = (table + k) >> 8
        out[o + 3] = dicts.BANK
    return {
        "표": common.fmt((dicts.BANK << 16) | table),
        "줄": COUNT,
        "끝": common.fmt((dicts.BANK << 16) | cur),
    }


def patch_ranges() -> list[tuple[int, int]]:
    return [(common.snes2off(a), common.snes2off(a) + 4) for a in SETUP]


def verify(out: bytes, slots: list) -> dict:
    """🔑 **체인이 다 끝난 롬**에서 게임이 하는 그대로 되읽는다 — `$02:A2C8` 의 피연산자 → 표 → 문자열.
    ⚠ 우리가 적어 둔 주소가 아니라 **롬에 박힌 값**을 따라간다(뒤 단계가 덮었으면 여기서 걸린다)."""
    o = common.snes2off(SETUP[0])
    table = (out[o + 3] << 16) | (out[o + 2] << 8) | out[o + 1]
    want = ["".join(c) for c in rows()]
    bad = []
    for i in range(COUNT):
        t = common.snes2off(table) + 2 * i
        p = out[t] | (out[t + 1] << 8)
        so = common.snes2off((table & 0xFF0000) | p)
        end = out.find(bytes([dicts.TERM]), so)
        got = encode.decode_kr(out[so:end], slots)
        if got != want[i]:
            bad.append(f"[{i}] {got!r} ≠ {want[i]!r}")
    if bad:
        raise SystemExit("전투 UI 되읽기 실패:\n  " + "\n  ".join(bad))
    return {"읽은 줄": COUNT, "표": common.fmt(table)}
