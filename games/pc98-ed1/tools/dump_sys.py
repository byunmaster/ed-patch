"""Event·Program 디스크의 문자열 덤프 — 오프닝 · 메뉴 · 아이템 · 시스템 문구.

시나리오와 문법이 다르다. 저기는 이벤트 스크립트라 제어코드가 규칙적인데, 여기는
**x86 코드와 표 사이에 문자열이 박혀** 있다.

🔴 **반각 가나(0xA0~0xDF)로 걸러선 안 된다** — 그 대역이 x86 코드 바이트와 통째로 겹쳐
   Event 디스크에서만 오탐이 28,652건 나왔다(실측). **전각 SJIS 만** 이어 붙이고,
   그 위에 **가나 유무**를 다시 건다(ss-ed3 에서 쓴 것과 같은 자).
⚠ 그래서 **순수 한자 이름은 놓친다**(「薬草」 류). 표 자리를 규명하면 그때 회수한다.

⚠ 산출물은 `work/derived/` 로 나가고 커밋하지 않는다(원문이다).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

LEAD = lambda b: 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF
MIN_CHARS = 2  # 🔴 3 이면 두 글자 UI 를 통째로 놓친다 — `はい`·`強さ`·`ロー`(2026-09-07)


def is_kana(ch: str) -> bool:
    return "ぁ" <= ch <= "ヿ"


def fullwidth_run(data: bytes, start: int) -> tuple[str, int]:
    """전각 SJIS 로 이어지는 최대 구간. 전각 공백·ASCII 공백·개행은 안 끊는다."""
    out: list[str] = []
    i = start
    while i < len(data) - 1:
        b = data[i]
        if b == 0x01 and LEAD(data[i + 1]):  # 개행 — 뒤에 전각이 이어질 때만
            out.append("\\n")
            i += 1
            continue
        if b == 0x20:
            out.append(" ")
            i += 1
            continue
        if LEAD(b):
            try:
                out.append(data[i : i + 2].decode("shift_jis"))
            except UnicodeDecodeError:
                break
            i += 2
            continue
        break
    return "".join(out), i


def dump(flat: bytes) -> list[dict]:
    blocks = []
    i = 0
    while i < len(flat) - 1:
        text, end = fullwidth_run(flat, i)
        body = text.replace("\\n", "").replace(" ", "").replace("　", "")
        if len(body) >= MIN_CHARS and any(is_kana(c) for c in body):
            blocks.append({"o": i, "n": end - i, "t": text})
        i = max(end, i + 1)
    return blocks


def main() -> int:
    common.check_originals()
    out_dir = common.OUT_DIR / "sys_jp"
    out_dir.mkdir(parents=True, exist_ok=True)
    for key in ("event", "program"):
        flat = common.read_flat(common.disk_path(key))
        blocks = dump(flat)
        # 라운드트립 — 표기를 되돌리면 같은 바이트가 나오나
        bad = 0
        for b in blocks:
            raw = flat[b["o"] : b["o"] + b["n"]]
            back = b["t"].replace("\\n", "\x01").encode("shift_jis")
            if back != raw:
                bad += 1
        chars = sum(len(b["t"]) for b in blocks)
        (out_dir / f"{key}.json").write_text(
            json.dumps(blocks, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(
            f"{key:9s} 블록 {len(blocks):4,}  글자 {chars:6,}  라운드트립 {len(blocks) - bad:,}/{len(blocks):,}"
        )
        if bad:
            raise SystemExit(f"🔴 {key} 라운드트립 실패 {bad}건")
    print(f"→ {out_dir}  ⚠ 원문이다, 커밋 금지")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
