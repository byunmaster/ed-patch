"""스크립트 구간을 **옮기지 않고** 대사를 늘리는 편집 — 문자열 추가 · 스크립트 꼬리에 코드 덧붙이기 · 대사 자리를 점프로 바꾸기(트램펄린).

왜: 쪽 수·줄 수는 스크립트가 정한다(`typeset.windows`). 번역이 한 쪽에 안 들어가면 쪽을 **더해야** 하는데, 스크립트 한복판에 바이트를 끼우면 **뒤의 모든 오프셋**이 밀린다
(VM 점프는 `멤버 시작 + s16` 절대 오프셋 — `docs/wrap.md`). 그래서 **끼우지 않고**:

  1. 새 문자열을 표 끝에 더한다(색인 N…). 표·풀이 늘 뿐 스크립트 오프셋은 안 변한다(문자열은 색인으로 가리킨다).
  2. 새 코드를 **스크립트 구간 맨 끝**(`TEXT_BASE` 바로 앞)에 덧붙인다 — 그 앞의 모든 오프셋은 그대로다.
  3. 늘리고 싶은 **메시지 블록**(VM 연산 `0F` + 메시지 언어 스트림 `…00`)을 `02 <s16>`(VM 연산 `02` = JMP, 멤버 시작 기준 s16 — `0x800431b0` 핸들러)으로 바꾸고,
     덧붙인 코드에 새 블록(원래 줄 + 새 줄들 — `01` 줄바꿈·`02` 쪽 넘김·`00` 끝) + 점프 복귀(원래 블록 다음 바이트)를 둔다.
     ⚠ 메시지 언어 안의 `02` 는 **쪽 넘김**이지 점프가 아니다 — 점프는 VM 연산 층(블록 밖)에서만 쓴다.

🔴 가정(코드로 읽은 것 — 인게임으로 확인한 건 `probe` 시험): ① 연산 `02` = 무조건 점프, 피연산자 s16 은 **짝수 정렬 뒤**에 읽는다(홀수 주소의 `02` 뒤는 패딩 없이 바로 s16)
② 점프 기준은 멤버의 RAM 시작 주소(`0x800C6E14` — 실측: 멤버가 올라간 `0x800FA6FC` 와 같다) ③ 대사 자리의 4째 바이트(흐름)는 점프가 건너뛰어 안 읽힌다.
⚠ 연산 `0F` 가 홀수 주소에 있어야 한다(색인 u16 이 짝수) — 덧붙이는 코드도 **첫 연산을 홀수 주소**에 둔다.
"""

import itertools
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared.ps1 import gmf_script as sm

JMP = 0x02
TEXT = 0x0F
TERM = 0xFFFF


class EditError(Exception):
    pass


def _parts(mem):
    """(base, script 바이트(머리 2B 제외), 표 N, 조각 코드열 목록, 꼬리) — 표 규격만."""
    if sm.layout(mem) != sm.LAYOUT_TABLE:
        raise EditError("표 규격 멤버만 다룬다")
    info = sm.parse(mem)
    base, n = info["base"], info["table_len"]
    segs = [list(c) for _, c in info["segments"]]
    last = info["segments"][-1]
    end = last[0] + len(last[1]) * 2 + 2
    return base, bytes(mem[2:base]), n, segs, bytes(mem[end:])


def _pack(script, segs, tail):
    """[base][script][표][풀][꼬리] — 표 첫 항목 = 표 자신의 길이(`N = 표[0]/2`)."""
    n = len(segs)
    base = 2 + len(script)
    if base % 2:
        raise EditError("스크립트 구간 길이가 홀수 — TEXT_BASE 가 짝수여야 한다")
    tbl, pool = [], bytearray()
    for codes in segs:
        tbl.append(n * 2 + len(pool))
        pool += struct.pack(f"<{len(codes)}H", *codes) + struct.pack("<H", TERM)
    if max(tbl) > 0xFFFF:
        raise EditError("풀이 u16 을 넘었다")
    return struct.pack("<H", base) + script + struct.pack(f"<{n}H", *tbl) + bytes(pool) + tail


def add_strings(mem, new_codes):
    """(새 멤버, [새 색인…]) — 표 끝에 문자열을 더한다. 스크립트는 안 건드린다(색인 참조)."""
    _base, script, n, segs, tail = _parts(mem)
    idx = list(range(n, n + len(new_codes)))
    return _pack(script, segs + [list(c) for c in new_codes], tail), idx


def append_code(mem, code):
    """(새 멤버, 코드 시작 오프셋) — 스크립트 구간 맨 끝에 `code` 를 덧붙인다. 코드의 첫 바이트가 **홀수 오프셋**에 앉게 패딩한다."""
    _base, script, _n, segs, tail = _parts(mem)
    off = 2 + len(script)  # 지금 TEXT_BASE = 덧붙일 자리
    pad = b"\x00" if off % 2 == 0 else b""
    new = script + pad + code
    new += b"\x00" * (len(new) % 2)  # TEXT_BASE 짝수
    return _pack(new, segs, tail), off + len(pad)


def blocks(mem):
    """[{p0, e, sites:[(q, 조각 색인, 흐름 바이트)]}] — **단순한 대사 블록**(VM 연산 `0F` + `0F <색인> <흐름>` 줄들 + `00`). 쪽 늘리기(`rewrite_message`)가 옮길 수 있는 꼴만.

    🔴 메시지는 **VM 연산 `0F`** 가 시작하고(핸들러 `0x80045be8` — 창을 열고 `0x8003c98c` 메시지 해석기에 커서를 넘긴다), 그 뒤 바이트는 **메시지 언어**다
    (해석기 점프표 `0x800103d0`, 16개): `0F`(+정렬 패딩+u16 색인) = 문자열 출력 · `01` 줄바꿈 · `02` 키 대기 후 쪽 넘김 · `00` 끝 · 나머지는 피연산자 없는 한 바이트 연산(색·대기·이름 삽입).
    ⇒ 블록 안엔 VM 점프가 없다(`02` 는 쪽 넘김이지 점프가 아니다). 블록을 **통째로** 옮겨야 한다.
    `p0` = 블록 시작(VM `0F`), `e` = 끝(`00` 다음 바이트 = 다음 VM 연산). 출력 사이가 정확히 흐름 바이트(`01`·`02`) 하나뿐인 스트림만 돌려준다 — 이름 삽입 같은 연산이 낀 블록은 다시 쓸 수 없다.
    """
    import typeset

    out = []
    for st in typeset.message_streams(mem):
        if st["kind"] != "A":
            continue
        qs = [q for q, _ in st["prints"]]
        if mem[qs[-1] + 2] != 0 or st["end"] != qs[-1] + 3:
            continue
        if any(
            b - a != 4 or mem[a + 2] not in (1, 2) or mem[b - 1] != TEXT
            for a, b in itertools.pairwise(qs)
        ):
            continue
        out.append(
            {"p0": st["p0"], "sites": [(q, v, mem[q + 2]) for q, v in st["prints"]], "e": st["end"]}
        )
    return out


def block_of(mem, seg):
    """조각 `seg` 를 가리키는 첫 대사 자리가 든 블록. 없으면 `EditError`."""
    for b in blocks(mem):
        if any(v == seg for _, v, _ in b["sites"]):
            return b
    raise EditError(f"조각 {seg} 가 든 대사 블록이 없다")


def jmp_bytes(at, target):
    """주소 `at` 에 놓는 JMP — 연산 바이트 뒤 커서가 홀수면 패딩 한 바이트(핸들러가 짝수로 올린다)."""
    if not 0 <= target < 0x8000:
        raise EditError(f"점프 목표 {target} 가 s16 밖이다")
    pad = b"\x00" if (at + 1) % 2 else b""
    return bytes([JMP]) + pad + struct.pack("<h", target)


def message_bytes(at, lines):
    """주소 `at` 에서 시작하는 블록 바이트 — `[VM 0F][ (0F [패딩] <색인 u16> <흐름>)… ]`. `lines` = [(색인, 흐름)…], 마지막 흐름은 `00`."""
    out = bytearray([TEXT])  # VM 연산
    for idx, flow in lines:
        out.append(TEXT)  # 메시지 언어: 문자열 출력
        if (at + len(out)) % 2:
            out.append(0)  # 정렬 패딩(짝수 주소에 u16)
        out += struct.pack("<H", idx)
        out.append(flow)
    return bytes(out)


def rewrite_message(mem, seg, extra, flows):
    """조각 `seg` 가 든 **메시지 블록**을 줄·쪽이 더해진 새 블록으로 바꾼다 — 블록을 스크립트 꼬리로 옮기고 원래 자리는 JMP 로 잇는다. 반환 = 새 멤버.

    `extra` = 더할 문자열 코드열들(표 끝에 색인 N… 로 붙는다), `flows` = 원래 줄(들) + 새 줄들 뒤의 흐름 바이트 — 길이 `원래 줄 수 + len(extra)`, 마지막은 `00`(끝).
    원래 줄들의 색인·순서는 그대로 두고 흐름만 새로 정한다(예: 원래 `[(4,02),(5,00)]` + 새 줄 하나 → flows `[02,02,00]`).
    """
    b = block_of(mem, seg)
    old = [v for _, v, _ in b["sites"]]
    if len(flows) != len(old) + len(extra):
        raise EditError(f"흐름 바이트 수는 {len(old) + len(extra)} 여야 한다")
    if flows[-1] != 0:
        raise EditError("마지막 흐름은 `00`(끝)이어야 한다")
    mem1, idx = add_strings(mem, extra)
    # 새 블록은 덧붙이는 자리에서 시작한다 — 그 주소를 알아야 정렬 패딩을 맞춘다. 덧붙일 자리 = 지금 스크립트 구간 끝 + (짝수면 패딩 1)
    base = sm.text_base(mem1)
    at = base + (1 if base % 2 == 0 else 0)
    body = message_bytes(at, list(zip(old + idx, flows, strict=True)))
    back_at = at + len(body)
    body += jmp_bytes(back_at, b["e"])
    mem2, off = append_code(mem1, body)
    assert off == at, (off, at)
    out = bytearray(mem2)
    j = jmp_bytes(b["p0"], off)
    if len(j) > b["e"] - b["p0"]:
        raise EditError("원래 블록이 JMP 를 못 담을 만큼 짧다")
    out[b["p0"] : b["p0"] + len(j)] = j
    return bytes(out)
