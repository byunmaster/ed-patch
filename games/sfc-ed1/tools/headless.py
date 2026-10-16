#!/usr/bin/env python3
"""Mesen2 헤드리스(`--testRunner` + Lua) 실행기 — 검수 일괄(전투·메시지 보기)을 emucap 호출 없이 몬다.

    python3 games/sfc-ed1/tools/headless.py --rom <롬> --lua battle_sweep --out <폴더> BT_JOBS=0-5 BT_MAXF=3500
    python3 games/sfc-ed1/tools/headless.py --rom <롬> --lua msg_viewer --out <폴더> MV_IDS=0x2000-0x2010

- 바이너리는 `vendor/emucap/adapters/mesen2/.../publish/Mesen`(emucap 빌드 그대로, 읽기 전용). 화면은 `DISPLAY`(기본 `:99`, Xvfb).
- 🔑 테스트러너는 **기본 100초에 강제 종료**(종료 코드 255, 로그가 중간에 끊긴다) — `--timeout=<초>` 가 필요하다(실행기가 붙인다). Lua 가 파일을 쓰려면 **명령줄 옵션** `--debug.scriptWindow.allowIoOsAccess=true` 가 필요하다(설정 파일이 아니다) — 이게 빠지면 `io.open` 이
  조용히 nil 이 된다. `--donotSaveSettings`·`--preferences.singleInstance=false`·`--snes.port1.type=SnesController` 도 같이.
- `NAME=값` 인자는 그대로 환경변수로 Lua 에 간다. 롬은 `ED_DEBUG=1` 빌드(`work/build/test-debug/…(DEBUG).sfc`)여야 메뉴 A 가 열린다.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

LUA_DIR = Path(__file__).resolve().parent / "lua"
PUBLISH = "adapters/mesen2/work/mesen/bin/linux-x64/Release/linux-x64/publish/Mesen"


def mesen_bin() -> Path:
    """워크트리면 메인 트리의 vendor 를 거슬러 찾는다(`vendor/` 는 워크트리에 링크되거나 없다)."""
    here = Path(__file__).resolve()
    for p in [here, *here.parents]:
        cand = p / "vendor" / "emucap" / PUBLISH
        if cand.exists():
            return cand
    common_dir = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        cwd=here.parent,
        check=False,
    ).stdout.strip()
    cand = (Path(common_dir).resolve().parent) / "vendor" / "emucap" / PUBLISH
    if cand.exists():
        return cand
    raise SystemExit(
        "emucap 의 Mesen 바이너리를 못 찾았다 — `sh scripts/check-updates.sh --update` 후 `adapters/mesen2/build.sh`"
    )


def check_rom_fresh(rom: Path) -> dict:
    """촬영 롬이 **지금 입력으로 구운 빌드 칸의 롬**인지 확인한다 — 아니면 `SystemExit`(2026-10-19 옛 롬 전수 촬영 사고).

    롬은 `work/build/<꼬리표>/` 안에 있어야 하고(롬 사본·임시 경로 금지), 옆 `manifest.json` 의 `output_sha1` 이 롬 sha1 과 같고
    `input_fingerprint`(`common.rom_input_fingerprint`)가 지금 값과 같아야 한다. 통과하면 sha·칸 경로·지문을 돌려준다(`rom.json` 으로 남는다).
    """
    rom = rom.resolve()
    slot = rom.parent
    if slot.parent.resolve() != common.BUILD_DIR.resolve():
        raise SystemExit(f"촬영 롬은 빌드 칸 {common.BUILD_DIR}/<꼬리표>/ 안의 파일이어야 한다(롬 사본 금지): {rom}")
    man = slot / "manifest.json"
    if not man.exists():
        raise SystemExit(f"빌드 칸에 manifest.json 이 없다 — 지금 입력으로 다시 구워라: {slot}")
    info = json.loads(man.read_text(encoding="utf-8"))
    sha = hashlib.sha1(rom.read_bytes()).hexdigest()
    if info.get("output_sha1") != sha:
        raise SystemExit(f"롬 sha1 {sha[:8]} 이 manifest 의 output_sha1 {str(info.get('output_sha1'))[:8]} 과 다르다 — 빌드 칸이 섞였다")
    now = common.rom_input_fingerprint()
    if info.get("input_fingerprint") != now:
        raise SystemExit(
            f"낡은 롬이다 — 이 롬을 구운 뒤 빌드 입력(tools/*.py · textmap · shared/text)이 바뀌었다(롬 {sha[:8]}). 다시 구운 뒤 찍어라"
        )
    return {"sha1": sha, "slot": str(slot.relative_to(common.ROOT)), "input_fingerprint": now}


def run(rom: Path, lua: str, out: Path, env: dict[str, str], timeout: int = 7200, rom_info: dict | None = None) -> int:
    out.mkdir(parents=True, exist_ok=True)
    if rom_info is not None:  # 촬영 때 쓴 롬을 자동으로 남긴다 — manifest 가 이 파일을 읽는다
        (out / "rom.json").write_text(json.dumps(rom_info, ensure_ascii=False, indent=1), encoding="utf-8")
    e = {
        **os.environ,
        "DISPLAY": os.environ.get("DISPLAY") or ":99",  # 빈 문자열이어도 :99 (헤드리스 실행이 로그 없이 멎던 원인)
        "LUA_DIR": str(LUA_DIR),
        "BT_OUT": str(out),
        **env,
    }
    cmd = [
        str(mesen_bin()), "--testRunner", str(rom), str(LUA_DIR / f"{lua}.lua"),
        "--debug.scriptWindow.allowIoOsAccess=true", "--preferences.singleInstance=false",
        "--snes.port1.type=SnesController", "--donotSaveSettings", f"--timeout={timeout}",
    ]  # fmt: skip
    return subprocess.run(
        cmd,
        env=e,
        timeout=timeout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--rom", type=Path, default=common.BUILD_DIR / "Dragon Slayer - Eiyuu Densetsu (DEBUG).sfc"
    )
    ap.add_argument(
        "--lua",
        required=True,
        choices=sorted(p.stem for p in LUA_DIR.glob("*.lua") if p.stem != "lib"),
    )
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--control",
        action="store_true",
        help="대조군 롬(원판 JP 디버그 등 우리 빌드가 아닌 롬) — 최신성 확인을 건너뛴다. 산출 manifest 에 대조군으로 적힌다",
    )
    ap.add_argument("env", nargs="*", help="NAME=값")
    a = ap.parse_args()
    if a.control:
        info = {"control": True, "sha1": hashlib.sha1(a.rom.read_bytes()).hexdigest(), "path": a.rom.name}
    else:
        info = check_rom_fresh(a.rom)
    return run(a.rom, a.lua, a.out, dict(x.split("=", 1) for x in a.env), rom_info=info)


if __name__ == "__main__":
    raise SystemExit(main())
