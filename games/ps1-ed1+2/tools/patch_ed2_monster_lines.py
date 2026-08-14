#!/usr/bin/env python3
"""ED2 몬스터 전투 대사(`ED2MON0~5.BIN`) 한글화 — **제자리 치환만** 한다.

이름은 `patch_ed2_monsters.py` 가 맡고 여기는 **대사**다. 파일 안의 일본어 문자열 1,557개
가운데 진짜 대사는 **123개뿐**이다 — 나머지는 이름이거나, 2바이트 값이 SJIS 한자로 읽힌
이진 자료다(`曚B席` 류). 그래서 걸러내는 규칙이 이 도구의 반이다.

**79개는 자동 생성한다.** `Xが現れた。`·`XとYが現れた。`·`Xとの戦闘だ。` 는 이름이 문자열에
**박혀 있어서**(런타임 인자가 아니다) 이름 정본만 있으면 조사까지 정적으로 정해진다 —
`슬라임` 은 받침이 있으니 `이`, `부두` 는 `가`. 병기(`이(가)`)를 쓸 이유가 없다.

나머지 28개는 손으로 옮겨 `textmap/monster_lines_ed2.json` 에 둔다.

⚠ **조각으로 갈려 있다.** 한 문장이 `%c%s%cは` + `%c%s%cを冷たい` + `視線で見つめた。` 로
나뉘어 저장되고 엔진이 이어 붙인다. 한국어도 일본어와 어순이 같아서 **조각째 옮겨도 이어
붙는다** — 조각을 합치려 들면 슬롯 구조를 깨뜨린다.

⚠ **넘치면 건너뛴다**(`patch_ed2_battle.py` 와 같은 방침). 뒤가 곧 다음 문자열이다.

  python3 tools/patch_ed2_monster_lines.py --plan   # 무엇이 들어가고 무엇이 남는지
  python3 tools/patch_ed2_monster_lines.py          # 이미지에 적용
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map as H
from common import BUILD_DIR, ROOT, extract, write_user_data
from ed2_monster_review import MON, SUFFIX, decode_sjis

IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"
NAMES = os.path.join(ROOT, "textmap", "monsters_ed2.json")
LINES = os.path.join(ROOT, "textmap", "monster_lines_ed2.json")

JP = re.compile(r"[ぁ-んァ-ヴー一-鿿]")
KANA = re.compile(r"[ぁ-んァ-ヴ]")
CTL = re.compile(r"[\x00-\x1f]")
# ⚠ cp932 는 미정의 바이트를 **사용자 영역**으로 넘긴다 — 이진 자료가 여기로 샌다.
PUA = re.compile(r"[-]")

APPEAR = re.compile(r"^(.+?)(?:と(.+?))?が現れた。$")
BATTLE = re.compile(r"^(.+?)との戦闘だ。$")


def is_dialog(s):
    """대사인가 — 이진 자료를 걸러낸다.

    ⚠ 규칙 셋이 다 필요하다. ①**세 글자 미만은 자료다**(2바이트 값 하나가 한자로 읽힌다 —
    `筧` 이 269번 나온다). ②**가나가 없으면 자료다**(대사엔 조사가 반드시 낀다). ③사용자
    영역 글자가 있으면 자료다. 하나라도 빼면 수백 개가 샌다.
    """
    if len(s) < 3 or PUA.search(s) or CTL.search(s) or not KANA.search(s):
        return False
    core = re.sub(r"%[csd]|[!?！？。、…・\s]", "", s)
    return bool(core) and len(JP.findall(core)) / len(core) >= 0.8


def josa(word, pair):
    """받침에 따라 조사를 고른다 — 이름이 문자열에 박혀 있으니 정적으로 정해진다.

    pair 는 (받침 있을 때, 없을 때). 한글이 아닌 꼬리(영문 접미 `A`)는 무받침으로 본다.
    """
    tail = word.strip()[-1:] if word.strip() else ""
    has = "가" <= tail <= "힣" and (ord(tail) - 0xAC00) % 28
    return pair[0] if has else pair[1]


def auto_lines(names):
    """`Xが現れた。` 류를 이름 정본에서 만든다 — {JP: KR}."""
    out = {}
    for jp, kr in names.items():
        # ⚠ 마침표를 안 붙인다 — **정발이 그렇고**(`슬라임이 나타났다`) 1바이트가 남아
        # 슬롯 넘침이 대부분 풀린다(13건 → 1건).
        out[f"{jp}が現れた。"] = f"{kr}{josa(kr, ('이', '가'))} 나타났다"
        out[f"{jp}との戦闘だ。"] = f"{kr}{josa(kr, ('과', '와'))}의 전투다"
        for jp2, kr2 in names.items():
            if jp2 != jp:
                out[f"{jp}と{jp2}が現れた。"] = (
                    f"{kr}{josa(kr, ('과', '와'))} {kr2}{josa(kr2, ('이', '가'))} 나타났다"
                )
    return out


def _enc(kr):
    out = bytearray()
    for ch in kr:
        out += H.encode_kr(ch) if "가" <= ch <= "힣" else ch.encode("shift_jis")
    return bytes(out)


def plan():
    """([(lba, 오프셋, JP, KR, 슬롯)], 넘치는 것, 문안 없는 것)."""
    with open(NAMES, encoding="utf-8") as f:
        names = json.load(f)
    with open(LINES, encoding="utf-8") as f:
        hand = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    table = auto_lines(names)
    table.update(hand)  # 손으로 정한 것이 이긴다

    fit, over, none = [], [], []
    for group, (lba, size) in sorted(MON.items()):
        buf = bytes(extract(lba, size))
        i = 0
        while i < len(buf) - 1:
            if buf[i] == 0:
                i += 1
                continue
            j = buf.find(b"\x00", i)
            if j < 0:
                break
            s = decode_sjis(buf[i:j]) if 2 <= j - i <= 200 else None
            if s and is_dialog(s) and SUFFIX.sub("", s) not in names:
                nxt = j
                while nxt < len(buf) and buf[nxt] == 0:
                    nxt += 1
                head = j - len(s.encode("cp932", "replace"))
                slot = nxt - head
                kr = table.get(s)
                if kr is None:
                    none.append((group, head, s))
                else:
                    (fit if len(_enc(kr)) + 1 <= slot else over).append((lba, head, s, kr, slot))
            i = j + 1
    return fit, over, none


def main():
    fit, over, none = plan()
    if "--plan" in sys.argv:
        for _lba, off, jp, kr, slot in fit:
            print(f"  {off:#07x} [{slot:>3}B] {jp} → {kr}")
        for _lba, off, jp, kr, slot in over:
            print(f"  ⚠ 넘침 {off:#07x} [{slot}B] {jp} → {kr} ({len(_enc(kr)) + 1}B)")
        for group, off, jp in none:
            print(f"  ⚠ 문안 없음 ED2MON{group} {off:#07x} {jp}")
        print(f"\n제자리 {len(fit)} · 넘침 {len(over)} · 문안 없음 {len(none)}")
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
            total += write_user_data(f, lba, bytes(buf), label=f"ED2MON{group} 전투 대사")
    print(
        f"ED2MON: 섹터 {total}개 수정 — 전투 대사 {len(fit)}건 제자리"
        f" (넘쳐 보류 {len(over)} · 문안 없음 {len(none)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
