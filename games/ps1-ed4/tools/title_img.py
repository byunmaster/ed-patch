"""타이틀·오프닝 그림(TIZ) 추출 · 검산 · 재삽입 멤버 만들기 — **그림을 마스터가 그린다**(마스터 10-24). 번역·판단 없음.

    python3 tools/title_img.py export <출력폴더>           # 원본 크기 PNG · 팔레트 · README
    python3 tools/title_img.py check  <PNG> <C_857.TIZ>     # 규격·색 수·압축 후 크기가 한도 안인가
    python3 tools/title_img.py member <PNG> <C_857.TIZ> <out.tiz>   # 검산 통과 시 재삽입용 멤버 바이트 저장

🔴 한도: 압축 뒤 크기 ≤ **원본 멤버 크기**(그보다 작으면 아카이브 안 자리가 남는다 — 다른 멤버는 안 움직인다). 넘으면 아카이브 재배치(마지막 섹터
여유 안)로도 해결되지 않는 경우가 있어 거부한다. 인코더는 `tiz_fit`(런·쌍·사전, 되풀기 검산) — 원 압축기보다 약하면 한도를 못 맞출 수 있다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import tiz_fit
from PIL import Image

from shared.ps1 import gmf_arc, tim, tiz

ARC = "/O/SC401.DAT"
# 이름 → 쓰임(실측: 시험 빌드에서 단색으로 바꿔 어느 화면에 뜨는지 봤다 — `docs/status.md` 그림 글자)
ASSETS = {
    "C_857.TIZ": "타이틀 화면(메뉴가 뜨는 배경 + 로고)",
    "C_847.TIZ": "데모 반복(가사 화면 뒤) 로고 화면",
    "C_848.TIZ": "데모 반복 로고 변형(인물 그림이 비치는 로고, 페이드)",
    "C_845.TIZ": "오프닝 내레이션 글(4bpp, 투명 배경 흰 글씨)",
    "C_846.TIZ": "오프닝 가사 글(4bpp)",
    "C_858.TIZ": "오프닝 일러스트(글자 없음 — 참고)",
}


def member(base, data=None):
    data = data or common.read_file(ARC)
    for n, o, s in gmf_arc.arc_parse(data)[1]:
        if n.split("\\")[-1] == base:
            return n, data[o : o + s]
    raise SystemExit(f"{ARC} 에 {base} 가 없다")


def load(base):
    n, blk = member(base)
    raw = tiz.decompress(blk)
    return n, blk, raw, tim.parse(raw)


def swatch(t, row, path):
    n = 16 if t["bpp"] == 4 else 256
    pal = tim.palette_of(t, row)
    cols = 16
    im = Image.new("RGBA", (cols * 12, ((n + cols - 1) // cols) * 12), (0, 0, 0, 0))
    for i, c in enumerate(pal[:n]):
        px = Image.new("RGBA", (12, 12), tim.rgba(c))
        im.paste(px, ((i % cols) * 12, (i // cols) * 12))
    im.save(path)


def export(outdir):
    os.makedirs(outdir, exist_ok=True)
    lines = []
    for base, use in ASSETS.items():
        _n, blk, raw, t = load(base)
        row = tim.best_palette(t)
        im = tim.to_image(t, row)
        stem = base.split(".")[0]
        im.save(os.path.join(outdir, f"{stem}.png"))
        bg = Image.new("RGBA", im.size, (48, 48, 80, 255))
        bg.alpha_composite(im)
        bg.convert("RGB").save(os.path.join(outdir, f"{stem}_on_dark.png"))
        swatch(t, row, os.path.join(outdir, f"{stem}_palette.png"))
        pal = tim.palette_of(t, row)
        used = {}
        w = int(tim.width(t))
        for b in t["pix"]:
            if t["bpp"] == 8:
                used[b] = used.get(b, 0) + 1
        if t["bpp"] == 4:
            for b in t["pix"]:
                for v in (b & 15, b >> 4):
                    used[v] = used.get(v, 0) + 1
        trans = [i for i in used if i < len(pal) and pal[i] == 0]
        best = min(len(tiz_fit.encode_plain(raw)), len(tiz_fit.encode_dict(raw)))
        lines.append(
            f"{base:10s} {w}x{t['h']} {t['bpp']}bpp · CLUT {t['pal_h']}벌 × {16 if t['bpp'] == 4 else 256}색 · 쓰인 색인 {len(used)}개"
            f" · 투명 색인 {trans or '없음'} · 원 압축 {len(blk):,}B · 우리 인코더로 원본 다시 압축 {best:,}B · {use}"
        )
        with open(os.path.join(outdir, f"{stem}_palette.txt"), "w", encoding="utf-8") as f:
            f.write("색인\tR G B\tRGB555(hex)\t픽셀 수\n")
            for i, c in enumerate(pal):
                r, g, b, _a = tim.rgba(c)
                f.write(
                    f"{i}\t{r} {g} {b}{' (투명)' if c == 0 else ''}\t{c:04X}\t{used.get(i, 0)}\n"
                )
    return lines


def check(png, base, quiet=False):
    """(통과?, 메시지, 새 멤버 바이트|None)."""
    _n, blk, raw, t = load(base)
    img = Image.open(png).convert("RGBA")
    w, h = int(tim.width(t)), t["h"]
    if img.size != (w, h):
        return False, f"크기 {img.size} ≠ {w}x{h}", None
    # 5비트 채널로 깎은 뒤 색 수를 센다(PS1 색은 15비트)
    colors = {tim.color15(*p) for p in img.getdata()}
    n_pal = 16 if t["bpp"] == 4 else 256
    if len(colors) > n_pal:
        return False, f"색 {len(colors)}개 > {n_pal}(15비트 색으로 센 값 — 투명도 1색이다)", None
    new = tim.replace(raw, t, img)
    blk2 = min(tiz_fit.encode_plain(new), tiz_fit.encode_dict(new), key=len)
    assert tiz.decompress(blk2) == new
    ok = len(blk2) <= len(blk)
    msg = (
        f"{'✅' if ok else '🔴'} {base}: 색 {len(colors)}/{n_pal} · 압축 {len(blk2):,}B / 한도 {len(blk):,}B"
        f" ({'여유 ' + format(len(blk) - len(blk2), ',') if ok else '초과 ' + format(len(blk2) - len(blk), ',')}B)"
    )
    return ok, msg, blk2 if ok else None


def main(argv):
    if len(argv) >= 3 and argv[1] == "export":
        common.verify_source()
        for ln in export(argv[2]):
            print(ln)
        return 0
    if len(argv) >= 4 and argv[1] in ("check", "member"):
        common.verify_source()
        ok, msg, blk = check(argv[2], argv[3])
        print(msg)
        if argv[1] == "member" and ok:
            with open(argv[4], "wb") as f:
                f.write(blk)
            print(f"→ {argv[4]}")
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
