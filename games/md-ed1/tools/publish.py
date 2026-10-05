"""지금 빌드를 파일서버(menu/)와 세이브 정본 자리에 게시한다 — 세이브는 **롬 md5 이름**으로 따라간다.

    python3 tools/publish.py          # 게시(기존 세이브가 다르면 .bak 로 남긴다)
    python3 tools/publish.py --dry    # 무엇을 어디로 옮길지만 보인다

왜 필요한가 — mednafen 은 `<롬 이름>.<롬 md5>.sav` 를 읽는다. 빌드를 다시 구우면 md5 가 바뀌어 **맥에서
`emu.sh md-ed1` 로 띄울 때 엔딩 전 세이브가 없어진다**(마스터 지적 2026-09-27). 그래서 게시 = 롬 + 그 md5
이름의 세이브 한 벌이다.

세이브 정본은 `~/save/md-ed1/md-ed1-slots.sav`(16KB, mednafen 그대로 = 폰 .srm 과 같은 바이트)다.
    슬롯 1 = 메뉴 확인용 극초반(L1 엘아스타, 새 게임 직후 왕의 방)
    슬롯 2 = 마스터가 메뉴 확인 중 저장한 것(L1 엘아스타)
    슬롯 3 = 엔딩 전(L99 바니스성 · 네 명 빛의 검 · 자동 전투 ON — 위로 한 화면 걸으면 아그니쟈)
⚠ 슬롯을 바꿀 땐 **게임 안에서 로드 → 저장**으로 만든다(체크섬은 게임이 계산). 슬롯 자리는 인터리브 파일에서
  1 = 0x400~0x1400 · 2 = 0x1400~0x2400 · 3 = 0x2400~0x3400, 머리 0x3E0~0x400 은 「MD-ED 02 <마지막 슬롯> <검사>」 두 벌.
"""

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

ROM = common.GAME_DIR / "work" / "build" / "md-ed1" / "ed1-kr.bin"
SAVES = Path.home() / "save" / "md-ed1"
SLOTS = SAVES / "md-ed1-slots.sav"
# ⚠ 파일서버는 **메인 트리**의 `.local/` 이다 — 워크트리엔 `.local/` 이 안 따라온다(루트 CLAUDE.md).
# `common.ROOT` 는 워크트리 뿌리라 그걸 쓰면 워크트리 안에 엉뚱한 게시 칸이 생긴다(2026-09-27 한 번 그랬다).
MAIN = Path(
    subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=common.ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
).parent
PUB = MAIN / ".local" / "cache" / "publish" / "md-ed1"
NAME = "Dragon Slayer - Eiyuu Densetsu (KR)"


def _put(src: Path, dst: Path, dry: bool) -> None:
    if dst.exists() and dst.read_bytes() != src.read_bytes() and dst.suffix == ".sav":
        print(f"  기존 {dst.name} 이 다르다 → {dst.name}.bak")
        if not dry:
            shutil.copy2(dst, dst.with_name(dst.name + ".bak"))
    print(f"  {src.name} → {dst}")
    if not dry:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def main(dry: bool) -> None:
    if not ROM.exists():
        raise SystemExit(f"빌드가 없다: {ROM}")
    if not SLOTS.exists() or SLOTS.stat().st_size != 16384:
        raise SystemExit(f"세이브 정본이 없거나 16KB 가 아니다: {SLOTS}")
    rom = ROM.read_bytes()
    md5 = hashlib.md5(rom).hexdigest()
    sha1 = hashlib.sha1(rom).hexdigest()
    sav = f"ed1-kr.{md5}.sav"
    print(f"롬 md5 {md5} · sha1 {sha1[:12]}")
    _put(ROM, PUB / "menu" / f"{NAME}.md", dry)
    _put(SLOTS, PUB / "menu" / f"{NAME}.srm", dry)
    _put(SLOTS, SAVES / sav, dry)
    _put(SLOTS, PUB / "saves" / sav, dry)
    _put(ROM, SAVES / "r5-menu" / f"{NAME}.md", dry)
    _put(SLOTS, SAVES / "r5-menu" / f"{NAME}.srm", dry)
    print("  ⚠ README(menu/README.txt)의 롬 해시 줄은 손으로 고친다")


if __name__ == "__main__":
    main("--dry" in sys.argv)
