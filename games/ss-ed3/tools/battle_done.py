#!/usr/bin/env python3
"""전 몬스터·보스 「전투가 멈추지 않고 끝나는가」 시험 — 헤드리스 새턴(롬·세이브 불변, 촬영 없음).

    sh scripts/capture.sh python3 games/ss-ed3/tools/battle_done.py <이미지.cue> <백업RAM.bkr> <출력폴더> \\
        [--ids 1,2,30 | --all] [--maxf 12000] [--pre <상태>]

방법(10-24 실측): Disc2 세이브 7번(이자벨 직전, 파티 공격 700)을 불러 옥상 이벤트를 지나면 이벤트 스크립트가 이자벨 전투를 세운다.
  전투 편성은 맵 파일 안의 구조 하나다(전투 때 포인터 `0x06089620` 이 가리킨다) — `+0x12` 마릿수(u16) · `+0x14+4k` 마리마다 4B, **`+0x17+4k` 가 적 번호**
  (= `param.ENEMY` 색인 + 1, 이자벨 0x1E). 전투 본체가 그 번호로 PARAM 적 표 사본(`0x2F3004 + 번호×76`)을 `0x06094700` 인스턴스로 복사한다
  (`0x060230BC`). ⇒ **편성 읽기 전에 그 바이트만 목표 번호로 써 넣으면 같은 진입으로 어떤 적이든 세울 수 있다.**
  끝 판정: `0x06095754`(전투 진행 깃발)가 1→0 으로 떨어지고 스크립트 PC(`0x0609408C`)가 돌아와 이벤트가 이어지면 「통과」. `--maxf` 프레임 안에
  못 끝나면 「멈춤」 — 화면·상태를 출력폴더에 남긴다.
⚠ 보스 뒤 이벤트 경로(레바스 → 단검 이벤트 등)는 이 방식으로 못 본다 — 인게임 QA 몫이다. 상태·RAM 쓰기는 진입용이고 문안 판정은 안 한다.
"""

import argparse
import json
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import glyph_guard as G
import param as P
import ss_headless as H

INST = 0x06094700
BATTLE_FLAG = 0x06095754
SCRIPT_PC = 0x0609408C
ISABEL_ID = 0x1E
SIG = bytes.fromhex("00014234031e")  # 편성 한 마리: 마릿수 u16=1 · 마리 4B(…·번호) — 이자벨


def enemy_ids():
    """`(번호, JP 이름)` — PARAM 적 표의 실제 이름 칸(표식 제외). 번호 = 색인 + 1."""
    with C.open_disc(2) as d:
        fs = {n: (lba, size) for n, lba, size in d.files()}
        b = d.read_extent(*fs[P.PATH])
    out = []
    for i, nm in enumerate(P.records(b, P.ENEMY)):
        if nm and nm not in P.MARKS:
            out.append((i + 1, nm))
    return out


class Run:
    def __init__(self, cue, bkr, out):
        core = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
        self.h = H.Harness(core, cue, out, bkr=bkr)
        self.out = out

    def u32(self, a):
        return struct.unpack(">I", self.h.peek(a, 4))[0]

    def navigate(self):
        """부팅 → 세이브 7번 → 옥상 이벤트까지. 편성 구조가 이자벨 것으로 보일 때 멈춘다."""
        h = self.h
        h.press("start", 10, 300)
        h.press("start", 10, 300)
        h.run(2205)
        h.press("start", 10, 120)
        h.press("c", 10, 120)
        h.press("c", 10, 120)  # 메뉴 → LOAD FILE
        for _ in range(6):
            h.press("down", 6, 10)
        h.press("c", 10, 300)
        h.press("c", 10, 300)
        h.held = {H.BTN["up"]}
        h.run(400)
        h.held = set()
        #   이벤트(대사·무비)가 얼마나 걸리는지 모르니 **전투가 서는 순간까지 가서** 60프레임마다 찍어 둔 상태 중 ~400프레임 전 것으로 돌아간다.
        ring = []
        for fr in range(80000):
            h.held = {H.BTN["c"]} if (fr // 8) % 8 == 0 else set()
            h.run(1)
            if fr % 60 == 0:
                ring.append(h.snap())
                del ring[:-8]
            if any(h.peek(INST, 24)):
                a = self.form_addr()
                if not a:
                    raise SystemExit("전투가 섰는데 이자벨 편성 구조를 못 찾았다")
                self.faddr = a
                h.restore(ring[0])
                return fr
        raise SystemExit("이자벨 편성 구조를 못 찾았다 — 진입 경로가 어긋났다")

    def form_addr(self):
        """맵 파일 안의 이자벨 편성(마릿수 1 · 적 번호 0x1E)이 LWRAM 에 올라와 있으면 그 번호 바이트의 주소."""
        hits = [j for j in self.h.find(SIG) if j < 0x100000]
        return 0x200000 + hits[0] + len(SIG) - 1 if hits else None

    def put_formation(self, eids):
        """편성 구조에 `eids`(1~n 마리)를 쓴다 — 첫 마리 4B 를 본떠 번호만 바꾼다(마릿수 `+0x12` u16, 번호 `+0x17+4k`)."""
        h = self.h
        if len(eids) > 1:
            if not hasattr(self, "entry0"):
                self.entry0 = bytes(h.peek(self.faddr - 3, 4))
            h.poke(self.faddr - 5, struct.pack(">H", len(eids)))
            for k, e in enumerate(eids):
                h.poke(self.faddr - 3 + 4 * k, self.entry0[:3] + bytes([e]))
        else:
            h.poke(self.faddr, bytes([eids[0]]))

    def fight(self, eid, maxf, after=0, shot_tag=None):
        """상태에서 시작해 `eid`(번호 또는 번호 목록)를 세운다. `(결과, 시작 프레임, 끝 프레임)`.

        `after` > 0 이면 전투가 끝난 뒤 그만큼 프레임 동안 45프레임마다 화면을 남긴다(보상 창·전투 뒤 이벤트 확인)."""
        h = self.h
        eids = [eid] if isinstance(eid, int) else list(eid)
        started = ended = None
        self.inst = ""
        flag_seen = False
        shots = 0
        for fr in range(maxf + 4000 + after):
            h.held = {H.BTN["c"]} if (fr // 8) % 8 == 0 else set()
            if started is None:
                self.put_formation(eids)
            h.run(1)
            if ended is not None and after and shot_tag and fr - ended <= after and (fr - ended) % 45 == 0:
                h.shot(f"{shot_tag}_after{shots:02d}")
                shots += 1
            if ended is not None and after and fr - ended > after:
                return "통과", started, ended
            if started is None:
                if any(h.peek(INST, 24)):
                    started = fr
                    self.inst = h.peek(INST, 0x4C).hex()
                elif fr > 2500:
                    return "시작 못 함", None, None
                continue
            flag = self.u32(BATTLE_FLAG)
            if flag:
                flag_seen = True
            elif flag_seen and ended is None:
                ended = fr
            if ended is not None and not after and self.u32(SCRIPT_PC) != 0:
                return "통과", started, fr
            if fr - started > maxf:
                break
        return ("멈춤" if ended is None else "멈춤(끝난 뒤 이벤트 안 이어짐)"), started, ended


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cue")
    ap.add_argument("bkr")
    ap.add_argument("out")
    ap.add_argument("--ids", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--maxf", type=int, default=12000)
    ap.add_argument("--pre", default="")
    ap.add_argument(
        "--guard",
        default="",
        help="LO-HI[,LO-HI…] — 그 글리프 색인대(HI 미포함)를 글자 그리기가 읽는지 센다(glyph_guard)",
    )
    ap.add_argument("--multi", default="", help="번호,번호,… — 한 편성에 여러 마리를 세운다(`--ids` 무시)")
    ap.add_argument("--after", type=int, default=0, help="전투가 끝난 뒤 이 프레임 동안 45프레임마다 화면을 남긴다")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    names = dict(enemy_ids())
    ids = sorted(names) if a.all or not a.ids else [int(x) for x in a.ids.split(",")]
    if a.multi:
        ids = [[int(x) for x in a.multi.split(",")]]
    r = Run(a.cue, a.bkr, a.out)
    pre = a.pre or os.path.join(a.out, "pre.state")
    if os.path.exists(pre):
        r.h.load(pre)
        with open(pre + ".json") as f:
            r.faddr = json.load(f)["faddr"]
        r.h.run(2)
    else:
        t = time.time()
        fr = r.navigate()
        r.h.save(pre)
        with open(pre + ".json", "w") as f:
            json.dump({"faddr": r.faddr}, f)
        print(f"진입 {fr} 프레임 · {time.time() - t:.0f}초 → {pre}", flush=True)
    if a.guard:
        G.install(r.h, G.parse(a.guard))
        r.h.run(1)
    base = r.h.snap()
    log = open(os.path.join(a.out, "result.jsonl"), "a")  # noqa: SIM115 — 전수 도는 동안 열어 둔다
    for eid in ids:
        r.h.restore(base)
        r.h.run(1)
        t = time.time()
        res, s, e = r.fight(eid, a.maxf, a.after, f"b{eid:03d}" if isinstance(eid, int) else "multi")
        gh = G.hits(r.h) if a.guard else None
        wr = G.unchanged(r.h) if a.guard else None
        rec = {
            "id": eid,
            "name": names.get(eid, "?") if isinstance(eid, int) else "+".join(names.get(x, "?") for x in eid),
            "result": res,
            "start": s,
            "end": e,
            "inst": r.inst[:24],
            "guard_hits": gh,
            "guard_unchanged": wr,
            "sec": round(time.time() - t),
        }
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        log.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.flush()
        if res != "통과":
            tag = f"{eid:03d}" if isinstance(eid, int) else "multi"
            r.h.shot(f"stuck_{tag}")
            r.h.save(os.path.join(a.out, f"stuck_{tag}.state"))


if __name__ == "__main__":
    main()
