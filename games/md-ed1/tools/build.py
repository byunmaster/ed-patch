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

import struct
import sys
from pathlib import Path
from typing import ClassVar

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(common_root := Path(__file__).resolve().parents[3] / "shared"))
import archives
import common
import hangul
import lz
import scene
import textmap
from text import krwrap

WIDTH = 18  # 대사창 한 줄(12px 피치, 안쪽 218px)
LINES = 3

SCRIPT_LO, SCRIPT_HI = 0x135324, 0x1918D2  # 대본 블록 자리(색인 0x134FA0 은 항목만 고친다)
TAIL_LO, TAIL_HI = common.FREE_TAIL


class Rom:
    """쓰기 통로 하나 — 허용 구간(라벨) 밖은 거부."""

    ALLOWED: ClassVar[dict[str, tuple[int, int]]] = {
        "script-table": (0x134FA0, 0x134FA0 + 225 * 4),
        "script": (SCRIPT_LO, SCRIPT_HI),
        "tail": (TAIL_LO, TAIL_HI),
        "font0-header": (0x1A54D2, 0x1A54DE),
        "font0-table": (0x1A551A, 0x1A6080),
        "font0-glyphs": (0x1A62CE, 0x1BA1FA),
        "checksum": (0x18E, 0x190),
    }

    def __init__(self, data: bytes):
        self.orig = data
        self.buf = bytearray(data)
        self.log: list[tuple[str, int, int]] = []

    def write(self, label: str, at: int, data: bytes) -> None:
        lo, hi = self.ALLOWED[label]
        if not (lo <= at and at + len(data) <= hi):
            raise SystemExit(
                f"[{label}] 허용 구간 밖 쓰기 {at:#x}+{len(data)} (구간 {lo:#x}~{hi:#x})"
            )
        self.buf[at : at + len(data)] = data
        self.log.append((label, at, len(data)))

    def verify_immutable(self) -> None:
        marks = bytearray(len(self.buf))
        for lo, hi in self.ALLOWED.values():
            marks[lo:hi] = b"\x01" * (hi - lo)
        for i, (a, b) in enumerate(zip(self.orig, self.buf, strict=True)):
            if a != b and not marks[i]:
                raise SystemExit(f"무변경 구간이 바뀌었다 @{i:#x}")


def typeset(text: str) -> list[list[str]]:
    """자유 문안 → 페이지(줄 목록). \\f 는 강제 페이지."""
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


def main(check_only: bool = False) -> None:
    orig = common.rom()
    maps = textmap.load_all()
    syll = set()
    for m in maps.values():
        for e in m["streams"].values():
            for ch in e.get("ours", ""):
                if hangul.is_hangul(ch):
                    syll.add(ch)
    cs = hangul.Charset(orig, syll)
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
    if check_only:
        print(f"  게이트 OK — 바뀌는 블록 {len(new_blocks)}")
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
    # 2. 글꼴 리소스 0
    hdr, tbl, gl = cs.resource0()
    rom.write("font0-header", cs.r0["hdr"], hdr)
    rom.write("font0-table", cs.r0["table"], tbl)
    rom.write("font0-glyphs", cs.r0["desc"], orig[cs.r0["desc"] : cs.r0["desc"] + 4] + gl)
    # 3. 체크섬 · 대조 · 출력
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
