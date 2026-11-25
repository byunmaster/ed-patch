"""BRAM 세이브(2KB) 슬롯별 읽기 전용 dump — 마스터가 보낸 세이브를 장별로 보관하려고(관리자 11-26). 롬·제품 불변.

    python3 tools/savedump.py <sav> [--emu] [--out <폴더>] [--cue <cue>]

- 기본(`--emu` 없이): BRAM 머리·항목(이름 `EIDEN_2.0n` = 슬롯 n · 크기 · 체크섬 칸)을 읽어 슬롯 목록만 낸다.
- `--emu`: 헤드리스 에뮬(`pcehl`)로 슬롯마다 타이틀 「이어하기」로 불러 **게임이 직접 그린 HUD**(장 띠 · 지명 · Lv)를 `<폴더>/slotN.png` 로 찍고,
  한 줄로 낸다. 장 띠·Lv 는 그림에서 읽는다(세이브 비트열을 풀지 않는다 — PCE I 의 `savefile.py` 같은 디스크립터 표 해독은 PCE II 에 아직 없다.
  RAM 에서 Lv·장을 한 바이트로 못 잡았다: 레벨 +1 에 값이 여럿 바뀌고, 장 변수 후보(`$27EB` 등)는 슬롯마다 다르지만 장 번호가 아니었다(시험: 전부 서장인데 값이 다 달랐다)).
저장 상태·세이브는 읽기만 한다(에뮬 안에서 불러볼 뿐 파일을 안 쓴다).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

NAME_PREFIX = b"EIDEN_2.0"


def entries(sav: bytes) -> list[tuple[int, int, int, int]]:
    """[(슬롯 번호, 이름 위치, 항목 시작(크기 필드), 크기)] — 이름 `EIDEN_2.0n` 을 찾아 앞 6바이트(크기 2 · 체크섬 2 · 00 00)를 머리로 본다."""
    out, pos = [], 0
    while True:
        i = sav.find(NAME_PREFIX, pos)
        if i < 0:
            return out
        n = sav[i + len(NAME_PREFIX)] - 0x30
        size = int.from_bytes(sav[i - 6 : i - 4], "little")
        if 1 <= n <= 5 and 0 < size < 0x400:
            out.append((n, i, i - 6, size))
        pos = i + len(NAME_PREFIX) + 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sav")
    ap.add_argument("--emu", action="store_true")
    ap.add_argument("--out", default="savedump")
    ap.add_argument(
        "--cue",
        default=str(Path(__file__).resolve().parents[1] / "work" / "build" / "pce-ed2" / "ed2.cue"),
    )
    a = ap.parse_args()
    sav = Path(a.sav).read_bytes()
    assert len(sav) == 2048 and sav[:4] == b"HUBM", "BRAM 2KB(HUBM)가 아니다"
    ents = entries(sav)
    print(f"{a.sav} — 슬롯 {len(ents)}개: " + ", ".join(str(e[0]) for e in ents))
    for n, name_at, start, size in ents:
        print(f"  슬롯 {n}: 이름 @{name_at:#06x} · 항목 @{start:#06x} · 크기 {size}")
    if not a.emu:
        return 0
    import pcehl
    from PIL import Image

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for n, *_ in ents:
        e = pcehl.Emu(a.cue, bram=a.sav)
        e.run(2500)
        e.press("run", 30, 1900)
        e.press("run", 30, 1500)
        e.press("run", 10, 300)
        e.press("right", 10, 30)
        e.press("i", 10, 400)  # 이어하기 → 파일 선택
        for _ in range(5 - n):
            e.press("up", 10, 20)  # 커서는 5번 칸에서 시작
        e.press("i", 10, 600)
        png = out / f"slot{n}.png"
        Image.fromarray(e.frame_img).save(png)
        print(f"슬롯 {n}: HUD {png} (장 띠·지명·Lv 는 그림에서)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
