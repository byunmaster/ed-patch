"""**QA 전용** — 읽을거리 한 권을 「손에 드는 책」 자리에 끼워 인게임에서 본다.

🔴 **소지할 수 있는 책은 열셋이다**(`PARAM.BIN` 아이템 표 실측). 「독서」 메뉴는 그
   **아이템 목록**이다(오른쪽 숫자가 개수다):

       38 ハックの手帳 → BOOK27 · 86 Ｈな本 · 87 巡礼者のこころえ → BOOK24
       108~115 サフィー 第2~9巻 → BOOK05~12 · 119 サフィー 第1巻 → BOOK04
       116~118 剣士教本 その1~3 → BOOK21~23

   ⚠ **처음엔 「셋뿐」으로 잘못 셌다**(2026-09-03) — `教本`·`剣士`·`本`·`書` 로 훑는 바람에
     가타카나(`サフィー`)·고유어(`こころえ`·`手帳`) 이름을 통째로 놓쳤다. 표는 **눈으로
     전수**를 봐야 한다.
   나머지 25 권은 책장 앞에서 그 자리에서 읽는 것이라 소지 플래그가 없다.
   ⇒ 그래서 **자리를 빌린다.** 가진 책의 칸에 다른 책의 바이트를 넣으면, 그 책을 펴는
     순간 넣은 책이 나온다.
   💡 **칸이 클수록 많이 들어간다** — 검사교본Ⅰ 6,270B 로 27 권, `巡礼者のこころえ`
     33,422B 로 32 권. 남는 6 권(기념 노트 2 · mona 2 · 순례자 명부 2)은 37K~72K 라
     어느 칸보다도 크다.

되는 이유는 **책 파일의 포인터가 파일 상대**이기 때문이다(`strtab.load_base` 가 BOOK 에
0 을 준다). 그래서 통째로 갈아 끼워도 문자열·그림이 제자리를 찾는다. 남는 뒤쪽은 0 으로
채운다 — 파일 크기는 ISO 가 정하므로 **더 작은 책만** 들어간다.

⚠ **이건 배포물이 아니다.** 갈아 끼우면 `check.sh` 가 「구워 둔 이미지가 낡았다」고 운다 —
  그게 정상이고 안전장치다. 확인이 끝나면 `--restore`, 아니면 다시 굽는다.

    python3 games/ss-ed3/tools/book_swap.py --list
    python3 games/ss-ed3/tools/book_swap.py BOOK04          # 검사교본Ⅰ 자리에 여검사 사피Ⅰ
    python3 games/ss-ed3/tools/book_swap.py BOOK13 --slot BOOK24   # 큰 책은 큰 칸으로
    python3 games/ss-ed3/tools/book_swap.py --restore
"""

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))

import common as C

from shared.disc import mode1

#   손에 들 수 있는 책 — 이 자리만 「독서」 메뉴에 뜬다. ⚠ **세이브가 가진 것**이어야 한다
SLOTS = {
    "BOOK04": "여검사 사피Ⅰ",
    "BOOK05": "여검사 사피Ⅱ",
    "BOOK06": "여검사 사피Ⅲ",
    "BOOK07": "여검사 사피Ⅳ",
    "BOOK08": "여검사 사피Ⅴ",
    "BOOK09": "여검사 사피Ⅵ",
    "BOOK10": "여검사 사피Ⅶ",
    "BOOK11": "여검사 사피Ⅷ",
    "BOOK12": "여검사 사피Ⅸ",
    "BOOK21": "검사교본Ⅰ",
    "BOOK22": "검사교본Ⅱ",
    "BOOK23": "검사교본Ⅲ",
    "BOOK24": "순례자의 마음가짐",  # 33,422B — 제일 큰 칸이다
    "BOOK27": "허크의 수첩",
}
BACKUP = os.path.join(C.REVIEW_DIR, "book_swap")


def image(disc=1):
    p = os.path.join(C.BUILD_DIR, f"Shiroki Majo (KR) (Disc {disc}).bin")
    if not os.path.exists(p):
        raise SystemExit(f"구운 이미지가 없다: {p}\n  먼저 `python3 games/ss-ed3/tools/build.py`")
    return p


def extents(path):
    d = C.Disc(path, user_off=C.USER_OFF)
    return {n: (lba, size) for n, lba, size in d.files() if n.startswith("/SYSTEM/BOOK")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?", help="끼울 책 (BOOK04 …)")
    ap.add_argument("--slot", default="BOOK21", choices=sorted(SLOTS), help="빌릴 자리")
    ap.add_argument("--restore", action="store_true", help="원래 책으로 되돌린다")
    ap.add_argument("--list", action="store_true", help="들어갈 수 있는 책")
    a = ap.parse_args()

    img = image()
    ex = extents(img)
    slot_key = f"/SYSTEM/{a.slot}.BIN"
    slot_lba, slot_size = ex[slot_key]
    os.makedirs(BACKUP, exist_ok=True)
    orig = os.path.join(BACKUP, f"{a.slot}.orig")

    if a.list:
        fits = [
            (os.path.basename(n)[:-4], s)
            for n, (_l, s) in sorted(ex.items())
            if s <= slot_size and n != slot_key
        ]
        print(f"{a.slot}({SLOTS[a.slot]}) 칸 {slot_size:,}B — 들어가는 책 {len(fits)}")
        for stem, s in fits:
            print(f"  {stem}  {s:,}B")
        return 0

    d = C.Disc(img, user_off=C.USER_OFF)
    if a.restore:
        if not os.path.exists(orig):
            raise SystemExit(f"되돌릴 백업이 없다: {orig}")
        with open(orig, "rb") as fh:
            data = fh.read()
        with open(img, "r+b") as f:
            mode1.write_at(f, slot_lba, slot_size, 0, data, label=slot_key)
        print(f"✅ {a.slot} 을 원래 책으로 되돌렸다 ({len(data):,}B)")
        return 0

    if not a.book:
        raise SystemExit("끼울 책을 준다 — `book_swap.py BOOK04` (목록은 `--list`)")
    src_key = f"/SYSTEM/{a.book}.BIN"
    if src_key not in ex:
        raise SystemExit(f"그런 책이 없다: {a.book}")
    src_lba, src_size = ex[src_key]
    if src_size > slot_size:
        raise SystemExit(f"{a.book} 은 {src_size:,}B 라 {a.slot} 칸 {slot_size:,}B 에 안 들어간다")

    #   ⚠ **백업은 한 번만** — 이미 갈아 끼운 것을 백업하면 원본을 영영 잃는다
    if not os.path.exists(orig):
        with open(orig, "wb") as fh:
            fh.write(d.read_extent(slot_lba, slot_size))
        print(f"   원래 책을 떠 뒀다 → {orig}")

    data = d.read_extent(src_lba, src_size) + b"\x00" * (slot_size - src_size)
    with open(img, "r+b") as f:
        mode1.write_at(f, slot_lba, slot_size, 0, data, label=slot_key)
    print(f"✅ {a.slot}({SLOTS[a.slot]}) 자리에 {a.book} 을 넣었다 — 인게임에서 그 책을 편다")
    print("   ⚠ QA 전용이다. `check.sh` 가 「낡았다」고 우는 게 정상 — 끝나면 `--restore`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
