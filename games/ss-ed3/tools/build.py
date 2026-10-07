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
import book_cover as BCV
import build_font
import common as C
import hangul_map as H
import movie_hardsub as MV
import patch_josa_hook as JOSA
import patch_ui_center as UIC
import reinsert as R
import reinsert_battle as RBT
import reinsert_book as RB
import reinsert_desc as RD
import reinsert_gfx as RG
import reinsert_param as RP
import reinsert_sys as RS
import relocate as RL
import subtitle_stub as SS
import dev_options as DEV
import voice_credits as VC
import voice_sub as VS
import choice_tail as CT

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


def copy_extra_tracks(disc, grown=0):
    """트랙 2 이후를 빌드 칸에 복사한다 — `(옮긴 수, 바이트)`.

    ⚠ **하드링크·심볼릭 링크로 때우지 않는다.** originals 는 어떤 트랙에서도 읽기 전용인데,
      링크를 걸면 빌드 칸에 쓰는 실수 하나가 **원본을 망친다**(루트 「originals」).
    ⓘ 이미 있고 크기가 같으면 건너뛴다 — 다시 구울 때 159MB 를 매번 복사하지 않는다.
    🔴 트랙 1 이 `grown` 섹터 늘었으면 **데이터 트랙은 섹터 헤더를 그만큼 민 사본**이다
      (`relocate.shift_track`) — 그건 매번 다시 쓴다(크기로는 못 가른다).
    """
    n = b = 0
    for num, mode, src in C.disc_tracks(disc):
        if num == 1:
            continue
        dst = track_path(disc, num)
        size = os.path.getsize(src)
        shifted = grown and mode.startswith("MODE")
        if not shifted and os.path.exists(dst) and os.path.getsize(dst) == size:
            continue
        if shifted:
            RL.shift_track(src, dst, grown)
        else:
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


def patched(disc, lay=None):
    """이 소스가 만드는 **그 디스크의 패치 결과 전량** — `(이름, lba, size, 원본, 새것, {갈래: 수})`.

    🔴 **빌드와 검사기가 같은 코드를 쓰게 하려고 뺐다.** 갈래를 양쪽에 따로 적어 두면
    둘이 조용히 어긋나고, 그러면 검사기가 「빌드가 맞다」고 보증하는 뜻이 없어진다.
    ⓘ 폰트는 통째로 갈아 끼우므로 **원본을 안 읽는다**(`원본 is None` 이 그 표식이다).
    ⓘ 음성 자막이 든 맵은 **트랙 1 끝의 새 자리**로 나온다(`relocate.Layout` — `lay` 를
      주면 부르는 쪽이 얼마나 늘었는지 본다). 그 자리의 「원본」은 빈 섹터(0)다.
    """
    lay = lay or RL.Layout(disc)
    fon, missing = build_font.build(disc)
    if missing:
        raise SystemExit(f"글리프가 없는 글자 {len(missing)}: {''.join(missing[:20])}")
    asc, npad = build_font.build_ascii(disc)
    table = H.load()
    #   🔴 **책만 다른 글리프 칸을 쓴다** — 책 화면이 12 열을 8 열로 더해 그려서, 칸을 꽉
    #     채우는 글꼴은 획 사이 틈이 먼저 사라진다(`hangul_map.BOOK_PATH` 주석).
    #     배정이 없으면 본 배정 그대로다.
    booktable = H.load_book()
    systbl, desctbl, paramtbl = RS.table(), RD.table(), RP.table()
    covertbl = BCV.table()
    #   ⓘ 무비는 **미리 구워 둔 것만** 넣는다 — 굽는 데 편당 몇 분이라 빌드를 세우지 않는다
    #     (`movie_hardsub.py --all`). 안 구운 편은 세어서 알린다.
    movietbl, movie_pend = MV.table(disc)
    if movie_pend:
        print(
            f"      ⓘ 자막을 안 구운 무비 {len(movie_pend)}: {' '.join(movie_pend)}"
            f" — `movie_hardsub.py --all` 로 구우면 다음 빌드에 들어간다"
        )

    voicetbl = VS.by_map()
    #   ⚠ 디렉터리 섹터는 **파일들을 다 돈 뒤** 한 번에 낸다 — 한 섹터에 레코드가 여럿이라
    #     파일마다 따로 내면 둘째 쓰기의 사전조건(원본 바이트)이 어긋난다.
    dirsec = {}

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
                if not R.load_script(stem)[0] and stem not in voicetbl:
                    continue
                b = d.read_extent(lba, size)
                new, k, bad = R.patch_blocks(b, stem, table)
                cnt = {"map": k}
                if stem in voicetbl or CT.has(stem):
                    #   🔴 **음성 자막** — 칸 + 글자 표를 파일 끝 섹터 여백에 붙인다.
                    #     파일이 **길어지므로** 원본도 그 여백(0)까지 같이 들어 사전조건이
                    #     서고, 디렉터리 레코드의 크기를 늘려야 엔진이 그만큼 읽는다.
                    #   🔴 그 여백이 맵마다 달라 **13 장면이 안 들어서** 파일을 트랙 1 끝으로
                    #     옮긴다(`relocate.py`). 새 자리는 빈 섹터라 원본은 0 이다.
                    if stem in voicetbl:
                        new, kv = VS.patch(new, stem, voicetbl[stem], table)
                        cnt["voice"] = kv
                    if CT.has(stem):
                        #   🔴 **선택지 항목이 칸보다 길다**(`_wide`) — 진짜 글을 꼬리에 붙이고 트램펄린을 건다.
                        new = CT.patch(new, stem, table, b)
                        cnt["wide"] = len(R.wide(stem))
                    drl, dro = VS.dir_record(d, name)
                    sec = dirsec.setdefault(drl, [d.read_extent(drl, 2048)] * 2)
                    new_lba = lay.alloc(name, lba, len(new))
                    sec[1] = RL.move_record(sec[1], dro, lba, size, new_lba, len(new))
                    cnt["moved"] = 1
                    lba, size, b = new_lba, len(new), b"\x00" * len(new)
            elif name in ("/0.BIN", "/RLTPRG.BIN", "/BLACK.BIN") and systbl:
                #   🔴 **미니게임 실행 파일에도 화면 문구가 있다**(실측 2026-08-28) —
                #     `/RLTPRG.BIN`(룰렛) 「当たったー/どんなもんだい！！」 ·
                #     `/BLACK.BIN`(블랙잭) 「ブラックジャックを終了しますか？」.
                #     `/0.BIN` 만 고치고 있어 여태 일본어로 남아 있었다.
                #   ⓘ `reinsert_sys` 의 **원바이트 폴백**이 `LOAD_BASE` 없는 파일도 받는다.
                b = d.read_extent(lba, size)
                new, k, bad = RS.patch(b, name, systbl)
                cnt = {"sys": k}
                if name == "/0.BIN":
                    #   🔴 **동적 조사 훅** — 문안에 넣은 병기(`을(를)`)를 표시 직전에
                    #     하나로 줄인다. `%s` 에 꽂히는 건 아이템·인물 이름이라 빌드 때
                    #     앞말을 모른다. 훅이 안 돌면 병기 그대로 보인다(안 틀린다).
                    new, hk = JOSA.patch(new)
                    cnt["josa"] = hk
                    #   전투 위쪽 배너(기술명·승리 문구) 글자를 세로 가운데로 — 상수 하나(`patch_ui_center`).
                    new = UIC.patch(new)
                    cnt["ui_center"] = 1
                    #   🔴 **음성 자막 렌더러** — 컷신 위에 우리 창을 그리는 스텁과 훅.
                    #     조사 스텁 뒤 같은 문자열 구역을 쓰므로 그 다음에 넣는다.
                    if voicetbl:
                        #   🔴 크레딧 자막(V20)도 이 파일에 든다 — 스텁 앞 죽은 구역에 코드·표를 얹고
                        #     프레임 태스크의 호출 주소를 바꾼다(`subtitle_stub` 「크레딧 자막」).
                        new = SS.patch(new, table_fn=lambda ctab: VC.blob(ctab))
                        cnt["voice_stub"] = 1
            elif name == RBT.PATH:
                #   🔴 **HP 창 이름은 문자열이 아니라 그림이다** — `status.spr` 안의
                #     프리렌더 이름판 아틀라스를 다시 그린다(`reinsert_battle`).
                b = d.read_extent(lba, size)
                new, k, bad = RBT.patch(b)
                cnt = {"plate": k}
            elif name.startswith("/SYSTEM/BOOK") and name.endswith(".BIN"):
                stem = os.path.basename(name)[:-4]
                booktbl = RB.table(stem)
                if not booktbl:
                    continue
                b = d.read_extent(lba, size)
                new, k, bad, _sq, _cut = RB.patch(b, stem, booktbl, booktable)
                cnt = {"book": k}
                #   🔴 **표지는 글자가 아니라 그림이다** — 폰트로는 안 바뀐다.
                #     정본(`script/book/covers.json`)에 적힌 것만 다시 그린다.
                new, kc = BCV.patch(new, stem, covertbl)
                if kc:
                    cnt["cover"] = kc
            elif name in movietbl:
                #   🔴 **하드섭이다** — 자막을 영상에 태워 굽는다(`movie_hardsub.py`).
                #     엔진에 그리게 하려던 소프트섭은 접었다: 엔진의 텍스트 그리기가
                #     VDP1 스프라이트 VRAM 을 덮는 걸 실측으로 잡았다(`devlog.md`).
                b = d.read_extent(lba, size)
                new, bad = movietbl[name], []
                cnt = {"movie": 1}
            elif name == RG.TARGETS[0][0]:
                b = d.read_extent(lba, size)
                new, _ = RG.apply(b)
                bad, cnt = [], {"gfx": 1 if new != b else 0}
            elif name == "/SYSTEM/PARAM.BIN":
                #   ⚠ 한 파일에 **설명문과 이름 표**가 같이 있다 — 둘을 이어서 넣는다.
                #     이름 표가 빠져 있어 장비창에 일본어가 떴다(2026-08-27 유저 실측).
                b = d.read_extent(lba, size)
                src = DEV.patch_param(b)  # 개발용: 환경변수로 켤 때만(ED_DEV_ISABEL_HP) — 이름이 일본어일 때(번역 전)에 찾는다
                new, k, bad = (src, 0, []) if not desctbl else RD.patch(src, table, desctbl)
                new, k2, bad2 = RP.patch(new, None, paramtbl)
                bad = bad + bad2
                cnt = {"desc": k, "name": k2}
            else:
                continue
            if bad:
                raise SystemExit(f"{name}: {bad[:3]}")
            assert len(new) == size, (len(new), size)
            yield name, lba, size, b, new, cnt
        if lay.grown:
            #   ⚠ 트랙 1 이 늘면 그 뒤 트랙의 파일(디스크 2 엔딩)이 밀린다 — 레코드와 PVD 도
            for name, lba, size in RL.track2_files(d, disc):
                drl, dro = VS.dir_record(d, name)
                sec = dirsec.setdefault(drl, [d.read_extent(drl, 2048)] * 2)
                sec[1] = RL.move_record(sec[1], dro, lba, size, lba + lay.grown, size)
            pvd = d.read_extent(16, 2048)
            yield "PVD", 16, 2048, pvd, RL.pvd_grow(pvd, lay.grown), {}
        for drl, (old, new) in sorted(dirsec.items()):
            yield f"디렉터리 @{drl}", drl, 2048, old, new, {}


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
        #   ⓘ 결과를 먼저 다 뽑는다 — 옮긴 맵을 쓰려면 트랙 1 을 **먼저** 늘려야 하는데
        #     얼마나 늘지는 다 뽑아야 안다.
        lay = RL.Layout(a.disc)
        items = list(patched(a.disc, lay))
        with open(dst, "r+b") as f:
            if lay.grown:
                RL.grow(f, a.disc, lay.grown)
                touched_lbas.append(("트랙 1 꼬리", *lay.span_bytes()))
            for name, lba, size, old, new, cnt in items:
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
                f"읽을거리 {n.get('book', 0)} · 화면 그림 {n.get('gfx', 0)} · 이름판 {n.get('plate', 0)} · "
                f"무비 자막 {n.get('movie', 0)} · 음성 자막 칸 {n.get('voice', 0)}"
            )
            if lay.grown:
                print(
                    f"      트랙 1 을 {lay.grown} 섹터 늘렸다 — 맵 {len(lay.moved)} 개를 "
                    f"LBA {lay.moved[0][2]}~ 로 옮겼다(`relocate.py`)"
                )

        print("[4/5] 섹터 무결성 자기검증")
        bad = mode1.selftest(dst, lbas=[l for _, l, _ in touched_lbas] or [16])
        if bad:
            raise SystemExit(f"EDC/ECC 불일치: {bad[:5]}")

        print("[5/5] 무변경 구간 대조 (선언한 파일 밖은 원본과 동일해야 한다)")
        diff = compare(C.DISC_BIN[a.disc], dst, touched_lbas)
        if diff:
            raise SystemExit(f"건드린다고 선언 안 한 자리가 바뀌었다: {diff[:5]}")

        nt, nb = copy_extra_tracks(a.disc, lay.grown)
        if nt:
            print(f"      트랙 {nt} 개를 옮겼다 ({nb / 1e6:.0f}MB) — 트랙1 밖의 파일이 여기 있다")
        write_cue(a.disc)
        write_m3u()
        emit_saves()
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


def emit_saves():
    """이 빌드의 **해시 이름 세이브**를 이미지 옆에 놓는다(`save_names`) — 세이브 보관함에는 안 쌓는다(마스터 10-05)."""
    import save_names as SN

    sys.path.insert(0, os.path.join(C.GAME_DIR, "..", "..", "scripts", "emu"))
    import ss_gameid as SG

    imgs = [out_paths(d)[1] for d in C.DISCS] + [m3u_path()]
    made = SN.emit(SN.default_src(), C.BUILD_DIR, imgs, SG.game_id)
    if made:
        print(f"      세이브 사본 {len(made)}개를 빌드 칸에 놓았다(해시 이름) ← {SN.default_src()}")


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
