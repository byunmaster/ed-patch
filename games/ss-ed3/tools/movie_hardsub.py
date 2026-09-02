"""무비 하드섭 — 원본 CPK 에 우리 자막을 **태워** 같은 크기로 되끼운다.

    python3 games/ss-ed3/tools/movie_hardsub.py --list        # 편별 현황
    python3 games/ss-ed3/tools/movie_hardsub.py M05           # 한 편 굽기
    python3 games/ss-ed3/tools/movie_hardsub.py --all         # 이 디스크의 자막 있는 편 전부
    python3 games/ss-ed3/tools/movie_hardsub.py M05 --preview # PNG 한 장 (굽기 전 확인용)

⭐ **소프트섭을 접고 여기로 왔다**(2026-08-31). 엔진이 그리게 하려던 계획은
   `docs/movie-subtitles.md` 에 있었는데, 인게임 음성 자막을 파다가 **엔진의 텍스트 그리기가
   VDP1 스프라이트 VRAM 을 덮는다**는 걸 실측으로 잡았다(`devlog.md` 「자막이 인물을 먹는다」).
   같은 그리기를 무비 위에 얹을 이유가 없다.

🔴 **「cinepak 인코더가 없다」는 옛 결론은 틀렸다.** ffmpeg 7.1 에는 `film_cpk` 디먹서·**먹서**와
   `cinepak` 인코더가 다 있다. 왕복이 성립한다:

       CPK → (디코드) → 자막 합성 → (cinepak 인코드) → CPK

   실측(M05, 13.5초): 3,497,432B → 3,115,138B 로 **작아진다**(원본이 1996년 인코더라
   여유가 있다). 남는 자리는 0 으로 채워 **크기를 원본에 맞춘다** — `build.py` 는
   길이가 같아야 제자리에 쓴다(`assert len(new) == size`).

⚠ **글꼴은 시스템 폰트를 안 쓴다.** libass + 설치 폰트로 구우면 머신마다 바이트가 갈리고
   (제1 원칙 「빌드는 결정적이어야 한다」) 화면에도 안 어울린다. **게임에 넣는 것과 같은
   Galmuri11** 을 직접 찍어 PNG 로 얹는다 — 인게임 글자와 같은 픽셀 격자가 된다.

⚠ **다시 굽는 건 비싸다** — M01(189초)이 10 분쯤 걸린다. 그래서 `work/derived/cpk/` 에
   캐시하고 **자막·설정이 바뀔 때만** 다시 굽는다(열쇠 = 문안 + 스타일 + 원본 크기 + ffmpeg 판).
   `build.py` 는 **캐시에 있는 것만** 넣고, 없는 편은 세어서 알린다(빌드를 10 분 세우지 않는다).

⚠ 산출물엔 원본 영상이 통째로 들어간다 — `work/` 라 gitignore 다. **커밋 절대 금지.**
"""

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
import common as C

from shared import fonts

SCRIPT = os.path.join(C.GAME_DIR, "script", "movie.json")
CACHE = os.path.join(C.OUT_DIR, "cpk")

# ── 조판 ─────────────────────────────────────────────────────────────────────
#   ⓘ 화면은 320×224 다. 갈무리11 은 한글 12 · 라틴 8 이 자리 폭이고 글자 높이는 11 이다.
W, H = 320, 224
LINE_H = 13
BOTTOM = 10  # 마지막 줄 밑 여백
DY = fonts.GALMURI11_DY  # 게임 폰트와 같은 베이스라인 보정
CELL = 12  # 한 글자를 찍는 칸 (한글 자리 폭)
ADV_LATIN = 8


def _adv(ch):
    """그 글자가 먹는 가로 자리 — 갈무리11 실측(라틴 8 · 한글 12)."""
    return ADV_LATIN if ord(ch) < 0x1100 else CELL


def _draw(text):
    """자막 한 장 → `(H, W)` 0/1 배열. 여러 줄은 `\\n` 으로 가른다."""
    import numpy as np

    bdf = fonts.galmuri()
    rows = text.split("\n")
    out = np.zeros((H, W), dtype=np.uint8)
    top0 = H - BOTTOM - LINE_H * len(rows)
    for r, line in enumerate(rows):
        wpx = sum(_adv(c) for c in line)
        x = (W - wpx) // 2
        y = top0 + r * LINE_H
        for c in line:
            if c != " ":
                b = bdf.bits(c, dy=DY, rows=LINE_H, width=CELL)
                h, w = b.shape
                if 0 <= y and y + h <= H and 0 <= x and x + w <= W:
                    out[y : y + h, x : x + w] |= b
            x += _adv(c)
    return out


def png(text, path):
    """자막 한 장을 RGBA PNG 로 — 흰 글자 + 검은 1px 테두리(영상 위에서 읽히게)."""
    import numpy as np
    from PIL import Image

    m = _draw(text)
    edge = np.zeros_like(m)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                edge |= np.roll(np.roll(m, dy, 0), dx, 1)
    edge &= ~m
    rgba = np.zeros((H, W, 4), dtype=np.uint8)
    rgba[..., :3] = (m[..., None] * 255).astype("uint8")  # 글자 흰색 · 테두리 검정
    rgba[..., 3] = (m | edge) * 255
    Image.fromarray(rgba, "RGBA").save(path)
    return path


# ── 굽기 ─────────────────────────────────────────────────────────────────────
def lines(name):
    with open(SCRIPT, encoding="utf-8") as f:
        return [tuple(x) for x in json.load(f).get(name) or []]


def ffmpeg_ver():
    out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=False).stdout
    return out.split("\n")[0].strip()


def enc_key(name, size):
    """**영상 자체**를 다시 인코딩해야 하나 — 문안·조판·인코더가 여기 들어간다.

    🔴 `key` 와 갈라 둔 이유가 있다. 종전엔 열쇠가 하나였고 `enc.CPK` 재사용 분기가
       **파일 존재만 보고** 탔다. 그래서 **자막을 고쳐도 옛 영상이 그대로 나갔고**,
       그 분기가 새 열쇠를 덮어써서 **다음부터는 유효해 보였다**(2026-09-02 실측 —
       M01·M08 문안을 고쳤는데 「캐시 재사용」으로 지나갔다).
       ⇒ 재인코딩 여부는 **이 열쇠**로만 정한다.
    """
    h = hashlib.sha1()
    h.update(json.dumps(lines(name), ensure_ascii=False).encode())
    h.update(f"|{size}|{W}x{H}|{LINE_H}|{BOTTOM}|{DY}|{CELL}|{ADV_LATIN}|".encode())
    h.update(ffmpeg_ver().encode())
    h.update(" ".join(ENC_OPTS).encode())
    return h.hexdigest()


def key(name, size):
    """최종물이 지금 소스의 것인가 — 영상 열쇠 + 머리 규약."""
    return hashlib.sha1(f"{enc_key(name, size)}|stab{STAB_VER}".encode()).hexdigest()


# ── STAB 되맞추기 ────────────────────────────────────────────────────────────
#   🔴 **ffmpeg 은 시간 기준을 원본과 다르게 쓴다.** 원본 STAB 은 `base_freq=600` 에
#     영상 `info1=타임스탬프 · info2=지속(40)`, 음성 `info1=0xFFFFFFFF · info2=1` 인데,
#     ffmpeg 은 `base_freq=15 · 지속=1` 로 쓰고 **키프레임 아님 비트(bit31)** 까지 세운다.
#     비율은 같아서 「지속/기준」을 계산하는 재생기라면 결과가 같지만, **기준을 상수로 든
#     재생기라면 40 배 빨라진다.** 인코더 옵션으로는 못 맞춘다(`-enc_time_base 1/600` 은
#     600fps 로 뽑아 버린다) — 그래서 **머리만 원본 규약으로 다시 쓴다.**
#   ⚠ 키프레임 비트는 **떨어뜨린다** — 원본이 한 번도 안 세운다. 정보를 버리는 셈이지만,
#     이 재생기가 그 비트를 어떻게 읽는지 모르는 채로 원본에 없던 값을 넣지 않는다.
STAB_BASE = 600  # 원본 실측
STAB_VER = 3  # 이 규약을 고치면 올린다 (캐시 열쇠에 들어간다)
AUDIO_INFO1 = 0xFFFFFFFF
ALIGN = 4  # 원본 실측 — 표본·스트립·청크 길이가 전부 4 의 배수다


def retime_stab(b, base=STAB_BASE):
    """ffmpeg 이 쓴 STAB 을 **원본 규약**으로 되맞춘다 — 크기·자리는 안 바뀐다."""
    i = b.find(b"STAB")
    if i < 0:
        raise SystemExit("STAB 이 없다 — film_cpk 가 아니다")
    _, cur, n = struct.unpack(">III", b[i + 4 : i + 16])
    if cur == base:
        return b
    if base % cur:
        raise SystemExit(f"시간 기준이 안 나눠떨어진다 ({base} / {cur})")
    k = base // cur
    out = bytearray(b)
    struct.pack_into(">I", out, i + 8, base)
    for j in range(n):
        p = i + 16 + j * 16
        off, size, i1, i2 = struct.unpack(">IIII", out[p : p + 16])
        if i1 != AUDIO_INFO1:  # 영상 — 타임스탬프·지속을 새 기준으로
            i1 = (i1 & 0x7FFFFFFF) * k
            i2 *= k
        struct.pack_into(">IIII", out, p, off, size, i1, i2)
    return bytes(out)


# ── 스트립은 둘, 112 줄씩 ────────────────────────────────────────────────────
#   🔴 **ffmpeg 기본값으로 구우면 화면 가운데 띠에 색 블록이 튄다**(2026-09-04 실측, M01).
#     ffmpeg 의 cinepak 인코더는 프레임마다 스트립 수를 1~3 으로 고르는데(224 · 112+112 ·
#     76+76+72), 엔진(`0x06060d50` → 3 스트립 경로 `0x06060ca4`)은 **스트립 1 과 2 에 같은
#     코드북 버퍼**(arg6+0x2000)를 준다. 슬레이브 SH-2 가 스트립 1 코드북 → 스트립 2 코드북
#     순으로 덮어쓴 뒤, **마스터가 스트립 1 의 벡터를 그 버퍼로 푼다** — 가운데 띠(76~152)만
#     엉뚱한 항목으로 그려진다. 게다가 스트립 N 의 목적지가 「앞 스트립 + **자기** 높이」라
#     72 줄짜리 셋째 스트립은 4 줄 위에 그려진다. 원본은 **항상 2 스트립 × 112 줄**이고
#     세가 라이브러리는 그 경우만 맞다. ⇒ 인코더에 둘로 못 박는다(캐시 열쇠에 든다).
ENC_OPTS = ["-min_strips", "2", "-max_strips", "2"]
STRIPS = 2
STRIP_H = H // STRIPS


def check_strips(b):
    """표본 전부가 2 스트립 × 112 줄인가 — 아니면 그 표본 번호를 돌려준다."""
    bad = []
    for j, f in _video_samples(b):
        ns = struct.unpack_from(">H", f, 8)[0]
        p, ok = 12, ns == STRIPS
        for _ in range(ns):
            ssz = struct.unpack_from(">I", f, p)[0] & 0xFFFFFF
            y0, _x0, y1, _x1 = struct.unpack_from(">HHHH", f, p + 4)
            ok = ok and y1 - y0 == STRIP_H
            p += ssz
        if not ok:
            bad.append(j)
    return bad


def _video_samples(b):
    i = b.find(b"STAB")
    hdr = struct.unpack_from(">I", b, 4)[0]
    n = struct.unpack_from(">I", b, i + 12)[0]
    for j in range(n):
        off, size, i1, _i2 = struct.unpack_from(">IIII", b, i + 16 + j * 16)
        if i1 != AUDIO_INFO1:
            yield j, b[hdr + off : hdr + off + size]


# ── 4 바이트 정렬 ────────────────────────────────────────────────────────────
#   🔴 **ffmpeg 산물을 그대로 넣으면 재생 1 초 안에 CPU 가 멈춘다**(2026-09-04 실측, M01).
#     엔진의 Cinepak 파서(`0x06060d50`)는 스트립 머리를 `mov.w @(r8+6)` 처럼 **워드로 읽는데**,
#     ffmpeg 의 cinepak 인코더는 청크 길이를 홀수로도 뽑는다(M01: 청크 2,995 · 표본 오프셋
#     1,768 개가 홀수). 홀수 주소 워드 접근 = SH-2 어드레스 에러 → `0x0600094E` 에서 정지.
#     원본은 청크·스트립·표본이 **모두 4 의 배수**다(인코더가 안에서 0 으로 채웠다).
#   ⓘ 청크 끝에 0 을 붙여도 무해하다 — 코드북 해독기(`0x06061f38`)는 「끝 − 6」까지만 돌아
#     여분 < 6 이면 항목이 안 는다. 벡터 해독기(`0x06062440`)는 가로·세로 블록 수로 돌지
#     길이를 안 본다. 원본의 마지막 청크에도 꼬리 0 이 0~4 개 있다.
def _pad(n):
    return (-n) % ALIGN


def align_frame(f):
    """영상 표본 하나 — 청크마다 4 의 배수로 채우고 스트립·프레임 길이를 되쓴다."""
    ns = struct.unpack_from(">H", f, 8)[0]
    out = bytearray(f[:12])
    p = 12
    for _ in range(ns):
        ssz = struct.unpack_from(">I", f, p)[0] & 0xFFFFFF
        strip = bytearray(f[p : p + 12])
        q, end = p + 12, p + ssz
        while q < end:
            clen = struct.unpack_from(">I", f, q)[0] & 0xFFFFFF
            if clen < 4:
                raise SystemExit(f"청크 길이가 이상하다 ({clen}) — cinepak 이 아닌가")
            chunk = bytearray(f[q : q + clen]) + b"\x00" * _pad(clen)
            struct.pack_into(">I", chunk, 0, (chunk[0] << 24) | len(chunk))
            strip += chunk
            q += clen
        struct.pack_into(">I", strip, 0, (strip[0] << 24) | len(strip))
        out += strip
        p = end
    struct.pack_into(">I", out, 0, (out[0] << 24) | (len(out) - 8))
    return bytes(out)


def align_samples(b):
    """표본 전부를 **4 바이트 경계**에 다시 늘어놓고 STAB 을 되쓴다. 머리는 그대로다."""
    i = b.find(b"STAB")
    hdr = struct.unpack_from(">I", b, 4)[0]
    n = struct.unpack_from(">I", b, i + 12)[0]
    stab = bytearray(b[i : i + 16 + n * 16])
    body = bytearray()
    for j in range(n):
        p = 16 + j * 16
        off, size, i1, i2 = struct.unpack_from(">IIII", stab, p)
        s = b[hdr + off : hdr + off + size]
        if i1 != AUDIO_INFO1:
            s = align_frame(s)
        body += b"\x00" * _pad(len(body))
        struct.pack_into(">IIII", stab, p, len(body), len(s), i1, i2)
        body += s
    return b[:i] + bytes(stab) + b[i + len(stab) : hdr] + bytes(body)


def check_align(b):
    """정렬 계약을 되읽어 센다 — `(홀수 표본 오프셋, 4 배수 아닌 청크)`. 둘 다 0 이어야 한다."""
    i = b.find(b"STAB")
    hdr = struct.unpack_from(">I", b, 4)[0]
    n = struct.unpack_from(">I", b, i + 12)[0]
    bad_off = bad_chunk = 0
    for j in range(n):
        off, size, i1, _ = struct.unpack_from(">IIII", b, i + 16 + j * 16)
        bad_off += off % ALIGN != 0
        if i1 == AUDIO_INFO1:
            continue
        f = b[hdr + off : hdr + off + size]
        p = 12
        for _ in range(struct.unpack_from(">H", f, 8)[0]):
            ssz = struct.unpack_from(">I", f, p)[0] & 0xFFFFFF
            q, end = p + 12, p + ssz
            while q < end:
                clen = struct.unpack_from(">I", f, q)[0] & 0xFFFFFF
                bad_chunk += clen % ALIGN != 0
                q += clen
            p = end
    return bad_off, bad_chunk


def paths(name):
    d = os.path.join(CACHE, name)
    return (
        d,
        os.path.join(d, "src.CPK"),  # 원본 사본 (ffmpeg 입력)
        os.path.join(d, "enc.CPK"),  # ffmpeg 이 뱉은 그대로 — **비싼 산물**
        os.path.join(d, "sub.CPK"),  # 머리를 되맞추고 크기까지 채운 최종물
        os.path.join(d, "key.json"),
    )


def cached(name, size):
    """캐시가 지금 문안과 맞으면 그 바이트, 아니면 `None`."""
    _, _, _, sub, kf = paths(name)
    if not (os.path.exists(sub) and os.path.exists(kf)):
        return None
    with open(kf, encoding="utf-8") as f:
        if json.load(f).get("key") != key(name, size):
            return None
    with open(sub, "rb") as f:
        b = f.read()
    return b if len(b) == size else None


def finish(enc, size):
    """ffmpeg 산물 → 이미지에 넣을 바이트. 머리를 되맞추고 원본 크기까지 0 으로 채운다."""
    out = align_samples(retime_stab(enc))
    if check_align(out) != (0, 0):
        raise SystemExit(f"정렬이 안 맞는다 {check_align(out)} — align_samples 가 틀렸다")
    if bad := check_strips(out):
        raise SystemExit(
            f"스트립이 2×{STRIP_H} 가 아닌 표본 {len(bad)}개 (첫 {bad[:5]}) — "
            "ffmpeg 가 ENC_OPTS 를 안 들었다. enc.CPK 를 지우고 다시 굽는다"
        )
    if len(out) > size:
        raise SystemExit(
            f"구운 결과가 원본보다 크다 ({len(out):,} > {size:,}B) — 제자리에 못 넣는다"
        )
    #   ⓘ 뒤 여백은 STAB 이 안 가리키니 무해하다(엔트리는 전부 앞쪽 오프셋이다)
    return out + b"\x00" * (size - len(out))


def burn(name, disc, quiet=False):
    """한 편을 굽는다 — `(바이트, 재사용했나)`. 크기는 원본과 같게 맞춰 돌려준다."""
    subs = lines(name)
    if not subs:
        raise SystemExit(f"{name}: 자막이 없다")
    iso = f"/CPK/{name}.CPK"
    with C.open_disc(disc) as d:
        _, lba, size = d.find(iso)
        raw = d.read_extent(lba, size)

    hit = cached(name, size)
    if hit is not None:
        return hit, True

    d0, src, enc, sub, kf = paths(name)
    os.makedirs(d0, exist_ok=True)
    #   ⓘ ffmpeg 산물(`enc.CPK`)을 따로 둔다 — 머리 규약(`STAB_VER`)만 고칠 때
    #     **10 분짜리 재인코딩을 다시 안 하려고**다.
    #   ⚠ **문안이 그대로일 때만** 재사용한다 — 아니면 옛 자막이 든 영상이 나간다.
    if os.path.exists(enc) and os.path.exists(src) and _enc_ok(kf, name, size):
        with open(enc, "rb") as f:
            out = finish(f.read(), size)
        _save(sub, kf, out, name, size)
        return out, True
    with open(src, "wb") as f:
        f.write(raw)

    #   자막 한 줄에 PNG 한 장. `enable` 로 그 구간에만 얹는다.
    ins, chain, cur = [], [], "0:v"
    for i, (a, b, t) in enumerate(subs):
        p = os.path.join(d0, f"s{i:03d}.png")
        png(t, p)
        ins += ["-i", p]
        nxt = f"v{i}"
        chain.append(f"[{cur}][{i + 1}:v]overlay=0:0:enable='between(t,{a},{b})'[{nxt}]")
        cur = nxt
    cmd = (
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src]
        + ins
        + ["-filter_complex", ";".join(chain), "-map", f"[{cur}]", "-map", "0:a"]
        + ["-c:v", "cinepak", *ENC_OPTS, "-c:a", "copy", "-f", "film_cpk", enc]
    )
    if not quiet:
        print(f"  {name}: 자막 {len(subs)}줄 굽는 중… (원본 {size:,}B)")
    subprocess.run(cmd, check=True)

    with open(enc, "rb") as f:
        raw_enc = f.read()
    out = finish(raw_enc, size)
    _save(sub, kf, out, name, size, len(raw_enc))
    return out, False


def _enc_ok(kf, name, size):
    """`enc.CPK` 가 지금 문안으로 구운 것인가."""
    if not os.path.exists(kf):
        return False
    with open(kf, encoding="utf-8") as f:
        return json.load(f).get("enc_key") == enc_key(name, size)


def _save(sub, kf, out, name, size, enc_len=None):
    with open(sub, "wb") as f:
        f.write(out)
    with open(kf, "w", encoding="utf-8") as f:
        json.dump(
            {
                "key": key(name, size),
                "enc_key": enc_key(name, size),
                "enc": enc_len,
                "ffmpeg": ffmpeg_ver(),
                "stab": STAB_VER,
            },
            f,
            indent=1,
        )


def names(disc):
    """이 디스크에 실제로 있는, 자막이 있는 편."""
    with open(SCRIPT, encoding="utf-8") as f:
        sc = json.load(f)
    have = set()
    with C.open_disc(disc) as d:
        for p, _, _ in d.files():
            if p.startswith("/CPK/") and p.endswith(".CPK"):
                have.add(os.path.basename(p)[:-4])
    return [k for k in sorted(sc) if not k.startswith("_") and sc[k] and k in have]


def table(disc):
    """`build.py` 가 쓴다 — **캐시에 있는 것만** `{ISO 경로: 바이트}`. 없는 건 안 굽는다."""
    out, pend = {}, []
    with C.open_disc(disc) as d:
        sizes = {p: s for p, _, s in d.files() if p.startswith("/CPK/")}
    for n in names(disc):
        iso = f"/CPK/{n}.CPK"
        b = cached(n, sizes.get(iso, -1))
        (out.__setitem__(iso, b) if b is not None else pend.append(n))
    return out, pend


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--disc", type=int, default=1)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--preview", action="store_true", help="굽지 않고 PNG 한 장만")
    a = ap.parse_args()

    if a.list:
        ready, pend = table(a.disc)
        print(f"── disc{a.disc} 자막 있는 편")
        for n in names(a.disc):
            mark = "✅ 캐시" if f"/CPK/{n}.CPK" in ready else "· 안 구움"
            print(f"  {n}  자막 {len(lines(n)):>3}줄  {mark}")
        if pend:
            print(f"\n안 구운 편 {len(pend)}: {' '.join(pend)}")
        return 0

    todo = a.names or (names(a.disc) if a.all else [])
    if not todo:
        ap.error("편 이름을 주거나 --all / --list")

    if a.preview:
        os.makedirs(C.REVIEW_DIR, exist_ok=True)
        for n in todo:
            for i, (_, _, t) in enumerate(lines(n)[:3]):
                p = os.path.join(C.REVIEW_DIR, f"{n}_sub{i}.png")
                png(t, p)
                print(f"  {p}")
        return 0

    for n in todo:
        b, reuse = burn(n, a.disc)
        print(f"  {n}  {'캐시 재사용' if reuse else '구움'}  {len(b):,}B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
