#!/usr/bin/env python3
"""**전투 완료 동작 시험** — 몬스터 그룹마다 전투를 띄워 이기고, 필드로 돌아오는지(멈추지 않고 끝나는지)만 본다.

    python3 tools/ss_battle_finish.py --game ed2 --groups 1-99 --out <폴더>
    python3 tools/ss_battle_finish.py --game ed1 --groups 1-110 --out <폴더>

🔴 촬영이 아니다(문안은 이미 확인했다) — 통과/멈춤만 기록하고, **멈춤·이상일 때만 화면 한 장**을 남긴다. 롬은 안 고친다.
방법은 `ss_battle_sweep.py` 의 조우 주입(그룹 번호를 읽는 두 자리에 `mov #NN` 을 RAM 에 쓴다)을 그대로 쓴다.

판정(그룹마다):
  field    승리 → 결과 창 → 필드로 돌아왔다(화면이 전투 전 필드와 가깝고 몬스터 표가 비었다) — 일반 몬스터의 통과
  event    돌아오진 않았지만 화면이 계속 움직이고 입력에 반응한다 — 보스 뒤 이벤트·장면 전환 후보(사람이 본다)
  hang     화면이 `FREEZE_FRAMES` 동안 한 픽셀도 안 바뀌었다 — **멈춤**
  timeout  제한 프레임 안에 끝나지 않았다
  broken   돌아왔는데 파티 레코드(HP·레벨)가 깨졌다
  no_enc   조우가 안 걸렸다(편성 없는 번호)
전투 중에는 몬스터 HP 를 1 로 묶고 파티 HP 를 채운다(능력치 올린 자동 전투). ED2 는 명령 메뉴에서 공격을 고르고, ED1 은 완전 자동이다.
"""

import argparse
import json
import os
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ss_battle_sweep as B
import ss_headless as H

FREEZE_FRAMES = 900  # 이 동안 화면이 완전히 같으면 멈춤(▽ 깜박임·애니메이션이 있으면 안 걸린다)
SHOT_FINAL = False  # `--shot-final` — 통과한 그룹도 마지막 화면 한 장(이벤트 전투의 복귀 화면을 눈으로 확인할 때)
PIN = False  # 기본: ED2 는 몬스터 그대로(파티 HP 만 매 틀 채운다 — 「능력치 올린 자동 전투」). `--pin` 은 HP 1 로 묶어 빨리 끝낸다
FORCE_AFTER = 2400  # 이 프레임까지 안 죽으면 HP 를 0 으로 직접 써서 승리 처리를 시험한다(보스의 면역 — ED2 카자즘 얼음벽은 평타가 안 먹는다. 결과에 forced 표시)
DARK_LIT = 0.1  # 맵 뷰포트가 어둡다(몬스터가 사라진 승리 화면)
FIELD_LIT = 0.6  # 맵 뷰포트가 가득 찼다(필드)


def lit(a):
    """맵 뷰포트(위 틀 안쪽)에서 검지 않은 픽셀의 비율 — 필드는 맵이 가득 차 0.76~0.94, 전투 승리 뒤 뷰포트는 검다 0.0, 보스 전투 중 0.47(실측).
    🔴 처음엔 전투 전 필드 화면과의 평균 차이로 쟀는데 믿을 수 없었다 — 걸어 들어간 자리와 전투 뒤 필드의 맵 스크롤이 달라 37 이 나왔고, 전체 화면은 장 제목 띠(「서장 …」)가 떠 있는 동안 18 로 남았다(ED2 그룹 15)."""
    v = a[25:125, 35:185].astype(int)
    return float((v.sum(axis=2) > 60).mean())


def party_ok(h, game):
    """파티 레코드가 살아 있나 — HP > 0 이고 최대 HP 이하. ED2 는 아트라스 레코드(+4 HP · +8 최대), ED1 은 HP 사본(+0 HP · +4 최대 — `ed1_fill_party` 가 +4 → +0 으로 채운다)."""
    if game == "ed2":
        hp, mx = B.be32(h.peek(B.PARTY + 4, 4)), B.be32(h.peek(B.PARTY + 8, 4))
    else:
        hp, mx = B.be32(h.peek(B.ED1_PARTY_HP[0], 4)), B.be32(h.peek(B.ED1_PARTY_HP[0] + 4, 4))
    return 0 < hp <= mx < 100000


def run_one(h, nav, game, g, limit, outdir, start=None):
    mon, stride = B.GAME.get("mon", (B.MON, B.STRIDE_MON))
    h.load(nav)
    h.run(5)
    # start: 특수 전투(ED2 83)는 앞 전투를 이어받아야 돈다 — 진입을 호출자가 정한다
    started = start(h) if start else (B.ed1_start_battle if game == "ed1" else B.start_battle)(h, nav, g)
    if not started:
        return {"group": g, "status": "no_enc"}

    def hps():
        return [B.be32(h.peek(mon + stride * k + 0x1C, 4)) for k in range(4)]

    t, killed_at, same, last, field_polls, tail_changed, forced, seen_alive = 0, None, 0, None, 0, 0, False, False
    pinned = set()
    battle_polls = 0
    while t < limit:
        if game == "ed2":
            for pc in B.PARTY_COPIES:
                h.poke(pc + 4, h.peek(pc + 8, 4))
        else:
            B.ed1_fill_party(h)
        for k in range(4 if PIN else 0):  # `--pin` 일 때만: 몬스터를 처음 볼 때 한 번만 HP 1 로(한 방에 이기게) — 기본은 몬스터를 안 건드리고 파티 HP 만 채운다
            a = mon + stride * k + 0x1C
            if k not in pinned and B.be32(h.peek(a, 4)):
                h.poke(a, struct.pack(">I", 1))
                pinned.add(k)
        if not forced and seen_alive and t >= FORCE_AFTER:
            forced = True  # 필드로 못 돌아온 채 기한 — HP 를 직접 0 으로 써서 승리 처리를 시험한다
            for k in range(4):
                h.poke(mon + stride * k + 0x1C, struct.pack(">I", 0))
        h.run(3)
        t += 3
        fr = h.frame
        # 멈춤 판정 — 전체 화면이 한 픽셀도 안 바뀐 채 길게 간다
        key = fr.tobytes()
        if key == last:
            same += 3
        else:
            same, last = 0, key
            if battle_polls >= 10:
                tail_changed += 1
        if same >= FREEZE_FRAMES:
            Image.fromarray(fr).save(os.path.join(outdir, f"hang_g{g:03d}.png"))
            return {"group": g, "status": "hang", "frames": t, "killed_at": killed_at, **({"forced": True} if forced else {})}
        alive = any(hps())
        seen_alive = seen_alive or alive  # 🔴 전투 그림이 올라오기 전엔 몬스터 표가 비어 있다 — 「살아 있는 걸 본 뒤」에만 처치로 센다(안 그러면 필드 화면이 가짜 통과가 된다)
        if killed_at is None and seen_alive and not alive:
            killed_at = t
        # 처치 뒤 새 전투가 시작되면(몬스터 표가 다시 찬다) 필드로 돌아와 조작이 풀렸다는 뜻이다 — 주입한 조우가 곧바로 또 걸린다
        if killed_at is not None and alive and t > killed_at + 150 and battle_polls >= 10:
            return {"group": g, "status": "field", "frames": t, "killed_at": killed_at, "via": "re-encounter", **({"forced": True} if forced else {})}
        if game == "ed2" and B.is_menu(fr) and alive:
            for b in ("up", "up", "left", "left", "c", "c", "c"):
                h.press(b, 4, 8)
        elif t % 45 == 0:
            h.press("c", 3, 0)  # 메시지·보스 대사·결과 창을 넘긴다
        d = lit(fr)
        if os.environ.get("FIN_TRACE") and t % 60 == 0:
            print(t, "lit=%.2f" % d, "hp", hps(), "menu", B.is_menu(fr), "bp", battle_polls, "fp", field_polls, flush=True)
        if d < DARK_LIT and seen_alive:
            battle_polls += 1  # 승리 뒤 어두운 뷰포트(몬스터가 사라진 전투 화면)를 본 횟수 — 이걸 본 뒤에만 필드 복귀를 인정한다
        if battle_polls >= 10 and seen_alive and t > 120:  # 승리 처리가 몬스터 표를 0 으로 만들지 않아도(빈 칸의 옛 HP) 화면으로 본다
            field_polls = field_polls + 1 if (d > FIELD_LIT and not B.is_menu(fr)) else 0
            if field_polls >= 8:  # 24프레임 동안 맵이 가득 찬 필드가 유지된다(강제 조우 주입이 남아 필드에 오래 못 머문다)
                ok = party_ok(h, game)
                if SHOT_FINAL:
                    Image.fromarray(fr).save(os.path.join(outdir, f"final_g{g:03d}.png"))
                if not ok:
                    Image.fromarray(fr).save(os.path.join(outdir, f"broken_g{g:03d}.png"))
                return {"group": g, "status": "field" if ok else "broken", "frames": t, "killed_at": killed_at, **({"forced": True} if forced else {})}
    Image.fromarray(h.frame).save(os.path.join(outdir, f"timeout_g{g:03d}.png"))
    # 끝나지 않았지만 화면이 계속 바뀌었으면 이벤트 후보(보스 뒤 장면 등)
    st = "event" if battle_polls >= 10 and tail_changed > 50 else "timeout"
    if not seen_alive:
        st = "never_alive"  # 전투가 올라오지 않았다(몬스터 표가 끝까지 빔)
    return {"group": g, "status": st, "frames": t, "killed_at": killed_at, **({"forced": True} if forced else {})}


def main():
    global PIN, FORCE_AFTER, SHOT_FINAL
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", choices=("ed1", "ed2"), default="ed2")
    ap.add_argument("--groups", default=None)
    ap.add_argument("--limit", type=int, default=5400, help="그룹마다 제한 프레임(기본 90초)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=None)
    ap.add_argument("--bkr", default=B.DEFAULT_BKR)
    ap.add_argument("--nav-only", action="store_true")
    ap.add_argument("--force-after", type=int, default=FORCE_AFTER, help="이 프레임까지 필드로 못 돌아오면 몬스터 HP 를 0 으로 쓴다(보스 면역·긴 전투)")
    ap.add_argument("--g83", action="store_true", help="ED2 그룹 83(최종장 이벤트 전투) — 82 를 이기고 씬 45 래퍼로 잇는다(`ss_battle_g83`)")
    ap.add_argument("--shot-final", action="store_true", help="통과한 그룹도 마지막 화면 한 장을 남긴다")
    ap.add_argument("--pin", action="store_true", help="몬스터 HP 를 1 로 묶는다(빠르지만 승리 처리가 비정상일 수 있다 — 기본은 안 건드림)")
    a = ap.parse_args()
    FORCE_AFTER = a.force_after
    SHOT_FINAL = a.shot_final
    PIN = a.pin or a.game == "ed1"  # ED1 시험 세이브는 파티가 약해(몬스터 HP 1000 이 거의 안 닳는다) 몬스터를 HP 1 로 묶어야 끝난다 — ED2 는 Lv90 이라 안 건드린다
    import common

    B.GAME = B.GAMES[a.game]
    B.FILL_NAMES = False
    cue = a.cue or os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.cue")
    so = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    os.makedirs(a.out, exist_ok=True)
    h = H.Harness(so, cue, a.out, bkr=a.bkr)
    nav = os.path.join(H.CACHE, "beetle-saturn", f"{B.GAME['state']}_{B.image_key(cue)}.state")
    if not os.path.exists(nav):
        (B.ed1_boot_to_field if a.game == "ed1" else B.boot_to_field)(h)
        h.save(nav)
    if a.nav_only:
        return
    start83 = None
    if a.g83:
        import ss_battle_g83 as G83

        G83.B_NAV[0] = nav
        start83 = G83.chain_start(cue)
        a.groups = "83"
    groups = B.parse_groups(a.groups or B.GAME["groups"])
    rows = []
    for g in groups:
        if a.game == "ed1" and g in B.ED1_NO_GROUP:
            continue
        r = run_one(h, nav, a.game, g, a.limit, a.out, start=start83)
        rows.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
    with open(os.path.join(a.out, f"finish_{a.game}_{a.groups or 'all'}.json".replace(",", "_")), "w") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    cnt = {}
    for r in rows:
        cnt[r["status"]] = cnt.get(r["status"], 0) + 1
    bad = [r["group"] for r in rows if r["status"] not in ("field", "no_enc")]
    print(f"요약 {game_label(a.game)} {cnt} — field 아님 {bad}", flush=True)


def game_label(g):
    return "ED1" if g == "ed1" else "ED2"


if __name__ == "__main__":
    main()
