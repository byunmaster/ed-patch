"""빈 슬롯 상자 msg1 — **도트로 찍은 PNG 를 실제 타일 수·압축 바이트로 잰다.**

도트판(웹)의 표시는 추정이다 — **이 스크립트가 정본**이다(관리자 요청 2026-09-16).
마스터가 그린 PNG(편집 영역 15×3칸 = 120×24px, 정수배 확대 가능)를 받아:

1. 흑백 2색으로 읽어(밝으면 잉크=흰 15, 어두우면 채움=14) 15×3 칸 캔버스를 만들고
2. 상자 테두리(열0·열16)를 붙여 17×3 전체 캔버스로 완성하고
3. `boxpack.sparse_catalog_and_map` 로 예약(49장, msg2·테두리가 실제 참조하는 원본 자리)
   자리는 공짜로 재사용하고 **빈 자리(19장)+새 자리(12장) = 새 타일 예산 31장** 안에서
   찍은 그림을 배정한 뒤
4. 실제 압축(`boxpack.pack`)까지 걸어 **타일 수 · 압축 바이트 · 합격 여부**를 낸다.

    python3 games/pce-ed1/tools/box_check.py <편집영역.png>
    python3 games/pce-ed1/tools/box_check.py --export-fixed  # box_fixed_tiles.json 다시 냄
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boxpack as bp
import common


def _main_tree() -> Path:
    """🔴 산출물은 **메인 트리**의 `.local/work/inbox/<게임>/` 에 둔다 — 마스터가 거기를 본다.
    워크트리 안에 떨어뜨리면 안 보인다(다른 게임 `qa_shot.py` 와 같은 규약)."""
    import subprocess

    g = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
        cwd=common.ROOT,
    ).stdout.strip()
    return Path(g).parent if g else common.ROOT


EDIT_W, EDIT_H = bp.MSG1_W - 2, bp.MSG1_H  # 15×3칸 — 열0·열(W-1)은 테두리라 편집 밖


def load_edit_png(path: str) -> np.ndarray:
    """편집 영역 PNG → 8×`EDIT_H` × 8×`EDIT_W` 색인 캔버스(14=채움·15=흰/잉크).

    ⚠ **정수배가 아니면 죽는다** — 120×24 의 배수가 아닌 크기를 조용히 리샘플하면
    픽셀 경계가 타일 경계와 어긋나 엉뚱한 타일이 나온다(patcher-checklist 「판단」).
    """
    im = Image.open(path).convert("L")  # 흑백 밝기로
    w0, h0 = 8 * EDIT_W, 8 * EDIT_H
    if im.width % w0 or im.height % h0:
        raise SystemExit(
            f"PNG 크기 {im.width}×{im.height} 가 {w0}×{h0} 의 정수배가 아니다 — "
            "편집 영역(15×3칸=120×24px)의 정수배 확대만 받는다"
        )
    sx, sy = im.width // w0, im.height // h0
    if sx != sy:
        raise SystemExit(f"가로·세로 배율이 다르다({sx} vs {sy}) — 정사각 배율만 받는다")
    arr = np.array(im)[::sy, ::sx]  # 좌상단 표본 — 안티에일리어싱 흐림을 피한다
    assert arr.shape == (h0, w0), arr.shape
    # 밝기 128 기준 이분(흑백 2색 토글 — 상자는 실질 2색이다, boxpack.py 상단 주석)
    return np.where(arr >= 128, 15, 14).astype(np.uint8)


def full_canvas(edit: np.ndarray) -> np.ndarray:
    """15×3칸 편집 캔버스(색인) → 17×3 전체 캔버스(테두리 붙임).

    ⚠ **맨 위·맨 아래 픽셀 행(행0·행23)은 편집 영역 안에서도 구조상 고정**이다
    (`frame()`: 상자 바깥 테두리, 모든 열에 걸쳐 값 0) — PNG 가 뭐라 찍었든 여기서
    되돌린다. 안 그러면 그 두 행만 「흰/채움 이분(14/15)」으로 잘못 읽혀 캔버스가
    깨진다(테스트 중 실측: 240픽셀 차이, 전부 이 두 행)."""
    cv = bp.frame(bp.MSG1_W, bp.MSG1_H)
    cv[:, 8:-8] = edit
    cv[0, :] = 0
    cv[-1, :] = 0
    return cv


def check(png_path: str, *, save_preview: str | None = None) -> dict:
    orig = bp.original_tiles()
    m2_words, border_words = bp.original_fixed_words()
    reserved = bp.reserved_indices(orig, m2_words, border_words)

    edit = load_edit_png(png_path)
    cv = full_canvas(edit)
    catalog, m1, _index = bp.sparse_catalog_and_map(cv, orig, reserved, bp.MSG1_W, bp.MSG1_H)

    def map_bytes(m, w, h):
        n = bp.map_nbytes(w, h) // 2
        m = m + [m[-1]] * (n - len(m))
        return b"".join(x.to_bytes(2, "little") for x in m)

    tiles_stream = bp.pack(b"".join(catalog), 4)
    map1_stream = bp.pack(map_bytes(m1, bp.MSG1_W, bp.MSG1_H), 2)
    total_bytes = 1 + len(tiles_stream) + 1 + len(map1_stream)
    new_tiles = len(catalog) - len(reserved & set(range(len(catalog))))
    ok = len(catalog) <= bp.MAX_TOTAL_TILES

    if save_preview:
        pal = {0: (20, 20, 20), 14: (0, 0, 150), 15: (255, 255, 255)}
        img = Image.new("RGB", (cv.shape[1], cv.shape[0]))
        for r in range(cv.shape[0]):
            for c in range(cv.shape[1]):
                img.putpixel((c, r), pal.get(int(cv[r, c]), (255, 0, 255)))
        img.resize((cv.shape[1] * 6, cv.shape[0] * 6), Image.NEAREST).save(save_preview)

    return {
        "reserved_tiles": len(reserved),
        "new_tiles": new_tiles,
        "total_tiles": len(catalog),
        "budget_tiles": bp.MAX_TOTAL_TILES,
        "tiles_bytes": len(tiles_stream) + 1,
        "map1_bytes": len(map1_stream) + 1,
        "total_bytes": total_bytes,
        "ok": ok,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("png", nargs="?", help="편집 영역 PNG(120×24px 정수배)")
    ap.add_argument(
        "--export-fixed", action="store_true", help="box_fixed_tiles.json 다시 낸다(도트판용)"
    )
    ap.add_argument("--preview", help="복원 캔버스를 이 경로에 PNG 로 저장(선택)")
    args = ap.parse_args()

    if args.export_fixed:
        out = _main_tree() / ".local" / "work" / "inbox" / common.GAME / "box_fixed_tiles.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        data = bp.export_fixed_tiles_json(str(out))
        print(f"{out}: 예약 {data['reserved_count']}장 · 새 타일 예산 {data['budget_for_new']}장")
        return

    if not args.png:
        raise SystemExit("PNG 경로를 주거나 --export-fixed 를 쓴다")

    r = check(args.png, save_preview=args.preview)
    tag = "✅ 예산 안" if r["ok"] else "❌ 예산 초과"
    print(
        f"{tag} — 타일 {r['total_tiles']}장(예약 {r['reserved_tiles']}+새 {r['new_tiles']}) "
        f"/ 천장 {r['budget_tiles']}장  ·  압축 {r['total_bytes']}B"
        f"(tiles {r['tiles_bytes']}B · map1 {r['map1_bytes']}B)"
    )
    if not r["ok"]:
        print(
            f"  {r['new_tiles']}장 중 {r['new_tiles'] - (r['budget_tiles'] - r['reserved_tiles'])}장을 줄여야 한다"
        )


if __name__ == "__main__":
    main()
