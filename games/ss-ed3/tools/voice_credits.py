"""크레딧 자막(V20) 자료 — `script/voice_credits.json` → 스텁이 읽는 표.

    python3 games/ss-ed3/tools/voice_credits.py --check    # 표를 만들어 검산

대사창(V17~V19)과 달리 **글자만** 그린다(테두리·얼굴 없음 — 마스터 09-30). 크레딧엔 맵 스크립트가 없어
시각을 **프레임 시계**(크레딧 시작 = 0)로 센다(`subtitle_stub` 「크레딧 자막」).

자료 = 음성 0초 기준 초(`start`·`end`) + 그림 쪽(`side`, 자막은 반대쪽) + 줄. `origin` 은 「음성 0초가
시계 0 에서 몇 초 뒤인가」다 — **아직 재지 않았다**(0 으로 둔다). 어긋나면 이 값 하나로 민다.
`scale` 은 글자 스프라이트 배율(0.75 = 글자 9px, 화면 18px — 마스터 09-30 「폰트 줄여라」)이다.
`fps` 는 시계(=프레임 태스크 호출)가 1 초에 몇 번 도는가 — 인터레이스 고해상도라 59.94 로 어림했다.

글자 꼴 = `<0> <x s16> <y s16> <xc s16> <yc s16>` + 이름 `\\0`(비움) + 줄들 — 대사창 글자와 같은 줄 인코딩.
글자 버퍼가 216px 라 줄을 **앞 공백으로 가운데 맞춘다**(반각 공백 6px 단위 — 오차 ±3px).
"""

import argparse
import re
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
import common as C
import hangul_map as H
import subtitle_stub as SS
import typeset as T

PATH = os.path.join(C.GAME_DIR, "script", "voice_credits.json")
BUF_W = SS.BUF_STRIDE * 2  # 글자 버퍼 폭(px) — 216
ART_BOTTOM = 230  # 그림 아래 끝(VDP1 좌표 — 화면 460 의 절반)
LINE_H = SS.LINE_PITCH  # 줄 간격(px)
#   그림이 왼쪽이면 자막은 오른쪽 검은 칸(화면 x 315~660 → VDP1 157~330)의 가운데 245,
#   오른쪽이면 왼쪽 검은 칸의 가운데 85. 글자 스프라이트의 **가운데**가 거기 오게 한다.
CENTER = {
    "L": 236,
    "R": 84,
}  # 그림 L: 검은 칸 화면 x 313~660 의 가운데 / 그림 R: 0~347 의 가운데(VDP1 = 화면/2.0625)
LOCAL = 160  # VDP1 로컬 원점 x(화면 가운데)
LOCAL_Y = 120  # 로컬 원점 y
BLACK_W = 172  # 그림 반대쪽 검은 칸 폭(VDP1 좌표) — 화면 x 315~660 을 절반으로


def load(path=PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


FULL = SS.CRED_CELL  # 전각(한글·부호) 전진량 — 엔진 draw 가 글자 폭 r7 로 잡는다
HALF = SS.CRED_CELL // 2 // 2 * 2  # 반각(공백) 전진량 — (r7>>1)>>1 바이트 × 2px (4bpp)
LINE_MAX = 164  # 한 줄 최대 폭(px) — 검은 칸(172) 안쪽 여유 포함


def rendered(line):
    """실제로 찍을 글: 부호는 전각 칸이라 **그 뒤 공백을 먹는다**(칸 안에 여백이 들어 있다)."""
    return re.sub(r"([" + re.escape(H.CRED_PUNCT) + r"])[ ]+", r"\1", line)


def width(line):
    """크레딧 글자의 폭(px) — 한글·부호 10 · 반각(공백 등) 4."""
    return sum(FULL if (ord(c) > 0x7F or c in H.CRED_PUNCT) else HALF for c in rendered(line))


def _greedy(words, limit):
    out, cur = [], ""
    for w in words:
        nxt = (cur + " " + w) if cur else w
        if cur and width(nxt) > limit:
            out.append(cur)
            cur = w
        else:
            cur = nxt
    if cur:
        out.append(cur)
    return out


def wrap(lines):
    """줄들을 이어 붙여 **폭 `LINE_MAX` 로 다시 접는다**(어절 단위) — 글꼴이 작아져 칸 수 기준 개행이 헐겁다."""
    #   ① 한 줄에 다 들어가면 한 줄 ② 아니면 **손으로 끊어 둔 줄**이 폭 안이면 그대로(의미 단위를 지킨다 — 마스터 10-01
    #   「써야 할 이가는 한 줄」) ③ 그것도 아니면 어절로 다시 접는다.
    joined = " ".join(lines)
    if width(joined) <= LINE_MAX:
        return [joined]
    if len(lines) <= 2 and all(width(t) <= LINE_MAX for t in lines):
        return list(lines)
    words = joined.split()
    out, cur = [], ""
    for w in words:
        nxt = (cur + " " + w) if cur else w
        if cur and width(nxt) > LINE_MAX:
            out.append(cur)
            cur = w
        else:
            cur = nxt
    if cur:
        out.append(cur)
    if len(out) > 1:  # 줄 수는 그대로 두고 **고르게** 맞춘다 — 짧은 꼬리 한 줄이 남지 않게
        n, lim = len(out), LINE_MAX
        while lim > 40:
            alt = _greedy(words, lim - 4)
            if len(alt) != n:
                break
            out, lim = alt, lim - 4
    return out


def _pad(line):
    """가운데 맞추는 앞 공백 개수 — 반각 공백 4px."""
    #   줄 끝 부호 칸은 잉크가 3px 쯤이고 나머지는 빈칸이라 폭에서 빈칸을 빼야 **눈으로** 가운데다
    tail = FULL - 3 if line.rstrip()[-1:] in H.CRED_PUNCT else 0
    #   반올림한다 — 내림이면 한 칸(4px) 가까이 왼쪽으로 쏠린 줄이 생긴다(마스터 10-03 「중앙정렬 안 된 부분」)
    return max(0, round((BUF_W - (width(line) - tail)) / 2 / HALF))


def table_cred():
    """한글·부호 → 크레딧 전용 슬롯을 본 배정 위에 얹은 표(없으면 본 배정)."""
    t = dict(H.load())
    t.update(H.load_cred())
    return t


def record(sub, table, scale=1.0):
    """글자 한 벌 — 좌표 + 이름(비움) + 줄들. 짝수 길이.

    좌표는 **그림 쪽 둘**이다: 그림이 왼쪽이면 자막은 오른쪽 검은 칸(`x`·`xc`), 오른쪽이면 왼쪽 검은 칸(`xR`·`xcR`).
    어느 쪽인지는 게임 중에 스텁이 고른다(`subtitle_stub.cemit`). 줄은 위에서 아래로 쌓이므로 **아래 끝(그림 아래 끝)** 기준으로 y 를 잡는다.
    """
    lines = wrap(sub["lines"])
    if not 1 <= len(lines) <= SS.CRED_ROWS:
        raise SystemExit(f"#{sub.get('n')}: 줄은 1~{SS.CRED_ROWS} 개다({len(lines)}): {lines}")
    for t in lines:
        if "\n" in t or width(t) > BUF_W:
            raise SystemExit(f"#{sub.get('n')}: 한 줄이 버퍼({BUF_W}px)를 넘는다: {t!r}")
    w, h = BUF_W * scale, SS.BUF_LEN // SS.BUF_STRIDE * scale
    #   글자 9 행(0~8) · 줄 간격 `CRED_PITCH` — 마지막 줄 잉크 아래 끝이 그림 아래 끝에서 5px 위에 오게 위 끝을 잡는다
    y = round(ART_BOTTOM - 5 - LOCAL_Y - ((len(lines) - 1) * SS.CRED_PITCH + 8) * scale)
    xs = [round(CENTER[side] - w / 2 - LOCAL) for side in ("L", "R")]
    out = (
        struct.pack(
            ">Hhhhhhh", 0, xs[0], y, xs[0] + round(w), y + round(h), xs[1], xs[1] + round(w)
        )
        + b"\x00"
    )
    for t in lines:
        out += H.encode_kr(" " * _pad(t) + rendered(t), table) + b"\x00"
    out += b"\x00"
    return out + b"\x00" * (len(out) % 2)


def merged(subs):
    """같은 번호·같은 글의 이어진 항목(그림 쪽이 바뀌는 자리에서 둘로 쪼갠 것)을 하나로 — 그림 쪽은 이제 게임이 정한다."""
    out = []
    for s in sorted(subs, key=lambda s: (s["start"], s["end"])):
        if out and out[-1].get("n") == s.get("n") and out[-1]["lines"] == s["lines"]:
            out[-1] = dict(out[-1], end=max(out[-1]["end"], s["end"]))
        else:
            out.append(s)
    return out


def blob(ctab, doc=None, table=None):
    """표 바이트 — `<개수 u16> <0 u16>` + 항목 12B(시작·끝·글자 포인터) + 글자들. 포인터는 `ctab` 기준."""
    doc = doc or load()
    table = table if table is not None else table_cred()
    fps, origin = float(doc["fps"]), float(doc.get("origin", 0.0))
    subs = merged(doc["subs"])
    n = len(subs)
    if n >= 0x8000:
        raise SystemExit("항목이 너무 많다")
    at = ctab + 4 + 12 * n
    ents, body = b"", b""
    for s in subs:
        a, b = round((s["start"] + origin) * fps), round((s["end"] + origin) * fps)
        if not 0 <= a < b < 0x7FFFFFFF:
            raise SystemExit(f"#{s.get('n')}: 시각이 이상하다 ({s['start']}~{s['end']})")
        rec = record(s, table, float(doc.get("scale", 1.0)))
        ents += struct.pack(">III", a, b, at + len(body))
        body += rec
    return struct.pack(">HH", n, 0) + ents + body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--bin", help="표를 이 파일로 쓴다(ctab 기준)")
    a = ap.parse_args()
    doc = load()
    _, w = SS.build_credits(SS.build()[2]["draw_line"])
    t = blob(w["ctab"], doc)
    n = len(doc["subs"])
    span = SS.STUB - w["ctab"]
    print(
        f"항목 {n} · 표 {len(t)}B (남는 자리 {span - len(t)}B) · 크레딧 코드 @ {SS.CRED:#x} · 표 @ {w['ctab']:#x}"
    )
    ends = max(s["end"] for s in doc["subs"])
    print(f"마지막 자막 끝 {ends:.1f}초 = 시계 {round(ends * doc['fps'])} 프레임")
    if len(t) > span:
        raise SystemExit("표가 자리를 넘는다")
    if a.bin:
        with open(a.bin, "wb") as f:
            f.write(t)


if __name__ == "__main__":
    main()
