"""독 이미지 비교 — 「옛 일본어 구역을 게임이 읽나」(밤샘 11-08, 관리자 지시; md-ed1/2 방법).

    python3 tools/poison_compare.py make          # 시험 이미지 둘(독·양성 대조)을 work/build/test-poison/ 에 만든다
    python3 tools/poison_compare.py run <clean|poison|posctl> <입력 수>   # 헤드리스 엔딩 주행 → 프레임 해시 열
    python3 tools/poison_compare.py compare       # 세 열 대조

- **독**(poison): 게임이 안 읽어야 하는 옛 일본어 구역을 0xEE 로 칠한다 — ① 옮긴 블록의 원 자리 죽은 구간(트램펄린 `FD 00 <꼬리>` 6바이트 뒤 ~ 돌아오는 자리 앞, Disc 2 구운 맵 전부)
  ② 파일 이전으로 버려진 옛 `MAP*.BIN` 연장(옛 LBA — 디렉터리가 이제 새 자리를 가리킨다. 지금 다른 파일이 덮는 섹터는 제외).
- **양성 대조**(posctl): 실제로 쓰는 구역(엔딩 길의 `MAP075.BIN` 본문 + 폰트 글리프 칸 일부)을 칠한다 — 프레임이 갈려야 한다.
- 주행 = 같은 입력 열(before_isabel 7번 칸 → 위로 걷기 → `c` 연타)로 돌려 N 프레임마다 화면 해시를 모은다. 독 = 깨끗한 제품과 열이 같으면 읽기 0.
  「화면이 움직였나」= 고유 해시 수.
⚠ 칠한 시험 이미지는 EDC/ECC 를 안 고친다(mednafen 은 안 본다). 이름이 `test-` 라 마스터 목록에 안 나온다.
"""

import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_structure as S
import common as C

TEST = os.path.join(os.path.dirname(C.BUILD_DIR), "test-poison")
SRC = os.path.join(C.BUILD_DIR, "Shiroki Majo (KR) (Disc 2).bin")
NAME = "Shiroki Majo (KR) (Disc 2)"
SEC = 2352
FILL = 0xEE


def paint(f, lba, nsec):
    for i in range(nsec):
        f.seek((lba + i) * SEC + C.USER_OFF)
        f.write(bytes([FILL]) * 2048)


def zones():
    """`(독 구간 [(lba, 바이트오프셋 안 구간)], …)` — 독: (파일 안 오프셋 구간) 목록 + 옛 LBA 연장."""
    o = C.open_disc(2, verify=False)
    n = C.Disc(SRC, user_off=C.USER_OFF)
    nfiles = {nm: (lba, size) for nm, lba, size in n.files()}
    cur = [(lba, lba + (size + 2047) // 2048) for nm, (lba, size) in nfiles.items()]
    dead = []  # (lba, 파일내 바이트 오프셋 a, b)
    old_ext = []
    for nm, lba, size in o.files():
        ok, _stem = C.is_map_file(nm)
        if not ok:
            continue
        ob = o.read_extent(lba, size)
        bb = S.entry(n, nm)
        for p, _t, r, _g in S.trampolines(ob, bb):
            if r:
                dead.append((nfiles[nm][0], p + 6, r))
        if nfiles[nm][0] != lba:
            a, b = lba, lba + (size + 2047) // 2048
            keep = [(max(a, x), min(b, y)) for x, y in cur if x < b and y > a]
            # 현재 다른 파일이 덮는 섹터는 뺀다
            sec = [s for s in range(a, b) if not any(x <= s < y for x, y in cur)]
            old_ext.append((nm, sec, len(keep)))
    return dead, old_ext, nfiles


def make():
    os.makedirs(TEST, exist_ok=True)
    dead, old_ext, nfiles = zones()
    for v in ("poison", "posctl"):
        d = os.path.join(TEST, v)
        os.makedirs(d, exist_ok=True)
        for fn in os.listdir(C.BUILD_DIR):
            if fn.startswith(NAME) and fn.endswith(".bin") and "Track" in fn:
                dst = os.path.join(d, fn)
                if not os.path.lexists(dst):
                    os.symlink(os.path.join(C.BUILD_DIR, fn), dst)
        shutil.copy(SRC, os.path.join(d, NAME + ".bin"))
        shutil.copy(os.path.join(C.BUILD_DIR, NAME + ".cue"), os.path.join(d, NAME + ".cue"))
    with open(os.path.join(TEST, "poison", NAME + ".bin"), "r+b") as f:
        nd = 0
        for lba, a, b in dead:  # 파일 안 바이트 a..b 를 칠한다(섹터 경계 가로질러도 바이트 단위)
            for q in range(a, b):
                f.seek((lba + q // 2048) * SEC + C.USER_OFF + q % 2048)
                f.write(bytes([FILL]))
            nd += b - a
        ns = 0
        for _nm, sec, _ in old_ext:
            for s in sec:
                paint(f, s, 1)
            ns += len(sec)
    print(f"독: 죽은 구간 {len(dead)}곳 {nd}B · 버려진 옛 맵 {len(old_ext)}개 {ns}섹터")
    lba, size = (
        nfiles["/MAP/MAP075.BIN"]
        if "/MAP/MAP075.BIN" in nfiles
        else next(v for k, v in nfiles.items() if k.endswith("MAP075.BIN"))
    )
    fl, _fs = next(v for k, v in nfiles.items() if k.endswith("KANJI12.FON"))
    with open(os.path.join(TEST, "posctl", NAME + ".bin"), "r+b") as f:
        paint(f, lba + 1, max(1, (size + 2047) // 2048 - 1))
        paint(f, fl + 4, 8)
    print(f"양성 대조: MAP075.BIN {(size + 2047) // 2048 - 1}섹터 + KANJI12.FON 8섹터")


def run(variant, presses):
    from ss_headless import Harness

    cue = os.path.join(
        C.BUILD_DIR if variant == "clean" else os.path.join(TEST, variant), NAME + ".cue"
    )
    bkr = "/tmp/claude-0/endrun/bi.bkr"
    out = os.path.join(TEST, "out-" + variant)
    os.makedirs(out, exist_ok=True)
    from ss_headless import CACHE

    h = Harness(
        os.path.join(CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so"),
        cue,
        out,
        bkr=bkr,
    )
    hs = []

    def runh(n, every=8):
        for i in range(n):
            h.core.retro_run()
            if i % every == 0:
                hs.append(hashlib.sha1(h.frame.tobytes()).hexdigest()[:10])

    def press(b, hold, after):
        h.held = {__import__("ss_headless").BTN[b]}
        runh(hold)
        h.held = set()
        runh(after)

    runh(3000)
    press("start", 10, 300)
    press("c", 6, 300)
    for _ in range(6):
        press("down", 6, 20)
    press("c", 6, 900)
    press("c", 6, 600)
    press("up", 120, 200)
    press("up", 120, 200)
    for i in range(presses):
        press("up", 30, 10) if i < 60 else None
        press("c", 6, 80)
    json.dump(hs, open(os.path.join(TEST, f"hash-{variant}.json"), "w"))
    h.shot("last")
    print(variant, "hashes", len(hs), "unique", len(set(hs)))


def compare():
    r = {
        v: json.load(open(os.path.join(TEST, f"hash-{v}.json")))
        for v in ("clean", "poison", "posctl")
    }
    for v in ("poison", "posctl"):
        d = sum(1 for a, b in zip(r["clean"], r[v], strict=True) if a != b)
        first = next((i for i, (a, b) in enumerate(zip(r["clean"], r[v], strict=True)) if a != b), None)
        print(f"{v}: 길이 {len(r[v])} (clean {len(r['clean'])}) · 다른 해시 {d} · 첫 차이 {first}")
    print("clean 고유 해시", len(set(r["clean"])), "/", len(r["clean"]))


if __name__ == "__main__":
    {
        "make": lambda: make(),
        "run": lambda: run(sys.argv[2], int(sys.argv[3])),
        "compare": lambda: compare(),
    }[sys.argv[1]]()
