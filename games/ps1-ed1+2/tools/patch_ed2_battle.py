#!/usr/bin/env python3
"""ED2 전투 문안(ED2.EXE) 한글화 — **제자리 치환만** 한다.

**소재.** 전투 문자열은 코드가 `lui`+`addiu/ori` 로 주소를 만들어 참조한다. 그 쌍을 전수로
훑어 **코드가 실제로 부르는 문자열**을 모은다(`patch_items.corpus_strings` 와 같은 방법).
ED2 는 477건이 나온다.

**절반은 공짜다.** ED1 전투 정본(`textmap/battle.json`, 498건)의 JP 원문과 **글자까지 같은
것**이 78건 있다 — 두 편이 같은 엔진이라 전투 메시지를 공유한다. 그건 다시 번역하지 않고
그대로 쓴다(표기가 갈릴 여지도 없어진다). ED2 에만 있는 것은 `textmap/battle_ed2.json`.

⚠ **제자리에 안 들어가면 건너뛴다.** ED1 쪽(`patch_items.apply_battle`)은 넘치는 문자열을
풀로 재배치하고 `lui` 까지 갱신하는데, 그건 참조를 하나라도 놓치면 **엉뚱한 주소를 읽어
깨진다.** ED2 는 아직 인게임 검증이 얕으므로 위험을 안 진다 — 남는 건 보고만 하고 다음에
재배치 경로를 붙인다.

  python3 tools/patch_ed2_battle.py --plan   # 무엇이 들어가고 무엇이 남는지
  python3 tools/patch_ed2_battle.py          # 이미지에 적용
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map as H  # noqa: E402
from battle_text import B  # noqa: E402
from common import BUILD_DIR, extract, write_user_data  # noqa: E402
from derive_text import jp_map  # noqa: E402
from patch_items import MIPS_ADDIU, MIPS_ORI, iter_lui_pairs  # noqa: E402

ED2_LBA, ED2_SIZE = 756, 872448
IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"

# 참조가 몰려 있는 구획 — 밖은 맵 데이터·코드다. `--plan` 으로 늘려가며 확인한다.
CORPUS = ((0x3000, 0xC000), (0xD4000, 0xD5000))
KANA = re.compile(r"[ぁ-んァ-ヴー]")

# ⚠ **메모리카드·세이브 문구는 여기서 손대지 않는다** — 같은 구획에 섞여 있지만
# ED1 에서도 `patch_sys_ui` 관할이고, 두 곳에서 쓰면 서로 덮는다.
SKIP = re.compile(r"メモリーカード|カードには|データが壊れ|フォーマット|セーブ|ロード")


def _enc(kr):
    """한글은 슬롯 SJIS, 나머지(숫자·영문·부호·개행)는 원래 SJIS."""
    out = bytearray()
    for ch in kr:
        if "가" <= ch <= "힣":
            out += H.encode_kr(ch)
        elif ch == "\n":
            out.append(0x0A)
        else:
            out += ch.encode("shift_jis")
    return bytes(out)


def strings(buf):
    """{파일오프셋: JP} — 코드가 부르는 전투 문자열."""
    out = {}
    for _imm, _lui, _op, addr in iter_lui_pairs(buf, {MIPS_ADDIU, MIPS_ORI}):
        fo = addr - 0x80010000 + 0x800
        if not any(lo <= fo < hi for lo, hi in CORPUS):
            continue
        j = buf.find(b"\x00", fo)
        if j < 0 or not (2 <= j - fo <= 200):
            continue
        try:
            s = buf[fo:j].decode("cp932")
        except Exception:  # noqa: BLE001 — 코드/데이터 구간
            continue
        # `\x80` 이 든 것은 문자열이 아니라 **포인터 배열이 앞에 붙은 자리**다.
        if ("\x80" in s) or not (KANA.search(s) or "%" in s):
            continue
        out[fo] = s
    return out


def plan():
    """([(오프셋, JP, KR, 슬롯)], 넘치는 것, 번역 없는 것)."""
    buf = extract(ED2_LBA, ED2_SIZE)
    ed2 = jp_map("battle_ed2")
    fit, over, none = [], [], []
    for fo, jp in sorted(strings(buf).items()):
        if SKIP.search(jp):
            continue
        kr = B.get(jp) or ed2.get(jp)
        if kr is None:
            none.append((fo, jp))
            continue
        end = buf.find(b"\x00", fo)
        nxt = end
        while nxt < len(buf) and buf[nxt] == 0:
            nxt += 1
        slot = nxt - fo
        (fit if len(_enc(kr)) + 1 <= slot else over).append((fo, jp, kr, slot))
    return fit, over, none


def main():
    fit, over, none = plan()
    if "--plan" in sys.argv:
        for fo, _jp, kr, slot in fit:
            print(f"  {fo:#07x} [{slot:>3}B] → {kr!r}")
        for fo, _jp, kr, slot in over:
            print(f"  ⚠ 넘침 {fo:#07x} [{slot}B] → {kr!r} ({len(_enc(kr)) + 1}B)")
        print(f"\n제자리 {len(fit)} · 넘침 {len(over)} · 번역 없음 {len(none)}")
        return 0
    buf = bytearray(extract(ED2_LBA, ED2_SIZE, path=IMG))
    for fo, _jp, kr, slot in fit:
        b = _enc(kr) + b"\x00"
        buf[fo : fo + slot] = b + b"\x00" * (slot - len(b))
    with open(IMG, "r+b") as f:
        n = write_user_data(f, ED2_LBA, bytes(buf), label="ED2 전투 문안 (ED2.EXE)")
    print(
        f"ED2.EXE: 섹터 {n}개 수정 — 전투 문안 {len(fit)}건 제자리"
        f" (넘쳐 보류 {len(over)} · 미번역 {len(none)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
