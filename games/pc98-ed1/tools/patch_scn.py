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


def areas() -> dict:
    """시나리오 + **전투** 청크를 한 자로 본다.

    🔴 전투 영역(`scn.COMBAT_RANGE`)도 **같은 이벤트 스크립트 문법**이다(2026-09-06 실측:
       청크 110 · 텍스트 런 3,474 · 안으로 점프가 오는 것 46 · 꼬리 빈자리 48,068B).
       몬스터 이름과 전투 대사가 거기 살아서, 여길 안 열면 **정본 86종이 화면에 못 간다.**
    """
    scenario, combat = scn.load()
    return {**scenario, **combat}


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


def plan() -> tuple[list[tuple[int, bytes, bytes]], dict]:
    """(평면 오프셋, 원본이어야 할 바이트, 새 바이트) 목록 + 통계."""
    script = json.loads(SCRIPT.read_text(encoding="utf-8")) if SCRIPT.exists() else {}
    scenario = areas()
    pierce = pierced_map(scenario)
    marks: list[tuple[int, bytes, bytes]] = []
    st = {
        "제자리": 0,
        "칸 표": 0,
        "건너뜀:칸 넘침": 0,
        "틈 건너뜀": 0,
        "공백 메움": 0,
        "밖으로": 0,
        "밖으로:점프가 온다": 0,
        "건너뜀:점프가 머리에": 0,
        "건너뜀:3B 미만": 0,
        "건너뜀:빈자리 부족": 0,
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

        for b in blocks:
            if any(c <= b["o"] < c + w for c, w in cells_all.items()):
                continue  # 🔴 칸 표는 위에서 처리했다 — 일반 경로가 덮으면 정렬이 깨진다
            k = line_key(reuse.normalise(b))
            if k not in script:
                continue
            o, n = b["o"], b["n"]

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
            if forced_pool:
                blob = None  # 아래 「밖으로」로 간다
            elif slack == 0:
                blob = new
                st["제자리"] += 1
            elif slack >= 3:
                blob = new + bytes((JUMP, *(W.BASE + o + n).to_bytes(2, "little")))
                st["틈 건너뜀"] += 1
            elif slack > 0:
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
