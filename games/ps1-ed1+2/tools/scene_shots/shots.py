"""대사 보기 — 실게임 흐름으로 씬 대사·임의 문안을 찍는다(ED1·ED2).

  python3 -m scene_shots.shots [옵션] 대상…        (tools/ 에서)

대상:  ED1SCN2:26                     씬:eid — 빌드 이미지 안 바이트로 쪽마다 한 장
       text:이름|본문                 임의 문안(줄바꿈은 \\n, 이름 생략 가능)
       natural                        갈아 끼우지 않은 자연 대사(비교 기준)
옵션:  --game ED1|ED2  게임(기본: 첫 씬 대상의 접두 — `text:` 만 있으면 ED1)
       --bin / --cue   촬영할 빌드 이미지(기본 현재 BUILD_DIR). 상태 캐시는 이미지 해시별로 갈라 둔다
       --core         pcsx_rearmed libretro `.so` (환경변수 PS1_LIBRETRO_CORE)
       --system-dir   BIOS 디렉터리 · --save-dir 코어 저장 디렉터리
       --out          PNG·index.tsv 를 둘 폴더
       --variant 태그=이름   `%s`(이름 주입)가 든 대상을 이름마다 한 번씩(예: 무받침=발견의 피리)
       --presses      말걸기 앞 대사 쪽 수(기본 10)
⚠ 코어는 프로세스당 하나만 — 에뮬 실행은 `sh scripts/capture.sh <명령>` 칸을 쓴다.
"""

import argparse
import hashlib
import os
import subprocess
import sys

from PIL import Image as PILImage

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "scene_shots"

import hangul_map
from common import BUILD_DIR

from . import catalog, pages, realflow
from .image_io import Image
from .libretro import Machine, default_core


def cache_root() -> str:
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()  # fmt: skip
        base = os.path.dirname(common)
    except (OSError, subprocess.CalledProcessError):
        base = os.getcwd()
    return os.path.join(base, ".local", "cache", "scene_shots")


def enc(s: str) -> bytes:
    out = bytearray()
    for ch in s:
        if ch == "\n":
            out += b"\n"
        elif ch in hangul_map.SYL_INDEX:
            out += hangul_map.syllable_sjis(ch).to_bytes(2, "big")
        else:
            try:
                out += ch.encode("ascii")
            except UnicodeEncodeError:
                out += ch.encode("cp932")  # 원판 이미지(일본어 글꼴)에 넣을 가나 이름 — 원판 대조 촬영용
    return bytes(out)


def image_sha1(bin_path: str) -> str:
    """이미지 전체 sha1 — 상태 캐시의 열쇠이자 메타. 앞 16MB 만 보면 뒤쪽(ED2MON 오버레이·씬 파일)이 바뀐 이미지를 같은 열쇠로 읽는다."""
    h = hashlib.sha1()
    with open(bin_path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def image_key(bin_path: str) -> str:
    """상태 캐시 열쇠 — 이미지 **전체** sha1 앞 12자(250MB 라도 1~2초). 옛 앞 16MB 지문은 뒤쪽 변경을 못 봤다."""
    return image_sha1(bin_path)[:12]


STATE_META = "state_meta.json"


def check_state_meta(cache_dir: str, sha1: str) -> None:
    """상태 옆 메타(만든 롬 sha1)가 지금 촬영 롬과 다르면 상태를 버려 새로 만들게 한다.

    세이브스테이트는 롬을 바꿔도 **옛 RAM(글리프 표·코드·텍스트)을 되살린다**(ps1-ed3 10-20: 「줄」이 「앗」으로 찍힘).
    """
    import json

    meta = os.path.join(cache_dir, STATE_META)
    if os.path.isdir(cache_dir):
        old = None
        if os.path.exists(meta):
            with open(meta, encoding="utf-8") as f:
                old = json.load(f).get("image_sha1")
        if old != sha1:  # 메타 없음(옛 캐시)도 신뢰하지 않는다
            for fn in os.listdir(cache_dir):
                if fn.endswith(".state"):
                    os.remove(os.path.join(cache_dir, fn))
    os.makedirs(cache_dir, exist_ok=True)
    with open(meta, "w", encoding="utf-8") as f:
        json.dump({"image_sha1": sha1}, f)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("targets", nargs="+")
    ap.add_argument("--bin", default=os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin"))
    ap.add_argument("--cue", default=None)
    ap.add_argument("--core", default=default_core())
    ap.add_argument("--system-dir", default=os.environ.get("PS1_SYSTEM_DIR", ""))
    ap.add_argument("--save-dir", default=os.environ.get("PS1_SAVE_DIR", ""))
    ap.add_argument("--out", required=True)
    ap.add_argument("--variant", action="append", default=[])
    ap.add_argument("--game", choices=sorted(realflow.PROFILES), default=None)
    ap.add_argument("--presses", type=int, default=None)
    a = ap.parse_intermixed_args()
    if not a.core or not os.path.exists(a.core):
        ap.error("--core(또는 PS1_LIBRETRO_CORE) 가 필요하다")
    cue = a.cue or a.bin[:-4] + ".cue"
    game = a.game
    if game is None:
        game = next((t[:3] for t in a.targets if t[:3] in realflow.PROFILES), "ED1")
    for t in a.targets:
        if t[:3] in realflow.PROFILES and t[:3] != game:
            ap.error(f"한 번에 한 게임만 — {t} 는 {game} 가 아니다")
    os.makedirs(a.out, exist_ok=True)
    variants = [tuple(v.split("=", 1)) for v in a.variant] or [("", None)]

    image = Image(a.bin)
    cats: dict[str, dict] = {}

    def entry(scn: str, eid: int):
        if scn not in cats:
            cats[scn] = {x["eid"]: x for x in catalog.build(scn, image)}
        return cats[scn].get(eid)

    slot_scn, slot_eid = realflow.PROFILES[game]["slot"]
    slot_piece = entry(slot_scn, slot_eid)["pieces"][0]
    m = Machine(a.core, a.system_dir, a.save_dir, cue)
    sha1 = image_sha1(a.bin)
    cache = os.path.join(cache_root(), sha1[:12])
    check_state_meta(cache, sha1)
    flow = realflow.RealFlow(m, cache, bytes.fromhex(slot_piece["hex"]), a.presses, game)
    flow.prepare()
    peek = m.peek

    with open(os.path.join(a.out, "index.tsv"), "w", encoding="utf-8") as index:
        index.write("대상\t쪽\t변형\t파일\t타자끝\t커서\t바이트\n")
        nshots = 0
        for ti, t in enumerate(a.targets, 1):
            jobs = []  # (태그, 변형, [쪽 바이트])
            if t == "natural":
                jobs.append(("natural", "", [None]))
            elif t.startswith("text:"):
                nm, sep, tx = t[5:].replace("\\n", "\n").partition("|")
                if not sep:
                    nm, tx = "", nm
                head = b"\x02" + enc(nm) + b"\x01\n" if nm else b""
                jobs.append((f"text{ti}", "", pages.pages_of(head + enc(tx))))
            else:
                scn, eid_s = t.split(":")
                x = entry(scn, int(eid_s))
                if not x or not x["pieces"]:
                    index.write(f"{t}\t0\t-\tNONE\t-\t-\t0\n")
                    continue
                p = x["pieces"][0]
                fm = bytes.fromhex(p["hex"])
                vs = variants if b"%s" in fm else [("", None)]
                for vtag, vname in vs:
                    full = pages.evaluate(fm, p["args"], peek, game, enc(vname) if vname else None)
                    jobs.append((f"{scn}_{int(eid_s):04d}", vtag, pages.pages_of(full)))
            for tag, vtag, pgs in jobs:
                for n, b in enumerate(pgs, 1):
                    win, done, cur = flow.shoot(b)
                    fn = f"{tag}{'_' + vtag if vtag else ''}_p{n}.png"
                    PILImage.fromarray(win).save(os.path.join(a.out, fn))
                    index.write(
                        f"{t}\t{n}\t{vtag or '-'}\t{fn}\t{int(done)}\t{int(cur)}\t{len(b) if b else 0}\n"
                    )
                    index.flush()
                    nshots += 1
    print(f"shots {nshots} → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
