"""새턴 이미지의 **mednafen GameID** — 백업 RAM 파일명에 쓰이는 그 해시.

    python3 scripts/emu/ss_gameid.py "<이미지.cue|.m3u|.bin>"          # 해시만
    python3 scripts/emu/ss_gameid.py --fit <세이브디렉터리> "<이미지>"  # 세이브 이름 맞추기

🔴 **왜 문제가 되나.** mednafen 은 세이브 이름을 `<이미지이름>.<GameID>.bkr` 로 짓는다.
GameID 는 **TOC + 앞 512 섹터의 유저 데이터**다(`ss/ss.cpp:CalcGameID`). 한글패치는 보통
**그 512 섹터 안을 고친다** — ss-ed3 만 해도 `/0.BIN`(LBA 48) · `KANJI12.FON`(358) ·
`PARAM.BIN`(431) 이 전부 안이다. 그래서 **빌드할 때마다 이름이 바뀌고 세이브가 조용히
안 읽힌다**(타이틀에 `Continue` 가 안 뜨고 그냥 New Game 이 시작된다).
⚠ 반대로 뒤쪽 파일(ss-ed3 의 `MAP*.BIN` 은 3203+)만 고치면 **안 바뀐다** — 그래서 대사만
건드리던 동안에는 이 함정이 안 보였다.

🔴 **그래서 해시를 쫓지 않고, 해시가 안 붙은 이름으로 모은다**(2026-08-29 전환).
mednafen 의 기본 `filesys.fname_sav` 는 `%f.%M%x` 인데, `%M` 의 규칙이 이렇다
(`general.cpp:MDFN_MakeFName`) — **먼저 해시 없이 찾아보고, 그 파일이 있으면 그걸 쓴다.**
없을 때만 해시를 끼워 넣는다. 즉 `<이미지이름>.bkr` 한 벌만 만들어 두면 **빌드를 아무리
갈아도 mednafen 이 늘 그 파일을 읽고 거기에 쓴다.**
⚠ 종전엔 GameID 를 **계산해서** 그 이름으로 사본을 떴는데, 계산이 한 자만 어긋나도
조용히 New Game 이 됐다. 실제로 어긋나 있었다 — 아래 참조.
⚠ `-filesys.fname_sav '%f.%x'` 로 아예 못 박는 길도 있지만 **쓰지 않는다.** mednafen 은
종료할 때 명령줄로 준 설정까지 `mednafen.cfg` 에 써 버려서(실측: `filesys.path_sav` 가
그렇게 박혀 있다), 새턴 때문에 준 설정이 **PS1·PCE 세이브 이름까지 영구히** 바꾼다.

🔴 **에뮬이 꺼진 상태에서 맞춘다** — mednafen 은 **종료할 때** 백업 RAM 을 덮어쓰므로,
켜 둔 채 복사하면 그 복사가 그대로 지워진다.

⚠ **emucap `get_rom_info` 의 `content_md5` 는 이게 아니다** — 그건 파일 해시다.

── GameID 계산 (`ss/ss.cpp:CalcGameID`) ────────────────────────────────────
    md5( 디스크마다:
         u32le(first_track) ‖ u32le(last_track) ‖ u32le(disc_type)
         ‖ [u32le(adr) ‖ u32le(control) ‖ u32le(lba) ‖ u32le(valid)] × 100
         ‖ 앞 512 섹터 중 **데이터 섹터**의 유저 데이터(2048B 씩) )

🔴 **TOC 는 진짜로 읽어야 한다**(2026-08-29 실측). 종전 판은 「데이터 트랙 하나」로 넘겨짚어
`first=last=1` 에 리드아웃만 채웠는데, 우리 새턴 이미지는 둘 다 그렇지 않다 —
ss-ed3 는 데이터 1 + 오디오 1, ss-ed1+2 는 데이터 1 + **오디오 31** 이다. 그래서 계산값이
mednafen 것과 달랐고(`4be90310…` vs 진짜 `cf6b0bc1…`), `--fit` 은 **mednafen 이 쳐다보지도
않는 이름**으로 사본을 떠 왔다. 세이브가 안 읽히던 게 이것이다.
LBA·리드아웃·control 은 `cdrom/CDAccess_Image.cpp:GenerateTOC` 를 그대로 옮겼다:
  · `RunningLBA` 는 **-150 에서 시작**하고 첫 트랙의 pregap 에 150 이 더해진다
  · cue 는 `pregap_dv = INDEX01 - INDEX00`(INDEX00 이 있을 때)만큼 파일 안에서 건너뛴다
  · 한 파일에 트랙이 여럿이면 sectors 는 **다음 트랙의 INDEX 차**, 파일의 마지막
    트랙이면 **남은 파일 크기 ÷ 섹터 크기**
  · 리드아웃(100)의 control 은 **마지막 트랙 것**이다(오디오로 끝나면 0 이다)
"""

import glob
import hashlib
import os
import shutil
import struct
import subprocess
import sys

# cue 의 트랙 형식 → (섹터 크기, 데이터인가, 섹터가 통째로(=헤더까지) 들었나)
# ⚠ **유저 데이터 위치는 여기서 안 정한다.** mednafen 은 cue 가 뭐라 적었든 **섹터 헤더의
#   모드 바이트**(오프셋 15)를 보고 16(모드1)이냐 24(모드2 form1)냐를 고른다
#   (`cdrom/CDInterface.cpp:ReadSectors`). ss-ed3 는 Disc 1 이 MODE1/2352,
#   Disc 2 가 MODE2/2352 라 이 구분이 실제로 갈린다.
# ⚠ 2336(헤더 없는 MODE2)은 **안 넣었다** — 우리 이미지에 없어서 맞는지 확인할 길이 없다.
#   넘겨짚어 넣으면 「조용히 틀린 해시」가 되는데, 그게 바로 이 파일이 한 번 낸 사고다.
FORMATS = {
    "AUDIO": (2352, False, True),
    "MODE1/2048": (2048, True, False),
    "MODE1/2352": (2352, True, True),
    "MODE2/2352": (2352, True, True),
}
LEADOUT = 100
SAVE_EXTS = ("bkr", "bcr", "smpc")


def _msf(s):
    m, sec, f = (int(x) for x in s.split(":"))
    return (m * 60 + sec) * 75 + f


def parse_cue(path):
    """cue → 트랙 목록. 형식은 `CDAccess_Image.cpp` 의 cue 갈래를 따른다.

    ⚠ `.bin` 을 바로 주면 **데이터 트랙 하나짜리**로 친다 — mednafen 이 cue 없는 이미지를
      그렇게 읽는다. 트랙이 여럿인 이미지를 이렇게 주면 값이 다르게 나오니 cue 를 준다.
    """
    if not path.lower().endswith(".cue"):
        return [
            {
                "num": 1,
                "fmt": "MODE1/2352",
                "file": path,
                "index": {1: 0},
                "pregap": 0,
                "postgap": 0,
                "first_in_file": True,
            }
        ]
    base = os.path.dirname(path)
    tracks = []
    cur_file = None
    seen_files = set()
    with open(path, encoding="utf-8", errors="replace") as fp:
        for line in fp:
            parts = line.split()
            if not parts:
                continue
            cmd = parts[0].upper()
            if cmd == "FILE":
                name = line.split('"')[1] if '"' in line else parts[1]
                cur_file = os.path.join(base, name)
            elif cmd == "TRACK":
                fmt = parts[2].upper()
                if fmt not in FORMATS:
                    raise SystemExit(f"⛔ 모르는 트랙 형식이라 GameID 를 못 만든다: {fmt}")
                tracks.append(
                    {
                        "num": int(parts[1]),
                        "fmt": fmt,
                        "file": cur_file,
                        "index": {},
                        "pregap": 0,
                        "postgap": 0,
                        # 이 트랙이 그 FILE 의 첫 트랙인가 — 파일 오프셋이 여기서 0 으로 돌아간다
                        "first_in_file": cur_file not in seen_files,
                    }
                )
                seen_files.add(cur_file)
            elif cmd == "INDEX" and tracks:
                tracks[-1]["index"][int(parts[1])] = _msf(parts[2])
            elif cmd == "PREGAP" and tracks:
                tracks[-1]["pregap"] = _msf(parts[1])
            elif cmd == "POSTGAP" and tracks:
                tracks[-1]["postgap"] = _msf(parts[1])
    if not tracks:
        raise SystemExit(f"⛔ cue 에 트랙이 없다: {path}")
    return tracks


def build_toc(tracks):
    """트랙 목록 → (first, last, disc_type, 트랙별 TOC 항목, total_sectors)."""
    running = -150
    tracks[0]["pregap"] += 150
    file_off = 0
    for i, t in enumerate(tracks):
        size, is_data, _ = FORMATS[t["fmt"]]
        t["control"] = 4 if is_data else 0
        if t["first_in_file"]:
            file_off = 0
        running += t["pregap"]
        # INDEX 00 이 있으면 그 차이만큼은 **파일 안의 갭**이라 건너뛴다
        dv = t["index"][1] - t["index"][0] if 0 in t["index"] else 0
        file_off += dv * size
        running += dv
        t["lba"] = running
        t["file_off"] = file_off
        nxt = tracks[i + 1] if i + 1 < len(tracks) else None
        if nxt is None or nxt["first_in_file"]:
            t["sectors"] = (os.path.getsize(t["file"]) - file_off) // size
        else:
            end = nxt["index"].get(0, nxt["index"][1])
            t["sectors"] = end - t["index"][1]
        running += t["sectors"] + t["postgap"]
        file_off += t["sectors"] * size
    return tracks[0]["num"], tracks[-1]["num"], running


def _read_user(tracks, lba):
    """그 LBA 의 유저 데이터 2048B — 해시에 안 들어가는 섹터면 None.

    `CDInterface::ReadSectors` 를 그대로 옮겼다 — **섹터 헤더의 모드 바이트**로 고른다.
    모드가 1·2 가 아니거나(오디오 등) 모드2 form2 면 mednafen 은 **0 을 돌려주고, 그 섹터는
    해시에 아예 안 들어간다**.
    ⚠ mednafen 은 여기서 EDC/ECC 도 확인하고 틀리면 버린다. 우리 빌드는 EDC 를 다시
      계산해 넣으므로 그대로 통과한다고 본다(틀리면 게임이 먼저 안 돈다).
    """
    for t in tracks:
        if not (t["lba"] <= lba < t["lba"] + t["sectors"]):
            continue
        size, is_data, raw = FORMATS[t["fmt"]]
        if not is_data:
            return None
        with open(t["file"], "rb") as f:
            f.seek(t["file_off"] + (lba - t["lba"]) * size)
            sec = f.read(size)
        if not raw:
            return sec[:2048]
        mode = sec[15]
        if mode == 1:
            return sec[16 : 16 + 2048]
        if mode == 2:
            if sec[18] & 0x20:  # form 2 — 통째로 버린다
                return None
            return sec[24 : 24 + 2048]
        return None
    return None


def _feed(m, cue):
    tracks = parse_cue(cue)
    first, last, total = build_toc(tracks)
    by_num = {t["num"]: t for t in tracks}
    u32 = lambda v: m.update(struct.pack("<I", v & 0xFFFFFFFF))  # noqa: E731
    u32(first)
    u32(last)
    u32(0)  # disc_type — MODE1/AUDIO 만 다루므로 늘 DISC_TYPE_CDDA_OR_M1
    for i in range(1, LEADOUT + 1):
        if i in by_num:
            adr, ctrl, lba, valid = 1, by_num[i]["control"], by_num[i]["lba"], 1
        elif i == LEADOUT:
            # ⚠ 리드아웃의 control 은 **마지막 트랙 것**이다 — 오디오로 끝나면 0 이다
            adr, ctrl, lba, valid = 1, tracks[-1]["control"], total, 1
        else:
            adr, ctrl, lba, valid = 0, 0, 0, 0
        for v in (adr, ctrl, lba, valid):
            u32(v)
    for i in range(512):
        data = _read_user(tracks, i)
        if data:
            m.update(data)


def game_id(path):
    """`.m3u` 면 **그 안의 디스크 전부**를 한 md5 에 이어 넣는다(CalcGameID 의 바깥 루프)."""
    m = hashlib.md5()
    for cue in discs_of(path):
        _feed(m, cue)
    return m.hexdigest()


def discs_of(path):
    if path.lower().endswith(".m3u"):
        base = os.path.dirname(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            xs = [os.path.join(base, ln.strip()) for ln in f if ln.strip() and ln[0] != "#"]
        if not xs:
            raise SystemExit(f"⛔ m3u 가 비었다: {path}")
        return xs
    return [path]


def _score(path):
    """그 세이브에 **얼마나 들어 있나** — 백업 RAM 의 빈 자리는 0 이라 비영 바이트로 잰다."""
    try:
        with open(path, "rb") as f:
            return sum(1 for b in f.read() if b)
    except OSError:
        return 0


def _mednafen_running():
    """켜져 있으면 손대지 않는다 — mednafen 은 **저장할 때 이름을 다시 정한다**.

    🔴 `ss.cpp:1880` 이 `MDFN_MakeFName(MDFNMKF_SAV, 0, "bkr")` 를 **쓰는 순간에** 부른다.
      켜 둔 채로 해시 없는 이름을 만들어 놓으면, 그 다음 저장(백업 RAM 이 더러워지면 3초 뒤
      자동, 아니면 종료할 때)에 **지금 켜져 있는 쪽의 백업 RAM 이 그 파일을 덮는다.**
      세이브를 못 읽은 회차라면 그게 곧 **빈 것**이라, 방금 살린 진행분이 그대로 날아간다.
    """
    return subprocess.run(["pgrep", "-x", "mednafen"], capture_output=True).returncode == 0


def fit(save_dir, image):
    """세이브를 **해시가 안 붙은 이름**으로 모은다 — 그러면 빌드를 갈아도 따라온다.

    🔴 **제일 새것을 고르면 안 된다**(2026-08-29 실측). 세이브를 못 읽은 회차에도 mednafen 은
      종료할 때 백업 RAM 을 쓰므로, **제일 새 파일이 바로 그 빈 것**이다 — 실측으로 방금 것이
      144B, 진짜 진행분이 880B 였다. 그래서 **든 것이 제일 많은** 파일을 고르고, 같으면
      새것을 고른다.
    ⚠ 옛 이름은 **안 지운다** — 되돌아갔을 때 필요하고, 지워서 얻는 것도 없다.
    ⚠ 해시 없는 쪽이 이미 있고 **더 새것이면 아무것도 안 한다** — mednafen 이 이미 그걸 쓰고
      있다는 뜻이라, 덮으면 진행분이 날아간다(게임 안에서 세이브를 지운 회차까지 포함해서).
    ⚠ 이름의 밑동은 **띄운 이미지**를 따른다 — m3u 로 띄우면 `Shiroki Majo (KR)`,
      Disc 1 cue 로 띄우면 `Shiroki Majo (KR) (Disc 1)` 이라 계보가 갈린다(mednafen 규칙이다).
    """
    base = os.path.splitext(os.path.basename(image))[0]
    if _mednafen_running():
        print("⚠ mednafen 이 켜져 있어 세이브 이름을 안 건드린다 — 끄고 다시 띄운다")
        return base, 0, None
    plain = os.path.join(save_dir, f"{base}.bkr")
    hashed = glob.glob(os.path.join(save_dir, glob.escape(base) + ".*.bkr"))
    if not hashed:
        return base, 0, None

    # 든 것이 많은 순 → 새것 순
    def rank(p):
        return (_score(p) + _score(p[: -len(".bkr")] + ".bcr"), os.path.getmtime(p))

    best = max(hashed, key=rank)
    if os.path.exists(plain):
        if os.path.getmtime(plain) >= os.path.getmtime(best) or rank(plain) >= rank(best):
            return base, 0, None
    # 셋을 **같은 회차 것으로** 맞춰 가져온다(고른 `.bkr` 의 해시를 따른다)
    old = os.path.basename(best)[len(base) + 1 : -len(".bkr")]
    n = 0
    for e in SAVE_EXTS:
        src = os.path.join(save_dir, f"{base}.{old}.{e}")
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(save_dir, f"{base}.{e}"))
            n += 1
    return base, n, old


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 3 and a[0] == "--fit":
        name, n, old = fit(a[1], a[2])
        if n:
            print(f"세이브를 해시 없는 이름으로 모았다: {old} → {name}.* ({n} 개)")
    elif len(a) == 1:
        print(game_id(a[0]))
    else:
        raise SystemExit(
            "사용: ss_gameid.py <이미지> | ss_gameid.py --fit <세이브디렉터리> <이미지>"
        )
