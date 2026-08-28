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
import glob
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
import reinsert_gfx as RG
import reinsert_param as RP
import reinsert_sys as RS

from shared.disc import mode1

# 우리가 건드린다고 선언한 것 — 이 밖은 원본과 바이트 동일해야 한다
TOUCHED = ("/SYSTEM/KANJI12.FON", "/SYSTEM/ASCII.FON")


def out_paths(disc):
    name = f"Shiroki Majo (KR) (Disc {disc})"
    return os.path.join(C.BUILD_DIR, name + ".bin"), os.path.join(C.BUILD_DIR, name + ".cue")


def track_path(disc, n):
    """트랙 1 은 우리가 구운 `.bin`, 나머지는 원본을 그대로 옮겨 놓은 사본."""
    return (
        out_paths(disc)[0]
        if n == 1
        else os.path.join(C.BUILD_DIR, f"Shiroki Majo (KR) (Disc {disc}) (Track {n}).bin")
    )


def write_cue(disc):
    """🔴 **트랙을 전부 적는다.** 트랙 1 만 적던 것을 2026-08-28 고쳤다 —
    disc2 는 **ISO 가 트랙 1 을 넘어가서**(파일 18 개: `END00~16.GRP` · `V20.SAP`)
    트랙 2 를 빼면 **엔딩 그림과 그 음성이 통째로 없다.** 타이틀·초반만 봐서 안 드러났다.
    ⓘ 인덱스는 원본 `.cue` 규약을 따른다 — 데이터 트랙은 `INDEX 01` 하나,
      뒤따르는 트랙은 `INDEX 00`(프리갭) + `INDEX 01`.
    """
    lines = []
    for n, mode, _src in C.disc_tracks(disc):
        lines.append(f'FILE "{os.path.basename(track_path(disc, n))}" BINARY')
        lines.append(f"  TRACK {n:02d} {mode}")
        if n == 1:
            lines.append("    INDEX 01 00:00:00")
        else:
            lines.append("    INDEX 00 00:00:00")
            lines.append("    INDEX 01 00:0{}:00".format(3 if mode.startswith("MODE") else 2))
    with open(out_paths(disc)[1], "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def copy_extra_tracks(disc):
    """트랙 2 이후를 빌드 칸에 그대로 복사한다 — `(옮긴 수, 바이트)`.

    ⚠ **하드링크·심볼릭 링크로 때우지 않는다.** originals 는 어떤 트랙에서도 읽기 전용인데,
      링크를 걸면 빌드 칸에 쓰는 실수 하나가 **원본을 망친다**(루트 「originals」).
    ⓘ 이미 있고 크기가 같으면 건너뛴다 — 다시 구울 때 159MB 를 매번 복사하지 않는다.
    """
    n = b = 0
    for num, _mode, src in C.disc_tracks(disc):
        if num == 1:
            continue
        dst = track_path(disc, num)
        size = os.path.getsize(src)
        if os.path.exists(dst) and os.path.getsize(dst) == size:
            continue
        shutil.copyfile(src, dst)
        n += 1
        b += size
    return n, b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", type=int, default=None, choices=C.DISCS, help="한 장만 (기본: 두 장)")
    a = ap.parse_args()

    # 🔴 **두 장이 기본이다.** 게임 데이터가 같은 한 벌이라(`common.check_discs`) 문안도 한
    #    벌인데, 한 장만 구우면 **디스크를 갈아 끼우는 순간 원문으로 돌아간다.** 확인용으로
    #    한 장만 굽고 싶으면 `--disc` 로 **명시**한다.
    for disc in [a.disc] if a.disc else list(C.DISCS):
        build_one(disc)


def patched(disc):
    """이 소스가 만드는 **그 디스크의 패치 결과 전량** — `(이름, lba, size, 원본, 새것, {갈래: 수})`.

    🔴 **빌드와 검사기가 같은 코드를 쓰게 하려고 뺐다.** 갈래를 양쪽에 따로 적어 두면
    둘이 조용히 어긋나고, 그러면 검사기가 「빌드가 맞다」고 보증하는 뜻이 없어진다.
    ⓘ 폰트는 통째로 갈아 끼우므로 **원본을 안 읽는다**(`원본 is None` 이 그 표식이다).
    """
    fon, missing = build_font.build(disc)
    if missing:
        raise SystemExit(f"글리프가 없는 글자 {len(missing)}: {''.join(missing[:20])}")
    asc, npad = build_font.build_ascii(disc)
    table = H.load()
    systbl, desctbl, paramtbl = RS.table(), RD.table(), RP.table()

    with C.open_disc(disc) as d:
        files = d.files()
        for name, lba, size in files:
            if name == "/SYSTEM/KANJI12.FON":
                assert len(fon) == size, (len(fon), size)
                yield name, lba, size, None, fon, {}
            elif name == "/SYSTEM/ASCII.FON":
                assert len(asc) == size, (len(asc), size)
                yield name, lba, size, None, asc, {"ascii": npad}

        for name, lba, size in files:
            b = None
            if C.is_map_file(name)[0]:
                stem = C.is_map_file(name)[1]
                if not R.load_script(stem)[0]:
                    continue
                b = d.read_extent(lba, size)
                new, k, bad = R.patch_blocks(b, stem, table)
                cnt = {"map": k}
            elif name in ("/0.BIN", "/RLTPRG.BIN", "/BLACK.BIN") and systbl:
                #   🔴 **미니게임 실행 파일에도 화면 문구가 있다**(실측 2026-08-28) —
                #     `/RLTPRG.BIN`(룰렛) 「当たったー/どんなもんだい！！」 ·
                #     `/BLACK.BIN`(블랙잭) 「ブラックジャックを終了しますか？」.
                #     `/0.BIN` 만 고치고 있어 여태 일본어로 남아 있었다.
                #   ⓘ `reinsert_sys` 의 **원바이트 폴백**이 `LOAD_BASE` 없는 파일도 받는다.
                b = d.read_extent(lba, size)
                new, k, bad = RS.patch(b, name, systbl)
                cnt = {"sys": k}
            elif name.startswith("/SYSTEM/BOOK") and name.endswith(".BIN"):
                stem = os.path.basename(name)[:-4]
                booktbl = RB.table(stem)
                if not booktbl:
                    continue
                b = d.read_extent(lba, size)
                new, k, bad = RB.patch(b, stem, booktbl, table)
                cnt = {"book": k}
            elif name == RG.TARGETS[0][0]:
                b = d.read_extent(lba, size)
                new, _ = RG.apply(b)
                bad, cnt = [], {"gfx": 1 if new != b else 0}
            elif name == "/SYSTEM/PARAM.BIN":
                #   ⚠ 한 파일에 **설명문과 이름 표**가 같이 있다 — 둘을 이어서 넣는다.
                #     이름 표가 빠져 있어 장비창에 일본어가 떴다(2026-08-27 유저 실측).
                b = d.read_extent(lba, size)
                new, k, bad = (b, 0, []) if not desctbl else RD.patch(b, table, desctbl)
                new, k2, bad2 = RP.patch(new, None, paramtbl)
                bad = bad + bad2
                cnt = {"desc": k, "name": k2}
            else:
                continue
            if bad:
                raise SystemExit(f"{name}: {bad[:3]}")
            assert len(new) == size, (len(new), size)
            yield name, lba, size, b, new, cnt


def build_one(a_disc):
    a = argparse.Namespace(disc=a_disc)
    print(f"\n── disc{a.disc}")
    C.verify_source(a.disc)
    os.makedirs(C.BUILD_DIR, exist_ok=True)
    dst, cue = out_paths(a.disc)
    # 🔴 **지난 실패 표식은 빌드를 **시작할 때** 지운다.** 안 지우면 한 번 실패한 칸은
    #    그 뒤 성공해도 `.failed` 가 남고, `scripts/pull-build.sh` 가 **그 칸을 통째로
    #    거부한다**(정상 이미지가 있는데도). 유저 실측 2026-08-27.
    #    ⚠ 「성공했을 때 지운다」가 아니라 **시작할 때**다 — 빌드가 중간에 죽으면(예외·
    #    Ctrl-C) 성공 시점을 못 밟아 표식이 또 남는다. 시작에 지워야 「이 칸의 `.failed` 는
    #    **직전 빌드의 결과만** 뜻한다」가 불변식으로 선다. ps1-ed1+2 의 규약과 같다.
    for stale in glob.glob(os.path.join(C.BUILD_DIR, "*.failed")):
        os.remove(stale)
    ok = False
    try:
        print(f"[1/5] 원본 사본 → {os.path.basename(dst)}")
        shutil.copyfile(C.DISC_BIN[a.disc], dst)

        print("[2/5] 폰트 — 한글 글리프 주입 + 반각 부호 여백")
        touched_lbas = []
        n = {}
        stage = "font"
        with open(dst, "r+b") as f:
            for name, lba, size, old, new, cnt in patched(a.disc):
                for kind, k in cnt.items():
                    n[kind] = n.get(kind, 0) + k
                if "ascii" in cnt:
                    print(f"      반각 여백 {cnt['ascii']}자 ({''.join(build_font.ASCII_PAD)})")
                if stage == "font" and old is not None:
                    stage = "text"
                    print("[3/5] 문안 재삽입 (길이 보존)")
                if old is None:  # 폰트 — 통째로 갈아 끼운다
                    mode1.write_at(f, lba, size, 0, new, label=name)
                    touched_lbas.append((name, lba, size))
                elif new != old:
                    mode1.write_at(f, lba, size, 0, new, label=name, expect=old)
                    touched_lbas.append((name, lba, size))
            print(
                f"      대사 블록 {n.get('map', 0)} · 시스템 문자열 {n.get('sys', 0)} · "
                f"설명문 {n.get('desc', 0)} · 이름 {n.get('name', 0)} · "
                f"읽을거리 {n.get('book', 0)} · 화면 그림 {n.get('gfx', 0)}"
            )

        print("[4/5] 섹터 무결성 자기검증")
        bad = mode1.selftest(dst, lbas=[l for _, l, _ in touched_lbas] or [16])
        if bad:
            raise SystemExit(f"EDC/ECC 불일치: {bad[:5]}")

        print("[5/5] 무변경 구간 대조 (선언한 파일 밖은 원본과 동일해야 한다)")
        diff = compare(C.DISC_BIN[a.disc], dst, touched_lbas)
        if diff:
            raise SystemExit(f"건드린다고 선언 안 한 자리가 바뀌었다: {diff[:5]}")

        nt, nb = copy_extra_tracks(a.disc)
        if nt:
            print(f"      트랙 {nt} 개를 옮겼다 ({nb / 1e6:.0f}MB) — 트랙1 밖의 파일이 여기 있다")
        write_cue(a.disc)
        write_m3u()
        ok = True
        print(f"\n✅ {dst}")
    finally:
        if not ok:
            #   ⚠ `.bin` 만 무효화하면 **`.cue`·`.m3u` 가 살아남는다** — 에뮬에 그걸 물리면
            #     「이미지가 없다」로 죽으니 조용히 틀리진 않지만, 칸에 성공물과 실패물이
            #     섞여 `pull-build.sh` 가 그 칸을 정상으로 센다. **남아 있는 건 전부 성공한
            #     산출물**이어야 규율이 선다. 둘 다 지운다(성공하면 다시 만든다).
            if os.path.exists(dst):
                os.replace(dst, dst + ".failed")
                print(f"\n❌ 빌드 실패 — 산출물을 무효화했다: {os.path.basename(dst)}.failed")
            for gone in (cue, m3u_path()):
                if os.path.exists(gone):
                    os.remove(gone)
            #   ⚠ 딸린 트랙 사본도 같이 치운다 — `.cue` 가 없으면 쓸 데가 없고, 남겨 두면
            #     실패한 칸이 정상 크기로 보인다.
            for num, _m, _s in C.disc_tracks(a.disc)[1:]:
                q = track_path(a.disc, num)
                if os.path.exists(q):
                    os.remove(q)


def m3u_path():
    return os.path.join(
        C.BUILD_DIR, f"{C.TITLE_KR}.m3u" if hasattr(C, "TITLE_KR") else "Shiroki Majo (KR).m3u"
    )


def write_m3u():
    """두 장이 다 구워져 있으면 `.m3u` 로 묶는다 — **에뮬에서 한 파일로 연다.**

    ⚠ 새턴 게임은 디스크를 갈아 끼워야 하는데(제2장 이후가 디스크2 다), `.m3u` 로 묶으면
    에뮬이 두 장을 한 묶음으로 알아 **교체가 에뮬 안에서** 된다(mednafen 1.32 확인).
    ⓘ `chd` 는 mednafen 이 안 받는다 — 받는 건 `cue`·`ccd`·`toc`·`m3u` 넷이다.
    """
    cues = [out_paths(d)[1] for d in C.DISCS]
    if not all(os.path.exists(c) for c in cues):
        return
    path = m3u_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(os.path.basename(c) + "\n" for c in cues))
    print(f"      두 장을 묶었다 → {os.path.basename(path)}")


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
