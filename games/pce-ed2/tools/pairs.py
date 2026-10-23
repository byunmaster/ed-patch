"""원판·한글 짝 표 — 두 이미지(원판 · 지금 HEAD 제품)에서 **번호마다 실제 바이트를 디코드**해 나란히 놓는다(마스터 10-20 「전체 대사를 원문 칸에 올바른 번역이 왔는가」).

    python3 pairs.py --iso <제품 이미지> --out <폴더>     # → pairs.tsv · manifest.md
촬영이 없다 — 대본 JSON 이 아니라 **구운 이미지**의 바이트를 읽는다(원판은 `common.track_data`, 한글은 제품 이미지 섹터).

번호 꼴:
  `rel:메시지번호:줄`   장면 패키지(본편 13개) 메시지 덩이의 줄 — 대사 · 전투 덩이 · 이름 라벨 · 메뉴 덩이 전부(번역이 맡는 덩이는 줄 단위로 전부 싣는다)
  `S<뱅크>:<오프셋>`    본 프로그램 리터럴 문자열(`JSR $503E/$4ED5/$4ED1` 뒤 `BIT` 피연산자) — 한글 쪽은 **같은 호출 자리의 피연산자**를 따라간다(같은 뱅크로 옮겼거나 공용 중계로 먼 뱅크에 놓은 것 모두)
  `T:<표>:<번호>`       본 프로그램 표(아이템 · 주문 · 지명 · 이름 · 켬꺼짐 · 상태) 항목 — 한글 쪽은 표 시작 즉치(`LDY #hi / LDX #lo`)를 따라간다
  `C<rel>:<오프셋>`     장면 코드 안 인라인 문자열(`codestr`) — 한글 쪽은 `BIT` 포인터를 따라간다
표기: 쪽 넘김 `13` = ⏎ · 줄바꿈 `0D` = ↵ · 이름·수 자리(`07` `13 nn` `1A` `1B`) = `{name}` · 동적 조사 = `{josa}` · 그 밖의 제어는 `{HH 인자}` 그대로 펼친다(`16 … 14` = 화자 머리, `1C`·`1D` 분기, `0C` 창 호출 …).
표시: 원판만(한글 쪽이 빔) · 한글만(원판 쪽이 빔) · 둘 다 빔 · 포인터 공유(원판에서 둘↑ 번호·호출이 같은 문자열을 가리킨다 — 한 문장이 여러 자리에 나간다).
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import codestr
import common
import font
import hook
import jptext
import package
import pceview
import systext

BANK = 8192
BANK0 = 0x68
MAIN_REL = 130
MAIN_SECTORS = 48  # 뱅크 0x68~0x73(12×8KB = 96KB)
HIRA = jptext.HIRA
ASC = jptext.ASC


# ── 한글 글리프 읽기 ─────────────────────────────────────────────────────────────
class KoGlyphs:
    """제품 이미지의 **글리프 비트맵**을 글자로 되읽는다 — 정적 풀(본 프로그램) + 패키지 지역 표(메시지 표 항목 0)."""

    def __init__(self, iso: str):
        self.iso = iso
        main = pceview.iso_pkg(iso, MAIN_REL, MAIN_SECTORS)
        nruns = hook.MAX_RUNS
        a = hook._routine(nruns)
        labs = a.labels
        base = 0x6000 + hook.HOOK_OFF
        hk = (hook.HOOK_BANK - BANK0) * BANK + hook.HOOK_OFF

        def tab(name):
            o = hk + (labs[name] - base)
            return main[o : o + nruns + 1]

        cnt, banks, adlo, adhi = (tab(n) for n in ("CNT", "BANKS", "ADLO", "ADHI"))
        self.static_n = main[hk + (labs["SLO"] - base)] | main[hk + (labs["SHI"] - base)] << 8
        pool = []
        for i in range(nruns):
            if not cnt[i]:
                continue
            off = (adhi[i] & 0x1F) << 8 | adlo[i]
            lin = (banks[i] - BANK0) * BANK + off
            for k in range(cnt[i]):
                pool.append(main[lin + k * 16 : lin + k * 16 + 16])
        font._load_bdf()
        cands = [chr(c) for c in sorted(font._cache) if c >= 0x20]  # 글꼴이 가진 글자 전부(한글 · ASCII · 전각 숫자·부호 …) — 비트맵으로 되읽는다
        self.bm: dict[bytes, str] = {}
        for ch in cands:
            try:
                self.bm.setdefault(font.pack(font.glyph(ch), font.flags(ch)), ch)
            except Exception:
                pass
        self.static = [self.bm.get(p, "") for p in pool]
        self.unknown = 0
        self._local: dict[int, list[str]] = {}

    def local(self, rel: int, pkg: bytes) -> list[str]:
        if rel not in self._local:
            _t, tab = package.msg_table(pkg)
            gl = pkg[tab[0] : tab[0] + 16 * 255]
            self._local[rel] = [self.bm.get(gl[i * 16 : (i + 1) * 16], "") for i in range(255)]
        return self._local[rel]

    def glyph(self, lead: int, trail: int, local: list[str]) -> str:
        idx = (lead - font.LEAD0) * font.PER_LEAD + (trail - font.TRAIL0)
        s = self.static[idx] if 0 <= idx < self.static_n and idx < len(self.static) else (local[idx - self.static_n] if 0 <= idx - self.static_n < len(local) else "")
        if not s:
            self.unknown += 1
            return "{?%d}" % idx
        return s


# ── 디코드 ───────────────────────────────────────────────────────────────────────
NAME_BYTES = {0x07, 0x1A, 0x1B}


def _is_ko(raw: bytes, sys_ctx: bool = False) -> bool:
    """줄에 한글 글리프 리드(`F0~F9`)가 있으면 한글 줄이다 — 아니면 원판 글자 그대로(일본어 줄)로 읽는다. 제어의 인자 바이트는 건너뛴다(`13 89` 의 `89` 가 SJIS 리드로 읽혀 뒤를 삼키지 않게)."""
    args = dict(jptext.ARGS)
    if sys_ctx:
        args.update({0x13: 1, 0x16: 4, 0x18: 4})
    i = 0
    while i < len(raw):
        b = raw[i]
        if b < 0x20:
            i += 1 + args.get(b, 0)
        elif font.LEAD0 <= b <= font.LEAD0 + font.MAX_LEADS:
            return True
        else:
            i += 2 if (0x80 <= b <= 0x9F or b >= 0xE0) else 1
    return False


def decode(raw: bytes, kg: KoGlyphs | None, local: list[str] | None, sys_ctx: bool = False) -> str:
    """바이트열 → 읽기용 글. 쪽 넘김(`13`) = ⏎ · 줄바꿈(`0D`) = ↵ · 이름·수 = `{name}` · 나머지 제어는 `{HH 인자}`.
    `sys_ctx` = 본 프로그램 문자열(`13` 이 1바이트 인자를 가진 이름 자리표, `16`/`18` 이 인자 4바이트)."""
    ko = kg is not None and _is_ko(raw, sys_ctx)
    args = dict(jptext.ARGS)
    if sys_ctx:
        args.update({0x13: 1, 0x16: 4, 0x18: 4})
    out = []
    i = 0
    kana = False
    while i < len(raw):
        a = raw[i]
        if a == 0x00:
            break
        if a < 0x20:
            if a == 0x0D:
                out.append("↵")
            elif a == 0x13 and not sys_ctx:
                out.append("⏎")
            elif a in NAME_BYTES or (sys_ctx and a == 0x13):
                n = 1 if (sys_ctx and a == 0x13) else 0
                out.append("{name}")
                i += n
            elif a == 0x0E:
                kana = True
                out.append("{0E}")
            elif a == 0x0F:
                kana = False
                out.append("{0F}")
            else:
                n = args.get(a, 0)
                out.append("{" + " ".join(f"{x:02X}" for x in raw[i : i + 1 + n]) + "}")
                i += n
            i += 1
        elif ko and font.LEAD0 <= a < font.LEAD0 + font.MAX_LEADS and i + 1 < len(raw):
            out.append(kg.glyph(a, raw[i + 1], local or []))
            i += 2
        elif ko and a == font.JOSA_LEAD and i + 1 < len(raw):
            out.append("{josa}")
            i += 2
        elif ko and a == 0x60:
            out.append(" ")
            i += 1
        elif ko and 0x20 <= a < 0x7F:
            out.append(chr(a))
            i += 1
        elif 0x80 <= a <= 0x9F or a >= 0xE0:
            try:
                out.append(raw[i : i + 2].decode("cp932"))
            except UnicodeDecodeError:
                out.append("{" + raw[i : i + 2].hex().upper() + "}")
            i += 2
        elif a >= 0xA0:
            ch = HIRA.get(a, f"{{{a:02X}}}")
            out.append(jptext._kata(ch) if kana else ch)
            i += 1
        else:
            ch = ASC.get(a, f"{{{a:02X}}}")
            out.append(jptext._kata(ch) if kana else ch)
            i += 1
    return "".join(out)


def blank(s: str) -> bool:
    """글이 없나 — 제어 표지·공백·줄바꿈뿐이면 빈 것으로 본다."""
    return not re.sub(r"\{(?!josa)[^}]*\}|[⏎↵\s　]", "", s)


SKIPPED: list[str] = []  # 대사가 아닌 꼬리 덩이로 빼낸 번호
MISMATCH: list[str] = []  # 원판·한글의 줄 수가 다른 덩이
DEAD_SITES: list[str] = []  # 죽은 코드(전투 디버그 출력 루틴 — 번역·한글 칸 없음)


# ── 추출 ─────────────────────────────────────────────────────────────────────────
def _final_track(iso: str):
    cache: dict[int, bytes] = {}

    def get(rel: int) -> bytes:
        if rel not in cache:
            cache[rel] = pceview.iso_pkg(iso, rel)
        return cache[rel]

    return get


def package_rows(iso: str, kg: KoGlyphs):
    """장면 패키지 메시지 덩이의 줄 — (번호, 원판, 한글, 공유 여부)."""
    get = _final_track(iso)
    for rel in package.CLEAN:
        po = bytes(common.track_data(rel, 128))
        pf = get(rel)
        to, tabo = package.msg_table(po)
        tf, tabf = package.msg_table(pf)
        cho = dict(package.chunks(po))
        chf = dict(package.chunks(pf))
        local = kg.local(rel, pf)
        # (원판 시작, 한글 시작) 쌍으로 묶는다 — 같은 덩이를 가리키는 번호들은 한 줄 묶음이다(포인터 공유)
        groups: dict[tuple[int, int], list[int]] = {}
        for m, p in enumerate(tabo):
            if p > to and p in cho and m < len(tabf) and tabf[m] > tf and tabf[m] in chf:
                groups.setdefault((p, tabf[m]), []).append(m)
        for (po_start, pf_start), ms in sorted(groups.items(), key=lambda kv: kv[1][0]):
            do = package.decode_chunk(po, po_start, cho[po_start])[0].split(b"\x00")
            df = package.decode_chunk(pf, pf_start, chf[pf_start])[0].split(b"\x00")
            if len(do) > 400 or do[0][:8] == package.SENTINEL or df[0][:8] == package.SENTINEL:  # 패키지 꼬리(압축 자료·0xFF 채움)가 덩이로 잡힌 것 — 대사가 아니다
                SKIPPED.append(f"{rel}:{'=' .join(map(str, ms))}")
                continue
            if len(do) != len(df):
                MISMATCH.append(f"{rel}:{'=' .join(map(str, ms))}")
            n = max(len(do), len(df))
            for j in range(n - 1 if n > 1 else n):  # 끝 `00` 뒤 빈 조각 제외
                o = decode(do[j], None, None) if j < len(do) else ""
                k = decode(df[j], kg, local) if j < len(df) else ""
                yield f"{rel}:{'=' .join(map(str, ms))}:{j}", o, k, len(ms) > 1


def _main(iso_bytes_fn) -> bytes:
    return iso_bytes_fn(MAIN_REL, MAIN_SECTORS)


def _bank(main: bytes, b: int) -> bytes:
    return main[(b - BANK0) * BANK : (b - BANK0 + 1) * BANK]


def _cstr(buf: bytes, off: int) -> bytes:
    e = buf.find(b"\x00", off)
    return buf[off : e if e >= 0 else len(buf)]


def literal_rows(iso: str, kg: KoGlyphs):
    """본 프로그램 리터럴 문자열 — 원판의 호출 자리마다 한글 쪽 피연산자를 따라간다."""
    mo = bytes(common.track_data(MAIN_REL, MAIN_SECTORS))
    mf = pceview.iso_pkg(iso, MAIN_REL, MAIN_SECTORS)
    pat = re.compile(rb"\x20(?:\x3e\x50|\xd5\x4e|\xd1\x4e)\x2c(..)", re.DOTALL)
    for b in range(0x69, 0x74):
        so, sf = _bank(mo, b), _bank(mf, b)
        sites: dict[int, list[int]] = {}
        for m in pat.finditer(so):
            addr = m.group(1)[0] | m.group(1)[1] << 8
            if 0x6000 <= addr < 0x8000:
                sites.setdefault(addr - 0x6000, []).append(m.start(1))
        for off, ps in sorted(sites.items()):
            ko_set = []
            dead = any(bk == b and lo <= off < lo + ln for bk, lo, ln, _h, _t in systext.DEAD_DEBUG)  # 죽은 디버그 문구 자리 — 글리프 풀로 돌려줘 한글 쪽에 문자열이 없다
            ps = [p for p in ps if not any(bk == b and lo <= p < lo + ln for bk, lo, ln, _h, _t in systext.DEAD_DEBUG)]
            if dead or not ps:
                DEAD_SITES.append(f"S{b:02X}:{off:04X}")
                continue
            for p in ps:
                head = sf[p - 4 : p]
                if head[:1] == b"\x20" and head[1:3] == so[p - 3 : p - 1] and 0x6000 <= (sf[p] | sf[p + 1] << 8) < 0x8000:  # 같은 뱅크(피연산자만 바뀐 것)
                    ko_set.append(_cstr(sf, (sf[p] | sf[p + 1] << 8) - 0x6000))
                elif head[:1] == b"\x20" and 0x4000 <= (head[1] | head[2] << 8) < 0x6000 and 0x68 <= head[3] <= 0x73:  # 공용 중계 — `JSR 중계 · 뱅크 · 주소`
                    fb = head[3]
                    ko_set.append(_cstr(_bank(mf, fb), (sf[p] | sf[p + 1] << 8) - 0x8000))
                else:
                    ko_set.append(b"")
            kos = list(dict.fromkeys(ko_set))
            o = decode(_cstr(so, off), None, None, True)
            k = " ‖ ".join(decode(x, kg, None, True) for x in kos)  # 호출 자리마다 다르면 ‖ 로 잇는다(원판은 한 문자열을 여럿이 부른다 — 한글이 갈라 놓았다)
            yield f"S{b:02X}:{off:04X}", o, k, len(ps) > 1


def table_rows(iso: str, kg: KoGlyphs):
    mo = bytes(common.track_data(MAIN_REL, MAIN_SECTORS))
    mf = pceview.iso_pkg(iso, MAIN_REL, MAIN_SECTORS)
    import layout

    class _P:  # `systext.table_sites` 가 쓰는 최소 면 — 뱅크 바이트만 준다
        def __init__(self, m):
            self.m = m

        def o(self, bank, off, n):
            return _bank(self.m, bank)[off : off + n]

    po, pf = _P(mo), _P(mf)
    assert layout.BANK == BANK
    for name, bank, start, end in systext.TABLES:
        sites = systext.table_sites(po, bank, start)
        so = _bank(mo, bank)
        ent_o = so[start:end].split(b"\x00")
        if ent_o and ent_o[-1] == b"":
            ent_o = ent_o[:-1]
        base_f = None
        if sites:
            hi_p, lo_p, _s = sites[0]
            sf = _bank(mf, bank)
            base_f = (sf[hi_p] << 8 | sf[lo_p]) - 0x6000
        ent_f = []
        if base_f is not None and 0 <= base_f < BANK:
            at = base_f
            for _ in ent_o:
                s = _cstr(_bank(mf, bank), at)
                ent_f.append(s)
                at += len(s) + 1
        for i, e in enumerate(ent_o):
            k = decode(ent_f[i], kg, None, True) if i < len(ent_f) else ""
            yield f"T:{name}:{i}", decode(e, None, None, True), k, False


def code_rows(iso: str, kg: KoGlyphs):
    get = _final_track(iso)
    for sp in codestr.SPECS:
        po = bytes(common.track_data(sp.rel, 128))
        pf = get(sp.rel)
        local = kg.local(sp.rel, pf)
        new = (pf[sp.ptr] | pf[sp.ptr + 1] << 8) - codestr.BASE
        yield f"C{sp.rel}:{sp.old:04X}", decode(_cstr(po, sp.old), None, None, True), decode(_cstr(pf, new), kg, local, True), False


# ── 표 ───────────────────────────────────────────────────────────────────────────
def mark(o: str, k: str, shared: bool) -> str:
    bo, bk = blank(o), blank(k)
    ms = []
    if bo and bk:
        ms.append("둘 다 빔")
    elif bk:
        ms.append("원판만")
    elif bo:
        ms.append("한글만")
    if shared:
        ms.append("포인터 공유")
    return ",".join(ms)


def build(iso: str, out: Path) -> dict:
    kg = KoGlyphs(iso)
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    kinds: dict[str, int] = {}
    n = 0
    same = pages_diff = 0  # 참고 — 표시 넷에 안 드는 것(양쪽 글이 같다 · ⏎ 수가 다르다)
    with open(out / "pairs.tsv", "w", encoding="utf-8") as f:
        f.write("번호\t원판\t한글\t표시\n")
        for kind, gen in (("패키지 줄", package_rows(iso, kg)), ("프로그램 리터럴", literal_rows(iso, kg)), ("프로그램 표", table_rows(iso, kg)), ("코드 문자열", code_rows(iso, kg))):
            for num, o, k, shared in gen:
                mk = mark(o, k, shared)
                f.write(f"{num}\t{o.replace(chr(9), ' ')}\t{k.replace(chr(9), ' ')}\t{mk}\n")
                n += 1
                if not blank(o) and o == k:
                    same += 1
                if kind == "패키지 줄" and o.count("⏎") != k.count("⏎"):
                    pages_diff += 1
                kinds[kind] = kinds.get(kind, 0) + 1
                for t in (mk.split(",") if mk else ["(표시 없음 — 양쪽에 글)"]):
                    counts[t] = counts.get(t, 0) + 1
    return {"rows": n, "same": same, "pages_diff": pages_diff, "skipped": list(SKIPPED), "mismatch": list(MISMATCH), "dead": list(DEAD_SITES), "kinds": kinds, "marks": counts, "unknown": kg.unknown, "static": kg.static_n}


def sha1(p) -> str:
    h = hashlib.sha1()
    with open(p, "rb") as fh:
        for ch in iter(lambda: fh.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


MANIFEST = """# 원판·한글 짝 표 — manifest (마스터 10-20)

- 원판 이미지: `{orig_name}` sha1 `{orig_sha}`
- 한글 이미지: 지금 HEAD 제품 이미지 sha1 `{ko_sha}` · {desc}
- 표: `pairs.tsv` — 열 = 번호 · 원판 · 한글 · 표시 · **{rows}줄**

## 분모
{kinds}
- 본편 패키지 {npk}개(`package.CLEAN`) — 메시지 덩이 줄을 전부 싣는다(대사 · 전투 덩이 · 이름 라벨 · 메뉴 덩이). 번호의 `=` 는 같은 덩이를 가리키는 메시지 번호들이다.

## 표시별 수
{marks}
- 참고(표시 넷에 안 든다): 양쪽 글이 **같은** 줄 {same} · 패키지 줄 중 쪽 넘김(⏎) 수가 **다른** 줄 {pages_diff}

## 방법
- 대본 JSON 이 아니라 **이미지의 바이트**다. 원판은 `common.track_data`(원판 이미지), 한글은 제품 이미지 섹터에서 읽는다. 촬영·에뮬 없음.
- 패키지 줄: 메시지 표(`package.msg_table`)로 번호 → 덩이, LZ 를 풀어(`package.decode_chunk`) `00` 으로 줄을 가른다. 원판·한글 모두 같은 번호의 덩이다.
- 프로그램 리터럴: 원판의 호출 자리(`JSR $503E/$4ED5/$4ED1` + `BIT`)마다 **한글 이미지의 같은 자리 피연산자**를 따라간다(같은 뱅크에서 옮긴 것 · 공용 중계로 먼 뱅크에 둔 것 둘 다). 한 문자열을 여러 자리가 부르면 `포인터 공유`, 자리마다 한글이 갈렸으면 `‖` 로 잇는다.
- 프로그램 표: 표 시작 즉치(`LDY #hi / LDX #lo`)를 한글 이미지에서 읽어 같은 항목 수만큼 따라간다. 코드 문자열(`codestr`): `BIT` 포인터를 따라간다.
- 한글 글자: 이미지의 **글리프 비트맵을 글꼴과 대조해 되읽는다**(정적 풀 {static}개 + 패키지 지역 표) — 못 읽은 글리프 {unknown}개. 한글 글리프 리드(`F0~F9`)가 든 줄만 한글 규칙으로 읽고, 없는 줄은 원판 글자 그대로(일본어)로 읽는다.
- 표기: 쪽 넘김 `13` = ⏎ · 줄바꿈 `0D` = ↵ · 이름·수 자리(`07` `1A` `1B`, 본 프로그램 문자열의 `13 nn`) = `{{name}}` · 동적 조사(`F9 nn`) = `{{josa}}` · 나머지 제어는 `{{HH 인자}}` 그대로 펼친다(`16 … 14` 화자 머리, `1C`·`1D` 분기, `0C` 창 호출, `10`·`11` 속도·멈춤 …).

## 한계
- 본편 밖 패키지(배틀 테스트 6 · 판정 불가 12 · 다른 타이틀 잔재 49 — `residual_gate`)와 대사가 아닌 꼬리 덩이({skipped_n}개: {skipped})는 싣지 않는다.
- 줄 수가 다른 덩이 {mismatch_n}개{mismatch}. 줄 번호는 그대로 맞대어 모자란 쪽이 비게 둔다.
- 죽은 디버그 문구(전투 디버그 출력, 호출자 0)는 한글 이미지에서 자리를 글리프 풀로 돌려줬으므로 뺐다({dead_n}곳).
- 이미지 안 **그림 글자·자체 글리프 후킹 문구**는 문자열 포인터 체계가 아니라 싣지 않았다 — 시스템 카드·백업 안내 4문(패키지 20) · 간판·말풍선 그림 · HUD 판 라벨.
- **자막**(오프닝 나레이션 · 대관식 성우 대사)은 원판에 글이 없고 한글 쪽도 스프라이트 셀·ADPCM 자료로 구워 문자열로 되읽히지 않는다 — 한글만 있는 줄이라 표에 없다.
- 쪽 넘김은 `13` 만 ⏎ 로 적는다(자동 넘김 `12` 는 `{{12}}` 그대로).
- 변수 자리는 종류를 가르지 않는다 — `1B` 는 수일 때도 `{{name}}` 으로 적힌다(전투 덩이에선 이름 버퍼 출력이다).
- 한글 줄 판별은 바이트(리드 `F0~F9`)로 한다 — 번역이 안 돼 일본어가 남은 줄은 원판과 같은 글자로 보인다(`참고` 의 같은 줄).
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--allow-stale", action="store_true")
    a = ap.parse_args()
    common.verify_originals()
    import romtag

    desc = romtag.check(a.iso, a.allow_stale)  # 지금 소스와 다른 롬이면 멈춘다(촬영과 같은 규율)
    r = build(a.iso, Path(a.out))
    sk, mm = r["skipped"], r["mismatch"]
    text = MANIFEST.format(
        orig_name=common.ORIG_ISO.name,
        orig_sha=common.ORIG_SHA1[common.ORIG_ISO.name],
        ko_sha=sha1(a.iso),
        desc=desc,
        rows=r["rows"],
        kinds="\n".join(f"- {k}: {v}줄" for k, v in r["kinds"].items()),
        npk=len(package.CLEAN),
        marks="\n".join(f"- {k}: {v}줄" for k, v in sorted(r["marks"].items())),
        same=r["same"],
        pages_diff=r["pages_diff"],
        static=r["static"],
        unknown=r["unknown"],
        skipped_n=len(sk),
        skipped=", ".join(sk) or "없음",
        mismatch_n=len(mm),
        mismatch=(": " + ", ".join(mm)) if mm else "",
        dead_n=len(r["dead"]),
    )
    (Path(a.out) / "manifest.md").write_text(text, encoding="utf-8")
    print(r["rows"], "줄", r["marks"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
