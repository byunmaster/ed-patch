"""음성 자막 확인 영상 — 단색 배경 + 엔진 대사창 모양 자막 + 원음 + 시각 (V01~V19).

    python3 games/ss-ed3/tools/voice_video.py V03 V04      # 골라서
    python3 games/ss-ed3/tools/voice_video.py --all        # V01~V19 → .local/work/inbox/ss-ed3/voice-video/V01.mp4 …

10-05 에 V17~V19 와 같은 방식으로 만들었던 것(정지 배경 + 창 + 원음 + 시각)을 다시 짠 것이다 — 그때 도구는 레포에 없다.
자료는 `voice_editor_data.build()`(= `voice.json` 의 지금 자막, 편집기와 같은 값)이고 시각은 `t_start`·`t_end` 다.
창은 `pos`(top/bottom, 기본 bottom)를 따른다. 얼굴은 안 그린다(그림이 없다). 화면은 320×240 을 3배로 키운다.
🔴 산출물에 원음이 들어 있다 — 커밋하지 않는다(`.local`). 구간별 정지 PNG 를 concat 목록으로 이어 구우므로 줄이 94개인 V12 도 몇 초면 된다.

창 모양: 안쪽 어두운 남색 + 밝은 테두리, 이름 한 줄(주황) + 본문 두 줄(흰색). 같은 화자가 이어 말하고 사이가 `HOLD_GAP` 초 이하면 창을 닫지 않고 글만 바꾼다
(`voice_sub.HOLD_GAP` — 실제 렌더러와 같은 규칙). 자막은 마지막 마디 끝 + 1초에 끈다.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import wave

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import sap
import voice_editor_data as ED
import voice_sub as VS

W, H, SCALE = 320, 240, 3
BG = (24, 28, 44)
WIN = (8, 160, 304, 72)  # x, y, w, h (320×240 기준) — 아래 창
WIN_TOP = (8, 8, 304, 72)  # 위 창(`pos: top`) — 원판 위 창 틀 y = −112 + 120
FILL, EDGE = (20, 24, 72), (190, 196, 255)
NAME_RGB, BODY_RGB = (255, 192, 96), (255, 255, 255)
TAIL = 1.0  # 마지막 마디 뒤 자막을 더 두는 초
FPS = 10


def repo_main():
    common = subprocess.run(
        ["git", "-C", C.GAME_DIR, "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return os.path.dirname(common)


def load_font(tmp=None):
    """Galmuri11 — `shared/fonts` 정본 BDF 를 읽는다(PIL 의 BDF 읽개는 한글·비ASCII 머리말에서 죽는다)."""
    sys.path.insert(0, os.path.join(repo_main(), "shared"))
    from fonts import load_bdf

    return load_bdf(os.path.join(repo_main(), "shared", "fonts", "Galmuri11.bdf"))


def put_text(im, xy, text, font, rgb):
    """BDF 글리프를 한 점씩 찍는다 — 가로 진행은 ASCII 6 · 그 밖 12."""
    glyphs, ascent = font
    x, y = xy
    for ch in text:
        g = glyphs.get(ord(ch))
        adv = 6 if ord(ch) < 0x300 else 12
        if g:
            w, h, xo, yo, rows = g
            nbits = ((w + 7) // 8) * 8
            top = y + ascent - (yo + h)
            for r, v in enumerate(rows):
                for cx in range(w):
                    if v & (1 << (nbits - 1 - cx)):
                        px, py = x + cx + xo, top + r
                        if 0 <= px < im.width and 0 <= py < im.height:
                            im.putpixel((px, py), rgb)
        x += adv


def frame(font, it):
    """320×240 한 장 — `it` 이 None 이면 창 없음."""
    im = Image.new("RGB", (W, H), BG)
    if it is not None:
        d = ImageDraw.Draw(im)
        x, y, w, h = WIN_TOP if it.get("pos") == "top" else WIN
        d.rectangle([x, y, x + w - 1, y + h - 1], fill=FILL, outline=EDGE)
        d.rectangle([x + 2, y + 2, x + w - 3, y + h - 3], outline=(90, 96, 170))
        put_text(im, (x + 12, y + 6), it["speaker_name"], font, NAME_RGB)
        for i, ln in enumerate(it["kr"].split("\n")[:2]):
            put_text(im, (x + 12, y + 24 + 17 * i), ln, font, BODY_RGB)
    return im.resize((W * SCALE, H * SCALE), Image.NEAREST)


def segments(items, total):
    """`[(시작, 끝, 항목|None)]` — 0 ~ total 을 빈틈없이 덮는다."""
    its = sorted(items, key=lambda x: x["t_start"])
    segs, t = [], 0.0
    for i, it in enumerate(its):
        s, e = it["t_start"], it["t_end"]
        nxt = its[i + 1] if i + 1 < len(its) else None
        if nxt and nxt["t_start"] - e <= VS.HOLD_GAP and nxt["speaker_name"] == it["speaker_name"] and nxt.get("pos") == it.get("pos"):
            e = nxt["t_start"]  # 창을 두고 글만 바꾼다 — 사이 빈틈에도 앞 글이 남는다
        e = min(max(e, s + 0.2), nxt["t_start"] if nxt else total)
        if s > t:
            segs.append((t, s, None))
        segs.append((s, e, it))
        t = e
    if its:  # 마지막 마디 뒤 TAIL 초 더 둔다
        last_end = segs[-1][1]
        segs.append((last_end, min(last_end + TAIL, total), segs[-1][2]))
        t = segs[-1][1]
    if t < total:
        segs.append((t, total, None))
    return segs


def wav_len(path):
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def make(vid, items, outdir, font, tmp):
    wavp = os.path.join(C.GAME_DIR, "work", "review", "sap", f"{vid}.wav")
    if not os.path.exists(wavp):
        sap.to_wav(vid)
    total = wav_len(wavp)
    segs = segments(items, total)
    lst, cache = [], {}
    for k, (s, e, it) in enumerate(segs):
        if e - s < 0.01:
            continue
        key = None if it is None else (it["idx"], it["kr"], it["speaker_name"], it.get("pos"))
        if key not in cache:
            p = os.path.join(tmp, f"{vid}-{len(cache):03d}.png")
            frame(font, it).save(p)
            cache[key] = p
        lst.append(f"file '{cache[key]}'\nduration {e - s:.3f}")
    lst.append(f"file '{cache[key]}'")  # concat 은 마지막 항목 duration 을 무시한다
    lp = os.path.join(tmp, f"{vid}.txt")
    open(lp, "w").write("\n".join(lst) + "\n")
    out = os.path.join(outdir, f"{vid}.mp4")
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            lp,
            "-i",
            wavp,
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            out,
        ],
        check=True,
    )
    return out, total, len(segs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenes", nargs="*")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    scenes = ED.SCENES if a.all else a.scenes
    if not scenes:
        ap.error("장면(V01…) 이나 --all")
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg 가 없다")
    items, _ = ED.build()
    outdir = os.path.join(repo_main(), ".local", "work", "inbox", "ss-ed3", "voice-video")
    os.makedirs(outdir, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        font = load_font(tmp)
        for v in scenes:
            out, total, n = make(v, [x for x in items if x["scene"] == v], outdir, font, tmp)
            print(f"{v}: {total:.1f}초 · 구간 {n} → {out}")


if __name__ == "__main__":
    main()
