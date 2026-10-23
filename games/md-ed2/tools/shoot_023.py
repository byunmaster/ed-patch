"""씬023-1(「…무기로는 대미지를 줄 수 없다」) 두 갈래와 1614 끝을 실제 화면으로 — 무기 문구(받침 없는/있는 아이템 이름) · 맨손 문구 · 1614(씬 끝).

    sh scripts/capture.sh --fix python3 tools/shoot_023.py [--out DIR]

후크 롬(`test-battle`)에 구운 롬의 023-1 모듈을 올리고(필드 위) 아이템 버퍼에 이름을 쓴 뒤 우편함 `SAY` 로 스트림을 띄운다. **분기 루틴(`$11C8`)은 이 하네스가 부르지 않는다** — 어느 문구가
뜨는지는 unicorn 으로 따로 확인했고(씬 `23-1` 의 d0=0 → 맨손, 그 밖 → 무기), 여기선 두 문구가 **화면에 제대로 찍히는지**를 본다.
"""

import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import battle_sweep as BS
import common
import headless
import scene
import scene_sweep as S

OUT = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "sweep" / "023-1"
NAMES = {"a": "란도플로라스", "b": "란도플로신"}
ITEM_BUF = 0xFF2028
RT = 0x11C8


HEADS = [
    (48, 1, 0xB44),
    (57, 0, 0x1650),
    (81, 0, 0x8E0),
    (83, 1, 0x1BB8),
]  # 상점 표 머리 — 바깥 표의 앞 포인터 워드 셋이 가리키는 문안(첫 음절 확인)


ONLY_HEADS = (
    "--heads" in sys.argv
)  # `--heads BBB-K/원판바깥오프셋 …`(맨 뒤에) — 023-1 은 건너뛰고 지정한 상점 표만 찍는다(표의 워드 셋이 가리키는 문안)


def main() -> None:
    out = OUT
    heads = HEADS
    if ONLY_HEADS:
        hs = sys.argv[sys.argv.index("--heads") + 1 :]
        hs = [h for h in hs if "/" in h]
        heads = [
            (int(h.split("/")[0][:3]), int(h.split("/")[0][4:]), int(h.split("/")[1], 16))
            for h in hs
        ]
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
    out.mkdir(parents=True, exist_ok=True)
    codes = json.loads(
        (common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")
    )
    rom = BS.ROM.read_bytes()
    km = {(b, k): m for b, k, m in S.built_modules(rom)}[(23, 1)]
    om = {(b, k): m for b, k, m in archives.modules(common.rom())}[(23, 1)]
    _k, pair = scene.pair_streams(scene.parse_module(om), km)
    bare = RT + 12 + 2 + struct.unpack(">h", km[RT + 14 : RT + 16])[0]  # `lea bare(pc),a1` 의 대상
    eq = (
        0x11B2 + 2 + struct.unpack(">h", km[0x11B2 + 2 : 0x11B2 + 4])[0]
    )  # 출력 lea 의 기본값(장비 문구)
    c = headless.Core(str(BS.ROM))
    armed = S.new_game_state(c, out)
    todo = [("eq_a", eq, "a"), ("eq_b", eq, "b"), ("bare", bare, "a"), ("1614", pair[0x1614], "a")]
    tsv = out / "index.tsv"
    tsv.write_text("태그\t자리\t이름\t쪽\t상태\n", encoding="utf-8")
    allmods = {(b, k): m for b, k, m in S.built_modules(rom)}
    orig_mods = {(b, k): m for b, k, m in archives.modules(common.rom())}
    shots = []
    for tag, at, v in todo:
        shots.append((tag, at, v, km))
    if ONLY_HEADS:
        shots = []
    for b, k, x in heads:
        m = allmods[(b, k)]
        _kk, pr = scene.pair_streams(scene.parse_module(orig_mods[(b, k)]), m)
        nx = pr[x]
        for i in range(3):
            w = struct.unpack(">H", m[nx + 2 * i : nx + 2 * i + 2])[0]
            shots.append((f"head_{b:03d}-{k}_{x:04x}_w{i}", w, "b", m))
    for tag, at, v, mod_bytes in shots:
        name = b"".join(codes[ch].to_bytes(2, "big") for ch in NAMES[v]) + b"\x06\x00"
        c.load_state(armed)
        S.set_speed(c, 1)
        c.poke(S.MOD_AT, mod_bytes)
        c.poke(ITEM_BUF, name)
        n, status = S.say(c, S.MOD_AT + at, out, tag)
        with tsv.open("a", encoding="utf-8") as f:
            f.write(f"{tag}\t{at:04x}\t{v}\t{n}\t{status}\n")
        print(tag, hex(at), n, status, flush=True)


if __name__ == "__main__":
    main()
