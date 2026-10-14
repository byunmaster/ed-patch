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
                    newtab[-16:] = b"\x80\x00" * (pad // 2) + data + (b" " if pad % 2 else b"") + b"\x06\x00"
                stats["records"] = stats.get("records", 0) + 1
                continue
            pad = st - len(data)
            # 왼쪽은 전각 공백 쌍만 둔다(출력기가 앞쪽 `80 00` 쌍을 건너뛰어 왼쪽 정렬로 보인다). 홀수 한 바이트는 **뒤**에 둔다 —
            # 앞에 두면 쌍 건너뛰기가 거기서 멈춰 이름이 반각 한 칸 밀린다(「천 옷」)
            left = b"\x80\x00" * (pad // 2)
            rom[a : a + st] = left + data + (b" " if pad % 2 else b"")
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
        if len(data) > n:
            raise SystemExit(f"문자열 {key}: 번역 {len(data)}B > 원문 {n}B — 줄이거나 이전(relocate)해야 한다")
        rom[a : a + n] = data + bytes([NOOP]) * (n - len(data))
        writes.append((a, a + n))
        stats["spans"] = stats.get("spans", 0) + 1

    # 4. 대사 구간 — 짧으면 제자리, 길면 트램펄린
    sg = {segs.seg_id(a): (a, b) for a, b in segs.segments(src)}
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
            text = typeset.typeset(text, names)
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--twice", action="store_true", help="두 번 만들어 sha1 대조(결정성)")
    ap.add_argument("--strict", action="store_true", help="(기본값 — 옛 호출 호환)")
    ap.add_argument("--lenient", action="store_true", help="번역 중간 상태 시험용 — 일본어·글리프 모자람을 실패로 안 친다")
    a = ap.parse_args()
    a.strict = not a.lenient
    common.verify_originals()
    out = common.BUILD_DIR / common.BUILD_TAG / OUT_NAME
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
    except BaseException:
        failed.write_bytes(rom)
        raise
    out.write_bytes(rom)
    print(f"{out.name}  {len(rom):,}B  sha1={common.sha1_of(rom)}")


if __name__ == "__main__":
    main()
