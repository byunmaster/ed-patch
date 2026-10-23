"""이름·아이템 자리가 든 스트림만 받침 두 꼴로 다시 띄운다 — 조사·공백 판정용(`scene_sweep` 의 변수 주입판).

    python3 tools/scene_vars.py a|b [--budget 초] [BBB-K ...]

대상: 코드 `02`(배우)·`09`(번호 이름)·`0B`(리더)·`0E`(아이템)·`EB`·`EC`(조사 훅)가 든 스트림. 파티 레코드 넷의 이름($FF1DBC+n*0x40+0x30)·아이템 버퍼($FF2028)·
주문 버퍼($FF3450)를 **같은 이름** 하나로 채워 띄운다 — a = 받침 없음·최장(6자, 「…라스」) · b = 받침 있음(6자, 「…신」).
산출 `sweep/scene-vars/<a|b>/BBB-K/<오프셋>_NN.png` + `index.tsv` + `done.txt`(--budget 초가 지나면 모듈 사이에서 멈추고 다음 묶음이 이어 받는다).
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_sweep as BS
import common
import headless
import scene
import scene_sweep as S

OUT = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "sweep" / "scene-vars"
VARS = {0x02, 0x09, 0x0B, 0x0E, 0xEB, 0xEC}
NAMES = {"a": "란도플로라스", "b": "란도플로신"}
PARTY, STEP, AT = 0xFF1DBC, 0x40, 0x30
ITEM_BUF, SPELL_BUF = 0xFF2028, 0xFF3450


def main() -> None:
    args = sys.argv[1:]
    variant = args.pop(0)
    budget = 10**9
    if "--budget" in args:
        i = args.index("--budget")
        budget = int(args[i + 1])
        del args[i : i + 2]
    t0 = time.time()
    out = OUT / variant
    out.mkdir(parents=True, exist_ok=True)
    codes = json.loads(
        (common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")
    )
    rev = {v.to_bytes(2, "big"): k for k, v in codes.items() if isinstance(v, int)}
    name = b"".join(codes[ch].to_bytes(2, "big") for ch in NAMES[variant]) + b"\x06\x00"
    rom = BS.ROM.read_bytes()
    c = headless.Core(str(BS.ROM))
    armed = S.new_game_state(c, OUT)
    tsv = out / "index.tsv"
    if not tsv.exists():
        tsv.write_text("모듈\t오프셋\t문안\t캡처\t상태\n", encoding="utf-8")
    done_f = out / "done.txt"
    done = set(done_f.read_text().split()) if done_f.exists() else set()

    def real(st):
        t = S.korean(b"".join(x.raw for x in st.tokens if x.kind == "text"), rev)
        return sum(1 for ch in t if "가" <= ch <= "힣") >= 2 or "…" in t

    def prime(m):
        c.load_state(armed)
        c.poke(S.MOD_AT, m)
        for n in range(4):
            c.poke(PARTY + n * STEP + AT, name)
        c.poke(ITEM_BUF, name)
        c.poke(SPELL_BUF, name)

    for bi, k, m in S.built_modules(rom):
        key = f"{bi:03d}-{k}"
        if (args and key not in args) or key in done:
            continue
        if time.time() - t0 > budget:
            print("BUDGET", key, flush=True)
            return
        mod = scene.parse_module(m)
        todo = [
            (o, st)
            for o, st in sorted(mod.streams.items())
            if real(st) and any(t.kind == "ctl" and t.code in VARS for t in st.tokens)
        ]
        for o, st in todo:
            prime(m)
            txt = S.korean(b"".join(t.raw for t in st.tokens if t.kind == "text"), rev)
            d = out / key
            d.mkdir(exist_ok=True)
            cnt, status = S.say(c, S.MOD_AT + o, d, f"{o:04x}")
            with tsv.open("a", encoding="utf-8") as f:
                f.write(f"{key}\t{o:04x}\t{txt.replace(chr(10), ' ')[:80]}\t{cnt}\t{status}\n")
        with done_f.open("a") as f:
            f.write(key + "\n")
        print(key, len(todo), flush=True)
    print("ALL_DONE", flush=True)


if __name__ == "__main__":
    main()
