"""시나리오·전투 대본 덤프 — JP 원문을 뜬다.

⚠ **산출물은 `work/derived/` 로 나가고 커밋하지 않는다**(원문이다 — 루트 「저작권」).

문법(선행 영문 패치의 옵코드 대장을 우리 이미지에서 재확인):

    바이트 < 0x20  = 옵코드(고정 길이)      · 0x00 종료 · 0x01 개행 · 0x05 페이지
    바이트 ≥ 0x20  = 텍스트                 · 0xA0~0xDF 는 **반각 가나 1바이트**
                                             그 밖의 ≥0x80 은 SJIS 2바이트

🔴 **옵코드를 따라가며 뜨지 않는다.** 텍스트와 코드가 섞여 있고 진입점·점프를 다 풀어야
제대로 갈리는데(선행 패치는 코드 훅 12종을 썼다), 지금 필요한 건 **번역할 원문**이지
재삽입이 아니다. 그래서 **텍스트로 보이는 최대 구간**을 뜨고 **가나 유무로 오탐을 거른다**
(ss-ed3 에서 쓴 것과 같은 자. `docs/reference/our-findings.md`).
⇒ 여기서 뜬 구간은 **번역 저본**이지 **재삽입 단위가 아니다.** 재삽입은 옵코드를 푼 뒤에.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import scn

# 텍스트 안에 섞여도 구간을 끊지 않는 제어코드 — 화면 조판에 속한다.
INLINE_CODES = {0x01: "\\n", 0x03: "<WAIT>", 0x05: "<PAGE>"}
MIN_CHARS = 2  # 이보다 짧은 구간은 오탐이 대부분이다


def decode_run(data: bytes, start: int) -> tuple[str, int, bool]:
    """start 부터 텍스트 구간을 읽는다 → (표기, 끝오프셋, 가나포함)."""
    out, i, has_kana = [], start, False
    while i < len(data):
        b = data[i]
        if b in INLINE_CODES:
            # 구간을 잇되, 뒤에 텍스트가 더 있을 때만 (끝에 붙은 개행은 코드다)
            j = i + 1
            if j < len(data) and data[j] >= 0x20:
                out.append(INLINE_CODES[b])
                i = j
                continue
            break
        if b < 0x20:
            break
        try:
            if 0xA0 <= b <= 0xDF:  # 반각 가나
                ch = data[i : i + 1].decode("shift_jis")
                i += 1
            elif b >= 0x80:
                ch = data[i : i + 2].decode("shift_jis")
                i += 2
            else:
                ch = data[i : i + 1].decode("shift_jis")
                i += 1
        except UnicodeDecodeError:
            break
        out.append(ch)
        if "぀" <= ch <= "ヿ" or 0xA0 <= b <= 0xDF:
            has_kana = True
    return "".join(out), i, has_kana


def encode_run(text: str) -> bytes:
    """decode_run 의 역 — 라운드트립 검증용."""
    out = bytearray()
    i = 0
    rev = {v: k for k, v in INLINE_CODES.items()}
    while i < len(text):
        for tag, code in rev.items():
            if text.startswith(tag, i):
                out.append(code)
                i += len(tag)
                break
        else:
            out += text[i].encode("shift_jis")
            i += 1
    return bytes(out)


SPEAKER_OPEN, SPEAKER_CLOSE = 0x1E, 0x04


def dump_area(directory: dict) -> tuple[list[dict], int, int]:
    """🔴 **화자를 살린다.** `1E <화자> 04` 는 PS1·새턴의 `%c화자%c` 와 같은 것이라,
    버리면 **문안 사전의 열쇠가 안 맞는다** — 실측으로 PS1 대사와 유사도 0.76~0.92 인 줄들이
    통째로 「없는 줄」이 됐다(devlog 2026-08-30).
    """
    blocks, checked, failed = [], 0, 0
    for key, info in directory.items():
        data = info["data"]
        i = 0
        speaker = None
        while i < len(data):
            b = data[i]
            if b == SPEAKER_OPEN and i + 1 < len(data) and data[i + 1] >= 0x20:
                name, end, _ = decode_run(data, i + 1)
                if end < len(data) and data[end] == SPEAKER_CLOSE:
                    checked += 1
                    if encode_run(name) != data[i + 1 : end]:
                        failed += 1
                    speaker = name
                    i = end + 1
                    continue
            if b < 0x20:
                i += 1
                continue
            text, end, has_kana = decode_run(data, i)
            raw = data[i:end]
            if end > i:
                checked += 1
                if encode_run(text) != raw:
                    failed += 1
                if has_kana and len(text.replace("\\n", "")) >= MIN_CHARS:
                    blk = {"k": scn.format_key(key), "o": i, "n": end - i, "t": text}
                    if speaker:
                        blk["s"] = speaker
                    blocks.append(blk)
                # ⚠ 화자는 **바로 다음 덩이까지**만 유효하다. 종료코드까지 늘려서 재 봤더니
                #   사전 적중이 6.8% → 6.5% 로 떨어졌다(2026-08-30) — 넓히면 남의 화자를 문다.
                speaker = None
            i = max(end, i + 1)
    return blocks, checked, failed


def main() -> int:
    common.check_originals()
    scenario, combat = scn.load()
    out_dir = common.OUT_DIR / "scn_jp"
    out_dir.mkdir(parents=True, exist_ok=True)

    total_fail = 0
    for name, directory in (("scenario", scenario), ("combat", combat)):
        blocks, checked, failed = dump_area(directory)
        total_fail += failed
        chars = sum(len(b["t"].replace("\\n", "")) for b in blocks)
        (out_dir / f"{name}.json").write_text(
            json.dumps(blocks, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(
            f"{name:9s} 블록 {len(blocks):5,}  글자 {chars:7,}  "
            f"라운드트립 {checked - failed:,}/{checked:,}"
        )

    # 마커 포착률 — 「덤프가 대본을 얼마나 건졌나」의 자
    markers = ["です", "ます", "ました", "という", "こと", "ない", "して"]
    flat = common.read_flat(common.disk_path("scenario"))
    in_disk = sum(flat.count(m.encode("shift_jis")) for m in markers)
    dumped = 0
    for name in ("scenario", "combat"):
        blob = json.loads((out_dir / f"{name}.json").read_text(encoding="utf-8"))
        joined = "".join(b["t"] for b in blob)
        dumped += sum(joined.count(m) for m in markers)
    print(f"마커 포착 {dumped:,}/{in_disk:,} = {dumped / in_disk:.1%}")

    if total_fail:
        raise SystemExit(f"🔴 라운드트립 실패 {total_fail}건 — 덤프를 못 믿는다")
    print(f"→ {out_dir}  ⚠ 원문이다, 커밋 금지")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
