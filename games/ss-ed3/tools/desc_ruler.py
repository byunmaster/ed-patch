"""설명 창의 **폭·행 수를 화면에 물어보는** 눈금자를 만든다.

원문 통계는 상한의 **하한**만 말해 준다 — 아이템 설명 284 행 중 9전각은 **1 건**뿐이라
「9 가 창 폭」인지 「원문이 9까지만 쓴 것」인지 못 가른다. 그래서 화면에 직접 묻는다.

수법은 `docs/reference/our-findings.md` 의 「창 폭·줄 수는 RAM 에 눈금자를 심어 잰다」다.
여기 몫은 **길이 보존**이라는 제약을 지키는 것 — 설명문은 NUL 로 끊긴 표라 한 조각이라도
길어지면 다음 조각을 먹는다. 조각마다 **제 길이 그대로** 전각 눈금으로 덮는다.

🔴 `＄`(개행)까지 지운다. 그래야 **화면이 스스로 답한다**:
  · 엔진이 접으면 → 창 폭에서 접힌 자리가 눈금 숫자로 읽힌다
  · 안 접으면   → 삐져나가거나 잘린 자리가 보인다

    python3 games/ss-ed3/tools/desc_ruler.py            # 페이로드 + 찾을 패턴을 낸다
    python3 games/ss-ed3/tools/desc_ruler.py --spell    # 마법 설명 쪽

쓰는 순서(emucap):
  1. `debug find_pattern` 으로 **아래 「찾을 패턴」** 을 `workraml` 에서 찾는다
     ⚠ **HWRAM 이 아니라 LWRAM 이다**(실측 2026-08-25 — `workramh` 는 0 건).
  2. 로드 베이스 = 찾은 오프셋 − 패턴의 **파일 오프셋**(아래에 같이 낸다)
  3. `write_memory(memory_type="workraml", address=베이스+영역시작, input_file=...)`
  4. 게임에서 그 창을 띄우고 스크린샷
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import common as C
import param as P

RULER = "１２３４５６７８９０"  # 전각 눈금 — 10 칸마다 자릿수가 돌아온다


def payload(b, area):
    """영역을 **길이 보존**으로 눈금 치환한 바이트열 → `(bytes, 덮은 조각 수)`."""
    seg = bytearray(b[area[0] : area[1]])
    i = n = 0
    while i < len(seg):
        e = seg.find(b"\x00", i)
        if e < 0:
            break
        if e - i >= 2:
            try:
                t = bytes(seg[i:e]).decode("shift_jis")
            except UnicodeDecodeError:
                t = None
            # ASCII 더미(`quux`·`Sentinel`)는 건드리지 않는다 — 표의 끝 표식이다.
            if t and not t.isascii():
                cells = (e - i) // 2
                seg[i:e] = "".join(RULER[k % 10] for k in range(cells)).encode("shift_jis")
                n += 1
        i = e + 1
    return bytes(seg), n


def anchor(b, area):
    """RAM 에서 로드 베이스를 잡을 **닻** → `(파일오프셋, hex패턴, 원문)`.

    영역의 **둘째** 조각을 쓴다 — 첫째는 숫자표(`零壱弐参…`)라 다른 자료와 겹칠 수 있다.
    """
    off = area[0]
    for _ in range(2):
        e = b.find(b"\x00", off)
        if _ == 0:
            off = e + 1
    e = b.find(b"\x00", off)
    raw = b[off:e]
    return off, raw.hex(), raw.decode("shift_jis")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spell", action="store_true", help="마법 설명 쪽 (기본은 아이템)")
    ap.add_argument("-o", "--out", help="페이로드를 쓸 경로 (기본 work/review/)")
    a = ap.parse_args()
    area = P.DESC_SPELL if a.spell else P.DESC_ITEM
    label = "마법" if a.spell else "아이템"

    b = P.load()
    data, n = payload(b, area)
    off, pat, txt = anchor(b, area)
    out = a.out or os.path.join(C.REVIEW_DIR, f"ruler_{'spell' if a.spell else 'item'}.bin")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(data)

    print(f"{label} 설명 {area[0]:#x}~{area[1]:#x} · 덮은 조각 {n} · {len(data):,}B")
    print(f"  페이로드  {out}")
    print(f"  찾을 패턴 {pat}   ({txt})")
    print(f"  그 파일 오프셋 {off:#x}   → 로드 베이스 = 찾은주소 − {off:#x}")
    print(f"  쓸 주소   베이스 + {area[0]:#x}")
    # ⚠ 한 번에 쓸 수 있는 상한을 넘으면 나눠 써야 한다 — 지금은 넉넉하다.
    if len(data) > 16384:
        print("  ⚠ write_memory 상한(16,384B)을 넘는다 — 나눠 써라")


if __name__ == "__main__":
    main()
