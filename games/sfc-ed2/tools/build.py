"""sfc-ed2 배치기 — 원본을 2MB 로 넓혀 번역 문안(`textmap/`)을 얹고 규율 검사를 건다.

입력: 원본 롬(지문 검사) + `textmap/{segments,ui,dict}.json`(우리 번역) + 정본(`shared/canon` — 사전 이름).
출력: `work/build/<꼬리표>/…(KR).sfc` (2MB, 헤더 체크섬 재계산).

순서: 코드 패치(`patches.py`) → 쓰인 글자 수집·글리프 배정(`kr.allocate`) → 사전(`$E0/$E1` 표) → UI 창 블록 → 대사 구간(트램펄린) →
      글꼴 표(`$D8:0000`) → 체크섬.

규율(루트 CLAUDE.md 「빌드 규율」):
  · 원본은 `common.rom_bytes()` 로만 읽는다(지문 검사) — 제자리 갱신 없음
  · 무변경 구간 선언 + 출력과 원본 byte 대조: 쓴 자리(`writes`)와 코드 패치 자리만 다를 수 있다
  · 결정성: 같은 입력이면 같은 바이트(`--twice`)
  · 화면 일본어 게이트: 번역 안 된 구간 수(`--strict` 면 0 이어야 한다)
  · 번역이 원문과 어긋나면(원문 바이트 sha1 불일치) 조용히 넘기지 않고 죽는다
  · 실패하면 산출물을 `*.failed` 로 돌린다

    python3 games/sfc-ed2/tools/build.py [--twice] [--strict]
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
import hangul_font
import hud_tiles
import kr
import monsters
import patches
import relocate
import scan_text
import script
import segs
import typeset
import ui

NEW_SIZE = 2 * 1024 * 1024
OUT_NAME = "Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"
CHK_OFF = common.HEADER_OFF + 0x1C  # 보수(2B) + 체크섬(2B)
IMMUTABLE = [(0, common.ROM_SIZE)]
EXCEPT = [(CHK_OFF, CHK_OFF + 4)] + patches.EXCEPT
NOOP = 0x16  # 대사 제어코드 `$16` = 핸들러가 `rts` 뿐인 빈 토큰(남는 자리 채움)
TRAMP = patches.TRAMP_CODE

# 확장 뱅크 배치: `$D8` = 글꼴(0x0000~0x8FFF) + 꼬리(0xA000~: 창 블록·사전) · `$D9~$DF` = 대사 번역문
TAIL_START = (patches.FONT_BANK << 16) | 0xA000
TAIL_END = (patches.FONT_BANK << 16) | 0xEFFF  # $D8:F000~ 은 조사 훅 표
FAR_BANKS = list(range(0xD9, 0xE0))


class Space:
    """확장 영역 배치기 — 항목이 뱅크 경계를 넘지 않게 순서대로 놓는다(결정적)."""

    def __init__(self, rom: bytearray, writes: list, banks=None, tail=False):
        self.rom, self.writes = rom, writes
        self.tail = tail
        self.cur = TAIL_START if tail else (FAR_BANKS[0] << 16)
        self.banks = banks

    def put(self, data: bytes) -> int:
        lo = self.cur & 0xFFFF
        if self.tail:
            if self.cur + len(data) > TAIL_END:
                raise SystemExit("확장 꼬리 영역 부족")
        elif lo + len(data) > 0x10000:
            nb = (self.cur >> 16) + 1
            if nb > FAR_BANKS[-1]:
                raise SystemExit("확장 뱅크 부족($D9~$DF)")
            self.cur = nb << 16
        addr = self.cur
        o = common.snes2off(addr)
        self.rom[o : o + len(data)] = data
        self.writes.append((o, o + len(data)))
        self.cur += len(data)
        return addr


# 뱅크 안 빈 자리(전부 $FF — `check_free` 가 단언한다). 16비트 포인터(`$0F`·표)가 뱅크를 못 넘으니 같은 뱅크에 둔다.
LOCAL_FREE = {
    0xC1: [(0xFC00, 0xFFFF)],
    0xCB: [(0xB380, 0xFFFF)],
    0xD4: [(0xCE60, 0xFFFF)],
    0xD5: [(0xDEF0, 0xFFFF)],
}


ITEM_TABLE = "$C1772D"
ITEM_TABLE_BANK = 0xD4
ITEM_NAME_MAX = 15


class Local:
    """뱅크별 빈 자리 배치기. 사용 전에 원본에서 전부 $FF 인지 확인한다."""

    def __init__(self, rom: bytearray, src: bytes, writes: list):
        self.rom, self.writes = rom, writes
        self.cur = {}
        for bank, rs in LOCAL_FREE.items():
            for a, b in rs:
                o = ((bank - 0xC0) << 16)
                if any(x != 0xFF for x in src[o + a : o + b + 1]):
                    raise SystemExit(f"빈 자리가 비어 있지 않다: ${bank:02X}:{a:04X}~{b:04X}")
            self.cur[bank] = [list(r) for r in rs]

    def put(self, bank: int, data: bytes) -> int:
        for r in self.cur[bank]:
            if r[1] - r[0] + 1 >= len(data):
                a = r[0]
                r[0] += len(data)
                o = ((bank - 0xC0) << 16) + a
                self.rom[o : o + len(data)] = data
                self.writes.append((o, o + len(data)))
                return a
        raise SystemExit(f"${bank:02X} 빈 자리 부족")


def fix_checksum(rom: bytearray) -> None:
    rom[CHK_OFF : CHK_OFF + 4] = b"\x00\x00\xff\xff"  # 합 계산 때 체크섬 칸은 00 00 FF FF 로 친다(SNES 규약)
    s = sum(rom) & 0xFFFF
    rom[CHK_OFF : CHK_OFF + 2] = (s ^ 0xFFFF).to_bytes(2, "little")
    rom[CHK_OFF + 2 : CHK_OFF + 4] = s.to_bytes(2, "little")


def apply_patches(rom: bytearray) -> None:
    for addr, old, new in patches.PATCHES:
        o = common.snes2off(addr)
        if bytes(rom[o : o + len(old)]) != old:
            raise SystemExit(f"패치 자리가 원본과 다르다: {common.fmt(addr)} {bytes(rom[o : o + len(old)]).hex()} ≠ {old.hex()}")
        rom[o : o + len(new)] = new


# ───────────────────────── 번역 문안 읽기 ─────────────────────────

_JOSA = re.compile(r"\{([^{}/*][^{}/]*)/([^{}/]+)\}")


def has_final(word: str) -> bool:
    """마지막 한글 음절에 받침이 있나(없으면 False). 한글이 아니면 False."""
    for c in reversed(word):
        if "가" <= c <= "힣":
            return (ord(c) - 0xAC00) % 28 != 0
    return False


def final_rieul(word: str) -> bool:
    for c in reversed(word):
        if "가" <= c <= "힣":
            return (ord(c) - 0xAC00) % 28 == 8
    return False


def resolve_josa(text: str, names: dict[str, str]) -> str:
    """`<E0:n>{은/는}` → 그 사전 이름의 받침에 맞는 쪽. 사전 참조 바로 뒤의 `{A/B}` 만 푼다(A = 받침 있을 때). `(으)로` 류는 `{으로/로}`.
    ⚠ ㄹ 받침 + `{으로/로}` 는 「로」."""
    out, pos = [], 0
    for m in _JOSA.finditer(text):
        before = text[pos : m.start()]
        out.append(before)
        pos = m.end()
        prev = text[: m.start()]
        ref = re.search(r"<E([01]):(\d+)>$", prev)
        if ref:
            name = names.get(f"E{ref.group(1)}:{ref.group(2)}")
            if name is None:
                raise SystemExit(f"조사 앞 사전 참조 {ref.group(0)} 의 이름이 없다")
        else:
            name = re.sub(r"<[^>]*>", "", prev)
        a, b = m.group(1), m.group(2)
        pick = a if has_final(name) else b
        if a.startswith("으") and final_rieul(name):
            pick = b
        out.append(pick)
    out.append(text[pos:])
    return "".join(out)


def _mon_lookup(canon, base: str):
    """몬스터 이름 정본 조회 — 원문 표기 차(공백·반각 숫자)는 같은 원문으로 본다(정본은 「ブラムナクイーン」「ゴドウィン２世」)."""
    for v in (base, base.replace(" ", ""), base.replace(" ", "").replace("2", "２")):
        r = canon.lookup(v, "monster", "ed2")
        if r:
            return r
    return None


def dict_names(src: bytes, tm_dict: dict) -> dict[str, str]:
    """사전 항목 → 한국어. `$E0`(이름 74) 는 정본에서 읽고(게임 폴더에 표를 안 둔다), 정본에 없거나 마스터 확인 대기인 건 textmap 이 덮는다."""
    import canon
    from canon import names

    out = {}
    for tbl, n, jp in script.dict_entries(src):
        key = f"{tbl}:{n}"
        if key in tm_dict:
            out[key] = tm_dict[key]["kr"]
        elif tbl == "E0":
            r = canon.lookup(jp, None, "ed2")
            if r:
                # 정본 지명은 **칸 꼴**(붙여 씀)이다 — 사전 `$E0` 은 대사에 나가므로 대사 꼴(종류 말·「~의」 뒤를 띄움)로 바꾼다
                out[key] = names.dialog_place(r) if canon.lookup(jp, "place", "ed2") else r
    return out


# ───────────────────────── 조립 ─────────────────────────


def e1_texts(src: bytes, seg_map: dict) -> dict[str, str]:
    """`$E1` 사전 항목(문장 끝맺음 등)의 한국어 — 이 문자열들은 사전 표가 아니라 **대사 구간**으로 번역돼 있다(표 포인터는 그대로, 구간이 제자리에 덮인다).
    조판기가 줄 폭을 셀 때 쓴다(이게 없으면 토큰 폭이 0 이라 뒤 문장이 줄 밖으로 넘치고, 토큰 바로 뒤 공백이 「줄 첫 공백」으로 지워졌다)."""
    out = {}
    base = common.snes2off(script.DICTS_BY_NAME["E1"])
    for tbl, n, _jp in script.dict_entries(src):
        if tbl != "E1":
            continue
        o = base + 3 * (n - 1)
        a = common.snes2off(src[o] | src[o + 1] << 8 | src[o + 2] << 16)
        v = seg_map.get(segs.seg_id(a))
        if v:
            out[f"E1:{n}"] = re.sub(r"<[^>]*>", "", v["kr"])
    return out


def call_texts(text: str, seg_off: int, seg_map: dict, sg: dict) -> dict[str, str]:
    """이 구간이 부르는 조각(`<10 lo hi>`)의 한국어 — 같은 뱅크 안 주소다. 조판기가 폭을 세는 데 쓴다."""
    out = {}
    bank = (common.off2snes(seg_off) >> 16) & 0xFF
    for m in re.finditer(r"<10 ([0-9a-f]{2}) ([0-9a-f]{2})>", text):
        lo, hi = m.group(1), m.group(2)
        tgt = segs.seg_id(common.snes2off((bank << 16) | int(hi, 16) << 8 | int(lo, 16)))
        v = seg_map.get(tgt)
        if v:
            out[f"call:{lo}{hi}"] = v["kr"]
    return out


BATTLE_NAME_W = 20  # 몬스터 이름(+접미 A~D) 가운데 가장 긴 폭(사일런트로드B · 스트라이프츠A) — 단위는 조판 폭(전각 한글 3 · 반각 2)
BATTLE_PREFIX_W = 6  # 두 이름이 이어지는 「A와 B가 나타났다」 앞에 붙는 표시 글자(`kkk`)


def battle_typeset(text: str) -> str:
    """전투 문구는 앞에 이름(몬스터·파티, 런타임 변수)이 붙어 문안 쪽 폭만으로는 줄 폭을 모른다 — 그 자리를 가장 긴 이름 폭으로 잡고 어절 단위로 줄을 나눈다.
    (엔진은 줄이 넘치면 낱말 가운데서 끊는다 — 「날아갔/다.」. 손으로 줄바꿈을 넣으면 문안이 바뀔 때 다시 깨진다.)"""
    m = re.match(r"((?:<02>)?)(\{\*[^{}]*\})", text)
    if m and "\n" not in text and "<1e>" not in text:
        rest = text[m.end(1) :]
        names = {"E0:999": "가나다라마바A"}  # 폭 3×6+2 = 20
        out = typeset.typeset("<E0:999>" + rest, names).replace("<E0:999>", "", 1)
        return m.group(1) + out
    if text.endswith(" 나타났다.") and "<" not in text and "\n" not in text:
        names = {"E0:998": "kkk"}  # 폭 6
        return typeset.typeset("<E0:998>" + text, names).replace("<E0:998>", "", 1)
    return text


def collect_texts(src: bytes) -> tuple[dict, dict, dict]:
    seg_map = kr.load("segments")
    ui_map = kr.load("ui")
    dict_map = kr.load("dict")
    return seg_map, ui_map, dict_map


def ptrs16_canon_chars(src: bytes, key: str, v: dict) -> set[str]:
    import canon

    base = int(key.lstrip("$"), 16)
    o = common.snes2off(base)
    out = set()
    for i in range(v["count"]):
        if str(i) in v.get("over", {}):
            continue
        w = src[o + 2 * i] | src[o + 2 * i + 1] << 8
        a = common.snes2off(((base >> 16) << 16) | w)
        e = a
        while src[e] != 0:
            e += 1
        jpn = ui.row_text(src, src[a:e]).rstrip(" 　")
        t = canon.lookup(jpn, v.get("cat"), "ed2") if jpn else None
        if t:
            out |= kr.chars_of(t)
    return out


def _fullwidth(t: str) -> str:
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in t)


def canon_lookup_jp(jp: str, ctx: str | None = None) -> str | None:
    """원문 글자(ROM 에서 읽은 것) → 정본 값. 롬 글리프표가 전각 영문을 반각으로 읽으니 전각 꼴도 시도하고, 자리 구분(`원문@자리`)이 있으면 그것도 본다."""
    import canon

    for k in (jp, _fullwidth(jp)):
        for kk in ((f"{k}@{ctx}", k) if ctx else (k,)):
            r = canon.lookup(kk, None, "ed2")
            if r:
                return r
    return None


def ui_row(src: bytes, addr: int, i: int, r: str, ctx: str | None, jp_over: dict | None = None) -> str:
    """ui 줄 — `{c}` 가 있으면 그 줄의 원문 글자로 정본을 조회해 채운다."""
    if "{c}" not in r:
        return r
    blk = ui.parse(src, addr)
    jp = (jp_over or {}).get(str(i)) or ui.row_text(src, blk["raw"][i]).strip(" 　")  # `jp`: 1바이트 반각 가타카나 줄처럼 글자표로 못 읽는 줄의 조회 열쇠
    c = canon_lookup_jp(jp, ctx)
    if not c:
        raise SystemExit(f"UI {common.fmt(addr)}[{i}]: 정본에 「{jp}」 가 없다 — 관리자에게 후보로")
    return r.replace("{c}", c)


def canon_text(src: bytes, key: str, v: dict) -> str:
    """cells·spans 의 문안 — `canon: true` 면 정본(canon ui)에서 읽어 `{c}` 자리에 넣는다(게임 폴더에 값을 두지 않는다). 원문은 `from`(없으면 자기 자리) 바이트에서 읽는다."""
    text = v["kr"]
    if not v.get("canon"):
        return text
    fa = common.snes2off(int(v.get("from", key).lstrip("$"), 16))
    jp = segs.notation(src, fa, fa + v.get("from_n", v["n"])).strip(" 　")
    c = canon_lookup_jp(jp, v.get("ctx"))
    if not c:
        raise SystemExit(f"{key}: 정본에 「{jp}」 가 없다 — 관리자에게 후보로")
    return text.replace("{c}", c)


def records_canon_chars(src: bytes, key: str, v: dict) -> set[str]:
    import canon

    base = common.snes2off(int(key.lstrip("$"), 16))
    out = set()
    for i in range(v["count"]):
        a = base + i * v["stride"]
        jp = ui.row_text(src, src[a : a + v["stride"]]).strip(" 　")
        t = v.get("over", {}).get(str(i)) or (canon.lookup(jp, v.get("cat"), "ed2") if jp else None)
        if t:
            out |= kr.chars_of(t)
    return out


def _build(slots, dead: list, font_out: bool = True, lenient: bool = False) -> tuple[bytes, list, dict]:
    """slots = 한글에 줄 글리프 색인 후보(오름차순). dead = 번역으로 옮겨 가 더는 안 읽히는 원문 구간(파일 오프셋)을 여기에 모은다."""
    src = common.rom_bytes()
    rom = bytearray(src) + bytearray(b"\xff" * (NEW_SIZE - len(src)))
    writes: list[tuple[int, int]] = []
    apply_patches(rom)
    seg_map, ui_map, dict_map = collect_texts(src)
    names = dict_names(src, dict_map)

    # 1. 쓰일 글자 수집 → 글리프 배정(결정적)
    chars = kr.Chars()
    for v in seg_map.values():
        chars |= kr.chars_of(resolve_josa(v["kr"], names))
    for k, v in ui_map.items():
        for i, r in enumerate(v["rows"]):
            chars |= kr.chars_of(ui_row(src, int(k.lstrip("$"), 16), i, r, v.get("ctx"), v.get("jp"))) if r is not None else set()
    for k, v in kr.load("cells").items():
        chars |= kr.chars_of(canon_text(src, k, v))
    for k, v in kr.load("spans").items():
        chars |= kr.chars_of(canon_text(src, k, v))
    for v in kr.load("opsplit").values():
        chars |= kr.chars_of(v["kr"])
    for v in kr.load("listsplit").values():
        chars |= kr.chars_of(v["kr"])
    for key, v in kr.load("records").items():
        chars |= records_canon_chars(src, key, v)
    if kr.load("monsters"):
        import canon

        for _w, ss in monsters.groups(src):
            for sb in ss:
                base, suf = monsters.split_name(monsters.decode(sb, src))
                k = _mon_lookup(canon, base)
                if k:
                    chars |= kr.chars_of(k + suf)
        for v in kr.load("monsters").get("over", {}).values():
            chars |= kr.chars_of(v)
    for key, v in kr.load("ptrs16").items():
        for t in v.get("over", {}).values():
            chars |= kr.chars_of(t)
        chars |= ptrs16_canon_chars(src, key, v)
    for v in names.values():
        chars |= kr.chars_of(v)
    chars |= kr.JOSA_CHARS
    for c in kr.JOSA_CHARS:
        chars[c] += 10**6  # 조사 훅이 부르는 글자는 절대 밀려나면 안 된다
    alloc = kr.allocate(chars, slots, lenient=lenient)

    far = Space(rom, writes)
    tail = Space(rom, writes, tail=True)
    stats = {"seg_inplace": 0, "seg_tramp": 0, "ui_inplace": 0, "ui_moved": 0, "dict": 0}

    # 2. 사전(`$E0/$E1`) — 새 문자열을 꼬리에 두고 3바이트 포인터 표 항목만 고친다
    for tbl, n, _jp in script.dict_entries(src):
        key = f"{tbl}:{n}"
        if key in names:
            data = kr.encode(resolve_josa(names[key], names), alloc) + b"\x06"
            addr = tail.put(data)
            base = script.DICTS_BY_NAME[tbl]
            o = common.snes2off(base) + 3 * (n - 1)
            oa = common.snes2off(src[o] | src[o + 1] << 8 | src[o + 2] << 16)
            oe = oa
            while src[oe] != 0x06:
                oe += 1
            dead.append((oa, oe + 1))
            rom[o : o + 3] = bytes([addr & 0xFF, (addr >> 8) & 0xFF, addr >> 16])
            writes.append((o, o + 3))
            stats["dict"] += 1

    # 3. UI 창 블록 — 제자리가 되면 제자리, 아니면 꼬리로 옮겨 stride·w 를 넓힌다
    for key, v in sorted(ui_map.items()):
        addr = int(key.lstrip("$"), 16)
        blk = ui.parse(src, addr)
        if v.get("h") and v["h"] != segs.src_hash(src, common.snes2off(addr), common.snes2off(addr) + 5 + blk["rows"] * blk["stride"]):
            raise SystemExit(f"UI 블록 {key}: 원문 해시 불일치 — 원본이 달라졌거나 textmap 이 낡았다")
        o0 = common.snes2off(addr) + 5
        rows = []
        for i, r in enumerate(v["rows"]):
            raw = bytes(src[o0 + i * blk["stride"] : o0 + (i + 1) * blk["stride"] - 1])
            if r is None:  # null = 정본(canon)에 같은 원문이 있으면 그 문안, 없으면 원문 줄 그대로(판정 대기)
                import canon

                jpn = ui.row_text(src, raw).strip(" 　")
                t = canon.lookup(jpn, None, "ed2") if jpn else None
                r = f"<1f> {t} " if t else None
            if r is not None:
                r = ui_row(src, addr, i, r, v.get("ctx"), v.get("jp"))
            rows.append(kr.encode(resolve_josa(r, names), alloc) if r is not None else raw.rstrip(b" "))
        dead.append((common.snes2off(addr), common.snes2off(addr) + 5 + blk["rows"] * blk["stride"]))
        try:
            ui.put_rows(rom, addr, rows, writes, v.get("n"))
            stats["ui_inplace"] += 1
        except SystemExit:
            tail.cur = ui.move_block(rom, src, addr, tail.cur, rows, writes)
            stats["ui_moved"] += 1

    # 3a. 16비트 포인터 표(같은 뱅크 안 문자열) — 지역명 등. 번역은 정본(canon)에서 읽고, 정본에 없는 건 textmap 의 over 가 채운다
    local = Local(rom, src, writes)
    missing = []
    for key, v in sorted(kr.load("ptrs16").items()):
        base = int(key.lstrip("$"), 16)
        bank = base >> 16
        o = common.snes2off(base)
        if v.get("h") != segs.src_hash(src, o, o + 2 * v["count"]):
            raise SystemExit(f"포인터 표 {key}: 원문 해시 불일치 — textmap 이 낡았다")
        cache = {}
        pad_px = 0
        jps = []
        for i in range(v["count"]):
            w = src[o + 2 * i] | src[o + 2 * i + 1] << 8
            a = common.snes2off((bank << 16) | w)
            e = a
            while src[e] != 0:
                e += 1
            jps.append(src[a:e])
            pad_px = max(pad_px, ui.px_width(src[a:e]))
        for i, jpb in enumerate(jps):
            over = v.get("over", {}).get(str(i))
            jp = segs.notation(src, 0, 0) if False else None
            if over is not None:
                text = over
            else:
                import canon

                jpn = ui.row_text(src, jpb).rstrip(" 　")
                text = canon.lookup(jpn, v.get("cat"), "ed2") if jpn else ""
                if text is None:
                    missing.append((key, i, jpn))
                    continue  # 정본에 없다 — 원문을 둔다(관리자에게 후보로 올린다)
            data = kr.encode(text, alloc)
            px = ui.px_width(data)
            dead.append((common.snes2off((bank << 16) | (src[o + 2 * i] | src[o + 2 * i + 1] << 8)), common.snes2off((bank << 16) | (src[o + 2 * i] | src[o + 2 * i + 1] << 8)) + len(jpb) + 1))
            data += b" " * max(0, (pad_px - px) // 8)
            addr = local.put(bank, data + b"\x00")
            rom[o + 2 * i : o + 2 * i + 2] = bytes([addr & 0xFF, (addr >> 8) & 0xFF])
            writes.append((o + 2 * i, o + 2 * i + 2))
            stats["ptrs16"] = stats.get("ptrs16", 0) + 1
    stats["missing"] = missing

    # 3d. 고정폭 레코드 표(records) — 아이템·주문 이름. 원문 이름은 레코드에서 읽어 정본(canon)으로 번역하고, 오른쪽 정렬로 채운다
    for key, v in sorted(kr.load("records").items()):
        base = common.snes2off(int(key.lstrip("$"), 16))
        st, cnt = v["stride"], v["count"]
        moved = key == ITEM_TABLE  # 아이템 이름 표는 16B 칸(이름 15B + 여분) 새 표로 옮긴다 — 14B 칸에 안 드는 이름 때문(마스터 10-13)
        newtab = bytearray() if moved else None
        lim = ITEM_NAME_MAX if moved else st
        if v.get("h") != segs.src_hash(src, base, base + st * cnt):
            raise SystemExit(f"레코드 표 {key}: 원문 해시 불일치 — textmap 이 낡았다")
        for i in range(cnt):
            a = base + i * st
            jp = ui.row_text(src, src[a : a + st]).strip(" 　")
            over = v.get("over", {}).get(str(i))
            if over is not None:
                text = over
            else:
                import canon

                text = canon.lookup(jp, v.get("cat"), "ed2") if jp else None
            if moved:
                newtab += bytes(src[a : a + st]) + b"\x06\x00"  # 기본 = 원본 14B 칸 + 끝 토큰(코드가 `$120F` 에 쓰던 것) + 여분
            if not text:
                if jp:
                    stats.setdefault("missing", []).append((key, i, jp))
                continue
            data = kr.encode(resolve_josa(text, names), alloc)
            if len(data) > lim:
                stats.setdefault("toolong", []).append((key, i, text, len(data), lim))
                continue
            if moved:
                if len(data) == ITEM_NAME_MAX:  # 15B — 끝 토큰 없이 칸을 꽉 채운다(소비자 패치가 14번 색인에서 멈춘다)
                    newtab[-16:] = data + b"\x00"
                else:
                    pad = st - len(data)
                    newtab[-16:] = b"\x80\x00" * (pad // 2) + data + (b"\x06" if pad % 2 else b"") + b"\x06\x00"  # 홀수 한 바이트는 반각 공백이 아니라 끝 토큰으로 채운다 — 공백이면 대사에서 이름 뒤 조사 앞에 한 칸이 찍힌다(「카논의 친서 를」, 원판은 없음)
                stats["records"] = stats.get("records", 0) + 1
                continue
            pad = st - len(data)
            # 왼쪽은 전각 공백 쌍만 둔다(출력기가 앞쪽 `80 00` 쌍을 건너뛰어 왼쪽 정렬로 보인다). 홀수 한 바이트는 **뒤**에 둔다 —
            # 앞에 두면 쌍 건너뛰기가 거기서 멈춰 이름이 반각 한 칸 밀린다(「천 옷」)
            left = b"\x80\x00" * (pad // 2)
            rom[a : a + st] = left + data + (b"\x06" if pad % 2 else b"")
            writes.append((a, a + st))
            stats["records"] = stats.get("records", 0) + 1
        if moved:
            ta = local.put(ITEM_TABLE_BANK, bytes(newtab))
            for addr3, lo in ((0xC13320, ta), (0xC1333B, ta + 76 * 16)):  # `ldx #lo` · `ldx #hi` · `ldx #bank` (id<100 · id≥100 의 시작 색인 76)
                for k, val in enumerate((lo & 0xFF, lo >> 8, ITEM_TABLE_BANK)):
                    o = common.snes2off(addr3 + 5 * k)
                    rom[o : o + 1] = bytes([val])
                    writes.append((o, o + 1))

    # 3d2. HUD 그림 타일 — 인물 이름(아트라스 …)·「あと」 라벨: 갈무리7 8×8 타일을 롬 타일 세트에 굽고 이름 표(`$C0:B525`)를 다시 쓴다
    import canon

    tiles, table = hud_tiles.plan(lambda jp: canon.lookup(jp, None, "ed2"))
    label = canon.lookup("あと@경험치표시", None, "ed2")
    if not label:
        raise SystemExit("HUD 라벨: 정본에 「あと@경험치표시」 가 없다")
    tiles.update(hud_tiles.label_tiles(label))
    for t, data in sorted(tiles.items()):
        o = hud_tiles.tile_off(t)
        rom[o : o + 32] = data
        writes.append((o, o + 32))
    o = common.snes2off(hud_tiles.NAME_TABLE)
    if bytes(src[o : o + 16]) != hud_tiles.NAME_TABLE_ORIG:
        raise SystemExit("HUD 이름 표가 원본과 다르다")
    rom[o : o + 16] = table
    writes.append((o, o + 16))
    stats["hud_tiles"] = len(tiles)

    # 3e. 몬스터 이름 풀 — 군(길이 접두 문자열 묶음)을 정본 이름으로 다시 만들어 뱅크 빈 자리에 두고 포인터 표만 고친다
    mon = kr.load("monsters")
    if mon:
        import canon

        t = common.snes2off(monsters.TABLE)
        if mon.get("h") != segs.src_hash(src, t, t + 2 * monsters.GROUPS):
            raise SystemExit("몬스터 포인터 표 원문 해시 불일치")
        for gi, (w, ss) in enumerate(monsters.groups(src)):
            new = bytearray()
            for si, sb in enumerate(ss):
                over = mon.get("over", {}).get(f"{gi}:{si}")
                jp = monsters.decode(sb, src)
                base, suf = monsters.split_name(jp)
                krn = over if over is not None else _mon_lookup(canon, base)
                if krn:
                    body = kr.encode(krn + suf, alloc)
                else:
                    body = sb  # 정본에 없다 — 원문 그대로(관리자에게 후보로)
                    stats.setdefault("missing", []).append(("monster", f"{gi}:{si}", base))
                new += bytes([len(body)]) + body
            dead.append((common.snes2off(0xCB0000 | w), common.snes2off(0xCB0000 | w) + sum(1 + len(sb) for sb in ss)))
            addr = local.put(0xCB, bytes(new))
            rom[t + 2 * gi : t + 2 * gi + 2] = bytes([addr & 0xFF, addr >> 8])
            writes.append((t + 2 * gi, t + 2 * gi + 2))
            stats["monsters"] = stats.get("monsters", 0) + 1

    # 3b. 고정 길이 칸(cells) — 코드가 `mvn` 으로 줄 버퍼에 복사하는 값 상수(OFF·速い…): 같은 길이로 제자리 치환(길이가 달라지면 죽는다)
    for key, v in sorted(kr.load("cells").items()):
        a = common.snes2off(int(key.lstrip("$"), 16))
        n = v["n"]
        if v.get("h") != segs.src_hash(src, a, a + n):
            raise SystemExit(f"칸 {key}: 원문 해시 불일치 — textmap 이 낡았다")
        text = canon_text(src, key, v)
        data = kr.encode(resolve_josa(text, names), alloc)
        if len(data) != n:
            raise SystemExit(f"칸 {key}: 번역 {len(data)}B ≠ 원문 {n}B — <pad:{n}> 로 맞춘다")
        rom[a : a + n] = data
        writes.append((a, a + n))
        stats["cells"] = stats.get("cells", 0) + 1

    # 3c. 제자리 치환 문자열(spans) — 길이가 정해진 레코드/문자열. 번역이 원문 바이트 수 n 을 넘으면 죽고, 모자라면 $16(빈 토큰)으로 채운다
    for key, v in sorted(kr.load("spans").items()):
        a = common.snes2off(int(key.lstrip("$"), 16))
        n = v["n"]
        if v.get("h") != segs.src_hash(src, a, a + n):
            raise SystemExit(f"문자열 {key}: 원문 해시 불일치 — textmap 이 낡았다")
        text = canon_text(src, key, v)
        data = kr.encode(resolve_josa(text, names), alloc)
        if v.get("move"):
            # 뱅크 $CB 빈 자리로 옮기고 `ldx #imm16`(`A2 lo hi`) 자리 — `move` 의 주소들 — 의 즉치를 돌린다. 복사 길이(`mvn`)가 원문(26B)보다 넓어졌으므로(patches.py `CB:66F3`)
            # 끝 토큰 뒤를 0 으로 채워 둔다(옆 문자열의 앞머리가 버퍼에 딸려 들어가지 않게)
            pad = v.get("pad", 30)
            if len(data) + 1 > pad:
                raise SystemExit(f"문자열 {key}: 번역 {len(data)}B 가 복사 길이 {pad}B 를 넘는다")
            new = local.put(0xCB, data + b"\x00" * (pad - len(data)))
            for site in v["move"]:
                so = common.snes2off(int(site.lstrip("$"), 16))
                if src[so] != 0xA2 or src[so + 1 : so + 3] != bytes([a & 0xFF, (common.off2snes(a) >> 8) & 0xFF]):
                    raise SystemExit(f"문자열 {key}: {site} 가 `ldx #{key[-4:]}` 가 아니다")
                rom[so + 1 : so + 3] = bytes([new & 0xFF, new >> 8])
                writes.append((so + 1, so + 3))
            rom[a : a + n] = bytes([NOOP]) * n
            writes.append((a, a + n))
            stats["spans"] = stats.get("spans", 0) + 1
            continue
        if len(data) > n:
            raise SystemExit(f"문자열 {key}: 번역 {len(data)}B > 원문 {n}B — 줄이거나 이전(`move`)해야 한다")
        rom[a : a + n] = data + bytes([NOOP]) * (n - len(data))
        writes.append((a, a + n))
        stats["spans"] = stats.get("spans", 0) + 1

    # 4. 대사 구간 — 짧으면 제자리, 길면 트램펄린
    e1w = e1_texts(src, seg_map)
    sg = {segs.seg_id(a): (a, b) for a, b in segs.segments(src)}
    typeset_end: dict[int, tuple[str, dict]] = {}  # 구간 끝 오프셋 → (조판한 문안, 폭 표) — 바로 이어지는 다음 구간의 시작 줄 폭
    for key, v in sorted(seg_map.items()):
        if key not in sg:
            raise SystemExit(f"textmap 구간 {key} 가 원본에 없다")
        a, b = sg[key]
        if v.get("h") != segs.src_hash(src, a, b):
            raise SystemExit(f"구간 {key}: 원문 해시 불일치({v.get('h')} ≠ {segs.src_hash(src, a, b)}) — textmap 이 낡았다")
        text = resolve_josa(v["kr"], names)
        dead.append((a, b))
        if (common.off2snes(a) >> 16) == 0xD7:
            # $D7(오프닝·엔딩) — UI 출력기($C0:9395)는 트램펄린($17)을 몰라 **문자열을 옮기고 포인터를 고친다**
            data = kr.encode(text, alloc) + b"\x00"
            old = common.off2snes(a)
            refs = relocate.refs24(src, old, (a, b)) + [x for t in relocate.a6_sites(src, old) for x in ()]
            sites = relocate.a6_sites(src, old)
            if not refs and not sites and len(data) - 1 <= b - a:  # 가리키는 포인터를 못 찾는 문자열(표 머리 앞 제어 토큰에 묻힌 첫 줄 등) — 제자리에 공백으로 채워 넣는다
                rom[a:b] = data[:-1] + b" " * (b - a - len(data) + 1)
                writes.append((a, b))
                stats["seg_inplace"] += 1
                continue
            if not refs and not sites:
                raise SystemExit(f"구간 {key}: 이 문자열을 가리키는 포인터가 없다 — 제자리({b - a}B)에 넣을 수 있는지 확인한다")
            new = tail.put(data)
            for x in refs:
                rom[x : x + 3] = bytes([new & 0xFF, (new >> 8) & 0xFF, new >> 16])
                writes.append((x, x + 3))
            for lo, hi, bk in sites:
                rom[lo], rom[hi], rom[bk] = new & 0xFF, (new >> 8) & 0xFF, new >> 16
                writes += [(lo, lo + 1), (hi, hi + 1), (bk, bk + 1)]
            stats["seg_reloc"] = stats.get("seg_reloc", 0) + 1
            continue
        if 0xC2 <= (common.off2snes(a) >> 16) <= 0xCB and not v.get("raw"):  # $C2~$CB 대사 — 대사창 규격으로 조판(`raw: true` 면 그대로)
            tw = {**names, **e1w, **call_texts(text, a, seg_map, sg)}
            pv = typeset_end.get(a)  # 바로 앞 구간이 이 자리에서 이어지면(이름 변수 뒤 조각) 그 줄의 남은 폭에서 시작한다
            text = typeset.typeset(text, tw, typeset.end_state(pv[0], pv[1]) if pv else None)
            typeset_end[b] = (text, tw)
        elif (common.off2snes(a) >> 16) in (0xD4, 0xD5) and not v.get("raw"):  # $D4·$D5 전투 문구 — 앞에 오는 이름(변수)의 폭을 가장 긴 이름으로 잡고 어절 단위로 나눈다
            text = battle_typeset(text)
        data = kr.encode(text, alloc)
        if len(data) <= b - a:
            rom[a:b] = data + bytes([NOOP]) * (b - a - len(data))
            stats["seg_inplace"] += 1
        elif b - a == 3 and (common.off2snes(a) >> 16) in LOCAL_FREE:
            # 3바이트 구간: 같은 뱅크 점프(`$0F lo hi`)로 뱅크 안 빈 자리에 둔다
            bank = (common.off2snes(a) >> 16) & 0xFF
            ret = common.off2snes(b) & 0xFFFF
            fa = local.put(bank, data + bytes([0x0F, ret & 0xFF, ret >> 8]))
            rom[a : a + 3] = bytes([0x0F, fa & 0xFF, fa >> 8])
            stats["seg_local"] = stats.get("seg_local", 0) + 1
        else:
            if b - a < 4:
                # 4바이트 미만이라 트램펄린은 못 둔다 — 이 문자열을 즉치 포인터(`lda #lo/hi/bank → $A6~$A8`)로 부르는 자리를 **새 자리로 돌린다**(끝 토큰 `06`/`00` 은 원문에서 가져온다)
                sites = relocate.a6_sites(src, common.off2snes(a))
                if sites and src[b] in (0x00, 0x06):
                    new = far.put(data + bytes([src[b]]))
                    for lo, hi, bk in sites:
                        rom[lo], rom[hi], rom[bk] = new & 0xFF, (new >> 8) & 0xFF, new >> 16
                        writes += [(lo, lo + 1), (hi, hi + 1), (bk, bk + 1)]
                    stats["seg_reloc"] = stats.get("seg_reloc", 0) + 1
                    continue
                raise SystemExit(f"구간 {key}: 원문 {b - a}B 라 트램펄린을 못 둔다 — 번역 {len(data)}B 를 {b - a}B 안으로 줄여야 한다")
            ret = common.off2snes(b)
            fa = far.put(data + bytes([TRAMP, ret & 0xFF, (ret >> 8) & 0xFF, ret >> 16]))
            rom[a : a + 4] = bytes([TRAMP, fa & 0xFF, (fa >> 8) & 0xFF, fa >> 16])
            rom[a + 4 : b] = bytes([NOOP]) * (b - a - 4)
            stats["seg_tramp"] += 1
        writes.append((a, b))

    # 4a. 오프닝 줄 나눔(`opsplit.json`) — 폭이 넘치는 줄을 둘로 나눈다. 둘째 줄은 원판의 빈 줄 문자열(`$D7:xxxx`, 2B)이 있던 자리라 **새 문자열을 두고 포인터 표 항목을 돌린다**
    # (스크립트 `$C1:CD3D` 의 해당 자리 `02`(빈 줄) → 줄 번호 는 patches.py).
    for key, v in sorted(kr.load("opsplit").items()):
        old = int(key.lstrip("$"), 16)
        refs = relocate.refs24(src, old, None)
        if len(refs) != 1:
            raise SystemExit(f"opsplit {key}: 포인터 표 항목이 {len(refs)}곳 — 하나여야 한다")
        new = tail.put(kr.encode(v["kr"], alloc) + b"\x00")
        rom[refs[0] : refs[0] + 3] = bytes([new & 0xFF, (new >> 8) & 0xFF, new >> 16])
        writes.append((refs[0], refs[0] + 3))
        stats["opsplit"] = stats.get("opsplit", 0) + 1

    # 4a'. 인물 소개 쪽 줄 추가(`listsplit.json`) — 쪽 하나가 문자열 포인터 목록(`$D7:xxxx`, 3B씩)과 줄 종류 표(`$C1:xxxx`: 0 첫 줄 · 1 중간 · 2 끝 · FF 끝남)로 돌아간다.
    # 줄을 하나 더하려면 두 표를 **새로 만들어 꼬리에 두고** 그 목록을 읽는 코드의 즉치 3곳(`A9 lo`·`A9 hi`·`A9 bank` → `$63~$65`)과 종류 표 읽는 곳(`BF lo hi bank`)을 돌린다.
    # 포인터는 위 4(대사 구간 이전)가 **이미 고친 rom 의 목록**에서 복사한다 — 원판 목록을 그대로 읽으면 옛 주소가 된다.
    for key, v in sorted(kr.load("listsplit").items()):
        sn = lambda t: common.snes2off(int(t.lstrip("$"), 16))  # noqa: E731
        lst, kinds, after = sn(key), sn(v["kinds"]), v["after"]
        pcode, kcode = sn(v["code_list"]), sn(v["code_kinds"])
        la = int(key.lstrip("$"), 16)
        if bytes(src[pcode + 1 : pcode + 12 : 5]) != bytes([la & 0xFF, (la >> 8) & 0xFF, la >> 16]):
            raise SystemExit(f"listsplit {key}: 목록을 읽는 코드 {v['code_list']} 의 즉치가 다르다")
        ka = int(v["kinds"].lstrip("$"), 16)
        if bytes(src[kcode : kcode + 4]) != bytes([0xBF, ka & 0xFF, (ka >> 8) & 0xFF, ka >> 16]):
            raise SystemExit(f"listsplit {key}: 종류 표를 읽는 코드 {v['code_kinds']} 가 다르다")
        n = 0
        while src[kinds + n] != 0xFF:
            n += 1
        ent = [bytes(rom[lst + 3 * i : lst + 3 * i + 3]) for i in range(n)]
        kd = bytes(src[kinds : kinds + n + 1])
        newstr = tail.put(kr.encode(v["kr"], alloc) + b"\x00")
        ent.insert(after + 1, bytes([newstr & 0xFF, (newstr >> 8) & 0xFF, newstr >> 16]))
        kd = kd[: after + 1] + bytes([1]) + kd[after + 1 :]
        nl, nk = tail.put(b"".join(ent)), tail.put(kd)
        for off, val in ((pcode + 1, nl & 0xFF), (pcode + 6, (nl >> 8) & 0xFF), (pcode + 11, nl >> 16)):
            rom[off] = val
            writes.append((off, off + 1))
        rom[kcode + 1 : kcode + 4] = bytes([nk & 0xFF, (nk >> 8) & 0xFF, nk >> 16])
        writes.append((kcode + 1, kcode + 4))
        stats["listsplit"] = stats.get("listsplit", 0) + 1

    # 4b. 조사 훅 표 — 받침 표(글리프 색인 → 받침 유무) · 조사 쌍(코드) · 숫자(읽는 소리)
    cls = bytearray(8192)
    for c, i in alloc.items():
        if "가" <= c <= "힣":
            cls[i] = 1 if (ord(c) - 0xAC00) % 28 else 0
    for k, (a_, b_) in enumerate(kr.JOSA_PAIRS):
        for j, ch in enumerate((a_, b_)):
            if ch not in alloc:
                alloc_missing = ch
                raise SystemExit(f"조사 글리프 {alloc_missing!r} 가 배정 안 됐다")
    pairs = b"".join(((0x8000 + alloc[a_]).to_bytes(2, "little") + (0x8000 + alloc[b_]).to_bytes(2, "little")) for a_, b_ in kr.JOSA_PAIRS)
    digits = bytes([1, 1, 0, 1, 0, 0, 1, 1, 1, 0])  # 영 일 이 삼 사 오 육 칠 팔 구
    for addr, data in ((patches.JOSA_TABLE, bytes(cls[:2048])), (patches.JOSA_PAIRS, pairs), (patches.JOSA_DIGITS, digits)):
        o = common.snes2off(addr)
        rom[o : o + len(data)] = data
        writes.append((o, o + len(data)))

    # 5. 글꼴 표 — 원본 글리프(1,284자) + 배정한 글자
    import font

    n0 = (common.snes2off(0xD6DC19) - font.FULL_BASE) // font.FULL_STRIDE
    ft = bytearray(src[font.FULL_BASE : font.FULL_BASE + n0 * font.FULL_STRIDE])
    if alloc:
        top = max(alloc.values())
        ft += b"\x00" * ((top + 1 - n0) * 18) if top + 1 > n0 else b""
    for c, i in alloc.items():
        if i >= n0 or font_out:
            ft[i * 18 : (i + 1) * 18] = hangul_font.glyph12(c)
    if font_out and 2 not in alloc.values():
        # 색인 2 = 일본어 「。」 — 「정말 고마워」 조각 뒤처럼 구간 밖 2바이트 코드로 남는 자리가 있어 화면에 그대로 나간다(마스터 규칙: 마침표는 반각 「.」). 모양을 「.」로 바꾼다
        ft[2 * 18 : 3 * 18] = hangul_font.glyph12(".")
    if font_out:
        rom[patches.FONT_OUT : patches.FONT_OUT + len(ft)] = ft
        writes.append((patches.FONT_OUT, patches.FONT_OUT + len(ft)))
        assert patches.FONT_OUT >= common.ROM_SIZE

    fix_checksum(rom)
    stats["glyphs"] = len(alloc)
    stats["alloc"] = alloc
    stats["dropped"] = list(kr.DROPPED)
    stats["reused_jp"] = sum(1 for i in alloc.values() if 0 < i < FIRST_KR)
    return bytes(rom), writes, stats


FIRST_KR = kr.FIRST_FREE
TEXT_BANKS = set(range(0x00, 0x0C)) | {0x14, 0x15, 0x17}  # 파일 뱅크 번호 = $C0~$CB · $D4 · $D5 · $D7


def _jp_kept(src: bytes, rom: bytes, dead: list) -> set[int]:
    """번역 뒤에도 롬에 남아 읽히는 일본어 글리프 색인 — 원문 글자 덩이(최소 2자) 가운데 바뀌지 않았고 옮겨 간 구간도 아닌 자리의 코드.
    ⚠ 보수적이다: 코드 곁 우연한 덩이도 남은 것으로 센다(자리를 덜 재활용할 뿐 깨지진 않는다)."""
    import scan_text

    merged: list[list[int]] = []
    for x, y in sorted(dead):
        if merged and x <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], y)
        else:
            merged.append([x, y])
    starts = [m[0] for m in merged]
    import bisect

    def is_dead(p: int) -> bool:
        k = bisect.bisect_right(starts, p) - 1
        return k >= 0 and p < merged[k][1]

    kept = set()
    for a, b, _c in scan_text.find_runs(src, 3):
        if (a >> 16) not in TEXT_BANKS:  # 그래픽·표 뱅크($CC~$D3 · $D6)의 우연한 덩이는 글자가 아니다 — 세면 자리를 거의 못 푼다
            continue
        i = a
        while i < b:
            if 0x80 <= src[i] <= 0x85:
                if rom[i : i + 2] == src[i : i + 2] and not is_dead(i):
                    kept.add(((src[i] - 0x80) << 8) | src[i + 1])
                i += 2
            else:
                i += 1
    return kept


def _protected() -> set[int]:
    """코드가 색인으로 직접 부르는 글자(숫자·기호 등 가나·한자가 아닌 것)는 재활용하지 않는다."""
    import glyphmap

    out = {0}
    for i, ch in enumerate(glyphmap.TABLE):
        o = ord(ch)
        if not (0x3041 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF):
            out.add(i)
    return out


def build() -> tuple[bytes, list, dict]:
    """두 번 돈다 — ① 한글 글리프를 무제한 가상 색인에 놓아 보고, 번역 뒤에도 남는 일본어 글리프를 센다(census) ② 안 남는 일본어 자리를 한글에 재활용해 실제로 굽는다."""
    src = common.rom_bytes()
    dead: list = []
    rom1, _w, _s = _build(range(kr.FIRST_FREE, kr.FIRST_FREE + 6000), dead, font_out=False)
    keep = _jp_kept(src, rom1, dead) | _protected()
    free = [i for i in range(1, kr.FIRST_FREE) if i not in keep] + list(range(kr.FIRST_FREE, kr.LAST_SLOT + 1))
    return _build(free, [], True, lenient=True)


def check_immutable(rom: bytes, writes: list) -> None:
    src = common.rom_bytes()
    bad = []
    for a, b in IMMUTABLE:
        for i in range(a, b):
            if rom[i] != src[i] and not any(x <= i < y for x, y in EXCEPT + writes):
                bad.append(i)
                if len(bad) >= 8:
                    break
    if bad:
        raise SystemExit("무변경 구간이 바뀌었다: " + ", ".join(common.fmt(common.off2snes(i)) for i in bad))
    if len(rom) != NEW_SIZE:
        raise SystemExit(f"크기 {len(rom):,}B (기대 {NEW_SIZE:,}B)")
    s = sum(rom[:CHK_OFF] + b"\x00\x00\xff\xff" + rom[CHK_OFF + 4 :]) & 0xFFFF
    got = int.from_bytes(rom[CHK_OFF + 2 : CHK_OFF + 4], "little")
    cmpl = int.from_bytes(rom[CHK_OFF : CHK_OFF + 2], "little")
    if got != s or cmpl != s ^ 0xFFFF:
        raise SystemExit("헤더 체크섬이 안 맞는다")


def screen_gate(strict: bool, stats: dict) -> None:
    """번역 안 된 대사 구간 수 — 번역이 끝나면 0 이어야 한다(`--strict`)."""
    src = common.rom_bytes()
    total = len(segs.segments(src))
    keep = set(kr.load("keep").get("ids", []))
    total -= len(keep)
    done = stats["seg_inplace"] + stats["seg_tramp"] + stats.get("seg_local", 0) + stats.get("seg_reloc", 0)
    print(f"  화면 일본어 게이트: 대사 구간 번역 {done:,}/{total:,} · 사전 {stats['dict']} · UI 창 {stats['ui_inplace'] + stats['ui_moved']} · 칸 {stats.get('cells', 0)} · 문자열 {stats.get('spans', 0)} · 레코드 {stats.get('records', 0)} · 몬스터군 {stats.get('monsters', 0)} · 표 {stats.get('ptrs16', 0)} · 글리프 {stats['glyphs']}")
    if stats.get("missing"):
        print(f"  ⚠ 정본에 없어 원문으로 남긴 이름 {len(stats['missing'])}개(관리자에게 후보로): " + ", ".join(f"{k}[{i}]{n}" for k, i, n in stats["missing"][:12]))
    unreach = kr.load("unreachable")
    if unreach.get("ranges"):
        print(f"  ⚠ 일반 플레이로 도달 불가(근거 textmap/unreachable.json)라 원문으로 둔 문자열 {len(unreach['ranges'])}곳: " + ", ".join(f"{r['a']}+{r['n']}B({r['note']})" for r in unreach["ranges"]))
    if stats.get("toolong"):
        print("  ⚠ 레코드 칸보다 길어 원문으로 남긴 이름: " + ", ".join(f"{k}[{i}]{t}({n}B>{m}B)" for k, i, t, n, m in stats["toolong"]))
    if stats.get("dropped"):
        print(f"  ⚠ 글리프 색인이 모자라 못 넣은 글자 {len(stats['dropped'])}개(번역이 끝나면 일본어 자리가 풀린다): " + "".join(stats["dropped"][:60]))
        if strict:
            raise SystemExit("글리프 모자람")
    if strict and done < total:
        raise SystemExit(f"일본어가 남았다: {total - done:,}개 구간")


# 번역 대상이 아닌 「글자처럼 읽히는 데이터」 — 그래픽·표·AI 데이터 잡음(SNES 시작, 끝 미포함). 새로 걸리면 **눈으로 보고** 여기 더하거나 번역한다.
JUNK_RUNS = (
    (0xC081EE, 0xC08213), (0xC08B71, 0xC08B8D), (0xC0C9CA, 0xC0C9E6), (0xC0ECAE, 0xC0ECC9),  # $C0 표 잡음
    (0xCCF9A2, 0xCCF9FD), (0xCDE7DC, 0xCDEA83), (0xD30965, 0xD30986),  # 그래픽·표 데이터
    (0xD48059, 0xD48081), (0xD48175, 0xD4819D),  # 몬스터 AI 데이터 안 잡음
)
# $D4·$D5 런에서 구간을 뺀 남은 조각 중 **글자가 아닌 것**(눈으로 확인) — 시작 SNES 주소
JUNK_PIECES = {
    0xD4122D,  # 숫자 표 + 코드(`育吉勉` 꼴 잡음)
    0xD47EB6, 0xD47EBE, 0xD47EC6, 0xD47ECE,  # 코드 곁 `「」リ` 꼴 잡음
    0xC103CD, 0xCB42BD,  # 표·그래픽 잡음(디코드하면 `ぴぴぶまオト` 꼴)
}
# 일본어이긴 한데 **쓰이는지 못 찾은** 조각 — 실패로 치지 않고 매 빌드 경고로 남긴다(호출처를 찾으면 구간으로 올리거나 JUNK 로 내린다)
PENDING_PIECES = {
    0xCB3869,  # `$E1` 사전 항목 0 `Gold になるけど` — 번역문이 `<E1:0>` 을 안 쓴다(메시지 목표 게이트가 사전 참조로 실측)
    0xCB393E,  # `$E1` 항목 10·11 `だな。`·`だね。` — 원문 참조 61곳은 번역문에서 어미로 풀어 써서 참조가 사라졌다
}


def residual_jp_gate(src: bytes, rom: bytes, strict: bool) -> None:
    """**롬 전체** 일본어 잔존 게이트 — 번역 분모(`segs.segments`)가 놓친 문안을 잡는다.
    원문에서 가나·한자 12자↑ 런을 찾아, 최종 롬에서 바이트가 그대로이고 **번역 대상으로 알려진 자리**(구간·EXCLUDE·도달 불가·잡음 표) 밖이면 실패.
    (10-18: 두 종 등장 첫 메시지 둘이 `_clean` 에 걷혀 분모 밖에서 화면 일본어로 나왔다 — 분모 안만 세는 게이트로는 안 잡혔다.)"""
    known = [(a, b) for a, b in segs.segments(src)]
    for a, b in segs.EXCLUDE + JUNK_RUNS:
        known.append((common.snes2off(a), common.snes2off(b)))
    for r in kr.load("unreachable").get("ranges", []):
        a = common.snes2off(int(r["a"].lstrip("$"), 16))
        known.append((a, a + r["n"]))
    bad = []
    for s, e, n in scan_text.find_runs(src, 12):
        if rom[s:e] == src[s:e] and not any(s < b and a < e for a, b in known):
            bad.append((s, e, n))
    # 문장 뱅크($C1~$CB 대사·메시지, $D4·$D5 전투 AI) — 런이 알려진 구간과 **겹치기만** 해도 통과시키면 구간 앞쪽 이름 박힌 문장(「…が現れた。」)이 통째로 샌다
    # (10-18 메탈스팀 군 화면 일본어). 그래서 런에서 알려진 자리를 **뺀 나머지 조각**을 본다 — 짧은 문장도 잡도록 최소 5자(10B)·가나 3자.
    # 잡음 실측(10-18): 이 조건에서 걸린 건 $C1·$CB 의 표·그래픽 둘 + 아래 PENDING 둘뿐이다($CC~ 는 그래픽 뱅크라 보지 않는다).
    kn = sorted(known)
    pending = []
    for s, e, n in scan_text.find_runs(src, 3):
        bank = common.off2snes(s) >> 16
        if not (0xC1 <= bank <= 0xCB or bank in (0xD4, 0xD5)):
            continue
        cur, pieces = s, []
        for a, b in kn:
            if b <= cur or a >= e:
                continue
            if a > cur:
                pieces.append((cur, a))
            cur = max(cur, b)
        if cur < e:
            pieces.append((cur, e))
        for ps, pe in pieces:
            sn = common.off2snes(ps)
            if pe - ps < 10 or rom[ps:pe] != src[ps:pe] or sn in JUNK_PIECES:
                continue
            if len(re.findall(r"[ぁ-ヿ]", segs.notation(src, ps, pe))) < 3:
                continue
            (pending if sn in PENDING_PIECES else bad).append((ps, pe, (pe - ps) // 2))
    if pending:
        print("  ⚠ 호출처 미확인 일본어 조각 " + ", ".join(f"${common.off2snes(s):06X}+{e - s}B" for s, e, _n in pending) + " — 전수 검수 때 화면으로 본다")
    if bad:
        print(f"  ⚠ 번역 분모 밖 일본어 런 {len(bad)}곳: " + ", ".join(f"${common.off2snes(s):06X}+{e - s}B({n}자)" for s, e, n in bad[:12]))
        if strict:
            raise SystemExit("분모 밖 일본어 런 — 구간 목록(segs.EXTRA)에 더하거나 build.JUNK_RUNS 에 근거와 함께 올린다")


# 메시지 목표 게이트의 잡음 — `$A6` 즉치 패턴에 걸렸지만 코드·그래픽을 글자로 잘못 읽은 자리(디코드하면 `？ツ` 꼴), 눈으로 확인
POINTER_NOISE = {0xC12E04, 0xC13B15}


def message_targets(src: bytes) -> dict[str, set[int]]:
    """대사 출력기가 **들어가는 자리**(파일 오프셋) 전부, 출처별로 — ① 코드가 `$A6~$A8` 에 즉치로 넣는 포인터 ② 대사 단위 안의 점프·호출(`$0F`·`$10`) 목표.
    (둘 다 구간 목록이 훑는 곳 밖을 가리킬 수 있다 — sfc-ed1 에서 포인터 표가 목록 밖을 가리켜 장면 대사 101개가 일본어로 남았다.)"""
    a6 = {common.snes2off(p) for p in script.a6_targets(src) if p not in POINTER_NOISE}
    jmp = set()
    for s, e in script.all_units(src):
        bank = (common.off2snes(s) >> 16) & 0xFF
        if not (0xC0 <= bank <= 0xCC or bank == 0xD7):  # 그래픽·코드 뱅크($CD~$D6)의 가짜 점프는 보지 않는다(실측 13곳 전부 잡음)
            continue
        for o, _ln in script.tokens(src, s, e):
            if src[o] in (0x0F, 0x10) and o + 2 < len(src):
                jmp.add(common.snes2off((bank << 16) | src[o + 1] | src[o + 2] << 8))
    return {"a6": a6, "jump": jmp}


def pointer_target_gate(src: bytes, rom: bytes, strict: bool) -> None:
    """**메시지 목표 게이트** — 메시지가 시작하는 자리 전부(`message_targets`)가 번역 단위(`segs.segments`·EXCLUDE·도달 불가 표) 안인가.
    목표에서 첫 글자 토큰을 찾아(앞의 제어 토큰은 건너뜀) 그 자리가 단위 밖이고 롬에서도 안 바뀌었으면 실패. 더해, 번역문이 쓰는 사전 참조(`<E1:n>`)의 항목이 번역됐는지도 본다."""
    import bisect

    S = segs.segments(src)
    starts = [a for a, _b in S]
    ends = [b for _a, b in S]
    unreach = [(common.snes2off(int(r["a"].lstrip("$"), 16)), common.snes2off(int(r["a"].lstrip("$"), 16)) + r["n"]) for r in kr.load("unreachable").get("ranges", [])]

    def covered(o: int) -> bool:
        i = bisect.bisect_right(starts, o) - 1
        return (i >= 0 and starts[i] <= o < ends[i]) or segs.excluded(o) or any(a <= o < b for a, b in unreach)

    def first_char(o: int) -> int | None:
        for t, ln in script.tokens(src, o, o + 300):
            b = src[t]
            if 0x80 <= b < 0x88 or 0x88 <= b < 0xE0 or 0xE2 <= b < 0xF0:
                return t
            if b in script.ENDS:
                return None
        return None

    tg = message_targets(src)
    bad, n_char = [], 0
    for kind, offs in tg.items():
        for o in sorted(offs):
            t = first_char(o)
            if t is None:
                continue
            n_char += 1
            if not covered(t) and rom[t : t + 2] == src[t : t + 2]:
                bad.append((kind, o))
    # 사전 참조 — 번역문이 가리키는 `$E1` 항목이 일본어 그대로면 화면에 샌다
    used = {int(m.group(1)) for v in kr.load("segments").values() for m in re.finditer(r"<E1:(\d+)>", v["kr"])}
    used = {n for n in used if n < script.DICTS[1][1]}  # 사전 항목 수(30) 밖 `<E1:n>` 은 앞머리 잡음 토큰(예: `$C850DB` 앞의 `<E1:80>`) — 사전 참조가 아니다
    base = common.snes2off(script.DICTS_BY_NAME["E1"])
    for n in sorted(used):
        p = base + 3 * n
        o = common.snes2off(src[p] | src[p + 1] << 8 | src[p + 2] << 16)
        t = first_char(o)
        if t is not None and rom[p : p + 3] == src[p : p + 3] and rom[t : t + 2] == src[t : t + 2]:
            bad.append((f"E1:{n}", o))
    print(f"  메시지 목표 {sum(len(v) for v in tg.values()):,}(즉치 {len(tg['a6']):,} · 점프 {len(tg['jump']):,}) 중 글자 든 {n_char:,} · 목록 밖 {len(bad)}")
    if bad:
        print("  ⚠ 번역 단위 밖 메시지 목표: " + ", ".join(f"{k}→${common.off2snes(o):06X}" for k, o in bad[:12]))
        if strict:
            raise SystemExit("메시지 목표가 번역 단위 밖 — segs.EXTRA 에 더하거나(글자면) build.POINTER_NOISE 에 근거와 함께")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--twice", action="store_true", help="두 번 만들어 sha1 대조(결정성)")
    ap.add_argument("--strict", action="store_true", help="(기본값 — 옛 호출 호환)")
    ap.add_argument("--lenient", action="store_true", help="번역 중간 상태 시험용 — 일본어·글리프 모자람을 실패로 안 친다")
    a = ap.parse_args()
    a.strict = not a.lenient
    common.verify_originals()
    if os.environ.get("ED_DEBUG") == "1" and not (common.BUILD_TAG.startswith("test-") or common.BUILD_TAG == "debug"):  # 제품 칸을 지우기 전에 막는다
        raise SystemExit("ED_DEBUG=1 은 꼬리표 test-* 또는 debug(마스터용)에서만 — ED_BUILD_TAG=debug 를 준다")
    # 디버그 롬은 파일명을 달리한다 — 에뮬 세이브(.srm)가 롬 이름으로 갈려서, 같은 이름이면 제품 세이브에 매직 코드 아이템이 섞인다
    name = OUT_NAME.replace(".sfc", " (DEBUG).sfc") if os.environ.get("ED_DEBUG") == "1" else OUT_NAME
    out = common.BUILD_DIR / common.BUILD_TAG / name
    out.parent.mkdir(parents=True, exist_ok=True)
    failed = out.with_name(out.name + ".failed")
    for p in (out, failed):
        p.unlink(missing_ok=True)
    rom = b""
    try:
        rom, writes, stats = build()
        if a.twice and common.sha1_of(build()[0]) != common.sha1_of(rom):
            raise SystemExit("비결정적 — 같은 입력에서 sha1 이 갈렸다")
        check_immutable(rom, writes)
        screen_gate(a.strict, stats)
        residual_jp_gate(common.rom_bytes(), rom, a.strict)
        pointer_target_gate(common.rom_bytes(), rom, a.strict)
        if os.environ.get("ED_DEBUG") == "1":  # 시험 빌드 전용 — 제품 롬(스위치 없음)은 바이트 하나도 안 바뀐다
            import debug_patch

            r = bytearray(debug_patch.apply(rom))
            fix_checksum(r)
            rom = bytes(r)
            print("  ⚠ ED_DEBUG=1 — 디버그 입력 훅이 든 시험 롬이다(배포·제품 아님)")
    except BaseException:
        failed.write_bytes(rom)
        raise
    out.write_bytes(rom)
    print(f"{out.name}  {len(rom):,}B  sha1={common.sha1_of(rom)}")


if __name__ == "__main__":
    main()
