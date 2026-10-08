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
import asm65816
import common
import dicts
import encode
import namesrc

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
    # 🔵 2026-10-08 — 자동 전투 중 취소 키 창(`$0F4F=$10`, 핸들러 `$02:A430`). 「にげる／せってい」 4칸 둘 — 속도 창과 같은 꼴(포인터 표 + `LDA #$0003` + MVN).
    #    정본 `逃げる@전투설정`(도망친다)·`戦闘設定` 이 네 칸을 꽉 쓴다.
    {"key": "flee", "table": 0x02A47C, "count": 2, "cells": 4, "setup": (0x02A43D, 0x02A444)},
    # 🔵 2026-09-15 — A4 전투 설정 창의 **라벨 자체**. 창 표(menus.py LAYOUT_TABLES)가 굽는
    #    $03:CC1B 는 아무도 안 읽는 사본이고, 실제 드로어는 이 포인터 표를 통해 $0305 로
    #    MVN 한다(라이브 BP 로 확인 — $02:ADFA, X=포인터, count=10). 10바이트 고정칸.
    {"key": "a4_labels", "table": 0x02AE59, "count": 6, "cells": 10, "setup": (0x02ADE1, 0x02ADE8)},
]


def rows(key: str) -> list[list[str]]:
    """한 무리를 **칸 단위 글자 목록**으로. `battle` = 격자 셋(칸 시작 0·5·10) + 이름 다섯,
    `title` = 타이틀 메뉴 세 줄."""
    d = namesrc.battle_ui()
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


# ── A3 시스템 설정 창 값 — **포인터 표가 아니라 즉치 4갈래** ─────────────────────────────
# 라이브 BP 로 확정(2026-09-15). `$1239` 의 비트를 마스킹해 옵션 번호(Y)를 얻고
# `베이스 + Y×스트라이드` 로 문자열을 찾는다. 베이스 셋(레벨업·EP표시·이동/메시지-공유)을
# **각 분기가 16비트 상수로 직접** 갖고 있어(`lda #$xx` 두 번) `GROUPS`/`bake()` 의 포인터
# 표 전제와 안 맞는다 — 그래서 별도 함수다.
#
# 🔴 원본 스트라이드는 ×3(바이트) 인데 한글 2음절(4바이트)이 그 안에 안 들어간다 — 그래서
# **원본 게임 코드**(`$02:AF10~AF31`, 스트라이드 계산)를 ×5 로 넓힌다. 우리 훅 코드가 아니라
# 원본을 고치는 것이라 루트 CLAUDE.md 「손인코딩 기계어는 디스어셈블로 검산한다」가 걸린다 —
# 아래 `_a3_stride_patch()` 가 어셈블러로 짓고, `test_hook.py` 류의 재디코드는 없지만 빌드
# 게이트(`--project`)의 무변경 구간·되읽기가 매 회차 재확인한다.
# 🔴 **처음엔 ×4 + 「name13 칸수를 2로 줄인다」로 갔다가 실기에서 깨졌다**(자기 정정) — 「수동」
# 뒤에 다음 옵션 「자동」의 「자」가 붙어 「수동자」로 보였다. 칸수(`LDA #$0002`)를 줄이면
# name13 이 **덜 읽고 멈추긴 하지만**, 그 뒤에 오는 **다른(미확인) 다운스트림 경로가 여전히
# 고정 3칸을 화면에 낸다** — 우리 루프가 안 쓴 세 번째 칸이 **이전 프레임의 잔재**를 그대로
# 내보인 것으로 보인다. ⇒ **원본 칸수(3)는 그대로 두고**, 다른 그룹(speed·yesno·a4_labels)과
# 똑같이 **`$FF` 종료 + `name13` 자체 패딩**으로 세 번째 칸을 **명시적으로 공백 처리**한다.
# 그러려면 스트라이드가 「내용(4B) + 종결자(1B)」= **5바이트**여야 다음 옵션과 안 겹친다.
A3_STRIDE_ORG = 0x02AF10
A3_STRIDE_LEN = 0x02AF31 - 0x02AF10  # 33바이트, 원본과 정확히 같은 길이 — 뒤 코드가 안 밀린다
A3_MVN = 0x02AF3C
A3_MVN_LDY = 0x02AF36  # `LDY #$0305` — hook.MVN_SITES 가 이 자리로 앞 3바이트를 확인한다
A3_SCRATCH = 0x000009  # ×5 계산용 임시 — $0006~$0008 바로 뒤, 이 루틴 안에서만 쓰고 버린다

# (행 이름, [분기의 즉치 lo 주소, 즉치 hi 주소] 목록, 옵션 jp 목록)
A3_ROWS = [
    ("레벨업", [(0x02AECD, 0x02AED2)], ["セット", "オート"]),
    ("EP표시", [(0x02AEDC, 0x02AEE1)], ["EP", "あと"]),
    (
        "이동·메시지",
        [(0x02AEEB, 0x02AEF0), (0x02AEFA, 0x02AEFF)],
        ["おそい", "ふつう", "はやい", "とまる"],
    ),
]
A3_STRIDE = 5  # 패치 후 스트라이드(바이트) — 한글 2음절(4B) + `$FF` 종결자(1B)


# 🔴 A4(전투 설정) 값 — `$02:AD42` 행 분기가 `$06` 에 원본 5칸 문자열(`$02:AE3B`·`AE45`·`AE4F`, 옵션 둘씩)을
# 넣고, 켜짐이면 `+5`(`$02:ADBC LDA #$05`) 한 뒤 `MVN` 으로 5바이트를 칸 `$030F` 에 옮긴다. 한글 2바이트 + `$FF`
# 가 5를 넘으므로 **짝마다 우리 뱅크에 A4_STRIDE 간격으로** 굽고, 즉치 lo/hi 여섯 쌍과 보폭 즉치를 바꾼다.
# `MVN` 은 `hook.A4V_MVN` 이 목적지 `$030F` 판 `name13_v` 로 바꾼다(2026-09-26, 라운드⑤).
A4_ROWS = [  # (행, 즉치 lo(`LDA #`) 주소, 즉치 hi 주소, 옵션 짝 jp)
    (0, 0x02AD64, 0x02AD69, ("しない", "する")),
    (1, 0x02AD72, 0x02AD77, ("しない", "する")),
    (2, 0x02AD80, 0x02AD85, ("つかわない", "つかう")),
    (3, 0x02AD8E, 0x02AD93, ("つかわない", "つかう")),
    (4, 0x02AD9C, 0x02ADA1, ("つかわない", "つかう")),
    (5, 0x02ADAA, 0x02ADAF, ("こべつに", "おなじに")),
]
A4_STEP_SITE = 0x02ADBC  # LDA #$05 — 켜짐 옵션까지의 보폭
A4_STRIDE = 8  # 한글 3음절(6B) + `$FF` 를 담는 보폭


def bake_a4_values(out: bytearray, rom: bytes, rep_index: dict[str, int], org: int) -> dict:
    d = namesrc.battle_ui()
    by_jp = {x["jp"]: x["kr"] for x in d["a4_values"]}
    if bytes(rom[common.snes2off(A4_STEP_SITE) : common.snes2off(A4_STEP_SITE) + 2]) != bytes(
        [0xA9, 0x05]
    ):
        raise SystemExit("A4 값 보폭 자리가 예상과 다르다")
    cur = org
    pairs: dict[tuple[str, str], int] = {}
    for _row, lo, hi, pair in A4_ROWS:
        for a in (lo, hi):
            if rom[common.snes2off(a)] != 0xA9:
                raise SystemExit(f"A4 값 즉치 자리가 예상과 다르다 {common.fmt(a)}")
        if pair not in pairs:
            pairs[pair] = cur
            for jp in pair:
                kr = by_jp[jp]
                b = bytearray()
                for ch in kr:
                    if encode.is_glyph(ch):
                        b += encode.glyph_code(rep_index[ch])
                    elif ch in encode.KR_TABLE:
                        b.append(encode.KR_TABLE[ch])
                    else:
                        raise SystemExit(f"A4 값에 못 넣는 글자: {ch!r}")
                b.append(dicts.TERM)
                if len(b) > A4_STRIDE:
                    raise SystemExit(f"A4 값 {kr!r} 이 {A4_STRIDE}바이트를 넘는다")
                b += bytes([dicts.TERM]) * (A4_STRIDE - len(b))
                so = common.snes2off((dicts.BANK << 16) | cur)
                out[so : so + A4_STRIDE] = bytes(b)
                cur += A4_STRIDE
        base = pairs[pair]
        out[common.snes2off(lo) + 1] = base & 0xFF
        out[common.snes2off(hi) + 1] = base >> 8
    out[common.snes2off(A4_STEP_SITE) + 1] = A4_STRIDE
    if cur > 0x10000:
        raise SystemExit(f"사전 뱅크가 넘친다: A4 값 {cur:#x}")
    return {"짝": len(pairs), "next": cur}


def patch_ranges_a4() -> list[tuple[int, int]]:
    r = [(common.snes2off(A4_STEP_SITE) + 1, common.snes2off(A4_STEP_SITE) + 2)]
    for _row, lo, hi, _p in A4_ROWS:
        r.append((common.snes2off(lo) + 1, common.snes2off(lo) + 2))
        r.append((common.snes2off(hi) + 1, common.snes2off(hi) + 2))
    return r


def _a3_stride_patch() -> bytes:
    """`베이스 + Y×5` — 원본의 ×3(TAY→ASL→ADC→TYA→ADC, 인터리브)과 달리 **Y×4 를 스크래치에
    모아 뒀다가 Y 를 한 번 더 더해** 캐리 전파를 한 번만 한다(안 그러면 33B 를 넘긴다)."""
    a = asm65816.Asm(org=A3_STRIDE_ORG, bank=0x02)
    a.tay()
    a.asl()
    a.asl()  # A = Y×4
    a.op("sta", addr=A3_SCRATCH, mode="abs")
    a.tya()  # A = Y (레지스터끼리 더하는 명령이 없어 스크래치를 거친다)
    a.clc()
    a.op("adc", addr=A3_SCRATCH, mode="abs")  # A = Y×4 + Y = Y×5
    a.clc()
    a.op("adc", addr=0x0006, mode="abs")
    a.op("sta", addr=0x0006, mode="abs")
    a.lda(imm=0x00)
    a.op("adc", addr=0x0007, mode="abs")
    a.op("sta", addr=0x0007, mode="abs")
    code = a.assemble()
    pad = A3_STRIDE_LEN - len(code)
    if pad < 0:
        raise SystemExit(f"A3 스트라이드 패치가 원본 자리({A3_STRIDE_LEN}B)보다 크다: {len(code)}B")
    return code + bytes([0xEA]) * pad  # 나머지는 NOP — 뒤 코드(REP#$30~)는 그대로 둔다


def bake_a3_values(out: bytearray, rom: bytes, rep_index: dict[str, int], org: int) -> dict:
    """A3 값 8종을 **5바이트 고정 스트라이드**(한글 4B + `$FF` 1B)로 사전 뱅크에 굽고,
    즉치 4갈래 + 스트라이드 ASM 을 함께 패치한다. `org` 이어 쓴다(battle_ui.bake() 뒤)."""
    d = namesrc.battle_ui()
    by_jp = {x["jp"]: x["kr"] for x in d["a3_values"]}
    for _row, addrs, _opts in A3_ROWS:
        for lo, hi in addrs:  # lo·hi 는 $A9(LDA #imm) **오피코드** 주소 — +1 이 피연산자다
            if rom[common.snes2off(lo)] != 0xA9 or rom[common.snes2off(hi)] != 0xA9:
                raise SystemExit(
                    f"A3 값 즉치 자리가 예상과 다르다 {common.fmt(lo)}/{common.fmt(hi)}"
                )
    if rom[common.snes2off(A3_MVN)] != 0x54:
        raise SystemExit(f"A3 값 MVN 자리가 예상과 다르다 {common.fmt(A3_MVN)}")

    cur = org
    info = {}
    for row, addrs, opts in A3_ROWS:
        base = cur
        for jp in opts:
            kr = by_jp.get(jp)
            if not kr:
                raise SystemExit(f"A3 값 원문 {jp!r} 이 battle_ui.json 의 a3_values 에 없다")
            b = bytearray()
            for ch in kr:
                if encode.is_glyph(ch):
                    b += encode.glyph_code(rep_index[ch])
                elif ch in encode.KR_TABLE:
                    b.append(encode.KR_TABLE[ch])
                else:
                    raise SystemExit(f"A3 값에 못 넣는 글자: {ch!r}")
            b.append(dicts.TERM)  # $FF — name13 이 여기서 멈추고 남은 칸을 공백으로 채운다
            if len(b) > A3_STRIDE:
                raise SystemExit(f"A3 값 {kr!r}(+종결자) 이 {A3_STRIDE}바이트를 넘는다({len(b)}B)")
            b += bytes([0xFF]) * (A3_STRIDE - len(b))  # 안 읽히는 자리 — 값은 안 중요하다
            so = common.snes2off((dicts.BANK << 16) | cur)
            out[so : so + A3_STRIDE] = bytes(b)
            cur += A3_STRIDE
        for lo, hi in addrs:  # 이 행의 모든 분기가 같은 base 를 가리킨다(이동·메시지는 공유)
            ol, oh = common.snes2off(lo), common.snes2off(hi)
            out[ol + 1] = base & 0xFF
            out[oh + 1] = base >> 8
        info[row] = {"표": common.fmt((dicts.BANK << 16) | base), "옵션": len(opts)}
        if cur > 0x10000:
            raise SystemExit(f"사전 뱅크가 넘친다: {cur:#x}")

    patch = _a3_stride_patch()
    po = common.snes2off(A3_STRIDE_ORG)
    out[po : po + A3_STRIDE_LEN] = patch
    info["끝"] = common.fmt((dicts.BANK << 16) | cur)
    info["next"] = cur
    return info


def verify_a3_values(out: bytes, slots: list) -> dict:
    """되읽기 — 즉치 4곳이 가리키는 자리를 그대로 따라가 디코드한다."""
    n_ok = 0
    bad = []
    d = namesrc.battle_ui()
    by_jp = {x["jp"]: x["kr"] for x in d["a3_values"]}
    for _row, addrs, opts in A3_ROWS:
        lo, hi = addrs[0]
        ol, oh = common.snes2off(lo), common.snes2off(hi)
        base = out[ol + 1] | (out[oh + 1] << 8)
        for i, jp in enumerate(opts):
            so = common.snes2off((dicts.BANK << 16) | (base + i * A3_STRIDE))
            end = out.find(bytes([dicts.TERM]), so, so + A3_STRIDE)
            got = encode.decode_kr(out[so:end], slots).rstrip()
            want = by_jp[jp]
            if got != want:
                bad.append(f"{jp} → {got!r} ≠ {want!r}")
            else:
                n_ok += 1
        for lo2, hi2 in addrs[1:]:  # 공유 분기도 같은 base 를 가리키는지
            ol2, oh2 = common.snes2off(lo2), common.snes2off(hi2)
            base2 = out[ol2 + 1] | (out[oh2 + 1] << 8)
            if base2 != base:
                bad.append(
                    f"공유 분기 base 불일치: {common.fmt(lo)}={base:#x} ≠ {common.fmt(lo2)}={base2:#x}"
                )
    if bad:
        raise SystemExit("A3 값 되읽기 실패:\n  " + "\n  ".join(bad))
    return {"읽은 옵션": n_ok}


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
    info["next"] = cur
    return info


def patch_ranges() -> list[tuple[int, int]]:
    return [(common.snes2off(a), common.snes2off(a) + 4) for g in GROUPS for a in g["setup"]]


def patch_ranges_a3() -> list[tuple[int, int]]:
    r = [(common.snes2off(A3_STRIDE_ORG), common.snes2off(A3_STRIDE_ORG) + A3_STRIDE_LEN)]
    for _row, addrs, _opts in A3_ROWS:
        for lo, hi in addrs:
            r.append((common.snes2off(lo) + 1, common.snes2off(lo) + 2))
            r.append((common.snes2off(hi) + 1, common.snes2off(hi) + 2))
    return r


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
