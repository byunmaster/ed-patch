#!/usr/bin/env python3
"""동영상 EXE 넷에 **우리가 못 본 문안**이 남아 있나 — 표를 안 거치고 파일을 전수로 훑는다.

**왜.** 2026-08-22 에 ED1 엔딩 마지막 문장(`そして、伝説は引き継がれる…`)이 통째로 빠진 채
화면에 원문이 떴다. 그 줄의 포인터가 내레이션 표(0x14AB8~0x14D84) **밖**(0x14F28)이라
추출도 검출도 **표를 따라 도느라 처음부터 시야에 없었다.** 새턴은 자막을 파일에서 전수로
뽑아 그 줄이 있었고, PS1 만 빠졌다 — 즉 **표 추종이 구조적 사각**이다.

그래서 여기서는 **표를 안 쓴다.** EXE 안의 NUL 종단 문자열을 전부 훑어 「일본어 문안처럼
보이는데 우리 것도 아니고 죽은 사본도 아닌」 것을 찾는다.

**덮였다고 보는 것** — ⓐ 그 EXE 의 `textmap` 좌표 ⓑ 스태프롤 표(`END_STAFF.json`)
ⓒ **다른 층의 원문**. ⓒ 가 필요한 이유: 동영상 EXE 넷은 **네 편 내레이션을 다 들고 있고**
각자 자기 몫만 화면에 낸다(읽기 BP 실측). 그 죽은 사본까지 세면 100건 넘게 뜬다.

⚠ **이진 잡음을 걸러야 쓸 수 있다.** 코드 영역(0x3000~)이 우연히 SJIS 로 디코드되며 가나
한둘을 품는다 — 실측 EXE 당 34~47건. 제어바이트가 섞였거나 일본어 글자 비율이 낮으면 뺀다.
그래서 이 검사는 **「문안처럼 보이는 것」만** 본다 — 짧은 조각은 놓칠 수 있다.
"""

import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import patch_opening_font as PF

KANA = re.compile(r"[ぁ-んァ-ヶ]")
JPCH = re.compile(r"[ぁ-んァ-ヶ一-龥、。・！？「」　０-９Ａ-Ｚａ-ｚ…]")
MIN_LEN, MAX_LEN = 4, 80
JP_RATIO = 0.8  # 이 아래면 이진 잡음으로 본다


def looks_like_text(t):
    if any(ord(c) < 0x20 and c != "\n" for c in t):
        return False
    body = t.rstrip("\n")
    return len(body) >= MIN_LEN and len(JPCH.findall(body)) / len(body) >= JP_RATIO


def _all_jp():
    """네 층이 쓰는 원문 전부 — 죽은 사본 판별용."""
    out = set()
    for g in PF.GAMES.values():
        b = common.extract(g["lba"], PF.SIZE)
        p = os.path.join(common.ROOT, "textmap", f"{g['cls']}.json")
        with open(p, encoding="utf-8") as f:
            for e in json.load(f)["entries"]:
                fo = int(e["k"], 16) + g["delta"]
                try:
                    out.add(bytes(b[fo : b.find(b"\x00", fo)]).decode("cp932").rstrip("\n"))
                except (UnicodeDecodeError, ValueError):
                    pass
    return out


def scan(verbose=False):
    alljp = _all_jp()
    with open(os.path.join(common.ROOT, "script", "END_STAFF.json"), encoding="utf-8") as f:
        staff = set(json.load(f))
    total = 0
    for name, g in PF.GAMES.items():
        buf = common.extract(g["lba"], PF.SIZE)
        p = os.path.join(common.ROOT, "textmap", f"{g['cls']}.json")
        with open(p, encoding="utf-8") as f:
            ours = {int(e["k"], 16) + g["delta"] for e in json.load(f)["entries"]}
        miss, i = [], 0x800
        while i < PF.SIZE - 1:
            if buf[i] == 0:
                i += 1
                continue
            e = buf.find(b"\x00", i)
            if e < 0:
                break
            s = bytes(buf[i:e])
            if MIN_LEN <= len(s) <= MAX_LEN:
                try:
                    t = s.decode("cp932")
                except UnicodeDecodeError:
                    t = None
                if t and KANA.search(t) and looks_like_text(t):
                    body = t.rstrip("\n")
                    if (
                        i not in ours
                        and body not in alljp
                        and hashlib.sha1(body.encode()).hexdigest()[:10] not in staff
                    ):
                        miss.append((i, body))
            i = e + 1
        total += len(miss)
        if miss or verbose:
            print(f"  {'❌' if miss else '✅'} {name}: 덮이지 않은 문안 {len(miss)}")
        for o, t in miss[:8]:
            print(f"      0x{o:05X} {t[:30]!r}  ← textmap 에 넣거나 `far` 로 등록한다")
    print(f"  {'✅' if not total else '❌'} 동영상 문안 덮임 — 남은 것 {total}")
    return total


if __name__ == "__main__":
    sys.exit(1 if scan("-v" in sys.argv) else 0)
