"""
DOS 정발판(만트라) 한국어 대사 추출기 — 씬별 DLL의 인라인 텍스트를 JSON으로 덤프.

대상 (originals/kr/, gitignore):
 - ED1: SINDLL/*.DLL (225파일)   - ED2: SCENA/*.DLL (파일 입수 시 자동 처리)

DLL 구조 (실측, 2026-07-09):
 - MZ 헤더 + 공용 인터프리터 스텁 (전 파일 공통 prefix, ED1은 0xF64 — 런타임 계산)
 - 씬별 x86 스크립트 코드에 CP949 평문 대사가 인라인으로 박힘
 - 제어코드: 1E <화자명> 04 = 화자 지정, 01 = 개행, 05 = 페이지 전환, 00 = 메시지 종료

원칙(vendor/create-retro-game-kr-patch text-extraction.md):
 - raw_hex 보존 + 라운드트립 검증 (블록·갭 이어붙이면 텍스트 영역과 바이트 동일)
 - 코드/텍스트 혼재 영역이므로 방법 B(영역+런 스캔): 한글 런을 클러스터링해 블록화,
   블록 사이 코드는 kind="gap"으로 보존. 버려진 고립 런은 통계로 보고 (침묵 누락 방지)

출력: out/dos_kr/<게임>/<파일>.json  (scn_jp와 동일 계열 스키마)
"""

import json
import os
import re

from common import OUT_DIR, ROOT

KR_DIR = os.path.join(ROOT, "..", "..", "originals", "kr")
GAMES = {"ED1": "SINDLL", "ED2": "SCENA"}

# KS X 1001 2바이트 런: 한글(B0-C8) + 특수문자행(A1-AF), 2연속 이상
KR_RUN = re.compile(rb"(?:[\xb0-\xc8\xa1-\xaf][\xa1-\xfe]){2,}")
HANGUL_PAIR = re.compile(rb"[\xb0-\xc8][\xa1-\xfe]")
# 화자 마커: 1E <화자(2바이트 한글/ASCII 혼용, 12자 이내)> 04
SPEAKER = re.compile(rb"\x1e((?:[\xb0-\xc8][\xa1-\xfe]|[\x20-\x7e]){1,24}?)\x04")

MERGE_GAP = 8  # 이 바이트 수 이하의 코드 갭은 같은 블록으로 병합 (인라인 opcode 흡수)
MIN_HANGUL = 4  # 클러스터 최소 한글 자수 (미달 시 아래 보조 신호 없으면 코드 오탐으로 드랍)
CTRL = {0x01: "{n}", 0x05: "{p}", 0x00: "{end}", 0x1E: "{spk}", 0x04: "{/spk}"}

# 짧은 클러스터 구제 신호: 한글 뒤 문장부호/공백 (실문장 조각 — '얻었다.' '그럼 ' 등)
HANGUL_PUNCT = re.compile(rb"[\xb0-\xc8][\xa1-\xfe][ .?!,\x01\x05]")
PARTIAL_SPEAKER = re.compile(rb"\x1e[\xb0-\xc8]")  # 04가 잘려도 화자 마커로 인정


def common_prefix_len(datas):
    """전 파일 공통 prefix 길이 = 공용 인터프리터 스텁 경계 (스캔 시작점)."""
    d0 = min(datas, key=len)
    n = len(d0)
    for d in datas:
        while n and d[:n] != d0[:n]:
            n -= 1
    return n


def valid_kr(raw):
    try:
        raw.decode("cp949")
        return True
    except UnicodeDecodeError:
        return False


def find_segments(data, start):
    """한글 런을 씨앗으로 텍스트 세그먼트 수집. 앞의 1E 마커, 뒤의 ASCII·제어코드 흡수."""
    segs = []
    n = len(data)
    for m in KR_RUN.finditer(data, start):
        if not valid_kr(m.group()):
            continue
        s, e = m.start(), m.end()
        if s and data[s - 1] == 0x1E:  # 화자 마커 시작
            s -= 1
        while e < n and (0x20 <= data[e] <= 0x7E or data[e] in (0x01, 0x05)):
            e += 1
        if data[s] == 0x1E and e < n and data[e] == 0x04:
            e += 1  # 화자 마커 종결 04 흡수 (SPEAKER 매치 보장)
        segs.append((s, e))
    return segs


def merge_segments(data, segs):
    """근접 세그먼트를 클러스터로 병합 + 종료 00 흡수. 반환: [(s, e)]."""
    merged = []
    for s, e in segs:
        if merged and s - merged[-1][1] <= MERGE_GAP:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    for c in merged:
        if c[1] < len(data) and data[c[1]] == 0x00:
            c[1] += 1  # 메시지 종료자 포함 (재삽입 시 경계 명확화)
    return [(s, e) for s, e in merged]


def cluster_ok(data, s, e):
    """코드 오탐 필터. 유지 조건: 한글 자수 충분 / 화자 마커 / 문장부호 동반 짧은 조각."""
    raw = data[s:e]
    if len(HANGUL_PAIR.findall(raw)) >= MIN_HANGUL:
        return True
    if SPEAKER.search(raw) or PARTIAL_SPEAKER.search(raw):
        return True
    return bool(HANGUL_PUNCT.search(raw))


def split_blocks(data, s, e):
    """클러스터를 메시지 블록으로 분할: 00 종료자 뒤, 화자 마커(1E) 앞에서 절단."""
    cuts = {s, e}
    for m in SPEAKER.finditer(data, s, e):
        cuts.add(m.start())
    for i in range(s, e):
        if data[i] == 0x00:  # 종료자 — 뒤에서 절단 (00은 앞 블록에 귀속)
            cuts.add(i + 1)
    edges = sorted(cuts)
    return [(a, b) for a, b in zip(edges, edges[1:], strict=False) if a < b]


def decode(raw):
    """raw → 읽기용 텍스트 (제어코드는 태그, 미해독 바이트는 \\xNN). raw가 정본."""
    out = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if b in CTRL:
            out.append(CTRL[b])
            i += 1
        elif 0xA1 <= b <= 0xC8 and i + 1 < len(raw) and valid_kr(raw[i : i + 2]):
            out.append(raw[i : i + 2].decode("cp949"))
            i += 2
        elif 0x20 <= b <= 0x7E:
            out.append(chr(b))
            i += 1
        else:
            out.append(f"\\x{b:02X}")
            i += 1
    return "".join(out)


def parse_file(data, code_end):
    """DLL 1개 → (entries, 드랍 목록). entries는 텍스트 영역을 빈틈없이 커버."""
    segs = find_segments(data, code_end)
    clusters = merge_segments(data, segs)
    kept, dropped = [], []
    for s, e in clusters:
        (kept if cluster_ok(data, s, e) else dropped).append((s, e))
    if not kept:
        return [], dropped

    entries = []
    pos = kept[0][0]
    for cs, ce in kept:
        if pos < cs:  # 클러스터 사이 코드
            entries.append((pos, data[pos:cs], "gap"))
        for bs, be in split_blocks(data, cs, ce):
            raw = data[bs:be]
            # 분할 조각에 한글도 화자 마커도 없으면 코드 조각 — gap으로 재분류
            kind = "block" if HANGUL_PAIR.search(raw) or PARTIAL_SPEAKER.search(raw) else "gap"
            entries.append((bs, raw, kind))
        pos = ce
    return entries, dropped


def block_fields(raw):
    """블록의 화자·flags 추출."""
    speaker = None
    flags = []
    m = SPEAKER.match(raw)
    if m:
        speaker = m.group(1).decode("cp949")
        body = raw[m.end() :]
    else:
        body = raw
        flags.append("no_speaker")  # 직전 블록 화자 승계 추정
    if not HANGUL_PAIR.search(body):
        flags.append("no_body")
    return speaker, flags


def dump_game(game, subdir):
    src_dir = os.path.join(KR_DIR, game, subdir)
    if not os.path.isdir(src_dir):
        print(f"{game}: {game}/{subdir} 없음 — 건너뜀 (원본 입수 후 재실행)")
        return 0
    # "._*" = macOS AppleDouble 잔재 — 섞이면 공용 prefix 계산이 무너짐
    files = sorted(
        f for f in os.listdir(src_dir) if f.upper().endswith(".DLL") and not f.startswith("._")
    )
    if not files:
        raise SystemExit(f"{src_dir}: DLL 파일 없음 — 원본 배치 확인")
    datas = {}
    for fname in files:
        with open(os.path.join(src_dir, fname), "rb") as f:
            datas[fname] = f.read()
    code_end = common_prefix_len(list(datas.values()))
    out_dir = os.path.join(OUT_DIR, "dos_kr", game)
    os.makedirs(out_dir, exist_ok=True)

    grand_blocks = empty = 0
    audit = []  # 드랍된 고립 런 감사 기록 (침묵 누락 방지)
    for fname, data in datas.items():
        stem = fname.rsplit(".", 1)[0]
        entries, dropped = parse_file(data, code_end)
        for s, e in dropped:
            audit.append(
                {"file": fname, "offset": f"0x{s:X}", "text": data[s:e].decode("cp949", "replace")}
            )

        # 라운드트립: 이어붙이면 텍스트 영역과 동일 + 각 raw가 파일 바이트와 일치
        if entries:
            text_start = entries[0][0]
            text_end = entries[-1][0] + len(entries[-1][1])
            rebuilt = b"".join(raw for _, raw, _ in entries)
            assert rebuilt == data[text_start:text_end], f"{game}/{stem}: 라운드트립 실패"
        else:
            text_start = text_end = 0
            empty += 1

        docs = []
        for idx, (off, raw, kind) in enumerate(entries):
            ent = {
                "entry_id": idx,
                "file_offset": f"0x{off:X}",
                "kind": kind,
                "raw_hex": raw.hex(),
                "text": decode(raw) if kind == "block" else "",
            }
            if kind == "block":
                speaker, flags = block_fields(raw)
                ent["speaker"] = speaker
                ent["flags"] = flags
            docs.append(ent)
        n_blocks = sum(1 for _, _, k in entries if k == "block")
        grand_blocks += n_blocks
        doc = {
            "table_id": f"{game}/{stem}",
            "source": {
                "file": f"{game}/{subdir}/{fname}",
                "size": len(data),
                "code_end": f"0x{code_end:X}",
                "text_start": f"0x{text_start:X}",
                "text_end": f"0x{text_end:X}",
                "method": "B",
                "encoding": "cp949",
            },
            "entry_count": len(docs),
            "block_count": n_blocks,
            "entries": docs,
        }
        with open(os.path.join(out_dir, f"{stem}.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)

    with open(os.path.join(out_dir, "_dropped.json"), "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=1)
    print(
        f"{game}: {len(files)}파일 → 블록 {grand_blocks}개 "
        f"(텍스트 없음 {empty}파일, 고립 런 드랍 {len(audit)}건 → _dropped.json)"
    )
    return grand_blocks


def main():
    total = 0
    for game, subdir in GAMES.items():
        total += dump_game(game, subdir)
    print(f"\n총 블록 {total}개 (전 파일 라운드트립 OK)")


if __name__ == "__main__":
    main()
