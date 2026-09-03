"""새턴 SCN/MON/본체의 텍스트 블록 덤프 → work/derived/scn_jp/<파일>.json

구조 (2026-08-19 정적 실측 — 근거는 docs/status.md):
  파일 = [지역 모듈]+  ·  모듈 = [지명 헤더][SH-2 코드][텍스트]
  텍스트 참조는 리터럴 풀의 BE32 절대 주소. 로드 베이스는 파일군마다 고정:
    ED.BIN·ED2.BIN 0x06028000 / ED1SCN* 0x060D0000 / ED2SCN* 0x060B8000 / ED2MON* 0x060E0000
  전 파일에서 %c 블록 포인터 커버리지 100% 확인(ED2SCN04 는 대사 없음).

덤프 단위는 「포인터가 가리키는 널 종단 문자열」이다 — 블록 시작만이 아니라
화자 스킵 체인·지명·시스템 서식 문자열도 전부 개별 entry 로 남긴다.
재삽입 때 고쳐야 하는 게 정확히 이 포인터들이기 때문이다.
"""

import json
import os
import re
import struct
import sys

import common

BASES = {
    re.compile(r"^ED2?\.BIN$"): 0x06028000,
    re.compile(r"^ED1SCN\d+\.BIN$"): 0x060D0000,
    re.compile(r"^ED2SCN\d+\.BIN$"): 0x060B8000,
    re.compile(r"^ED2MON\d+\.BIN$"): 0x060E0000,
}

# SH-2 함수 프롤로그(레지스터 푸시) — 모듈의 코드 시작 판정
CODE_HEAD = re.compile(rb"\x2f[\x86\x96\xa6\xb6\xc6\xd6\xe6]|\x4f\x22")


def base_for(name):
    for pat, base in BASES.items():
        if pat.match(name):
            return base
    return None


def cstr(d, off):
    end = d.find(b"\x00", off)
    return d[off:end] if end >= 0 else b""


# 🔴 **전각 공백은 「출력 가능」이 아니다** — 파이썬의 `str.isprintable()` 은 U+3000 을
#    구분자(Zs)로 보아 **False** 를 준다. 이 게임은 폭을 맞추느라 전각 공백을 잔뜩 쓰므로,
#    그대로 두면 그런 문자열이 통째로 「데이터」로 걸러진다 — 실측 2026-09-03: 33개가
#    덤프에서 빠져 있었고 그중 **ED1SCN27 셋은 화면에 일본어로 남아 있었다.**
#    ⚠ 초록불이 「없다」가 아니라 「안 봤다」였던 자리다(체크리스트 4-B).
PRINTABLE_EXTRA = "\n\t\u3000"


def plausible_text(raw):
    """SJIS 로 온전히 디코드되고 출력 가능한 문자 위주인가 — 본체(ED.BIN)의
    코드/데이터 포인터를 걸러낸다. 대사·지명·서식 문자열만 남기는 게 목적."""
    if not (2 <= len(raw) <= 4096):
        return False
    try:
        s = raw.decode("cp932")
    except UnicodeDecodeError:
        return False
    ok = sum(1 for c in s if c.isprintable() or c in PRINTABLE_EXTRA)
    return ok >= len(s) * 0.9 and any(ord(c) > 0x7F or c.isalpha() for c in s)


def classify(d, off):
    if CODE_HEAD.match(d[off : off + 2]):
        return "code"
    raw = cstr(d, off)
    if raw[:2] == b"%c":
        return "block"
    return "string" if plausible_text(raw) else "data"


def dump_file(name, data, base):
    n = len(data)
    ptr_map = {}  # 대상 오프셋 → [포인터 위치들]
    for off in range(0, n - 3, 4):
        v = struct.unpack_from(">I", data, off)[0]
        if base <= v < base + n:
            ptr_map.setdefault(v - base, []).append(off)
    entries = []
    for tgt in sorted(ptr_map):
        kind = classify(data, tgt)
        if kind in ("code", "data"):
            continue  # 모듈 코드 진입점·데이터 포인터 — 텍스트 아님
        raw = cstr(data, tgt)
        entries.append(
            {
                "entry_id": len(entries),
                "file_offset": hex(tgt),
                "ptr_at": [hex(p) for p in ptr_map[tgt]],
                "kind": kind,
                "raw_hex": raw.hex(),
                "text": raw.decode("cp932", "replace"),
            }
        )
    return {
        "table_id": name.rsplit(".", 1)[0],
        "source": {"base": hex(base), "size": n},
        "entry_count": len(entries),
        "entries": entries,
    }


def main():
    common.verify_source()
    out_dir = os.path.join(common.OUT_DIR, "scn_jp")
    os.makedirs(out_dir, exist_ok=True)
    f, mm = common.open_image()
    try:
        files = common.iso_files(mm)
        done = 0
        for path, lba, size in files:
            name = path.rsplit("/", 1)[-1]
            base = base_for(name)
            if base is None:
                continue
            data = common.read_extent(mm, lba, size)
            doc = dump_file(name, data, base)
            with open(os.path.join(out_dir, doc["table_id"] + ".json"), "w") as fo:
                json.dump(doc, fo, ensure_ascii=False, indent=1)
            done += 1
            print(f"{name}: {doc['entry_count']} entries")
        print(f"\n{done} files -> {out_dir}")
    finally:
        mm.close()
        f.close()


if __name__ == "__main__":
    sys.exit(main())
