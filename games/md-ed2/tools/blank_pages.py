"""촬영 묶음의 「글자 없는 쪽」 수 — 창 안쪽(대사 영역)의 글자 잉크가 6px 미만인 장을 센다. manifest 의 「글자 없는 쪽 수」 열.

    python3 tools/blank_pages.py <폴더> [--list 파일]      # 폴더 아래 png 전부

md-ed2(MD 320×224)는 대사가 필드 위에 **테두리 없이** 아래쪽(y146~206 · x36~292)에 얹힌다 — 그 영역에서 글자색(흰색 R·G·B>215 · 이름 주황)만 센다.
배경(맵)에 흰 점이 있는 장면이 있어 6px 문턱은 느슨한 하한이다(「빈 창」 의심 목록이지 결함 확정이 아니다 — 변수 버퍼가 빈 대사 · ▼ 만 뜬 쪽 · 전투 검은 화면이 섞인다).
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

BOX = (slice(146, 206), slice(36, 292))
BATTLE_BOX = (slice(182, 222), slice(8, 308))  # 전투 창은 아래쪽 테두리 상자(y178~222) — 필드 창 영역은 몬스터 그림이 겹친다
MIN_INK = 6


def ink(f: Path, box=BOX) -> int:
    a = np.asarray(Image.open(f).convert("RGB")).astype(int)[box]
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    white = (r > 215) & (g > 215) & (b > 215)
    orange = (r > 215) & (g > 140) & (g < 215) & (b < 120)
    return int(white.sum() + orange.sum())


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = sys.argv[sys.argv.index("--list") + 1] if "--list" in sys.argv else None
    if out and out in args:
        args.remove(out)
    files = sorted(Path(args[0]).rglob("*.png"))
    box = BATTLE_BOX if "--battle" in sys.argv else BOX
    low = [f for f in files if ink(f, box) < MIN_INK]
    if out:
        Path(out).write_text("\n".join(map(str, low)) + "\n", encoding="utf-8")
    print(f"장 {len(files)} · 글자 없는 쪽 {len(low)}")


if __name__ == "__main__":
    main()
