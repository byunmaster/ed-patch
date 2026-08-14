#!/usr/bin/env python3
"""ED2 몬스터 이름(`ED2MON0~5.BIN`) 한글화 — **제자리 치환만** 한다.

레코드는 **[이름들][대사들][능력치표]** 반복이고 이름은 레코드 머리에 붙어 있다. 구조와
그 근거는 `docs/ed2-status.md`, 원문↔정발 짝짓기는 `tools/ed2_monster_review.py`.

**정본은 `textmap/monsters_ed2.json`** 이고 이 패처는 그것만 읽는다. 짝짓기(음차 유사도)는
제안이라 빌드 경로에 두지 않는다 — 두면 결과가 환경을 탄다(레포 제1원칙).

⚠ **개체 접미는 반각으로 쓴다**(`スライムＡ` → `슬라임A`). ED1 에서 이미 반각으로 통일했고
(전각이면 이름표 폭이 어긋난다), 덤으로 1바이트가 남아 제자리에 들어갈 여지가 커진다.

⚠ **넘치면 건너뛴다.** 뒤가 곧바로 다음 이름·대사라 밀어 쓰면 그걸 덮는다. 남는 건 보고만
하고 재배치는 붙이지 않는다 — `patch_ed2_battle.py` 와 같은 방침이다.

  python3 tools/patch_ed2_monsters.py --plan   # 무엇이 들어가고 무엇이 남는지
  python3 tools/patch_ed2_monsters.py          # 이미지에 적용
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map as H
from common import BUILD_DIR, ROOT, extract, write_user_data
from ed2_monster_review import MON, SUFFIX, records
from ed2_monster_review import strings as jp_strings

IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"
CANON = os.path.join(ROOT, "textmap", "monsters_ed2.json")

JP = re.compile(r"[ぁ-んァ-ヴ一-鿿]")
CTL = re.compile(r"[\x00-\x1f]")
DIALOG = re.compile(r"[。！？…、」『%\n]")
NAME_MAX = 14

# 전각 접미 → 반각. `′`·`”` 는 분열체 구분이라 살린다(`赤スライムＡ′`).
HALF = {chr(0xFF21 + i): chr(ord("A") + i) for i in range(26)}


def _enc(kr):
    """한글은 슬롯 SJIS, 나머지(숫자·영문·부호)는 원래 SJIS — 전투 패처와 같은 관용."""
    out = bytearray()
    for ch in kr:
        if "가" <= ch <= "힣":
            out += H.encode_kr(ch)
        else:
            out += ch.encode("shift_jis")
    return bytes(out)


def name_strings(buf, start, end):
    """레코드 머리의 이름 문자열 — [(오프셋, 슬롯 바이트, 원문)].

    ⚠ 슬롯은 **다음 문자열이 시작하는 자리까지**다(널 패딩 포함). 널 하나만 보면 뒤에 남는
    패딩을 못 쓰는데, 한글이 SJIS 보다 길어지는 이름이 많아 그 1~2바이트가 당락을 가른다.

    ⚠ 검토표와 **같은 스캐너**를 쓴다. 여기서 직접 훑으면 이름 사이에 낀 쓰레기 바이트에서
    스캔이 끊겨 뒤쪽 이름을 통째로 놓친다(실측: 302건이 36건으로 줄었다).
    """
    out = []
    for off, text in jp_strings(buf, start, end):
        if len(text) > NAME_MAX or DIALOG.search(text) or CTL.search(text):
            break  # 이름 구간은 대사를 만나면 끝난다
        j = buf.find(b"\x00", off)
        nxt = j
        while nxt < end and buf[nxt] == 0:
            nxt += 1
        # ⚠ 스캔 시작이 아니라 **실제 문자열 시작**을 쓴다 — 앞에 잡음 바이트가 붙은 자리가
        # 있어(`ff 82 8f 50` + `モーンガーＡ`) 그대로 쓰면 잡음 위에 덮어쓴다.
        head = j - len(text.encode("cp932", "replace"))
        out.append((head, nxt - head, text))
    return _drop_noise_prefix(out)


def _drop_noise_prefix(items):
    """같은 레코드의 **깨끗한 형제**로 잡음 접두를 걷어낸다(검토표와 같은 규칙).

    `襲モーンガーＡ` 는 앞 데이터의 꼬리가 한자로 읽힌 것이고, 형제 `モーンガーＢ` 가
    깨끗하다. 안 걷어내면 정본에서 못 찾아 그 이름만 일본어로 남는다.

    ⚠ 오프셋·슬롯도 같이 민다 — 잡음 바이트 위에 덮어쓰면 그 자리의 데이터가 깨진다.
    """
    stems = {SUFFIX.sub("", t) for _o, _s, t in items}
    out = []
    for off, slot, text in items:
        st = SUFFIX.sub("", text)
        short = min((x for x in stems if x != st and st.endswith(x)), key=len, default=None)
        if short:
            drop = len(st[: -len(short)].encode("cp932", "replace"))
            off, slot, text = off + drop, slot - drop, text[len(st) - len(short) :]
        out.append((off, slot, text))
    return out


def plan():
    """([(lba, 오프셋, 원문, KR, 슬롯)], 넘치는 것, 정본에 없는 것)."""
    with open(CANON, encoding="utf-8") as f:
        canon = json.load(f)
    fit, over, none = [], [], []
    for group, (lba, size) in sorted(MON.items()):
        buf = bytes(extract(lba, size))
        for s, e in records(buf):
            for off, slot, jp in name_strings(buf, s, e):
                sfx = SUFFIX.search(jp)
                stem = jp[: sfx.start()] if sfx else jp
                tail = "".join(HALF.get(c, c) for c in (sfx.group() if sfx else ""))
                kr = canon.get(stem)
                if kr is None:
                    none.append((group, off, jp))
                    continue
                kr += tail
                (fit if len(_enc(kr)) + 1 <= slot else over).append((lba, off, jp, kr, slot))
    return fit, over, none


def main():
    fit, over, none = plan()
    if "--plan" in sys.argv:
        for _lba, off, jp, kr, slot in fit:
            print(f"  {off:#07x} [{slot:>3}B] {jp} → {kr}")
        for _lba, off, jp, kr, slot in over:
            print(f"  ⚠ 넘침 {off:#07x} [{slot}B] {jp} → {kr} ({len(_enc(kr)) + 1}B)")
        for group, off, jp in none:
            print(f"  ⚠ 정본에 없음 ED2MON{group} {off:#07x} {jp}")
        print(f"\n제자리 {len(fit)} · 넘침 {len(over)} · 정본에 없음 {len(none)}")
        return 0

    by_lba = {}
    for lba, off, _jp, kr, slot in fit:
        by_lba.setdefault(lba, []).append((off, kr, slot))
    total = 0
    for group, (lba, size) in sorted(MON.items()):
        if lba not in by_lba:
            continue
        buf = bytearray(extract(lba, size, path=IMG))
        for off, kr, slot in by_lba[lba]:
            b = _enc(kr) + b"\x00"
            buf[off : off + slot] = b + b"\x00" * (slot - len(b))
        with open(IMG, "r+b") as f:
            total += write_user_data(f, lba, bytes(buf), label=f"ED2MON{group} 몬스터 이름")
    print(
        f"ED2MON: 섹터 {total}개 수정 — 몬스터 이름 {len(fit)}건 제자리"
        f" (넘쳐 보류 {len(over)} · 정본에 없음 {len(none)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
