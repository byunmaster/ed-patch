"""전투 꼬리 조각 정적 표 — 앞 스트림이 이름을 부르고 이어 붙는 조각(`<ebXX> 쉬고 있다.` · `<02>의 촉수가…`)이 받침 있는/없는 이름 뒤에서 어떻게 나오는지.

    python3 tools/battle_tail9.py [--out DIR]     # DIR/force/tail9.tsv (기본 .local/work/inbox/md-ed2/sweep/battle)

열: 오프셋 | 원문 구조 | 우리 문안 | 받침 있는 이름 결과 | 받침 없는 이름 결과.
결과 문자열 = **이름 + 조사(런타임 훅 `EB p` 와 같은 규칙: shared.text.josa) + 조각 문안**을 빌드 조판기(`build.typeset`)에 통과시킨 값. 손으로 잇지 않는다.
이름 = 받침 있는 「디임」 · 받침 없는 「아트라스」(대표값). ⚠ 원문(JP) 구조가 들어 있다 — 커밋 금지.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle
import build
import common
import headless
import textmap

from shared.text import josa

TAILS = [
    (5, 0x668),
    (5, 0x677),
    (4, 0x42D),
    (5, 0x62A),
    (20, 0x6E6),
    (26, 0x96E),
    (26, 0x9F4),
    (26, 0xA20),
    (82, 0xAC8),
]
NAMES = {"받침있음": "디임", "받침없음": "아트라스"}
HOOK = {0: "은/는", 1: "이/가", 2: "을/를", 3: "과/와", 4: "으로/로"}


def main() -> None:
    out = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "sweep" / "battle"
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
    orig = common.rom()
    ob = {i: b for i, (_s, b, _e) in enumerate(battle.blocks(orig))}
    import battle_sweep as BS

    bb = {i: b for i, (_s, b, _e) in enumerate(battle.blocks(BS.ROM.read_bytes()))}
    codes = json.loads(
        (common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")
    )
    rev = {v.to_bytes(2, "big"): k for k, v in codes.items() if isinstance(v, int)}

    def korean(raw: bytes) -> str:
        r, i = "", 0
        while i < len(raw):
            if raw[i : i + 2] in rev:
                r, i = r + rev[raw[i : i + 2]], i + 2
            elif 0x20 <= raw[i] < 0x7F:
                r, i = r + chr(raw[i]), i + 1
            else:
                r, i = r + "·", i + (2 if raw[i] >= 0x80 else 1)
        return r

    def norm(t: str) -> str:
        return re.sub(r"<[0-9a-f:]+>|\s+", "", t)

    bmap = json.loads(battle.MAP_JSON.read_text(encoding="utf-8"))
    rows = [
        "오프셋\t원문 구조\t우리 문안\t받침 있는 이름(디임) 결과\t받침 없는 이름(아트라스) 결과"
    ]
    for b, off in TAILS:
        st = battle.refs(ob[b]).get(off)
        if not st:  # 블록이 구워지며 오프셋이 달라진 곳(20·26·82) — 구운 롬의 스트림을 한글로 읽어 정본 문안과 맞춘다
            st = battle.refs(bb[b]).get(off)
            if not st:
                rows.append(f"{b}:{off:#x}\t(구운 롬에도 없음)\t\t\t")
                continue
            kr = norm(korean(b"".join(t.raw for t in st["stream"].tokens if t.kind == "text")))
            jp_keys = [k for k, v in bmap.items() if kr and norm(v.get("ours", "")) == kr]
            shape = " ".join(
                f"[{t.raw.hex()}]" if t.kind != "text" else f"'{korean(t.raw)}'"
                for t in st["stream"].tokens
            )
            ours = bmap[jp_keys[0]]["ours"] if jp_keys else ""
            shape = "(구운 롬) " + shape
            stream = None
        else:
            stream = st["stream"]
        if stream is not None:
            shape = " ".join(
                f"[{t.raw.hex()}]" if t.kind != "text" else f"'{t.raw.decode('cp932', 'replace')}'"
                for t in stream.tokens
            )
            ours = bmap.get(textmap.jp_key(stream), {}).get("ours", "")
        cells = []
        for nm in NAMES.values():
            # 우리 문안: `<ebXX>` 는 직전 이름의 조사 자리 · `<02>` 는 이름 자리(여기선 대표 이름으로 채운다)
            def hook(m, nm=nm):
                return josa.josa(nm, HOOK.get(int(m.group(1), 16) & 0x0F, "은/는"))

            s = re.sub(r"<eb([0-9a-f]{2})>", hook, ours)
            s = s.replace("<02>", nm)
            s = re.sub(r"<[0-9a-f:]+>", "", s)
            if not re.match(r"\s*<02>", ours):
                s = (
                    nm + s
                )  # 조각은 앞 스트림이 이름을 그려 준다 — 이름 뒤에 이어 붙인다(제 이름 자리 `<02>` 로 시작하면 그대로)
            try:
                cells.append(
                    "⏎".join(" ".join(ln.split()) if False else ln for ln in build.typeset(s)[0])
                )
            except SystemExit as e:
                cells.append(f"(조판 실패: {e})")
        rows.append(f"{b}:{off:#x}\t{shape}\t{ours}\t{cells[0]}\t{cells[1]}")
    d = out / "force"
    d.mkdir(parents=True, exist_ok=True)
    (d / "tail9.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"{len(rows) - 1}행 → {d / 'tail9.tsv'}")


if __name__ == "__main__":
    main()
