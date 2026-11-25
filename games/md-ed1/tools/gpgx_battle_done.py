"""전 몬스터·보스 전투 완료 동작 시험 — 「전투가 멈추지 않고 끝나는가」만 본다(문안은 안 본다, 촬영 안 한다).

`gpgx_battle` 과 같은 강제 조우(`$FF3606` = 블록 · `$FF1852` = 0040 + 더미 객체)로 블록마다 한 번 열고,
파티 HP·공격력을 매 프레임 올려 둔 채 **공격 → 첫째 대상**을 누른다. 명령창이 없을 땐 가끔 확인 키(c)를 눌러 ▼ 대기를 넘긴다.
끝났다고 보는 기준은 화면이 **조우 전 필드 화면과 같아진 채 30프레임 유지**다(승리 처리를 지나 필드 복귀).
못 돌아오면 `maxf` 프레임 뒤 판정한다 — 화면이 바뀌고 있으면 `이벤트`(보스 뒤 연출 등으로 넘어간 것으로 본다),
`maxf/3` 동안 화면이 같고 명령창도 없으면 `멈춤`.

    python3 gpgx_battle_done.py --rom <롬> --out <폴더> [--blocks 0-109] [--maxf 9000]

산출: `<out>/done.json`(블록별 판정·프레임·턴) · 멈춤·이상만 `<out>/b<블록>_<판정>.png`.
"""

import argparse
import hashlib
import json
import os
import random
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gpgx_battle import STATE_NAME, WIN, boot_to_field, recipe, win_hash
from gpgx_run import Genesis

ATK = os.environ.get("ED_ATK", "0F9F")  # 파티 공격력 poke(빈 문자열이면 안 건드린다)
MPOKE = [
    (int(a, 0), bytes.fromhex(b))
    for a, b in (x.split(":") for x in os.environ.get("ED_MPOKE", "").split(",") if x)
]
PARTY_REC = 0xFF1DBC - 0xFF0000  # 파티 레코드 시작(램 오프셋) — +4 HP · +0x10 공격(워드)


def is_menu(g, tmpl) -> bool:
    """명령창 판정 — 보스 전투는 창 아래 이름·숫자가 달라 `gpgx_battle.is_menu`(0.93)보다 느슨하게(0.84) 본다."""
    cur = g.frame[WIN[0] : WIN[1]]
    return cur.shape == tmpl.shape and float(np.mean(cur == tmpl)) > 0.84


def rand_table(g: Genesis, rng: random.Random):
    """난수표(`$FF3480`, 55B)를 무작위로 — 한 값으로 고정하면 명중 판정이 늘 같아 공격이 계속 빗나간다(10-24 실측: 고정 때 미결 58 → 무작위로 바꾸니 22·3 이 끝났다)."""
    g.poke(0x3480, bytes(rng.randrange(256) for _ in range(55)))


def boost(g: Genesis):
    """파티 HP·공격력을 올려 둔다(네 명 다)."""
    g.poke(0x1DC0, bytes.fromhex("270F270F"))
    for m in range(4):
        if ATK:
            g.poke(PARTY_REC + m * 0x40 + 0x10, bytes.fromhex(ATK))


def run_one(g, state, blk, tmpl, maxf, level, weak=False, weak_hp=3, auto=False, flee=False, seed=0):
    g.load_state(state)
    g.run(2)
    ref = g.frame.copy()  # 조우 전 필드 화면(해상도가 전투 화면과 다르다)
    recipe(g, level)
    g.poke(0x3606, bytes([blk]))
    g.poke(0x1852, bytes.fromhex("0040"))
    rng = random.Random(blk + seed * 1000)
    rand_table(g, rng)
    turn = 0
    stable = 0
    last = ""
    same = 0
    left = False  # 한 번이라도 전투 화면으로 갔나(필드 화면과 달라졌나)
    from collections import deque

    recent: deque[str] = deque(
        maxlen=1500
    )  # 최근 1500프레임의 창 해시 — ▼ 깜박임(둘)뿐이면 진행이 멈춘 것
    menu_at = -1
    for f in range(maxf):
        boost(g)
        if weak and f >= 90 and f % 30 == 0:  # 몬스터 HP 를 바닥으로(`gpgx_battle` weak 와 같다)
            for rec in (0x1EC0, 0x1F00, 0x1F40, 0x1F80):
                g.poke(rec, struct.pack(">H", weak_hp))
        if MPOKE:  # 몬스터 레코드 칸 덮어쓰기("오프셋:헥스,…") — 명중·회피 칸을 눌러 격파 경로를 연다
            for rec in (0x1EC0, 0x1F00, 0x1F40, 0x1F80):
                for off, hx in MPOKE:
                    g.poke(rec + off, hx)
        g.run(1)
        eq = float(np.mean(g.frame == ref)) if g.frame.shape == ref.shape else 0.0
        if eq < 0.6:
            left = True
        if left and eq > 0.97:
            same += 1
            if same >= 30:
                return "통과", f, turn
        else:
            same = 0
        h = win_hash(g)
        recent.append(h)
        stable = stable + 1 if h == last else 0
        last = h
        menu = stable >= 20 and is_menu(g, tmpl) and not auto
        if menu:
            menu_at = f
            rand_table(g, rng)
            if flee:  # 도망 — 둘째 줄 오른쪽 끝(`gpgx_battle` flee 모드와 같은 입력)
                g.press("down", 8, 6)
                for _ in range(3):
                    g.press("right", 8, 6)
                g.press("c", 8, 20)
            elif not auto:
                g.press("c", 8, 20)
                g.press("c", 8, 20)
            turn += 1
        elif left and f > 100 and f % 45 == 0:
            g.press("c", 8, 4)  # ▼ 대기 넘김
        if left and f % 300 == 0 and len(recent) == recent.maxlen and len(set(recent)) <= 4:
            return "멈춤", f, turn
    # 시간 안에 안 끝났다 — 최근에도 명령창이 떴으면 전투가 계속 도는 것(끝나지 않은 것), 아니면 연출로 넘어간 것
    if left and maxf - menu_at < 1500:
        return "미결", maxf, turn
    return "이벤트", maxf, turn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--blocks", default="0-109")
    ap.add_argument("--weak", action="store_true", help="몬스터 HP 를 3 으로 눌러 둔다")
    ap.add_argument("--weak-hp", type=int, default=3)
    ap.add_argument(
        "--auto",
        action="store_true",
        help="자동 전투가 켜진 세이브(--slot 2)에서 명령 입력 없이 확인 키만 누른다",
    )
    ap.add_argument("--slot", type=int, default=0, help="이어하기 슬롯(0=L1, 2=L99 바니스성)")
    ap.add_argument("--flee", action="store_true", help="공격 대신 도망을 고른다(보스는 도망이 막힌다)")
    ap.add_argument("--seed", type=int, default=0, help="난수표 시드 가감(같은 블록의 다른 운)")
    ap.add_argument("--maxf", type=int, default=9000)
    ap.add_argument("--save", default="/root/save/md-ed1/md-ed1-slots.sav")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    g = Genesis(a.rom, srm=Path(a.save).read_bytes())
    sp = out / STATE_NAME
    rom_sha = hashlib.sha1(Path(a.rom).read_bytes()).hexdigest()
    shp = sp.with_name(sp.name + ".sha1")
    if sp.exists() and (not shp.exists() or shp.read_text().strip() != rom_sha):
        sp.unlink()  # 상태 파일은 롬을 바꿔도 옛 RAM 을 되살린다
    if sp.exists():
        state = sp.read_bytes()
    else:
        boot_to_field(g, a.slot)
        state = g.save_state()
        sp.write_bytes(state)
        shp.write_text(rom_sha)
    from PIL import Image

    tmpl = np.array(
        Image.open(Path(__file__).resolve().parent / "gpgx_menu_tmpl.png").convert("RGB")
    )
    blocks = []
    for part in a.blocks.split(","):
        if "-" in part:
            x, y = part.split("-")
            blocks += list(range(int(x), int(y) + 1))
        else:
            blocks.append(int(part))
    res = {}
    for b in blocks:
        verdict, f, turn = run_one(g, state, b, tmpl, a.maxf, 2, a.weak, a.weak_hp, a.auto, a.flee, a.seed)
        if verdict != "통과":
            g.shot(out / f"b{b:03d}_{verdict}.png")
        res[b] = {"판정": verdict, "프레임": f, "턴": turn}
        print(b, res[b], flush=True)
    (out / "done.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    from collections import Counter

    print(Counter(v["판정"] for v in res.values()))


if __name__ == "__main__":
    main()
