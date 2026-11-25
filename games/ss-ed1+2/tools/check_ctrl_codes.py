"""제어 코드 대조 — 원판 메시지마다 `%c`(색·쪽 넘김 인자)·`%s`·`%d` 를 세어 **빌드 이미지 바이트**의 같은 메시지와 맞춘다.

왜: 번역 조립기가 원문의 색 전환 코드를 한 번도 안 낸 게임이 있었다(pce-ed1, 마스터 인게임 발견 — 빌드·게이트·짝 표
어느 것도 못 잡았다). 이 게임에서 `%c` 하나는 호출처가 넘기는 sprintf 인자 한 바이트(2·3 색 켜기 · 1 끄기 · 8 쪽 넘김 ·
6·7·12 끝맺음 — `callargs.py`)라, **개수·순서가 틀어지면 뒤 인자가 전부 밀려** 색이 엉뚱한 글자에 걸린다.

본 것
  ① 토큰 열(`%c %s %d %숫자`)이 원판과 같은가 — 누락·여분·순서. 하나라도 갈리면 실패.
  ② 토큰 둘레의 모양(문자열 끝 · 이웃 토큰 · 글) — 갈린 메시지는 **알려진 사유**만 허용한다(아래 `KNOWN_SHIFT`).
  ③ 색·토큰이 아닌 제어 바이트(0x00~0x1F, 개행 제외) 증감 — 보고(실패 아님). 지금은 쪽 가르기가 넣는 `08` 뿐이다.

알려진 모양 이동 사유(14, 2026-10-29 전수 확인)
  · 주입 `%c` 쌍(ニア 이름칸 · 〜を 앞뒤) — 인자가 0x20 으로 바뀌고 쌍이 같은 창 꼬리로 옮겨 간다(`inject_pairs.py`). 순서는 그대로.
  · 블록 머리 개행(`\\n%c%s%c…`) · 쪽 가르기 `08` 머리 — 토큰 앞에 글자 하나가 생겼을 뿐 토큰은 그대로.
이 수가 **늘면** 실패(래칫) — 새 이동은 사유를 확인해 `KNOWN_SHIFT` 를 올린다.
"""

import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import dump_scn

KNOWN_SHIFT = 14  # 알려진 모양 이동 메시지 수(주입 쌍 5 + 머리 개행·쪽 가르기 9)
TOKEN = re.compile(rb"%[csd]|%[0-9]")


def _sig(raw):
    out = []
    for m in TOKEN.finditer(raw):
        a, b = raw[: m.start()], raw[m.end() :]
        pc = "S" if not a else ("C" if a[-2:] == b"%c" else "T")
        nc = "S" if not b else ("C" if b[:2] == b"%c" else "T")
        out.append((m.group(0).decode(), pc, nc))
    return out


def _load(path):
    f, mm = common.open_image(path)
    res = {}
    try:
        for p, lba, size in common.iso_files(mm):
            name = p.rsplit("/", 1)[-1]
            base = dump_scn.base_for(name)
            if base is None:
                continue
            res[p] = dump_scn.dump_file(name, common.read_extent(mm, lba, size), base)
    finally:
        mm.close()
        f.close()
    return res


def main():
    built = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if not os.path.exists(built):
        print(f"  ⛔ 빌드 이미지가 없다: {built}")
        return 1
    orig, new = _load(common.ORIG_BIN), _load(built)
    msgs = tokens = nomatch = 0
    seq_bad, shift = [], []
    ctl = collections.Counter()
    for p, od in orig.items():
        bmap = {tuple(e["ptr_at"]): e for e in new.get(p, {"entries": []})["entries"]}
        for e in od["entries"]:
            ob = bytes.fromhex(e["raw_hex"])
            if e["kind"] != "block" and b"%" not in ob:
                continue
            msgs += 1
            be = bmap.get(tuple(e["ptr_at"]))
            if be is None:
                nomatch += 1
                continue
            nb = bytes.fromhex(be["raw_hex"])
            so, sn = _sig(ob), _sig(nb)
            tokens += len(so)
            if [t for t, _, _ in so] != [t for t, _, _ in sn]:
                seq_bad.append((p, e["entry_id"], [t for t, _, _ in so], [t for t, _, _ in sn]))
            elif so != sn:
                shift.append((p, e["entry_id"]))
            a = collections.Counter(x for x in ob if x < 0x20 and x != 0x0A)
            b = collections.Counter(x for x in nb if x < 0x20 and x != 0x0A)
            for k in set(a) | set(b):
                if a[k] != b[k]:
                    ctl[(hex(k), "+" if b[k] > a[k] else "-")] += 1
    print(f"  제어 코드 대조 [메시지 {msgs:,} · 토큰 {tokens:,}] — 열 갈림 {len(seq_bad)} · 모양 이동 {len(shift)}(알려진 {KNOWN_SHIFT}) · 짝 없음 {nomatch}")
    if ctl:
        print("  ℹ 색 아닌 제어 바이트 증감(보고): " + " · ".join(f"{k[0]}{k[1]} {v}" for k, v in sorted(ctl.items())))
    bad = False
    for p, i, a, b in seq_bad[:10]:
        print(f"    ❌ {p} #{i}: 원판 {a} → 빌드 {b}")
        bad = True
    if len(shift) > KNOWN_SHIFT:
        print(f"    ❌ 모양 이동이 알려진 수({KNOWN_SHIFT})보다 늘었다 — 새 사유를 확인한다:")
        for p, i in shift[:20]:
            print(f"       {p} #{i}")
        bad = True
    if nomatch:
        print(f"    ❌ 짝을 못 찾은 메시지 {nomatch}")
        bad = True
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
