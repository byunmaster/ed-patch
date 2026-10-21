#!/usr/bin/env python3
"""**구조 대조 — 원본과 빌드의 모든 대사 블록에서 글자를 빼고 「제어 코드 열」만 대조한다**(마스터 10-22 「재배치사고 막는 정적검사」).

배경: ss-ed3 에서 재조판 때 대사 끝에 넣은 채움 바이트(FF FF)가 다음 블록 호출을 막아, 새 게임 첫 장면에서 대사가 통째로 빠졌다
(1,046블록). 블록을 한 장씩 띄우는 하네스·qa 로는 안 보이고 연속 재생에서만 드러났다. 재배치·꼬리 옮기기·채움을 한 게임은 모두 위험하다.
이 게임의 재배치는 **씬 파일 안에서 블록을 풀로 옮기고 포인터(BE32)를 돌리는 것**이라, 엔진이 읽는 구조는 셋이다 —
    ① 포인터가 가리키는 자리에서 **NUL 까지** 읽는다(문자열 하나 = 블록 하나)
    ② 그 안의 제어 = `%c`·`%s`·`%d`(sprintf 인자 — 창 시작/끝·이름 끝은 이 인자가 만든다) · `0x0a`(줄) · 그 밖의 1바이트 제어
    ③ 블록 뒤 꼬리 = `NUL + 0 채움 + 이따금 0x09`(다음 블록 시작 표지 — 안 건드린다)
이 도구는 원본 이미지(`originals`)와 빌드 이미지에서 **같은 블록**을 짝지어(원본 `ptr_at` 의 BE32 → 빌드의 새 목표) 아래를 잰다 —

  A. 제어 열 — `%c%s%d` 순서열 · 그 밖의 제어 바이트(0x0a·0x08 과 NUL 빼고) 순서열이 원본과 **같아야 한다**. 줄(0x0a) 수는 재조판이라 다를 수 있다(허용 · 건수만 센다).
     `0x08`(창 끝 = 쪽 넘김)은 **원본보다 늘 수만 있다**(`patch_scn.page_split` 이 쪽 5행 한도를 넘는 자리에 넣는다 — 실측: 씬 34 번호 43 에 08 을 넣자 쪽이 하나 늘었다). 줄면 실패.
  B. 종단 — 블록이 **NUL 로 끝난다**(파일 끝을 넘기지 않는다). 안에 원본에 없던 제어 바이트(채움 FF 등)가 **없다**.
  C. 포인터 — 한 블록의 `ptr_at` 이 전부 **같은 목표**를 가리키고, 이주분은 **짝수 주소**다(어떤 화면은 두 바이트를 한 글자로 고정해 읽는다 — `patch_scn._place`).
  G. 놓인 자리 — 이주분의 최종 구간이 원본의 **글 구간(블록들이 있던 자리) 안**이거나, 그 밖이면 원본 바이트가 **전부 0**(빈 자리)이다 — 코드·표 위에 안 깔린다.
  D. 겹침 — 파일 안 모든 블록의 최종 구간 `[목표, 목표+길이+NUL)` 이 **서로 안 겹친다**.
  E. 꼬리 — 제자리 블록은 원문 길이를 안 넘는다(`내용 ≤ 원문`). 비워진 옛 칸(옮겨진 블록의 칸)은 풀이라 대상이 아니다.
  F. 채움 — 제자리 블록 뒤 칸 안의 바이트는 **0 · 다른 블록의 최종 구간(이주분이 칸 뒤쪽 빈 자리를 씀) · 원본과 같은 바이트(다음 블록 시작 표지 0x09)** 셋 중 하나다 — 그 밖의 채움은 실패.
  표 칸·겹친 꼬리 — 원본에서 NUL 로 안 끝나는 항목(고정 폭 표 칸)이나 서로 겹친 항목(꼬리 공유 문자열)은 제어 열만 대조하고 겹침·꼬리 검사는 건너뛴다(건수를 센다).

허용(= 의도적으로 바뀐 것)은 **재배치 장부**(`relocations.tsv`, `relocations.py` 가 빌드에서 자동으로 뽑는다)와 같은 출처다 — 장부에 없는 이주가 있으면 실패한다.
순수 판정 함수(`ctrl_column` · `compare_blocks` · `tail_ok` · `overlaps`)는 합성 바이트로 테스트한다(`tests/test_check_structure.py`).

    python3 tools/check_structure.py          # 빌드 이미지 대조 (원본 필요)
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MAX_GAP = 8  # 블록 사이 빈틈 경계(`patch_scn.MAX_GAP` 와 같다 — 1~4B 정렬 틈 vs 64B↑ 코드 사이)


def ctrl_column(b):
    """바이트열 → `(형식 토큰 열, 기타 제어 열, 줄 수)` — 글자는 건너뛴다.

    SJIS 2바이트 글자(선두 0x81~0x9F · 0xE0~0xFC)는 뒷 바이트(0x40~)가 제어와 안 섞이게 통째로 건너뛴다. SJIS 에 없는 바이트(0x7F·0x80·0xA0·0xFD~0xFF)와 선두 뒤의 범위 밖 바이트는 **기타 제어**로 센다(채움 FF 같은 것).
    `%` 뒤 `c·s·d` = 형식 토큰. 0x0a = 줄. 그 밖의 0x20 미만(NUL 제외) = 기타 제어. 0xA1~0xDF(반각 가나)는 글자다.
    """
    fmt, other, lf = [], [], 0
    i, n = 0, len(b)
    while i < n:
        c = b[i]
        if 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC:
            # 뒷 바이트가 SJIS 범위 밖이면(채움 FF 가 글자 뒤에 붙은 꼴 등) 그 바이트를 제어로 센다
            if i + 1 < n and not (0x40 <= b[i + 1] <= 0xFC and b[i + 1] != 0x7F):
                other.append(c)
                i += 1
                continue
            i += 2
            continue
        if c in (0x7F, 0x80, 0xA0, 0xFD, 0xFE, 0xFF):  # SJIS 에 없는 바이트 — 채움·깨짐
            other.append(c)
            i += 1
            continue
        if c == 0x25 and i + 1 < n and b[i + 1] in b"csd":
            fmt.append(chr(b[i + 1]))
            i += 2
            continue
        if c == 0x0A:
            lf += 1
        elif c < 0x20 and c != 0:
            other.append(c)
        i += 1
    return fmt, other, lf


def compare_blocks(orig, built):
    """원본 블록 ↔ 빌드 블록(둘 다 NUL 앞까지) → `(문제 목록, 줄 수 변화)`."""
    of, oo, ol = ctrl_column(orig)
    bf, bo, bl = ctrl_column(built)
    bad = []
    if of != bf:
        bad.append(f"형식 토큰 열 {''.join(of)!r} → {''.join(bf)!r}")
    o8, b8 = oo.count(8), bo.count(8)
    oo2, bo2 = [c for c in oo if c != 8], [c for c in bo if c != 8]
    if oo2 != bo2:
        bad.append(f"기타 제어 열 {bytes(oo2).hex()} → {bytes(bo2).hex()}")
    if b8 < o8:
        bad.append(f"쪽 넘김(08) 이 줄었다 {o8} → {b8}")
    return bad, bl - ol, b8 - o8


def block_at(data, t):
    """`data[t:]` 에서 NUL 까지 → `(바이트, 종단 여부)`. 파일 끝까지 NUL 이 없으면 종단 False."""
    j = data.find(b"\x00", t)
    if j < 0:
        return data[t:], False
    return data[t:j], True


def tail_gap_bad(orig, built, off, new_len, slot_end, live):
    """제자리 블록 뒤 칸 안의 바이트 중 **설명 안 되는 것**의 위치 목록.

    설명되는 바이트 = 0 · 다른 블록의 최종 구간(`live` = `[(시작, 끝)]`) · 원본과 같은 바이트(다음 블록 시작 표지).
    """
    out = []
    for p in range(off + new_len, slot_end):
        v = built[p]
        if v == 0 or v == orig[p] or any(a <= p < b for a, b in live):
            continue
        out.append(p)
    return out


def slot_tail_end(orig, p):
    """원본 칸의 꼬리 끝 — `p`(= 글자 끝) 부터 `NUL + 0 채움(+ 0x09 한 바이트)`. 이 안은 이 블록의 자리다.

    `0x09` 는 다음 블록의 시작 표지처럼 보이지만 **아무도 안 가리키고 본문에도 안 나온다** — 실기로 꼬리 09 열둘을 0 으로 지우고 오프닝을 월드맵까지
    돌려 무죄를 확인했다(`docs/devlog.md` 2026-09-04 「`0x09` 를 실기로 무죄 판정」 · `docs/status.md` 1-D). 그래서 비워진 칸을 풀로 낼 때 같이 낸다(`patch_scn._place`).
    """
    q = p
    while q < len(orig) and orig[q] == 0:
        q += 1
    if q < len(orig) and orig[q] == 0x09 and q > p:
        q += 1
    return max(q, p + 1)


def outside_nonzero(orig, a, b, runs):
    """`[a, b)` 중 원본 글 구간(`runs`) **밖**이면서 원본 바이트가 0 이 아닌 자리 목록(원본 파일 끝 뒤 = 확장 영역은 0 으로 본다)."""
    out = []
    for p in range(a, min(b, len(orig))):
        if orig[p] and not any(r0 <= p < r1 for r0, r1 in runs):
            out.append(p)
    return out


def overlaps(spans):
    """`[(시작, 끝, 이름)]` → 겹치는 쌍 목록."""
    out = []
    s = sorted(spans)
    for (a0, a1, an), (b0, b1, bn) in zip(s, s[1:]):
        if b0 < a1:
            out.append((an, bn, b0, a1))
    return out


def tail_entry_changed(orig, built, base, entries):
    """**남이 들어오는 꼬리 바이트를 우리가 바꿨나**(pce-ed1 이 잡은 꼴 — 마스터 10-22).

    원본의 모든 정렬된 4바이트 값 중 파일 안을 가리키는 것을 모아, 목표가 **어떤 블록의 NUL·0 채움·0x09 꼬리 안**(블록 시작은 아님)인 것을 고른다 —
    블록 하나씩 대조로는 안 보이는 진입점이다(덤프에 없는 리터럴 풀 포인터 · 끝 점프). 그 포인터 값이 빌드에서 그대로인데 목표 꼬리 바이트가 바뀌었으면
    진입한 쪽이 우리 글자를 읽는다. → `[(포인터 위치, 목표, 원본 꼬리, 빌드 꼬리)]`.
    """
    spans = sorted((int(e["file_offset"], 16), int(e["file_offset"], 16) + len(bytes.fromhex(e["raw_hex"])) + 1) for e in entries)
    starts = [a for a, _ in spans]
    import bisect

    out = []
    for q in range(0, len(orig) - 3, 2):
        w = struct.unpack(">I", orig[q : q + 4])[0] - base
        if not (0 <= w < len(orig)):
            continue
        i = bisect.bisect_right(starts, w) - 1
        if i < 0:
            continue
        s, e = spans[i]
        te = slot_tail_end(orig, e - 1)
        if w == s or not (e - 1 <= w < te):
            continue
        if struct.unpack(">I", built[q : q + 4])[0] - base == w and orig[w:te] != built[w:te]:
            out.append((q, w, orig[w:te], built[w:te]))
    return out


def scan_file(orig, built, base, entries, moved_ok=None):
    """한 파일 → `(통계, 문제 목록, 이주 목록, 쪽 넘김 목록)`.

    `moved_ok`: 장부가 허용한 이주 블록 키 집합(`None` 이면 장부 대조를 안 한다).
    """
    size = len(built)
    ents = sorted(entries, key=lambda e: int(e["file_offset"], 16))
    offs = [int(e["file_offset"], 16) for e in ents]
    raws = [bytes.fromhex(e["raw_hex"]) for e in ents]
    # 원본 글 구간(블록들이 있던 자리) — G 규칙
    runs = []
    for o_, r_ in zip(offs, raws):
        e_ = slot_tail_end(orig, o_ + len(r_))
        if runs and o_ - runs[-1][1] <= MAX_GAP:
            runs[-1][1] = max(runs[-1][1], e_)
        else:
            runs.append([o_, e_])
    st = {k: 0 for k in ("블록", "대조", "핀", "이주", "제자리", "줄 수 변화", "쪽 넘김 추가", "표 칸·겹친 꼬리", "바이트 동일", "채움 블록", "채움 바이트")}
    bad, moved, pages, rows = [], [], [], []
    grow = []  # 제자리인데 원문보다 길어 이웃 칸을 이어 쓴 블록 — 이웃이 전부 이주했을 때만 허용
    # 1차: 각 블록의 최종 목표
    info = []
    for idx, e in enumerate(ents):
        off, raw = offs[idx], raws[idx]
        n = len(raw)
        key = f"#{e['entry_id']}"
        st["블록"] += 1
        ptrs = [int(q, 16) if isinstance(q, str) else q for q in e.get("ptr_at", [])]
        tg = set()
        for q in ptrs:
            tg.add(struct.unpack(">I", built[q : q + 4])[0] - base)
            if struct.unpack(">I", orig[q : q + 4])[0] - base != off:
                bad.append((key, f"원본 포인터 @{q:#x} 가 블록 시작을 안 가리킨다(덤프 어긋남)"))
        if len(tg) > 1:
            bad.append((key, f"한 블록의 포인터들이 서로 다른 목표를 가리킨다 {sorted(hex(x) for x in tg)}"))
            continue
        t = tg.pop() if tg else off
        if not ptrs:
            st["핀"] += 1
        if not (0 <= t < size):
            bad.append((key, f"포인터 목표가 파일 밖 {t:#x}"))
            continue
        # 표 칸·겹친 꼬리 — 원본이 NUL 로 안 끝나거나 다른 항목과 겹친다
        term_o = off + n < len(orig) and orig[off + n] == 0
        shared = any(
            j != idx and offs[j] < off + n + 1 and off < offs[j] + len(raws[j]) + 1 for j in (idx - 1, idx + 1) if 0 <= j < len(ents)
        )
        if not term_o or shared:
            st["표 칸·겹친 꼬리"] += 1
            blk = built[t : t + n] if t == off else block_at(built, t)[0]
            why, dl, dp = compare_blocks(raw, blk if t == off else blk)
            bad += [(key, w) for w in why] if t == off or why else []
            info.append(None)
            continue
        blk, term = block_at(built, t)
        if not term:
            bad.append((key, f"NUL 종단이 없다 @{t:#x}"))
            info.append(None)
            continue
        info.append((idx, key, off, n, t, blk))
    live = [(t, t + len(blk) + 1, key) for x in info if x for (_i, key, _o, _n, t, blk) in [x]]
    for a, b, x, y in overlaps(live):
        bad.append((a, f"{b} 와 최종 구간이 겹친다 @{x:#x}<{y:#x}"))
    live2 = [(a, b) for a, b, _k in live]
    for x in info:
        if not x:
            continue
        idx, key, off, n, t, blk = x
        raw = raws[idx]
        st["대조"] += 1
        if t == off and built[off : off + n] == raw:
            st["바이트 동일"] += 1
        why, dl, dp = compare_blocks(raw, blk)
        bad += [(key, w) for w in why]
        if dl:
            st["줄 수 변화"] += 1
        if dp > 0:
            st["쪽 넘김 추가"] += 1
            pages.append((key, off, t, dp))
        if t != off:
            st["이주"] += 1
            moved.append((key, off, t, n, len(blk)))
            if t & 1:
                bad.append((key, f"이주분이 홀수 주소 {t:#x}"))
            a, b = t, t + len(blk) + 1
            for p in outside_nonzero(orig, a, b, runs)[:1]:
                bad.append((key, f"이주분이 원본 글 구간 밖의 0 이 아닌 자리를 덮는다 @{p:#x}"))
            if moved_ok is not None and key not in moved_ok:
                bad.append((key, "장부(relocations.tsv)에 없는 이주"))
        else:
            st["제자리"] += 1
            if len(blk) < n:
                st["채움 블록"] += 1
                st["채움 바이트"] += n - len(blk)
            nxt = offs[idx + 1] if idx + 1 < len(offs) else size
            slot_end = nxt if nxt - (off + n) <= MAX_GAP else slot_tail_end(orig, off + n)
            if len(blk) > n:
                # 칸 꼬리의 0 채움(4바이트 정렬 틈)을 쓴 것은 허용 — 원본 0 인 자리만(0x09·코드·다음 블록은 안 건드린다)
                # 또는 **이주해 비운 이웃 칸**(구간 재깔기에서 첫 블록이 제자리에 남아 이웃 칸을 이어 쓴다) — 이주 판정이 끝난 뒤 아래에서 본다
                if any(orig[off + n : off + len(blk) + 1]):
                    grow.append((key, off, n, len(blk), idx))
                    continue
            for p in tail_gap_bad(orig, built, off, len(blk), slot_end, live2)[:3]:
                bad.append((key, f"칸 뒤 채움에 설명 안 되는 바이트 @{p:#x}"))
    # 비운 칸 = 이주한 블록의 원래 칸(+ 꼬리). 이어 쓴 바이트 중 원본이 0 이 아닌 자리는 모두 비운 칸 안이어야 한다.
    vacated = [(o_, slot_tail_end(orig, o_ + n_)) for (_i, _k, o_, n_, t_, _b) in (x for x in info if x) if t_ != o_]
    st["꼬리 진입점 변경"] = 0
    st["_꼬리진입"] = tail_entry_changed(orig, built, base, entries)
    st["꼬리 진입점 변경"] = len(st["_꼬리진입"])
    for q_, w_, a_, b_ in st["_꼬리진입"]:
        bad.append((f"@{q_:#x}", f"남이 포인터로 들어오는 꼬리 {w_:#x} 의 바이트가 바뀌었다 — 원본 {a_.hex()} → 빌드 {b_.hex()}(이주 풀이 못 쓰게 보호해야 한다)"))
    st["이웃 칸 인수"] = 0
    st["_인수"] = []
    for key, off, n, new_n, _idx in grow:
        stray = [p for p in range(off + n, off + new_n + 1) if orig[p] and not any(a <= p < b for a, b in vacated) and p >= slot_tail_end(orig, off + n)]
        if stray:
            bad.append((key, f"제자리 블록이 원문보다 길다 {new_n}B > {n}B (칸 꼬리 0 채움·비운 이웃 칸을 넘는다 @{stray[0]:#x})"))
        else:
            st["이웃 칸 인수"] += 1
            st["_인수"].append((key, off, n, new_n))
    return st, bad, moved, pages


def main():
    import common
    import patch_scn as P

    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    fo, mo = common.open_image(common.ORIG_BIN)
    fb, mb = common.open_image(dst)
    orig = {n: (lba, s) for n, lba, s in common.iso_files(mo)}
    tot, problems, notes = {}, [], []
    files = 0
    allowed = None
    try:
        import relocations as R

        allowed = R.allowed_moves()
    except Exception as exc:  # noqa: BLE001  (장부가 없으면 이주 허용 검사만 건너뛴다 — 아래에서 알린다)
        print(f"  ⚠ 재배치 장부를 못 읽었다({exc}) — 이주 허용 검사는 건너뛴다")
    for name, lba, size in common.iso_files(mb):
        if name not in orig or size > 3_000_000 or not P.SCN_RE.match(name):
            continue
        got = P.load(name)
        if not got:
            continue
        base, entries = got
        o = common.read_extent(mo, *orig[name])
        b = common.read_extent(mb, lba, size)
        ok = None if allowed is None else {k for f_, k in allowed if f_ == name}
        st, bad, _moved, _pages = scan_file(o, b, base, entries, ok)
        files += 1
        for k, v in st.items():
            if not k.startswith("_"):
                tot[k] = tot.get(k, 0) + v
        problems += [(name, k, w) for k, w in bad]
    allow_n = "-" if allowed is None else str(len(allowed))
    mark = "✅" if not problems else "🔴"
    print(
        f"  {mark} 구조 대조 — 파일 {files} · 대조 {tot.get('대조', 0):,}/{tot.get('블록', 0):,} 블록"
        f" (제자리 {tot.get('제자리', 0):,} · 이주 {tot.get('이주', 0):,} · 포인터 없는 핀 {tot.get('핀', 0):,} · 바이트 동일 {tot.get('바이트 동일', 0):,})"
        f" · 줄 수 변화(재조판 허용) {tot.get('줄 수 변화', 0):,} · 쪽 넘김 추가 {tot.get('쪽 넘김 추가', 0):,} · 표 칸·겹친 꼬리 {tot.get('표 칸·겹친 꼬리', 0):,} · 이웃 칸 인수 {tot.get('이웃 칸 인수', 0):,} · 꼬리 진입점 변경 {tot.get('꼬리 진입점 변경', 0):,} · 장부 이주 {allow_n} · 어긋남 {len(problems)}"
    )
    for name, k, w in problems[:30]:
        print(f"    ❌ {name} {k}: {w}")
    if len(problems) > 30:
        print(f"    … 외 {len(problems) - 30}건")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
