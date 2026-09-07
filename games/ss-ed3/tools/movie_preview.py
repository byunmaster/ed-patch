"""자막 검수용 영상 — 원본 무비에 우리 문안을 **태워서** mp4 로 굽는다.

    python3 games/ss-ed3/tools/movie_preview.py            # 대사 있는 편 전부
    python3 games/ss-ed3/tools/movie_preview.py M01 M17    # 골라서
    python3 games/ss-ed3/tools/movie_preview.py --srt      # SRT 만

🔴 **검수용이지 패치가 아니다.** 실제 패치는 소프트섭(엔진이 그린다)이라 영상을 안 건드린다
   (`docs/movie-subtitles.md`). 이 mp4 는 **사람이 싱크·문안을 눈으로 보려고** 만든다.

⚠ 산출물은 `work/review/` 다 — 원본 영상이 통째로 들어가니 **커밋 절대 금지**.

준비물: `ffmpeg`(`film_cpk` 디먹서 + `cinepak` 디코더 + libass). 한글 폰트가 하나 필요하다.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

SCRIPT = os.path.join(C.GAME_DIR, "script", "movie.json")
CPK_DIR = os.path.join(C.REVIEW_DIR, "cpk")
OUT_DIR = os.path.join(C.REVIEW_DIR, "movie_sub")
#   ⚠ 폰트는 이 머신에 있는 것을 쓴다 — 없으면 `fc-list` 로 한글 폰트를 찾아 바꾼다
FONT = os.environ.get("ED_SUB_FONT", "Apple SD Gothic Neo")
#   2 배로 키운다(320×224 → 640×448). `neighbor` 라야 원본 픽셀이 안 뭉갠다
SCALE = 2
#   보내기 한도(30MiB)를 넘으면 화질을 한 단계 낮춰 다시 굽는다
LIMIT_MB = 28
VAAPI_DEV = os.environ.get("ED_VAAPI", "/dev/dri/renderD128")
#   화질 단계 — 앞에서부터 시도하고 한도를 넘으면 다음 것으로 (VA-API 는 CQP 의 qp, x264 는 crf)
#   ⓘ 첫 값은 **가장 긴 편(M01, 189초)이 한 번에 한도 안에 들어오는** 자리로 잡았다.
#     실측(M01): GPU qp24=33.8MiB · qp28=22.9 · qp32=14.5 / CPU crf20=31.4 · crf26=16.3 · crf30=9.8
QUALITY = (28, 32, 36)
QUALITY_SW = (26, 30, 34)


def hw_ok():
    """VA-API 로 **인코딩**할 수 있나.

    🔴 **디코딩은 GPU 로 못 넘긴다.** 원본이 Cinepak(1991년 코덱)이라 VA-API 프로파일에
      아예 없다(H.264·HEVC·VP8/9·AV1·MPEG2·MJPEG 뿐). 자막을 태우는 `subtitles`(libass)도
      시스템 메모리에서 도는 CPU 필터다.
      ⇒ **디코드·필터는 CPU, 인코드만 GPU** 다. 그래도 x264 `slow` 가 제일 비싼 자리라
        이득이 크다.
    """
    if os.environ.get("ED_NO_HW"):
        return False
    if not os.path.exists(VAAPI_DEV) or not os.access(VAAPI_DEV, os.R_OK | os.W_OK):
        return False
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20
        )
    except Exception:
        return False
    return " h264_vaapi " in r.stdout


def ts(sec):
    """`0:00:06,000` — SRT 시각."""
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h}:{m:02d}:{s:02d},{ms:03d}"


def srt(lines):
    out = []
    for i, (a, b, t) in enumerate(lines, 1):
        out.append(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--srt", action="store_true", help="SRT 만 만들고 굽지 않는다")
    ap.add_argument("--no-hw", action="store_true", help="GPU 인코딩을 쓰지 않는다")
    a = ap.parse_args()

    if not a.srt and not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg 가 없다 — `apt-get install ffmpeg`")
    hw = (not a.srt) and (not a.no_hw) and hw_ok()
    if not a.srt:
        print(f"  인코더: {'VA-API (GPU)' if hw else 'libx264 (CPU)'}")
    sc = json.load(open(SCRIPT, encoding="utf-8"))
    names = a.names or [k for k in sorted(sc) if not k.startswith("_") and sc[k]]
    os.makedirs(OUT_DIR, exist_ok=True)

    for n in names:
        lines = sc.get(n) or []
        if not lines:
            print(f"  {n} 건너뜀 (대사 없음)")
            continue
        sp = os.path.join(OUT_DIR, f"{n}.srt")
        open(sp, "w", encoding="utf-8").write(srt(lines))
        if a.srt:
            print(f"  {n} → {sp} ({len(lines)}줄)")
            continue
        src = os.path.join(CPK_DIR, f"{n}.CPK")
        if not os.path.exists(src):
            raise SystemExit(f"{src} 가 없다 — 먼저 원본에서 꺼낸다")
        dst = os.path.join(OUT_DIR, f"{n}.mp4")
        #   ⚠ 자막 경로에 `:` `'` 가 있으면 필터 문법이 깨진다 — 그래서 그 폴더로 들어가서 돈다
        #   🔴 `BorderStyle=3`(불투명 상자)은 **줄마다 상자를 그려 두 줄일 때 위아래가 겹친다**
        #     (유저 스크린샷 2026-08-29). 글자 테두리(`BorderStyle=1`)로 바꾸면 겹칠 상자가 없다.
        style = (
            f"FontName={FONT},FontSize=20,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,BackColour=&HA0000000,"
            "BorderStyle=1,Outline=2,Shadow=1,MarginV=16"
        )
        #   🔴 **시각을 화면에 새긴다**(2026-09-01). 싱크 검수는 「몇 초에 어긋났나」를
        #     사람이 불러 줘야 하는데, 눈대중으로는 0.5 초를 못 짚는다. 자동으로 잡아 보려
        #     했지만 발화 속도가 1.9~8.9 자/초로 흩어져 못 쓴다(정답지 18 점으로 실측).
        #     ⇒ 재는 자를 화면에 얹는 게 제일 싸게 먹힌다.
        clock = (
            "drawtext=text='%{pts\\:hms\\:0}':x=8:y=8:fontcolor=yellow:fontsize=22:"
            "box=1:boxcolor=black@0.6:boxborderw=4"
        )
        base = (
            f"scale={320 * SCALE}:{224 * SCALE}:flags=neighbor,"
            f"subtitles={n}.srt:force_style='{style}',{clock}"
        )
        #   화질을 한 단계씩 낮추며 한도 안에 들어올 때까지 — 30MiB 넘으면 못 보낸다
        for q in (QUALITY if hw else QUALITY_SW):
            if hw:
                #   ⚠ `format=nv12,hwupload` 로 **필터가 끝난 뒤** GPU 로 올린다.
                #     VA-API 인코더는 NV12 서피스만 받는다.
                cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-init_hw_device", f"vaapi=va:{VAAPI_DEV}", "-filter_hw_device", "va",
                    "-i", os.path.abspath(src),
                    "-vf", base + ",format=nv12,hwupload",
                    "-c:v", "h264_vaapi", "-rc_mode", "CQP", "-qp", str(q),
                    "-profile:v", "high",
                    "-c:a", "aac", "-b:a", "96k",
                    os.path.abspath(dst),
                ]  # fmt: skip
            else:
                cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", os.path.abspath(src),
                    "-vf", base,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", str(q), "-preset", "veryfast",
                    "-c:a", "aac", "-b:a", "96k",
                    os.path.abspath(dst),
                ]  # fmt: skip
            t0 = time.time()
            r = subprocess.run(cmd, cwd=OUT_DIR, capture_output=True, text=True)
            if r.returncode:
                print(r.stderr[-800:])
                raise SystemExit(f"{n} 굽기 실패")
            mb = os.path.getsize(dst) / 1048576
            dt = time.time() - t0
            if mb <= LIMIT_MB:
                break
        tag = f"GPU qp{q}" if hw else f"CPU crf{q}"
        print(f"  {n}  자막 {len(lines):3}줄  {mb:5.1f}MiB  {dt:5.1f}초  [{tag}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
