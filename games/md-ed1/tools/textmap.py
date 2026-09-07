"""번역 정본 `script/NNN.json` — 스트림 단위. 원문은 **해시만**(루트 「저작권」), 우리 문안만 담는다.

    {"block": 104, "streams": {"0818": {"jp": "<sha1 앞 10자>", "ours": "…"}}}

`ours` 표기: 글자 + 제어 태그. 개행은 빌드가 조판(18칸 × 3줄)으로 넣으므로 쓰지 않는다 — 단, 페이지를
강제로 가르려면 `\\f`. 원본 스트림의 **참조 제어코드**(call/goto/셀/코드)는 `<10:08c0>` 꼴(코드:원본 대상)로
그 자리에 있어야 한다(빌드가 원본 토큰과 맞대 검증). 그 밖의 제어코드는 `<0e>` 처럼 raw hex.
화자 머리 스트림(`<1e>이름<04><07>`)은 `<1e>시녀<04><07>` 로 쓴다.

    python3 tools/textmap.py --seed 104   # 블록 104 의 스트림을 정본 초안(ours = 원문 태그 골격)으로
"""

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import scene

SCRIPT_DIR = common.GAME_DIR / "script"
TAG = re.compile(r"<([0-9a-f]{2})(?::([0-9a-f]{1,4}))?>|\f")


def jp_key(st: scene.Stream) -> str:
    return hashlib.sha1(b"".join(t.raw for t in st.tokens)).hexdigest()[:10]


def stream_to_text(st: scene.Stream) -> str:
    """원문 스트림 → 태그 표기(정본 초안용). 01 은 공백, 05 는 \\f, 참조는 <코드:대상>."""
    out = []
    for t in st.tokens:
        if t.kind == "text":
            out.append(t.raw.decode("cp932", "replace"))
        elif t.kind == "end":
            out.append(f"<{t.code:02x}>")
        elif t.kind == "eof":
            pass
        elif t.code == 0x01:
            out.append(" ")
        elif t.code == 0x05:
            out.append("\f")
        elif t.ref:
            out.append(f"<{t.code:02x}:{t.target:04x}>")
        else:
            out.append(f"<{t.raw.hex()}>")
    return "".join(out)


def parse_ours(s: str) -> list[tuple[str, object]]:
    """태그 표기 → [("text", str) | ("page", None) | ("ctl", (code, target|None, raw|None))]."""
    out = []
    pos = 0
    for m in TAG.finditer(s):
        if m.start() > pos:
            out.append(("text", s[pos : m.start()]))
        if m.group(0) == "\f":
            out.append(("page", None))
        else:
            code = int(m.group(1), 16)
            tgt = int(m.group(2), 16) if m.group(2) else None
            out.append(("ctl", (code, tgt, None if tgt is not None else bytes.fromhex(m.group(1)))))
        pos = m.end()
    if pos < len(s):
        out.append(("text", s[pos:]))
    return out


def load_all() -> dict[int, dict]:
    maps = {}
    for p in sorted(SCRIPT_DIR.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        maps[int(d["block"])] = d
    return maps


if __name__ == "__main__":
    import archives

    if "--seed" in sys.argv:
        n = int(sys.argv[sys.argv.index("--seed") + 1])
        d = common.rom()
        b = archives.blocks(d, archives.ARCHIVES["script"][0])[n][1]
        mod = scene.parse_module(b)
        SCRIPT_DIR.mkdir(exist_ok=True)
        p = SCRIPT_DIR / f"{n:03d}.json"
        cur = (
            json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"block": n, "streams": {}}
        )
        for off in sorted(mod.streams):
            k = f"{off:04x}"
            cur["streams"].setdefault(k, {"jp": jp_key(mod.streams[off]), "ours": ""})
        p.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {p}: 스트림 {len(cur['streams'])} (ours 비면 원문 유지)")
        # 원문 골격은 커밋 안 되는 work/ 로
        out = common.OUT_DIR / "text" / "script" / f"{n:03d}.seed.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            "\n".join(
                f"{off:04x}\t{stream_to_text(mod.streams[off])}" for off in sorted(mod.streams)
            ),
            encoding="utf-8",
        )
