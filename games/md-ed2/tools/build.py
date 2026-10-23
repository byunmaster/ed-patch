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

import json
import os
import re
import struct
import sys
from pathlib import Path
from typing import ClassVar

import archives
import banners
import battle
import captions
import chapters
import common
import ctl_toggle_scan
import debug_build
import dict_names
import field_hud
import gfxtext
import halfspace
import hangul
import hud_status
import josa
import kana_gate
import lz
import places
import punctwrap
import repack
import scene
import spell_digit
import sysmsg
import tables
import textmap
import wordwrap

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from text import krwrap

ARCHIVE_BASE = archives.ARCHIVES["script"][0]
TAIL_HI = common.FREE_TAIL[1]
# 꼬리 **끝**에 훅 코드를 예약한다(ED1 build.py 와 같은 배치) — 아카이브는 그 앞까지만 쓴다. ED2 는 꼬리 빈 공간이 2KB 뿐이지만
# 아카이브를 다시 눌러 16KB 를 비우므로 훅이 들어간다.
JOSA_RESERVE = 0x400  # 조사 훅 기계어+표(글리프 표가 한글 코드 수에 비례 — 대사 번역으로 코드 900자 넘김) — 으로/로·과/와 포함
WRAP_RESERVE = 0x260  # 어절 줄넘김 본체 540B(이름 속 틈 검사 포함) + 반각 「의␣」·「′」 되감기 50B
FIELD_HUD_RESERVE = 0x20  # 필드 HUD 트램펄린(이식 전 — 자리만 잡아 둔다)
CAPTION_RESERVE = 0xA00  # 오프닝·엔딩 자막 표+문안(captions.RELOCATE)이 앉는 꼬리 칸
SYSMSG_TAIL = sysmsg.TAIL_SIZE  # 시스템 메시지 중 꼬리로 옮기는 스트림(RELOCATE)의 칸
# 🔴 씬 크기 표(블록당 BE16×4, 712B)를 **꼬리로 옮긴다** — 원래 자리(0x19DC3C)는 전투 아카이브 바로 뒤라, 전투 문안이 늘면 그 712B 가
# 전투 아카이브의 유일한 여유다. 표를 가리키는 코드는 `lea $19DC3C.l,a1` 하나뿐(0x1A490, `verify_archive_refs` 가 지킨다)이라 피연산자만 고치면 된다.
SCENE_TABLE_SIZE = 8 * archives.SCENE_BLOCKS
BATTLE_TAIL_RESERVE = 0x1000  # 전투 블록이 원래 자리에 안 들어갈 때 앉는 꼬리 칸
SCENE_REF = 0x1A492  # 0x1A490 `lea.l $19dc3c.l,a1` 의 32비트 피연산자 자리
ARCHIVE_END = (
    TAIL_HI
    - JOSA_RESERVE
    - WRAP_RESERVE
    - FIELD_HUD_RESERVE
    - SYSMSG_TAIL
    - CAPTION_RESERVE
    - SCENE_TABLE_SIZE
    - BATTLE_TAIL_RESERVE
)  # 이 앞까지 아카이브가 쓴다
SCENE_TABLE_AT = ARCHIVE_END
# 전투 아카이브 — 색인(0x18BF76, 99×4)은 제자리지만 **블록은 색인 상대 오프셋이라 어디든 앉는다**. 원래 자리(끝 0x19D96E 뒤는 다른 표라 못 쓴다 —
# 첫 시도에서 그 718B 를 「여유」로 보고 덮어 새 게임이 까만 화면에서 멈췄다)에 먼저 채우고 넘치는 블록은 꼬리 예약 칸에 앉힌다.
BATTLE_PRIMARY_END = 0x19D96E
BATTLE_TAIL_AT = SCENE_TABLE_AT + SCENE_TABLE_SIZE
SYSMSG_TAIL_AT = BATTLE_TAIL_AT + BATTLE_TAIL_RESERVE
CAPTION_AT = SYSMSG_TAIL_AT + SYSMSG_TAIL
N_BLOCKS = archives.ARCHIVES["script"][1]


class Rom:
    """쓰기 통로 하나 — 허용 구간(라벨) 밖은 거부."""

    ALLOWED: ClassVar[dict[str, tuple[int, int]]] = {
        "script-archive": (ARCHIVE_BASE, ARCHIVE_END),
        "scene-sizes": (SCENE_TABLE_AT, SCENE_TABLE_AT + SCENE_TABLE_SIZE),
        "scene-ref": (SCENE_REF, SCENE_REF + 4),
        "checksum": (0x18E, 0x190),
        "battle-archive": (battle.ARCHIVE, BATTLE_PRIMARY_END),
        "battle-tail": (BATTLE_TAIL_AT, BATTLE_TAIL_AT + BATTLE_TAIL_RESERVE),
        # 글꼴 리소스 0(대사) · 1(반각) — ED1 구간을 같은 이동량(hangul.SHIFT)으로 옮긴 것(글꼴 구역이 바이트 동일)
        "font0-header": (0x1A54D2 + hangul.SHIFT, 0x1A54DE + hangul.SHIFT),
        "font0-table": (0x1A551A + hangul.SHIFT, 0x1A6080 + hangul.SHIFT),
        "font0-glyphs": (0x1A62CE + hangul.SHIFT, 0x1BA1FA + hangul.SHIFT),
        "font1-header": hangul.FONT1_HDR,
        "spell-digit": (spell_digit.AT, spell_digit.AT + len(spell_digit.NEW)),
        "hud-status": (hud_status.BASE, hud_status.BASE + hud_status.N * hud_status.STRIDE),
        "font2-glyphs": hangul.FONT2_GLYPHS,
        "font4-header": hangul.FONT4_HDR,
        "font4-table": hangul.FONT4_TABLE,
        "font4-glyphs": hangul.FONT4_GLYPHS,
        **{f"table:{t[0]}": (t[1], t[1] + (t[2] + 1) * t[4]) for t in tables.TABLES},
        **{f"table:{g[0]}": (g[1], g[1] + 0x200) for g in tables.ZGROUPS},
        **{f"table:{t[0]}": (t[1], t[1] + t[2] * t[3]) for t in tables.SLOTS},
        **gfxtext.allowed(),
        **places.allowed(),
        **debug_build.allowed(),
        "field-hud-space-tramp": (
            TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE,
            TAIL_HI - JOSA_RESERVE - WRAP_RESERVE,
        ),
        "field-hud-space-site": (field_hud.SPACE_SITE, field_hud.SPACE_SITE + 6),
        "field-hud-align": (field_hud.ALIGN_SITE, field_hud.ALIGN_SITE + 4),
        **{f"field-hud-dir:{i}": (a, a + 2) for i, (a, _c, _w) in enumerate(field_hud.DIRECTIONS)},
        **{f"field-hud-suffix:{i}": (a, a + 4) for i, (a, _c, _w) in enumerate(field_hud.SUFFIX)},
        "josa-code": (TAIL_HI - JOSA_RESERVE, TAIL_HI),
        **sysmsg.allowed(common.rom()),
        **sysmsg.allowed_tail(SYSMSG_TAIL_AT),
        **captions.allowed(common.rom(), CAPTION_AT, CAPTION_RESERVE),
        "font5-header": hangul.FONT5_HDR,
        "josa-tramp": (josa.DEAD_HANDLER, josa.DEAD_HANDLER + 12),
        "josa-name-hook": (josa.NAME_FN_PATCH, josa.NAME_FN_PATCH + 6),
        "josa-mon-hook": (josa.MON_HEAD_PATCH, josa.MON_HEAD_PATCH + 6),
        "josa-head2-hook": (josa.HEAD2_PATCH, josa.HEAD2_PATCH + 10),
        "wrap-code": (TAIL_HI - JOSA_RESERVE - WRAP_RESERVE, TAIL_HI - JOSA_RESERVE),
        "wrap-tramp": (wordwrap.TRAMP, wordwrap.TRAMP + 6),
        "half-code": (
            TAIL_HI - JOSA_RESERVE - WRAP_RESERVE + halfspace.CODE_OFF,
            TAIL_HI - JOSA_RESERVE - WRAP_RESERVE + halfspace.CODE_OFF + halfspace.CODE_LEN,
        ),
        "half-tramp": (halfspace.TRAMP, halfspace.TRAMP + 6),
        "half-site": (halfspace.SITE, halfspace.SITE + 4),
        "punct-code": (TAIL_HI - punctwrap.CODE_LEN, TAIL_HI),
        "punct-site": (punctwrap.SITE, punctwrap.SITE + 6),
        **{f"hang:{at:x}": (at, at + len(new) // 2) for at, _o, new, _w in punctwrap.HANG_PATCHES},
        **{f"wrap-site:{x:x}": (x, x + 4) for x in wordwrap.SITES},
        **{
            f"josa-tbl:{i:02x}": (josa.HANDLER_TBL + i * 2, josa.HANDLER_TBL + i * 2 + 2)
            for i in (josa.IDX_ACTOR, josa.IDX_ITEM)
        },
        **{
            f"josa-arg:{i:02x}": (josa.ARGLEN_TBL + i, josa.ARGLEN_TBL + i + 1)
            for i in (josa.IDX_ACTOR, josa.IDX_ITEM)
        },
    }

    def __init__(self, data: bytes):
        self.orig = data
        self.buf = bytearray(data)
        self.log: list[tuple[str, int, bytes]] = []
        self.allowed = dict(self.ALLOWED)

    def allow(self, label: str, lo: int, hi: int) -> None:
        self.allowed[label] = (lo, hi)

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
    """부호 규칙(유저 확정 2026-09-05): 온점·쉼표·공백은 반각, 「…」은 전각(연속은 그대로 — 규칙 1-3: 원문 점 n개 → 「…」 round(n/3)개, 옛 「하나로 줄이기」는 걷었다 10-18), 「…」 뒤에 온점 없음."""
    text = text.replace("...", "…").replace("‥", "…").replace("。", ".").replace("、", ",")
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
        # 앞 공백(lead)이 첫 줄에 붙으므로 **그 쪽 줄 폭을 공백만큼 줄여** 감싼다 — 붙인 뒤 17.5칸을 넘던 일(「<이름> 왕자 뒤를…」)
        w = WIDTH - krwrap.text_width(lead) if lead and not pages else WIDTH
        pages += krwrap.wrap_pages(chunk, width=w, lines_per_page=LINES, strip_after="")
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
    # 상점 표 머리(`<포인터 워드들+4E71>` 원판 바이트 그대로) — 파서가 워드의 앞 바이트(`10`·`0F`·`F2`…)를 호출·분기로 읽은 참조는 **자료**다. 머리 구간의 참조는
    # 정본에 안 적어도 되고(원본 토큰으로 되살리면 재조립이 변위를 다시 재 워드가 망가진다 — 064-1·069-3), 머리는 바이트 그대로 나간다.
    hm = re.match(r"<((?:[0-9a-f]{2}){3,})>", ours)
    head_toks: list[scene.Token] = []
    if hm and bytes.fromhex(hm.group(1)).endswith(b"\x4e\x71"):
        head_end = st.start + len(hm.group(1)) // 2
        refs = [t for t in refs if t.off >= head_end]
        # 머리 토큰은 원본 파서가 가른 그대로, 단 참조 표시는 뗀다(재조립이 변위를 다시 재지 못하게) — 구운 바이트를 다시 파싱한 토큰열과 맞는다
        for t in st.tokens:
            if t.off >= head_end:
                break
            raw = t.raw[: head_end - t.off]
            head_toks.append(scene.Token(t.off, raw, t.kind, t.code))
        ours = ours[hm.end() :]
    end = next((t for t in st.tokens if t.kind == "end"), None)
    cont = ours.endswith(
        "<~>"
    )  # 이어 읽기 — 끝 표식 없이 바로 뒤 글줄(꼬리를 같이 쓰는 스트림)로 이어진다. 재조립이 남는 칸을 공백으로 채운다
    if cont:
        ours = ours[:-3]
        end = None
        refs = []
    out: list[scene.Token] = list(head_toks)
    pending_text: list[str] = []

    def flush_text(trail: bool = True):
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
        if (
            body and not body.strip()
        ):  # 변수 사이 공백 하나(`<eb00> <0e>`) — 조판기가 빈 덩이로 지운다(10-19)
            pending_text.clear()
            out.append(scene.Token(0, cs.encode(body.replace("\n", " ")), "text"))
            return
        # 🔴 덩이 가장자리의 `\n` 은 조판기가 **조용히 버린다**(10-19 qa: 「배를 타시겠습니까?」 뒤 줄바꿈이 사라져 다음 글이 붙었다) —
        # 제어코드·덩이 끝 앞뒤 줄바꿈은 `<01>` 태그로 쓴다. (덩이 가운데 `\n` 은 공백이다.)
        edge = body.strip(" ")
        if edge[:1] == "\n" or edge[-1:] == "\n":
            raise SystemExit(
                f"덩이 가장자리 `\\n` 은 조판기가 버린다 @{st.start:#x} — `<01>` 태그를 쓴다: {body[:30]!r}"
            )
        lead = " " if body[:1] == " " else ""
        pages = typeset(body, lead)
        # 🔴 조판기는 덩이의 앞뒤 공백을 지운다 — 태그(이름 호출 등) **앞** 공백이 사라져 「이런아트라스님」이 됐다
        # (2026-10-12 화면). 뒤 공백은 덩이 뒤에 태그가 이어질 때만 되살린다.
        if trail and body[-1:] == " " and pages:
            pages[-1][-1] += " "
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
                if m is None and code == 0x0F:
                    # 꼬리를 같이 쓰는 스트림 — 마지막 쪽을 따로 둔 스트림으로 **새로 잇는다**(고정 스트림이 안에 낀 스트림을 못 옮길 때)
                    m = scene.Token(0, b"\x0f\x00\x00", "ctl", 0x0F, scene.GOTO, tgt)
                    flush_text()
                    out.append(m)
                    continue
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
    flush_text(False)
    if refs:
        raise SystemExit(
            f"원본의 참조 {[hex(t.target) for t in refs]} 가 정본에 없다 @{st.start:#x}"
        )
    if end is not None and not (out and (out[-1].kind == "end" or out[-1].ref == scene.GOTO)):
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
            "표 항목이 폭을 넘는다 — 칸 배치(textmap/ui_layout.json)나 정본 값을 줄인다:\n    "
            + "\n    ".join(over)
        )
    return out


def load_sysmsg(orig: bytes) -> dict:
    """코드 영역 문안 정본 — `textmap/sysmsg.json` + 장 카드(정본 장 제목에서 만든다, `chapters.plan`)."""
    smap = (
        json.loads(sysmsg.MAP_JSON.read_text(encoding="utf-8")) if sysmsg.MAP_JSON.exists() else {}
    )
    for k, ours in chapters.plan(sysmsg.streams(orig)).items():
        smap.setdefault(
            k, {"jp": sysmsg.jp_key(sysmsg.streams(orig)[int(k, 16)]["stream"]), "ours": ""}
        )
        smap[k]["ours"] = ours
    return smap


def load_captions() -> dict:
    return (
        json.loads(captions.MAP_JSON.read_text(encoding="utf-8"))
        if captions.MAP_JSON.exists()
        else {}
    )


def all_chars(orig: bytes) -> set[str]:
    """정본 전부(대본 · 표 · 코드 영역 문안 · 전투)가 쓰는 글자 — `--freeze` 와 빌드가 같은 분모를 쓴다."""
    bmap = (
        json.loads(battle.MAP_JSON.read_text(encoding="utf-8")) if battle.MAP_JSON.exists() else {}
    )
    return collect_chars(
        textmap.load_all(),
        dict_names.names(orig),
        load_sysmsg(orig),
        bmap,
        battle.monsters(orig),
        load_captions(),
    )


def verify_jump_readback(buf: bytes, orig: bytes, smap: dict, encode) -> None:
    """🔴 되읽기 게이트 — 제자리엔 goto 만 두고 본문을 다른 칸에 앉힌 스트림(`sysmsg.TAIL_JUMP`)을, **구운 이미지에서** 참조를 따라
    goto 를 펴 읽은 글이 정본 문안과 같은지 본다. 묶음 재배치·변위 수정이 조용히 어긋나도 여기서 걸린다(마스터 10-12)."""
    strs = sysmsg.streams(orig)
    for t in sorted(sysmsg.TAIL_JUMP):
        ent = smap.get(f"{t:06x}", {})
        if not ent.get("ours"):
            continue
        e = strs[t]
        toks = sysmsg._tokens_from_ours(e["stream"], normalize(ent["ours"]), encode)
        want = b"".join(k.raw for k in toks if k.ref is None)
        if not e["refs"]:  # 참조 없이 앞 스트림에서 흘러 닿는 꼬리 — 자기 참조로는 못 따라간다
            continue
        kind, ins = e["refs"][0]
        if kind == "pc":
            at = ins + 2 + struct.unpack(">h", buf[ins + 2 : ins + 4])[0]
        elif kind == "abs":
            at = struct.unpack(">I", buf[ins + 2 : ins + 6])[0]
        elif kind.startswith("tbl:"):  # 워드 표 — 표 시작 + 워드 = 스트림 시작(`kind` 의 16진이 표 시작)
            at = int(kind[4:], 16) + struct.unpack(">H", buf[ins : ins + 2])[0]
        else:
            raise SystemExit(f"되읽기: {t:#x} 의 참조 종류 {kind} 를 못 따라간다")
        got = bytearray()
        for _hop in range(8):  # goto 사슬(최대 8)
            st = scene.parse_stream(bytes(buf), at)
            nxt = None
            for k in st.tokens:
                if k.ref == scene.GOTO:
                    nxt = k.target
                    break
                if k.kind != "eof":
                    got += k.raw
            if nxt is None:
                break
            at = nxt
        if bytes(got) != want:
            raise SystemExit(
                f"되읽기 불일치 {t:#x}: 구운 이미지의 글이 정본과 다르다\n  구움 {bytes(got).hex()}\n  정본 {want.hex()}"
            )
        print(f"  되읽기 OK {t:#x} — goto 를 펴 읽은 {len(got)}B 가 정본과 같다")


def collect_chars(
    maps: dict,
    names: dict | None = None,
    smap: dict | None = None,
    bmap: dict | None = None,
    monsters: dict | None = None,
    cmap: dict | None = None,
) -> set[str]:
    """정본 전체가 쓰는 글자 집합(태그 제거 · 부호 정규화 뒤) — 글꼴 표 0 과 코드 배정의 분모."""
    chars: set[str] = set()

    def strip(t: str) -> str:
        return normalize(re.sub(r"<[^>]*>", "", t))

    for m in maps.values():
        for e in m["streams"].values():
            chars.update(strip(e.get("ours", "")))
    for t in (names or {}).values():
        for e in t.values():
            chars.update(strip(e.get("ours", "")))
    for e in (smap or {}).values():
        chars.update(strip(e.get("ours", "")))
    for e in (bmap or {}).values():
        chars.update(strip(battle.expand_names(e.get("ours", ""), monsters or {})))
    for e in (monsters or {}).values():
        chars.update(e.get("ours", ""))
    for e in (cmap or {}).values():  # 오프닝·엔딩 자막(리소스 5 도 같은 글자 코드를 쓴다)
        chars.update(strip(e.get("ours", "")))
    chars.update(josa.chars())  # 조사 훅이 그리는 글자(는은가이를을와과으로) — 늘 굽는다
    chars.update(
        banners.chars()
    )  # 입장 배너 지명 사전(모듈 데이터라 문안 스트림이 아니다) — 늘 굽는다
    chars.update(field_hud.chars())  # 필드 HUD 뒷말·방위(문안을 안 거친다) — 늘 굽는다
    chars.update(halfspace.chars())  # 「의␣」 — 아이템 칸 14B 에 반각 공백을 녹인 합성 글자
    return chars


def pack_battle(blocks: list[bytes]) -> tuple[bytes, bytes, bytes]:
    """전투 아카이브 → (색인, 원래 자리 블록들, 꼬리 블록들). 앞에서부터 원래 자리에 채우고 넘치면 나머지를 꼬리로.
    색인 값은 **색인 시작 기준 오프셋**이라 꼬리 블록도 그대로 가리킨다(32비트)."""
    n = len(blocks)
    room = BATTLE_PRIMARY_END - battle.ARCHIVE - 4 * n
    offs, primary, tail = [], bytearray(), bytearray()
    for b in blocks:
        p = lz.encode(b)
        p += b"\x00" * (len(p) & 1)
        if not tail and len(primary) + len(p) <= room:
            offs.append(4 * n + len(primary))
            primary += p
        else:
            offs.append(BATTLE_TAIL_AT + len(tail) - battle.ARCHIVE)
            tail += p
    if len(tail) > BATTLE_TAIL_RESERVE:
        raise SystemExit(f"전투 꼬리 예약 {len(tail):,}B 가 {BATTLE_TAIL_RESERVE:,}B 를 넘는다")
    return struct.pack(f">{n}I", *offs), bytes(primary), bytes(tail)


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


def pack_script(
    blocks: list[bytes], free: list[tuple[int, int]]
) -> tuple[bytes, bytes, list[tuple[int, bytes]]]:
    """대본 블록 → (색인, 본 칸 블록들, [(자리, 압축 블록)]). 큰 블록부터 **다른 아카이브가 비운 칸**(`repack`)에 앉히고(색인은 부호 있는
    32비트 상대 오프셋이라 앞쪽 자리도 된다) 나머지는 본 칸에 차례로 둔다."""
    n = len(blocks)
    packed = []
    for b in blocks:
        p = lz.encode(b)
        packed.append(p + b"\x00" * (len(p) & 1))
    iv = [[lo, hi] for lo, hi in free]
    place: dict[int, int] = {}
    for i in sorted(range(n), key=lambda i: -len(packed[i])):
        c = [x for x in iv if x[1] - x[0] >= len(packed[i])]
        if not c:
            continue
        x = min(c, key=lambda x: x[1] - x[0])
        place[i] = x[0]
        x[0] += len(packed[i])
    main = bytearray()
    offs = []
    cur = 4 * n
    for i in range(n):
        if i in place:
            offs.append(place[i] - ARCHIVE_BASE)
        else:
            offs.append(cur)
            main += packed[i]
            cur += len(packed[i])
    index = struct.pack(f">{n}i", *offs)
    return index, bytes(main), [(place[i], packed[i]) for i in sorted(place)]


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


# 씬 모듈의 「무기 번호로 では/ので 4B 를 글 한복판에 덮는」 루틴(보스 82 와 같은 문장) — 한글은 4B 덮기가 안 되니(받침·무기 이름이 가변) 정본 두 문안으로 가르고
# 루틴을 「무기 번호로 둘 중 하나의 주소를 골라 문구를 찍는 `lea` 의 변위 워드에 쓴다」로 바꾼다(자기 수정 — 원본도 같은 방식으로 문안을 고쳤다).
# 정본(ed2.json 607·608): 무기 「하지만 {이름}은(는) 통하지\n않는다!!」 · 맨손 「하지만 맨손으로는 피해를 줄 수 없다!!」.
WEAPON_BRANCH = {
    (23, 1): {
        "routine": 0x11C8,  # 원본 루틴 48B(`48E7 0060` … `4E75`)
        "print_lea": 0x11B2,  # `lea $138A(pc),a1` — 문구를 찍는 곳
        "eq": 0x138A,  # 장비 문안(=이 스트림의 번역)
        "bare": "하지만 맨손으로는 피해를 줄 수 없다!!<0a>",
    }
}
WEAPON_ROUTINE_HEAD = bytes.fromhex("48e7006040e745fa")  # 원본 루틴 머리(검산)


def apply_weapon_branch(blk, k, new, mod, cs):
    cfg = WEAPON_BRANCH.get((blk, k))
    if cfg is None:
        return new
    rt, pl = cfg["routine"], cfg["print_lea"]
    out = bytearray(new)
    if bytes(out[rt : rt + 8]) != WEAPON_ROUTINE_HEAD or bytes(out[pl : pl + 2]) != b"\x43\xfa":
        raise SystemExit(f"{blk}-{k}: 무기 분기 루틴/출력 lea 가 원본과 다르다")
    st = mod.streams[cfg["eq"]]
    eq = scene.pair_streams(mod, new)[1][cfg["eq"]]
    body = b"".join(t.raw for t in build_stream(st, cfg["bare"], cs))
    # 맨손 문구는 **죽은 글 칸**(옮겨진·줄어든 스트림의 옛 자리 — 원판 스트림 칸 안이고 지금 0)에 앉힌다 — 모듈 끝에 덧붙이면 디코드 블록이 원본 최대를 넘는다
    covered = bytearray(len(out))
    for s_, st_ in mod.streams.items():
        covered[s_ : st_.end] = b"\x01" * (st_.end - s_)
    # 지금 **쓰이는** 스트림(끝 표지 `00` 까지)은 빈 칸이 아니다 — 스트림 끝의 0 바이트를 죽은 칸으로 오인해 맨손 문구가 씬 끝 `00` 을 덮었다(씬023-1:1614, 10-20)
    live, _pair = scene.pair_streams(mod, new)
    for s_, st_ in live.streams.items():
        covered[s_ : st_.end] = b"\x00" * (st_.end - s_)
    need = len(body) + 2  # 뒤에 0 한 칸(끝 표지 뒤 여백)
    bare = -1
    for a in range(len(out) - need):
        if a & 1 == 0 and all(covered[x] and out[x] == 0 for x in range(a, a + need)):
            bare = a
            break
    if bare < 0:
        if len(out) & 1:
            out.append(0)
        bare = len(out)
        out += body
        if len(out) & 1:
            out.append(0)
    else:
        out[bare : bare + len(body)] = body

    def disp(at: int, target: int) -> bytes:  # lea d16(pc),aN — 확장 워드는 at+2
        return struct.pack(">h", target - (at + 2))

    code = bytearray()
    code += bytes.fromhex("48e78060")  # movem.l d0/a1-a2,-(a7)
    code += bytes.fromhex("43fa") + disp(rt + 4, eq)  # lea eq(pc),a1
    code += bytes.fromhex("4a00")  # tst.b d0   (무기 번호)
    code += bytes.fromhex("6604")  # bne.s +4   (장비 있음 → eq)
    code += bytes.fromhex("43fa") + disp(rt + 12, bare)  # lea bare(pc),a1
    code += bytes.fromhex("45fa") + disp(rt + 16, pl + 2)  # lea <출력 lea 의 변위 워드>(pc),a2
    code += bytes.fromhex("2009")  # move.l a1,d0
    code += bytes.fromhex("908a")  # sub.l a2,d0
    code += bytes.fromhex("3480")  # move.w d0,(a2)   — 출력 lea 의 변위로
    code += bytes.fromhex("4cdf0601")  # movem.l (a7)+,d0/a1-a2
    code += bytes.fromhex("4e75")  # rts
    code += b"\x4e\x71" * ((48 - len(code)) // 2)  # nop 로 원본 칸(48B)을 채운다
    assert len(code) == 48, len(code)
    out[rt : rt + 48] = code
    out[pl + 2 : pl + 4] = disp(pl, eq)  # 기본값 = 장비 문구
    return bytes(out)


def head_table_streams(m: dict) -> frozenset[int]:
    """정본 항목 가운데 상점 표 머리(`<포인터 워드들+4E71>` 로 시작)인 스트림 시작들."""
    out = set()
    for key, ent in m["streams"].items():
        mm = re.match(r"<((?:[0-9a-f]{2}){3,})>", ent.get("ours") or "")
        if mm and mm.group(1).endswith("4e71"):
            out.add(int(key, 16))
    return frozenset(out)


def fix_head_words(new: bytes, mod, rep) -> tuple[bytes, int]:
    """상점 표 머리의 포인터 워드를 새 자리로 다시 쓴다 → (바이트, 고친 워드 수).

    워드 0 은 원판에서 `표 시작 + 머리 길이` — 표 바로 뒤 첫 문안(= 안쪽 스트림 I 와 같은 글)이다. 번역으로 I 가 옮겨져도 표의 **자기 복사본**(머리 + 같은 글)이 있으니 그리로 돌린다.
    다른 워드는 가리키던 문안(가장 안쪽 스트림)의 새 자리 + 안쪽 오프셋으로 돌린다(제자리면 그대로)."""
    _k, pair = scene.pair_streams(mod, new)
    om = mod.data
    out = bytearray(new)
    n = 0
    for o, st in mod.streams.items():
        if o not in rep or o not in pair:
            continue
        j = next(
            (x for x in range(o + 2, min(o + 12, st.end), 2) if om[x : x + 2] == b"\x4e\x71"), None
        )
        if j is None or j - o < 4:
            continue
        hl = j + 2 - o
        nw = pair[o]
        for i in range(0, hl - 2, 2):
            w = struct.unpack(">H", om[o + i : o + i + 2])[0]
            if w == o + hl:
                tgt = nw + hl
            else:
                owner = max(
                    (x for x, sx in mod.streams.items() if x <= w < sx.end and x != o), default=None
                )
                if owner is None or owner not in pair:
                    continue
                tgt = pair[owner] + (w - owner)
            if struct.unpack(">H", out[nw + i : nw + i + 2])[0] != tgt:
                out[nw + i : nw + i + 2] = struct.pack(">H", tgt)
                n += 1
    return bytes(out), n


def verify_head_tables(new: bytes, mod, rep) -> int:
    """🔴 상점 표 머리(원판 `[포인터 워드 ×N] 4E71 …`)가 구운 모듈에서 맞는지 본다 → 검사한 표 수.

    표의 워드는 **같은 모듈 안 문안의 자리**다. 번역으로 문안이 옮겨지거나 머리가 글자로 오인돼 바이트가 바뀌면(2026-10-20: 064-1·069-3 은 `10 xx` 가 호출로 읽혀 변위가 다시 재졌고,
    073-1 은 머리 뒤에 「お」 가 남고, 074-2 는 워드 하나·`4E71` 이 빠졌다) 메뉴가 엉뚱한 곳을 읽는다. ① 머리 끝의 `4E71`(머리 워드 자리)이 그대로 ② 워드 0 = 표 자기 복사본 ③ 나머지 워드는
    제자리 그대로(바이트 같음)이거나 가리키던 문안의 새 자리."""
    _k, pair = scene.pair_streams(mod, new)
    om = mod.data
    n = 0
    for o, st in mod.streams.items():
        if o not in rep or o not in pair:
            continue
        j = next(
            (x for x in range(o + 2, min(o + 12, st.end), 2) if om[x : x + 2] == b"\x4e\x71"), None
        )
        if j is None or j - o < 4:
            continue
        hl = j + 2 - o
        nw = pair[o]
        if bytes(new[nw + hl - 2 : nw + hl]) != b"\x4e\x71":
            raise ValueError(
                f"상점 표 머리 @{o:#x} 의 머리 워드 자리(4E71)가 원판과 다르다({bytes(new[nw + hl - 2 : nw + hl]).hex()})"
            )
        for i in range(0, hl - 2, 2):
            w = struct.unpack(">H", om[o + i : o + i + 2])[0]
            nv = struct.unpack(">H", new[nw + i : nw + i + 2])[0]
            if w == o + hl:
                if nv != nw + hl:
                    raise ValueError(
                        f"상점 표 머리 @{o:#x} 워드 0 이 표 자기 복사본({nw + hl:#x})이 아니다({nv:#x})"
                    )
                continue
            if nv == w and bytes(new[w : w + 4]) == bytes(om[w : w + 4]):
                continue  # 제자리 그대로
            owner = max(
                (x for x, sx in mod.streams.items() if x <= w < sx.end and x != o), default=None
            )
            # 워드가 스트림 **한 바이트 앞**(아이템 코드 `0E` 가 파서에선 스트림 밖 — 「{item}…」 문구)을 가리킨다 — 그 바이트가 제자리고 뒤 스트림이 제자리(또는 제자리 goto 스텁)면 된다
            if (
                owner is None
                and (w + 1) in mod.streams
                and (w + 1) in pair
                and nv == w
                and new[w] == om[w]
                and (pair[w + 1] == w + 1 or new[w + 1] == 0x0F)
            ):
                continue
            if owner is None or owner not in pair or pair[owner] + (w - owner) != nv:
                raise ValueError(
                    f"상점 표 머리 @{o:#x} 의 워드 {w:#x}→{nv:#x} 가 가리키는 문안과 어긋난다"
                )
        n += 1
    return n


def repoint_shared_heads(new: bytes, mod, rep_keys) -> tuple[bytes, int]:
    """🔴 머리 워드를 런타임에 쓰는 `lea`(원판 `4E71` 자리 — 상점 표 「…더는 못 가지실 것 같군요」 류)를 **바깥 복사본**으로 돌린다.

    원판은 안쪽 스트림 I(`4E71` 로 시작)가 바깥 스트림 O(앞 포인터 워드 표 + I) 의 **꼬리**라 한 번 쓰면 둘 다 고쳐졌다. 번역으로 O 가 옮겨지면 복사본이 둘이라
    코드는 I 의 복사본만 고치고, 표를 읽는 서비스는 O 의 복사본(머리 워드 자리 `4E71` 그대로 = NOP 워드)을 읽는다(2026-10-20 unicorn 으로 확인).
    I 의 `lea` 변위를 O 새 자리 + (I−O) 로 바꾼다 — 두 복사본의 그 자리 바이트가 같을 때만."""
    _kmod, pair = scene.pair_streams(mod, new)
    out = bytearray(new)
    n = 0
    for ins, s in mod.roots.items():
        if s not in rep_keys:
            continue
        outer = next((o for o, st in mod.streams.items() if o < s < st.end), None)
        if outer is None or outer not in pair or s not in pair:
            continue
        cand = pair[outer] + (s - outer)
        cur = pair[s]
        ln = min(mod.streams[s].end - s, 8)
        if cand == cur or bytes(out[cand : cand + ln]) != bytes(out[cur : cur + ln]):
            continue
        if bytes(out[cand : cand + 2]) != b"\x4e\x71":
            continue
        out[ins + 2 : ins + 4] = struct.pack(">h", cand - (ins + 2))
        n += 1
    return bytes(out), n


def main(check_only: bool = False) -> None:
    debug_build.check_tag()  # 꼬리표와 디버그 스위치가 어긋나면 일을 시작하기 전에 거부한다
    orig = common.rom()
    verify_archive_refs(orig)
    maps = textmap.load_all()
    names = dict_names.names(orig)
    smap = load_sysmsg(orig)
    bmap = (
        json.loads(battle.MAP_JSON.read_text(encoding="utf-8")) if battle.MAP_JSON.exists() else {}
    )
    monsters = battle.monsters(orig)
    cmap = load_captions()
    chars = collect_chars(maps, names, smap, bmap, monsters, cmap)
    cs = hangul.Charset(orig, chars)
    table_writes = build_tables(orig, names, cs)
    sys_writes = sysmsg.plan(
        orig,
        {k: dict(v, ours=normalize(v.get("ours", ""))) for k, v in smap.items()},
        cs.encode,
        tail_at=SYSMSG_TAIL_AT,
    )
    cap_writes = captions.plan(
        orig,
        {k: dict(v, ours=normalize(v.get("ours", ""))) for k, v in cmap.items()},
        cs.encode,
        CAPTION_AT,
        CAPTION_RESERVE,
    )
    replace: dict[tuple[int, int], bytes] = {}
    reasm_errors: list[str] = []
    n_evt = 0
    n_repoint = 0
    n_heads = 0
    n_headwords = 0
    for (blk, k), m in sorted(maps.items()):
        mb = banners.patch(
            (blk, k), textmap.module_bytes(orig, blk, k), lambda s: encode_tagged(s, cs)
        )
        mod = scene.parse_module(mb)
        rep = {}
        for key, ent in m["streams"].items():
            if not ent.get("ours"):
                continue
            off = int(key, 16)
            if any(
                o <= off < o + banners.STRIDE * n for o, n in banners.BY_MODULE.get((blk, k), ())
            ):
                continue  # 지명 배너 표 칸 — banners.patch 가 굽는다(스트림 번역이 덮으면 안 된다)
            st = mod.streams.get(off)
            if st is None:
                raise SystemExit(f"블록 {blk}-{k}: 스트림 {key} 가 없다")
            if textmap.jp_key(st) != ent["jp"]:
                raise SystemExit(f"블록 {blk}-{k} 스트림 {key}: 원문 해시가 갈렸다")
            rep[off] = build_stream(st, ent["ours"], cs, raw_text=bool(ent.get("raw")))
        if not rep:
            if mb != textmap.module_bytes(orig, blk, k):  # 배너 표만 바뀐 모듈 — 같은 길이
                replace[(blk, k)] = mb
            continue
        try:
            new = scene.reassemble(mod, rep)
            scene.verify_reassembly(mod, new, rep, head_table_streams(m))
            scene.verify_cond_tails(
                mod, new, rep
            )  # 조건 분기 뒤 물리적 꼬리가 원판과 같은지(10-19 md-ed1 발견)
            n_evt += scene.verify_event_tables(
                mod.data, new, rep
            )  # 이벤트 표가 바이트까지 같은지(10-20 md-ed1 발견)
            new = ctl_toggle_scan.neutralize(
                blk, k, new
            )  # 코드가 글 한복판 4B 를 덮는 자리를 자료 위로(10-20)
            new, n_rp = repoint_shared_heads(new, mod, set(rep))
            n_repoint += n_rp
            new, n_hw = fix_head_words(new, mod, rep)
            n_headwords += n_hw
            n_heads += verify_head_tables(new, mod, rep)
            new = apply_weapon_branch(
                blk, k, new, mod, cs
            )  # 023-1 「…무기 では/ので」 — 정본 두 문안 + 무기 번호 분기
        except (ValueError, KeyError) as e:
            reasm_errors.append(f"블록 {blk}-{k}: {type(e).__name__} {e}")
            continue
        replace[(blk, k)] = new
    if reasm_errors:
        raise SystemExit("\n".join(reasm_errors))
    print(f"  이벤트 표 {n_evt}개(재조립 모듈 안) — 원판과 바이트까지 같다")
    print(f"  머리 워드 쓰기 lea {n_repoint}곳을 바깥 복사본으로 돌렸다")
    print(
        f"  상점 표 머리 {n_heads}개 — 머리 워드 자리(4E71)·포인터 워드 {n_headwords}개를 새 자리로 고쳐 의도와 같다"
    )
    for key in banners.BY_MODULE:  # 번역 정본이 없는 모듈의 배너 표
        if key not in maps and key not in replace:
            replace[key] = banners.patch(
                key, textmap.module_bytes(orig, *key), lambda s: encode_tagged(s, cs)
            )
    nban = sum(
        banners.verify(
            key, replace[key], textmap.module_bytes(orig, *key), lambda s: encode_tagged(s, cs)
        )
        for key in banners.BY_MODULE
    )
    print(f"  배너 표 {len(banners.BY_MODULE)}모듈 {nban}항목 — 최종 모듈 바이트가 의도와 같다")
    blocks, sizes = script_blocks(orig, replace)
    if os.environ.get("MD_DUMP_BLOCKS"):  # 실험용 — 번역이 든 디코드 블록을 파일로(코덱 설계 측정)
        import pickle

        Path(os.environ["MD_DUMP_BLOCKS"]).write_bytes(pickle.dumps(blocks))
    over_blocks = [
        f"블록 {i}: {len(b):,}B > {MAX_BLOCK:,}B (+{len(b) - MAX_BLOCK:,})"
        for i, b in enumerate(blocks[: archives.SCENE_BLOCKS])
        if len(b) > MAX_BLOCK
    ]
    if over_blocks:
        raise SystemExit(
            "디코드 블록이 원본 최대(램 버퍼 근거 없음)를 넘는다:\n    "
            + "\n    ".join(over_blocks)
        )
    for i, s in enumerate(sizes):
        if sum(s) != len(blocks[i]) and i < archives.SCENE_BLOCKS:
            raise SystemExit(f"블록 {i}: 모듈 크기 합 {sum(s)} ≠ 블록 길이 {len(blocks[i])}")
        if max(s) > scene.MODULE_MAX:
            raise SystemExit(f"블록 {i}: 모듈 {max(s)}B 가 한도 {scene.MODULE_MAX}B 를 넘는다")
    if os.environ.get("MD_KANA_DUMP"):  # 점검용 — 남은 가나 글줄 전체를 파일로
        _lf = kana_gate.scan(blocks[: archives.SCENE_BLOCKS], sizes)
        Path(os.environ["MD_KANA_DUMP"]).write_text(
            "\n".join(
                f"{k} {h} x{n} {kana_gate.sample(blocks[: archives.SCENE_BLOCKS], sizes, k, h)}"
                for k, c in sorted(_lf.items(), key=lambda kv: tuple(map(int, kv[0].split("-"))))
                for h, n in c.items()
            ),
            encoding="utf-8",
        )
    kana_gate.check(blocks[: archives.SCENE_BLOCKS], sizes, freeze="--freeze-kana" in sys.argv)
    rp_writes, rp_free, rp_info = repack.plan(
        orig
    )  # 다른 아카이브를 다시 눌러 만든 빈 칸 — 대본 블록이 앉는다
    sindex, main_blocks, placed = pack_script(blocks, rp_free)
    room = ARCHIVE_END - ARCHIVE_BASE
    used = len(sindex) + len(main_blocks)
    if used > room:
        raise SystemExit(
            f"대본 아카이브가 {used - room:,}B 넘친다 (본 칸 {used:,} > {room:,} · 다른 칸에 앉힌 블록 {len(placed)}개 {sum(len(p) for _a, p in placed):,}B)"
        )
    # 왕복: 다시 깐 아카이브(본 칸 + 앉힌 블록)를 색인으로 푼 결과가 입력과 같아야 한다
    img = bytearray(0x200000)
    img[ARCHIVE_BASE : ARCHIVE_BASE + used] = sindex + main_blocks
    for at, p in placed:
        img[at : at + len(p)] = p
    rt = [b for _, b, _ in archives.blocks(bytes(img), ARCHIVE_BASE)]
    if rt != blocks:
        raise SystemExit("재배치 왕복이 입력과 다르다")
    gain = sum(a - b for _n, a, b in rp_info)
    print(
        f"  대본 아카이브 본 칸 {used:,}B / {room:,}B (여유 {room - used:,}B) · 다른 칸에 앉힌 블록 {len(placed)}개 "
        f"{sum(len(p) for _a, p in placed):,}B (재압축으로 {gain:,}B 확보) · 왕복 OK · 정본 모듈 {len(maps)} · 바뀐 모듈 {len(replace)}"
    )
    if check_only:
        return

    rom = Rom(orig)
    hdr, tbl, gl = cs.resource0()  # 글꼴 리소스 0(대사) + 반각(리소스 1)
    rom.write("font0-header", cs.r0["hdr"], hdr)
    rom.write("font0-table", cs.r0["table"], tbl)
    rom.write("font0-glyphs", cs.r0["desc"], orig[cs.r0["desc"] : cs.r0["desc"] + 4] + gl)
    for label, pos, body in hangul.resource1(cs):
        rom.write(label, pos, body)
    for label, pos, body in table_writes:  # 고정 폭 표(아이템·주문·지명·메뉴 라벨) — 제자리
        rom.write(label, pos, body)
    for label, pos, body in places.plan(
        orig,
        {k: dict(v, ours=normalize(v.get("ours", ""))) for k, v in names["place_list"].items()},
        lambda s: encode_tagged(s, cs),
    ):  # 필드 HUD 지명 65 — 가변 폭 레코드 + 오프셋 표를 다시 깐다
        rom.write(label, pos, body)
    # 조사 훅 · 어절 줄넘김 · 반각 부호 줄 끝 · 「의␣」(ED1 과 같은 훅 — 주소만 engine.py 대응)
    halfspace.ensure_glyph()
    for label, pos, body in josa.plan(orig, cs, TAIL_HI - JOSA_RESERVE):
        rom.write(label, pos, body)
    for label, pos, body in wordwrap.plan(orig, TAIL_HI - JOSA_RESERVE - WRAP_RESERVE):
        rom.write(label, pos, body)
    for label, pos, body in halfspace.plan(cs, TAIL_HI - JOSA_RESERVE - WRAP_RESERVE):
        rom.write(label, pos, body)
    if josa.size(cs) > JOSA_RESERVE - punctwrap.CODE_LEN:
        raise SystemExit("조사 훅이 부호 줄바꿈 꼬리 자리를 침범한다 — JOSA_RESERVE 를 늘린다")
    for label, pos, body in punctwrap.plan(TAIL_HI - punctwrap.CODE_LEN):
        rom.write(label, pos, body)
    # 🔴 어절 줄넘김의 공백 판정 문턱을 **구운 글꼴로 매번 다시 잰다** — 글꼴이 바뀌어 문턱이 무너지면 빌드가 실패한다
    # ⚠ 합성 글리프(field_hud 의 PUA 콘덴스드 슬라이스)는 뺀다 — 일부러 큰 왼쪽 여백을 구워 둔 자리라 정상 글자처럼 재면 문턱이 깨진다
    normal_wide = {
        v
        for k, v in cs.hangul.items()
        if k not in hangul.CUSTOM_GLYPHS and k not in hangul.DEAD_CODES
    }
    gap, sp = wordwrap.gap_gate(bytes(rom.buf), normal_wide)
    print(
        f"  어절 줄넘김 — 글자 틈 최대 {gap}px < 문턱 {wordwrap.SPACE_PX}px ≤ 공백 틈 최소 {sp}px"
    )
    # 필드 HUD 뒷말(부근·입구)·방위(동서남북) — 문안을 안 거치고 코드가 SJIS 를 직접 찍는 여덟 자리 + 공백 트램펄린·정렬 상수
    for label, pos, body in field_hud.plan(
        cs, TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE
    ):
        rom.write(label, pos, body)
    for (
        label,
        pos,
        body,
    ) in sys_writes:  # 코드 영역 문안(시스템 메시지·이벤트 대사·장 카드) 묶음 + 참조 명령
        rom.write(label, pos, body)
    # 오프닝·엔딩 자막 — 글꼴 리소스 5(네오둥근모 16px, `<fd85>`)와 표·문안(꼬리로 옮김)
    cap5 = {c for c in captions.font5_chars(cmap) if c.strip() or c == " "}
    if cap5:
        for label, pos, body in hangul.resource5(
            cs,
            cap5,
            hangul.layout_after_r1(cs),
            cell=captions.FONT_CELL,
            source=captions.FONT_SRC,
            narrow_adv=captions.FONT_PITCH // 2,
            digit_extra=captions.DIGIT_EXTRA,
        ):
            rom.write(label, pos, body)
    for label, pos, body in cap_writes:
        rom.write(label, pos, body)
    for label, pos, body in hangul.resource2_labels():  # HUD 「ｱﾄ」 → 「남다」 (8×8, 마스터 도안)
        rom.write(label, pos, body)
    hud_chars: set[str] = set()
    for grp in ("party_rec", "party_name"):
        for e in names.get(grp, {}).values():
            hud_chars.update(re.sub(r"<[^>]*>", "", e.get("ours", "")))
    for label, pos, body in hangul.resource4(cs, hud_chars):  # HUD 이름 12×12
        rom.write(label, pos, body)
    spell_digit.check(orig)  # 주문 레벨 숫자를 반각으로(「레지나1을」)
    for label, pos, body in spell_digit.plan():
        rom.write(label, pos, body)
    for (
        label,
        pos,
        body,
    ) in hud_status.plan():  # HUD 상태이상 8칸 타일(守跳毒眠黙乱気絶 → 수·반·독·잠·묵·혼·기·절)
        rom.write(label, pos, body)
    tg = names.get("title_gfx", {})  # 타이틀 시작 메뉴 — 글꼴이 아니라 셀 그림
    words = {"start": tg.get("0", {}).get("ours", ""), "continue": tg.get("1", {}).get("ours", "")}
    for label, pos, body in gfxtext.plan(orig, words):
        rom.write(label, pos, body)
    # 전투 아카이브 — 블록마다 새 바이트(없으면 원본 디코드)를 다시 눌러 같은 자리에 깐다(남는 칸은 FF)
    bblocks = [b for _s, b, _e in battle.blocks(orig)]
    nchanged = 0
    for n, b in enumerate(bblocks):
        nb = battle.plan_block(
            b,
            n,
            {k: dict(v, ours=normalize(v.get("ours", ""))) for k, v in bmap.items()},
            monsters,
            cs.encode,
        )
        if nb is not None:
            bblocks[n] = nb
            nchanged += 1
    index, primary, tail = pack_battle(bblocks)
    rom.write(
        "battle-archive",
        battle.ARCHIVE,
        (index + primary).ljust(BATTLE_PRIMARY_END - battle.ARCHIVE, b"\xff"),
    )
    if tail:
        rom.write("battle-tail", BATTLE_TAIL_AT, tail.ljust(BATTLE_TAIL_RESERVE, b"\xff"))
    print(
        f"  전투 아카이브 원래 자리 {len(index) + len(primary):,}B / {BATTLE_PRIMARY_END - battle.ARCHIVE:,}B · "
        f"꼬리 {len(tail):,}B / {BATTLE_TAIL_RESERVE:,}B · 바뀐 블록 {nchanged}"
    )
    for (
        label,
        pos,
        body,
    ) in rp_writes:  # 다시 누른 아카이브(그래픽·misc) + 색인 없이 가리키던 직접 참조
        rom.allow(label, *repack.allowed(orig, [(label, pos, body)])[label])
        rom.write(label, pos, body)
    rom.write("script-archive", ARCHIVE_BASE, (sindex + main_blocks).ljust(room, b"\xff"))
    for k, (at, p) in enumerate(placed):
        rom.allow(f"script-placed:{k}", at, at + len(p))
        rom.write(f"script-placed:{k}", at, p)
    rom.write(
        "scene-sizes",
        SCENE_TABLE_AT,
        b"".join(struct.pack(">4H", *s) for s in sizes[: archives.SCENE_BLOCKS]),
    )
    if orig[SCENE_REF - 2 : SCENE_REF + 4] != b"\x43\xf9" + struct.pack(">I", archives.SCENE_SIZES):
        raise SystemExit("씬 크기 표를 부르는 명령(0x1A490 lea.l $19DC3C.l,a1)이 원본과 다르다")
    rom.write("scene-ref", SCENE_REF, struct.pack(">I", SCENE_TABLE_AT))
    debug_build.check_tag()
    ndbg = debug_build.apply(rom)
    if ndbg:
        print(
            f"  ⚠ 디버그 스위치 켜짐({debug_build.ENV}=1) — 시험·마스터 디버그 전용, 패치 {ndbg}곳(제품 롬 아님)"
        )
    rom.write("checksum", 0x18E, struct.pack(">H", common.header_checksum(rom.buf)))
    kana_gate.check_rom(
        bytes(rom.buf), freeze="--freeze-kana" in sys.argv
    )  # 최종 롬 전체 일본어 잔존(대본 밖 포함)
    verify_jump_readback(bytes(rom.buf), orig, smap, cs.encode)
    ncap = captions.verify_readback(
        bytes(rom.buf),
        orig,
        {k: dict(v, ours=normalize(v.get("ours", ""))) for k, v in cmap.items()},
        cs.encode,
    )
    nplace = places.verify_readback(
        bytes(rom.buf),
        orig,
        {k: dict(v, ours=normalize(v.get("ours", ""))) for k, v in names["place_list"].items()},
        lambda s: encode_tagged(s, cs),
    )
    print(f"  지명 표 되읽기 OK — 오프셋 표를 따라 읽은 레코드 {nplace}개가 의도와 같다")
    print(f"  자막 되읽기 OK — 표 포인터를 따라 읽은 스트림 {ncap}개가 의도와 같다")
    # 🔴 구운 이미지에서 전투 아카이브를 **색인으로** 다시 풀어 의도한 블록과 같은지 — 색인 오프셋(꼬리로 간 블록 포함)·압축·자리를 한 번에 본다
    got_b = [b for _s, b, _e in archives.blocks(bytes(rom.buf), battle.ARCHIVE)]
    if got_b != bblocks:
        bad = [i for i, (x, y) in enumerate(zip(got_b, bblocks, strict=True)) if x != y]
        raise SystemExit(f"전투 아카이브 되읽기 불일치(블록 {bad[:8]})")
    print(f"  전투 아카이브 되읽기 OK — 색인으로 푼 {len(got_b)}블록이 의도와 같다")
    # 🔴 다시 누른 아카이브(그래픽·misc)와 대본 아카이브(앉힌 블록 포함)를 **구운 이미지에서 색인으로** 풀어 의도와 같은지
    for name in repack.OTHER:
        base = archives.ARCHIVES[name][0]
        want = [b for _s, b, _e in archives.blocks(orig, base)]
        got = [b for _s, b, _e in archives.blocks(bytes(rom.buf), base)]
        if got != want:
            raise SystemExit(f"{name} 아카이브 되읽기가 원본 디코드와 다르다")
    got_s = [b for _s, b, _e in archives.blocks(bytes(rom.buf), ARCHIVE_BASE)]
    if got_s != blocks:
        raise SystemExit("대본 아카이브 되읽기가 의도와 다르다")
    print("  아카이브 되읽기 OK — 그래픽·misc 5개가 원본 디코드와, 대본 90블록이 의도와 같다")
    rom.verify_no_overlap()
    rom.verify_immutable()
    out_dir = common.BUILD_DIR / common.BUILD_TAG.replace("/", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    # 🔴 지난 실패 표식을 지운다 — pull-build.sh 는 .failed 가 하나라도 있으면 그 칸을 통째로 거부한다
    for stale in out_dir.glob("*.failed"):
        stale.unlink()
    out = out_dir / debug_build.rom_name()
    out.write_bytes(bytes(rom.buf))
    print(f"  {out} — 쓰기 {len(rom.log)}건 · sha1 {common.sha1_of_bytes(bytes(rom.buf))[:8]}…")


if __name__ == "__main__":
    try:
        main("--check" in sys.argv)
    except SystemExit as e:
        out_dir = common.BUILD_DIR / common.BUILD_TAG.replace("/", "_")
        p = out_dir / debug_build.rom_name()
        if p.exists():
            p.rename(p.with_suffix(".bin.failed"))
        raise SystemExit(f"❌ 빌드 실패: {e}") from e
