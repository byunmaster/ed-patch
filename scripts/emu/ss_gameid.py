"""새턴 이미지의 **mednafen GameID** — 백업 RAM 파일명에 쓰이는 그 해시.

    python3 scripts/emu/ss_gameid.py "<이미지.cue|.bin>"              # 해시만
    python3 scripts/emu/ss_gameid.py --fit <세이브디렉터리> "<이미지>"  # 세이브 이름 맞추기

🔴 **왜 필요한가.** mednafen 은 세이브 이름을 `<게임 이름>.<GameID>.bkr` 로 짓는다.
GameID 는 **TOC + 앞 512 섹터의 유저 데이터**다(`ss/ss.cpp:CalcGameID`). 한글패치는 보통
**그 512 섹터 안을 고친다** — ss-ed3 만 해도 `/0.BIN`(LBA 48) · `KANJI12.FON`(358) ·
`PARAM.BIN`(431) 이 전부 안이다. 그래서 **빌드할 때마다 이름이 바뀌고 세이브가 조용히
안 읽힌다**(타이틀에 `Continue` 가 안 뜨고 그냥 New Game 이 시작된다 — 실측으로 네 번
헛돌았다, 2026-08-25).
⚠ 반대로 뒤쪽 파일(ss-ed3 의 `MAP*.BIN` 은 3203+)만 고치면 **안 바뀐다** — 그래서 대사만
건드리던 동안에는 이 함정이 안 보였다.

🔴 **에뮬이 꺼진 상태에서 맞춘다** — mednafen 은 **종료할 때** 백업 RAM 을 덮어쓰므로,
켜 둔 채 복사하면 그 복사가 그대로 지워진다.

⚠ **emucap `get_rom_info` 의 `content_md5` 는 이게 아니다** — 그건 파일 해시다. 그걸로
이름을 지으면 안 읽힌다(2026-08-25 에 이걸로 네 번 헛돌았다).

계산은 `mednafen/src/ss/ss.cpp` 의 `CalcGameID` 그대로다:

    md5( u32le(first_track) ‖ u32le(last_track) ‖ u32le(disc_type)
         ‖ [u32le(adr) ‖ u32le(control) ‖ u32le(lba) ‖ u32le(valid)] × 100
         ‖ 앞 512 섹터의 유저 데이터(2048B 씩) )

⚠ 단일 데이터 트랙(MODE1/2352) 기준이다 — 트랙이 여럿인 이미지는 TOC 를 채워야 한다.
"""

import hashlib
import os
import struct
import sys

SECTOR = 2352
USER_OFF = 16  # MODE1
LEADOUT = 100


def game_id(bin_path):
    size = os.path.getsize(bin_path)
    sectors = size // SECTOR
    m = hashlib.md5()
    u32 = lambda v: struct.pack("<I", v & 0xFFFFFFFF)
    m.update(u32(1))  # first_track
    m.update(u32(1))  # last_track
    m.update(u32(0))  # disc_type = CDDA_OR_M1
    for i in range(1, 101):
        if i == 1:
            adr, ctrl, lba, valid = 1, 4, 0, 1
        elif i == LEADOUT:
            adr, ctrl, lba, valid = 1, 4, sectors, 1
        else:
            adr, ctrl, lba, valid = 0, 0, 0, 0
        for v in (adr, ctrl, lba, valid):
            m.update(u32(v))
    with open(bin_path, "rb") as f:
        for i in range(512):
            f.seek(i * SECTOR + USER_OFF)
            m.update(f.read(2048))
    return m.hexdigest()


def resolve(path):
    """`.cue` 를 주면 그 안의 `FILE` 을 따라간다."""
    if path.lower().endswith(".cue"):
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.upper().startswith("FILE"):
                    name = line.split('"')[1] if '"' in line else line.split()[1]
                    return os.path.join(os.path.dirname(path), name)
        raise SystemExit(f"cue 안에 FILE 이 없다: {path}")
    return path


def fit(save_dir, image):
    """`save_dir` 의 가장 최근 세이브를 **지금 이미지의 이름**으로 복사한다.

    ⚠ 옮기지 않고 **복사**한다 — 옛 이름을 지우면 다른 빌드로 되돌아갔을 때 못 읽는다.
    """
    import glob
    import shutil

    gid = game_id(resolve(image))
    xs = sorted(glob.glob(os.path.join(save_dir, "*.bkr")), key=os.path.getmtime, reverse=True)
    if not xs:
        return gid, 0, None
    stem = os.path.basename(xs[0])[: -len(".bkr")]
    name, _, old = stem.rpartition(".")
    if old == gid:
        return gid, 0, old
    n = 0
    for e in ("bkr", "bcr", "smpc"):
        src = os.path.join(save_dir, f"{name}.{old}.{e}")
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(save_dir, f"{name}.{gid}.{e}"))
            n += 1
    return gid, n, old


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 3 and a[0] == "--fit":
        gid, n, old = fit(a[1], a[2])
        if n:
            print(f"세이브를 지금 빌드 이름으로 맞췄다: {old} → {gid} ({n} 개)")
        elif old:
            print(f"세이브 이름이 이미 맞다 ({gid})")
    elif len(a) == 1:
        print(game_id(resolve(a[0])))
    else:
        raise SystemExit(
            "사용: ss_gameid.py <이미지> | ss_gameid.py --fit <세이브디렉터리> <이미지>"
        )
