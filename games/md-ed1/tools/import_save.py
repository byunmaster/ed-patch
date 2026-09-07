"""유저 세이브를 지금 빌드에 물린다 — emucap(mednafen)이 읽는 이름·크기로 넣어 준다.

    python3 tools/import_save.py            # 가장 알맹이가 많은 세이브를 골라 넣는다
    python3 tools/import_save.py --list     # 후보와 알맹이 양만 본다
    python3 tools/import_save.py <파일>     # 그 파일로

왜 필요한가 — 이름을 못 맞추면 **빈 슬롯 셋**이 뜨는데, 그게 「세이브가 안 맞는다」로 보인다.
2026-09-07 에 두 번 헛돌았다:

1. **이름은 롬 md5 다.** mednafen 은 `<롬 이름>.<롬 md5>.sav` 를 읽는다 — 빌드를 다시 하면
   md5 가 바뀌어 **전에 넣어 둔 세이브가 안 읽힌다.** 그래서 이 스크립트가 매번 다시 짓는다.
2. **크기는 16,384B 그대로다.** 이 카트의 SRAM 은 `0x200001~0x203fff` **홀수 바이트**인데,
   mednafen 은 그 범위를 통째로(짝수 자리는 패딩) 담는다. 홀수만 뽑아 8,192B 로 주면
   `Unexpected EOF` 로 **에뮬레이터가 뜨지도 않는다**(실측).
3. 🔴 **빈 세이브를 고르지 말 것.** 유저 폴더에 여럿이 있고 그중 둘은 설정만 든 빈 파일이었다
   (비-FF 바이트 14). 알맹이가 있는 건 하나뿐이었는데 그걸 모르고 빈 것을 넣어 놓고
   「형식이 다른가」를 한참 뒤졌다. ⇒ **비-FF 바이트 수로 고른다.**
"""

import hashlib
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

INBOX = Path("/root/save/md-ed1")
EMUCAP = Path.home() / ".local" / "share" / "emucap" / "mednafen"


def rom_path() -> Path:
    p = common.BUILD_DIR / common.BUILD_TAG.replace("/", "_") / "ed1-kr.bin"
    if not p.exists():
        raise SystemExit(f"빌드가 없다: {p} — python3 tools/build.py 부터")
    return p


def payload(p: Path) -> int:
    """알맹이 = 비-FF 바이트 수. 빈 세이브는 열댓 개뿐이다."""
    return sum(1 for b in p.read_bytes() if b != 0xFF)


def candidates() -> list[tuple[int, Path]]:
    return sorted(((payload(p), p) for p in INBOX.glob("*.sav")), reverse=True)


def sav_dirs(rom: Path) -> list[Path]:
    """emucap 은 포트마다 집을 따로 쓴다 — **이 롬을 띄운 적 있는 집**에만 넣는다.

    ⚠ 전부에 뿌리면 다른 게임 세션(새턴·PCE·SFC…)의 집을 건드린다. 읽히지는 않지만 남의 자리다.
    """
    out = []
    for d in sorted(EMUCAP.glob("*/sav")):
        log = d.parent / "mednafen.log"
        if d.is_dir() and log.exists() and rom.name in log.read_text(errors="replace"):
            out.append(d)
    return out


def main() -> None:
    cands = candidates()
    if not cands:
        raise SystemExit(f"세이브가 없다: {INBOX}")
    if "--list" in sys.argv:
        for n, p in cands:
            print(f"  {n:>6}B 알맹이  {p.name}")
        return
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src = Path(args[0]) if args else cands[0][1]
    rom = rom_path()
    md5 = hashlib.md5(rom.read_bytes()).hexdigest()
    dirs = sav_dirs(rom)
    if not dirs:
        raise SystemExit(f"이 롬({rom.name})을 띄운 emucap 집이 없다 — 먼저 한 번 띄운다")
    for d in dirs:
        dst = d / f"{rom.stem}.{md5}.sav"
        shutil.copyfile(src, dst)
        print(f"  {dst}")
    print(f"  ← {src.name} (알맹이 {payload(src)}B) · 롬 md5 {md5}")
    print("  ⚠ 에뮬레이터는 **띄울 때** 읽는다 — 이미 떠 있으면 다시 launch 한다.")


if __name__ == "__main__":
    main()
