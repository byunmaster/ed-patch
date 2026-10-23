"""코드 영역 문안(sysmsg) 가운데 이름·아이템·주문 자리가 든 것만 받침 두 꼴로 다시 띄운다 — 도구·주문 사용 문구의 조사·공백 판정용.

    python3 tools/sysmsg_vars.py a|b [--budget 초] [주소 ...]

`scene_vars` 의 sysmsg 판: 파티 레코드 넷의 이름·아이템 버퍼·주문 버퍼를 **같은 이름** 하나로 채운다 — a = 받침 없음(6자 「…라스」) · b = 받침 있음(6자 「…신」).
산출 `sweep/sysmsg-vars/<a|b>/<주소>_NN.png` + `index.tsv`(열: 주소 · 문안 · 캡처 · 상태 · 완성(▼) · 글자 없는 쪽 수) + `done.txt`.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_sweep as BS
import blank_pages
import headless
import scene_sweep as S
import scene_vars as V
import sysmsg
from sysmsg_sweep import arrow, category


def main() -> None:
    args = sys.argv[1:]
    variant = args.pop(0)
    budget = 10**9
    if "--budget" in args:
        i = args.index("--budget")
        budget = int(args[i + 1])
        del args[i : i + 2]
    t0 = time.time()
    out = V.OUT.parent / "sysmsg-vars" / variant
    out.mkdir(parents=True, exist_ok=True)
    codes = json.loads(
        (S.common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")
    )
    rev = {v.to_bytes(2, "big"): k for k, v in codes.items() if isinstance(v, int)}
    name = b"".join(codes[ch].to_bytes(2, "big") for ch in V.NAMES[variant]) + b"\x06\x00"
    rom = BS.ROM.read_bytes()
    c = headless.Core(str(BS.ROM))
    armed = S.new_game_state(c, V.OUT.parent)
    tsv = out / "index.tsv"
    if not tsv.exists():
        tsv.write_text("주소\t문안\t캡처\t상태\t완성(▼)\t글자 없는 쪽 수\t분류\n", encoding="utf-8")
    done_f = out / "done.txt"
    done = set(done_f.read_text().split()) if done_f.exists() else set()
    for a, e in sorted(sysmsg.streams(rom).items()):
        key = f"{a:06x}"
        st = e["stream"]
        if (args and key not in args) or key in done:
            continue
        if not any(t.kind == "ctl" and t.code in V.VARS for t in st.tokens):
            continue
        txt = S.korean(b"".join(t.raw for t in st.tokens if t.kind == "text"), rev)
        if sum(1 for ch in txt if "가" <= ch <= "힣") < 2 and "…" not in txt:
            continue
        if time.time() - t0 > budget:
            print("BUDGET", key, flush=True)
            return
        c.load_state(armed)
        S.set_speed(c, S.speed_for(st))
        for n in range(4):
            c.poke(V.PARTY + n * V.STEP + V.AT, name)
        c.poke(V.ITEM_BUF, name)
        c.poke(V.SPELL_BUF, name)
        cnt, status = S.say(c, a, out, key, maxf=900)
        shots = [out / f"{key}_{i:02d}.png" for i in range(1, cnt + 1)]
        blank = sum(1 for f in shots if f.exists() and blank_pages.ink(f) < blank_pages.MIN_INK)
        mark = arrow(out / f"{key}_{cnt:02d}.png") if cnt else "-"
        with tsv.open("a", encoding="utf-8") as f:
            f.write(
                f"{key}\t{txt.replace(chr(10), ' ')[:80]}\t{cnt}\t{status}\t{mark}\t{blank}\t{category(txt)}\n"
            )
        with done_f.open("a") as f:
            f.write(key + "\n")
        print(key, cnt, status, mark, blank, flush=True)
    print("ALL_DONE", flush=True)


if __name__ == "__main__":
    main()
