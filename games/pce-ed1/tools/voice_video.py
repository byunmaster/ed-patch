#!/usr/bin/env python3
"""음성 자막 확인 영상 — 단색 배경 + 게임 창 모양 자막 + 실제 음성(ss-ed3 V01~V16 방식).

  sh scripts/heavy.sh python3 games/pce-ed1/tools/voice_video.py [토막 이름…]     # 이름을 안 주면 전부
입력: `voice_editor_data.py` 가 낸 data.json · clips.json · voice/<clip>.wav (편집기 폴더). 출력: `<메인 트리>/.local/work/inbox/pce-ed1/voice-video/<clip>.mp4`.
자막 글자는 게임이 쓰는 12×12 글리프(`font.glyph`)를 그대로 찍는다 — 줄바꿈도 `typeset` 가 정한 대로. 번역이 없는 쪽은 「미번역」 안내 창이다.
한 파일 15MB 이하(정지 화면이라 보통 1MB 안팎). 시각은 정적 모델이다 — 창이 열리는 지연은 실측한 장면만 값이 있다(`open_delay_measured`).
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import font
import typeset
import voice_editor_data as D

W, H, SCALE = 344, 232, 3
BG, PANEL, WIN, EDGE = (0, 0, 0), (24, 24, 120), (16, 16, 96), (200, 168, 64)
FG, NAME, DIM = (255, 255, 255), (255, 224, 96), (150, 150, 190)


def draw_text(img: Image.Image, x: int, y: int, text: str, color) -> None:
    px = img.load()
    for ch in text:
        adv = typeset.SPACE_PX if ch in typeset.NARROW else 12
        if ch in (" ", "　"):
            x += adv if ch == " " else 12
            continue
        try:
            g = font.glyph(ch)
        except Exception:  # noqa: BLE001 — 글꼴에 없는 글자는 건너뛴다
            x += adv
            continue
        for r in range(12):
            bits = int.from_bytes(g[2 * r : 2 * r + 2], "big")
            for c in range(12):
                if bits >> (15 - c) & 1 and 0 <= x + c < W and 0 <= y + r < H:
                    px[x + c, y + r] = color
        x += adv


def frame(speaker: str, lines: list[str], note: str = "") -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([228, 20, 318, 210], fill=PANEL)  # 오른쪽 상태창 자리
    if lines or speaker:
        d.rectangle([34, 124, 210, 206], fill=WIN, outline=EDGE)
        if speaker:
            draw_text(img, 42, 128, speaker, NAME)
        for i, ln in enumerate(lines[:3]):
            draw_text(img, 42, 144 + 17 * i, ln, FG)
    if note:
        draw_text(img, 40, 40, note, DIM)
    return img.resize((W * SCALE, H * SCALE), Image.NEAREST)


def page_frame(row: dict) -> Image.Image:
    if row["kr"]:
        lines = row["kr"].split("\n")
        return frame(row["speaker_name"], lines)
    return frame(row["speaker_name"], ["(번역 전)", "게임에는 원문이", "그대로 나옵니다"], "")


def build_clip(clip: str, rows: list[dict], meta: dict, wav: Path, out: Path) -> None:
    dur = meta["voice_sec"]
    segs: list[tuple[Image.Image, float]] = []
    t = 0.0
    for r in rows:
        if r["t_start"] > t + 1e-3:
            segs.append((frame("", [], ""), r["t_start"] - t))
        segs.append((page_frame(r), max(0.1, r["t_end"] - r["t_start"])))
        t = r["t_end"]
    if t < dur:
        segs.append((frame("", [], ""), dur - t))
    with tempfile.TemporaryDirectory() as td:
        lst = ["ffconcat version 1.0"]
        for i, (im, d) in enumerate(segs):
            p = Path(td) / f"s{i:03d}.png"
            im.save(p)
            lst += [f"file '{p}'", f"duration {d:.3f}"]
        lst.append(f"file '{Path(td) / f's{len(segs) - 1:03d}.png'}'")
        (Path(td) / "list.txt").write_text("\n".join(lst) + "\n")
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(Path(td) / "list.txt"), "-i", str(wav),
             "-vf", "fps=10,format=yuv420p", "-c:v", "libx264", "-crf", "30", "-preset", "veryfast", "-c:a", "aac", "-b:a", "64k", "-shortest", str(out)],
            check=True,
        )


def main() -> int:
    ed = D.main_tree() / ".local" / "work" / "inbox" / "pce-ed1" / "voice-editor"
    rows = json.loads((ed / "data.json").read_text("utf-8"))
    clips = {c["clip"]: c for c in json.loads((ed / "clips.json").read_text("utf-8")) if not c.get("skipped")}
    want = sys.argv[1:] or list(clips)
    outdir = D.main_tree() / ".local" / "work" / "inbox" / "pce-ed1" / "voice-video"
    for name in want:
        r = [x for x in rows if x["clip"] == name]
        out = outdir / f"{name}.mp4"
        build_clip(name, r, clips[name], ed / clips[name]["wav"], out)
        mb = out.stat().st_size / 1e6
        print(f"{name}: {len(r)}쪽 · {clips[name]['voice_sec']:.1f}초 · {mb:.2f}MB")
        assert mb <= 15, f"{name} 가 15MB 를 넘었다"
    return 0


if __name__ == "__main__":
    sys.exit(main())
