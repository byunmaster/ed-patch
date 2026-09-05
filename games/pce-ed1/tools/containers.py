"""시나리오 컨테이너 — 디렉터리 파싱 · 전수 스캔 · 대본 덤프.

컨테이너 = [디렉터리][LZ 블록들]. 디렉터리 항목은 5B 고정 `id, src_lo, src_hi, len_lo, len_hi`
이고 0xFF 로 끝난다. src 는 컨테이너 시작(=디렉터리 첫 바이트) 기준 오프셋, len 은 **풀린**
길이다(스트림엔 길이가 없다). 게임은 컨테이너를 CD RAM 뱅크 0x80~ 에 통째로 올리고
(`$378D[그룹]` 표가 뱅크를 준다) 씬 id 로 항목을 찾아 뱅크 0x76 ($8000~) 에 푼다 — 그 블록이
**이벤트 코드 + 대본**이다(SJIS 평문, 제어코드는 docs/status.md 3절).

⚠ 덤프는 `work/derived/text/` 로 나가고 커밋하지 않는다 — 원문이다(루트 「저작권」).
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import lz

DIR_END = 0xFF
ENTRY = 5
MAX_ENTRIES = 64
MAX_BLOCK = 0x4000
CONTAINER_SPAN = 0x20000  # 한 컨테이너가 넘지 않는 크기(실측 최대 32KB, 여유)

# 대본 제어코드 — 실측(2026-09-05). 뜻은 status.md 3절이 정본이고 여기선 스캔 필터로만 쓴다.
CTL = b"\x00\x01\x04\x05\x07\x09\x10\x12\x1e\x1f"
SJIS2 = rb"[\x81-\x9f\xe0-\xea][\x40-\xfc]"


def parse_dir(buf: bytes):
    """디렉터리로 읽히면 (entries, dir_end) 아니면 None. 형태만 본다 — 검증은 decode 가 한다."""
    ents = []
    i = 0
    while i + ENTRY <= len(buf) and buf[i] != DIR_END:
        ents.append((buf[i], buf[i + 1] | buf[i + 2] << 8, buf[i + 3] | buf[i + 4] << 8))
        i += ENTRY
        if len(ents) > MAX_ENTRIES:
            return None
    if not ents or i >= len(buf) or buf[i] != DIR_END:
        return None
    prev = i
    for _id, src, ln in ents:
        if src <= prev or ln == 0 or ln > MAX_BLOCK:
            return None
        prev = src
    if ents[0][1] - (i + 1) > 64:
        return None
    return ents, i + 1


def scan(track: bytes | None = None) -> list[dict]:
    """트랙 전 섹터를 훑어 **전 항목이 푸는** 컨테이너만 남긴다."""
    if track is None:
        track = common.track_data()
    found = []
    nsec = len(track) // common.USER
    for rel in range(nsec):
        head = track[rel * common.USER : (rel + 1) * common.USER]
        r = parse_dir(head)
        if not r:
            continue
        ents, _ = r
        cont = track[rel * common.USER : rel * common.USER + CONTAINER_SPAN]
        blocks = []
        try:
            for id_, src, ln in ents:
                out, used = lz.decode(cont[src:], ln)
                blocks.append({"id": id_, "src": src, "len": ln, "packed": used, "data": out})
        except (IndexError, ValueError):
            continue
        found.append({"rel": rel, "blocks": blocks})
    return found


def text_runs(block: bytes) -> list[bytes]:
    """블록 안의 대본 구간 — 전각 2자 이상이 든 SJIS·제어코드 런만(코드 바이트를 거른다)."""
    pat = rb"(?:%s|[%s\x20-\x7e\xa1-\xdf]){12,}" % (SJIS2, re.escape(CTL))
    return [r for r in re.findall(pat, block) if len(re.findall(SJIS2, r)) >= 4]


def to_text(seg: bytes) -> str:
    out = []
    i = 0
    while i < len(seg):
        a = seg[i]
        if (
            (0x81 <= a <= 0x9F or 0xE0 <= a <= 0xEA)
            and i + 1 < len(seg)
            and 0x40 <= seg[i + 1] <= 0xFC
        ):
            try:
                out.append(seg[i : i + 2].decode("cp932"))
                i += 2
                continue
            except UnicodeDecodeError:
                pass
        if 0x20 <= a < 0x7F:
            out.append(chr(a))
        elif 0xA1 <= a <= 0xDF:
            out.append(bytes([a]).decode("cp932"))
        else:
            out.append(f"[{a:02X}]")
        i += 1
    return "".join(out)


def stats(found: list[dict]) -> dict:
    seen = set()
    uniq = 0
    chars = 0
    for c in found:
        for b in c["blocks"]:
            if b["data"] in seen:
                continue
            seen.add(b["data"])
            uniq += 1
            chars += sum(len(re.findall(SJIS2, r)) for r in text_runs(b["data"]))
    return {
        "containers": len(found),
        "blocks": sum(len(c["blocks"]) for c in found),
        "unique_blocks": uniq,
        "sjis_chars": chars,
    }


# 실측 지문 — 스캐너·디코더가 흔들리면 여기서 운다(check.sh).
EXPECT = {"containers": 23, "blocks": 318, "unique_blocks": 214, "sjis_chars": 127725}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", action="store_true", help="work/derived/text/ 에 블록·대본을 쓴다")
    ap.add_argument("--check", action="store_true", help="실측 지문과 대조한다(게이트)")
    a = ap.parse_args()
    common.verify_originals()
    found = scan()
    st = stats(found)
    print("컨테이너", st)
    if a.check and st != EXPECT:
        raise SystemExit(f"컨테이너 지문 불일치: 기대 {EXPECT}")
    if a.dump:
        out = common.OUT_DIR / "text"
        out.mkdir(parents=True, exist_ok=True)
        index = []
        with open(out / "script_dump.txt", "w") as f:
            for c in found:
                for b in c["blocks"]:
                    name = f"{c['rel']:04d}_{b['id']:03d}"
                    (out / f"{name}.bin").write_bytes(b["data"])
                    runs = text_runs(b["data"])
                    index.append(
                        {
                            "rel": c["rel"],
                            **{k: b[k] for k in ("id", "src", "len", "packed")},
                            "runs": len(runs),
                        }
                    )
                    f.write(
                        f"\n===== rel {c['rel']} id {b['id']} src {b['src']} len {b['len']} packed {b['packed']}\n"
                    )
                    f.writelines(to_text(r) + "\n" for r in runs)
        (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1))
        print(f"덤프: {out}")


if __name__ == "__main__":
    main()
