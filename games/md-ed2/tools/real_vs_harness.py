"""대사 보기 하네스 ↔ 실게임 화면 대조 — 같은 스트림을 **실게임 흐름**(새 게임 → 왕좌의 방 → 병사에게 걸어가 말 걸기)과 **하네스**(`SAY` 우편함)로 찍어 글자 픽셀이 같은지 센다.

    python3 tools/real_vs_harness.py [--out DIR]

산출 `sweep/real-vs-harness/`: `real_NN.png`(실게임 쪽) · `harn_NN.png`(하네스 쪽) · `pair_NN.png`(위·아래 나란히) · `result.txt`(쪽별 흰 글자 픽셀 차).
흰 글자(R·G·B 모두 ≥236, 글 색은 238)만 비교한다 — 배경(길·바닥)과 이름 색(주황)은 위치가 달라 섞이므로 뺀다. 실게임 모듈은 말을 건 뒤 RAM `$FF6650` 에서 덤프해 하네스에 그대로 올린다.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_sweep as BS
import headless
import scene
import scene_sweep as S
from PIL import Image

ROOT = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "sweep"


def white(frame, y0=140):
    f = frame[y0 : y0 + 75, 50:270]  # 글 자리(이름 위~넷째 줄)·왼쪽 건물 벽 제외
    return (f[:, :, 0] >= 236) & (f[:, :, 1] >= 236) & (f[:, :, 2] >= 236)


def real_pages(c, st, n=6):
    """왕좌의 방 상태 → 걸어가 병사에게 말 → 쪽마다 글이 멈춘 뒤 찍는다."""
    c.load_state(st)
    c.run(30)
    for d, k in [("down", 50), ("down", 50), ("right", 40), ("right", 40), ("left", 40)]:
        c.hold(d)
        c.run(k)
        c.hold("")
        c.run(10)
    c.press("c", 6, 60)
    mod = c.ram(S.MOD_AT, 8720)
    pages = []
    for _ in range(n):
        for _ in range(60):  # 글이 뜨고 다 찍힐 때까지
            a = c.frame.copy()
            c.run(6)
            if (
                int(white(c.frame).sum()) > 200
                and int((np.abs(c.frame.astype(int) - a.astype(int)).sum(axis=2) > 0).sum()) < 40
            ):
                break
        pages.append(c.frame.copy())
        c.press("c", 5, 40)
    return mod, pages


def throne_pages(c):
    """새 게임 흐름의 왕좌의 방 이벤트 대사(창 없이 지도 위에 직접 찍힌다)를 쪽마다 찍는다 → (처음 글이 뜰 때의 모듈 덤프, 쪽 목록)."""
    c.run(1601)
    c.press("start", 20, 400)
    c.press("c", 15, 200)
    mod, pages, last = None, [], None
    for _ in range(560):
        c.press("c", 4, 50)
        f = c.frame.copy()
        if int(white(f).sum()) < 150 or int((f == (32, 206, 32)).all(axis=2).sum()) < 1500:
            continue  # 글이 없거나 지도가 아닌 화면(오프닝 자막) — 왕좌의 방 이벤트만
        for _ in range(20):  # 글이 멈출 때까지
            a = c.frame.copy()
            c.run(6)
            if int((np.abs(c.frame.astype(int) - a.astype(int)).sum(axis=2) > 0).sum()) < 40:
                break
        f = c.frame.copy()
        if mod is None:
            mod = c.ram(S.MOD_AT, 8720)
        if last is None or int((white(f) != white(last)).sum()) > 60:
            pages.append(f)
            last = f
    return mod, pages


def main() -> None:
    out = ROOT / "real-vs-harness"
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
    out.mkdir(parents=True, exist_ok=True)
    c = headless.Core(str(BS.ROM))
    st = S.new_game_state(c, ROOT / "scene")
    mod, real = real_pages(c, st)
    # 어느 스트림인가 — 실게임 쪽 첫 쪽의 글과 같은 한글 문안을 가진 스트림(하네스는 그 스트림을 띄운다)
    import json

    import common

    codes = json.loads(
        (common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")
    )
    rev = {v.to_bytes(2, "big"): k for k, v in codes.items() if isinstance(v, int)}
    m = scene.parse_module(mod)
    target = None
    for o, s_ in sorted(m.streams.items()):
        t = S.korean(b"".join(x.raw for x in s_.tokens if x.kind == "text"), rev)
        if "외출하시옵니까" in t:
            target = o
            break
    if target is None:
        sys.exit("실게임 모듈에서 병사 문안을 못 찾았다")
    c.load_state(st)
    c.poke(S.MOD_AT, mod)
    d = out / "h"
    d.mkdir(exist_ok=True)
    n, status = S.say(c, S.MOD_AT + target, d, "harn")
    harn = [np.array(Image.open(p).convert("RGB")) for p in sorted(d.glob("harn_*.png"))]
    lines = [f"스트림 {target:#x} · 실게임 {len(real)}쪽 찍음 · 하네스 {n}쪽({status})"]
    for i, (r, h) in enumerate(zip(real, harn, strict=False)):
        Image.fromarray(r).save(out / f"real_{i:02d}.png")
        Image.fromarray(h).save(out / f"harn_{i:02d}.png")
        pr, ph = white(r), white(h)
        diff = int((pr != ph).sum())
        lines.append(
            f"쪽 {i}: 실게임 흰 글자 {int(pr.sum())}px · 하네스 {int(ph.sum())}px · 차 {diff}px"
        )
        Image.fromarray(np.vstack([r, h])).save(out / f"pair_{i:02d}.png")

    # ── 둘째: 왕좌의 방 이벤트 쪽(이름 없이 최대 줄) — 실게임 쪽을 모두 모아, 하네스가 같은 모듈의 스트림을 띄운 쪽 가운데 글 픽셀이 같은 것을 찾는다
    c2 = headless.Core(str(BS.ROM))
    tmod, tpages = throne_pages(c2)
    lines.append(f"왕좌의 방 이벤트: 실게임 {len(tpages)}쪽")
    if tmod is not None:
        tm = scene.parse_module(tmod)
        c2.load_state(st if False else c2.save_state())
        hp = []
        for o, s_ in sorted(tm.streams.items()):
            t = S.korean(b"".join(x.raw for x in s_.tokens if x.kind == "text"), rev)
            if sum(1 for ch in t if "가" <= ch <= "힣") < 6:
                continue
            c.load_state(st)
            c.poke(S.MOD_AT, tmod)
            dd = out / "t"
            dd.mkdir(exist_ok=True)
            for p in dd.glob("*.png"):
                p.unlink()
            S.say(c, S.MOD_AT + o, dd, "t")
            hp += [np.array(Image.open(p).convert("RGB")) for p in sorted(dd.glob("t_*.png"))]
            if len(hp) > 400:
                break
        hmasks = [white(h) for h in hp]
        ok = 0
        for i, r in enumerate(tpages):
            rm = white(r)
            best = min((int((rm != hm).sum()) for hm in hmasks), default=-1)
            ok += best == 0
            lines.append(
                f"  이벤트 쪽 {i}: 하네스 {len(hmasks)}쪽 중 가장 가까운 것과 흰 글자 차 {best}px"
            )
            Image.fromarray(r).save(out / f"throne_real_{i:02d}.png")
        lines.append(f"왕좌의 방 이벤트: 차 0px 인 쪽 {ok}/{len(tpages)}")
    (out / "result.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
