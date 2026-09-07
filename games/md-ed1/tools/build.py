"""md-ed1 빌드 — 정본(script/*.json)만 읽어 work/build/<꼬리표>/ed1-kr.bin 을 만든다. 결정적이다.

    python3 tools/build.py            # 빌드 + 게이트
    python3 tools/build.py --check    # 빌드 없이 게이트만(정본 검증)

안전장치(docs/patcher-checklist.md):
- 입력 지문(common.rom) · 쓰기는 `_write(label, lo, hi)` 한 통로 — **허용 구간 밖은 즉시 거부**
  (대본 아카이브 자리 · 꼬리 빈 공간 · 글꼴 리소스 0 · 헤더 체크섬).
- 끝에 원본과 byte 대조: 허용 구간 밖은 한 바이트도 안 바뀌어야 한다.
- 화면에 나가는 바이트 게이트: 미수록 글자(인코딩 불가) · 18칸 초과 줄 · 3줄 초과 페이지 ·
  참조 제어코드 불일치 → **빌드 실패**. 실패하면 산출물을 `.failed` 로 이름 바꾼다.
"""

import json
import re
import struct
import sys
from pathlib import Path
from typing import ClassVar

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(common_root := Path(__file__).resolve().parents[3] / "shared"))
import archives
import battle
import captions
import common
import gfxtext
import hangul
import lz
import scene
import sysmsg
import tables
import textmap
from text import krwrap

WIDTH = 18  # 대사창 한 줄(12px 피치, 안쪽 218px)
LINES = 3

SCRIPT_LO, SCRIPT_HI = 0x135324, 0x1918D2  # 대본 블록 자리(색인 0x134FA0 은 항목만 고친다)
TAIL_LO, TAIL_HI = common.FREE_TAIL


BATTLE_LO, BATTLE_HI = 0x0CAB04, 0x0D85B4  # 전투 아카이브 LZ 구간(첫 블록 시작 ~ 끝 블록 끝)


class Rom:
    """쓰기 통로 하나 — 허용 구간(라벨) 밖은 거부."""

    ALLOWED: ClassVar[dict[str, tuple[int, int]]] = {
        "script-table": (0x134FA0, 0x134FA0 + 225 * 4),
        "battle-table": (battle.ARCHIVE, battle.ARCHIVE + battle.COUNT * 4),
        "battle": (BATTLE_LO, BATTLE_HI),
        "script": (SCRIPT_LO, SCRIPT_HI),
        "tail": (TAIL_LO, TAIL_HI),
        "font0-header": (0x1A54D2, 0x1A54DE),
        "font0-table": (0x1A551A, 0x1A6080),
        "font0-glyphs": (0x1A62CE, 0x1BA1FA),
        "font1-header": hangul.FONT1_HDR,
        "checksum": (0x18E, 0x190),
        **{f"table:{t[0]}": (t[1], t[1] + (t[2] + 1) * t[4]) for t in tables.TABLES},
        **{f"table:{g[0]}": (g[1], g[1] + 0x200) for g in tables.ZGROUPS},
        **{f"table:{t[0]}": (t[1], t[1] + t[2] * t[3]) for t in tables.SLOTS},
        "font2-glyphs": hangul.FONT2_GLYPHS,
        "font4-header": hangul.FONT4_HDR,
        "font4-table": hangul.FONT4_TABLE,
        "font4-glyphs": hangul.FONT4_GLYPHS,
    }

    def __init__(self, data: bytes):
        self.orig = data
        self.buf = bytearray(data)
        self.log: list[tuple[str, int, int]] = []
        self.allowed = dict(
            self.ALLOWED, **sysmsg.allowed(data), **gfxtext.allowed(), **captions.allowed(data)
        )

    def write(self, label: str, at: int, data: bytes) -> None:
        lo, hi = self.allowed[label]
        if not (lo <= at and at + len(data) <= hi):
            raise SystemExit(
                f"[{label}] 허용 구간 밖 쓰기 {at:#x}+{len(data)} (구간 {lo:#x}~{hi:#x})"
            )
        self.buf[at : at + len(data)] = data
        self.log.append((label, at, len(data)))

    def verify_immutable(self) -> None:
        marks = bytearray(len(self.buf))
        for lo, hi in self.allowed.values():
            marks[lo:hi] = b"\x01" * (hi - lo)
        for i, (a, b) in enumerate(zip(self.orig, self.buf, strict=True)):
            if a != b and not marks[i]:
                raise SystemExit(f"무변경 구간이 바뀌었다 @{i:#x}")


def normalize(text: str) -> str:
    """부호 규칙(유저 확정 2026-09-05): 온점·쉼표·공백은 반각, 「…」은 전각 하나, 「…」 뒤에 온점 없음."""
    text = text.replace("...", "…").replace("‥", "…").replace("。", ".").replace("、", ",")
    text = re.sub(r"…+", "…", text)
    text = re.sub(r"…\s*[.。]", "…", text)
    return text


def typeset(text: str) -> list[list[str]]:
    """자유 문안 → 페이지(줄 목록). \\f 는 강제 페이지."""
    text = normalize(text)
    pages = []
    for chunk in text.split("\f"):
        chunk = chunk.strip()
        if not chunk:
            continue
        pages += krwrap.wrap_pages(chunk, width=WIDTH, lines_per_page=LINES, strip_after="")
    for pg in pages:
        if len(pg) > LINES:
            raise SystemExit(f"페이지가 {LINES}줄을 넘는다: {pg}")
        for ln in pg:
            if krwrap.text_width(ln) > WIDTH:
                raise SystemExit(f"줄이 {WIDTH}칸을 넘는다: {ln!r}")
    return pages


def build_stream(st: scene.Stream, ours: str, cs: hangul.Charset) -> list[scene.Token]:
    """정본 한 항목 → 새 토큰 목록. 참조 토큰은 원본 토큰을 그대로(오프셋은 재조립이 다시 잰다)."""
    refs = [t for t in st.tokens if t.ref]
    end = next((t for t in st.tokens if t.kind == "end"), None)
    out: list[scene.Token] = []
    pending_text: list[str] = []

    def flush_text():
        if not pending_text:
            return
        pages = typeset("".join(pending_text))
        pending_text.clear()
        for pi, pg in enumerate(pages):
            if pi:
                out.append(scene.Token(0, b"\x05", "ctl", 0x05))
            for li, ln in enumerate(pg):
                if li:
                    out.append(scene.Token(0, b"\x01", "ctl", 0x01))
                out.append(scene.Token(0, cs.encode(ln), "text"))

    for kind, val in textmap.parse_ours(ours):
        if kind == "text":
            pending_text.append(val)
        elif kind == "page":
            pending_text.append("\f")
        else:
            code, tgt, raw = val
            if tgt is not None:
                m = next((t for t in refs if t.code == code and t.target == tgt), None)
                if m is None:
                    raise SystemExit(
                        f"정본의 참조 <{code:02x}:{tgt:04x}> 가 원본 스트림에 없다 @{st.start:#x}"
                    )
                refs.remove(m)
                flush_text()
                out.append(m)
            elif code in scene.END:
                flush_text()
                out.append(scene.Token(0, bytes([code]), "end", code))
            else:
                flush_text()
                out.append(scene.Token(0, raw, "ctl", code))
    flush_text()
    if refs:
        raise SystemExit(
            f"원본의 참조 {[hex(t.target) for t in refs]} 가 정본에 없다 @{st.start:#x}"
        )
    if end is not None and not (out and out[-1].kind == "end"):
        out.append(scene.Token(0, end.raw, "end", end.code))
    return out


def encode_tagged(s: str, cs: hangul.Charset) -> bytes:
    """`<fe0c>` 같은 raw 태그를 섞은 표 문안 → 바이트."""
    out = b""
    pos = 0
    for m in re.finditer(r"<([0-9a-fA-F]+)>", s):
        out += cs.encode(s[pos : m.start()]) + bytes.fromhex(m.group(1))
        pos = m.end()
    return out + cs.encode(s[pos:])


def build_tables(orig: bytes, names: dict, cs: hangul.Charset) -> list[tuple[str, int, bytes]]:
    """표 → (라벨, 자리, 본문). 폭 = 원본 본문 길이. 넘치는 항목은 **전부 모아** 실패로 알린다."""
    out = []
    over = []
    for name, recs in tables.records(orig).items():
        tbl = names.get(name, {})
        align = tables.align_of(name)
        for i, (pos, raw) in enumerate(recs):
            ours = normalize(tbl.get(str(i), {}).get("ours", ""))
            if not ours:
                continue
            enc = encode_tagged(ours, cs)
            if name in tables.SLOT_CAP:  # 06 종결 칸 — 이름+06 만, 나머지는 원본
                if len(enc) > tables.SLOT_CAP[name]:
                    over.append(f"{name}[{i}] {ours!r} {len(enc)}B > {tables.SLOT_CAP[name]}B")
                    continue
                out.append((f"table:{name}", pos, enc + b"\x06"))
                continue
            w = len(raw)
            if len(enc) > w:
                over.append(f"{name}[{i}] {ours!r} {len(enc)}B > {w}B")
                continue
            pad = b" " * (w - len(enc))
            body = pad + enc if align == "right" else enc + pad
            out.append((f"table:{name}", pos, body))
    if over:
        raise SystemExit(
            "표 항목이 폭을 넘는다 — textmap/names.json 을 줄인다:\n    " + "\n    ".join(over)
        )
    return out


def _load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_textmaps() -> dict:
    """정본 전부 — 대본(script/*.json) · 표(names.json) · 시스템 메시지 · 자막 · 전투(메시지·몬스터)."""
    return {
        "maps": textmap.load_all(),
        "names": _load(tables.NAMES_JSON),
        "smap": _load(sysmsg.MAP_JSON),
        "cmap": _load(captions.MAP_JSON),
        "bmap": _load(battle.MAP_JSON),
        "monsters": _load(battle.MONSTERS_JSON),
    }


def collect_chars(tm: dict) -> set[str]:
    """정본 전체가 쓰는 글자 집합(태그 제거 · 부호 정규화 뒤) — 글꼴 표 0 과 코드 배정의 분모."""
    chars: set[str] = set()
    strip = lambda t: normalize(re.sub(r"<[^>]*>", "", t))
    for m in tm["maps"].values():
        for e in m["streams"].values():
            chars.update(strip(e.get("ours", "")))
    for t in tm["names"].values():
        for e in t.values():
            chars.update(normalize(e.get("ours", "")))
    for e in tm["smap"].values():
        chars.update(strip(e.get("ours", "")))
    for e in tm["cmap"].values():
        chars.update(strip(e.get("ours", "")))
    for e in tm["bmap"].values():
        chars.update(strip(battle.expand_names(e.get("ours", ""), tm["monsters"])))
    for e in tm["monsters"].values():
        chars.update(e.get("ours", ""))
    return chars


def main(check_only: bool = False) -> None:
    orig = common.rom()
    tm = load_textmaps()
    maps, names, smap, cmap, bmap, monsters = (
        tm["maps"],
        tm["names"],
        tm["smap"],
        tm["cmap"],
        tm["bmap"],
        tm["monsters"],
    )
    chars = collect_chars(tm)
    cs = hangul.Charset(orig, chars)
    table_writes = build_tables(orig, names, cs)
    sys_writes = sysmsg.plan(
        orig, {k: dict(v, ours=normalize(v.get("ours", ""))) for k, v in smap.items()}, cs.encode
    )
    cap_writes = captions.plan(
        orig, {k: dict(v, ours=normalize(v.get("ours", ""))) for k, v in cmap.items()}, cs.encode
    )
    print(
        f"  정본 블록 {len(maps)} · 한글 {len(cs.hangul)}자 · 표 0 {len(cs.entries)}/{cs.r0['entries']}"
    )

    base = archives.ARCHIVES["script"][0]
    bl = archives.blocks(orig, base)
    new_blocks: dict[int, bytes] = {}
    for n, m in sorted(maps.items()):
        s, b, e = bl[n]
        mod = scene.parse_module(b)
        replace = {}
        for k, ent in m["streams"].items():
            if not ent.get("ours"):
                continue
            off = int(k, 16)
            st = mod.streams.get(off)
            if st is None:
                raise SystemExit(f"블록 {n}: 스트림 {k} 가 없다")
            if textmap.jp_key(st) != ent["jp"]:
                raise SystemExit(f"블록 {n} 스트림 {k}: 원문 해시가 갈렸다")
            replace[off] = build_stream(st, ent["ours"], cs)
        if not replace:
            continue
        new = scene.reassemble(mod, replace)
        scene.verify_reassembly(mod, new, replace)
        new_blocks[n] = new
    battle_blocks: dict[int, bytes] = {}
    for n, (_s, bb, _e) in enumerate(battle.blocks(orig)):
        nb = battle.plan_block(
            bb,
            n,
            {k: dict(v, ours=normalize(v.get("ours", ""))) for k, v in bmap.items()},
            monsters,
            cs.encode,
        )
        if nb is not None:
            battle_blocks[n] = nb
    if check_only:
        print(
            f"  게이트 OK — 바뀌는 블록 {len(new_blocks)} · 표 항목 {len(table_writes)} · 시스템 메시지 쓰기 {len(sys_writes)} · 자막 쓰기 {len(cap_writes)} · 전투 블록 {len(battle_blocks)}"
        )
        return

    rom = Rom(orig)
    # 1. 대본 아카이브 — 블록을 원 자리부터 차례로, 넘치면 꼬리로
    cur, region = SCRIPT_LO, "script"
    table = bytearray(orig[base : base + 225 * 4])
    for n, (s, _b, e) in enumerate(bl):
        packed = lz.encode(new_blocks[n]) if n in new_blocks else orig[s:e]
        packed = packed + (b"\x00" if len(packed) & 1 else b"")
        if region == "script" and cur + len(packed) > SCRIPT_HI:
            cur, region = TAIL_LO, "tail"
        if region == "tail" and cur + len(packed) > TAIL_HI:
            raise SystemExit("대본 아카이브가 꼬리 빈 공간도 넘는다")
        rom.write(region, cur, packed)
        table[n * 4 : n * 4 + 4] = struct.pack(">I", cur - base)
        cur += len(packed)
    rom.write("script-table", base, bytes(table))
    # 1b. 전투 아카이브 — 같은 규칙, 꼬리는 대본과 이어 쓴다
    bbase = battle.ARCHIVE
    bbl = battle.blocks(orig)
    btable = bytearray(orig[bbase : bbase + battle.COUNT * 4])
    bcur, bregion = BATTLE_LO, "battle"
    for n, (s, _b, e) in enumerate(bbl):
        packed = lz.encode(battle_blocks[n]) if n in battle_blocks else orig[s:e]
        packed = packed + (b"\x00" if len(packed) & 1 else b"")
        if bregion == "battle" and bcur + len(packed) > BATTLE_HI:
            bcur, bregion = (cur if region == "tail" else TAIL_LO), "tail"
        if bregion == "tail" and bcur + len(packed) > TAIL_HI:
            raise SystemExit("전투 아카이브가 꼬리 빈 공간도 넘는다")
        rom.write(bregion, bcur, packed)
        btable[n * 4 : n * 4 + 4] = struct.pack(">I", bcur - bbase)
        bcur += len(packed)
    if bregion == "tail":
        cur, region = bcur, "tail"
    rom.write("battle-table", bbase, bytes(btable))
    # 2. 글꼴 리소스 0
    hdr, tbl, gl = cs.resource0()
    rom.write("font0-header", cs.r0["hdr"], hdr)
    rom.write("font0-table", cs.r0["table"], tbl)
    rom.write("font0-glyphs", cs.r0["desc"], orig[cs.r0["desc"] : cs.r0["desc"] + 4] + gl)
    for label, pos, body in hangul.resource1(cs):  # 반각 쉼표 — 표 0 이 비운 자리에
        rom.write(label, pos, body)
    for label, pos, body in hangul.resource2_labels():  # HUD 「ｱﾄ」 → 「다음」 (8×8)
        rom.write(label, pos, body)
    hud_chars = set()
    for grp in ("party_rec", "party_name"):
        for e in names.get(grp, {}).values():
            hud_chars.update(re.sub(r"<[^>]*>", "", e.get("ours", "")))
    for label, pos, body in hangul.resource4(cs, hud_chars):  # HUD 이름 12×12
        rom.write(label, pos, body)
    # 3. 고정 폭 표(아이템·주문·지명·메뉴 라벨) — 제자리
    for label, pos, body in table_writes:
        rom.write(label, pos, body)
    # 3a. 그래픽 문자(타이틀 메뉴 셀)
    for label, pos, body in gfxtext.plan(orig, names):
        rom.write(label, pos, body)
    # 3b. 시스템 메시지 묶음 + 참조 명령
    for label, pos, body in sys_writes:
        rom.write(label, pos, body)
    # 3c. 오프닝 자막 · 엔딩 문안 영역 + 표
    for label, pos, body in cap_writes:
        rom.write(label, pos, body)
    # 4. 체크섬 · 대조 · 출력
    rom.write("checksum", 0x18E, struct.pack(">H", common.header_checksum(rom.buf)))
    rom.verify_immutable()
    out_dir = common.BUILD_DIR / common.BUILD_TAG.replace("/", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "ed1-kr.bin"
    out.write_bytes(bytes(rom.buf))
    used = cur - SCRIPT_LO if region == "script" else (SCRIPT_HI - SCRIPT_LO) + (cur - TAIL_LO)
    print(
        f"  {out} — 바뀐 블록 {len(new_blocks)} · 아카이브 {used:,}B ({region}) · 쓰기 {len(rom.log)}건"
    )


if __name__ == "__main__":
    try:
        main("--check" in sys.argv)
    except SystemExit as e:
        out_dir = common.BUILD_DIR / common.BUILD_TAG.replace("/", "_")
        p = out_dir / "ed1-kr.bin"
        if p.exists():
            p.rename(p.with_suffix(".bin.failed"))
        raise SystemExit(f"❌ 빌드 실패: {e}") from e
