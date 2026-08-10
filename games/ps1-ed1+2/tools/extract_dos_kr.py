"""
DOS 정발판(만트라) 한국어 대사 추출기 — 씬별 DLL의 인라인 텍스트를 JSON으로 덤프.

대상 (originals/kr/, gitignore):
 - ED1: dos-ed1/SINDLL/*.DLL (225파일) + dos-ed1/MONDLL/*.DLL (보스 등장·격파·드롭 문구)
 - ED2: dos-ed2/SCENA/*.DLL

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
# 논리 게임 ID → (originals/kr 하위 폴더, 대사 DLL 폴더).
# ID("ED1")는 out/ 산출물·정렬 키에 쓰이므로 originals 폴더명과 분리해 둔다.
# ⚠ **대사가 SINDLL 에만 있는 게 아니다.** 보스 등장·격파·드롭 문구는 `MONDLL/M0NN.DLL`
# 에 산다(유혈의 동굴 가르고 격파문이 미번역으로 남아 발견, 유저 QA 2026-08-07).
# 폴더마다 공용 스텁 prefix 가 다르므로 **폴더 단위로 따로 재고** 산출물만 한 이름공간에 모은다.
GAMES = {"ED1": ("dos-ed1", ["SINDLL", "MONDLL"]), "ED2": ("dos-ed2", ["SCENA"])}

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


# gap 승격에서 허용하는 저바이트 제어코드(정발 대사에 실제로 섞여 나오는 것들)
_CTRL_OK = frozenset(range(0x00, 0x11)) | {0x14, 0x1E}


def gap_is_text(raw):
    """코드로 분류된 조각이 사실 **텍스트**인가 — `KR_RUN` 이 못 본 자리를 되찾는다.

    **왜(2026-08-06).** `KR_RUN` 은 한글이 **연속 2자 이상**(`{2,}`)이라야 씨앗으로 삼는다.
    그래서 `좋{n}을 것 `(T_042#11)처럼 **글자마다 제어코드·공백이 끼는** 조각은 세그먼트가
    아예 안 생기고 클러스터 사이 코드(gap)로 떨어진다. 전수 **145건**이고, 무기점 문안이
    `사시는게` 에서 끊기던 원인이 이거였다(`check_text_health ①`).

    ⚠ **세그먼트 규칙은 못 건드린다** — 경계가 바뀌면 `entry_id` 가 밀려 `align_map` ·
    `align_overrides` 의 좌표가 통째로 어긋난다. gap 도 이미 인덱스를 차지하므로 **분류만**
    바로잡으면 번호가 안 밀린다.

    판정은 보수적으로 — 한글+부호가 있고, 바이트가 **전부** 한글쌍·ASCII·알려진 제어코드이며,
    `0xFF` 가 없고 `0x00` 은 꼬리에만 있다(코드 조각은 `9affff0000` 류 포인터를 물고 있다)."""
    if not HANGUL_PUNCT.search(raw) or b"\xff" in raw:
        return False
    if raw.count(b"\x00") > 1 or (b"\x00" in raw and not raw.endswith(b"\x00")):
        return False
    i, n = 0, len(raw)
    while i < n:
        b = raw[i]
        if 0xA1 <= b <= 0xC8 and i + 1 < n and 0xA1 <= raw[i + 1] <= 0xFE:
            i += 2
        elif 0x20 <= b <= 0x7E or b in _CTRL_OK:
            i += 1
        else:
            return False
    return True


# gap 꼬리에 붙은 본문 — 한글쌍·공백·문장부호만으로 이뤄진 **끝자락**
_GAP_TAIL = re.compile(rb"(?:[\xb0-\xc8\xa1-\xaf][\xa1-\xfe]|[ .,!?])+$")


def gap_text(raw):
    """이 gap 조각에서 **본문으로 쓸 부분**(없으면 None).

    조각 전체가 텍스트면 그대로, 아니면 **끝에 붙은 깨끗한 한글 꼬리**를 돌려준다.

    **왜(2026-08-07).** 정발은 짧은 도입부(`왜 `·`앗 !? `·`게, `)를 **제어바이트 덩어리
    뒤에** 붙여 둔다(`T_100#17` = `…\x00\x01왜 ` → 다음 블록이 `울고 있니?`). 조각 전체로는
    `0x00` 이 섞여 `gap_is_text` 를 통과 못 하니 **꼬리만** 살린다. 전수 122건이고, 안 살리면
    화면에 `울고 있니?` 처럼 첫 낱말이 빠진 채 나간다(유저 QA 2026-08-07).

    ⚠ 이때 `text` 는 raw 전체의 디코드가 **아니다** — 앞의 제어바이트는 버린다.
    `raw_hex` 가 정본이라는 규약(모듈 도크스트링)은 그대로다.
    ⚠ **엔트리를 쪼개면 안 된다** — 번호가 밀려 `align_map` 좌표가 통째로 어긋난다."""
    if gap_is_text(raw):
        return raw
    m = _GAP_TAIL.search(raw)
    return m.group() if m and len(m.group()) >= 3 else None


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
        if pos < cs:  # 클러스터 사이 코드 — 사실은 텍스트인 조각을 되찾는다(gap_text)
            raw = data[pos:cs]
            body = gap_text(raw)
            # ⚠ 네 번째 칸 = **본문으로 쓸 조각**(None = raw 전체). gap 승격분만 꼬리를 쓴다 —
            # 정상 블록에 `gap_text` 를 걸면 본문이 꼬리만 남는다(2026-08-07 실측: `T_022#11`
            # 이 125B 인데 `코웃음을 치면서 가 버렸다.` 만 남아 체인이 통째로 깨졌다).
            entries.append((pos, raw, "block" if body else "gap", body))
        for bs, be in split_blocks(data, cs, ce):
            raw = data[bs:be]
            # 분할 조각에 한글도 화자 마커도 없으면 코드 조각 — gap으로 재분류
            kind = "block" if HANGUL_PAIR.search(raw) or PARTIAL_SPEAKER.search(raw) else "gap"
            entries.append((bs, raw, kind, None))
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


def dump_game(game, src_sub, subdirs):
    if isinstance(subdirs, str):
        subdirs = [subdirs]
    out_dir = os.path.join(OUT_DIR, "dos_kr", game)
    os.makedirs(out_dir, exist_ok=True)

    # (파일명, 바이트, 그 폴더의 공용 prefix 길이, 폴더명) — prefix 는 **폴더마다** 다르다
    todo, n_files = [], 0
    for subdir in subdirs:
        src_dir = os.path.join(KR_DIR, src_sub, subdir)
        if not os.path.isdir(src_dir):
            print(f"{game}: kr/{src_sub}/{subdir} 없음 — 건너뜀 (원본 입수 후 재실행)")
            continue
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
        ce = common_prefix_len(list(datas.values()))
        todo += [(fname, data, ce, subdir) for fname, data in datas.items()]
        n_files += len(files)
    if not todo:
        return 0

    grand_blocks = empty = 0
    audit = []  # 드랍된 고립 런 감사 기록 (침묵 누락 방지)
    for fname, data, code_end, subdir in todo:
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
            rebuilt = b"".join(raw for _, raw, _, _ in entries)
            assert rebuilt == data[text_start:text_end], f"{game}/{stem}: 라운드트립 실패"
        else:
            text_start = text_end = 0
            empty += 1

        docs = []
        for idx, (off, raw, kind, body) in enumerate(entries):
            ent = {
                "entry_id": idx,
                "file_offset": f"0x{off:X}",
                "kind": kind,
                "raw_hex": raw.hex(),
                # ⚠ gap 에서 승격된 조각은 **꼬리만** 본문이다(`gap_text` 도크스트링)
                "text": decode(body if body is not None else raw) if kind == "block" else "",
            }
            if kind == "block":
                speaker, flags = block_fields(raw)
                ent["speaker"] = speaker
                ent["flags"] = flags
            docs.append(ent)
        n_blocks = sum(1 for _, _, k, _ in entries if k == "block")
        grand_blocks += n_blocks
        doc = {
            "table_id": f"{game}/{stem}",
            "source": {
                "file": f"{src_sub}/{subdir}/{fname}",
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
        f"{game}: {n_files}파일 → 블록 {grand_blocks}개 "
        f"(텍스트 없음 {empty}파일, 고립 런 드랍 {len(audit)}건 → _dropped.json)"
    )
    return grand_blocks


def main():
    total = 0
    for game, (src_sub, subdirs) in GAMES.items():
        total += dump_game(game, src_sub, subdirs)
    print(f"\n총 블록 {total}개 (전 파일 라운드트립 OK)")


if __name__ == "__main__":
    main()
