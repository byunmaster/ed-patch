#!/usr/bin/env python3
"""최소 libretro 프런트(PC엔진 CD) — beetle-pce(mednafen_pce_libretro.so)를 ctypes 로 돌려 스크립트를 재생한다(emucap 호출 0번, 부팅~침실 약 17초).
코어: `git clone https://github.com/libretro/beetle-pce-libretro && make` → `.local/cache/libretro/mednafen_pce_libretro.so`(바이너리 커밋 금지, `CORE` 환경변수로 덮음). 시스템 디렉터리 = 같은 폴더 `system/`(syscard3.pce 를 둔다).
사용: headless_pce.py <cue> <스크립트.json> <출력폴더> [BRAM.sav]
⚠ 부팅 타이밍이 emucap 과 다르다(타이틀이 더 늦게 온다) — 입력은 화면 확인으로 맞춘다. 패드는 코어 포트 장치를 JOYPAD 로 지정해야 먹는다.
스크립트 연산: wait N · press "i+run" 프레임 [뒤프레임] · shot 이름 · peek 주소(CPU $2000~$3FFF) 길이 · poke 주소 hex ·
              until 주소 hex 최대프레임 (워크 RAM 바이트 열이 나올 때까지) · save 파일 · load 파일
              view 접두 최대쪽수 [크롭 y0 y1] — 대사 보기 빌드용 닫힌 고리: 화면이 멈추면(12프레임 같음) 찍고(+ZP $10/$11 = 메시지 포인터 기록) I 를 누른다.
              화면이 600프레임 안 바뀌면 끝(멈춤·종료)으로 보고 멈춘다. 색인은 `<출력>/view.tsv`.
"""

import ctypes as C
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image

CUE, SCRIPT, OUT = sys.argv[1:4]
BRAM = sys.argv[4] if len(sys.argv) > 4 else None
# 메인 트리 `.local/cache/libretro/`(워크트리엔 .local 이 없다 — git 공용 디렉터리를 거슬러 찾는다): 코어 .so · system/(syscard3.pce) · save/
_COMMON = subprocess.check_output(
    ["git", "rev-parse", "--git-common-dir"],
    text=True,
    cwd=os.path.dirname(os.path.abspath(__file__)),
).strip()
HERE = os.path.join(os.path.dirname(os.path.abspath(_COMMON)), ".local", "cache", "libretro")
SYS = os.path.join(HERE, "system")
SAVE = os.path.join(HERE, "save")
os.makedirs(OUT, exist_ok=True)
core = C.CDLL(os.environ.get("CORE", os.path.join(HERE, "mednafen_pce_libretro.so")))
ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VID = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUD = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
AUS = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
POLL = C.CFUNCTYPE(None)
INP = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)


class Var(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


class GameInfo(C.Structure):
    _fields_ = [
        ("path", C.c_char_p),
        ("data", C.c_void_p),
        ("size", C.c_size_t),
        ("meta", C.c_char_p),
    ]


state = {"fmt": 0, "frame": None, "held": set()}
keep = []
LOG = C.CFUNCTYPE(None, C.c_int, C.c_char_p)
logcb = LOG(
    lambda lv, fmt: print(
        "LOG", lv, fmt.decode(errors="replace").strip(), file=sys.stderr, flush=True
    )
)


class LogCB(C.Structure):
    _fields_ = [("log", LOG)]


logs = LogCB(logcb)


def env(cmd, data):
    cmd &= 0xFFFF
    if os.environ.get("ENVDBG"):
        print("ENV", cmd, file=sys.stderr, flush=True)
    if cmd == 27:
        C.cast(data, C.POINTER(LogCB))[0] = logs
        return True
    if cmd in (9, 31):
        p = C.c_char_p((SYS if cmd == 9 else SAVE).encode())
        keep.append(p)
        C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(p, C.c_void_p)
        return True
    if cmd == 10:
        state["fmt"] = C.cast(data, C.POINTER(C.c_uint))[0]
        return True
    if cmd == 15:
        return False
    if cmd == 17:
        C.cast(data, C.POINTER(C.c_bool))[0] = False
        return True
    if cmd == 3:
        C.cast(data, C.POINTER(C.c_bool))[0] = True
        return True
    return False


def vid(data, w, h, pitch):
    if not data:
        return
    buf = C.string_at(data, pitch * h)
    if state["fmt"] == 2:
        a = np.frombuffer(buf, dtype="<u2").reshape(h, pitch // 2)[:, :w].astype(np.uint32)
        r = ((a >> 11) & 31) * 255 // 31
        g = ((a >> 5) & 63) * 255 // 63
        b = (a & 31) * 255 // 31
        state["frame"] = np.dstack([r, g, b]).astype(np.uint8)
    else:
        a = np.frombuffer(buf, dtype=np.uint8).reshape(h, pitch)[:, : w * 4].reshape(h, w, 4)
        state["frame"] = a[:, :, [2, 1, 0]].copy()


WIN_BG = (0, 0, 106)  # 대사창 바탕색(343×243 프레임, 실측 — 창은 플레이어 위치에 따라 위쪽·아래쪽에 뜬다)


def winbox(frame):
    """대사창 안쪽 잘라내기 — 바탕색 픽셀의 경계 상자(왼쪽 지도 영역 x<225). 창이 없으면 None."""
    reg = frame[54:240, 10:225]  # 제목 띠(y<54)도 같은 바탕색이라 빈 쪽으로 찍혔다 — 지도 영역(안쪽)만
    m = (reg[:, :, 0] == WIN_BG[0]) & (reg[:, :, 1] == WIN_BG[1]) & (reg[:, :, 2] == WIN_BG[2])
    if int(m.sum()) < 3000:
        return None
    ys = np.nonzero(m.sum(axis=1) > 40)[0]
    xs = np.nonzero(m.sum(axis=0) > 12)[0]
    if not len(ys) or not len(xs):
        return None
    return reg[ys[0] : ys[-1] + 1, xs[0] : xs[-1] + 1]


VICTORY_LINE = np.asarray(Image.open(os.path.join(os.path.dirname(__file__), "victory_line.png")).convert("RGB"))


def is_victory(frame):
    """전투 승리 창(첫 줄 「…승리했다.」) 인가 — 창이 위·아래 어디에 떠도 찾도록 세로로 밀어 가며 비교."""
    h, w = VICTORY_LINE.shape[:2]
    for y in range(54, 214 - h):
        if np.array_equal(frame[y : y + h, 38 : 38 + w], VICTORY_LINE):
            return True
    return False


def same_win(a, b):
    return a is not None and b is not None and a.shape == b.shape and np.array_equal(a, b)
# beetle-pce 패드: PCE I = RetroPad B(0), II = RetroPad A(8), SELECT=2, RUN=START(3)
BTN = {"i": 8, "ii": 0, "select": 2, "run": 3, "up": 4, "down": 5, "left": 6, "right": 7}


def inp(port, dev, idx, id_):
    return 1 if (port == 0 and dev == 1 and id_ in state["held"]) else 0


AUDIO_OUT = open(os.environ["PCE_AUDIO"], "wb") if os.environ.get("PCE_AUDIO") else None  # 소리를 raw s16 스테레오로 저장(음성 겹침 비교용)


def audio_batch(data, n):
    if AUDIO_OUT is not None and n:
        AUDIO_OUT.write(C.string_at(data, n * 4))
    return n


cbs = [
    ENV(env),
    VID(vid),
    AUD(audio_batch),
    AUS(lambda l, r: None),
    POLL(lambda: None),
    INP(inp),
]
core.retro_set_environment(cbs[0])
core.retro_set_video_refresh(cbs[1])
core.retro_set_audio_sample(cbs[3])
core.retro_set_audio_sample_batch(cbs[2])
core.retro_set_input_poll(cbs[4])
core.retro_set_input_state(cbs[5])
core.retro_init()
assert core.retro_load_game(C.byref(GameInfo(CUE.encode(), None, 0, None))), "load fail"
core.retro_get_memory_data.restype = C.c_void_p
core.retro_get_memory_size.restype = C.c_size_t
core.retro_serialize_size.restype = C.c_size_t
core.retro_set_controller_port_device(0, 1)
core.retro_run()
if BRAM:
    mp = core.retro_get_memory_data(0)
    d = open(BRAM, "rb").read()
    C.memmove(mp, d, min(d.__len__(), core.retro_get_memory_size(0)))
frames = 0


TRACE = None  # battle 의 dense — 전투 시작 기준 프레임 번호가 [lo, hi) 면 <접두>_d/ 에 저장. 관찰·I 누름 구간도 빠짐없이


def run(n):
    global frames
    for _ in range(n):
        core.retro_run()
        frames += 1
        if TRACE and TRACE[2] <= frames - TRACE[1] < TRACE[3]:
            if os.environ.get("PCE_WATCH"):  # 「주소:길이,…」 — 프레임마다 워크 RAM 값을 `<접두>_w.tsv` 로(그림은 안 저장)
                row = [str(frames - TRACE[1])]
                for it in os.environ["PCE_WATCH"].split(","):
                    ad, ln = it.split(":")
                    row.append(C.string_at(ram(ad), int(ln)).hex())
                with open(TRACE[0] + "_w.tsv", "a") as wf:
                    wf.write("\t".join(row) + "\n")
            else:
                Image.fromarray(state["frame"]).save(os.path.join(TRACE[0], f"{frames - TRACE[1]:06d}.png"))


def ram(a):
    return core.retro_get_memory_data(2) + ((int(a.lstrip("$"), 16) - 0x2000) & 0x1FFF)


def shot(name):
    Image.fromarray(state["frame"]).save(os.path.join(OUT, name + ".png"))


for step in json.load(open(SCRIPT)):
    op = step[0]
    if op == "wait":
        run(step[1])
    elif op == "press":
        state["held"] = {BTN[b] for b in step[1].split("+")}
        run(step[2])
        state["held"] = set()
        run(step[3] if len(step) > 3 else 20)
    elif op == "wait":  # ["wait", 프레임]
        run(step[1])
    elif op == "encounter":
        # ["encounter", 번호hex] — 조우 번호(`$3FFA`)를 넣고 걸어서 전투 화면이 뜰 때까지만(디버그 롬 전용). 그 뒤 조작은 스크립트가 한다(자동전투 끄기·커맨드 창 촬영)
        C.memmove(ram("3FFA"), bytes.fromhex(step[1]), len(step[1]) // 2)
        walked = 0
        while walked < 400 and float((state["frame"][50:170, 35:215].sum(axis=2) == 0).mean()) < 0.5:
            state["held"] = {BTN["down" if walked % 2 == 0 else "up"]}
            run(16)
            state["held"] = set()
            run(10)
            walked += 1
        print("encounter", step[1], "walked", walked, "frame", frames, flush=True)
    elif op == "shot":
        shot(step[1])
        print("shot", step[1], "frame", frames, flush=True)
    elif op == "holdpeek":  # ["holdpeek", 버튼들, 프레임, 주소, 길이] — 쥔 채 10프레임마다 값을 찍는다(입력이 어디에 반영되는지 찾는 용)
        state["held"] = {BTN[b] for b in step[1].split("+")}
        for _ in range(step[2] // 10):
            run(10)
            print("hp", frames, C.string_at(ram(step[3]), step[4]).hex(), flush=True)
        state["held"] = set()
    elif op == "holdpoke":  # ["holdpoke", 주소, 값hex, 프레임] — 매 프레임 값을 써 넣는다(코어가 막는 ←+→ 같은 입력을 패드 변수에 직접)
        b = bytes.fromhex(step[2])
        for _ in range(step[3]):
            C.memmove(ram(step[1]), b, len(b))
            run(1)
    elif op == "peek":
        print(
            "peek", step[1], C.string_at(ram(step[1]), step[2]).hex(), "frame", frames, flush=True
        )
    elif op == "poke":
        C.memmove(ram(step[1]), bytes.fromhex(step[2]), len(step[2]) // 2)
    elif op == "until":
        want = bytes.fromhex(step[2])
        n = 0
        while C.string_at(ram(step[1]), len(want)) != want and n < step[3]:
            run(1)
            n += 1
        print("until", step[1], "hit" if n < step[3] else "timeout", "frame", frames, flush=True)
    elif op == "view":
        prefix, maxp = step[1], step[2]
        crop = (step[3], step[4]) if len(step) > 4 else None
        idx = open(os.path.join(OUT, "view.tsv"), "a", encoding="utf-8")
        prev, same, last_shot, shown, stall, last_mk, run_mk = None, 0, None, 0, 0, 0, 0
        shot_marks, fb_mk, fb_at, fb_done, progress = set(), -1, 0, True, frames
        for _ in range(maxp * 700):
            run(1)
            cur = state["frame"]
            # 🔴 창이 없거나 쪽 대기가 없는 메시지(상점 토막 등)는 위 안정 판정에 안 걸린다 — 번호가 바뀐 지 50프레임 뒤에도 그 번호로 찍힌 게 없으면 전체 화면을 한 장 찍는다(5열 = 1, 「창 근거 없음」)
            mk_now = int.from_bytes(C.string_at(ram("$3FF8"), 2), "little")
            if mk_now != fb_mk:
                fb_mk, fb_at, fb_done, progress = mk_now, frames, mk_now in shot_marks, frames
            if frames - progress > 2000:  # 번호도 안 바뀌고 쪽도 안 찍힌 채 2000프레임 — 닫히지 않는 메시지. 호출부가 이 번호를 건너뛰고 다시 돈다
                print("stall 300 mk", mk_now.to_bytes(2, "little").hex(), "timeout", flush=True)
                break
            elif not fb_done and frames - fb_at >= 50 and shown < maxp:
                name = f"{prefix}{shown:04d}"
                img = cur if crop is None else cur[crop[0] : crop[1]]
                Image.fromarray(img).save(os.path.join(OUT, name + ".png"))
                idx.write(f"{name}\t{mk_now.to_bytes(2, 'little').hex()}\t{frames}\t0\t1\n")
                idx.flush()
                shot_marks.add(mk_now)
                progress = frames
                fb_done = True
                shown += 1
            # 🔴 멈췄나는 **대사창 안쪽만** 본다 — 지도의 물결·깜박이는 타일 때문에 전체 화면은 12프레임 같은 때가 없어 창이 떠 있어도 한 장도 못 찍었다(씬 126, 실측)
            win = winbox(cur)
            if same_win(win, prev):
                same += 1
            else:
                same = 0
            prev = win
            if same == 12 and win is not None and not same_win(win, last_shot):
                ptr = C.string_at(ram("$3FF8"), 2).hex()
                mk = int.from_bytes(bytes.fromhex(ptr), "little")
                if mk < last_mk:  # 번호가 되감기면 스텁이 한 바퀴 돌고 다시 들어온 것 — 한 바퀴만 찍는다
                    break
                run_mk = run_mk + 1 if mk == last_mk else 0
                if run_mk >= 30:  # 같은 번호에서 30쪽이 넘게 이어지면 닫히지 않는 창·되풀이 — 이 번호만 더는 안 찍는다(호출부가 「반복」으로 적는다)
                    print("view loop mk", mk, flush=True)
                    break
                last_mk = mk
                shot_marks.add(mk)
                progress = frames
                name = f"{prefix}{shown:04d}"
                img = cur if crop is None else cur[crop[0] : crop[1]]
                Image.fromarray(img).save(os.path.join(OUT, name + ".png"))
                last_shot = win.copy()
                # 완성 근거 = ▼ 대기 커서 — 쪽이 뜬 뒤 60프레임 동안 창 안쪽이 둘 이상으로 바뀌면(깜박임) 글이 다 나온 쪽이다(실측: 씬 126 은 90프레임에 2가지)
                seen = {win.tobytes()}
                for _ in range(60):
                    run(1)
                    w2 = winbox(state["frame"])
                    seen.add(w2.tobytes() if w2 is not None else b"")
                cur_flag = 1 if len(seen) > 1 else 0
                idx.write(f"{name}\t{ptr}\t{frames}\t{cur_flag}\t0\n")
                idx.flush()
                shown += 1
                stall = 0
                if shown >= maxp:
                    break
                state["held"] = {BTN["i"]}
                run(6)
                state["held"] = set()
                run(6)
            elif same >= 12:
                stall += 1
                if stall in (60, 180, 300):  # 닫히지 않는 창 — 다른 버튼으로 풀리는지(II·RUN·I) 본다
                    b = {60: "ii", 180: "run", 300: "i"}[stall]
                    print("stall", stall, "mk", C.string_at(ram("$3FF8"), 2).hex(), "press", b, flush=True)
                    state["held"] = {BTN[b]}
                    run(6)
                    state["held"] = set()
                    run(6)
                if stall > 600:
                    break
        Image.fromarray(state["frame"] if crop is None else state["frame"][crop[0] : crop[1]]).save(os.path.join(OUT, prefix + "END.png"))
        idx.close()
        print("view", prefix, "shots", shown, "frame", frames, flush=True)
    elif op == "battle":
        # 전투 한 판 촬영(디버그 롬 ED_BATTLE_DBG 전용 — 조우 번호를 `$3FFA` 에서 읽는다): ["battle", 접두, 번호hex, 최대쪽수]
        #   조우 번호를 poke → 위아래로 걸어 전투 화면(지도 영역이 까맣다)이 뜨길 기다림 → 메시지 창이 12프레임 멈추면 찍고 I → 필드로 돌아오면 끝.
        prefix, enc, maxp = step[1], step[2], step[3]
        dense = step[4] if len(step) > 4 else 0  # >0 이면 전투 프레임을 전부 `<접두>_d/` 에 저장(어디서 글이 빠지는지 볼 때) · step[5:7] = 저장할 프레임 범위 [시작, 끝)
        if dense:
            os.makedirs(os.path.join(OUT, prefix + "_d"), exist_ok=True)
        C.memmove(ram("3FFA"), bytes.fromhex(enc), len(enc) // 2)

        def dark(fr):
            reg = fr[50:170, 35:215]
            return float((reg.sum(axis=2) == 0).mean())

        walked = 0
        while walked < 400 and dark(state["frame"]) < 0.5:
            state["held"] = {BTN["down" if walked % 2 == 0 else "up"]}
            run(16)
            state["held"] = set()
            run(10)
            walked += 1
        idx = open(os.path.join(OUT, "battle.tsv"), "a", encoding="utf-8")
        if dark(state["frame"]) < 0.5:
            idx.write(f"{prefix}\t{enc}\tNO_ENCOUNTER\t{walked}\n")
            idx.close()
            print("battle", prefix, "no encounter", flush=True)
            continue
        TRACE = (os.path.join(OUT, prefix + "_d"), frames, step[5] if len(step) > 5 else 0, step[6] if len(step) > 6 else 10**9) if dense else None
        prev, same, last_shot, shown, stall, quiet = None, 0, None, 0, 0, 0
        victory = None  # 승리 창을 찍은 뒤 더 찍은 쪽 수(None = 아직 못 찍음)
        for _ in range(maxp * 700):
            run(1)
            cur = state["frame"]
            win = winbox(cur)
            same = same + 1 if same_win(win, prev) else 0
            prev = win
            if dark(cur) < 0.05 and win is None:
                quiet += 1
                if quiet > 25 and shown >= 3:  # 필드로 돌아와 25프레임 — 전투 끝(한 판만. 더 두면 같은 자리에서 다음 조우가 붙는다)
                    break
            else:
                quiet = 0
            if same == 12 and win is not None and not same_win(win, last_shot):
                name = f"{prefix}_{shown:03d}"
                Image.fromarray(cur).save(os.path.join(OUT, name + ".png"))
                last_shot = win.copy()
                seen = {win.tobytes()}
                vname = None
                if victory is not None:
                    victory += 1
                elif is_victory(cur):
                    victory = 0
                    vname = name
                shown += 1
                # 찍은 뒤 60프레임 관찰 — 이 사이 창이 저절로 다음 쪽으로 넘어가며 승리 창이 여기서 떴다(블라인드였다).
                # 눈을 떼지 않고, 12프레임 선 승리 창이면 그 쪽도 찍는다(다른 쪽은 아래 본 루프가 찍는다)
                ow, oc = None, 0
                for _ in range(60):
                    run(1)
                    w2 = winbox(state["frame"])
                    seen.add(w2.tobytes() if w2 is not None else b"")
                    oc = oc + 1 if same_win(w2, ow) else 0
                    ow = w2
                    if oc == 12 and w2 is not None and victory is None and not same_win(w2, last_shot) and is_victory(state["frame"]):
                        vname = f"{prefix}_{shown:03d}"
                        Image.fromarray(state["frame"]).save(os.path.join(OUT, vname + ".png"))
                        last_shot = w2.copy()
                        victory = 0
                        shown += 1
                idx.write(f"{name}\t{enc}\t{frames}\t{1 if len(seen) > 1 else 0}\n")
                if vname:
                    idx.write(f"{prefix}\t{enc}\tVICTORY\t{vname}\n")  # 이 쪽이 승리 문구 — 뒤 쪽(레벨 업 등)은 3쪽까지만 더 찍고 끝낸다
                idx.flush()
                stall = 0
                if shown >= maxp or (victory is not None and victory >= 3):
                    break
                state["held"] = {BTN["i"]}
                run(6)
                state["held"] = set()
                run(6)
            elif same >= 12:
                stall += 1
                if stall in (60, 180):
                    state["held"] = {BTN["i"]}
                    run(6)
                    state["held"] = set()
                    run(6)
                if stall > 400:
                    idx.write(f"{prefix}\t{enc}\tSTALL\t{frames}\n")
                    break
        TRACE = None
        Image.fromarray(state["frame"]).save(os.path.join(OUT, f"{prefix}_END.png"))
        idx.write(f"{prefix}\t{enc}\tEND\tshots={shown} walked={walked}\n")
        idx.close()
        print("battle", prefix, "enc", enc, "shots", shown, "walked", walked, "frame", frames, flush=True)
    elif op == "save":
        n = core.retro_serialize_size()
        b = C.create_string_buffer(n)
        core.retro_serialize(b, n)
        open(step[1], "wb").write(b.raw)
    elif op == "load":
        d = open(step[1], "rb").read()
        core.retro_unserialize(d, len(d))
print("done", frames)
