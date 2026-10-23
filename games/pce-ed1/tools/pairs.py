#!/usr/bin/env python3
"""원판·한글 짝 표 — 두 이미지(원판 · 지금 HEAD 제품)에서 **번호(포인터)마다 실제 바이트를 디코드**해 나란히 놓는다
(마스터 10-20 「전체 대사를 원문 칸에 올바른 번역이 왔는가」). 촬영 없음 — 대본 JSON 이 아니라 **구운 이미지의 바이트**를 읽는다.

    python3 tools/pairs.py [--iso <제품 이미지>] [--out <폴더>]   # → pairs.tsv · manifest.md

번호 꼴: `rel:씬:시작`(씬 블록이 든 컨테이너 rel · 씬 번호 · 메시지 시작 주소 16진) — 원판 메시지 시작 주소는 번역본 블록에서도 그대로다
(`messages.splice` 는 제자리에 쓰고 넘치는 꼬리만 끝에 붙이고 `0F` 로 잇는다 → 그 점프는 따라가서 읽는다).
표기: ⏎ 쪽 넘김(`03`/`05`) · ↵ 줄바꿈(`01`) · `{S:이름}` 화자(`1F … 04`) · `{공용 nn}`(`09 nn`) · `{josa 은/는}` 동적 조사 ·
그 밖 옵코드는 `{HH 인자…}` 그대로 펼친다(`0F`·`10`·`11`~`15` 분기·호출 포함 — 이름·수 자리도 여기 든다).
표시: 원판만(한글 쪽이 빔) · 한글만(원판 쪽이 빔) · 둘 다 빔 · 포인터 공유(원판에서 둘↑ 참조가 같은 메시지를 가리킨다) · 비움.
한글 글자는 **제품 이미지의 글리프 비트맵을 글자로 되읽는다**(상주 뱅크 = 이미지 섹터, 동적 칸 = 블록 꼬리 스텁이 복사할 자료) —
글리프 순서 파일이 아니라 비트맵이 진실이다. ⚠ 한계는 manifest.md 에 적는다.
"""

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "shared"))
import common
import containers
import font
import glyphdyn
import messages as M
import translate

BANK_SECTORS = font.GLYPH_NBANKS * 0x2000 // common.USER
JOSA = font.JOSA_PAIRS
OPEN_LEN = {**M.TEXT_OPS, **M.OTHER_OPS}  # 옵코드 → 바이트 길이(옵코드 포함)


def iso_track(iso: Path) -> bytes:
    """제품 이미지의 데이터 트랙(트랙 2) 유저 데이터 — `common.track_data()` 와 같은 꼴."""
    n = len(common.track_data())  # 원판 트랙 길이(섹터 수 × 2048) — 제품도 같은 자리·길이
    out = bytearray()
    with open(iso, "rb") as f:
        for rel in range(n // common.USER):
            f.seek((common.T2_SECTOR + rel) * common.RAW + common.USER_OFF)
            out += f.read(common.USER)
    return bytes(out)


class Glyphs:
    """비트맵 → 글자 되읽기. 상주 뱅크는 이미지에서, 동적 칸은 블록 스텁 시뮬레이션에서 읽는다."""

    def __init__(self, iso: Path):
        bank = b""
        with open(iso, "rb") as f:
            for s in range(BANK_SECTORS):
                f.seek((common.T2_SECTOR + 114 + s) * common.RAW + common.USER_OFF)
                bank += f.read(common.USER)
        self.bank = bank
        order = json.load(open(HERE.parent / "script" / "glyph_order.json", encoding="utf-8"))["order"]
        self.rev: dict[bytes, str] = {}
        cands = list(order)
        for sid in glyphdyn.body_scene_ids():  # 동적 글자 후보(비트맵 조회용 — 식별은 비트맵으로 한다)
            cands += sorted(translate.body_chars(sid))
        for ch in dict.fromkeys(cands):
            try:
                g = font.glyph(ch)
            except (KeyError, ValueError):
                continue
            if any(g) and (g not in self.rev or 0xE000 <= ord(self.rev[g]) <= 0xF8FF):
                self.rev[g] = ch
        self.static: dict[int, str] = {}
        for i in range(font.DYN0):
            at = font.glyph_at(i)
            g = font.unpack(bank[at : at + font.PACKED_BYTES])
            self.static[i] = self.rev.get(g, f"[글리프{i}]")

    def dyn_of(self, block: bytes, orig_len: int) -> dict[int, str]:
        """블록 꼬리 스텁이 동적 칸에 복사하는 비트맵 → {칸 번호: 글자}. 스텁이 없으면(머리 점프가 덧붙인 꼬리를 안 가리키면) 빈 표."""
        if block[0] not in glyphdyn.HEAD_OPS or (block[1] | block[2] << 8) - M.BASE < orig_len:
            return {}
        try:
            win, _h, _r, _pc, _sp = glyphdyn.simulate(block)
        except Exception:
            return {}
        base = font.glyph_at(font.DYN0) % glyphdyn.BANK
        out = {}
        for k in range(font.DYN_SLOTS):
            g = font.unpack(bytes(win[base + k * font.PACKED_BYTES : base + (k + 1) * font.PACKED_BYTES]))
            if any(g):
                out[font.DYN0 + k] = self.rev.get(g, f"[동적{k}]")
        return out


def decode(block: bytes, start: int, *, ko: bool, orig_len: int, gl: Glyphs | None, dyn: dict[int, str], terms=M.TERM, base: int = M.BASE) -> tuple[str, int]:
    """`start`(블록 안 오프셋)에서 메시지 하나를 문자열로. 돌려주는 값 = (문자열, 읽은 바이트 수 — 점프 따라간 건 안 센다).

    한글 쪽(`ko`)은 **원판 길이 밖(덧붙인 꼬리)을 가리키는 `0F`** 만 따라간다 — 번역이 넘쳐서 이은 자리다. 원판에 원래 있던 점프는 `{0F …}` 로 적는다.
    """
    out: list[str] = []
    i = start
    n = len(block)
    spk = False
    steps = 0
    while i < n and steps < 4000:
        steps += 1
        b = block[i]
        if b >= 0x24:  # 두 바이트 글자
            if i + 1 >= n:
                out.append("[끝]")
                break
            if ko and gl is not None and 0xF0 <= b < 0xF8:
                trail = block[i + 1]
                lead = b
                plus = False
                if lead >= font.VARIANT_LEAD0:
                    lead -= font.VARIANT_LEAD0 - font.LEAD0
                    plus = True
                idx = (lead - font.LEAD0) * font.PER_LEAD + (trail - font.TRAIL0)
                ch = gl.static.get(idx) or dyn.get(idx) or f"[코드{b:02X}{trail:02X}]"
                out.append(ch + (" " if plus else ""))
            elif ko and b == 0xF8 and block[i + 1] == 0x24:
                out.append(" ")
            elif ko and b == font.JOSA_LEAD:
                k = block[i + 1] - font.TRAIL0
                out.append("{josa %s}" % (JOSA[k] if 0 <= k < len(JOSA) else f"?{block[i + 1]:02X}"))
            else:
                try:
                    out.append(block[i : i + 2].decode("cp932"))
                except UnicodeDecodeError:
                    out.append(f"[{block[i]:02X}{block[i + 1]:02X}]")
            i += 2
            continue
        if b in terms:
            if spk:
                out.append("}")
            return "".join(out), i + 1 - start
        if b == 0x1F:
            out.append("{S:")
            spk = True
            i += 1
            continue
        if b == 0x04 and spk:
            out.append("}")
            spk = False
            i += 1
            continue
        if b == 0x01:
            out.append("↵")
            i += 1
            continue
        if b in (0x03, 0x05):
            out.append("⏎")
            i += 1
            continue
        if b == 0x09 and i + 1 < n:
            out.append("{공용 %d}" % block[i + 1])
            i += 2
            continue
        if b == M.JUMP and i + 2 < n:
            tgt = (block[i + 1] | block[i + 2] << 8) - base
            if ko and tgt >= orig_len:  # 번역이 넘쳐 덧붙인 꼬리로 잇는 점프 — 따라간다
                i = tgt
                continue
            out.append("{0F %04X}" % (tgt + base))
            i += 3
            break  # 무조건 점프 — 메시지는 여기서 끝난다(뒤 바이트는 다른 메시지·코드라 읽으면 다음 메시지로 이어 읽힌다)
        ln = OPEN_LEN.get(b, 1)
        args = " ".join(f"{x:02X}" for x in block[i + 1 : i + ln])
        out.append("{%02X%s}" % (b, " " + args if args else ""))
        i += ln
        if b not in M.TEXT_OPS:  # 🔴 텍스트 밖 옵코드(`02` `0D` `10`~`15` `16` `17` `21` `23` …)는 메시지 끝이다 — `messages.parse` 와 같은 규칙. 넘어서 읽으면 뒤 코드·다음 조각이 이어 읽힌다
            break
    return "".join(out), i - start


def _glyph_ch(b0: int, b1: int, gl: Glyphs, dyn: dict[int, str]) -> str | None:
    if not 0xF0 <= b0 < 0xF8:
        return None
    plus = b0 >= font.VARIANT_LEAD0
    lead = b0 - (font.VARIANT_LEAD0 - font.LEAD0) if plus else b0
    idx = (lead - font.LEAD0) * font.PER_LEAD + (b1 - font.TRAIL0)
    return (gl.static.get(idx) or dyn.get(idx) or f"[코드{b0:02X}{b1:02X}]") + (" " if plus else "")


def dec_plain(buf: bytes, ko: bool, gl: Glyphs, pads=(b" ",)) -> str:
    """고정폭 칸 하나(이름·지명·라벨) → 문자열. 앞뒤 패딩(0x20 · 전각 공백 `81 40`)은 뗀다. `06`·`00` 에서 끝. 옵코드는 `{HH}`."""
    out = []
    i = 0
    n = len(buf)
    while i < n:
        b = buf[i]
        if b in (0x00, 0x06):
            break
        if b == 0x20:
            out.append(" ")
            i += 1
            continue
        if b >= 0x24 and i + 1 < n:
            g = _glyph_ch(b, buf[i + 1], gl, {}) if ko else None
            if g is None and ko and b == 0xF8 and buf[i + 1] == 0x24:
                g = " "
            if g is None:
                try:
                    g = buf[i : i + 2].decode("cp932")
                except UnicodeDecodeError:
                    g = f"[{b:02X}{buf[i + 1]:02X}]"
            out.append(g)
            i += 2
            continue
        out.append("{%02X}" % b)
        i += 1
    t = "".join(out)
    return t.strip(" ").strip("\u3000")


def sys_rows(orig_track: bytes, ko_track: bytes, gl: Glyphs) -> list[tuple]:
    """시스템 문구 — 본 프로그램(뱅크 0x68~) 고정 문자열 가족. 한글 쪽은 **같은 뱅크 오프셋**을 읽는다(재삽입이 주소를 안 옮긴다)."""
    import sysstrings as SS

    MAIN = SS.MAIN_REL

    def bank(track, bk):
        o = (MAIN + (bk - 0x68) * 4) * common.USER
        return track[o : o + 4 * common.USER]

    rows = []

    def add(num, jp, kr, memo=""):
        ink = lambda x: "".join(c for c in x if not c.isspace() and c not in "↵⏎")  # noqa: E731
        mark = "" if ink(jp) and ink(kr) else ("둘 다 빔" if not ink(jp) and not ink(kr) else ("원판만" if ink(jp) else "한글만"))
        rows.append((num, jp, kr, mark, memo))

    for fam, (bk, base, stride, w, n, pad, _tail) in SS.FIXED.items():
        bo, bk_ = bank(orig_track, bk), bank(ko_track, bk)
        for k in range(n):
            a = base + k * stride
            add(f"S:{fam}:{k}", dec_plain(bo[a : a + w], False, gl), dec_plain(bk_[a : a + w], True, gl))
    bo, bk_ = bank(orig_track, 0x74), bank(ko_track, 0x74)
    for k in range(4):
        a = 0x330 + k * 64
        add(f"S:speakers:{k}", dec_plain(bo[a : a + 16], False, gl), dec_plain(bk_[a : a + 16], True, gl))
    ch = SS.read_chapter()[0]
    ln = len(bytes.fromhex(ch["raw"]))
    add("S:chapter:0", dec_plain(bo[0x198 : 0x198 + ln], False, gl), dec_plain(bk_[0x198 : 0x198 + ln], True, gl))
    bo, bk_ = bank(orig_track, 0x6D), bank(ko_track, 0x6D)
    for u in SS.read_labels():
        a, r = u["off"], u["room"]
        add(f"S:labels:{a:04X}", decode(bo[a : a + r] + b"\0", 0, ko=False, orig_len=r, gl=None, dyn={}, terms={0})[0],
            decode(bk_[a : a + r] + b"\0", 0, ko=True, orig_len=r, gl=gl, dyn={}, terms={0})[0])
    for u in SS.read_sysmsg():
        a, r = u["off"], u["room"]
        so = bo[a : a + r].rstrip(b"\xff").rstrip(b"\0")
        sk = bk_[a : a + r].rstrip(b"\xff").rstrip(b"\0")
        add(f"S:sysmsg:{a:04X}", decode(so + b"\0", 0, ko=False, orig_len=r, gl=None, dyn={}, terms={0})[0],
            decode(sk + b"\0", 0, ko=True, orig_len=r, gl=gl, dyn={}, terms={0})[0])
    for sc in SS.read_screens():
        bo, bk_ = bank(orig_track, sc["bank"]), bank(ko_track, sc["bank"])
        io = ik = sc["off"]
        for li, ln_ in enumerate(sc["lines"]):
            jo = bo.index(0, io + 2)
            jk = bk_.index(0, ik + 2)
            add(f"S:screens:{sc['key']}:{li}", f"({bo[io]},{bo[io + 1]})" + dec_plain(bo[io + 2 : jo], False, gl),
                f"({bk_[ik]},{bk_[ik + 1]})" + dec_plain(bk_[ik + 2 : jk], True, gl))
            io, ik = jo + 1, jk + 1
    for u in SS.read_inline():
        bo, bk_ = bank(orig_track, u["bank"]), bank(ko_track, u["bank"])
        a, r = u["off"], u["room"]
        add(f"S:inline:{u['key']}", dec_plain(bo[a : a + r], False, gl), dec_plain(bk_[a : a + r], True, gl))
    rows += omake_rows(orig_track, ko_track)
    return rows


def omake_rows(orig_track: bytes, ko_track: bytes) -> list[tuple]:
    """오마케 모듈(사운드 테스트 목록 · 메뉴 · 몬스터 도감 88건). 한글 글자는 **전용 칸 글리프 블록**(rel 466~, 12px 칸 비트맵 — 글자 단위가 아니라
    글자를 이어 붙인 **픽셀 조각**)이라 글자로 되읽을 수 없다. 그래서 **후보 문구(우리 번역 정본)를 같은 방식으로 칸 비트맵으로 구워 롬의 칸 비트맵 열과 대조**한다:
    롬의 줄이 후보와 한 칸도 안 틀리고 같으면 그 문구로 적고(메모 `롬 칸 비트맵 일치`), 못 찾으면 `[칸 n개 미확인]`. 즉 글자 판독이 아니라 **롬 바이트가 정본 문구와 같음의 확인**이다."""
    import omake_font as OF
    import sysstrings as SS

    blk = ko_track[OF.GLYPH_REL * common.USER : (OF.GLYPH_REL + OF.GLYPH_SECTORS) * common.USER]

    def sig_bytes(b: bytes, cell_of) -> tuple:
        out, i = [], 0
        while i < len(b):
            c = b[i]
            if 0xF0 <= c < 0xF8 and i + 1 < len(b):
                out.append(cell_of((c - 0xF0) * font.PER_LEAD + (b[i + 1] - font.TRAIL0)))
                i += 2
            elif c >= 0x24 and i + 1 < len(b):
                out.append(bytes(b[i : i + 2]))
                i += 2
            else:
                out.append(bytes([c]))
                i += 1
        return tuple(out)

    cands = set()
    extras = json.load(open(HERE.parent / "script" / "sys" / "extras.json", encoding="utf-8"))
    for k, v in extras.items():
        if not k.startswith("_") and isinstance(v, list):
            cands.update(v)
    dexj = json.load(open(HERE.parent / "script" / "sys" / "dex.json", encoding="utf-8"))["desc"]
    cands.update(OF.dex_names())
    for n, t in enumerate(dexj):
        cands.update(OF.dex_lines(n, t))
    rev = {}
    sigs: dict[tuple, str] = {}
    for t in sorted(cands):
        enc = OF.encode_item(t)
        if not rev:
            pass
        sigs_t = enc
        sigs[("raw", enc)] = t  # 같은 코드열도 같은 문구(같은 프로세스에서 같은 칸 번호)
    inv = {idx: g for g, idx in OF._CELLS.items()}  # 칸 번호 → 후보 칸 비트맵
    by_sig = {sig_bytes(enc, lambda ix: inv[ix]): t for (_k, enc), t in sigs.items()}

    def kr_text(seg: bytes) -> tuple[str, bool]:
        if not seg:
            return "", True
        sg = sig_bytes(seg, lambda ix: bytes(blk[ix * OF.STRIDE : ix * OF.STRIDE + font.GLYPH_BYTES]))
        t = by_sig.get(sg)
        if t is not None:
            return t, True
        if all(len(x) == 2 and x[0] >= 0x81 and x[0] < 0xF0 or len(x) == 1 and x[0] < 0x24 for x in sg if isinstance(x, bytes)) and not any(len(x) == 24 for x in sg):
            try:
                return b"".join(sg).decode("cp932"), True
            except UnicodeDecodeError:
                pass
        return "[칸 %d개 미확인]" % sum(1 for x in sg if len(x) == 24), False

    def jp_text(seg: bytes) -> str:
        return seg.decode("cp932", "replace")

    rows = []

    def add(num, jp, kr, ok, memo=""):
        ink = lambda x: "".join(c for c in x if not c.isspace() and c not in "↵⏎")  # noqa: E731
        mark = "" if ink(jp) and ink(kr) else ("둘 다 빔" if not ink(jp) and not ink(kr) else ("원판만" if ink(jp) else "한글만"))
        rows.append((num, jp, kr, mark, ("롬 칸 비트맵 일치" if ok else "🔴 정본 문구와 안 맞음(칸 비트맵)") + (" " + memo if memo else "")))

    eo = orig_track[SS.EXTRAS_REL * common.USER : (SS.EXTRAS_REL + 2) * common.USER]
    ek = ko_track[SS.EXTRAS_REL * common.USER : (SS.EXTRAS_REL + 2) * common.USER]
    for name, lo, hi in SS.EXTRAS:
        jo = [x for x in eo[lo:hi].split(b"\0") if x]
        jk = [x for x in ek[lo:hi].split(b"\0") if x]
        for k in range(max(len(jo), len(jk))):
            kt, ok = kr_text(jk[k]) if k < len(jk) else ("", True)
            add(f"O:extras:{name}:{k}", jp_text(jo[k]) if k < len(jo) else "", kt, ok)
    # 몬스터 도감 88건 — 레코드 `1F 이름 04 01 [HP 칸] 01 05 줄 01 줄 … 06`
    def stream(track):
        return b"".join(track[(OF.DEX_REL + k) * common.USER : (OF.DEX_REL + k + 1) * common.USER] for k in range(5))

    def recs(d):
        out, pos = [], OF.DEX_OFF
        while len(out) < OF.DEX_COUNT:
            a = d.index(b"\x1f", pos)
            b = d.index(b"\x06", a) + 1
            out.append(d[a:b])
            pos = b
        return out

    for n, (ro, rk) in enumerate(zip(recs(stream(orig_track)), recs(stream(ko_track)), strict=True)):
        def split(r):
            name = r[1 : r.index(b"\x04")]
            body = r[r.index(b"\x01\x05") + 2 : -1]
            return name, body.split(b"\x01")

        no, lo_ = split(ro)
        nk, lk = split(rk)
        kn, okn = kr_text(nk)
        kls = [kr_text(x) for x in lk]
        add(f"O:dex:{n}", "{S:" + jp_text(no) + "}↵" + "↵".join(jp_text(x) for x in lo_), "{S:" + kn + "}↵" + "↵".join(t for t, _ in kls), okn and all(o for _, o in kls))
    return rows


def _batt_text(data: bytes, off: int, term, *, ko: bool, orig_len: int, gl: Glyphs) -> str:
    import battle

    out = []
    i = off
    n = len(data)
    steps = 0
    while i < n - 1 and steps < 2000:
        steps += 1
        b = data[i]
        if b >= battle.MSG_TERM:
            g = _glyph_ch(b, data[i + 1], gl, {}) if ko else None
            if g is None and ko and b == 0xF8 and data[i + 1] == 0x24:
                g = " "
            if g is None:
                try:
                    g = data[i : i + 2].decode("cp932")
                except UnicodeDecodeError:
                    g = f"[{b:02X}{data[i + 1]:02X}]"
            out.append(g)
            i += 2
            continue
        if b == 0x0F and i + 2 < n:
            t = (data[i + 1] | data[i + 2] << 8) - battle.LOAD_ADDR
            if ko and t >= orig_len:
                i = t
                continue
            out.append("{0F %04X}" % (t + battle.LOAD_ADDR))
            i += 3
            break
        if term is not None and b == term:
            break
        if b in battle.INLINE_OPS:
            out.append("↵" if b == 0x01 else "{%02X}" % b)
            i += 1
            continue
        break
    return "".join(out)


def battle_rows(orig_track: bytes, ko_track: bytes, gl: Glyphs) -> list[tuple]:
    """전투 컨테이너(rel 162~) — 몬스터 이름(64B 레코드의 16B 이름칸 · 간접 `23 주소` 는 펼침)과 전투 문구 단위(오프셋 = 번호)."""
    import battle

    def blocks(track, rel):
        raw = track[rel * common.USER : (rel + 8) * common.USER]
        dl = (raw[0] | raw[1] << 8) - battle.BASE
        ents = [(raw[i] | raw[i + 1] << 8, raw[i + 2] | raw[i + 3] << 8) for i in range(0, dl, 4)]
        out = []
        import lz

        for src, ln in ents:
            d, _used = lz.decode(raw[src - battle.BASE :], ln)
            out.append(d)
        return out

    rows = []

    def add(num, jp, kr, memo=""):
        ink = lambda x: "".join(c for c in x if not c.isspace() and c not in "↵⏎")  # noqa: E731
        mark = "" if ink(jp) and ink(kr) else ("둘 다 빔" if not ink(jp) and not ink(kr) else ("원판만" if ink(jp) else "한글만"))
        rows.append((num, jp, kr, mark, memo))

    def name_of(data, a, ko):
        nm = data[a + battle.NAME_OFF : a + battle.NAME_OFF + battle.NAME_LEN]
        out = []
        i = 0
        while i < len(nm):
            c = nm[i]
            if c in (0x06, 0x00):
                break
            if c == 0x23 and i + 2 < len(nm):
                off = (nm[i + 1] | nm[i + 2] << 8) - battle.LOAD_ADDR
                out.append(dec_plain(data[off : off + 80], ko, gl))
                i += 3
                continue
            if c >= 0x24 and i + 1 < len(nm):
                g = _glyph_ch(c, nm[i + 1], gl, {}) if ko else None
                if g is None and ko and c == 0xF8 and nm[i + 1] == 0x24:
                    g = " "
                if g is None:
                    try:
                        g = nm[i : i + 2].decode("cp932")
                    except UnicodeDecodeError:
                        g = f"[{c:02X}{nm[i + 1]:02X}]"
                out.append(g)
                i += 2
                continue
            out.append("{%02X}" % c)
            i += 1
        return "".join(out)

    for rel in battle.CONTAINERS:
        bo, bk = blocks(orig_track, rel), blocks(ko_track, rel)
        for bi, (do, dk) in enumerate(zip(bo, bk)):
            for r in battle.records(do):
                a = r["off"]
                add(f"B:{rel}:{bi}:name{a:04X}", name_of(do, a, False), name_of(dk, a, True))
            for u in battle.msg_units(do):
                a = u["off"]
                add(f"B:{rel}:{bi}:{a:04X}", _batt_text(do, a, u.get("term"), ko=False, orig_len=len(do), gl=gl),
                    _batt_text(dk, a, u.get("term"), ko=True, orig_len=len(do), gl=gl))
    return rows


def _cell(x: str) -> str:
    """TSV 칸 — 탭·줄바꿈 계열(\\r \\x0b \\x0c \\x1c~\\x1e \\x85 U+2028/9)은 `{U+XXXX}` 로 적어 행이 쪼개지지 않게 한다."""
    return "".join("{U+%04X}" % ord(c) if c in "\t\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029" else c for c in x)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", default=str(common.BUILD_DIR / common.BUILD_TAG / "ed1.iso"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    iso = Path(a.iso)
    out = Path(a.out) if a.out else Path(".")
    out.mkdir(parents=True, exist_ok=True)
    orig_track = common.track_data()
    ko_track = iso_track(iso)
    oc, kc = containers.scan(orig_track), containers.scan(ko_track)
    gl = Glyphs(iso)
    kmap = {c["rel"]: c for c in kc}
    # 🔴 넘친 컨테이너는 트랙 끝으로 **이사**하고 참조표가 새 자리를 가리킨다 — 옛 자리엔 손 안 댄 원판 사본이 남는다(죽은 사본). 짝은 참조표로 잇는다
    b42 = ko_track[containers.REF_BANK_REL * common.USER :][: 4 * common.USER]
    moved = {}
    for i, (r0, _n0) in enumerate(containers.referenced()):
        e = b42[containers.REF_TABLE_OFF + 3 * i :][:3]
        moved[r0] = containers.REC_BASE + (e[0] | e[1] << 8)
    rows = []
    stat = Counter()
    nblocks = nmiss = 0
    for c in oc:
        k = kmap.get(moved.get(c["rel"], c["rel"]))
        if k is None or len(k["blocks"]) != len(c["blocks"]):
            nmiss += 1
            continue
        for ob, kb in zip(c["blocks"], k["blocks"]):
            if ob["id"] != kb["id"]:
                nmiss += 1
                continue
            sid = ob["id"]
            nblocks += 1
            dyn = gl.dyn_of(kb["data"], len(ob["data"]))
            sj = HERE.parent / "script" / f"scn{sid:03d}.json"
            tkeys = set(json.load(open(sj, encoding="utf-8"))["messages"]) if sj.exists() else set()
            msgs = M.parse(ob["data"])
            refs = M.references(ob["data"])  # 메시지 시작을 가리키는 참조(머리 표·분할 즉치·JMP/JSR) — 둘↑이면 포인터 공유
            for m in msgs:
                num = f"{c['rel']}:{sid}:{m.start:04X}"
                jp, _ = decode(ob["data"], m.start, ko=False, orig_len=len(ob["data"]), gl=None, dyn={})
                kr, _ = decode(kb["data"], m.start, ko=True, orig_len=len(ob["data"]), gl=gl, dyn=dyn)
                ink = lambda s: "".join(x for x in s if not x.isspace() and x not in "↵⏎")  # noqa: E731
                if len(refs.get(m.start, [])) >= 2:
                    mark = "포인터 공유"
                elif not ink(jp) and not ink(kr):
                    mark = "둘 다 빔"
                elif not ink(kr):
                    mark = "원판만"
                elif not ink(jp):
                    mark = "한글만"
                else:
                    mark = ""
                memo = []
                intgt = m.key in tkeys  # 우리 번역 정본에 이 원문 열쇠가 있나 — 번역 대상
                if m.pinned:
                    memo.append("핀")
                if not intgt:
                    memo.append("번역 대상 아님(정본에 열쇠 없음 — 코드·표·비대사 포함)")
                elif jp == kr:
                    memo.append("🔴 번역 대상인데 원판 그대로")
                rows.append((num, jp, kr, mark, ",".join(memo)))
                stat[mark or "(정상 짝)"] += 1
                if m.pinned:
                    stat["핀"] += 1
                stat["번역 대상" if intgt else "번역 대상 아님"] += 1
                if intgt and jp == kr:
                    stat["🔴 번역 대상인데 원판 그대로"] += 1
    sysr = sys_rows(orig_track, ko_track, gl)
    battr = battle_rows(orig_track, ko_track, gl)
    for r in sysr:
        stat["시스템 행"] += 1
        stat[r[3] or "(정상 짝)"] += 1
    for r in battr:
        stat["전투 행"] += 1
        stat[r[3] or "(정상 짝)"] += 1
    rows = rows + sysr + battr
    with open(out / "pairs.tsv", "w", encoding="utf-8") as f:
        f.write("번호\t원판\t한글\t표시\t메모\n")
        for r in rows:
            f.write("\t".join(_cell(x) for x in r) + "\n")
    sha = lambda p: hashlib.sha1(open(p, "rb").read()).hexdigest()  # noqa: E731
    (out / "manifest.md").write_text(
        f"""# pce-ed1 원판·한글 짝 표 (씬 대사 · 시스템 · 전투)

- 한글 이미지: `{iso.name}` sha1 {sha(iso)} (꼬리표 {common.BUILD_TAG})
- 원판 이미지: {common.ORIG_ISO.name if hasattr(common, "ORIG_ISO") else "originals/jp/pce-ed1"} (데이터 트랙, `common.track_data()`)
- 분모: 씬 블록 {nblocks}개(컨테이너 {len(oc)}개 — 이사한 {sum(1 for a, b in moved.items() if a != b)}개는 참조표로 새 자리와 짝) · 씬 메시지 {len(rows) - len(sysr) - len(battr)}행 · 시스템 {len(sysr)}행 · 전투 {len(battr)}행 (합 {len(rows)}){" · 짝이 안 맞아 건너뛴 블록 %d" % nmiss if nmiss else ""}
- 표시별(표시 열): 원판만 {stat["원판만"]} · 한글만 {stat["한글만"]} · 둘 다 빔 {stat["둘 다 빔"]} · 포인터 공유 {stat["포인터 공유"]} · 표시 없음(정상 짝) {stat["(정상 짝)"]}
- 메모 열: 번역 대상(우리 번역 정본에 원문 열쇠가 있는 메시지) {stat["번역 대상"]} · 번역 대상 아님 {stat["번역 대상 아님"]}(코드·표 안의 우연한 글자 덩이 · 비대사) · 🔴 번역 대상인데 원판 그대로 {stat["🔴 번역 대상인데 원판 그대로"]}

## 방법
- 두 이미지(원판 · 위 한글 이미지)의 **데이터 트랙에서 컨테이너를 풀어**(`containers.scan`) 씬 블록마다 원판 메시지 시작 주소(`messages.parse`)에서 **두 블록 같은 주소**의 바이트를 디코드한다. 대본 JSON 은 읽지 않는다(번역 대상 여부 표시에만 열쇠 집합을 쓴다).
- 넘쳐서 이사한 컨테이너 {sum(1 for a, b in moved.items() if a != b)}개는 **참조표**(원판 44항목 ↔ 한글 이미지의 같은 항목)로 짝을 잇는다 — 옛 자리에는 손 안 댄 원판 사본이 남아 있다(죽은 사본).
- 한글 글자는 **글리프 비트맵을 글자로 되읽는다**: 상주 뱅크 = 이미지 섹터(rel 114~) 의 18B 비트맵, 동적 칸 = 블록 꼬리 스텁이 복사할 자료(`glyphdyn.simulate`) — 글꼴(`font.glyph`) 비트맵과 대조해 글자를 정한다. 못 읽으면 `[글리프n]` `[동적n]` 로 남는다(현재 0).
- 번역이 넘쳐 덧붙인 꼬리로 잇는 `0F`(원판 길이 밖을 가리키는 점프)는 따라가 읽고, 원판에 원래 있던 분기·호출은 `{{0F 주소}}` · `{{HH 인자}}` 로 적는다.

## 한계
- 판정 메모: 한글 칸에 일본어가 남은 행의 원인 분류와 실제 결함 후보는 `defects.md`.\n- 범위: ① 씬 대사 블록(번호 `rel:씬:시작`) ② 시스템 문구(번호 `S:<가족>:…` — 아이템 117 · 주문 29 · 파일 지명 52 · HUD 지명 50 · 화자 4 · 장 제목 · 메뉴 라벨 · 시스템 메시지 단위 · 부팅·파일 선택 화면 줄 · 필드 HUD · 오마케 목록) ③ 전투 컨테이너(번호 `B:<rel>:<블록>:<오프셋>` — 몬스터 이름(간접 `23 주소` 는 펼침)·전투 문구 단위) ④ 오마케 모듈(번호 `O:…` — 사운드 테스트 · 메뉴 · 몬스터 도감 88건; 전용 칸 글리프라 정본 문구를 같은 방식으로 구워 롬 칸 비트맵과 대조 — 글자 판독이 아님). **그림 글자**(엔딩 카드·오마케 간판·타이틀)와 오프닝·엔딩 자막·나레이션 자막(음성)은 이 표 밖이다.
- 시스템·전투 행 중 `원판만` 은 한글 쪽 칸이 **비어 있는 것**이다 — 시스템 메시지(sysmsg) 단위 일부는 번역이 앞 단위에 합쳐 쓰고(제자리 + `0F` 로 같은 뱅크 안 다음 단위에 잇기) 뒤 단위를 비우므로 결함이 아닐 수 있다. 읽는 쪽이 보고 가른다.
- 씬 메시지 목록은 `messages.parse` 의 휴리스틱이라 코드 안의 우연한 글자 덩이가 「메시지」로 잡힌 행이 있다(번역 대상 아님 표시). 반대로 파서가 놓친 메시지는 이 표에 없다.
- 이름·수 자리(`{{HH 인자}}`)와 `{{S:화자}}` 는 코드 그대로 적는다 — 실제 화면 값(받침 있는/없는 이름 등)은 대사 보기 캡처의 몫이다.
- 한글 쪽 쪽 넘김(⏎)은 번역 문안이 쪽마다 새로 짠 것이라 원판과 위치·수가 다를 수 있다(한국어 줄 길이). 마지막 쪽의 대기 `05` 가 한글 쪽엔 없는 메시지가 있다(원판 `…⏎` / 한글 끝에 ⏎ 없음 — 번역기가 마지막 쪽 대기를 종단 `06` 에 맡긴다. 화면으로 확정한 것은 아니다).
""",
        encoding="utf-8",
    )
    print("rows", len(rows), dict(stat), "blocks", nblocks, "skipped", nmiss)
    return 0


if __name__ == "__main__":
    sys.exit(main())
