"""세이브를 지금 빌드(특히 test-debug)의 롬 md5 이름으로 emucap 집에 복사한다 — **원본 세이브는 건드리지 않는다**.

    ED_BUILD_TAG=debug python3 tools/import_save.py                 # 기본 원천 → 마스터용 「(DEBUG)」 롬 이름으로(+ 웹 실행기 세이브)
    ED_BUILD_TAG=test-debug python3 tools/import_save.py            # 시험 칸 — emucap 집에만
    ED_BUILD_TAG=debug python3 tools/import_save.py <파일>          # 그 파일로
    python3 tools/import_save.py --list                              # 후보와 알맹이 양만

왜 필요한가(md-ed1 `import_save.py` 와 같은 이유) — mednafen 은 `<롬 이름>.<롬 md5>.sav` 를 읽는다. 시험 빌드는 md5 가 제품과 달라
(디버그 패치 · 헤더 체크섬) **제품 세이브가 안 읽히고 빈 슬롯이 뜬다.** 크기는 16,384B 그대로(홀수 바이트만 8,192B 로 주면 에뮬이 안 뜬다).
알맹이(비-FF 바이트 수)가 가장 많은 파일을 기본으로 고른다 — 빈 세이브를 고르지 않으려는 것이다.

원천: `~/save/md-ed2/*.sav`(마스터 웹 세이브 — 슬롯 1 마스터 · 슬롯 2 ED2-END 후크 · 슬롯 3 보스 직전 L99). 🔴 원천은 **읽기만** 한다.
쓰는 곳은 이 롬을 띄운 적 있는 emucap 집의 `sav/` 뿐이다(다른 게임 집은 건드리지 않는다). 에뮬레이터는 **띄울 때** 읽으니 복사 뒤에 launch 한다.
"""

import hashlib
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

INBOX = Path.home() / "save" / "md-ed2"
EMUCAP = Path.home() / ".local" / "share" / "emucap" / "mednafen"
SAV_SIZE = 16384


def rom_path() -> Path:
    d = common.BUILD_DIR / common.BUILD_TAG.replace("/", "_")
    roms = sorted(d.glob("ed2-kr*.bin"))
    if len(roms) != 1:
        raise SystemExit(
            f"빌드가 없거나 둘 이상이다: {d} {roms} — 먼저 굽는다(status.md 「디버그 빌드」)"
        )
    return roms[0]


def payload(p: Path) -> int:
    """알맹이 = 비-FF 바이트 수."""
    return sum(1 for b in p.read_bytes() if b != 0xFF)


def candidates() -> list[tuple[int, Path]]:
    return sorted(
        (
            (payload(p), p)
            for p in INBOX.glob("*.sav")
            if p.stat().st_size == SAV_SIZE
            and "DEBUG" not in p.name  # 디버그 롬 사본은 원천이 아니다
        ),
        key=lambda t: (t[0], str(t[1])),
        reverse=True,
    )


def sav_dirs(rom: Path) -> list[Path]:
    """이 롬 이름을 띄운 적 있는 emucap 집만 — 남의 게임 집은 건드리지 않는다."""
    out = []
    for d in sorted(EMUCAP.glob("*/sav")):
        log = d.parent / "mednafen.log"
        if d.is_dir() and log.exists() and rom.name in log.read_text(errors="replace"):
            out.append(d)
    return out


def main() -> None:
    cands = candidates()
    if "--list" in sys.argv:
        for n, p in cands:
            print(f"  {n:>6}B 알맹이  {p.name}")
        return
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src = Path(args[0]) if args else (cands[0][1] if cands else None)
    if src is None or not src.exists():
        raise SystemExit(f"세이브가 없다: {INBOX}")
    if src.stat().st_size != SAV_SIZE:
        raise SystemExit(f"크기가 {SAV_SIZE}B 가 아니다: {src} ({src.stat().st_size}B)")
    rom = rom_path()
    md5 = hashlib.md5(rom.read_bytes()).hexdigest()
    dirs = sav_dirs(rom)
    if not dirs and common.BUILD_TAG != "debug":
        raise SystemExit(f"이 롬({rom.name})을 띄운 emucap 집이 없다 — 먼저 한 번 launch 한다")
    for d in dirs:
        dst = d / f"{rom.stem}.{md5}.sav"
        if dst.resolve() == src.resolve():
            raise SystemExit("원천과 목적지가 같다")
        shutil.copyfile(src, dst)
        print(f"  {dst}")
    if common.BUILD_TAG == "debug":
        # 파일서버(웹 실행기)용 — 롬 이름(stem)과 같은 이름의 세이브. 마스터 세이브(원천)와 갈라 둔다(원천은 안 건드린다)
        web = INBOX / f"{rom.stem}.sav"
        if web.resolve() == src.resolve():
            raise SystemExit("원천과 웹 세이브 목적지가 같다")
        shutil.copyfile(src, web)
        print(f"  {web}")
    print(f"  ← {src.name} (알맹이 {payload(src)}B) · 롬 md5 {md5} · 꼬리표 {common.BUILD_TAG}")
    print("  ⚠ 에뮬레이터는 **띄울 때** 읽는다 — 이미 떠 있으면 stop 하고 다시 launch 한다.")


if __name__ == "__main__":
    main()
