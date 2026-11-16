"""알선소 게시판 「본문 4줄」 안 — 요약과 본문 사이 빈 줄을 없애고(창 6행 그대로) 의뢰별 본문 슬롯 수를 늘린다.

    python3 tools/board4.py --gen      # board4_ed4.json 을 만든다(어느 의뢰가 몇 줄이 되나)
    python3 tools/board4.py --verify   # 구운 롬을 읽어 검산

🔴 기본 켬(마스터 확인 11-06). `ED_BOARD_4LINE=0` 이면 옛 3줄 배치로 굽는다.

구조(11-06 실측, `docs/devlog.md`):
  · 의뢰 표(`0x767D8`, 8B)의 u16 = (시작 색인 − 1) | ((본문 슬롯 수 + 2) << 12). 슬롯 수는 **데이터**다. 코드는 [요약, 줄바꿈, 색, (줄바꿈, 슬롯)×슬롯 수]를 만들어 그린다.
  · 슬롯 = 문자열 포인터 표(607 항목)의 **연속된** 색인. 슬롯을 늘리려면 의뢰 하나를 표 끝(색인 607~)의 새 구간으로 옮긴다 — 표 항목은 요약·서명이 기존 문자열을 그대로 가리키고 본문 줄은 새 문자열이다.
  · 새 줄 문자열은 그 의뢰의 옛 본문 문자열 자리(죽은 자료)를 먼저 쓰고, 모자라면 글리프 arena 의 남은 자리(`uitext.ARENA_FREE`)를 쓴다.
  · 빈 줄 제거: `0x8003FA3C` 의 `ori v0,zero,0x8001`(둘째 줄바꿈) → `0x8010`(색 코드) — 줄바꿈 하나가 빠져 본문이 행 1부터 시작한다. 보상 줄은 행 5 그대로, 창 크기·인물 가림은 그대로다.
서명 줄(부크·촌장 등)은 앞쪽을 빈 글자로 채운 문자열이라 오른쪽에 붙는다.
"""

import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))
import common

DATA = os.path.join(common.ROOT, "board4_ed4.json")
QUESTS = 0x767D8  # 의뢰 표 8B 항목(EXE 파일 오프셋)
STRTBL = 0x72B88
N_ORIG = 607  # 포인터 표 원래 항목 수
RESERVE = 200  # 새 색인 구간 몫 — 표 뒤에 비워 두는 항목 수
BLANK_ROW_PATCH = (0x8003FA3C, 0x34028001, 0x34028010)  # (주소, 원판 명령, 새 명령)
MAX_LINES = 4  # 본문 최대 줄 수(행 1~4, 보상 줄은 행 5)
CELLS = 16  # 줄 칸 수 — 공백·부호도 한 칸


def enabled():
    return os.environ.get("ED_BOARD_4LINE") != "0"  # 기본 켬(마스터 확인 11-06) — =0 이면 옛 3줄 배치


def load():
    with open(DATA, encoding="utf-8") as f:
        return {int(k): v for k, v in json.load(f)["quests"].items()}


def generate():
    """본문을 지금 슬롯 수 안에 못 담는 의뢰 → {의뢰: {"lines": [...], "sig": 서명|None}} 를 `board4_ed4.json` 에 쓴다. 문안은 불변, 줄 구분만."""
    import board_text as B
    import reflow_board as R

    b = B.Board()
    sigs = R.signatures()
    out, failed = {}, []
    for q, a1, a2, _r in b.quests():
        t = b.texts(a1, a2)
        body = t[1:]
        sg = sigs.get(q) or sigs.get(str(q))
        main, merged, sep = body, False, False
        if sg:
            if body[-1].strip() == sg:
                main, sep = body[:-1], True
            elif body[-1].endswith(sg):
                main, merged = [*body[:-1], body[-1][: -len(sg)].rstrip()], True  # 서명이 본문 줄에 붙어 있다 → 떼어 별도 줄로
        words = " ".join(x for x in main if x)
        fits = B.reflow(t[0], list(main))[0] is not None
        if fits and not merged:
            continue
        for n in range(1, MAX_LINES + 1):
            lines, _why = B.reflow(t[0], [words] + [""] * (n - 1))
            if lines is not None:
                break
        else:
            failed.append(q)
            continue
        lines = [x for x in lines if x]
        out[str(q)] = {"lines": lines, "sig": sg, "sig_sep": sep}
    doc = {
        "_설명": "게시판 본문 4줄 안(ED_BOARD_4LINE=1)에서 본문 줄 수가 느는 의뢰 — 문안 불변, 줄 구분만. 서명(sig)은 별도 줄(오른쪽)이다. 줄 칸 수 16 이내(공백·부호 한 칸). `board4.py --gen` 으로 만든다.",
        "quests": out,
    }
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return out, failed


def _u16(exe, off):
    return struct.unpack_from("<H", exe, off)[0]


def _str_span(exe, a):
    """앞의 0 워드(왼쪽 채움)도 문자열 몫 — 끝은 0xFFFF 까지."""
    s = a
    while _u16(exe, a) != 0xFFFF:
        a += 2
    return s, a + 2


def apply(exe, table):
    """(구운) 실행파일 버퍼에 4줄 안을 얹는다 — `uitext.apply` 뒤. 반환 (바뀐 의뢰 수, 쓴 새 항목 수)."""
    import halfwidth
    import uitext

    T = uitext.RELOC.get(STRTBL)
    if T is None:
        raise SystemExit("🔴 게시판 4줄: 문자열 표가 arena 로 안 옮겨졌다 — 새 색인 자리가 없다")
    data = load()
    pad = table[" "]
    free = [list(x) for x in uitext.ARENA_FREE if x[0] >= T]  # [시작, 끝] — 표 기준보다 앞 자리는 u16 오프셋이 못 닿는다
    nxt = N_ORIG
    for q, spec in sorted(data.items()):
        qoff = QUESTS + 8 * q
        v = _u16(exe, qoff)
        a1, a2 = (v & 0xFFF) + 1, (v >> 12) - 2
        ents = struct.unpack_from(f"<{N_ORIG}H", exe, T)
        spans = [_str_span(exe, T + ents[a1 + k]) for k in range(1, a2 + 1)]
        sig_sep = bool(spec.get("sig_sep"))  # 서명이 따로 한 슬롯이었다 — 그 자리는 죽은 자료가 되고 서명도 새 문자열로 다시 만든다(오른쪽 맞춤 채움을 칸 수에 맞게)
        main_spans = spans
        _add_free(free, [list(x) for x in main_spans if x[0] >= T])  # 이 의뢰의 옛 본문 문자열 자리가 죽은 자료가 됐다
        strs = []  # (바이트)
        for ln in spec["lines"]:
            codes = _codes(ln, table)
            strs.append(struct.pack(f"<{len(codes) + 1}H", *codes, 0xFFFF))
        sig_b = None
        if spec["sig"] is not None:
            sc = _codes(spec["sig"], table)
            sc = [pad] * (CELLS - len(sc)) + sc
            sig_b = struct.pack(f"<{len(sc) + 1}H", *sc, 0xFFFF)
        blobs = strs + ([sig_b] if sig_b else [])
        places = [None] * len(blobs)
        for k in sorted(range(len(blobs)), key=lambda k: -len(blobs[k])):  # 큰 것부터, 가장 꼭 맞는 빈자리에
            fits = [fr for fr in free if fr[1] - fr[0] >= len(blobs[k])]
            if not fits:
                raise SystemExit(
                    f"🔴 게시판 4줄: 의뢰 {q} 새 문자열 {len(blobs[k])}B 자리가 없다 — 남은 {sorted(b - a for a, b in free)}"
                )
            fr = min(fits, key=lambda fr: (fr[1] - fr[0], fr[0]))
            places[k] = fr[0]
            fr[0] += len(blobs[k])
        for blob, at in zip(strs + ([sig_b] if sig_b else []), places, strict=True):
            exe[at : at + len(blob)] = blob
        run = [ents[a1 - 1], ents[a1]]  # 목록 창 제목(구간 맨 앞 칸 = 시작 색인−1 이 아니라 시작 색인 자리) · 요약은 옛 문자열 그대로
        for at in places[: len(strs)]:
            run.append(at - T)
        if spec["sig"] is not None:
            run.append(places[len(strs)] - T)
        if nxt + len(run) > N_ORIG + RESERVE:
            raise SystemExit("🔴 게시판 4줄: 새 색인 자리 부족")
        for i, off in enumerate(run):
            if not 0 <= off <= 0xFFFF:
                raise SystemExit(f"🔴 게시판 4줄: 의뢰 {q} 오프셋 {off} 가 u16 을 넘는다")
            struct.pack_into("<H", exe, T + 2 * (nxt + i), off)
        struct.pack_into("<H", exe, qoff, (nxt & 0xFFF) | (len(run) << 12))  # 구간 시작(= 목록 제목 색인, 요약은 +1) | (본문 수+2)<<12, 본문 수 = 제목·요약 뺀 항목 수
        nxt += len(run)
    a, want, new = BLANK_ROW_PATCH
    o = halfwidth._off(a)
    got = int.from_bytes(exe[o : o + 4], "little")
    if got != want:
        raise SystemExit(f"🔴 게시판 빈 줄 자리 {a:#x} 가 원판이 아니다({got:#010x})")
    exe[o : o + 4] = new.to_bytes(4, "little")
    return len(data), nxt - N_ORIG


def _add_free(free, spans):
    """빈자리 목록에 [시작, 끝) 을 더하고 맞닿은 것은 합친다."""
    free.extend(spans)
    free.sort()
    out = []
    for fr in free:
        if out and fr[0] <= out[-1][1]:
            out[-1][1] = max(out[-1][1], fr[1])
        else:
            out.append(fr)
    free[:] = [fr for fr in out if fr[1] > fr[0]]


_DEAD = []


def dead_offsets():
    """원본 EXE 에서 옛 본문 문자열(요약·별도 서명 제외)의 시작 오프셋 집합 — 4줄 안이 덮어쓰는 자리."""
    if not _DEAD:
        import board_text as B
        import reflow_board as R

        b = B.Board()
        sigs = R.signatures()
        out = set()
        for q, spec in load().items():
            a1, a2 = next((x[1], x[2]) for x in b.quests() if x[0] == q)
            n = a2
            out |= {b.slot(a1 + k)[0] for k in range(1, n + 1)}
        _DEAD.append(out)
    return _DEAD[0]


def _codes(text, table):
    import uitext

    return uitext.kr_codes(text, table)


def _is_sig_slot(exe, T, ents, idx, sig, table):
    """그 슬롯이 서명만 든 별도 줄인가(앞은 빈 글자) — 글자를 되읽어 서명과 같은지."""
    inv = {c: ch for ch, c in table.items()}
    s, e = _str_span(exe, T + ents[idx])
    txt = "".join(inv.get(w, "?") for w in struct.unpack_from(f"<{(e - s) // 2 - 1}H", exe, s))
    return txt.strip() == sig


def readback(exe, table):
    """{의뢰 번호: [요약, 본문 줄…]} — 구운 실행파일에서 의뢰 표와 문자열 표를 다시 읽어 글자로 푼다(0 채움은 공백)."""
    import halfwidth

    o_l, o_a = halfwidth._off(0x8003FABC), halfwidth._off(0x8003FAC0)
    hi = struct.unpack_from("<I", exe, o_l)[0] & 0xFFFF
    lo = struct.unpack_from("<h", exe, o_a)[0]
    base = halfwidth._off(((hi << 16) + lo) & 0xFFFFFFFF)  # RAM 주소 → 파일 오프셋
    inv = {c: ch for ch, c in table.items()}
    out = {}
    for q in range(1, 125):
        v = _u16(exe, QUESTS + 8 * q)
        a1, a2 = (v & 0xFFF) + 1, (v >> 12) - 2
        if not (1 <= a2 <= 8 and a1 <= N_ORIG + RESERVE):
            continue
        lines = []
        for k in range(a2 + 1):
            a = base + _u16(exe, base + 2 * (a1 + k))
            ws = []
            while _u16(exe, a) != 0xFFFF:
                ws.append(_u16(exe, a))
                a += 2
            lines.append("".join(" " if w == 0 else inv.get(w, "?") for w in ws))
        out[q] = lines
    return out


def readback_titles(exe, table):
    """{의뢰 번호: 목록 창 제목} — 시작 색인 자리(요약 바로 앞) 문자열. 🔴 옛 판은 새 구간 앞에 제목 칸이 없어 앞 의뢰의 본문 줄이 목록 제목으로 나왔다(11-06)."""
    import halfwidth

    o_l, o_a = halfwidth._off(0x8003FABC), halfwidth._off(0x8003FAC0)
    hi = struct.unpack_from("<I", exe, o_l)[0] & 0xFFFF
    lo = struct.unpack_from("<h", exe, o_a)[0]
    base = halfwidth._off(((hi << 16) + lo) & 0xFFFFFFFF)
    inv = {c: ch for ch, c in table.items()}
    out = {}
    for q in range(1, 125):
        v = _u16(exe, QUESTS + 8 * q)
        a0, a2 = v & 0xFFF, (v >> 12) - 2
        if not (1 <= a2 <= 8 and a0 <= N_ORIG + RESERVE):
            continue
        a = base + _u16(exe, base + 2 * a0)
        ws = []
        while _u16(exe, a) != 0xFFFF:
            ws.append(_u16(exe, a))
            a += 2
        out[q] = "".join(" " if w == 0 else inv.get(w, "?") for w in ws)
    return out


def verify(image=None):
    """[사유] — 구운 롬의 게시판을 읽어 정본 문안과 대조: 줄이 16칸 안 · 본문 4줄 이하 · 글자가 정본과 같다(글자표가 못 푸는 코드 「?」는 와일드카드) · 4줄 안 의뢰는 데이터와 같다."""
    import board_text as B
    import hangul

    image = image or common.build_bin()  # 기본은 이 꼬리표의 구운 롬(원판이 아니다)
    exe = bytes(common.read_file(common.EXE_PATH, image=image))
    rb = readback(exe, hangul.load())
    rt = readback_titles(exe, hangul.load())
    b = B.Board()
    data = load()
    bad = []

    def same(got, want):
        got, want = got.strip(), want.strip()
        return len(got) == len(want) and all(g == w or g == "?" for g, w in zip(got, want, strict=True))

    for q, a1, a2, _r in b.quests():
        t = b.texts(a1, a2)
        if q in data:
            t = [t[0], *data[q]["lines"], *([data[q]["sig"]] if data[q]["sig"] else [])]
        if q in rt and not same(rt[q], b.slot(a1 - 1)[2]):  # 목록 창 제목
            bad.append(f"의뢰 {q}: 목록 제목 읽은 「{rt[q]}」 ≠ 정본 「{b.slot(a1 - 1)[2]}」")
        got = rb.get(q)
        if got is None:
            bad.append(f"의뢰 {q}: 못 읽었다")
            continue
        if len(got) != len(t):
            bad.append(f"의뢰 {q}: 줄 수 {len(got) - 1} ≠ 정본 {len(t) - 1}")
            continue
        if len(t) - 1 > MAX_LINES:
            bad.append(f"의뢰 {q}: 본문 {len(t) - 1}줄 > {MAX_LINES}")
        for k, (g, w) in enumerate(zip(got, t, strict=True)):
            if len(g) > CELLS:
                bad.append(f"의뢰 {q} {'요약' if k == 0 else f'본문 {k}'}: {len(g)}칸 > {CELLS} 「{g}」")
            if not same(g, w):
                bad.append(f"의뢰 {q} 줄 {k}: 읽은 「{g}」 ≠ 정본 「{w}」")
            # 마스터 11-06: 줄 첫머리 부호(고아)·첫 칸 공백·빈 줄 0 (보상 줄 앞 빈 본문 줄은 슬롯 채움이라 제외)
            if k and w and w[:1] in " .,…!?)」』:;·":
                bad.append(f"의뢰 {q} 본문 {k}: 줄 첫머리 {'공백' if w[0] == ' ' else '부호'} 「{w}」")
        body = t[1:]
        while body and not body[-1].strip():
            body.pop()
        if any(not x.strip() for x in body):
            bad.append(f"의뢰 {q}: 본문 중간에 빈 줄")
    return bad


def main():
    if "--verify" in sys.argv:
        bad = verify(sys.argv[sys.argv.index("--verify") + 1] if len(sys.argv) > sys.argv.index("--verify") + 1 else None)
        print("\n".join(bad) or "게시판 4줄: 이상 없음")
        raise SystemExit(1 if bad else 0)
    if "--gen" in sys.argv:
        out, failed = generate()
        n = sum(1 + len(v["lines"]) + (1 if v["sig"] else 0) for v in out.values())
        print(f"의뢰 {len(out)}건 · 새 색인 {n}개 · 4줄에도 안 드는 것 {failed}")
        raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
