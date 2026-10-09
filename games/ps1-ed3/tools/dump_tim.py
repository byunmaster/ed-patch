"""TIM 그림을 PNG 로 내린다 — **글자가 그림으로 박힌 자리**를 찾기 위한 눈.

타이틀 로고·버튼·창틀·오프닝/엔딩 컷은 문자열이 아니라 **그림**이다. 코드표로는 안 보이니
그려서 봐야 한다.

⚠ **산출물은 `work/review/` 로만 나간다 — 커밋 금지**(원본 그림이다, 루트 CLAUDE.md).
⚠ 압축 멤버는 `gmfz` 로 풀고, 안 풀리면 생 데이터로 본다(둘 다 TIM 을 품는다).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import gmfz
import tim


def members(disc):
    for path, (lba, size) in sorted(common.iso_files(disc).items()):
        if size > 16 << 20 or path.endswith("/"):
            continue
        data = common.read_lba(disc, lba, size)
        try:
            _, ents = common.arc_parse(data)
        except common.ArchiveError:
            ents = [(os.path.basename(path), 0, size)]
        for nm, off, sz in ents:
            if sz < 32:
                continue
            yield path, nm, bytes(data[off : off + sz])


def images(blob):
    """[(오프셋, 정보)] — 압축이면 풀고 나서 찾는다."""
    raw = blob
    try:
        raw, _ = gmfz.decompress(blob)
        raw = bytes(raw)
    except Exception:  # noqa: BLE001 — 안 눌린 멤버가 더 많다
        raw = blob
    return raw, tim.find_all(raw)


def catalog_path(disc):
    return os.path.join(common.ROOT, f"graphics_{disc}.json")


def check_catalog(disc):
    """자리표가 아직 맞는가 — **크기까지 대조**한다.

    🔴 자리는 「멤버 안 몇 번째 TIM 인가」다. `gmfz`·`tim` 을 고치면 밀릴 수 있고, 그러면
       엉뚱한 그림에 한글을 그리게 된다. 크기를 같이 보면 밀린 걸 그 자리에서 안다.
    """
    import json

    p = catalog_path(disc)
    if not os.path.exists(p):
        print(f"⏭ {disc}: 그림 자리표가 없다")
        return 0
    with open(p, encoding="utf-8") as f:
        want = json.load(f)["images"]
    found = {}
    for path, nm, blob in members(disc):
        _, ts = images(blob)
        if ts:
            found[f"{path}!{nm}"] = [(int(tim.width(t)), t["h"], t["bpp"]) for _, t in ts]
    bad = []
    for it in want:
        got = found.get(it["member"])
        if got is None or it["index"] >= len(got):
            bad.append(f"{it['member']} [{it['index']}] 가 없다")
            continue
        w, h, bpp = got[it["index"]]
        if (w, h, bpp) != (it["w"], it["h"], it["bpp"]):
            bad.append(
                f"{it['member']} [{it['index']}]: {w}x{h}/{bpp}bpp "
                f"(자리표는 {it['w']}x{it['h']}/{it['bpp']}bpp) — 자리가 밀렸다"
            )
    for m in bad[:8]:
        print(f"  🔴 {m}")
    print(f"{disc}: 그림 자리표 {len(want)}장 — {'🔴 밀렸다' if bad else '✅ 원본과 맞는다'}")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--only", help="이 문자열이 든 멤버만 (예: M01.DAT)")
    ap.add_argument("--min-px", type=int, default=0, help="이보다 작은 그림은 건너뛴다")
    ap.add_argument("--write", action="store_true", help="PNG 로 내린다")
    ap.add_argument(
        "--catalog", action="store_true", help="자리표(graphics_<disc>.json)와 대조 (게이트)"
    )
    a = ap.parse_args()
    common.verify_source(a.disc)
    if a.catalog:
        return check_catalog(a.disc)
    outdir = os.path.join(common.REVIEW_DIR, "tim", a.disc)
    n = 0
    for path, nm, blob in members(a.disc):
        key = f"{path}!{nm}"
        if a.only and a.only not in key:
            continue
        _, ts = images(blob)
        for i, (off, t) in enumerate(ts):
            w, h = int(tim.width(t)), t["h"]
            if w * h < a.min_px:
                continue
            n += 1
            tag = f"{os.path.basename(path)}_{nm.rsplit(chr(92), 1)[-1]}_{i}"
            tag = "".join(c if c.isalnum() or c in "._-" else "_" for c in tag)
            print(f"  {key} [{i}] 0x{off:X}  {w}x{h} {t['bpp']}bpp 팔레트 {t['pal_h']}")
            if a.write:
                os.makedirs(outdir, exist_ok=True)
                img = tim.to_image(t)
                # ⚠ **어두운 바탕에 올려 저장한다.** 글자가 그림으로 박힌 자리는 대개
                #   「흰 잉크 + 투명」 1비트 마스크라, 흰 바탕에 그리면 **아무것도 안 보인다**
                #   (실측: 타이틀 버튼 판이 새하얗게 나와 「빈 그림」으로 넘길 뻔했다).
                from PIL import Image

                bg = Image.new("RGBA", img.size, (24, 24, 34, 255))
                bg.alpha_composite(img)
                bg.convert("RGB").save(os.path.join(outdir, f"{tag}.png"))
    print(f"{a.disc}: 그림 {n}" + (f" → {outdir}  ⚠ 커밋 금지" if a.write else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
