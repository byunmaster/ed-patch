"""코드 영역 문안(sysmsg — 아이템·주문 사용/효과/실패, 시스템 메시지, 상점 문구 등) 전부를 대사 보기로 띄운다.

    python3 tools/sysmsg_sweep.py [--out DIR]       # DIR/sysmsg/<주소>_NN.png + sysmsg-index.tsv

시험 롬(`test_battle.py`)의 SAY 우편함에 **롬 주소**를 써서 메시지 서비스를 부른다(`scene_sweep.say`). 새 게임 첫 필드(왕좌의 방) 상태에서 찍으므로
전투 창 전용 문구는 필드 창으로 나온다(줄바꿈·글자·조사 검수용 — 전투 창 폭은 `battle_sweep` 로 따로 본다). 이름·수치 자리는 그 시점 RAM 값.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_sweep as BS
import headless
import scene_sweep as S
import sysmsg


def main() -> None:
    out = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "sweep" / "scene"
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
    d = out / "sysmsg"
    d.mkdir(parents=True, exist_ok=True)
    rom = BS.ROM.read_bytes()
    c = headless.Core(str(BS.ROM))
    armed = S.new_game_state(c, out)
    import json

    from scene_sweep import korean

    codes = json.loads((S.common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8"))
    rev = {v.to_bytes(2, "big"): k for k, v in codes.items() if isinstance(v, int)}
    tsv = d / "sysmsg-index.tsv"
    done = {ln.split("\t")[0] for ln in tsv.read_text(encoding="utf-8").splitlines()[1:]} if tsv.exists() else set()
    if not tsv.exists():
        tsv.write_text("주소\t문안\t캡처\t상태\n", encoding="utf-8")
    for a, e in sorted(sysmsg.streams(rom).items()):
        key = f"{a:06x}"
        if key in done:
            continue
        txt = korean(b"".join(t.raw for t in e["stream"].tokens if t.kind == "text"), rev)
        if sum(1 for ch in txt if "가" <= ch <= "힣") < 2 and "…" not in txt:
            continue
        c.load_state(armed)
        cnt, status = S.say(c, a, d, key, maxf=900)
        with tsv.open("a", encoding="utf-8") as f:
            f.write(f"{key}\t{txt.replace(chr(10), ' ')[:80]}\t{cnt}\t{status}\n")
        print(key, cnt, status, flush=True)


if __name__ == "__main__":
    main()
