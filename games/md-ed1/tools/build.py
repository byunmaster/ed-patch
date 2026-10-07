"""md-ed1 빌드 — 정본(script/*.json)만 읽어 work/build/<꼬리표>/ed1-kr.bin 을 만든다. 결정적이다.

    python3 tools/build.py            # 빌드 + 게이트
    python3 tools/build.py --check    # 빌드 없이 게이트만(정본 검증)

안전장치(docs/patcher-checklist.md):
- 입력 지문(common.rom) · 쓰기는 `_write(label, lo, hi)` 한 통로 — **허용 구간 밖은 즉시 거부**
  (대본 아카이브 자리 · 꼬리 빈 공간 · 글꼴 리소스 0 · 헤더 체크섬).
- 끝에 원본과 byte 대조: 허용 구간 밖은 한 바이트도 안 바뀌어야 한다.
- 화면에 나가는 바이트 게이트: 미수록 글자(인코딩 불가) · 대사창 210px(17.5칸) 초과 줄 · 3줄 초과 페이지 ·
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
import field_hud
import field_names
import gfxtext
import halfspace
import hangul
import josa
import lz
import scene
import sysmsg
import tables
import textmap
import wordwrap
from text import krwrap

# 대사창 한 줄 = 210px(전각 17.5칸) — 원판이 **저절로 넘긴다**: 전각 17자(204px) 뒤 18째 글자를 다음 줄로
# 보냈다(화자 없는 꼴·이름창 꼴 둘 다, 09-27 `r5-typeset-dialog-wrap-jp*.png`). 옛 값 18칸(216px)은 안쪽 폭으로 잰 추정이었다
WIDTH = 17.5
LINES = 3

SCRIPT_LO, SCRIPT_HI = 0x135324, 0x1918D2  # 대본 블록 자리(색인 0x134FA0 은 항목만 고친다)
TAIL_LO, TAIL_HI = common.FREE_TAIL
CAPTION_RESERVE = (
    0x1000  # 자막(오프닝·엔딩 나레이션·엔딩 대사)을 꼬리로 옮길 자리 — 제자리 칸이 만원이라서
)
# 꼬리 **끝**에 조사 훅(기계어+표)을 예약한다 — 아카이브는 그 앞까지만 쓴다.
# ⚠ 표는 **한글 코드 수를 따라 자란다**(종성 비트표 = 코드 하나에 1비트). 0x180 으로 재 두었더니
# 글자 33 자를 새로 굳히자마자 2바이트가 넘쳤다(2026-09-07). 그래서 **글리프 상한**(1,370자)까지
# 재 둔다 — 172B(한글 비트표) + 16B(반각) + 252B(기계어) + 쌍 표 ≈ 460B.
JOSA_RESERVE = 0x280
# 조사 훅 앞에 어절 줄넘김 본체(tools/wordwrap.py, 326B)를 둔다 — 넘칠 때 글자가 아니라 어절을
# 다음 줄로 보낸다(마스터 2026-09-30 번복, 전 기종 — 09-27 밤의 글자 단위 "최종 판정"을 다시 뒤집었다)
WRAP_RESERVE = 0x180
# 어절 줄넘김 앞에 필드 HUD 뒷말·방위 앞 공백 트램펄린(tools/field_hud.py, 18B)을 둔다(2026-09-27 밤)
FIELD_HUD_RESERVE = 0x20


BATTLE_LO, BATTLE_HI = 0x0CAB04, 0x0D85B4  # 전투 아카이브 LZ 구간(첫 블록 시작 ~ 끝 블록 끝)


class Rom:
    """쓰기 통로 하나 — 허용 구간(라벨) 밖은 거부."""

    ALLOWED: ClassVar[dict[str, tuple[int, int]]] = {
        "script-table": (0x134FA0, 0x134FA0 + 225 * 4),
        "battle-table": (battle.ARCHIVE, battle.ARCHIVE + battle.COUNT * 4),
        "battle": (BATTLE_LO, BATTLE_HI),
        "script": (SCRIPT_LO, SCRIPT_HI),
        "tail": (TAIL_LO, TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE - CAPTION_RESERVE),
        "josa-code": (TAIL_HI - JOSA_RESERVE, TAIL_HI),
        "josa-tramp": (josa.DEAD_HANDLER, josa.DEAD_HANDLER + 12),
        "wrap-code": (TAIL_HI - JOSA_RESERVE - WRAP_RESERVE, TAIL_HI - JOSA_RESERVE),
        "wrap-tramp": (wordwrap.TRAMP, wordwrap.TRAMP + 6),
        "half-code": (
            TAIL_HI - JOSA_RESERVE - WRAP_RESERVE + halfspace.CODE_OFF,
            TAIL_HI - JOSA_RESERVE - WRAP_RESERVE + halfspace.CODE_OFF + halfspace.CODE_LEN,
        ),
        "half-tramp": (halfspace.TRAMP, halfspace.TRAMP + 6),
        "half-site": (halfspace.SITE, halfspace.SITE + 4),
        **{f"wrap-site:{s:x}": (s, s + 4) for s in wordwrap.SITES},
        "field-hud-space-tramp": (
            TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE,
            TAIL_HI - JOSA_RESERVE - WRAP_RESERVE,
        ),
        "field-hud-space-site": (field_hud.SPACE_SITE, field_hud.SPACE_SITE + 6),
        "field-hud-align": (field_hud.ALIGN_SITE, field_hud.ALIGN_SITE + 4),
        **{f"field-hud-dir:{i}": (a, a + 2) for i, (a, _c, _w) in enumerate(field_hud.DIRECTIONS)},
        **{f"field-hud-suffix:{i}": (a, a + 4) for i, (a, _c, _w) in enumerate(field_hud.SUFFIX)},
        **{
            f"josa-tbl:{i:02x}": (josa.HANDLER_TBL + i * 2, josa.HANDLER_TBL + i * 2 + 2)
            for i in (josa.IDX_ACTOR, josa.IDX_ITEM)
        },
        **{
            f"josa-arg:{i:02x}": (josa.ARGLEN_TBL + i, josa.ARGLEN_TBL + i + 1)
            for i in (josa.IDX_ACTOR, josa.IDX_ITEM)
        },
        "font0-header": (0x1A54D2, 0x1A54DE),
        "font0-table": (0x1A551A, 0x1A6080),
        "font0-glyphs": (0x1A62CE, 0x1BA1FA),
        "font1-header": hangul.FONT1_HDR,
        "font5-header": hangul.FONT5_HDR,
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
        self.log: list[tuple[str, int, bytes]] = []
        self.allowed = captions.widen_for_tail(
            dict(
                self.ALLOWED,
                **sysmsg.allowed(data),
                **gfxtext.allowed(),
                **captions.allowed(data),
                **captions.allowed_tail(
                    TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE - CAPTION_RESERVE, CAPTION_RESERVE
                ),
            ),
            TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE - CAPTION_RESERVE,
            CAPTION_RESERVE,
        )

    def write(self, label: str, at: int, data: bytes) -> None:
        lo, hi = self.allowed[label]
        if not (lo <= at and at + len(data) <= hi):
            raise SystemExit(
                f"[{label}] 허용 구간 밖 쓰기 {at:#x}+{len(data)} (구간 {lo:#x}~{hi:#x})"
            )
        self.buf[at : at + len(data)] = data
        self.log.append((label, at, bytes(data)))

    def verify_no_overlap(self) -> None:
        """🔴 **앞 단계가 쓴 바이트가 최종 이미지에 살아남았나.**

        ⚠ 묻는 말이 「겹치나」가 아니라 **「살아남았나」**다(pce-ed1 이 다듬어 준 축, 2026-09-07) —
        겹침만 보면 **내 겹침 판정에 구멍이 있으면 같이 샌다.** 최종 버퍼와 대조하면 어떤 경로로
        덮였든 잡힌다. 덮인 것을 찾으면 **누가 덮었는지**까지 기록에서 되짚어 말해 준다.

        ss-ed1+2 가 2026-09-07 에 물린 자리다: 뒤 단계가 이주 자리를 **원본 덤프의 칸 경계**로
        골랐는데 앞 단계가 그 표를 통째로 다시 깔아 놓아, **살아 있는 한글 이름 위에 대사를 얹었다.**
        게이트 셋이 다 초록이었다 — 되읽기는 *자기가 쓴 직후*를, 라운드트립은 *덤프↔원본*을,
        무변경 구간은 *안 여는 자리*를 본다. **아무도 「두 단계가 같은 바이트를 썼나」를 안 본다.**

        주인 목록을 손으로 들지 않는다 — `write()` 가 남긴 기록만 보면 구조로 잡힌다.
        """
        for i, (label, at, data) in enumerate(self.log):
            if self.buf[at : at + len(data)] == data:
                continue
            culprit = next(
                (
                    f"[{lb}] {a:#x}+{len(dd)}"
                    for lb, a, dd in self.log[i + 1 :]
                    if a < at + len(data) and at < a + len(dd)
                ),
                "(뒤에 겹쳐 쓴 기록이 없다 — write() 를 안 거친 쓰기다)",
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
            n = w - len(enc)
            if align == "right":
                body = b" " * n + enc
            elif align == "center":
                # 🔴 `center` 를 안 다뤄 장 제목·지명이 **왼쪽에 붙어** 있었다(2026-09-06).
                # 원본이 앞뒤로 공백을 나눠 넣은 자리다 — 남는 칸은 뒤에 준다(반각 6px 단위).
                body = b" " * (n // 2) + enc + b" " * (n - n // 2)
            else:
                body = enc + b" " * n
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
    chars.update(field_hud.chars())  # 필드 HUD 뒷말·방위(문안을 안 거친다) — 늘 굽는다
    chars.update(halfspace.chars())  # 「의␣」 — 아이템 칸 14B 에 반각 공백을 녹인 합성 글자
    chars.update(field_names.chars())  # 대본 블록 91 지명 표(문안 스트림 밖) — 늘 굽는다
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
        orig,
        {k: dict(v, ours=normalize(v.get("ours", ""))) for k, v in cmap.items()},
        cs.encode,
        tail_at=TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE - CAPTION_RESERVE,
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
            replace[off] = build_stream(st, ent["ours"], cs, raw_text=bool(ent.get("raw")))
        if not replace:
            continue
        new = scene.reassemble(mod, replace)
        scene.verify_reassembly(mod, new, replace)
        new_blocks[n] = new
    # 대본 블록 91 — 문안 스트림 밖의 지명 표(입장 배너). scene.py 로는 안 보여 별도 경로로 얹는다.
    fn_base = new_blocks.get(field_names.BLOCK, bl[field_names.BLOCK][1])
    new_blocks[field_names.BLOCK] = field_names.new_block(fn_base, cs)
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
        if (
            region == "tail"
            and cur + len(packed) > TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE - CAPTION_RESERVE
        ):
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
        if (
            bregion == "tail"
            and bcur + len(packed) > TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE - CAPTION_RESERVE
        ):
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
    cap5 = {c for c in captions.font5_chars(cmap) if c.strip()}
    if captions.FONT_ID and cap5:  # <fd85> 를 단 자막 전용 글꼴(리소스 5, Galmuri14 14×14)
        for label, pos, body in hangul.resource5(
            cs, cap5, hangul.layout_after_r1(cs), cell=captions.FONT_CELL, source=captions.FONT_SRC
        ):
            rom.write(label, pos, body)
    for label, pos, body in hangul.resource2_labels():  # HUD 「ｱﾄ」 → 「남다」 (8×8, 마스터 도안)
        rom.write(label, pos, body)
    hud_chars = set()
    for grp in ("party_rec", "party_name"):
        for e in names.get(grp, {}).values():
            hud_chars.update(re.sub(r"<[^>]*>", "", e.get("ours", "")))
    for label, pos, body in hangul.resource4(cs, hud_chars):  # HUD 이름 12×12
        rom.write(label, pos, body)
    # 2c. 조사 훅 — 이름 뒤 조사를 런타임에 고른다(제어코드 EB·EC)
    for label, pos, body in josa.plan(orig, cs, TAIL_HI - JOSA_RESERVE):
        rom.write(label, pos, body)
    # 2d. 어절 줄넘김 — 렌더러($978C)가 넘칠 때 글자가 아니라 어절을 다음 줄로 보낸다(마스터 2026-09-30)
    for label, pos, body in wordwrap.plan(orig, TAIL_HI - JOSA_RESERVE - WRAP_RESERVE):
        rom.write(label, pos, body)
    for label, pos, body in halfspace.plan(cs, TAIL_HI - JOSA_RESERVE - WRAP_RESERVE):
        rom.write(label, pos, body)
    # ⚠ 합성 글리프(field_hud·field_names 의 PUA 콘덴스드 슬라이스)는 뺀다 — 일부러 큰 왼쪽
    # 여백을 구워 둔 자리라(공백을 그림 안에 녹였다) 정상 글자처럼 재면 문턱이 깨진다. 이
    # 글리프들은 로그 렌더러($978C)를 안 타는 고정폭 HUD 전용이라 애초에 안 재도 된다.
    normal_wide = {v for k, v in cs.hangul.items() if k not in hangul.CUSTOM_GLYPHS}
    gap, sp = wordwrap.gap_gate(bytes(rom.buf), normal_wide)
    print(f"  어절 줄넘김 — 글자 틈 최대 {gap}px < 문턱 {wordwrap.SPACE_PX}px ≤ 공백 틈 최소 {sp}px")
    # 2e. 필드 HUD 뒷말(부근·입구)·방위(동서남북) — 문안을 안 거치고 코드가 SJIS 를 직접 찍는 여덟 자리
    field_hud_tramp_at = TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE
    for label, pos, body in field_hud.plan(cs, field_hud_tramp_at):
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
    rom.verify_no_overlap()
    rom.verify_immutable()
    out_dir = common.BUILD_DIR / common.BUILD_TAG.replace("/", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    # 🔴 지난 실패 표식을 지운다 — `pull-build.sh` 는 `.failed` 가 하나라도 있으면 **그 칸을 통째로**
    # 거부한다(유저 맥에서 실측 2026-09-06: 성공 이미지 옆에 아침의 .failed 가 남아 못 받았다).
    for stale in out_dir.glob("*.failed"):
        stale.unlink()
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
