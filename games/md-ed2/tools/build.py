"""md-ed2 빌드 — 뼈대(2026-10-12). 번역 정본이 아직 없어 **문안은 원본 그대로**, 구조만 선다.

    python3 tools/build.py          # → work/build/<꼬리표>/ed2-kr.bin
    python3 tools/build.py --check  # 빌드 없이 게이트만(원본 지문 · 재배치 왕복 · 무변경 대조)

ED1 build.py 와 같은 규율을 옮겼다(루트 CLAUDE.md 「빌드 규율」):
- 쓰기는 `Rom.write(label, at, data)` 한 통로, **라벨의 허용 구간 밖은 거부**한다.
- 쓴 바이트가 최종 이미지에 살아남았는지(`verify_no_overlap`), 허용 구간 밖이 원본과 같은지(`verify_immutable`).
- 실패하면 산출물을 `.failed` 로 이름 바꾼다.
- 결정적이다 — 같은 입력이면 같은 바이트(인코더는 순수 DP, 해시 순서에 기대지 않는다).

대본 아카이브(0x19DF08~0x1FF71E)는 **다시 눌러 처음부터 깐다**: 색인 90 + 블록들(2B 정렬, 0 패딩).
블록은 씬 모듈 넷의 연속이고 크기는 `archives.SCENE_SIZES` 표에 있으므로, 모듈을 바꾸면 그 표(블록당
8B)도 같이 쓴다. 아카이브는 롬 맨 끝이라 뒤로 밀려 날 참조가 없고, 줄면 남는 자리는 FF 로 채운다.
"""

import re
import struct
import sys
from pathlib import Path
from typing import ClassVar

import archives
import common
import hangul
import lz
import scene
import textmap

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from text import krwrap

ARCHIVE_BASE = archives.ARCHIVES["script"][0]
ARCHIVE_END = common.FREE_TAIL[1]  # 이 앞까지 아카이브가 쓸 수 있다(마지막 2B 는 건드리지 않는다)
N_BLOCKS = archives.ARCHIVES["script"][1]


class Rom:
    """쓰기 통로 하나 — 허용 구간(라벨) 밖은 거부."""

    ALLOWED: ClassVar[dict[str, tuple[int, int]]] = {
        "script-archive": (ARCHIVE_BASE, ARCHIVE_END),
        "scene-sizes": (archives.SCENE_SIZES, archives.SCENE_SIZES + 8 * archives.SCENE_BLOCKS),
        "checksum": (0x18E, 0x190),
        # 글꼴 리소스 0(대사) · 1(반각) — ED1 구간을 같은 이동량(hangul.SHIFT)으로 옮긴 것(글꼴 구역이 바이트 동일)
        "font0-header": (0x1A54D2 + hangul.SHIFT, 0x1A54DE + hangul.SHIFT),
        "font0-table": (0x1A551A + hangul.SHIFT, 0x1A6080 + hangul.SHIFT),
        "font0-glyphs": (0x1A62CE + hangul.SHIFT, 0x1BA1FA + hangul.SHIFT),
        "font1-header": hangul.FONT1_HDR,
    }

    def __init__(self, data: bytes):
        self.orig = data
        self.buf = bytearray(data)
        self.log: list[tuple[str, int, bytes]] = []
        self.allowed = dict(self.ALLOWED)

    def write(self, label: str, at: int, data: bytes) -> None:
        lo, hi = self.allowed[label]
        if not (lo <= at and at + len(data) <= hi):
            raise SystemExit(
                f"[{label}] 허용 구간 밖 쓰기 {at:#x}+{len(data)} (구간 {lo:#x}~{hi:#x})"
            )
        self.buf[at : at + len(data)] = data
        self.log.append((label, at, bytes(data)))

    def verify_no_overlap(self) -> None:
        """🔴 앞 단계가 쓴 바이트가 최종 이미지에 **살아남았나**(겹침 판정이 아니라 결과 대조)."""
        for i, (label, at, data) in enumerate(self.log):
            if self.buf[at : at + len(data)] == data:
                continue
            culprit = next(
                (
                    f"[{lb}] {a:#x}+{len(dd)}"
                    for lb, a, dd in self.log[i + 1 :]
                    if a < at + len(data) and at < a + len(dd)
                ),
                "(write() 를 안 거친 쓰기다)",
            )
            raise SystemExit(
                f"[{label}] {at:#x}+{len(data)} 가 최종 이미지에 안 남았다 — {culprit} 이 덮었다"
            )

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


def typeset(text: str, lead: str = "") -> list[list[str]]:
    """자유 문안 → 페이지(줄 목록). `\\f` 는 강제 페이지.

    `lead` 는 **첫 줄 앞에 그대로 붙는** 글자다(조판기가 지우면 안 되는 자리). 조사 훅 뒤의
    공백이 그것이다 — `<0e><ec01> 들어 있었습니다.` 에서 앞 공백이 없으면 화면이
    「눈물이들어 있었습니다」가 된다. krwrap 도 typeset 도 앞 공백을 지우므로 따로 받는다
    (2026-09-07 초벌 시험에서 잡았다). ⚠ 폭 검사는 **붙인 뒤**에 한다.
    """
    text = normalize(text)
    pages = []
    for chunk in text.split("\f"):
        chunk = chunk.strip()
        if not chunk:
            continue
        pages += krwrap.wrap_pages(chunk, width=WIDTH, lines_per_page=LINES, strip_after="")
    if lead and pages and pages[0]:
        pages[0][0] = lead + pages[0][0]
    for pg in pages:
        if len(pg) > LINES:
            raise SystemExit(f"페이지가 {LINES}줄을 넘는다: {pg}")
        for ln in pg:
            if krwrap.text_width(ln) > WIDTH:
                raise SystemExit(f"줄이 {WIDTH}칸을 넘는다: {ln!r}")
    return pages


def build_stream(
    st: scene.Stream, ours: str, cs: hangul.Charset, *, raw_text: bool = False
) -> list[scene.Token]:
    """정본 한 항목 → 새 토큰 목록. 참조 토큰은 원본 토큰을 그대로(오프셋은 재조립이 다시 잰다).

    `raw_text` 면 조판기를 안 태운다 — 여백까지 우리가 정한 자리(장 카드·HUD 제목)를 위해서다.
    조판기는 줄을 strip 하고 다시 감기 때문에 「30바이트 고정」 같은 계약을 조용히 깬다.
    """
    refs = [t for t in st.tokens if t.ref]
    end = next((t for t in st.tokens if t.kind == "end"), None)
    out: list[scene.Token] = []
    pending_text: list[str] = []

    def flush_text():
        if not pending_text:
            return
        if raw_text:
            body = "".join(pending_text)
            pending_text.clear()
            for pi, pg in enumerate(body.split("\f")):
                if pi:
                    out.append(scene.Token(0, b"\x05", "ctl", 0x05))
                for li, ln in enumerate(pg.split("\n")):
                    if li:
                        out.append(scene.Token(0, b"\x01", "ctl", 0x01))
                    if ln:
                        out.append(scene.Token(0, cs.encode(ln), "text"))
            return
        body = "".join(pending_text)
        lead = " " if body[:1] == " " else ""
        pages = typeset(body, lead)
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
            # 🔴 예전엔 `\f` 를 본문에 이어 붙여 조판기에 맡겼는데, **뒤에 제어코드가 오면**
            # 조판기가 빈 쪽으로 보고 버려 `<05>` 가 통째로 사라졌다(2026-09-07 실측: 퍼거슨 대화에서
            # 왕자의 말과 퍼거슨의 대답이 한 창에 붙었다). 쪽 넘김은 **여기서** 토큰으로 낸다.
            flush_text()
            out.append(scene.Token(0, b"\x05", "ctl", 0x05))
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


def collect_chars(maps: dict) -> set[str]:
    """정본 전체가 쓰는 글자 집합(태그 제거 · 부호 정규화 뒤) — 글꼴 표 0 과 코드 배정의 분모."""
    chars: set[str] = set()
    strip = lambda t: normalize(re.sub(r"<[^>]*>", "", t))
    for m in maps.values():
        for e in m["streams"].values():
            chars.update(strip(e.get("ours", "")))
    chars.update(
        set("는은가이를을와과으로")
    )  # 조사 훅이 그릴 글자(이식 전이지만 코드를 미리 굳힌다)
    return (
        chars
        if any(len(strip(e.get("ours", ""))) for m in maps.values() for e in m["streams"].values())
        else set()
    )


def pack_archive(blocks: list[bytes]) -> bytes:
    """색인(BE32 × n, 첫 값 4n) + LZ 블록들(2B 정렬, 0 패딩). 원본 꼴과 같다."""
    n = len(blocks)
    packed = []
    for b in blocks:
        p = lz.encode(b)
        packed.append(p + b"\x00" * (len(p) & 1))
    offs, cur = [], 4 * n
    for p in packed:
        offs.append(cur)
        cur += len(p)
    return struct.pack(f">{n}I", *offs) + b"".join(packed)


def script_blocks(
    orig: bytes, replace: dict[tuple[int, int], bytes] | None = None
) -> tuple[list[bytes], list[tuple[int, ...]]]:
    """대본 블록 90개(디코드)와 블록별 모듈 크기 표. `replace[(블록, 순번)]` 로 모듈을 바꾼다."""
    replace = replace or {}
    bl = [b for _, b, _ in archives.blocks(orig, ARCHIVE_BASE)]
    sizes = [list(archives.scene_sizes(orig, i)) for i in range(archives.SCENE_BLOCKS)]
    for (blk, k), new in replace.items():
        mods, o = [], 0
        for s in sizes[blk]:
            mods.append(bl[blk][o : o + s])
            o += s
        mods[k] = new
        sizes[blk][k] = len(new)
        bl[blk] = b"".join(mods)
    return bl, [tuple(s) for s in sizes]


WIDTH = 17.5
LINES = 3

# 블록 디코드 크기 상한 — 원본 최대(블록 23)가 **램에서 돌았다**는 사실만이 근거다. 로더가 블록 통째를 FF6650 에
# 푼다(0x1A432) — 그보다 큰 블록이 램의 뒤 칸을 덮는지는 아직 분석 전이라 넘기지 않는다.
MAX_BLOCK = 23_124

# 아카이브·분할표를 직접 가리키는 코드(lea/jsr/move.l #abs) — 이 넷뿐이어야 아카이브를 다시 깔아도 안전하다
KNOWN_ARCHIVE_REFS = {0x1A426, 0x1A470, 0x1A490, 0x24BEC}
_ABS_OPS = {0x4EB9, 0x4EF9, 0x4879, 0x23FC, 0x21FC, 0x2D7C, *range(0x41F9, 0x4DFA, 0x200)}


def verify_archive_refs(d: bytes) -> None:
    """🔴 대본 아카이브(분할표 포함) 안 주소를 직접 쓰는 코드가 알려진 넷뿐인가 — 블록 위치가 바뀌어도
    색인만 고치면 되는지의 근거다. 새 참조가 생기면(다른 소비자) 재배치가 조용히 깨진다."""
    lo, hi = archives.SCENE_SIZES, common.FREE_TAIL[0]
    got = set()
    for p in range(2, lo - 3, 2):
        op = struct.unpack(">H", d[p - 2 : p])[0]
        v = struct.unpack(">I", d[p : p + 4])[0]
        if op in _ABS_OPS and lo <= v < hi:
            got.add(p - 2)
    if got != KNOWN_ARCHIVE_REFS:
        raise SystemExit(f"아카이브를 가리키는 코드가 알려진 것과 다르다: {sorted(map(hex, got))}")


def main(check_only: bool = False) -> None:
    orig = common.rom()
    verify_archive_refs(orig)
    maps = textmap.load_all()
    chars = collect_chars(maps)
    cs = hangul.Charset(orig, chars) if chars else None
    replace: dict[tuple[int, int], bytes] = {}
    for (blk, k), m in sorted(maps.items()):
        mb = textmap.module_bytes(orig, blk, k)
        mod = scene.parse_module(mb)
        rep = {}
        for key, ent in m["streams"].items():
            if not ent.get("ours"):
                continue
            off = int(key, 16)
            st = mod.streams.get(off)
            if st is None:
                raise SystemExit(f"블록 {blk}-{k}: 스트림 {key} 가 없다")
            if textmap.jp_key(st) != ent["jp"]:
                raise SystemExit(f"블록 {blk}-{k} 스트림 {key}: 원문 해시가 갈렸다")
            rep[off] = build_stream(st, ent["ours"], cs, raw_text=bool(ent.get("raw")))
        if not rep:
            continue
        new = scene.reassemble(mod, rep)
        scene.verify_reassembly(mod, new, rep)
        replace[(blk, k)] = new
    blocks, sizes = script_blocks(orig, replace)
    for i, b in enumerate(blocks[: archives.SCENE_BLOCKS]):
        if len(b) > MAX_BLOCK:
            raise SystemExit(
                f"블록 {i}: 디코드 {len(b):,}B 가 원본 최대 {MAX_BLOCK:,}B 를 넘는다(램 버퍼 근거 없음)"
            )
    for i, s in enumerate(sizes):
        if sum(s) != len(blocks[i]) and i < archives.SCENE_BLOCKS:
            raise SystemExit(f"블록 {i}: 모듈 크기 합 {sum(s)} ≠ 블록 길이 {len(blocks[i])}")
        if max(s) > scene.MODULE_MAX:
            raise SystemExit(f"블록 {i}: 모듈 {max(s)}B 가 한도 {scene.MODULE_MAX}B 를 넘는다")
    arch = pack_archive(blocks)
    room = ARCHIVE_END - ARCHIVE_BASE
    if len(arch) > room:
        raise SystemExit(f"대본 아카이브가 {len(arch) - room:,}B 넘친다 ({len(arch):,} > {room:,})")
    # 왕복: 다시 깐 아카이브를 푼 결과가 입력과 같아야 한다
    rt = [b for _, b, _ in archives.blocks(arch.ljust(room, b"\xff"), 0)]
    if rt != blocks:
        raise SystemExit("재배치 왕복이 입력과 다르다")
    print(
        f"  대본 아카이브 {len(arch):,}B / 칸 {room:,}B (여유 {room - len(arch):,}B) · 왕복 OK · "
        f"정본 모듈 {len(maps)} · 바뀐 모듈 {len(replace)}"
    )
    if check_only:
        return

    rom = Rom(orig)
    if cs is not None:  # 글꼴 리소스 0(대사) + 반각(리소스 1)
        hdr, tbl, gl = cs.resource0()
        rom.write("font0-header", cs.r0["hdr"], hdr)
        rom.write("font0-table", cs.r0["table"], tbl)
        rom.write("font0-glyphs", cs.r0["desc"], orig[cs.r0["desc"] : cs.r0["desc"] + 4] + gl)
        for label, pos, body in hangul.resource1(cs):
            rom.write(label, pos, body)
    rom.write("script-archive", ARCHIVE_BASE, arch.ljust(room, b"\xff"))
    rom.write(
        "scene-sizes",
        archives.SCENE_SIZES,
        b"".join(struct.pack(">4H", *s) for s in sizes[: archives.SCENE_BLOCKS]),
    )
    rom.write("checksum", 0x18E, struct.pack(">H", common.header_checksum(rom.buf)))
    rom.verify_no_overlap()
    rom.verify_immutable()
    out_dir = common.BUILD_DIR / common.BUILD_TAG.replace("/", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    # 🔴 지난 실패 표식을 지운다 — pull-build.sh 는 .failed 가 하나라도 있으면 그 칸을 통째로 거부한다
    for stale in out_dir.glob("*.failed"):
        stale.unlink()
    out = out_dir / "ed2-kr.bin"
    out.write_bytes(bytes(rom.buf))
    print(f"  {out} — 쓰기 {len(rom.log)}건 · sha1 {common.sha1_of_bytes(bytes(rom.buf))[:8]}…")


if __name__ == "__main__":
    try:
        main("--check" in sys.argv)
    except SystemExit as e:
        out_dir = common.BUILD_DIR / common.BUILD_TAG.replace("/", "_")
        p = out_dir / "ed2-kr.bin"
        if p.exists():
            p.rename(p.with_suffix(".bin.failed"))
        raise SystemExit(f"❌ 빌드 실패: {e}") from e
