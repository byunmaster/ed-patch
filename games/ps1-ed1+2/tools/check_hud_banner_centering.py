#!/usr/bin/env python3
"""**HUD 지명·입장 배너의 가운데정렬이 왼쪽으로 기우는가** — 규칙 2-8(마스터 11-08: 딱 가운데가 안 되면
왼쪽 여백이 더 짧게, 남는 여백은 오른쪽).

엔진은 이 줄들을 **바이트 길이로** 가운데 맞춘다: x = 0x1F9 + ((0x33 − 3·len) >> 1) (내림 = 왼쪽 쏠림).
그래서 값에 **선·후행 공백 바이트가 비대칭**이면 그만큼(바이트당 3px) 조용히 한쪽으로 쏠린다 —
지명이 바뀔 때 생기는 사고가 이것이다. 이 검사는 빌드된 이미지의 표를 읽어 정적 계산으로 본다
(에뮬 없이): ED2 입장 배너 표(ED2.EXE 0x9A030, 16B) · ED1 HUD 표(ED.EXE 0xBE690, 14B — 접미 앞 틈 공백
한 칸은 설계라 접미 없는 꼴에선 뺀다) · ED1 접미꼴(표 항목+접미 6) · ED2 씬 HUD 지명(`patch_scn_hud_copy._sites`).

기하 오차 g = (오른쪽 − 왼쪽 여백, px) = (0 또는 1) + 3·(후행 − 선행 공백 바이트).
실측 글리프 잉크 편향이 약 −3px 를 더 왼쪽으로 보태므로 g 는 0..3 이어야 한다(총 |L−R| ≤ 6px = 반각 공백 한 칸).
또 3·len ≤ 0x33 (틀에 든다).

🔴 **입장 배너는 「최대한 가운데」 + 띄움 꼴**(마스터 11-09 — 핫픽스 경로): 가능한 위치 중 가운데에 가장 가까운 것, 같을 때만 왼쪽.
공백 한 바이트가 g 를 ±3 옮기므로 **|g| ≤ 1** 이면 최근접이다(`judge_near`). 배너 꼴은 정본 일반 꼴(`canon.place_general`, 성·섬 붙임)을
정적으로 만들어 잰다 — ED2 는 표 값(`patch_ed2_sys.banner_general`), ED1 은 표 항목에서 후행 틈 공백을 떼고 위치 바이트로 공백을 끼운 꼴
(`patch_ed1_banner`, 0x800A6D1C 가 그리는 값).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")
import common
import hangul_map as H
import patch_scn_hud_copy as P
from patch_sys_ui import _scn_layout

REV = {H.syllable_sjis(ch).to_bytes(2, "big"): ch for ch in H.SYL_INDEX}
BOX = 0x33


def dec(b):
    o, i = "", 0
    while i < len(b):
        if b[i] < 0x80:
            o += chr(b[i])
            i += 1
        else:
            o += REV.get(bytes(b[i : i + 2]), "?")
            i += 2
    return o


def judge(raw, strip_one_trailing=False):
    n = len(raw)
    s = raw
    if strip_one_trailing and s.endswith(b" "):
        s = s[:-1]
    lead = len(s) - len(s.lstrip(b" "))
    trail = len(s) - len(s.rstrip(b" "))
    if 3 * len(s) > BOX:
        return f"틀 초과({len(s)}B)"
    pl = (BOX - 3 * len(s)) >> 1
    pr = BOX - 3 * len(s) - pl
    g = (pr - pl) + 3 * (trail - lead)
    if not 0 <= g <= 3:
        return f"기하 오차 g={g:+d}px (선행 공백 {lead} 후행 {trail})"
    return None


POPUP_BOX = 0x30  # ED1 입장 배너(0x800A6D1C): x = 0x380 + ((0x30 − 3·strlen) >> 1), 1단위 = 2px


def judge_near(raw, box):
    """최근접 가운데 — |g| ≤ 1 (g = 오른쪽 − 왼쪽 여백, 공백 한 바이트 = ±3). 틀에 들어야 한다."""
    if 3 * len(raw) > box:
        return f"틀 초과({len(raw)}B)"
    lead = len(raw) - len(raw.lstrip(b" "))
    trail = len(raw) - len(raw.rstrip(b" "))
    pl = (box - 3 * len(raw)) >> 1
    pr = box - 3 * len(raw) - pl
    g = (pr - pl) + 3 * (trail - lead)
    if abs(g) > 1:
        return f"가운데에서 먼 꼴 g={g:+d} (선행 공백 {lead} 후행 {trail}) — 공백 하나로 더 가깝게 된다"
    return None


def _enc(s):
    return b"".join(b" " if c == " " else H.encode_kr(c) for c in s)


def main():
    img = P.IMG
    ed2 = common.extract(756, 872448, path=img)
    ed1 = common.extract(257, 1021952, path=img)
    bad, n = [], 0
    for tag, buf, lo, hi, st, strip in (
        ("ED2 배너", ed2, 0x9A030, 0x9A490, 16, False),
        ("ED1 HUD", ed1, 0xBE690, 0xBE690 + 14 * 48, 14, True),
    ):
        for o in range(lo, hi, st):
            raw = bytes(buf[o : o + st].split(b"\0")[0])
            if not raw:
                continue
            n += 1
            r = judge(raw, strip)
            if r:
                bad.append((tag, dec(raw), r))
    # ED1 입장 배너 — HUD 와 같은 표를 다른 그리기 경로(0x800A6D1C)가 그린다. 핫픽스: 후행 틈 공백을 떼고 위치 바이트로 공백 하나를 끼운 꼴(=정본 일반 꼴)
    import canon
    import patch_sys_ui as PSU

    for slot_jp in PSU.PLACE_SLOTS:
        n += 1
        r = judge_near(_enc(canon.place_general(slot_jp, "ed1")), POPUP_BOX)
        if r:
            bad.append(("ED1 배너", canon.place_general(slot_jp, "ed1"), r))
    # ED2 입장 배너 — 핫픽스: 정본 일반 꼴(띄움, 성·섬 붙임). 표 값 자체는 위 「ED2 배너」(제품 꼴)로도 잰다
    import patch_ed2_sys as E2

    ed2_jp = common.extract(756, 872448, path=common.ORIG_BIN)  # 원문(JP)은 원판에서 읽는다
    for o in range(0x9A030, 0x9A280, 16):
        if not ed2_jp[o]:
            continue
        jp = E2._jp_at(ed2_jp, o)
        gen = E2.banner_general(jp) if jp else None
        if gen:
            n += 1
            r = judge_near(_enc(gen), BOX)
            if r:
                bad.append(("ED2 배너(띄움)", gen, r))
    # ED1 접미꼴 — HUD 표 항목(틈 공백 포함) + 접미(ED.EXE 0xF9074, NUL 구분 6개)를 한 줄로 이어 그린다
    sufs = [x for x in bytes(ed1[0xF9074 : 0xF9074 + 40]).split(b"\0")[:6]]
    for o in range(0xBE690, 0xBE690 + 14 * 48, 14):
        raw = bytes(ed1[o : o + 14].split(b"\0")[0])
        if not raw:
            continue
        for sf in sufs:
            n += 1
            r = judge(raw + sf)
            if r:
                bad.append(("ED1 HUD+접미", dec(raw + sf), r))
    seen = set()
    for name, lba, size in _scn_layout():
        buf = common.extract(lba, size, path=img)
        for s in P._sites(buf):
            if s["jal"] not in (P.HUD_DRAW, P.BIOS_STRCPY):
                continue
            o = s["src"] - P.SCN_BASE
            e = buf.find(b"\0", o, o + 64)
            raw = bytes(buf[o:e])
            if not raw or (name[:3], raw) in seen or name.startswith("ED1"):
                continue
            seen.add((name[:3], raw))
            n += 1
            r = judge(raw)
            if r:
                bad.append(("ED2 HUD " + name, dec(raw), r))
    print(f"  {'✅' if not bad else '❌'} HUD 지명·입장 배너 가운데정렬(HUD 왼 ≤ 오·차 ≤ 반각 한 칸 / 배너 최근접) {n}곳 중 어긋남 {len(bad)}")
    for t, nm, r in bad:
        print(f"      {t}: {nm!r} — {r}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
