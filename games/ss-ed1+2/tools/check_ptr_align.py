"""**우리가 옮긴 문자열이 짝수 주소에 있나** — 두 바이트를 한 글자로 고정해 읽는 화면이 있다.

    python3 tools/check_ptr_align.py      # 홀수가 하나라도 있으면 종료코드 1

## 왜 이 검사가 있나

이 게임의 어떤 화면은 **SJIS 선행 바이트를 안 본다** — 두 바이트를 무조건 한 글자로 읽는다
(필드 HUD 의 지명이 그렇다). 그래서 우리가 문자열을 **홀수 주소**로 옮기면 그 화면에서만
통째로 반 칸씩 밀려 깨진다.

🔴 **제일 나쁜 건 「거기서만」이다.** 메뉴·대사는 선행 바이트를 보므로 멀쩡하고, 되읽기도
   통과한다(우리 되읽기 역시 선행 바이트를 본다). 화면 하나만 조용히 깨진 채로 남는다.
   실측 2026-08-28: `엘아스타` 가 `0x2C6A1` 에 놓였고 그 포인터가 HUD 조립 루틴의 리터럴
   풀(0x44E6C)에 있었다 — 화면엔 `ッ니日_처` 가 떴다. 홀수는 문안에 **반각이 섞이면**
   자연히 생긴다(`전투 직전으로` = 13B).

## 무엇을 보나

원본과 빌드를 대조해 **값이 바뀐 BE32 포인터**를 전부 모으고, 그 대상 오프셋이 짝수인지 본다.
어느 패처가 옮겼는지는 안 따진다 — 배치기가 셋이라(`patch_ui` · `patch_scn` ·
`patch_mon_names`) **결과를 보는 쪽이 맞다.**
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import patch_scn
import patch_ui


def odd_targets(mm, files, path):
    """`[(포인터 오프셋, 새 대상)]` — 옮겨졌는데 **홀수** 자리를 가리키는 것."""
    base = patch_ui.ptr_base(path)
    if base is None:
        return []
    orig = bytes(common.extract(path))
    built = bytes(common.read_extent(mm, *files[path]))
    out = []
    for q in range(0, min(len(orig), len(built)) - 3, 2):
        ov = struct.unpack(">I", orig[q : q + 4])[0]
        bv = struct.unpack(">I", built[q : q + 4])[0]
        if ov == bv:
            continue
        if not (base <= ov < base + len(orig) and base <= bv < base + len(built)):
            continue
        if (bv - base) % 2:
            out.append((q, bv - base))
    return out


def main():
    common.verify_source()
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if not os.path.exists(dst):
        raise SystemExit(f"먼저 빌드한다 — {dst} 가 없다")
    _f, mm = common.open_image(dst)
    files = {p: (lba, s) for p, lba, s in common.iso_files(mm)}
    bad, n = [], 0
    for path in files:
        if path not in ("/ED.BIN", "/ED2.BIN") and not patch_scn.SCN_RE.match(path):
            continue
        hits = odd_targets(mm, files, path)
        n += 1
        bad += [(path, q, a) for q, a in hits]
    mm.close()
    _f.close()
    if bad:
        print(f"  ❌ 홀수 주소를 가리키는 포인터 {len(bad)}곳")
        for path, q, a in bad[:10]:
            print(f"     {path} 0x{q:X} → 0x{a:X}")
        raise SystemExit("두 바이트 고정으로 읽는 화면에서 깨진다 — 배치기가 정렬을 어겼다")
    print(f"  ✅ 옮긴 문자열이 전부 짝수 주소다 ({n}파일)")


if __name__ == "__main__":
    main()
