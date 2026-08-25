"""테스트 이미지를 굽는다 — 폰트 교체 + 문안 재삽입 + 무결성 재계산.

    python3 games/ss-ed3/tools/build.py            # disc1
    python3 games/ss-ed3/tools/build.py --disc 2

🔴 **실패한 빌드는 산출물을 무효화한다** — 남은 낡은 이미지를 정상으로 오해하고 조사하면
   엉뚱한 결론이 나온다(이 레포가 실제로 겪은 사고). 실패하면 `*.failed` 로 리네임한다.

🔴 **무변경 구간을 선언하고 원본과 byte 대조한다** — 우리가 건드린다고 선언한 파일 말고는
   **한 바이트도 안 달라야** 한다. 클리어 범위를 잘못 잡아 남의 자료를 지우는 사고를 잡는다.

⚠ **원본은 읽기 전용이다.** 사본을 만들어 그 사본만 고친다.
⚠ **2디스크 계약** — 배포하려면 두 장에 같은 문안을 넣어야 한다(`common.check_discs`).
   지금은 확인용이라 한 장씩 굽는다.
"""

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
import build_font
import common as C
import hangul_map as H
import reinsert as R
import reinsert_book as RB
import reinsert_desc as RD
import reinsert_sys as RS

from shared.disc import mode1

# 우리가 건드린다고 선언한 것 — 이 밖은 원본과 바이트 동일해야 한다
TOUCHED = ("/SYSTEM/KANJI12.FON",)


def out_paths(disc):
    name = f"Shiroki Majo (KR) (Disc {disc})"
    return os.path.join(C.BUILD_DIR, name + ".bin"), os.path.join(C.BUILD_DIR, name + ".cue")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", type=int, default=None, choices=C.DISCS, help="한 장만 (기본: 두 장)")
    a = ap.parse_args()

    # 🔴 **두 장이 기본이다.** 게임 데이터가 같은 한 벌이라(`common.check_discs`) 문안도 한
    #    벌인데, 한 장만 구우면 **디스크를 갈아 끼우는 순간 원문으로 돌아간다.** 확인용으로
    #    한 장만 굽고 싶으면 `--disc` 로 **명시**한다.
    for disc in ([a.disc] if a.disc else list(C.DISCS)):
        build_one(disc)


def build_one(a_disc):
    a = argparse.Namespace(disc=a_disc)
    print(f"\n── disc{a.disc}")
    C.verify_source(a.disc)
    os.makedirs(C.BUILD_DIR, exist_ok=True)
    dst, cue = out_paths(a.disc)
    ok = False
    try:
        print(f"[1/5] 원본 사본 → {os.path.basename(dst)}")
        shutil.copyfile(C.DISC_BIN[a.disc], dst)

        print("[2/5] 폰트 — 한글 글리프 주입")
        fon, missing = build_font.build(a.disc)
        if missing:
            raise SystemExit(f"글리프가 없는 글자 {len(missing)}: {''.join(missing[:20])}")

        table = H.load()
        touched_lbas = []
        with C.open_disc(a.disc) as d, open(dst, "r+b") as f:
            files = d.files()
            for name, lba, size in files:
                if name == "/SYSTEM/KANJI12.FON":
                    assert len(fon) == size, (len(fon), size)
                    mode1.write_at(f, lba, size, 0, fon, label=name)
                    touched_lbas.append((name, lba, size))

            print("[3/5] 문안 재삽입 (길이 보존)")
            done = nsys = ndesc = nbook = 0
            systbl = RS.table()
            desctbl = RD.table()
            for name, lba, size in files:
                b = None
                if name.startswith("/MAP/") and name.endswith(".BIN"):
                    stem = os.path.basename(name).rsplit(".", 1)[0]
                    if not R.load_script(stem):
                        continue
                    b = d.read_extent(lba, size)
                    new, k, bad = R.patch_blocks(b, stem, table)
                    done += k
                elif name == "/0.BIN" and systbl:
                    b = d.read_extent(lba, size)
                    new, k, bad = RS.patch(b, name, systbl)
                    nsys += k
                elif name.startswith("/SYSTEM/BOOK") and name.endswith(".BIN"):
                    stem = os.path.basename(name)[:-4]
                    booktbl = RB.table(stem)
                    if not booktbl:
                        continue
                    b = d.read_extent(lba, size)
                    new, k, bad = RB.patch(b, stem, booktbl, table)
                    nbook += k
                elif name == "/SYSTEM/PARAM.BIN" and desctbl:
                    b = d.read_extent(lba, size)
                    new, k, bad = RD.patch(b, table, desctbl)
                    ndesc += k
                else:
                    continue
                if bad:
                    raise SystemExit(f"{name}: {bad[:3]}")
                assert len(new) == size, (len(new), size)
                if new != b:
                    mode1.write_at(f, lba, size, 0, new, label=name, expect=b)
                    touched_lbas.append((name, lba, size))
            print(f"      대사 블록 {done} · 시스템 문자열 {nsys} · 설명문 {ndesc} · 읽을거리 {nbook}")

        print("[4/5] 섹터 무결성 자기검증")
        bad = mode1.selftest(dst, lbas=[l for _, l, _ in touched_lbas] or [16])
        if bad:
            raise SystemExit(f"EDC/ECC 불일치: {bad[:5]}")

        print("[5/5] 무변경 구간 대조 (선언한 파일 밖은 원본과 동일해야 한다)")
        diff = compare(C.DISC_BIN[a.disc], dst, touched_lbas)
        if diff:
            raise SystemExit(f"건드린다고 선언 안 한 자리가 바뀌었다: {diff[:5]}")

        with open(cue, "w", encoding="utf-8") as f:
            f.write(
                f'FILE "{os.path.basename(dst)}" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n'
            )
        ok = True
        print(f"\n✅ {dst}")
    finally:
        if not ok and os.path.exists(dst):
            os.replace(dst, dst + ".failed")
            print(f"\n❌ 빌드 실패 — 산출물을 무효화했다: {os.path.basename(dst)}.failed")


def compare(src, dst, touched, chunk=1 << 22):
    """선언한 파일이 차지하는 섹터 **밖**에서 바이트가 달라진 자리."""
    from shared.disc.iso9660 import SECTOR, USER_SIZE

    allow = set()
    for _, lba, size in touched:
        for i in range((size + USER_SIZE - 1) // USER_SIZE):
            allow.add(lba + i)
    out = []
    with open(src, "rb") as a, open(dst, "rb") as b:
        off = 0
        while True:
            x, y = a.read(chunk), b.read(chunk)
            if not x:
                break
            if x != y:
                for i in range(len(x)):
                    if x[i] != y[i] and (off + i) // SECTOR not in allow:
                        out.append(hex(off + i))
                        if len(out) > 8:
                            return out
            off += len(x)
    return out


if __name__ == "__main__":
    main()
