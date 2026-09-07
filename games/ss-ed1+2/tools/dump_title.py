#!/usr/bin/env python3
"""`TITLE.BIN` 의 오프닝·엔딩·스태프롤 내레이션을 뽑는다.

**왜 따로 있나.** 본편 대사는 `BIN/*.BIN` 에 있고 `dump_scn.py` 가 본다. 그런데 오프닝·
엔딩은 **`TITLE.BIN` 한 파일**에 모여 있고 형식이 아예 다르다 — 창도 이름표도 없고,
**고정 폭 레코드**가 줄줄이 늘어선 스크롤 자막이다.

🔴 **먼저 확인한 것: 그림이 아니라 텍스트다**(2026-08-21). `/OPENEND/` 가 `*.DG2`(그림)
투성이라 문구가 그려져 들어갔을 가능성이 있었는데, 화면에서 본 문구를 이미지 전량에서
찾으니 `TITLE.BIN` 에 **평문 SJIS** 로 있었다. 그래서 폰트 교체 + 문안 재삽입이 먹는다.
그리고 `TITLE.BIN` 이 쓰는 폰트가 `KANJI.FON`(16×16)이라 Neo둥근모가 네이티브로 들어간다.

## 규격 (실측)

    레코드 42B  +  구분 \\x00\\x00 2B      스트라이드 44

- ⚠ **레코드 꼴이 둘이다**(실측). 크기·스트라이드는 같고 앞머리만 다르다:
    · `\\x00\\x09` + 전각 **20자**(40B) — ED1 오프닝·엔딩 계열
    · 전각 **21자**(42B) — ED2 오프닝 계열 (접두 없음)
  `\\x09` 가 무엇인지는 아직 모른다(줄 제어로 보인다). **둘 다 받아야** 한 구간이 통째로
  샌다 — 처음엔 접두 있는 꼴만 봐서 ED2 오프닝이 23줄인데 5줄로 나왔다.
- 🔴 **중앙정렬을 데이터가 직접 한다** — 문안 좌우를 전각 공백 `　` 으로 채워 20칸을
  맞춰 놨다. PS1 은 엔진이 필드 폭(64유닛)에 맞춰 중앙정렬했다. **여기선 우리가 채워야 한다.**
- 🔴 **역순 저장** — 화면이 아래에서 위로 흐르므로 마지막 줄이 앞에 온다.
- 폭이 **정확히 20칸**이라 PS1(오프닝 21자·advance 12px)과 다르다. 넘치면 잘린다.

  python3 games/ss-ed1+2/tools/dump_title.py        # 요약
  python3 games/ss-ed1+2/tools/dump_title.py -v     # 전문(화면 순서)
"""

import json
import os
import sys

import common

TITLE = "/TITLE.BIN"
PREFIX = b"\x00\x09"
SEP = b"\x00\x00"
REC = 42  # 레코드 바이트 (꼴에 따라 전각 20자 + 접두, 또는 전각 21자)
STRIDE = REC + len(SEP)  # 44B
WIDTHS = (20, 21)  # 실측된 레코드 폭 — 이 밖이면 레코드가 아니다

# 구간 이름 — **오프셋으로 못 박는다**. 순번으로 붙였다가 구간이 하나 늘자 전부 한 칸씩
# 밀려 잘못 붙었다(2026-08-21). 배치가 바뀌면 조용히 틀리는 대신 **실패**해야 한다.
# ⚠ ED2 오프닝만 폭이 **21칸**이다(나머지는 20칸). 왜 갈렸는지는 아직 모른다.
LABELS = {
    0x00B00: "ED1 오프닝",
    0x01D10: "ED2 오프닝",
    0x02B1C: "ED1 엔딩·스태프롤",
    0x04C60: "ED2 엔딩·스태프롤",
}


def _load(mm):
    files = {p: (l, s) for p, l, s in common.iso_files(mm)}
    lba, size = files[TITLE]
    n = (size + common.USER_SIZE - 1) // common.USER_SIZE
    return b"".join(bytes(common.sector_user(mm, lba + i)) for i in range(n))[:size]


def _decode(body):
    """레코드 본문 → 전각 문자열. 앞의 2바이트 제어(`\\x00\\x09` 등)는 떼어 낸다."""
    pre = b""
    if len(body) >= 2 and body[0] == 0x00:
        pre, body = body[:2], body[2:]
    if not body or len(body) % 2:
        return None, None
    try:
        t = body.decode("cp932")
    except UnicodeDecodeError:
        return None, None
    return (t, pre) if len(t) == len(body) // 2 else (None, None)


def runs(raw):
    """이어지는 레코드 덩어리들 → `[(시작오프셋, [(본문, 오프셋, 바이트수)…])]`.

    🔴 **보폭을 가정하지 않는다 — 구분자로 끊는다.** 처음엔 스트라이드 44 로 훑었는데,
    두 덩어리 사이에 **보폭 42 짜리 레코드 하나**가 끼어 있어 통째로 건너뛰었다
    (2026-08-21: ED2 오프닝 중간 한 줄이 화면에 **일본어로 남아** 발각). 크기가 다른 자리가
    있다는 건 다른 데도 있을 수 있다는 뜻이라, 규칙을 「보폭」이 아니라 「구분자」로 바꾼다.

    ⚠ 접두는 **셋**이다 — `\\x00\\x09` · `\\x00\\x00` · 없음. 앞 2바이트가 `\\x00` 로
    시작하면 제어로 보고 뗀다.
    """
    seps = []
    i = raw.find(SEP)
    while i >= 0:
        seps.append(i)
        i = raw.find(SEP, i + 2)
    out, cur, start = [], [], None
    for a, b in zip([None] + seps, seps):
        lo = (a + len(SEP)) if a is not None else 0
        # ⚠ 구간의 **첫 레코드**는 앞이 구분자가 아니라 바이너리다 — 구간째로 디코드하면
        #   실패해 한 줄이 통째로 빠진다(2026-08-21: ED2 오프닝 마지막 줄). 앞을 다듬어 본다.
        t = None
        for cand in (lo, b - 42, b - 40):
            if cand < 0 or cand > b:
                continue
            t, _pre = _decode(raw[cand:b])
            if t is not None and len(t) in WIDTHS:
                lo = cand
                break
            t = None
        if t is None:
            if len(cur) >= 3:
                out.append((start, cur))
            cur, start = [], None
            continue
        if start is None:
            start = lo
        # 레코드마다 **실제 구간**을 들고 다닌다 — 길이가 40B/42B 로 갈린다(접두 유무).
        cur.append((t, lo, b - lo))
    if len(cur) >= 3:
        out.append((start, cur))
    return out


def main():
    verbose = "-v" in sys.argv
    _f, mm = common.open_image()
    raw = _load(mm)
    rs = runs(raw)
    print(f"■ {TITLE} {len(raw):,}B · 레코드 {REC}B + 구분 {len(SEP)}B · 스트라이드 {STRIDE}")
    total = 0
    out = {}
    unknown = [f"0x{o:05X}" for o, _ in rs if o not in LABELS]
    assert not unknown, f"모르는 구간 {unknown} — 배치가 바뀌었다. LABELS 를 실측으로 갱신할 것"
    for off, recs in rs:
        name = LABELS[off]
        body = [t.strip("　") for t, _o, _n in recs][::-1]  # 역순 저장 → 화면 순서
        total += len(recs)
        blank = sum(1 for t in body if not t)
        w = max(len(t) for t, _o, _n in recs)
        print(f"   0x{off:05X}  {len(recs):>4}줄 (빈 줄 {blank}) · 폭 {w}칸  {name}")
        if verbose:
            for t in body:
                print(f"        |{t}|")
        out[name] = {"offset": off, "width": w, "lines": body}
    print(f"   합계 {total}줄 · 구간 {len(rs)}개")

    os.makedirs(common.OUT_DIR, exist_ok=True)
    dst = os.path.join(common.OUT_DIR, "title_jp.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"   → {dst}")


if __name__ == "__main__":
    main()
