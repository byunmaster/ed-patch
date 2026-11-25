"""대사 숫자 꼴 게이트 — 숫자 한 덩이마다 **원판이 낸 꼴**을 따랐나(마스터 11-16 「원판이 반각쓴곳은 반각, 전각쓴곳은 전각」).

    python3 tools/check_digit_form.py

원판 조각의 숫자는 둘 중 하나로 나온다 — ① 수 그리기 연산 `0xEEEE a b`(값 a+b, 반각 꼴: HUD 숫자와 같다) ② 글자 코드열에 박힌 전각 숫자(코드 25~34).
번역 문안의 숫자 덩이 값이 ①에 있으면 **ASCII(반각)**, ②에 있으면 **전각**이어야 한다. 원판에 숫자가 없는 자리(한자 수사를 우리가 아라비아 수로 쓴 곳)는 전각을 쓴다(애매 목록 — 기준선).
영문은 원판 대사에 반각이 없어 전부 전각이다(ASCII 영문 금지 — `master_rulings.json`).
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import reinsert
import script_kr
import textenc

FW = "０１２３４５６７８９"
NO_ORIG = 3  # 원판에 숫자가 없는 자리(한자 수사 → 아라비아) — 전각으로 둔 곳. 늘면 실패


def events(codes, cm):
    nums, lits, cur, i = [], [], "", 0
    while i < len(codes):
        c = codes[i]
        if c == 0xEEEE and i + 2 < len(codes):
            if cur:
                lits.append(cur)
                cur = ""
            nums.append(codes[i + 1] + codes[i + 2])
            i += 3
            continue
        ch = cm.get(c, "")
        if ch and ch in FW:
            cur += str(FW.find(ch))
        elif cur:
            lits.append(cur)
            cur = ""
        i += 1
    if cur:
        lits.append(cur)
    return nums, lits


def find_bad():
    cm = textenc.charmap()
    members = build.identity_gate({})
    bad, noorig = [], []
    for (arc, mem), rows in script_kr.load_all().items():
        segs = reinsert.member_segments(members[(arc, mem)])
        for si, r in rows.items():
            kr = r["kr"]
            if not re.search("[0-9０-９]", kr):
                continue
            nums, lits = events(segs[si], cm)
            for m in re.finditer("[0-9０-９]+", kr):
                ru = m.group(0)
                half = ru.isascii()
                v = int(ru) if half else int("".join(str(FW.find(x)) for x in ru))
                sv = str(v)
                if v in nums:
                    want = "half"
                elif sv in lits or "".join(lits) == sv:
                    want = "full"
                elif nums and not lits:
                    want = "half"  # 수 그리기 둘의 합쳐 쓴 값(예: 22000+16)
                else:
                    noorig.append((mem, si))
                    want = "full"
                if (want == "half") != half:
                    bad.append(
                        f"{os.path.basename(script_kr.path_of(arc, mem))}#{si} 「{ru}」 — 원판 꼴은 {'반각' if want == 'half' else '전각'}"
                    )
    return bad, noorig


def main():
    bad, noorig = find_bad()
    print(
        f"  대사 숫자 꼴 [ps1-ed4] — 원판 꼴과 어긋남 {len(bad)} · 원판에 숫자 없는 자리 {len(noorig)} (기준 {NO_ORIG})"
    )
    for b in bad[:10]:
        print("    ✗", b)
    return 1 if bad or len(noorig) > NO_ORIG else 0


if __name__ == "__main__":
    sys.exit(main())
