#!/usr/bin/env python3
"""전투·시스템 문구 + 엔딩·오프닝 문구 짝 표 — 원판 롬 ↔ 제품 롬 (문안 검수용, 읽기 전용·촬영 없음, 10-20 판의 도구화).

  python3 tools/pair_table_sys.py --out <폴더> [--kr-bin <제품 이미지 bin>]

산출 `<out>/pairs-battle.tsv`(번호 · 원판 문구 · 한글 문구 · 표시 · 참조 사이트 수 — 5열) ·
`<out>/pairs-opening-ending.tsv`(번호 · 원판 대사 · 한글 대사 · 분류 — 4열) + `<out>/sys-stats.json`.
⚠ 원문 포함 — 저장소 밖(`.local/work/inbox/`)에만 낸다. **탭으로만 나눠 읽을 것.**

전투·시스템: 원판 코드의 lui+addiu/ori 쌍(레지스터 재사용 거리 제한)과 정렬 포인터 워드가 가리키는 문자열을 원판 문구로,
같은 사이트가 제품 이미지에서 가리키는 문자열을 한글 문구로 디코드한다(ED.EXE · ED2.EXE · ED2MON0~5 의 현재 ISO 디렉터리 파일).
엔딩·오프닝: 번호 = `<EXE>:<원판 파일 오프셋>`, 원판 = 원판 EXE 의 그 자리 문자열, 한글 = 제품 문안 정본(derive_text).
⚠ 오프닝·엔딩 EXE 의 한글은 슬롯 코드 글리프라 롬 바이트에서 글자로 되읽지 않는다(문안 정본이 곧 그 입력이다).
"""

import argparse
import collections
import contextlib
import hashlib
import io
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")
with contextlib.redirect_stdout(io.StringIO()):
    import hangul_map as H
    import patch_ed2_battle as EB
    import patch_ed2_monster_lines as L
    import patch_items as PI
    from common import BUILD_DIR, extract
    from ed2_monster_review import MON
REV = {H.syllable_sjis(c).to_bytes(2, "big"): c for c in H.SYL_INDEX}
EXE_BASE = 0x80010000
EXE_HDR = 0x800
OVB = 0x8014A000
LUI, ADDIU, ORI = 0x0F, 0x09, 0x0D


def dec_kr(b):
    out = []
    i = 0
    while i < len(b):
        x = b[i : i + 2]
        if x in REV:
            out.append(REV[x])
            i += 2
            continue
        c = b[i]
        if c == 0x0A:
            out.append("/")
            i += 1
        elif 0x20 <= c < 0x7F:
            out.append(chr(c))
            i += 1
        elif (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC) and i + 1 < len(b):
            try:
                out.append(b[i : i + 2].decode("cp932"))
                i += 2
            except (UnicodeDecodeError, ValueError):
                out.append(f"<{c:02X}>")
                i += 1
        elif 0xA1 <= c <= 0xDF:
            out.append(b[i : i + 1].decode("cp932"))
            i += 1
        else:
            out.append(f"<{c:02X}>")
            i += 1
    return "".join(out)


def dec_jp(b):
    out = []
    i = 0
    while i < len(b):
        c = b[i]
        if c == 0x0A:
            out.append("/")
            i += 1
        elif 0x20 <= c < 0x7F:
            out.append(chr(c))
            i += 1
        elif 0xA1 <= c <= 0xDF:
            out.append(b[i : i + 1].decode("cp932"))
            i += 1
        elif (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC) and i + 1 < len(b):
            try:
                out.append(b[i : i + 2].decode("cp932"))
                i += 2
            except (UnicodeDecodeError, ValueError):
                out.append(f"<{c:02X}>")
                i += 1
        else:
            out.append(f"<{c:02X}>")
            i += 1
    return "".join(out)


def has_jp(b):
    i = 0
    while i < len(b):
        c = b[i]
        if (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC) and i + 1 < len(b):
            return True
        if 0xA1 <= c <= 0xDF:
            return True
        i += 1
    return False


def cstr(buf, o):
    if o < 0 or o >= len(buf):
        return None
    j = buf.find(b"\x00", o)
    return bytes(buf[o:j]) if j >= 0 else None


def kanas0(b):
    i = 0
    k = 0
    while i < len(b):
        c = b[i]
        if (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC) and i + 1 < len(b):
            v = (c << 8) | b[i + 1]
            if 0x829F <= v <= 0x82F1 or 0x8340 <= v <= 0x8396:
                k += 1
            i += 2
        else:
            i += 1
    return k


def textlike(b):
    if not b or len(b) < 2:
        return False
    t = dec_jp(b)
    import re

    marks = [
        m for m in re.findall(r"<([0-9A-F]{2})>", t) if m not in ("01", "02", "03", "04", "05")
    ]
    if marks:
        return False
    if has_jp(b):
        return kanas0(b) >= 1
    return sum(1 for c in b if 0x20 <= c < 0x7F) >= max(2, len(b) // 2)


MAX_DIST = 6  # lui 와 짝 명령 사이 최대 명령 수(common.iter_lui_pairs 와 같다)


def _writes(w):
    """이 명령이 덮어쓰는 GPR 번호(없으면 None). 보수적 — 모르면 rt/rd 를 덮는 것으로 본다."""
    op = w >> 26
    if op == 0:  # R-type
        f = w & 0x3F
        if f in (0x08, 0x11, 0x13, 0x18, 0x19, 0x1A, 0x1B, 0x0C, 0x0D):
            return None  # jr/mthi/mtlo/mult/div/syscall/break
        return (w >> 11) & 31
    if op in (0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F):
        return (w >> 16) & 31  # addi..lui
    if op in (0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26):
        return (w >> 16) & 31  # 메모리 로드
    if op == 0x03:
        return 31  # jal
    return None


def pairs_code(buf):
    """[(imm_off,lui_off,op,addr)] — 레지스터 재사용 거리 제한 버전.

    lui 의 상위값은 ① MAX_DIST 명령 안에서만, ② 그 레지스터를 덮는 명령(rt/rd 쓰기·로드)이 끼면 끊기고,
    ③ 분기·점프를 만나면 지연 슬롯 한 칸까지만 유효(그 뒤 전부 끊김) — 스택 구조체 복사 루프의
    `addiu t0,t0,0x10` 이 멀리 있는 옛 lui 와 짝지어지던 도구 가짜(ED2.EXE:801·803·810 · ED.EXE:803)를 막는다.
    짝 명령(addiu/ori)이 자기 rs 를 덮는 경우(rt==rs)는 그 줄로 상위값이 사라진다."""
    out = []
    lr = {}
    n = len(buf) // 4
    cut_at = None
    for idx in range(n):
        p = idx * 4
        w = struct.unpack_from("<I", buf, p)[0]
        op = w >> 26
        if cut_at is not None and idx > cut_at:
            lr.clear()
            cut_at = None
        if op == LUI:
            lr[(w >> 16) & 31] = ((w & 0xFFFF) << 16, idx)
            continue
        if op in (ADDIU, ORI):
            rs = (w >> 21) & 31
            if rs in lr:
                hi, li = lr[rs]
                if idx - li <= MAX_DIST:
                    imm = w & 0xFFFF
                    if op == ADDIU and imm & 0x8000:
                        imm -= 0x10000
                    out.append((p, li * 4, op, hi + imm))
                else:
                    lr.pop(rs, None)
        rt = _writes(w)
        if rt is not None and rt in lr and op != LUI:
            lr.pop(rt, None)
        # 분기·점프: 지연 슬롯(idx+1) 뒤 전부 끊김
        is_br = op in (1, 2, 3, 4, 5, 6, 7) or (op == 0 and (w & 0x3F) in (0x08, 0x09))
        if is_br:
            cut_at = idx + 1
    return out


def addr_of(buf, imm_off, lui_off, op):
    w = struct.unpack_from("<I", buf, imm_off)[0]
    wl = struct.unpack_from("<I", buf, lui_off)[0]
    imm = w & 0xFFFF
    if op == ADDIU and imm & 0x8000:
        imm -= 0x10000
    return ((wl & 0xFFFF) << 16) + imm


def battle_system(IMG, OUT):
    """전투·시스템 문구 짝 표 → OUT(5열 tsv). (행 수, 표시별 수, 행 목록)."""
    # ── 대상 파일 정의
    live = L._live_group_lba(IMG)
    FILES = {}  # 이름 → dict(orig, final, base, hdr)
    ed1o = bytes(extract(PI.ED_LBA, PI.ED_SIZE))
    ed1f = bytes(extract(PI.ED_LBA, PI.ED_SIZE, path=IMG))
    ed2o = bytes(extract(EB.ED2_LBA, EB.ED2_SIZE))
    ed2f = bytes(extract(EB.ED2_LBA, EB.ED2_SIZE, path=IMG))
    FILES["ED.EXE"] = {"o": ed1o, "f": ed1f, "base": EXE_BASE, "hdr": EXE_HDR}
    FILES["ED2.EXE"] = {"o": ed2o, "f": ed2f, "base": EXE_BASE, "hdr": EXE_HDR}
    for g, (lba, osize) in sorted(MON.items()):
        o = bytes(extract(lba, osize))
        clba, csize = live[g]
        f = bytes(extract(clba, (csize + 2047) // 2048 * 2048, path=IMG))
        FILES[f"ED2MON{g}"] = {"o": o, "f": f, "base": OVB, "hdr": 0}

    def region_of(addr, name, fin=False):
        """주소 → (파일이름, 오프셋). 오버레이는 EXE(ED2) 도 가리킬 수 있다."""
        if name.startswith("ED2MON"):
            d = FILES[name]
            if OVB <= addr < OVB + len(d["f" if fin else "o"]):
                return name, addr - OVB
        ex = "ED.EXE" if name == "ED.EXE" else "ED2.EXE"
        d = FILES[ex]
        off = addr - EXE_BASE + EXE_HDR
        if EXE_BASE <= addr and 0 <= off < len(d["o"]):
            return ex, off
        return None, None

    rows = {}  # (파일,오프셋) → dict(sites=[], finals=set, kind)

    def add(key, site_kind, fin_bytes):
        r = rows.setdefault(key, {"n": 0, "fin": collections.OrderedDict(), "kinds": set()})
        r["n"] += 1
        r["kinds"].add(site_kind)
        r["fin"][fin_bytes] = r["fin"].get(fin_bytes, 0) + 1

    for name, d in FILES.items():
        o, f = d["o"], d["f"]
        # 코드 참조
        for imm, lui, op, addr in pairs_code(o):
            tf, to = region_of(addr, name)
            if tf is None:
                continue
            so = FILES[tf]["o"]
            s = cstr(so, to)
            if s is None or not textlike(s):
                continue
            a2 = addr_of(f, imm, lui, op)
            # 최종 대상: 같은 사이트가 가리키는 주소 → 같은 영역 규칙
            tf2, to2 = region_of(a2, name, True)
            fb = cstr(FILES[tf2]["f"], to2) if tf2 else None
            add((tf, to), "code", fb)
        # 정렬 포인터 워드(데이터 표)
        n = len(o)
        for p in range(0, n - 3, 4):
            w = struct.unpack_from("<I", o, p)[0]
            if not (0x80010000 <= w < 0x80210000 or OVB <= w < OVB + 0x20000):
                continue
            tf, to = region_of(w, name)
            if tf is None:
                continue
            so = FILES[tf]["o"]
            if to > 0 and so[to - 1] != 0:
                continue
            s = cstr(so, to)
            if not s or not textlike(s):
                continue
            if not (has_jp(s) or all(0x20 <= c < 0x7F or c == 0x0A for c in s)):
                continue
            # 코드 영역 오인 방지: 이 워드는 명령이 아니라 표 항목이어야 — 앞뒤 워드도 같은 영역 주소거나 0
            if not has_jp(s):
                continue
            w2 = struct.unpack_from("<I", f, p)[0]
            tf2, to2 = region_of(w2, name, True)
            fb = cstr(FILES[tf2]["f"], to2) if tf2 else None
            add((tf, to), "table", fb)
    # ── 행 만들기
    ref_ranges = collections.defaultdict(list)
    for fn, off in rows:
        ref_ranges[fn].append(off)
    out = []
    cnt = collections.Counter()

    def mark(o_b, fin, ref):
        if ref == 0:
            return "참조 없는 죽은 데이터"
        if not has_jp(o_b):
            return "번역 대상 아님"
        if not fin:
            return "한글 쪽 비어 있음"
        if fin == o_b:
            return "원판 일본어 그대로(참조 있음)"
        if has_jp(fin) and not any(b"\x00" == bytes([c]) for c in []):
            # 한글 슬롯도 SJIS 영역이라 has_jp 는 참이다 — 한글 디코드가 한글을 만들었는지로 가른다
            pass
        return ""

    for (fn, off), r in sorted(rows.items()):
        ob = cstr(FILES[fn]["o"], off)
        fins = [b for b in r["fin"] if b is not None]
        fb = fins[0] if fins else None
        kr = dec_kr(fb) if fb is not None else ""
        if len(fins) > 1:
            kr = " ‖ ".join(dec_kr(b) for b in fins)
        m = mark(ob, fb, r["n"])
        if len(fins) > 1 and m == "":
            m = "사이트별 최종 문자열 다름"
        if (
            m == ""
            and fb is not None
            and not any("가" <= c <= "힣" for c in kr)
            and has_jp(fb)
            and fb != ob
            and not kr.isascii()
        ):
            m = "한글 없음(일본어 아님 — 확인)"
        if off > 0 and FILES[fn]["o"][off - 1] != 0:
            m = "중간 포인터(앞 글자 건너뜀)" if m == "" else m + " · 중간 포인터"
        cnt[m or "정상"] += 1
        out.append(
            (
                f"{fn}:{off:X}",
                dec_jp(ob),
                kr,
                m,
                str(r["n"])
                + (
                    "/표"
                    if "table" in r["kinds"] and "code" not in r["kinds"]
                    else ("+표" if "table" in r["kinds"] else "")
                ),
            )
        )

    # ── 참조 없는 죽은 일본어(가나 2자 이상)
    def kanas(b):
        i = 0
        k = 0
        while i < len(b):
            c = b[i]
            if (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC) and i + 1 < len(b):
                v = (c << 8) | b[i + 1]
                if 0x829F <= v <= 0x82F1 or 0x8340 <= v <= 0x8396:
                    k += 1
                i += 2
            else:
                i += 1
        return k

    dead = 0
    for fn, d in FILES.items():
        o, f = d["o"], d["f"]
        refd = set()
        for a, off in rows:
            if a == fn:
                e = o.find(b"\x00", off)
                refd.update(range(off, e if e >= 0 else off + 1))
        p = 0
        while p < len(o):
            if o[p] == 0 or (p > 0 and o[p - 1] != 0):
                p += 1
                continue
            j = o.find(b"\x00", p)
            if j < 0:
                break
            s = o[p:j]
            if 4 <= len(s) <= 200 and p not in refd and kanas(s) >= 2:
                try:
                    s.decode("cp932")
                except (UnicodeDecodeError, ValueError):
                    p = j + 1
                    continue
                if not any(x in refd for x in range(p, j)):
                    fb = cstr(f, p) if p < len(f) else None
                    out.append(
                        (
                            f"{fn}:{p:X}",
                            dec_jp(s),
                            dec_kr(fb) if fb else "",
                            "참조 없는 죽은 데이터",
                            "0",
                        )
                    )
                    cnt["참조 없는 죽은 데이터"] += 1
                    dead += 1
            p = j + 1
    with open(OUT, "w", encoding="utf-8") as fo:
        fo.write("번호\t원판 문구\t한글 문구\t표시\t참조 사이트 수\n")
        for r in out:
            fo.write("\t".join(x.replace("\t", " ") for x in r) + "\n")
    print(len(out), dict(cnt))

    return len(out), dict(cnt)


def opening_ending(IMG, OUT):
    """엔딩·오프닝·event 문구 짝 표(4열). 원판 = 원판 EXE 그 자리, 한글 = 문안 정본."""
    import derive_text
    import patch_opening_font as OF

    rows = []
    for name, g in OF.GAMES.items():
        orig = bytes(extract(g["lba"], OF.SIZE))
        for off, kr in derive_text.off_pairs(g["cls"]):
            o = off + g["delta"]
            j = orig.find(b"\x00", o)
            rows.append(
                (f"{name}:{o:X}", dec_jp(orig[o:j]).rstrip("/"), kr.replace("\n", "/"), g["cls"])
            )
    for k, v in derive_text.derive("event").items():
        rows.append((f"event:{k}", "(해시키)", v.replace("\n", "/"), "event"))
    with open(OUT, "w", encoding="utf-8", newline="\n") as fo:
        fo.write("번호\t원판 대사\t한글 대사\t분류\n")
        fo.writelines("\t".join(x.replace("\t", " ") for x in r) + "\n" for r in rows)
    return len(rows), dict(collections.Counter(r[3] for r in rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--kr-bin", default=os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    nb, cb = battle_system(a.kr_bin, os.path.join(a.out, "pairs-battle.tsv"))
    ne, ce = opening_ending(a.kr_bin, os.path.join(a.out, "pairs-opening-ending.tsv"))
    h = hashlib.sha1()
    with open(a.kr_bin, "rb") as f:
        for ch in iter(lambda: f.read(1 << 22), b""):
            h.update(ch)
    st = {"battle_rows": nb, "battle": cb, "oe_rows": ne, "oe": ce, "kr_sha1": h.hexdigest()}
    with open(os.path.join(a.out, "sys-stats.json"), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    print(json.dumps(st, ensure_ascii=False))


if __name__ == "__main__":
    main()
