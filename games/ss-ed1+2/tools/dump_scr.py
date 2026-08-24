"""`SCR*.2D` — 인게임 화면 그래픽(챕터 판 · HUD 패널 · 프레임)을 뜯는다.

🔴 **HUD 의 인명·`あと`·하단 챕터 판은 문자열이 아니라 그림이다.** 문자열을 다 고치고도
   화면이 안 바뀌어서 알았다(2026-08-24) — 디스크 어디에도 그 낱말의 SJIS 가 없고 실행 중
   RAM 에도 없다. 전부 여기 들어 있다.

## 파일 꼴 (실측)

    0x00  "SEGA SATURN SCR\\0"
    0x20~ 구획 표 — 16B 씩 `[오프셋 BE32][크기 BE32][0 8B]`, 네 칸

    구획0  패턴 네임 테이블 : 16B 머리 + 64×64 × BE16
    구획1  문자 데이터      : 16B 머리 + **4bpp · 8×16 문자**(8×8 셀 둘을 세로로)
    구획2  팔레트           : 16B 머리 + 256색 RGB555 BE (⚠ **R 이 하위 5비트**)
    구획3  0 으로 찬 칸     : 미사용

⚠ **4bpp 다.** 8bpp 로 읽어도 글자가 읽혀서 한참 속았다 — 가로가 절반으로 눌릴 뿐이라
  「읽히니까 맞겠지」로 넘어가기 쉽다. 패턴 색인이 **2씩 뛴다**는 게 단서였다(문자 하나가
  셀 둘). 확증은 조립해서 「Dragon Slayer」 워터마크가 제대로 읽히는지로 했다.
⚠ 그래서 **8bpp 셀 하나(64B)와 4bpp 문자 하나가 같은 64B** 다 — 색인이 우연히 일치한다.

## 어디에 뭐가 있나 (SCR1 = ED1 필드 화면)

    문자   0~ 375   기본 맵이 쓰는 것 — 금색 프레임 · 우측 패널 · 판 바탕
    문자 240~1007   **챕터 판 여섯 장**(第１章…終章). 판마다 24×3 문자
    문자1008~1457   **HUD 패널** — 인명(セリオス·リュナン·ロー·ソニア·ゲイル)과
                    `Lv`·`EP`·`HP`·`MP`·`Gold` 가 **미리 합성된 채로** 들어 있다
    ⚠ 기본 맵은 238 자만 쓴다. 나머지는 게임이 **런타임에 패턴 이름을 바꿔 끼운다.**

    python3 tools/dump_scr.py            # 구획 요약
    python3 tools/dump_scr.py --sheet    # 문자 시트 PNG → work/review/scr/
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

FILES = ("/SCR1.2D", "/SCR2.2D")
MAGIC = b"SEGA SATURN SCR\x00"
SEC_TABLE = 0x20
SEC_HEAD = 16  # 각 구획 앞머리
CHAR_BYTES = 64  # 4bpp 8×16 = 8×8 셀 둘


def sections(d):
    """`[(오프셋, 크기)]` — 0 인 칸은 버린다."""
    assert d[: len(MAGIC)] == MAGIC, "SCR 시그니처가 아니다"
    out = []
    for i in range(SEC_TABLE, SEC_TABLE + 16 * 8, 16):
        off, size = struct.unpack_from(">II", d, i)
        if size:
            out.append((off, size))
    return out


def parse(d):
    """`{map, chars, palette}` — 각각 numpy 배열."""
    import numpy as np

    sec = sections(d)
    assert len(sec) >= 3, f"구획이 {len(sec)}개뿐이다"
    (mo, ms), (co, cs), (po, _ps) = sec[0], sec[1], sec[2]
    nt = np.frombuffer(d[mo + SEC_HEAD : mo + ms], ">u2")
    n = (cs - SEC_HEAD) // CHAR_BYTES
    raw = np.frombuffer(d[co + SEC_HEAD : co + SEC_HEAD + n * CHAR_BYTES], np.uint8)
    px = np.empty(raw.size * 2, np.uint8)
    px[0::2], px[1::2] = raw >> 4, raw & 15
    chars = px.reshape(n, 16, 8)  # 세로 두 셀이 이어져 8×16 이 된다
    pal = np.frombuffer(d[po + SEC_HEAD : po + SEC_HEAD + 512], ">u2").astype(np.uint32)
    rgb = np.stack([pal & 31, (pal >> 5) & 31, (pal >> 10) & 31], 1).astype(np.uint8) * 8
    return {"map": nt.reshape(64, 64), "chars": chars, "pal": rgb}


def main():
    from PIL import Image

    common.verify_source()
    _f, mm = common.open_image()
    files = {p: (lba, size) for p, lba, size in common.iso_files(mm)}
    out = os.path.join(common.REVIEW_DIR, "scr")
    for path in FILES:
        lba, size = files[path]
        d = common.read_extent(mm, lba, size)
        r = parse(d)
        used = sorted({int(v) >> 1 for v in r["map"].flatten()})
        print(f"{path} {size:,}B · 구획 {[(hex(o), s) for o, s in sections(d)]}")
        print(f"   문자 {len(r['chars'])} · 기본 맵이 쓰는 문자 {len(used)} (최대 {used[-1]})")
        if "--sheet" in sys.argv:
            import numpy as np

            os.makedirs(out, exist_ok=True)
            n = len(r["chars"])
            w = 48
            h = (n + w - 1) // w
            sheet = np.zeros((h * 16, w * 8), np.uint8)
            for i, c in enumerate(r["chars"]):
                y, x = divmod(i, w)
                sheet[y * 16 : y * 16 + 16, x * 8 : x * 8 + 8] = c
            # ⚠ 뱅크가 블록마다 달라 한 팔레트로는 다 안 보인다 — 대비만 주는 램프를 쓴다
            ramp = (np.arange(16) * 17).astype(np.uint8)
            p = os.path.join(out, os.path.basename(path).replace(".2D", "_chars.png"))
            Image.fromarray(ramp[sheet]).resize((w * 8 * 2, h * 16 * 2), Image.NEAREST).save(p)
            print(f"   → {p}")


if __name__ == "__main__":
    main()
