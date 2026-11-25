"""줄·쪽 나눔 재촬영 화면 검사 — `msg_viewer.lua` 가 찍은 쪽 PNG 를 **화면 픽셀**로 재고 조판 계산값과 대조한다(번역 규칙 2-16, 10-26).

    .venv/bin/python games/sfc-ed1/tools/shot_check.py <촬영 폴더(단위별 하위 폴더)> --units units.json [--sheet <출력 폴더> --before <전 촬영 폴더>]

촬영 폴더 구조: `<폴더>/<단위 id>/shots/v0001_<쪽>.png`. `units.json` = {id: [후 조판, 전 조판]}.
화면 검사(창 영역 y 14..100 × x 10..156):
  빈 쪽 · 넘침/잘림(글자 잉크가 글줄 영역 밖 — 오른쪽 x≥150·왼쪽 x<10) · 줄 수 대조(화면 글줄 수 ↔ 조판 계산 줄 수) ·
  마지막 창 한 어절(마지막 쪽이 한 줄·짧은 잉크) · 첫 칸 공백(줄 들머리 잉크가 다른 줄보다 4px 이상 안쪽 — 따옴표 들임은 정보로만).
낱말 가운데 꺾임은 화면으로는 못 가르고 조판 지표(g)가 계산한다 — 이 도구는 계산값과 어긋난 화면(= 훅이 다르게 꺾은 곳)만 센다.
"""

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import typeset

BOX = (14, 100, 10, 156)  # y0, y1, x0, x1
RIGHT_LIMIT = 150  # 글줄 영역 오른쪽 끝(17칸 = 136px, x 10..146 + 여유)
LEFT_LIMIT = 10


def _ink(path: str) -> np.ndarray:
    a = np.array(Image.open(path).convert("RGB")).astype(int)
    return a[:, :, 1] >= 150  # 글자 = 흰·노랑·하늘색 전부(창 바탕 보라·틀 파랑은 G 가 낮다)


def analyse(path: str) -> dict:
    """창 틀(가로줄 y=11·24·101 · 세로줄 x=9·158)은 빼고 글 잉크만 잰다. 글줄 영역 = x 16..152, 이름 띠가 있으면 그 아래."""
    m = _ink(path)
    full = m[:, 16:150].sum(axis=1) >= 100  # 창 틀 가로줄(이름 띠 구분선 포함)
    y0 = 12
    for y in range(18, 30):
        if full[y]:
            y0 = y + 1  # 이름 띠 아래부터가 본문
            break
    m = m.copy()
    m[full, :] = False
    m[90:102, 74:94] = False  # ▼ 대기 커서
    body = m[y0:100, 11:157]
    n = int(body[:, 5:142].sum())
    rows = np.where(body[:, 5:142].any(axis=1))[0]
    lines, starts = 0, []
    if len(rows):
        y = rows[0]
        slots = {int((r - y) // 16) for r in rows}
        lines = len(slots)
        for sl in sorted(slots):
            band = body[y + 16 * sl : y + 16 * sl + 16, 5:142]
            cols = np.where(band.any(axis=0))[0]
            if len(cols):
                starts.append(int(cols[0]))
    over = int(body[:, 143:].sum() + body[:, :3].sum())  # x ≥ 154 · x ≤ 13 — 글줄 영역 밖
    width = 0
    if n:
        cols = np.where(body[:, 5:142].any(axis=0))[0]
        width = int(cols[-1] - cols[0] + 1)
    indent = sum(1 for s0 in starts if s0 - min(starts) >= 4) if len(starts) >= 2 else 0
    return {"ink": n, "lines": lines, "over": over, "width": width, "indent": indent}


def _distinct(paths: list[str]) -> list[str]:
    """연속으로 같은 화면(타자 끝난 장 반복)은 하나로."""
    out, last = [], None
    for p in paths:
        h = hash(Image.open(p).convert("RGB").tobytes())
        if h != last:
            out.append(p)
        last = h
    return out


def computed_pages(res: str) -> list[int]:
    """쪽별 화면 줄 수 = 본문 줄 + 화자 머리(이름 띠 줄) 1."""
    res = typeset._HEADER.sub("\x01", res)
    out = []
    for p in typeset._PAGE_SPLIT.split(res):
        if p in ("<FF>", "<EF>", "<FE>", "<E0>") or "<E2>" in p or "클리어" in p:
            continue
        head = "\x01" in p
        p = p.replace("\x01", "")
        rows = [ln for ln in typeset._CTRL_TOK.sub("", p).split("\n") if ln.split()]
        head = head or any(
            typeset._TAGLINE.fullmatch(ln.strip()) for ln in rows
        )  # 파티 화자 표지 줄도 화면엔 이름 띠 줄이다
        n = len([ln for ln in rows if not typeset._TAGLINE.fullmatch(ln.strip())])
        if n:
            out.append(n + head)
    return out


def check(folder: str, units: dict) -> dict:
    out = {
        "units": 0,
        "shots": 0,
        "blank": 0,
        "over": 0,
        "linemismatch": 0,
        "lastword": 0,
        "indent": 0,
        "missing": 0,
        "aligned": 0,
        "detail": [],
    }
    for uid, (after, _before) in units.items():
        files = sorted(glob.glob(os.path.join(folder, uid, "shots", "*.png")))
        if not files:
            out["missing"] += 1
            continue
        out["units"] += 1
        comp = computed_pages(after)
        # 단위가 끝나도 원판 스크립트가 다음 메시지로 이어 가 쪽이 더 찍힌다 — 계산 쪽 수까지만 본다(그 뒤는 이웃 메시지)
        shots = [analyse(p) for p in _distinct(files)][: max(len(comp), 1)]
        out["shots"] += len(shots)
        plain = not re.search(
            r"<(?:EF|FE|FC|FA|F[0-9A-F]|EE)\b", after
        )  # 분기·호출·조각 단위는 화면 쪽 ↔ 계산 쪽이 1:1 이 아니다 — 줄 수 대조에서 뺀다
        aligned = (
            plain and len(shots) == len(comp)
        )  # 찍힌 쪽이 계산 쪽 수만큼일 때만 줄 수를 대조한다(`<FE>`·`<EF>` 조각은 화면 쪽이 계산 쪽과 1:1 이 아니다)
        out["aligned"] = out.get("aligned", 0) + aligned
        for k, s in enumerate(shots):
            if s["ink"] < 6:
                out["blank"] += 1
                out["detail"].append(f"{uid} 쪽{k + 1}: 빈 쪽")
            if s["over"] > 3 and s["ink"] >= 6 and s["over"] < 200:
                out["over"] += 1
                out["detail"].append(f"{uid} 쪽{k + 1}: 넘침/잘림 잉크 {s['over']}px")
            if s["indent"]:
                out["indent"] += 1
            if aligned and s["ink"] >= 6 and s["lines"] != comp[k]:
                out["linemismatch"] += 1
                out["detail"].append(f"{uid} 쪽{k + 1}: 화면 {s['lines']}줄 ↔ 계산 {comp[k]}줄")
        if (
            len(shots) >= 2
            and shots[-1]["lines"] == 1
            and 0 < shots[-1]["width"] < 40
            and re.search(r"<FF>", after)
        ):
            out["lastword"] += 1
            out["detail"].append(f"{uid}: 마지막 창이 짧은 한 줄(폭 {shots[-1]['width']}px)")
    return out


def sheet(after_dir: str, before_dir: str, units: dict, outdir: str, per: int = 12) -> list[str]:
    os.makedirs(outdir, exist_ok=True)
    ids = [u for u in units if glob.glob(os.path.join(after_dir, u, "shots", "*.png"))]
    paths = []
    cw, ch = 150, 92
    for si in range(0, len(ids), per):
        chunk = ids[si : si + per]
        W = 90 + 6 * cw
        im = Image.new("RGB", (W, ch * len(chunk)), (20, 20, 28))
        d = ImageDraw.Draw(im)
        for r, uid in enumerate(chunk):
            d.text((4, r * ch + 4), uid[:8], fill=(255, 255, 255))
            d.text((4, r * ch + 18), "전→ / 후→", fill=(160, 160, 255))
            for col, base in enumerate((before_dir, after_dir)):
                ps = _distinct(sorted(glob.glob(os.path.join(base, uid, "shots", "*.png"))))[:3]
                for k, p in enumerate(ps):
                    c = Image.open(p).convert("RGB").crop((8, 12, 8 + cw, 12 + ch - 2))
                    im.paste(c, (90 + (col * 3 + k) * cw, r * ch))
        pth = os.path.join(outdir, f"sheet_{si // per + 1:02d}.png")
        im.save(pth)
        paths.append(pth)
    return paths


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--units", required=True)
    ap.add_argument("--sheet")
    ap.add_argument("--before")
    a = ap.parse_args()
    units = json.loads(Path(a.units).read_text(encoding="utf-8"))
    r = check(a.folder, units)
    det = r.pop("detail")
    print(json.dumps(r, ensure_ascii=False))
    for x in det[:40]:
        print(" ", x)
    if a.sheet and a.before:
        print("\n".join(sheet(a.folder, a.before, units, a.sheet)))


if __name__ == "__main__":
    main()
