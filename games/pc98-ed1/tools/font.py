"""한글 글리프 표 — 16×16 1bpp, 글자당 32B.

이 게임의 CG 루틴이 CGROM 에서 읽어 오는 것이 **16행 × 좌·우 1바이트**다(status.md 2절).
한글도 같은 기하로 만들면 후킹한 자리에 그대로 흘려 넣을 수 있다.

폰트는 **Neo둥근모**(`shared/fonts/neodgm.ttf`, OFL) — 16×16 네이티브 설계다.
⚠ Galmuri 는 11px 설계라 16 셀에 넣으면 여백만 는다. 반대로 16px 설계를 11 셀에 우겨넣으면
받침 있는 글자가 무너진다 — 근거는 `shared/fonts/README.md`.

🔴 **결정적이어야 한다**(루트 CLAUDE.md 제1 원칙). TTF 렌더는 환경을 탈 수 있어
`--check` 가 두 번 그려 대조하고, 표 전체의 sha1 을 **얼려 둔다**.
"""

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

TTF = common.ROOT / "shared" / "fonts" / "neodgm.ttf"
CELL = 16
STRIDE = CELL * 2  # 행당 2바이트 × 16행 = 32B

# 표 전체 지문 — 폰트나 렌더가 바뀌면 여기가 먼저 운다. `--freeze` 로만 갱신한다.
TABLE_SHA1 = "516e5a8f031241ee0e129bcd3e5d9a3384f9f96c"


def ksc_syllables() -> list[str]:
    """KS X 1001 완성형 한글 2,350자를 **코드 순서**로."""
    out = []
    for hi in range(0xB0, 0xC9):
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes([hi, lo]).decode("euc-kr")
            except UnicodeDecodeError:
                continue
            if "가" <= ch <= "힣":
                out.append(ch)
    return out


def render(ch: str, font: ImageFont.FreeTypeFont) -> np.ndarray:
    img = Image.new("1", (CELL, CELL), 0)
    ImageDraw.Draw(img).text((0, 0), ch, font=font, fill=1)
    return np.array(img, dtype=np.uint8)


def pack32(bits: np.ndarray) -> bytes:
    """(16, 16) 0/1 → 32B. **행당 2바이트, MSB 우선** — CG 루틴이 읽는 꼴 그대로."""
    grid = np.zeros((CELL, CELL), dtype=np.uint8)
    h, w = min(CELL, bits.shape[0]), min(CELL, bits.shape[1])
    grid[:h, :w] = bits[:h, :w]
    return np.packbits(grid, axis=1).tobytes()


def build() -> tuple[list[str], bytes]:
    font = ImageFont.truetype(str(TTF), CELL)
    syllables = ksc_syllables()
    table = b"".join(pack32(render(ch, font)) for ch in syllables)
    return syllables, table


def preview(syllables: list[str], table: bytes, path: Path, cols: int = 48) -> None:
    """미리보기 PNG — 구워 넣기 전에 눈으로 본다(유저 확인 절차)."""
    n = len(syllables)
    rows = (n + cols - 1) // cols
    img = Image.new("1", (cols * CELL, rows * CELL), 0)
    arr = np.array(img, dtype=np.uint8)
    for i in range(n):
        g = np.unpackbits(
            np.frombuffer(table[i * STRIDE : (i + 1) * STRIDE], dtype=np.uint8)
        ).reshape(CELL, CELL)
        y, x = (i // cols) * CELL, (i % cols) * CELL
        arr[y : y + CELL, x : x + CELL] = g
    Image.fromarray(arr * 255).convert("L").save(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="두 번 그려 결정성을 본다")
    ap.add_argument("--freeze", action="store_true", help="표 지문을 얼린다")
    ap.add_argument("--preview", action="store_true", help="미리보기 PNG 를 낸다")
    args = ap.parse_args()

    syllables, table = build()
    digest = hashlib.sha1(table).hexdigest()
    print(f"음절 {len(syllables):,}자 · 표 {len(table):,}B · sha1 {digest}")

    if args.check:
        _, again = build()
        if again != table:
            raise SystemExit("🔴 두 번 그린 결과가 다르다 — 렌더가 환경을 탄다")
        print("결정성 OK (두 번 그려 같은 바이트)")

    if TABLE_SHA1 and digest != TABLE_SHA1 and not args.freeze:
        raise SystemExit(f"🔴 표 지문이 바뀌었다\n  want {TABLE_SHA1}\n  got  {digest}")

    if args.freeze:
        print(f'→ TABLE_SHA1 = "{digest}" 로 갱신한다')

    if args.preview:
        out = common.REVIEW_DIR / "font_preview.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        preview(syllables, table, out)
        print(f"→ {out}")

    # 빈 글리프 = 렌더 실패. 하나라도 있으면 폰트나 셀이 안 맞는 것이다.
    blanks = [
        syllables[i] for i in range(len(syllables)) if not any(table[i * STRIDE : (i + 1) * STRIDE])
    ]
    if blanks:
        raise SystemExit(f"🔴 빈 글리프 {len(blanks)}자: {''.join(blanks[:20])}")
    print("빈 글리프 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
