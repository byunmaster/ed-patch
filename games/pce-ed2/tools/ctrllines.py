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


_REF = re.compile(r"\{([@!])(\d+)\}")


def build(raw: bytes, tmpl: str, tab, system: bool = False) -> bytes:
    """틀 + 원문 제어 → 새 줄 바이트. 틀이 잘못이면 ValueError."""
    skel, ctrls, head10 = parse(raw, system)
    tmpl = tmpl.replace("\u3000", "   ")  # 전각 공백(12px) = 반각 공백(4px) 셋 — 글리프가 아니라 공백 바이트
    used: set[int] = set()
    out = bytearray(head10)
    pos = 0
    for m in _REF.finditer(tmpl):
        if m.start() > pos:
            out += tab.enc(tmpl[pos : m.start()])
        n = int(m.group(2))
        if n >= len(ctrls):
            raise ValueError(f"제어 {n} 번이 없다(원문 제어 {len(ctrls)}개)")
        used.add(n)
        if m.group(1) == "@":
            out += ctrls[n]
        pos = m.end()
    if pos < len(tmpl):
        out += tab.enc(tmpl[pos:])
    for n, c in enumerate(ctrls):
        if n not in used and c[0] in STRUCT:
            raise ValueError(f"구조 제어 {n} 번({c.hex(' ')})을 틀이 가리키지 않았다 — 쓰려면 {{@{n}}}, 버리려면 {{!{n}}}")
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
    for rel in sorted(dialogue.package_chars()):
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
