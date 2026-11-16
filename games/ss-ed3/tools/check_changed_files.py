#!/usr/bin/env python3
"""**원판 대비 바뀐 파일 전수 감사** — 구운 이미지에서 원판과 바이트가 다른 파일이 **선언한 집합**(`changed_files_allow.json`) 안인가.

    python3 games/ss-ed3/tools/check_changed_files.py            # 감사(목록에 없는 변경 → rc 1)
    python3 games/ss-ed3/tools/check_changed_files.py --freeze   # 지금 집합을 선언으로(래칫 아님 — 사유를 손으로 단다)

🔴 왜: 「이미지 전체에서 포인터 바이트 패턴을 찾아 바꾸는」 재배치는 우연히 같은 바이트를 가진 음악·팔레트·그래픽·이벤트 데이터까지 고쳐
   제품만 멈춘다(SFC II 11-07 실제 프리징). 이 게임의 빌드는 **파일 이름별 패처**(`build.py` 의 `elif name == …`)라 전체 검색·치환이 없고,
   안 매칭된 파일은 `continue` 로 건드리지 않는다 — 그걸 **결과 쪽에서 한 번 더** 확인한다(새 패처가 선언 없이 파일을 건드리면 여기서 걸린다).
   파일 안의 바뀐 구간은 `check_structure`(구조 대조 · 포인터표 · 제어 바이트 보호) · `check_build_discs`(무변경 구간)가 본다.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import check_build_discs as B
import common as C

ALLOW = os.path.join(C.GAME_DIR, "changed_files_allow.json")


def changed(disc=1):
    img = build.out_paths(disc)[0]
    if not os.path.exists(img):
        return None
    files = {n: (lba, size) for n, lba, size, *_ in build.patched(disc)}
    out = {}
    with C.open_disc(disc) as d:
        for n, lba, size in d.files():
            if n not in files:
                continue
            o = d.read_extent(lba, size)
            g = B.read_extent(img, *files[n])
            if o != g:
                out[n] = sum(1 for a, b in zip(o, g) if a != b) + abs(len(o) - len(g))
    return out


def main():
    got = {}
    for disc in (1, 2):
        r = changed(disc)
        if r is None:
            print(f"  ⓘ 바뀐 파일 감사는 못 쟀다 — disc{disc} 빌드 이미지가 없다")
            return 0
        got.update({f"d{disc}:{n}": v for n, v in r.items()})
    if "--freeze" in sys.argv:
        with open(ALLOW, "w", encoding="utf-8") as fh:
            json.dump({"_why": "원판 대비 바뀐 파일 선언(11-08) — 새 파일이 늘면 사유와 함께 여기 올린다", "allow": sorted(got)}, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        print(f"  선언 {len(got)} 파일")
        return 0
    allow = set(json.load(open(ALLOW, encoding="utf-8"))["allow"]) if os.path.exists(ALLOW) else set()
    new = sorted(set(got) - allow)
    gone = sorted(allow - set(got))
    print(f"  원판 대비 바뀐 파일 감사 — 바뀐 {len(got)} · 선언 {len(allow)} · 선언 밖 {len(new)}")
    for n in new[:15]:
        print(f"    ❌ 선언 없이 바뀐 파일 {n} ({got[n]}B)")
    for n in gone[:5]:
        print(f"    ⓘ 선언했으나 안 바뀐 파일 {n}")
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
