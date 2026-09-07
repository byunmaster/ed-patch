#!/usr/bin/env python3
"""시나리오 문안 재삽입 — 정본의 한글을 **원래 자리에** 넣는다.

`units.py` 가 잰 것을 실제로 쓴다. 전략은 넷이고 **길이에 따라 자동으로 갈린다**:

    틈 0        그대로 쓴다
    틈 3 이상   문안 + `0F <런이 끝나던 주소>` — 남는 자리는 건너뛴다
    틈 1~2      반각 공백으로 메운다 (`0F` 를 심을 3바이트가 없다)
    넘친다      런 머리에 `0F <꼬리 빈자리>` 를 심고 그리로 문안을 뺀다

🔴 **루틴 길이가 안 변한다.** 그래서 시나리오 안의 절대주소를 **하나도 다시 계산하지
   않는다** — 전체 재구성(선행 영문 패치의 `Block`/`Link`/`BlockPool`)이 필요 없다.

⚠ **넣지 않는 자리** — 조건이 안 서면 조용히 건너뛰고 **왜 건너뛰었는지 센다**:

  · 런 안으로 점프가 들어온다 → 우리 코드 한복판에 떨어진다(`units.py` 조건 ②)
  · 3바이트 미만이라 점프를 못 심는다
  · 꼬리 빈자리가 모자란다

## 좌표

블록의 `o` 는 **시나리오 데이터 안의 오프셋**이고, 주소는 `0xe000 + o`, 평면 오프셋은
`index * 1024 + o` 다. 셋을 섞으면 조용히 엉뚱한 자리를 고친다(게임 CLAUDE.md 「좌표 규약」).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
import dump_scn
import font
import patch_font_hook as H
import reuse
import scn
import units
import walk_scn as W
from text import sjis
from text.line_key import key as line_key

SCRIPT = common.ROOT / "games" / "pc98-ed1" / "script" / "scn.json"
PIERCE_CACHE = common.OUT_DIR / "pierce2.json"  # v2 = 전투 영역 포함
JUMP = 0x0F
# 🔴 **주소를 인자로 갖는 옵코드 전부**(길이 3). 분기(`0F`~`14`)에 `0C`·`15`(ASM 호출)까지.
#    런 머리에 이 주소가 딸려 들어오면 덮어쓰면 안 된다 — 아래 두 자리에서 쓴다.
ADDR_OPS = frozenset(c for c, n in W.CODE_LEN.items() if n == 3)
KU0 = H.KU_LO - 0x20  # ah 바이트에서 구 번호로 (JIS 고위 = 0x20 + 구)

# 🔴 **칸 표** — 한 청크 안에 「이름 14B + 종결자 07」이 줄줄이 이어지는 자리가 있다
#    (장소 선택 목록 46칸, 2026-09-06 실측). 일반 런처럼 다루면 **정렬이 깨진다** —
#    밖으로 빼면 칸이 비고, 틈을 쓰면 이름이 왼쪽에 붙는다. 원본은 **가운데 정렬**이다.
#    ⇒ 여기만 **제자리에 가운데 정렬**로 넣는다(점프를 안 쓴다).
#    ⚠ 구조를 사전조건으로 검사한다 — 칸마다 종결자가 그 자리에 없으면 우리가 표를
#      잘못 읽은 것이므로 죽는다(patcher-checklist 2).
CELL_TABLES = [
    {
        "chunk": "10.00.20",
        "off": 0x14DA,
        "stride": 15,
        "width": 14,
        "cells": 46,
        "end": 0x07,
        # ⚠ 덤퍼가 못 보는 칸은 여기서 직접 채운다. 둘뿐이고 이유가 서로 다르다 —
        #   0번은 런이 칸보다 앞에서 시작하고, 34번(`竜の卵`)은 **순수 한자라 가나 필터가
        #   버린다**(`dump_scn` 머리말의 그 구멍이다). 문안은 우리 것이라 여기 둬도 된다.
        "kr": {0: "엘아스타마을", 34: "용의알"},  # ⚠ 표 층이라 접미를 붙인다
    },
]

_SYL = None


def syllables() -> dict:
    """한글 음절 → 표에서의 차례(0..2349). `font.build()` 가 정본이다."""
    global _SYL
    if _SYL is None:
        syl, _ = font.build()
        _SYL = {c: i for i, c in enumerate(syl)}
    return _SYL


def slot_of(i: int) -> int:
    """표 차례 → JIS 글리프 색인. 표는 **구마다 94자**로 깔린다(`ku128_table` 과 같은 셈)."""
    return (KU0 - 1 + i // 94) * 94 + (i % 94)


def encode(text: str) -> bytes:
    """정본 문안 → 스크립트 바이트. 마커는 원래 1바이트 코드로 되돌린다."""
    out = bytearray()
    i = 0
    syl = syllables()
    while i < len(text):
        # ⚠ 개행이 **두 꼴**로 온다 — 우리 덤퍼는 `\\n`(두 글자), PS1 사전은 **진짜 개행**이다.
        #   한 꼴만 받으면 사전에서 온 줄이 통째로 제어 바이트 검사에 걸린다(실측 2026-08-31).
        for tag, code in (("\\n", 0x01), ("\n", 0x01), ("<PAGE>", 0x05), ("<WAIT>", 0x03)):
            if text.startswith(tag, i):
                out.append(code)
                i += len(tag)
                break
        else:
            c = text[i]
            if c in syl:
                out += sjis.sjis_of_index(slot_of(syl[c]))
            else:
                try:
                    out += c.encode("shift_jis")
                except UnicodeEncodeError as e:
                    raise SystemExit(f"🔴 SJIS 로 못 적는 글자 {c!r} — 문안을 고친다") from e
            i += 1
    # 🔴 제어 대역이 섞이면 **화면이 아니라 흐름이 깨진다.** 마커 말고는 0x20 아래가 없어야 한다.
    bad = [n for n, b in enumerate(out) if b < 0x20 and b not in (0x01, 0x03, 0x05)]
    if bad:
        raise SystemExit(f"🔴 제어 바이트가 섞였다 {bad[:4]} — {text[:30]!r}")
    return bytes(out)


ONLY = None  # None | "scenario" | "combat" — `build.py --only` 이 세운다

# 🔴 **전투 청크에서 「밖으로」를 금지한다**(`build.py --no-pool-combat`).
#    「밖으로」는 청크 **꼬리 빈자리**에 문안을 두고 런 머리에서 `0F` 로 뛴다. 로더가 청크를
#    통째로 안 올리고 **본문 길이만** 올리면 그 점프는 **안 올라온 자리**로 뛴다.
#    전투 프리즈의 용의자라 개입 하나로 가르려고 둔 문이다. 넘치는 블록은 **안 넣는다.**
NO_POOL_COMBAT = False

# 전투 청크에서 **길이가 딱 맞는 제자리 교체만** 한다(틈 건너뜀·공백 메움도 끈다).
STRICT_INPLACE_COMBAT = False

# 전투 청크를 **원문 그대로 두고 한 글자만** 우리 한글 코드로 바꾼다.
#    ⇒ 뻗으면 전투 렌더러가 우리 코드 대역(JIS ku 0x40~0x58)을 다른 뜻으로 읽는 것이다.
ONE_GLYPH_COMBAT = False
ONE_GLYPH_AT = ("38.00.20", 0x0030, 8, "가")  # 청크 · 런 오프셋 · 런 안 바이트 · 넣을 글자

# 전투 청크를 **절반씩** 넣는다 — 「어느 청크가 범인인가」로 좁힐 때(이분 탐색).
COMBAT_HALF = None  # None | "a"(앞 절반) | "b"(뒤 절반)

# 전투 청크에서 「틈 건너뜀」/「공백 메움」을 각각 끈다 — 둘 중 누가 범인인가.
NO_GAP_COMBAT = False  # 틈 건너뜀(`0F` 로 런 끝으로) 금지
NO_FILL_COMBAT = False  # 공백 메움(꼬리에 반각 공백) 금지


def areas() -> dict:
    """시나리오 + **전투** 청크를 한 자로 본다.

    🔴 전투 영역(`scn.COMBAT_RANGE`)도 **같은 이벤트 스크립트 문법**이다(2026-09-06 실측:
       청크 110 · 텍스트 런 3,474 · 안으로 점프가 오는 것 46 · 꼬리 빈자리 48,068B).
       몬스터 이름과 전투 대사가 거기 살아서, 여길 안 열면 **정본 86종이 화면에 못 간다.**
    """
    scenario, combat = scn.load()
    # ⚠ **원인을 가르는 빌드**를 위한 문(`build.py --only`). 평소엔 None 이라 둘 다 나간다.
    #    프리즈처럼 「어느 개입이 범인인가」를 물어야 할 때 개입 그룹을 하나씩 뺀다.
    if ONLY == "scenario":
        return dict(scenario)
    if ONLY == "combat":
        return dict(combat)
    return {**scenario, **combat}


_COMBAT_KEYS = None


def _combat_keys() -> set:
    """전투 청크의 열쇠 집합 — `NO_POOL_COMBAT` 판정에만 쓴다."""
    global _COMBAT_KEYS
    if _COMBAT_KEYS is None:
        _COMBAT_KEYS = {scn.format_key(k) for k in scn.load()[1]}
    return _COMBAT_KEYS


def pierced_map(scenario: dict) -> dict:
    """{청크키: [들어오는 점프 목적지]} — 느려서 `work/derived/` 에 캐시한다."""
    if PIERCE_CACHE.exists():
        return json.loads(PIERCE_CACHE.read_text())
    out = {}
    for key, info in scenario.items():
        data = info["data"]
        body = len(data) - info["tail_free"]
        _seen, cands = W.walk_x86(data)
        entries = W.pointer_sweep(data, body, cands)
        out[scn.format_key(key)] = sorted(units.incoming_targets(data, body, entries))
    PIERCE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    PIERCE_CACHE.write_text(json.dumps(out))
    return out


def check_no_jump_clobber(marks: list[tuple[int, bytes, bytes]], chunks: dict[int, bytes]) -> None:
    """마크가 **앞선 `0F` 의 주소 2바이트**에 앉으면 죽는다.

    덤퍼는 `< 0x20` 을 건너뛰기만 하므로 `0F <addr16>` 의 주소가 `>= 0x20` 이면 그 두
    바이트가 **다음 런의 머리로 딸려 들어온다.** 거기에 쓰면 점프가 어긋나 흐름이 깨진다
    — 화면이 아니라 **진행**이 깨지는, 전투 프리즈와 같은 등급이다(2026-09-07).

    ⚠ 판별 축은 「`0F` 가 있나」가 아니라 **「그 주소가 창(`0xExxx`)인가」**다. 전투 청크의
      `0F` 는 점프가 아니라 데이터다(policy 「전투 청크에서는 `0F` 를 쓰지 않는다」).
    """
    for off, _old, _new in marks:
        for base, blob in chunks.items():
            if not base <= off < base + len(blob):
                continue
            r = off - base
            for q in (r - 1, r - 2):
                if (
                    q >= 0
                    and blob[q] in ADDR_OPS
                    and q + 3 > r
                    and (blob[q + 2] & 0xF0) == ((W.BASE >> 8) & 0xF0)
                ):
                    raise SystemExit(
                        f"🔴 `0F` 의 주소를 덮어쓴다 {off:#08x} — "
                        f"점프 {blob[q : q + 3].hex(' ')} 가 어긋난다"
                    )
            break


def plan() -> tuple[list[tuple[int, bytes, bytes]], dict]:
    """(평면 오프셋, 원본이어야 할 바이트, 새 바이트) 목록 + 통계."""
    script = json.loads(SCRIPT.read_text(encoding="utf-8")) if SCRIPT.exists() else {}
    scenario = areas()
    pierce = pierced_map(scenario)
    marks: list[tuple[int, bytes, bytes]] = []
    st = {
        "제자리": 0,
        "머리가 주소 인자라 건너뜀": 0,
        "머리를 앞으로 되넓힘": 0,
        "칸 표": 0,
        "건너뜀:칸 넘침": 0,
        "틈 건너뜀": 0,
        "공백 메움": 0,
        "밖으로": 0,
        "밖으로:점프가 온다": 0,
        "건너뜀:점프가 머리에": 0,
        "건너뜀:3B 미만": 0,
        "건너뜀:빈자리 부족": 0,
        "건너뜀:전투 밖으로 금지": 0,
        "건너뜀:전투 제자리만": 0,
        "건너뜀:전투 틈 금지": 0,
        "건너뜀:전투 공백 금지": 0,
        "건너뜀:전투 0F 금지": 0,
        "쓴 바이트": 0,
        "빈자리 쓴 바이트": 0,
    }

    for key, info in scenario.items():
        skey = scn.format_key(key)
        data = info["data"]
        base_off = info["index"] * common.SECTOR_SIZE
        targets = set(pierce.get(skey, ()))
        body = len(data) - info["tail_free"]
        pool = body  # 꼬리 빈자리의 다음 쓸 자리 (시나리오 데이터 안 오프셋)

        # ── 칸 표를 먼저 처리하고, 그 구간의 블록은 일반 경로에서 뺀다
        cells = {}
        for t in CELL_TABLES:
            if t["chunk"] != skey:
                continue
            for i in range(t["cells"]):
                c0 = t["off"] + i * t["stride"]
                if data[c0 + t["width"]] != t["end"]:
                    raise SystemExit(
                        f"🔴 {skey}: 칸 표가 어긋난다 — {c0 + t['width']:#06x} 가 종결자가 아니다"
                    )
                cells[c0] = t["width"]
        cells_all = dict(cells)  # 🔴 건너뛰기 판정은 **원래 칸 집합**으로 한다

        for t in CELL_TABLES:
            if t["chunk"] != skey:
                continue
            for i, txt in t.get("kr", {}).items():
                c0 = t["off"] + i * t["stride"]
                w = t["width"]
                cell = encode(txt)
                if len(cell) > w:
                    st["건너뜀:칸 넘침"] += 1
                    continue
                left = (w - len(cell)) // 2
                marks.append(
                    (
                        base_off + c0,
                        data[c0 : c0 + w],
                        b" " * left + cell + b" " * (w - len(cell) - left),
                    )
                )
                st["칸 표"] += 1
                st["쓴 바이트"] += w
                cells.pop(c0, None)  # 덤프 경로가 같은 칸을 또 쓰지 않게

        blocks = dump_scn.dump_area({key: info})[0]
        for b in blocks:
            c0 = next((c for c, w in cells.items() if c <= b["o"] < c + w), None)
            if c0 is None:
                continue
            k = line_key(reuse.normalise(b))
            if k not in script:
                continue
            w = cells[c0]
            cell = encode(script[k]["t"])
            if len(cell) > w:
                st["건너뜀:칸 넘침"] += 1
                continue
            left = (w - len(cell)) // 2
            blob = b" " * left + cell + b" " * (w - len(cell) - left)
            marks.append((base_off + c0, data[c0 : c0 + w], blob))
            st["칸 표"] += 1
            st["쓴 바이트"] += w

        # ── 원인 가르기: 전투 청크를 절반만 넣는다(이분 탐색).
        if COMBAT_HALF and skey in _combat_keys():
            ks = sorted(_combat_keys())
            half = ks[: len(ks) // 2] if COMBAT_HALF == "a" else ks[len(ks) // 2 :]
            if skey not in half:
                continue

        # ── 원인 가르기: 전투 청크를 **원문 그대로** 두고 **한 글자만** 우리 코드로.
        if ONE_GLYPH_COMBAT and skey in _combat_keys():
            ck, co, ci, ch = ONE_GLYPH_AT
            if skey == ck:
                cell = encode(ch)
                assert len(cell) == 2, ch
                marks.append((base_off + co + ci, data[co + ci : co + ci + 2], cell))
                st["쓴 바이트"] += 2
                print(f"  ⚠ 한 글자만: {skey} {co + ci:#06x} ← {ch!r}")
            continue

        for b in blocks:
            if any(c <= b["o"] < c + w for c, w in cells_all.items()):
                continue  # 🔴 칸 표는 위에서 처리했다 — 일반 경로가 덮으면 정렬이 깨진다
            k = line_key(reuse.normalise(b))
            if k not in script:
                continue
            o, n = b["o"], b["n"]

            # ── 🔴 런 머리가 **앞선 옵코드의 주소 인자 2바이트**일 수 있다 (2026-09-07).
            #    덤퍼는 `< 0x20` 을 제어코드로 **건너뛰기만** 하므로, 주소를 인자로 갖는
            #    옵코드(`ADDR_OPS` = 길이 3 — 분기 `0F`~`14` + `0C` + ASM 호출 `15`)의
            #    주소가 `>= 0x20` 이면 그 두 바이트가
            #    **다음 런의 머리로 딸려 들어온다.**
            #    거기에 우리 문안을 쓰면 **점프가 엉뚱한 데로 간다** — 화면이 아니라
            #    흐름이 깨지는, 2026-09-07 전투 프리즈와 **같은 등급**의 사고다.
            #    실측: `0F` 만 세도 시나리오 215 · 전투 35(정본 4) · 분기 전체 +164(정본 8)
            #          · `0C`·`15` 까지 +54(정본 0 — 아직 안 물렸을 뿐이다).
            #    ⚠ 판별은 「`0F` 가 있나」가 아니라 **「그 주소가 창(0xExxx)인가」**다 —
            #      전투 청크의 `0F` 는 점프가 아니라 데이터고(policy 「전투 청크 `0F`」),
            #      실제로 넷 중 전투 하나는 목적지가 `0x95C3` 라 여기 안 걸린다.
            #    이건 판단이 아니라 **원본에서 유도되는 구조**라 정본이 아니라 코드에 둔다.
            for _p in (o - 1, o - 2):
                if _p >= 0 and data[_p] in ADDR_OPS and _p + 3 > o:
                    if (data[_p + 2] & 0xF0) == (W.BASE >> 8) & 0xF0:
                        _skip = _p + 3 - o
                        o += _skip
                        n -= _skip
                        st["머리가 주소 인자라 건너뜀"] += 1
                    break

            # ── 반대 방향의 어긋남 — **런이 늦게 시작해 앞 글자를 흘린다** (2026-09-07).
            #    앞선 런이 한자 두 바이트를 물어 가면 뒤에 **홀로 남은 바이트**가 생기고,
            #    덤퍼는 그걸 못 읽어 다음 런을 **한 글자 뒤에서** 시작한다. 실측으로
            #    `わしは…` 가 `しは…` 로, `ああ、…` 가 `あ、…` 로 잘려 있었다.
            #    그 자리에 그냥 쓰면 화면에 **`わ` 하나가 우리 문안 앞에 남는다.**
            #    ⇒ 앞으로 **되넓힌다.** 흘린 글자도 우리가 이미 번역에 담고 있다.
            #    ⚠ 넓히면 안 되는 자리 셋 — 분기 주소(위) · 남의 블록이 덮는 자리 ·
            #      제어코드. 셋을 다 피할 때만 두 바이트씩 물린다.
            _covered = {
                (bb["o"], bb["o"] + bb["n"])
                for bb in blocks
                if line_key(reuse.normalise(bb)) in script and bb["o"] != b["o"]
            }
            #    ⚠ 정본이 `head` 를 적은 자리는 **손대지 않는다** — 사람이 이미 판정한
            #      머리라 되넓히면 그 사전조건이 깨진다.
            for _ in range(0 if "head" in script[k] else 4):
                if o < 2 or data[o - 3 : o - 2] and data[o - 3] in ADDR_OPS:
                    break
                if any(a <= o - 1 < e for a, e in _covered):
                    break
                try:
                    _c = data[o - 2 : o].decode("shift_jis")
                except UnicodeDecodeError:
                    break
                if len(_c) != 1 or not ("\u3040" <= _c <= "\u30ff" or "\u4e00" <= _c <= "\u9fff"):
                    break
                o -= 2
                n += 2
                st["머리를 앞으로 되넓힘"] += 1

            # ── 런 머리에 **코드가 잡음으로 붙은** 자리 (덤퍼 런 경계 문제, status `[P4]`).
            #    거기에 쓰면 8086 코드를 뭉갠다. 정본이 `head` 로 **그 바이트를 그대로 적어**
            #    두면 우리는 그만큼 건너뛰고 뒤부터 쓴다.
            #    🔴 사전조건 — 원본이 정본이 적은 것과 **바이트로 같아야** 한다. 다르면
            #       덤퍼나 원본이 바뀐 것이므로 그 자리에서 죽는다(patcher-checklist 2).
            head = bytes.fromhex(script[k].get("head", ""))
            if head:
                if data[o : o + len(head)] != head:
                    raise SystemExit(
                        f"🔴 {skey} {o:#06x}: 머리 잡음이 정본과 다르다\n"
                        f"  정본 {head.hex(' ')}\n  원본 {data[o : o + len(head)].hex(' ')}"
                    )
                o += len(head)
                n -= len(head)

            new = encode(script[k]["t"])

            # 🔴 **안으로 점프가 들어와도 대개 살릴 수 있다**(2026-09-06).
            #    「밖으로」는 런 **머리 3바이트**에만 `0F <빈자리>` 를 심고 나머지는 원본 그대로
            #    둔다. 그러니 들어오는 점프가 **오프셋 3 이상**에 떨어지면 그 점프는 여전히
            #    **원본 바이트**에 앉는다 — 지금(무패치)과 **똑같이** 동작한다. 잃는 게 없다.
            #    ⚠ 반대로 `d < 3` 이면 우리 점프 한복판에 떨어져 흐름이 깨진다 → 건너뛴다.
            #    ⚠ 그리고 이때는 **「틈」을 쓰면 안 된다** — 그건 런 몸통을 덮어써서
            #      들어오는 점프가 우리 문안 한복판에 앉는다. 반드시 밖으로 뺀다.
            #    실측: 건너뛰던 434 중 **404** 가 `d >= 3` 이었다.
            inside = [t - (W.BASE + o) for t in targets if W.BASE + o < t < W.BASE + o + n]
            forced_pool = False
            if inside:
                if min(inside) < 3:
                    st["건너뜀:점프가 머리에"] += 1
                    continue
                forced_pool = True

            slack = n - len(new)
            is_combat = skey in _combat_keys()

            # 🔴 **전투 청크에서는 `0F` 를 쓰지 않는다**(2026-09-07 확정, 유저 실측 + 원본 계측).
            #    시나리오 청크의 `0F` 는 653번이 **같은 청크 안**을 가리키고 목적지의
            #    상위 니블이 `0xE`(= `W.BASE`)인 것이 669다. **전투 청크는 0번이다** —
            #    188개 `0x0F` 바이트는 전부 데이터고, `0xExxx` 를 가리키는 건 5뿐이며
            #    그중 청크 안은 하나도 없다. ⇒ 전투 스크립트는 그 창에 안 올라오거나
            #    전투 해석기가 `0F` 를 점프로 안 읽는다. 우리가 심으면 **거기서 뻗는다.**
            #    ⇒ 전투는 **제자리 · 공백 메움**만. 「틈 건너뜀」도 「밖으로」도 금지다.
            #    (실측 갈림: `nogap` 정상 · `nofill` 뻗음 · `strict` 정상 · `1glyph` 정상)
            #    ⚠ 그리고 **틈이 3바이트 이상이면 아예 안 넣는다.** 공백으로 메우면 되겠거니
            #       했다가 화면이 통째로 깨졌다(2026-09-07 유저 실측 — 앞선 프리즈보다 나쁘다).
            #       원문보다 한참 짧은 문안 뒤에 공백을 수십 개 붙이면 전투 화면이
            #       그걸 그대로 그린다. **정상으로 확인된 것은 `nogap` 뿐이고, 그건
            #       3바이트 이상을 건너뛰었다.** 그 규칙을 그대로 기본값으로 둔다.
            #    🔴 **규칙을 정본으로 우회할 수 있었다**(2026-09-08 회귀). 문안 꼬리에 공백을
            #       손으로 달아 두면 `slack` 이 0이 되어 위 조건을 그냥 통과한다 — 바이트로는
            #       「공백 메움 slack≥3」과 **똑같은 것**인데 코드는 「제자리」로 본다.
            #       실측: 그렇게 들어간 전투 블록이 64(고유 51)였고, 공백을 떼면 실제 slack 이
            #       **49개가 4 이상**이었다. 유저 실측으로 전투가 다시 크래시했다.
            #       ⇒ 전투에서는 **문안 꼬리 공백을 세지 않는다.** 잰 다음 우리가 다시 붙인다.
            if is_combat:
                new = encode(script[k]["t"].rstrip(" "))
                slack = n - len(new)
                if forced_pool or slack < 0 or slack >= 3:
                    st["건너뜀:전투 0F 금지"] += 1
                    continue
                if slack > 0:
                    marks.append((base_off + o, data[o : o + n], new + b" " * slack))
                    st["공백 메움"] += 1
                    st["쓴 바이트"] += n
                    continue

            if STRICT_INPLACE_COMBAT and is_combat and slack != 0:
                st["건너뜀:전투 제자리만"] += 1
                continue
            if NO_POOL_COMBAT and is_combat and (forced_pool or slack < 0):
                st["건너뜀:전투 밖으로 금지"] += 1
                continue
            if forced_pool:
                blob = None  # 아래 「밖으로」로 간다
            elif slack == 0:
                blob = new
                st["제자리"] += 1
            elif slack >= 3:
                if NO_GAP_COMBAT and is_combat:
                    st["건너뜀:전투 틈 금지"] += 1
                    continue
                blob = new + bytes((JUMP, *(W.BASE + o + n).to_bytes(2, "little")))
                st["틈 건너뜀"] += 1
            elif slack > 0:
                if NO_FILL_COMBAT and is_combat:
                    st["건너뜀:전투 공백 금지"] += 1
                    continue
                blob = new + b" " * slack
                st["공백 메움"] += 1
            else:
                blob = None
            if blob is None:  # 밖으로 — 넘치거나, 안으로 점프가 들어오거나
                if n < 3:
                    st["건너뜀:3B 미만"] += 1
                    continue
                need = len(new) + 3
                if pool + need > len(data):
                    st["건너뜀:빈자리 부족"] += 1
                    continue
                out_blob = new + bytes((JUMP, *(W.BASE + o + n).to_bytes(2, "little")))
                if data[pool : pool + need] != b"\x00" * need:
                    raise SystemExit(f"🔴 {skey} 꼬리 빈자리가 안 비었다 {pool:#06x}")
                marks.append((base_off + pool, data[pool : pool + need], out_blob))
                blob = bytes((JUMP, *(W.BASE + pool).to_bytes(2, "little")))
                st["빈자리 쓴 바이트"] += need
                pool += need
                st["밖으로:점프가 온다" if forced_pool else "밖으로"] += 1
            marks.append((base_off + o, data[o : o + len(blob)], blob))
            st["쓴 바이트"] += len(blob)
    # 🔴 **전투 청크에 `0F` 를 심지 않았나** — 규칙을 코드가 아니라 **결과로** 못 박는다.
    #    (2026-09-07 프리즈의 원인. 규칙만 두면 다음 사람이 조건 하나를 더하다 되살린다.)
    _combat_span = [
        (v["index"] * common.SECTOR_SIZE, v["index"] * common.SECTOR_SIZE + len(v["data"]))
        for v in scn.load()[1].values()
    ]
    for off, _e, new_b in marks:
        if 0x0F in new_b and any(a <= off < b for a, b in _combat_span):
            raise SystemExit(
                f"🔴 전투 청크에 `0F` 를 심었다 {off:#08x} — 전투 해석기는 그걸 점프로 안 읽는다"
            )

    # 🔴 **`0F` 의 주소 2바이트를 덮어쓰지 않았나** — 위의 자동 건너뜀이 정말 걸렸나를
    #    **결과로** 확인한다. 덮으면 점프가 엉뚱한 데로 가서 흐름이 깨진다(화면이 아니라).
    _chunks = {}
    for _d in scn.load():
        for _v in _d.values():
            _chunks[_v["index"] * common.SECTOR_SIZE] = _v["data"]
    check_no_jump_clobber(marks, _chunks)
    # 🔴 **전투 마크의 꼬리 공백은 원본보다 2를 넘지 못한다** — 규칙(위)을 정본으로
    #    우회하는 길을 **결과로** 막는다. 2026-09-08 회귀가 정확히 그 길로 들어왔다.
    _combat_span = [
        (v["index"] * common.SECTOR_SIZE, v["index"] * common.SECTOR_SIZE + len(v["data"]))
        for v in scn.load()[1].values()
    ]
    for off, old_b, new_b in marks:
        if not any(a <= off < b for a, b in _combat_span):
            continue
        grew = (len(new_b) - len(new_b.rstrip(b" "))) - (len(old_b) - len(old_b.rstrip(b" ")))
        if grew > 2:
            raise SystemExit(
                f"🔴 전투 청크에 꼬리 공백을 {grew}개 붙였다 {off:#08x} — "
                "전투 화면은 그걸 그대로 그린다(규칙: 2 이하)"
            )

    # 🔴 **겹치면 나중 것이 앞 것을 뭉갠다** — 조용히 틀리는 종류라 여기서 죽인다.
    seen: dict[int, int] = {}
    for off, _e, new in marks:
        for i in range(off, off + len(new)):
            if i in seen:
                raise SystemExit(f"🔴 패치가 겹친다 {i:#08x}")
            seen[i] = off
    return marks, st


_REV = None


def _rev() -> dict:
    """SJIS 2바이트 → 한글. ⚠ 폰트를 다시 만들면 느리다 — 한 번만 만든다."""
    global _REV
    if _REV is None:
        syl, _ = font.build()
        _REV = {sjis.sjis_of_index(slot_of(i)): c for i, c in enumerate(syl)}
    return _REV


def decode_back(b: bytes) -> str:
    """넣은 바이트를 **우리 규약으로 되읽는다** — 슬롯 계산의 역.

    🔴 이게 이 층의 진짜 게이트다. `shared/text/sjis.py` 가 못 박아 뒀듯 **슬롯이 틀리면
       화면에만 엉뚱한 글자가 나오고 빌드도 단위 테스트도 통과한다.** 그래서 넣은 것을
       되읽어 정본과 글자로 대조한다(왕복).
    """
    rev = _rev()
    out, i = [], 0
    while i < len(b):
        c = b[i]
        if c in (0x01, 0x03, 0x05):
            out.append({0x01: "\\n", 0x03: "<WAIT>", 0x05: "<PAGE>"}[c])
            i += 1
        elif c == JUMP:
            break  # 우리가 심은 점프 — 여기까지가 문안이다
        elif c >= 0x81:
            two = b[i : i + 2]
            out.append(rev.get(two) or two.decode("shift_jis", "replace"))
            i += 2
        else:
            out.append(chr(c))
            i += 1
    return "".join(out)


def verify_built(tag: str) -> int:
    """구운 이미지를 되읽어 **정본과 글자로** 대조한다. 점프 목적지도 본다."""
    built = common.BUILD_DIR / tag / "scenario.d88"
    if not built.exists():
        raise SystemExit(f"🔴 빌드가 없다: {built} — tools/build.py 를 먼저")
    flat = b"".join(x["data"] for x in common.read_sectors(built))
    script = json.loads(SCRIPT.read_text(encoding="utf-8"))
    marks, _ = plan()
    bad = jbad = 0
    n = 0
    for off, _expect, new in marks:
        got = flat[off : off + len(new)]
        if got != new:
            bad += 1
            continue
        if new[0] == JUMP and len(new) == 3:
            continue  # 밖으로 뺀 자리의 머리 — 문안은 빈자리에 있다
        n += 1
        # ⚠ 우리가 넣은 패딩은 떼고 본다 — 「공백 메움」은 꼬리에, **칸 표는 양쪽에** 붙는다.
        want = decode_back(new).strip(" ")
        # 정본을 찾으려면 열쇠가 필요한데, 여기선 **되읽은 것이 어떤 정본과도 같은가**로 본다
        if want and want not in _script_values(script):
            jbad += 1
    print(f"되읽기 대조 {n:,}건 · 바이트 불일치 {bad} · 정본에 없는 문안 {jbad}")
    return 1 if (bad or jbad) else 0


_VALS = None


def _script_values(script: dict) -> set:
    global _VALS
    if _VALS is None:
        _VALS = set()
        # 표에 직접 채운 칸도 우리 문안이다 — 안 넣으면 「정본에 없다」로 잘못 센다
        for t in CELL_TABLES:
            for txt in t.get("kr", {}).values():
                _VALS.add(txt)
                _VALS.add(txt.strip(" "))
        for v in script.values():
            t = v["t"]
            for x in (t, t.replace("\n", "\\n")):
                _VALS.add(x)
                _VALS.add(x.strip(" "))
    return _VALS


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--verify",
        metavar="TAG",
        nargs="?",
        const=common.BUILD_TAG,
        help="구운 이미지를 되읽어 정본과 대조한다",
    )
    a = ap.parse_args()
    common.check_originals()
    if a.verify:
        return verify_built(a.verify)
    marks, st = plan()
    print(f"문안 패치 {len(marks):,}건")
    for k, v in st.items():
        print(f"  {k:20s} {v:7,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
