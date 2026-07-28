"""
PS1 일문 대사 추출기 — SCN 파일(오버레이)의 텍스트 블록을 JSON으로 덤프.

SCN 구조(리버싱 노트 참조): [헤더 지명] + 반복 블록 `%c 화자 %c ␊ 본문 %c` + 00패딩,
그 뒤 0x13208~ 등부터 MIPS 이벤트 코드. 텍스트 영역만 추출한다.

원칙(vendor/create-retro-game-kr-patch text-extraction.md):
 - raw_hex 보존 → 디코더 버그와 무관하게 원본 바이트 1:1 복원
 - 라운드트립 검증: 파싱 결과 재직렬화 == 원본 텍스트 영역 (바이트 동일)
 - 텍스트 영역 밖(코드)은 제외

출력: out/scn_jp/<파일>.json  (테이블 단위)
"""

import json
import os
import re

from common import OUT_DIR, extract

# 4+ 연속 SJIS 전각 문자 (텍스트 영역 판별용, 코드엔 드묾)
SJIS_RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]){4,}")

# ISO 파일: (이름, LBA, size) — iso_files.txt에서
SCN_FILES = [
    ("ED1SCN1", 1183, 206260),
    ("ED1SCN2", 1284, 217940),
    ("ED1SCN3", 1391, 199084),
    ("ED1SCN4", 1489, 134184),
    ("ED1SCN5", 1555, 171392),
    ("ED1SCN6", 1639, 100270),
    ("ED2SCN1", 1688, 94200),
    ("ED2SCN2", 1734, 116288),
    ("ED2SCN3", 1791, 195954),
    ("ED2SCN4", 1887, 164280),
    ("ED2SCN5", 1968, 138004),
    ("ED2SCN6", 2036, 89700),
    ("ED2SCN7", 2080, 106456),
    ("ED2SCN8", 2132, 102848),
    ("ED2SCN9", 2183, 101772),
    ("ED2SCN10", 2233, 79332),
    ("ED2SCN11", 2272, 105648),
    ("ED2SCN12", 2324, 97345),
    ("ED2SCN13", 2372, 72288),
]

MC = b"\x25\x63"  # %c 마커
CTRL = {0x0A: "{n}", 0x20: " ", 0xA5: "·"}  # 개행/공백/반각 가운뎃점


def is_sjis_lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF


def find_text_end(data):
    """텍스트 영역 끝(코드 시작): 마지막 유효 SJIS 런(4+)의 끝 뒤, 다음 00패딩까지.
    SCN 오버레이는 텍스트 뒤에 MIPS 코드가 오는데 코드엔 4+ SJIS 런이 드물다."""
    last_end = 0
    for m in SJIS_RUN.finditer(data):
        try:
            m.group().decode("cp932")
        except UnicodeDecodeError:
            continue
        last_end = m.end()
    # 마지막 문자열 뒤의 블록 종료 %c·00패딩까지 포함
    j = last_end
    while j < len(data) and data[j] != 0x00:
        j += 2 if data[j : j + 2] == MC else 1
    while j < len(data) and data[j] == 0x00:
        j += 1
    return j


def parse_blocks(region):
    """텍스트 영역을 00패딩 경계로 블록 분할. 패딩도 보존해 라운드트립 무손실."""
    blocks = []
    i = 0
    n = len(region)
    # 헤더(선두 지명): 첫 %c 전까지
    first_mc = region.find(MC)
    if first_mc > 0:
        blocks.append((0, region[:first_mc], "header"))
        i = first_mc
    while i < n:
        # 블록 = 다음 00런까지 (00런 포함)
        j = i
        while j < n and not (region[j] == 0x00 and region[j : j + 2] != MC):
            j += 2 if region[j : j + 2] == MC else 1
        # 00 런 흡수
        k = j
        while k < n and region[k] == 0x00:
            k += 1
        blocks.append((i, region[i:k], "block"))
        i = k
    return blocks


def decode(raw):
    """raw → 읽기용 텍스트 (제어코드는 태그, %c는 {c})."""
    out = []
    i = 0
    while i < len(raw):
        if raw[i : i + 2] == MC:
            out.append("{c}")
            i += 2
        elif raw[i] in CTRL:
            out.append(CTRL[raw[i]])
            i += 1
        elif raw[i] == 0x00:
            i += 1  # 패딩은 표시 생략
        elif is_sjis_lead(raw[i]) and i + 1 < len(raw):
            try:
                out.append(raw[i : i + 2].decode("cp932"))
                i += 2
            except UnicodeDecodeError:
                out.append(f"\\x{raw[i]:02X}")
                i += 1
        else:
            out.append(f"\\x{raw[i]:02X}")
            i += 1
    return "".join(out)


def main():
    out_dir = os.path.join(OUT_DIR, "scn_jp")
    os.makedirs(out_dir, exist_ok=True)
    grand_blocks = 0
    for name, lba, size in SCN_FILES:
        data = extract(lba, size)
        text_end = find_text_end(data)
        region = data[:text_end]
        blocks = parse_blocks(region)

        # 라운드트립: 블록 raw 이어붙이면 region과 동일해야 함
        rebuilt = b"".join(b for _, b, _ in blocks)
        assert rebuilt == region, f"{name}: 라운드트립 실패 ({len(rebuilt)} vs {len(region)})"

        entries = []
        for idx, (off, raw, kind) in enumerate(blocks):
            entries.append(
                {
                    "entry_id": idx,
                    "file_offset": f"0x{off:X}",
                    "kind": kind,
                    "raw_hex": raw.hex(),
                    "text": decode(raw),
                }
            )
        text_blocks = sum(1 for _, _, k in blocks if k == "block")
        grand_blocks += text_blocks
        doc = {
            "table_id": name,
            "source": {"lba": lba, "size": size, "text_end": f"0x{text_end:X}", "method": "C"},
            "entry_count": len(entries),
            "entries": entries,
        }
        with open(os.path.join(out_dir, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        print(f"{name}: 텍스트끝 0x{text_end:X}, 블록 {text_blocks} (라운드트립 OK)")

    print(f"\n총 텍스트 블록 {grand_blocks}개 → {out_dir}")


if __name__ == "__main__":
    main()
