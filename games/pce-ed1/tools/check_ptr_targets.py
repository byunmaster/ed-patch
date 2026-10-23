#!/usr/bin/env python3
"""씬 블록의 **메시지 포인터 참조** 목표가 번역 단위(메시지) 안에 드는지 센다 — 목록 밖 글 목표가 있으면 실패(10-18, sfc-ed1 발견).

  python3 tools/check_ptr_targets.py [--list]

`messages.references()` 가 블록의 포인터 자리(머리 표 · 분할 즉치 · 옵코드/JMP/JSR 피연산자)를 모은다. 목표 오프셋마다:
  · 메시지 구간 `[start, end)` 안 → 번역 단위에 든다(통과)
  · 밖인데 거기가 **글처럼 생김**(SJIS 두 글자 이상 · `1F` 화자 머리 · `09 nn`) → **목록 밖 글 목표**(실패 — 화면에 일본어가 뜰 수 있다)
  · 밖이고 글처럼 안 생김 → 코드·표 목표(통과)
⚠ 메시지 파서가 훑는 구간 밖을 가리키는 표가 있으면 단위·잔존 게이트 둘 다 못 본다(sfc-ed1: 대사 101개가 일본어로 남았다) — 이 검사가 그 구멍이다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import containers
import messages as M


HEAD_MAX = 16  # `1F + 화자(SJIS ≤6자) + 04 + 01 …` 머리 길이 상한


def looks_like_text(block: bytes, off: int) -> bool:
    if off + 4 > len(block):
        return False
    b = block[off:]
    if b[0] == 0x1F:  # 화자 머리 — 뒤(`04` 와 줄바꿈 `01` 다음)에 글이 와야 글 목표다. 옵코드(`12` 조건 · `0F` 점프)가 오면 분기 머리라 글은 점프 목적지에 있다
        k = b.find(0x04, 1, 16)
        if k < 0:
            return False
        k += 1
        while k < len(b) and b[k] == 0x01:
            k += 1
        try:
            name = b[1 : k - 2].decode("cp932")  # 화자 이름은 엄격한 전각 SJIS — 코드 바이트가 우연히 `1F` 로 시작하는 소음을 거른다
        except UnicodeDecodeError:
            return False
        return bool(name) and all(ord(c) > 0xFF and not 0xFF61 <= ord(c) <= 0xFF9F for c in name) and k + 1 < len(b) and M.is_lead(b[k])
    if b[0] == 0x09 and b[1] < 0x40:
        return False  # 공용 화자 머리 — 메시지 파서가 이미 단위로 잡는다(안쪽 일치는 우연)
    # 글 머리 — 앞 6바이트(세 글자)가 **엄격한** SJIS 전각 글자이고 가나가 든다(코드 바이트가 우연히 두 글자로 읽히는 소음을 거른다)
    try:
        head = b[:6].decode("cp932")
    except UnicodeDecodeError:
        return False
    return len(head) == 3 and all(ord(c) > 0xFF and not 0xFF61 <= ord(c) <= 0xFF9F for c in head) and M.KANA.search(head) is not None


def scan_block(block: bytes) -> dict:
    msgs = M.parse(block)
    refs = M.references(block)
    # 스크립트 옵코드(0F·10…)의 피연산자는 `references()` 가 소음이라 뺀다 — 그 점프가 가리키는 글이 목록 밖이면 아무도 못 본다.
    # 그래서 블록 안 **모든 16비트 값**을 목표 후보로 보되, 글 머리처럼 생긴 자리(엄격)만 센다 — 소음은 「글 아님」으로 걸러진다.
    for i in range(len(block) - 1):
        w = block[i] | block[i + 1] << 8
        if M.BASE <= w < M.BASE + len(block):
            refs.setdefault(w - M.BASE, []).append(i)
    inside = outside_text = other = 0
    bad: list[int] = []
    for off in sorted(refs):
        # 메시지 머리(`1F 화자 04 01` 등)는 `start` 앞에 있다 — 목표가 머리 자리면 그 메시지 몫이다
        if any(m.start <= off < m.end or 0 <= m.start - off <= HEAD_MAX for m in msgs):
            inside += 1
        elif looks_like_text(block, off):
            outside_text += 1
            bad.append(off)
        else:
            other += 1
    return {"targets": len(refs), "inside": inside, "text_outside": outside_text, "other": other, "bad": bad}


def main() -> int:
    seen: set[int] = set()
    tot = {"blocks": 0, "targets": 0, "inside": 0, "text_outside": 0, "other": 0}
    bad_rows = []
    for c in containers.scan():
        for b in c["blocks"]:
            if b["id"] in seen:
                continue
            seen.add(b["id"])
            r = scan_block(b["data"])
            tot["blocks"] += 1
            for k in ("targets", "inside", "text_outside", "other"):
                tot[k] += r[k]
            for off in r["bad"]:
                bad_rows.append((b["id"], off))
    print(
        f"씬 블록 {tot['blocks']} · 포인터 목표 {tot['targets']} — 번역 단위 안 {tot['inside']} · 코드·표 {tot['other']} · "
        f"🔴 목록 밖 글 {tot['text_outside']}"
    )
    for sid, off in bad_rows[:20]:
        print(f"  🔴 scn{sid:03d} +{off:#06x}")
    return 1 if bad_rows else 0


if __name__ == "__main__":
    sys.exit(main())
