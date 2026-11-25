"""제어가 낀 줄(상점 금액 · 아이템 수령/장비 · 보물상자 · 화자 머리줄 · 이벤트)을 **틀**로 번역한다.

`dialogue.py` 는 제어가 안 낀 「단순한 줄」만 PS1 문안으로 바꾼다. 이 모듈은 나머지 — 이름(`1C`)·항목(`1D`)·수(`1E`) 자리표,
쪽 넘김(`13`)·대기(`12`)·창 열기(`0C`)·강조(`06`…`04`) 따위가 글 사이에 끼어 있는 줄 — 을 **한국어 틀**로 다시 짠다.

원리
- 줄을 **뼈대**로 읽는다: 글(가나·한자)은 읽기용 일본어로 풀고(`18 a b c d` 는 `14 a b c d` 와 같다 — 강조를 끝내고 글 4바이트를 잇는 줄임꼴),
  나머지 제어는 `{HH arg…}` 로 둔다. 말 속도(`10`)·멈춤(`11`)은 뼈대에서 뺀다(같은 줄이 속도값만 다른 사본이 많다).
  뼈대의 sha1 앞 12자가 열쇠다 — **원문은 데이터에 두지 않는다**(저작권 규칙 · 게임 폴더에 JP→KR 표를 두지 않는다).
- `data/ctrl_lines.tsv` = `열쇠 <TAB> 한국어 틀 [<TAB> 메모]`. 틀 문법: 글 · `\\n`(줄바꿈 `0D`) · `\\f`(쪽 넘김 `13 0D`) · `{@N}` = 원문의 **N 번째 제어**
  (`0D`·`0E`·`0F`·`10`·`11` 제외, 0부터)를 그 자리에 그대로 낸다. 병기 조사(`은(는)` 등)는 `font.mark_josa` 가 앞 글자로 풀거나 런타임 훅으로 넘긴다.
- 틀이 안 가리킨 제어는 버린다 — 단 **구조 제어**(`12` `13` `14` `16` `17` `1A` `0C`)를 버리려면 틀에 `{!N}` 으로 명시해야 한다(실수 방지).
- 검토표(`work/review/ctrl_lines_todo.tsv`, 원문 포함 → 커밋 금지)가 열쇠 · 제어 번호 · 나오는 자리를 보여 준다: `python3 tools/ctrllines.py --review`.
"""

import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
import jptext

TSV = common.GAME_DIR / "data" / "ctrl_lines.tsv"
DROP_FREE = {0x10, 0x11, 0x0D, 0x0E, 0x0F}  # 뼈대·번호에서 빠지는 제어(속도 · 멈춤 · 줄바꿈 · 가나 모드)
STRUCT = {0x0C, 0x12, 0x13, 0x14, 0x16, 0x17, 0x1A}  # 틀이 가리키지도 `{!N}` 으로 버리지도 않으면 오류
_table: dict[str, str] | None = None


def _args(system: bool) -> dict:
    """제어 인자 길이 — 대사 줄은 `jptext.ARGS`, **본 프로그램 시스템 문자열**은 `13`(이름 자리표)이 1바이트·`16`/`18` 이 4바이트(`systext.ARGS`)다."""
    if system:
        import systext

        return systext.ARGS
    return jptext.ARGS


def normalize(raw: bytes, system: bool = False) -> bytes:
    """`18 a b c d` → `14 a b c d`(강조 끝 + 글 4바이트). 다른 제어의 인자는 건드리지 않는다. 시스템 문자열은 그대로(규칙이 다르다)."""
    if system:
        return raw
    out = bytearray()
    i = 0
    while i < len(raw):
        a = raw[i]
        if a < 0x20:
            n = 1 + jptext.ARGS.get(a, 0)
            if a == 0x18:
                out.append(0x14)
                out += raw[i + 1 : i + n]
            else:
                out += raw[i : i + n]
            i += n
        elif 0x80 <= a <= 0x9F or a >= 0xE0:
            out += raw[i : i + 2]
            i += 2
        else:
            out.append(a)
            i += 1
    return bytes(out)


def blank_item_particle(line: bytes) -> bytes:
    """`1D xx`(항목 이름 + 조사 가나 xx 한 글자 — 6B=だ · 6E=で · CA=は …) 뒤에 우리 공백 `60` 이 곧바로 오면, 원문 가나가 화면에 찍히지 않게 xx 를 빈 칸(`60` 전각 공백)으로 바꾸고 우리 공백은 뺀다
    (상점 구입 줄 「폭약だ 말이군요」 — 11-05 마스쿤 도구점 실화면). 뒤에 한국어 조사 훅(`F9`)이 오는 꼴(`1D CA F9 …`)은 건드리지 않는다."""
    out = bytearray()
    i = 0
    while i < len(line):
        a = line[i]
        if a < 0x20:
            n = 1 + jptext.ARGS.get(a, 0)
            if a == 0x1D and line[i + 1 : i + 2] and line[i + 2 : i + 3] == b"\x60":
                out += b"\x1d\x60"
                i += 3
                continue
            out += line[i : i + n]
            i += n
        elif 0x80 <= a <= 0x9F or a >= 0xE0:
            out += line[i : i + 2]
            i += 2
        else:
            out.append(a)
            i += 1
    return bytes(out)


def parse(raw: bytes, system: bool = False):
    """정규화한 줄 → (뼈대 문자열, 제어 목록[N] = 바이트, 맨 앞 `10 nn`)."""
    raw = normalize(raw, system)
    ARGS = _args(system)
    parts: list[str] = []
    ctrls: list[bytes] = []
    head10 = b""
    run = bytearray()
    kana = False

    def flush():
        nonlocal run
        if run:
            parts.append(jptext.decode((b"\x0e" if kana else b"") + bytes(run)).replace("{0E}", ""))
            run = bytearray()

    i = 0
    while i < len(raw):
        a = raw[i]
        if a < 0x20:
            n = 1 + ARGS.get(a, 0)
            blob = raw[i : i + n]
            i += n
            if a in (0x0E, 0x0F):
                flush()
                kana = a == 0x0E
            elif a == 0x0D:
                flush()
                parts.append("/")
            elif a in (0x10, 0x11):
                flush()
                if a == 0x10 and not parts and not ctrls and not head10:
                    head10 = blob
            else:
                flush()
                ctrls.append(blob)
                parts.append("{" + " ".join(f"{x:02X}" for x in blob) + "}")
        elif 0x80 <= a <= 0x9F or a >= 0xE0:
            run += raw[i : i + 2]
            i += 2
        else:
            run.append(a)
            i += 1
    flush()
    return "".join(parts), ctrls, head10


def key_of(skel: str) -> str:
    return hashlib.sha1(skel.encode("utf-8")).hexdigest()[:12]


def table() -> dict[str, str]:
    global _table
    if _table is None:
        _table = {}
        if TSV.exists():
            for ln in TSV.read_text(encoding="utf-8").splitlines():
                if not ln.strip() or ln.startswith("#"):
                    continue
                cols = ln.split("\t")
                _table[cols[0]] = cols[1].replace("\\n", "\n").replace("\\f", "\f")
    return _table


_REF = re.compile(r"\{([@!])(\d+)\}|\{\$((?:[0-9A-Fa-f]{2})+)\}")  # `{$8267}` = 원문 글꼴 코드(SJIS) 그대로 — 강조(`06`) 안에서 우리 글리프는 깨지므로(좁은 숫자 글꼴) 원판 글자를 쓴다(ＨＰ)


def strip_refs(tmpl: str) -> str:
    """틀 → 화면 글(검사용) — 제어 자리표는 지우고 `{$..}` 는 SJIS 글자로 푼다."""
    return _REF.sub(lambda m: bytes.fromhex(m.group(3)).decode("cp932") if m.group(3) else "", tmpl)


def _jp_marks(raw: bytes, system: bool) -> tuple[list[tuple[int, bytes]], int]:
    """원문 줄의 본문 한복판 연출 타이밍 제어 → ([(앞선 원문 글자 수, `10 nn`/`11 nn nn`)…], 원문 글자 수) — `dialog.parse_frame` 의 마크와 같은 셈이다
    (여백 `A0` · 반각 공백 `60` 은 글자로 안 센다 · `18 a b c d` 는 글자 둘). 줄 머리의 `10 nn`(뼈대의 `head10`)은 뺀다. 시스템 문자열엔 없다."""
    if system:
        return [], 0
    ARGS = jptext.ARGS
    marks: list[tuple[int, bytes]] = []
    n = 0
    seen = False  # 머리 `10` 이전에 다른 게 나왔나
    head10 = False
    in_name = False  # `16` … `14` 사이(화자 이름 칸)는 글자로 안 센다
    i = 0
    while i < len(raw):
        a = raw[i]
        if a < 0x20:
            k = 1 + ARGS.get(a, 0)
            blob = raw[i : i + k]
            if a == 0x16:
                in_name = True
                seen = True
            elif a == 0x14:
                in_name = False
                seen = True
            elif a == 0x18:
                n += 2
            elif a in (0x10, 0x11):
                if a == 0x10 and not seen and not head10:
                    head10 = True
                else:
                    if a == 0x11 and i + k < len(raw) and 0x30 <= raw[i + k] <= 0x39:  # 멈춤 바로 뒤 ASCII 숫자 한 글자(원판의 보이지 않는 글자) — 멈춤에 붙여 보존(11-07)
                        blob = raw[i : i + k + 1]
                        k += 1
                    marks.append((n, blob))
            elif a not in (0x0D, 0x0E, 0x0F):
                seen = True
                in_name = False  # 이름 칸은 `14` 말고 다른 제어(이름 자리표 따위)로도 끝난다
            i += k
        else:
            seen = True
            k = 2 if (0x80 <= a <= 0x9F or a >= 0xE0) else 1
            if not in_name and raw[i : i + k] not in (b"\xa0", b"`"):
                n += 1
            i += k
    return marks, n


def _with_marks(items: list, marks: list[tuple[int, bytes]], jp_n: int, tab) -> bytes:
    """틀의 글 조각 사이에 원문 타이밍 제어를 **구절 경계**에 되살린다 — 위치는 원문 글자 비율을 한글 글자 수에 옮기고 가장 가까운 어절·부호 경계로 당긴다(`dialogue._encode` 와 같은 잣대, ±6자)."""
    import dialogue
    import font

    texts = [(font.mark_josa(v) if k == "t" else v) for k, v in items]
    ink_idx: list[tuple[int, int]] = []  # (조각, 글자 위치) — 글자로 세는 칸들
    in_name = False  # `16` 뒤 다음 제어까지는 화자 이름 칸 — 글자로 안 센다(타이밍 제어가 이름 한복판에 끼면 이름이 깨진다)
    for ti, (kind, _v) in enumerate(items):
        if kind == "t":
            for ci, ch in enumerate(texts[ti]):
                if not in_name and ch not in " \n\f" and ch not in font.JOSA_MARK:
                    ink_idx.append((ti, ci))
        else:
            in_name = _v[:1] == b"\x16"
    k = len(ink_idx)

    def ch_at(p):
        ti, ci = ink_idx[p]
        return texts[ti][ci]

    def bound(p):  # p = 「p 번째 글자 앞」 — 어절·부호 경계인가
        if p <= 0 or p >= k:
            return True
        ti, ci = ink_idx[p]
        pti, pci = ink_idx[p - 1]
        prev = texts[pti][pci]
        spaced = ti != pti or texts[ti][ci - 1] in " \n\f"
        if not spaced and prev not in dialogue._BOUND:
            return False
        if prev in dialogue._PUNCT_RUN and ch_at(p) in dialogue._PUNCT_RUN:
            return False
        w, j = "", p - 1
        while j >= 0:
            w = ch_at(j) + w
            if j == 0 or ink_idx[j - 1][0] != ink_idx[j][0] or ink_idx[j - 1][1] + 1 != ink_idx[j][1]:
                break
            j -= 1
        return w not in dialogue._DET

    at: dict[int, list[bytes]] = {}
    taken: set[int] = set()
    for n, b in marks:
        if b[:1] == b"\x11" and len(b) == 3 and not 0x30 <= b[2] <= 0x39:
            b = b[:2] + b"0"  # 멈춤 둘째 인자가 숫자가 아니면 엔진이 글자로 찍는다(dialogue._encode 와 같다)
        t = 0 if jp_n <= 0 else max(0, min(k, round(n / jp_n * k)))
        if n == 0 or k == 0:
            best = 0
        else:
            best = min((q for q in range(max(0, t - 6), min(k, t + 6) + 1) if bound(q) and q not in taken), key=lambda q: (abs(q - t), q), default=t)
        taken.add(best)
        at.setdefault(best, []).append(b)
    out = bytearray()
    ink = 0
    in_name2 = False
    for ti, (kind, v) in enumerate(items):
        if kind != "t":
            out += v
            in_name2 = v[:1] == b"\x16"
            continue
        run = ""
        for ch in texts[ti]:
            counted = not in_name2 and ch not in " \n\f" and ch not in font.JOSA_MARK
            if counted and ink in at:
                if run:
                    out += tab.enc(run)
                    run = ""
                for b in at.pop(ink):
                    out += b
            run += ch
            if counted:
                ink += 1
        if run:
            out += tab.enc(run)
    for q in sorted(at):  # 끝 위치 — 마지막 글자 뒤(조각 사이 제어는 그 뒤에 이미 나갔다)
        for b in at[q]:
            out += b
    return bytes(out)


def build(raw: bytes, tmpl: str, tab, system: bool = False) -> bytes:
    """틀 + 원문 제어 → 새 줄 바이트. 틀이 잘못이면 ValueError."""
    skel, ctrls, head10 = parse(raw, system)
    padmode = tmpl.startswith("¦")  # 장 제목 띠 꼴 — 공백(전각·반각)을 그려서 지우는 `a0` 칸(12px)으로 낸다(앞 줄의 글을 덮어 지워야 하는 디버그 마을 제목 줄)
    if padmode:
        tmpl = tmpl[1:]
    narrow = tmpl.startswith("⟦")  # 좁은 글꼴(`06` 모드 한글, 디버그 마을 목록) 틀 — 글자를 `narrowhan` 부호(리드 FA)로 낸다
    if narrow:
        import narrowhan

        tmpl = tmpl[1:]
    enc_text = narrowhan.enc if narrow else ((lambda v: b"\xa0".join(tab.enc(x) for x in v.split("\u3000"))) if padmode else tab.enc)
    tmpl = tmpl.replace("\u3000", "   ")  # 전각 공백(12px) = 반각 공백(4px) 셋 — 글리프가 아니라 공백 바이트
    used: set[int] = set()
    items: list[tuple[str, object]] = []  # ("t", 글) · ("b", 바이트)
    pos = 0
    for m in _REF.finditer(tmpl):
        if m.start() > pos:
            items.append(("t", tmpl[pos : m.start()]))
        if m.group(3):
            items.append(("b", bytes.fromhex(m.group(3))))
            pos = m.end()
            continue
        n = int(m.group(2))
        if n >= len(ctrls):
            raise ValueError(f"제어 {n} 번이 없다(원문 제어 {len(ctrls)}개)")
        used.add(n)
        if m.group(1) == "@":
            items.append(("b", ctrls[n]))
        pos = m.end()
    if pos < len(tmpl):
        items.append(("t", tmpl[pos:]))
    for n, c in enumerate(ctrls):
        if n not in used and c[0] in STRUCT:
            raise ValueError(f"구조 제어 {n} 번({c.hex(' ')})을 틀이 가리키지 않았다 — 쓰려면 {{@{n}}}, 버리려면 {{!{n}}}")
    marks, jp_n = _jp_marks(raw, system)
    if marks:
        import dialogue

        if not dialogue.KEEP_MARKS:
            marks = []
    if marks:
        return bytes(head10) + _with_marks(items, marks, jp_n, tab)
    out = bytearray(head10)
    for kind, v in items:
        out += enc_text(v) if kind == "t" else v
    return bytes(out)


def edit_chunk(orig: bytes, cur: bytes, tab, stats=None) -> bytes:
    """`orig`(원본 덩이)의 줄 중 틀이 있는데 아직 안 바뀐 줄(`cur` 의 같은 줄 == 원본)만 틀로 바꾼다."""
    t = table()
    if not t:
        return cur
    lo = orig.split(b"\x00")
    lc = cur.split(b"\x00")
    if len(lo) != len(lc):
        return cur
    for i, (o, c) in enumerate(zip(lo, lc, strict=True)):
        if o != c or not o:
            continue
        skel, _ctrls, _h = parse(o)
        tmpl = t.get(key_of(skel))
        if tmpl is None:
            continue
        lc[i] = build(o, tmpl, tab)
        if stats is not None:
            stats["제어 줄 번역"] = stats.get("제어 줄 번역", 0) + 1
    return b"\x00".join(lc)


def review(out_path: Path, built_tag: str | None = None) -> int:
    """원본 일본어가 **지금 빌드에도 그대로 남은** 줄을 뼈대별로 모아 검토표로 쓴다 — 원문 포함이라 work/review 에만 둔다.
    `built_tag` = 비교할 빌드 꼬리표(`work/build/<꼬리표>/ed2.iso`, 기본 제품 `common.BUILD_TAG`)."""
    import package
    from collections import defaultdict

    import dialogue

    t = table()
    tag = built_tag or common.BUILD_TAG
    every = tag == "all"  # 「all」 = 빌드와 비교하지 않고 원본의 모든 줄(틀 작성 때 열쇠 확인용)
    built = b"" if every else (common.BUILD_DIR / tag / "ed2.iso").read_bytes()

    def btrack(rel):
        out = []
        for i in range(128):
            off = (common.T2_SECTOR + rel + i) * common.RAW + common.USER_OFF
            out.append(built[off : off + common.USER])
        return b"".join(out)

    where = defaultdict(list)
    skels = {}
    for rel in sorted(dialogue.package_chars()):
        po = bytes(common.track_data(rel, 128))
        pb = po if every else btrack(rel)
        co = [(a, b) for a, b in package.chunks(po) if po[a : a + 8] != package.SENTINEL]
        cb = [(a, b) for a, b in package.chunks(pb) if pb[a : a + 8] != package.SENTINEL]
        for (a, b), (a2, b2) in zip(co, cb, strict=False):
            do = package.decode_chunk(po, a, b)[0]
            db = package.decode_chunk(pb, a2, b2)[0]
            lo, lb = do.split(b"\x00"), db.split(b"\x00")
            if len(lo) != len(lb):
                continue
            for i, (x, y) in enumerate(zip(lo, lb, strict=True)):
                if not x or (x != y and not every):  # 빌드가 이미 바꾼 줄은 대상이 아니다
                    continue
                skel, ctrls, _h = parse(x)
                if not re.search(r"[぀-ヿ一-鿿]", re.sub(r"\{[^}]*\}", "", skel)):
                    continue
                k = key_of(skel)
                where[k].append(f"{rel}:{a}:{i}")
                skels[k] = (skel, ctrls)
    rows = []
    for k, (skel, ctrls) in skels.items():
        mark = "있음" if k in t else ""
        idx = " ".join(f"{n}={c.hex(' ')}" for n, c in enumerate(ctrls))
        rows.append((k, mark, len(where[k]), where[k][0], skel, idx))
    rows.sort(key=lambda r: (r[1] != "", -r[2], r[0]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "열쇠\t틀\t횟수\t첫 자리\t뼈대(원문)\t제어 번호\n" + "\n".join("\t".join(map(str, r)) for r in rows) + "\n",
        encoding="utf-8",
    )
    return len(rows)


def system_strings():
    """본 프로그램 리터럴 문자열 → {"s"+열쇠: (뱅크, 오프셋, 원문 바이트)} — 시스템 문자열 틀의 열쇠 목록(`systext.scan_literals`)."""
    import layout
    import systext

    prog = layout.Prog()
    out = {}
    for bank, off in sorted(systext.scan_literals(prog)):
        s = prog.o(bank, 0, layout.BANK)
        raw = s[off : s.index(0, off)]
        out["s" + key_of(parse(raw, True)[0])] = (bank, off, raw)
    return out


def verify() -> int:
    """`data/ctrl_lines.tsv` 의 모든 틀을 원본 줄에 대 본다 — 열쇠가 어느 원본 줄에도 안 맞으면(낡은 틀) · 틀이 어느 사본에서든 오류면 실패(종료 코드 1)."""
    import package
    from collections import defaultdict

    import dialogue
    import font

    t = table()
    tab = font.GlyphTable()
    hits: dict[str, int] = defaultdict(int)
    errs = []
    import residual_gate

    for rel in sorted(set(dialogue.package_chars()) | set(residual_gate.DEBUG_RELS)):  # 디버그로 닿는 패키지(258·배틀 테스트 마을)도 틀이 닿는지 본다
        po = bytes(common.track_data(rel, 128))
        for a, b in package.chunks(po):
            if po[a : a + 8] == package.SENTINEL:
                continue
            d = package.decode_chunk(po, a, b)[0]
            for i, line in enumerate(d.split(b"\x00")):
                if not line:
                    continue
                k = key_of(parse(line)[0])
                if k in t:
                    hits[k] += 1
                    try:
                        build(line, t[k], tab)
                    except ValueError as e:
                        errs.append(f"{k} @{rel}:{a}:{i}: {e}")
    from collections import defaultdict as _dd  # noqa: F401

    sysmap = system_strings()
    for k, (bank, off, raw) in sysmap.items():
        if k in t:
            hits[k] += 1
            try:
                build(raw, t[k], tab, True)
            except ValueError as e:
                errs.append(f"{k} @{bank:02X}+{off:04X}: {e}")
    stale = [k for k in t if k not in hits]
    for e in errs[:20]:
        print("✗", e)
    for k in stale[:20]:
        print("✗ 어느 원본 줄에도 안 맞는 낡은 틀", k)
    print(f"제어 줄 틀 {len(t)}개 · 원본 줄 {sum(hits.values())}곳에 적용 · 오류 {len(errs)} · 낡은 틀 {len(stale)}")
    return 1 if errs or stale else 0


if __name__ == "__main__":
    if "--verify" in sys.argv:
        sys.exit(verify())
    if "--review" in sys.argv:
        tag = sys.argv[sys.argv.index("--review") + 1] if len(sys.argv) > sys.argv.index("--review") + 1 else None
        name = "ctrl_lines_all.tsv" if tag == "all" else "ctrl_lines_todo.tsv"
        n = review(common.REVIEW_DIR / name, tag)
        print(f"검토표 {n}줄 → work/review/{name}")
