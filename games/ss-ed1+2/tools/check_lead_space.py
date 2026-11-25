"""새 창 첫 칸 공백 대조 — 원판엔 없는데 빌드 메시지의 **창 머리**(블록 첫 글 · `%c` 뒤 첫 글)가 공백으로 시작하는 곳을 센다.

왜(2026-11-11, pce-ed1 「새 창 첫 칸 공백」 결함이 나온 뒤 전 게임 점검): 창 머리 공백은 줄 맨 앞이 한 칸 비어 보이는 결함이거나,
**키 대기 뒤 같은 줄에 이어 그려지는 블록의 읽힘 공백**(`patch_scn.key_cont_fix.cont` — 설계) · 행위자 이름 뒤 이음이다.
검사: 원판 메시지와 `ptr_at` 로 짝지어 `%c` 조각마다 머리(개행 건너뜀)를 보고, 원판엔 공백이 없는데 빌드엔 공백(0x20 · 전각)인 조각을 센다.
`%s`·`%d` 바로 뒤 `%c`(변수를 감싼 색의 닫힘)는 이름 뒤 이음이라 제외한다. 이 수가 **늘면** 실패(래칫) — 새로 생긴 곳은
`key_cont_fix` 설계(이음)인지 확인해 `KNOWN` 을 올린다. 조각 수가 달라진 메시지(쪽 가르기 등)는 비교에서 빠진다.
"""

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_ctrl_codes as C
import common

KNOWN = 44  # 2026-11-11 전수 — 29 = 키 대기 이음 공백(`key_cont.json` 열쇠 있음, `key_cont_fix.cont` 설계) · 15 = 창 머리가 아니라 행위자 이름·색 낱말 뒤 어절 사이 공백(로그 이음 · 「…%c 10%c 올랐다」)


def heads(raw):
    out = []
    parts = raw.split(b"%c")
    for i, p in enumerate(parts):
        if i > 0 and parts[i - 1].endswith((b"%s", b"%d")):
            continue
        out.append(p.lstrip(b"\n")[:2])
    return out


def sp(h):
    return h[:1] == b" " or h[:2] == b"\x81\x40"


def main():
    built = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    orig, new = C._load(common.ORIG_BIN), C._load(built)
    cnt = collections.Counter()
    show = []
    for p, od in orig.items():
        bm = {tuple(e["ptr_at"]): e for e in new.get(p, {"entries": []})["entries"]}
        for e in od["entries"]:
            be = bm.get(tuple(e["ptr_at"]))
            if not be:
                continue
            ho, hn = heads(bytes.fromhex(e["raw_hex"])), heads(bytes.fromhex(be["raw_hex"]))
            if len(ho) != len(hn):
                continue
            for a, b in zip(ho, hn):
                if sp(b) and not sp(a):
                    cnt["새로"] += 1
                    show.append((p, e["entry_id"]))
    print(f"  첫 칸 공백 대조 — 원판엔 없고 빌드 창 머리에 생긴 공백 {cnt['새로']}(알려진 {KNOWN} — 키 대기 이음)")
    if cnt["새로"] > KNOWN:
        print(f"    ❌ 알려진 수보다 늘었다 — 이음(`key_cont_fix`)인지 확인한다: {show[:10]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
