"""
재삽입기: ED1 전 씬(SCN1~6)의 고신뢰 정렬 블록을 DOS 한국어로 교체한 이미지 빌드.

씬별로 (README '재삽입 전략' 그대로):
 1. 앵커(점프 테이블) 고정 재배치 — 앵커와 겹치는 블록 pinned, 사이만 대사 reflow
 2. 코드의 lui+addiu/ori 텍스트 포인터를 새 주소로 패치 (lo>=0x8000이면 hi+1 보정)
 3. 한글 폰트(ED.EXE) 탑재 + 섹터 재패킹/EDC 재계산 → 한 이미지에 6씬 + 폰트

안전장치:
 - PILOT_IDENTITY=1: 번역 0건으로 돌려 원본과 바이트 동일 확인 (기계 정확성 검증)
 - PILOT_FIXED=1: 블록별 원본 길이 고정(무이동), PILOT_SCN=ED1SCN3: 특정 씬만
 - 앵커/블록 중간 참조/크기 초과/인코딩 불가는 해당 블록 번역 제외 후 보고
 - 공유 lui의 hi 충돌 시 해당 블록 제외 후 재배치 (수렴까지 반복)

입력: out/scn_jp/EDxSCNn.json + out/align/EDx_SCNn.json + out/dos_kr/ED1/*.json
출력: work/Eiyuu Densetsu (KR Pilot).bin/.cue
"""

import bisect
import json
import os
import re
import shutil

import hangul_map
from common import (
    MIPS_ADDIU,
    MIPS_LW,
    MIPS_ORI,
    OUT_DIR,
    WORK_DIR,
    extract,
    iter_lui_pairs,
    write_cue,
    write_user_data,
)
from common import ORIG_BIN as SRC

ED_LBA, ED_SIZE = 257, 1021952  # ED.EXE (폰트 탑재 대상)
OVERLAY_RAM_BASE = 0x8016A000  # SCN 오버레이 로드 주소 (ED1 전 씬 공통, 참조 커버리지로 검증)
# ED1 씬별 (이름, LBA, size) — extract_scn.py SCN_FILES. text_end는 scn_jp JSON에서 씬별로.
SCN_FILES = [
    ("ED1SCN1", 1183, 206260),
    ("ED1SCN2", 1284, 217940),
    ("ED1SCN3", 1391, 199084),
    ("ED1SCN4", 1489, 134184),
    ("ED1SCN5", 1555, 171392),
    ("ED1SCN6", 1639, 100270),
]
MC = b"\x25\x63"  # %c
WRAP = 14  # 줄 폭 (전각 기준 — 실측: 박스 자동줄바꿈이 ~14.5자에서 개입, 2026-07-09 스크린샷)
LINES_PER_PAGE = 3

DST = os.path.join(WORK_DIR, "Eiyuu Densetsu (KR Pilot).bin")
DST_CUE = os.path.join(WORK_DIR, "Eiyuu Densetsu (KR Pilot).cue")

HANGUL = re.compile(r"[가-힣]")


class SkipBlock(Exception):
    pass


# ── 한국어 → 게임 바이트 (hangul_map 확장: 구두점·숫자·라틴은 전각 SJIS) ────
def encode_ext(text):
    out = bytearray()
    for ch in text:
        if ch == " ":
            out.append(0x20)
        elif ch == "\n":
            out.append(0x0A)
        elif ch in hangul_map.SYL_INDEX:
            out += hangul_map.syllable_sjis(ch).to_bytes(2, "big")
        else:
            if 0x21 <= ord(ch) <= 0x7E:  # ASCII → 전각
                ch = chr(ord(ch) + 0xFEE0)
            try:
                b = ch.encode("cp932")
            except UnicodeEncodeError:
                raise SkipBlock(f"인코딩 불가: {ch!r}") from None
            if len(b) != 2 or not 0x81 <= b[0] <= 0x84:
                raise SkipBlock(f"글리프 범위 밖: {ch!r}")
            out += b
    return bytes(out)


# ── DOS 블록 텍스트 → (화자, 페이지 목록) ───────────────────────────────────
def parse_kr(entry):
    t = entry["text"]
    t = re.sub(r"^.*?\{/spk\}", "", t, count=1)  # 화자 마크업(+선행 opcode 노이즈) 제거
    t = t.replace("{n}", " ").replace("{end}", "")
    t = re.sub(r"\\x[0-9A-F]{2}|\{spk\}|\{/spk\}", "", t)
    pages = []
    for seg in t.split("{p}"):
        seg = re.sub(r"\s+", " ", seg).strip()
        m = HANGUL.search(seg)
        if not m:
            continue
        seg = seg[m.start() :] if m.start() < 4 else seg  # 선두 opcode 잔여 노이즈 절삭
        pages.append(seg)
    if not pages:
        raise SkipBlock("본문 없음")
    return entry["speaker"], pages


def wrap_page(text, width=WRAP):
    """공백 기준 그리디 줄바꿈 (전각=1, 공백·반각=0.5)."""

    def w(s):
        return sum(0.5 if ord(c) < 0x100 else 1 for c in s)

    lines, cur = [], ""
    for word in text.split(" "):
        cand = f"{cur} {word}" if cur else word
        if cur and w(cand) > width:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def build_block(speaker, pages):
    """PS1 블록 재구성: %c 화자 %c 0A 본문(페이지는 %c 구분) %c + 4바이트 정렬 00패딩."""
    lines = []
    for page in pages:
        lines += wrap_page(page)
    # 페이지 재구성: 3줄 단위
    chunks = [lines[i : i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)]
    body = MC.join(encode_ext("\n".join(c)) for c in chunks)
    blk = MC + encode_ext(speaker) + MC + b"\x0a" + body + MC
    pad = 4 - len(blk) % 4 or 4
    return blk + b"\x00" * pad


# ── 포인터 참조 수집 (공용 iter_lui_pairs 사용) ─────────────────────────────
def find_refs(data, text_end):
    """lui+addiu/ori 쌍으로 텍스트 영역을 가리키는 참조: [(addiu_off, lui_off, op, addr)]."""
    return [
        (imm_off, lui_off, op, addr)
        for imm_off, lui_off, op, addr in iter_lui_pairs(data, (MIPS_ADDIU, MIPS_ORI))
        if OVERLAY_RAM_BASE <= addr < OVERLAY_RAM_BASE + text_end
    ]


def patch_word_imm(buf, off, imm):
    wd = int.from_bytes(buf[off : off + 4], "little")
    buf[off : off + 4] = ((wd & 0xFFFF0000) | (imm & 0xFFFF)).to_bytes(4, "little")


def hi_lo(addr, op):
    lo = addr & 0xFFFF
    hi = (addr >> 16) + (1 if op == MIPS_ADDIU and lo >= 0x8000 else 0)
    return hi, lo


def compute_anchors(data, text_end):
    """텍스트 영역 내 lui+lw로 참조되는 데이터 테이블(점프 테이블 등)의 바이트 범위.

    코드가 절대주소로 읽으므로 절대 이동 금지 앵커다. 재배치 멈춤의 원인
    (2026-07-09 emucap 규명)이 바로 이 테이블이 대사에 밀려 어긋난 것.
    각 lui+lw base에서 오버레이 포인터(또는 null 슬롯)가 이어지는 동안을 테이블로 보고,
    인접 범위는 병합. 큰 쪽으로 근사(테이블을 조금 크게 잡으면 안전, 작으면 위험)."""
    lo, hi = OVERLAY_RAM_BASE, OVERLAY_RAM_BASE + len(data)  # 오버레이 전체 범위 (파일 크기)
    bases = {
        addr - OVERLAY_RAM_BASE
        for _, _, _, addr in iter_lui_pairs(data, (MIPS_LW,))
        if 0 <= addr - OVERLAY_RAM_BASE < text_end
    }

    def is_entry(v):
        return lo <= v < hi or v == 0  # 오버레이 포인터 또는 null 슬롯

    ranges = []
    for b in sorted(bases):
        if b % 4:
            continue  # 워드 정렬 안 된 우연 일치는 무시
        o = b
        while o + 4 <= text_end and is_entry(int.from_bytes(data[o : o + 4], "little")):
            o += 4
        if o > b:
            ranges.append((b, o))
    merged = []
    for s, e in sorted(ranges):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def reflow_run(region, run, run_start, run_end, translations, excluded, fixed, layout):
    """자유 구간 [run_start, run_end)(앵커 사이)에 자유 블록들을 재배치.

    총량이 구간 크기를 넘으면 성장폭 큰 번역부터 제외(size). fixed=True면
    블록별 원본 길이 고정(짧으면 00패딩). 남는 공간은 00패딩 — 앵커 위치 불변."""
    run_space = run_end - run_start
    news = []
    for b in run:
        new, eid = b["raw"], b["eid"]
        if eid in translations and eid not in excluded:
            try:
                cand = build_block(*translations[eid])
            except SkipBlock:
                excluded[eid] = "encode"
                cand = None
            if cand is not None:
                if fixed:
                    if len(cand) <= len(b["raw"]):
                        new = cand + b"\x00" * (len(b["raw"]) - len(cand))
                    else:
                        excluded[eid] = "size"
                else:
                    new = cand
        news.append(new)
    if not fixed:
        while sum(len(x) for x in news) > run_space:
            cands = [
                k
                for k, b in enumerate(run)
                if b["eid"] in translations and b["eid"] not in excluded and news[k] != b["raw"]
            ]
            if not cands:
                raise SystemExit(f"자유 구간 0x{run_start:X} 수용 불가 (원본조차 초과?)")
            k = max(cands, key=lambda k: len(news[k]) - len(run[k]["raw"]))
            excluded[run[k]["eid"]] = "size"
            news[k] = run[k]["raw"]
    assert sum(len(x) for x in news) <= run_space, "run 초과"
    pos = run_start
    for b, new in zip(run, news, strict=True):
        region[pos : pos + len(new)] = new
        layout.append((b["off"], len(b["raw"]), pos, len(new), b["eid"]))
        pos += len(new)
    for p in range(pos, run_end):  # 앞선 축소분 → 00패딩(다음 앵커 위치 고정)
        region[p] = 0


# ── 메인 ────────────────────────────────────────────────────────────────────
def _load_overrides():
    """사람 검수 교정(align_overrides.json). 없으면 빈 dict."""
    path = os.path.join(os.path.dirname(OUT_DIR), "align_overrides.json")
    if not os.path.exists(path):
        return {}
    return json.load(open(path, encoding="utf-8"))


def load_translations(align_name, scn_name):
    """정렬 고신뢰 쌍(+ 사람 검수 오버라이드) → {jp_entry_id: (화자, 페이지들)}."""
    align = json.load(open(os.path.join(OUT_DIR, "align", f"{align_name}.json"), encoding="utf-8"))
    kr_cache = {}

    def kr_entry(table, eid):
        if table not in kr_cache:
            doc = json.load(
                open(os.path.join(OUT_DIR, "dos_kr", f"{table}.json"), encoding="utf-8")
            )
            kr_cache[table] = {e["entry_id"]: e for e in doc["entries"]}
        return kr_cache[table][eid]

    out, skipped = {}, {}
    for p in align["pairs"]:
        if not p["jp"] or p["flags"]:
            continue
        entry = dict(kr_entry(p["kr"]["table"], p["kr"]["entry_id"]))
        entry["speaker"] = p["kr"]["speaker"]  # 승계 화자 반영
        try:
            spk, pages = parse_kr(entry)
            if not spk:
                raise SkipBlock("화자 없음")
            out[p["jp"]["entry_id"]] = (spk, pages)
        except SkipBlock as e:
            skipped[str(e)] = skipped.get(str(e), 0) + 1

    # 사람 검수 오버라이드: align보다 우선 (틀린 짝 교정 or 신규 추가)
    applied = 0
    for jp_id_str, ov in _load_overrides().get(scn_name, {}).items():
        if jp_id_str.startswith("_"):
            continue
        entry = dict(kr_entry(ov["table"], ov["entry_id"]))
        entry["speaker"] = ov.get("speaker") or entry.get("speaker")
        try:
            spk, pages = parse_kr(entry)
            final_spk = ov.get("speaker") or spk
            if not final_spk:  # 메인 경로와 동일 가드 — 화자 없는 블록은 대사로 승격 불가
                raise SkipBlock("화자 없음")
            out[int(jp_id_str)] = (final_spk, pages)
            applied += 1
        except SkipBlock as e:
            # 사람이 지정한 교정이 조용히 사라지면 안 된다 — 반드시 보고
            print(f"경고: {scn_name} 오버라이드 jp={jp_id_str} 적용 실패 ({e}) — 수정 필요")
    return out, skipped, applied


def rebuild(scn_entries, data, translations, excluded, anchors, text_end, fixed=False):
    """앵커(테이블) 고정 재배치. 반환: (region, old→new 오프셋 매핑 블록 목록).

    앵커와 겹치는 블록은 pinned(원본 위치·바이트 그대로) — 테이블 보존.
    나머지 자유 블록은 앵커 사이 구간에서만 재배치(reflow_run). 앵커는 절대 안 움직여
    lui+lw 절대참조가 유효하게 유지된다. fixed=True는 블록별 원본 길이 고정."""
    blocks = []
    for e in scn_entries:
        off = int(e["file_offset"], 16)
        raw = bytes.fromhex(e["raw_hex"])
        assert data[off : off + len(raw)] == raw, f"scn_jp raw 불일치 @{e['entry_id']}"
        blocks.append({"off": off, "raw": raw, "eid": e["entry_id"]})

    def hits_anchor(s, e):
        return any(s < ae and a_s < e for a_s, ae in anchors)

    for b in blocks:
        b["pinned"] = hits_anchor(b["off"], b["off"] + len(b["raw"]))
        if b["pinned"] and b["eid"] in translations:
            excluded[b["eid"]] = "anchor_overlap"

    region = bytearray(data[:text_end])  # 앵커·pinned는 원본 그대로 유지
    layout = []
    i, n = 0, len(blocks)
    while i < n:
        if blocks[i]["pinned"]:
            b = blocks[i]
            layout.append((b["off"], len(b["raw"]), b["off"], len(b["raw"]), b["eid"]))
            i += 1
            continue
        j = i
        while j < n and not blocks[j]["pinned"]:
            j += 1
        run = blocks[i:j]
        run_start = run[0]["off"]
        run_end = blocks[j]["off"] if j < n else text_end
        reflow_run(region, run, run_start, run_end, translations, excluded, fixed, layout)
        i = j
    return bytes(region), layout


def build_scene(name, lba, size, identity, fixed):
    """한 SCN 오버레이를 번역·재배치·포인터 패치. 반환: (patched_bytes, stats_str).

    identity=True면 검증만(원본과 바이트 동일 확인, 반환 bytes=None)."""
    data = extract(lba, size)
    scn = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{name}.json"), encoding="utf-8"))
    entries = scn["entries"]
    text_end = int(scn["source"]["text_end"], 16)
    align_name = name.replace("SCN", "_SCN")  # ED1SCN1 → ED1_SCN1

    translations, skipped, applied = (
        ({}, {}, 0) if identity else load_translations(align_name, name)
    )
    refs = find_refs(data, text_end)
    anchors = compute_anchors(data, text_end)

    block_offs = sorted(
        (int(e["file_offset"], 16), e["entry_id"]) for e in entries if e["kind"] != "gap"
    )
    offs_only = [o for o, _ in block_offs]

    def owner(off):
        i = bisect.bisect_right(offs_only, off) - 1
        return block_offs[i], off - block_offs[i][0]

    excluded = {}
    for _, _, _, addr in refs:
        (_, eid), delta = owner(addr - OVERLAY_RAM_BASE)
        if delta and eid in translations:
            excluded[eid] = "mid_block_ref"

    # 공유 lui 충돌 해소 루프
    for _ in range(5):
        region, layout = rebuild(entries, data, translations, excluded, anchors, text_end, fixed)
        newoff = {eid: (no, oo) for oo, _, no, _, eid in layout}
        lui_need, conflict = {}, None
        for addiu_off, lui_off, op, addr in refs:
            if addiu_off < text_end or lui_off < text_end:
                continue  # 텍스트 영역 내 우연 일치 — 패치 단계와 동일 필터 (오탐 충돌 방지)
            (_, eid), delta = owner(addr - OVERLAY_RAM_BASE)
            hi, _ = hi_lo(OVERLAY_RAM_BASE + newoff[eid][0] + delta, op)
            if lui_off in lui_need and lui_need[lui_off][0] != hi:
                conflict = (eid, lui_need[lui_off][1])
                break
            lui_need[lui_off] = (hi, eid)
        if not conflict:
            break
        for eid in conflict:
            if eid in translations:
                excluded[eid] = "shared_lui_conflict"
    else:
        raise SystemExit(f"{name}: 공유 lui 충돌 미수렴")

    # 파일 재조립 + 포인터 패치 (코드 영역만)
    out_file = bytearray(data)
    out_file[:text_end] = region
    patched = 0
    for addiu_off, lui_off, op, addr in refs:
        if addiu_off < text_end or lui_off < text_end:
            continue  # 텍스트 영역 내 우연 일치는 패치 대상 아님
        (_, eid), delta = owner(addr - OVERLAY_RAM_BASE)
        new_addr = OVERLAY_RAM_BASE + newoff[eid][0] + delta
        if fixed:
            assert new_addr == addr, f"{name} fixed 모드에서 주소 이동: {addr:#x}→{new_addr:#x}"
            continue
        hi, lo = hi_lo(new_addr, op)
        patch_word_imm(out_file, lui_off, hi)
        patch_word_imm(out_file, addiu_off, lo)
        patched += 1

    if identity:
        assert bytes(out_file) == data, f"{name}: 아이덴티티 라운드트립 실패"
        return None, f"{name}: 라운드트립 OK (포인터 {patched}건 = 원본 동일)"

    n_tr = sum(1 for _, _, _, _, eid in layout if eid in translations and eid not in excluded)
    used = sum(nl for _, _, _, nl, _ in layout)
    parse_skip = f", 파싱제외 {sum(skipped.values())}" if skipped else ""
    ov = f", 검수교정 {applied}" if applied else ""
    stats = (
        f"{name}: 재삽입 {n_tr}블록 (후보 {len(translations)}, 제외 {len(excluded)}"
        f"{sorted(set(excluded.values()))}{parse_skip}{ov}, 포인터 {patched}건, "
        f"사용 0x{used:X}/0x{text_end:X})"
    )
    return out_file, stats


def main():
    identity = os.environ.get("PILOT_IDENTITY") == "1"  # 번역 0건 라운드트립 검증 모드
    fixed = os.environ.get("PILOT_FIXED") == "1"  # 길이 고정 모드 (블록 무이동 — 포인터 격리)
    only = os.environ.get("PILOT_SCN")  # 특정 씬만 (예: ED1SCN1). 미지정=전 씬
    if not os.path.exists(SRC):
        raise SystemExit(
            "원본 이미지 없음 — originals/ps1-eiyuu12/에 .bin/.cue를 복사한 뒤 재실행\n"
            f"  기대 경로: {os.path.relpath(SRC, os.path.dirname(OUT_DIR))}"
        )
    scenes = [s for s in SCN_FILES if not only or s[0] == only]
    if not scenes:
        raise SystemExit(f"PILOT_SCN={only} 는 SCN_FILES에 없음")

    built = {}  # lba → patched bytes
    total_tr = 0
    for name, lba, size in scenes:
        out_file, stats = build_scene(name, lba, size, identity, fixed)
        print(stats)
        if out_file is not None:
            built[lba] = out_file
            total_tr += int(stats.split("재삽입 ")[1].split("블록")[0])
    if identity:
        print("전 씬 아이덴티티 라운드트립 OK")
        return
    print(f"\n총 재삽입 {total_tr}블록 ({len(built)}씬)")

    # 폰트 + 이미지 기록 (전 씬 + ED.EXE 폰트를 한 이미지에)
    import hangul_font  # numpy/PIL 의존 — 빌드 단계에서만 필요

    print("Galmuri11 폰트 변환·탑재 중...")
    glyphs = hangul_font.convert_chars(hangul_map.SYLLABLES)
    font_block = b"".join(glyphs[ch] for ch in hangul_map.SYLLABLES)
    base_off = hangul_map.slot_ed_offset(0)

    suffix = " Fixed" if fixed else ""
    dst = DST.replace("Pilot", "Pilot" + suffix) if fixed else DST
    dst_cue = DST_CUE.replace("Pilot", "Pilot" + suffix) if fixed else DST_CUE
    os.makedirs(WORK_DIR, exist_ok=True)
    shutil.copyfile(SRC, dst)
    with open(dst, "r+b") as f:
        ed = bytearray(extract(ED_LBA, ED_SIZE))
        ed[base_off : base_off + len(font_block)] = font_block
        print(f"ED.EXE: 섹터 {write_user_data(f, ED_LBA, ed)}개 수정 (폰트)")
        for lba, out_file in built.items():
            print(f"  LBA {lba}: 섹터 {write_user_data(f, lba, out_file)}개 수정")
    write_cue(dst_cue, os.path.basename(dst))
    print(f"완료:\n  {dst}\n  {dst_cue}")


if __name__ == "__main__":
    main()
