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

# 고정 칸 문자열 표 **둘** — 둘 다 `MVN` 으로 칸 배열에 통째로 옮긴다(`hook.MVN_SITES`).
GROUPS = [
    {"key": "battle", "table": 0x02A30A, "count": 8, "cells": 13, "setup": (0x02A2C8, 0x02A2CF)},
    {"key": "title", "table": 0x02A646, "count": 3, "cells": 12, "setup": (0x02A607, 0x02A60E)},
    # 🔵 2026-09-08 — **타이틀 흐름에서 한 칸 들어간 자리 둘.** 유저가 「여기까지 한글 되어야
    #    타이틀 닫았다」며 짚은 화면이 이 둘이다(`docs/status.md` E2).
    #    ⚠ 앞 둘과 달리 **표가 고정 폭이 아니라 포인터 표**다 — 그래서 문자열 길이가 자유롭고
    #    `cells` 는 **화면 칸 수**일 뿐이다(`name13` 이 모자란 칸을 공백으로 채운다).
    {"key": "speed", "table": 0x02A3CE, "count": 2, "cells": 4, "setup": (0x02A38F, 0x02A396)},
    {"key": "yesno", "table": 0x02A426, "count": 2, "cells": 3, "setup": (0x02A3E7, 0x02A3EE)},
]


def rows(key: str) -> list[list[str]]:
    """한 무리를 **칸 단위 글자 목록**으로. `battle` = 격자 셋(칸 시작 0·5·10) + 이름 다섯,
    `title` = 타이틀 메뉴 세 줄."""
    d = json.loads((common.GAME_DIR / "textmap" / "battle_ui.json").read_text(encoding="utf-8"))
    g = next(x for x in GROUPS if x["key"] == key)
    n = g["cells"]
    out = []
    if key == "battle":
        for grid in d["grid"]:
            cells = [" "] * n
            for col in grid["cols"]:
                for i, ch in enumerate(col["kr"]):
                    cells[col["at"] + i] = ch
            out.append(cells)
        for name in d["names"]:
            cells = [" "] * n
            for i, ch in enumerate(name["kr"]):
                cells[i] = ch
            out.append(cells)
    else:
        # `title`·`speed`·`yesno` — {jp, kr} 목록을 칸 수에 맞춰 오른쪽을 공백으로 채운다
        for t in d[key]:
            if len(t["kr"]) > n:
                raise SystemExit(f"{key} 줄 {t['kr']!r} 이 {n}칸을 넘는다")
            out.append(list(t["kr"]) + [" "] * (n - len(t["kr"])))
    if len(out) != g["count"]:
        raise SystemExit(f"{key} 줄이 {len(out)} — {g['count']} 이어야 한다")
    return out


def encode_rows(key: str, rep_index: dict[str, int]) -> list[bytes]:
    out = []
    for cells in rows(key):
        b = bytearray()
        for ch in cells:
            if encode.is_glyph(ch):
                b += encode.glyph_code(rep_index[ch])
            elif ch in encode.KR_TABLE:
                b.append(encode.KR_TABLE[ch])
            else:
                raise SystemExit(f"고정 칸 문자열에 못 넣는 글자: {ch!r}")
        if dicts.TERM in b:
            raise SystemExit("고정 칸 문자열 안에 $FF")
        out.append(bytes(b))
    return out


def bake(out: bytearray, rom: bytes, rep_index: dict[str, int], org: int) -> dict:
    """무리마다 [포인터 표][문자열] 을 사전 뒤에 이어 놓고 그 무리의 표 참조를 우리 것으로."""
    info = {}
    cur = org
    for g in GROUPS:
        for addr in g["setup"]:
            if rom[common.snes2off(addr)] != 0xBF:
                raise SystemExit(f"표 참조가 예상과 다르다 {common.fmt(addr)}")
        strs = encode_rows(g["key"], rep_index)
        table = cur
        cur += 2 * g["count"]
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
        for k, addr in enumerate(g["setup"]):  # 두 참조가 표의 lo·hi 를 각각 집는다
            o = common.snes2off(addr)
            out[o + 1] = (table + k) & 0xFF
            out[o + 2] = (table + k) >> 8
            out[o + 3] = dicts.BANK
        info[g["key"]] = {"표": common.fmt((dicts.BANK << 16) | table), "줄": g["count"]}
    info["끝"] = common.fmt((dicts.BANK << 16) | cur)
    return info


def patch_ranges() -> list[tuple[int, int]]:
    return [(common.snes2off(a), common.snes2off(a) + 4) for g in GROUPS for a in g["setup"]]


def verify(out: bytes, slots: list) -> dict:
    """🔑 **체인이 다 끝난 롬**에서 게임이 하는 그대로 되읽는다 — 표 참조의 피연산자 → 표 → 문자열."""
    n_ok = 0
    bad = []
    for g in GROUPS:
        o = common.snes2off(g["setup"][0])
        table = (out[o + 3] << 16) | (out[o + 2] << 8) | out[o + 1]
        want = ["".join(c).rstrip() for c in rows(g["key"])]
        for i in range(g["count"]):
            t = common.snes2off(table) + 2 * i
            p = out[t] | (out[t + 1] << 8)
            so = common.snes2off((table & 0xFF0000) | p)
            end = out.find(bytes([dicts.TERM]), so)
            got = encode.decode_kr(out[so:end], slots).rstrip()
            if got != want[i]:
                bad.append(f"{g['key']}[{i}] {got!r} ≠ {want[i]!r}")
            else:
                n_ok += 1
    if bad:
        raise SystemExit("고정 칸 문자열 되읽기 실패:\n  " + "\n  ".join(bad))
    return {"읽은 줄": n_ok}
