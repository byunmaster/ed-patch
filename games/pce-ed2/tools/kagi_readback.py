"""「」『』 되읽기 — 제품 이미지 정적 풀에서 네 글리프를 비트맵으로 찾아(`pairs.KoGlyphs`) 지금 도안(마스터 파일 또는 옛 방식)과 바이트가 같은지 본다.

    python3 kagi_readback.py [--iso <이미지>]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
import font
import pairs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", default=str(common.BUILD_DIR / "pce-ed2" / "ed2.iso"))
    a = ap.parse_args()
    kg = pairs.KoGlyphs(a.iso)
    bad = [ch for ch in font.KAGI if ch not in kg.static]
    src = "마스터 도안 파일" if font.KAGI_MASTER_FILE.exists() else "옛 방식(16×12 반쪽+SHIFT)"
    print(f"  「」『』 되읽기 [pce-ed2] — 도안 출처 {src} · 풀에서 못 찾음 {bad or 0}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
