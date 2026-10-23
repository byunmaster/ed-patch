"""음성 장면의 **나레이션 OFF 흐름 + 음성 + 전역 시각표**(마스터 10-12 「나레이션 off 때의 대사창 기준으로 음성에 맞춰서 기존 대사창을 넘긴다」).

게이트 자막(`narration_gates.patch_block`)은 ON 경로에 타이머가 하나 있는 자리만 건다. 원판 ON 은 그 밖에도 하위 스크립트(`$5EC9`)·연출 박자로 음성에 맞춰 짠
**ON 전용 연출**을 따로 갖고 있어 대사창이 안 뜨는 자리가 있다(006·032·041·098·151). 게임의 대사창은 월드를 멈추는 모달이라 연출과 동시에 흐르는 자막 창은
이 엔진으로 안 된다(장면 2 실측: 초기화 쪽에 창을 끼우자 컷신이 통째로 죽었다). 그래서 이 장면들은 **ON 이어도 OFF 흐름**(대사창 + 연출)으로 보내고 음성만 얹는다:

  · 음성이 시작되는 게이트(`voice_gate`)의 `LDA $C04C` 를 스텁 호출로 바꾼다 — 스텁은 나레이션이 ON 이면 원래 음성을 틀고 **전역 시각표**(`narration_gates` 상주부 `sched`)를
    건 뒤 어느 쪽이든 `LDA #0` 으로 돌아와 원래 `BEQ` 가 OFF 경로로 간다(나레이션 OFF 면 음성도 시각표도 없이 원판 OFF 그대로).
  · 같은 장면의 나머지 ON 게이트(`force_off`)는 `LDA $C04C` 를 `LDA #0 · NOP` 으로 — ON 에서도 OFF 흐름으로 간다(OFF 설정에서는 원래도 그렇다).
  · 시각표 = 그 토막에서 뜨는 모든 쪽의 끝 시각(음성 시작에서 잰 초), 메시지 순서대로. 대사창은 쪽마다 즉시 찍히고 그 시각에 자동으로 넘어간다 —
    연출 시간이 길어 늦게 뜬 창은 밀린 만큼 빨리 넘어간다. 마지막 쪽이 넘어가면 자동 넘김은 꺼진다.

정본 `script/voice_sched.json`:
    {"scenes": {"98": {"voice_gate": 2, "force_off": [0, 1],
                       "msgs": [{"key": "<메시지 열쇠>", "ends": [쪽마다 끝 시각(초)]}, …]}}}
메시지 순서는 나레이션 OFF 로 실제로 흐르는 순서(에뮬로 확인)고, `ends` 길이는 그 메시지의 쪽 수(조판 결과)와 같아야 한다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import font
import messages as M
import narration_gates as G
import typeset

SPEC = common.GAME_DIR / "script" / "voice_sched.json"
BASE = M.BASE


class SchedError(Exception):
    pass


def load() -> dict[str, list[dict]]:
    """씬 → 토막 목록(음성이 둘 이상인 장면은 토막이 여럿). 정본이 토막 하나면 dict 로 적어도 된다."""
    raw = json.loads(SPEC.read_text("utf-8"))["scenes"] if SPEC.exists() else {}
    return {k: v if isinstance(v, list) else [v] for k, v in raw.items()}


def scene_ids() -> set[int]:
    return {int(k) for k in load()}


def pages_of(sid: int, key: str, msgs: dict[str, M.Message]) -> int:
    """그 메시지가 화면에 뜰 때의 쪽 수 — 번역이 있으면 조판 결과, 없으면 원문 `\\f` 쪽."""
    m = msgs.get(key)
    if m is None:
        raise SchedError(f"scn{sid:03d}: 열쇠 {key} 가 원문 블록에 없다")
    tr = M.load_translations(sid).get(key)
    if tr is not None and tr["t"]:
        return len(typeset.pages(font.expand_packed(tr["t"]), speaker=m.speaker is not None or m.common is not None))
    return len([p for p in m.jp.split("\f") if p.strip()]) or 1


def validate(sid: int, orig: bytes) -> list[str]:
    segs = load().get(str(sid))
    if not segs:
        return []
    msgs = {m.key: m for m in M.parse(orig)}
    errs: list[str] = []
    for si, spec in enumerate(segs):
        last = 0.0
        for i, it in enumerate(spec["msgs"]):
            try:
                n = pages_of(sid, it["key"], msgs)
            except SchedError as e:
                errs.append(str(e))
                continue
            ends = [float(x) for x in it["ends"]]
            if len(ends) != n:
                errs.append(f"scn{sid:03d} 토막{si} 메시지 {i}({it['key']}): 쪽 {n}개 · 끝 시각 {len(ends)}개")
            for e in ends:
                if e <= last:
                    errs.append(f"scn{sid:03d} 토막{si} 메시지 {i}: 끝 시각 {e} 이 앞 시각 {last} 이하")
                last = e
    return errs


def voice_of(blk: bytes, gate: int) -> tuple[int, int]:
    """음성 게이트의 ON 경로가 거는 음성 — (디스크 rel, 섹터 수). 편집기 자료가 쓴다."""
    import voice

    gates = [m.start() for m in re.finditer(re.escape(G.GATE), blk)]
    o = gates[gate]
    v = G.VOICE_AT.search(blk, o + 5, o + 5 + blk[o + 4])
    if not v:  # `voice_from` 로 앞 게이트가 틀 때 — 호출은 다른 게이트의 ON 경로에 있다
        for g2 in gates:
            v = G.VOICE_AT.search(blk, g2 + 5, g2 + 5 + blk[g2 + 4])
            if v:
                break
    if not v:
        raise SchedError(f"게이트 {gate}: ON 경로에 음성 호출이 없다")
    return voice.VOICE_BASE + (blk[v.start() + 3] | blk[v.start() + 4] << 8), blk[v.start() + 5] | blk[v.start() + 6] << 8


def table(spec: dict) -> bytes:
    """`[쪽 수] + 쪽마다 끝 프레임(16비트)` — 음성 시작(상주부 `sched` 가 카운터를 적은 때)에서 잰다."""
    ends = [float(e) for it in spec["msgs"] for e in it["ends"]]
    out = bytearray([len(ends)])
    for e in ends:
        f = round(e * G.FPS)
        if not 0 <= f <= 0xFFFF:
            raise SchedError(f"끝 시각 {e}초가 16비트 프레임을 넘는다")
        out += f.to_bytes(2, "little")
    if len(ends) > 0xFF:
        raise SchedError(f"쪽 {len(ends)}개 — 한 바이트에 안 든다")
    return bytes(out)


def patch_block(sid: int, orig: bytes, blk: bytes) -> tuple[bytes, int]:
    """씬 `sid` 블록을 OFF 흐름 + 음성 + 전역 시각표로 바꾼다. (새 블록, 바꾼 게이트 수)."""
    segs = load().get(str(sid))
    if not segs:
        return blk, 0
    errs = validate(sid, orig)
    if errs:
        raise SchedError("\n".join(errs))
    out = bytearray(blk)
    gates = [m.start() for m in re.finditer(re.escape(G.GATE), bytes(out))]
    todo: list[tuple[int, str, dict]] = []
    for spec in segs:
        todo.append((spec["voice_gate"], "voice", spec))
        todo += [(g, "off", spec) for g in spec.get("force_off", [])]
    for gi, _, _ in todo:
        if gi >= len(gates):
            raise SchedError(f"scn{sid:03d}: 게이트 {gi} 가 없다(블록에 {len(gates)}개)")
        if out[gates[gi] + 3] != 0xF0:
            raise SchedError(f"scn{sid:03d} 게이트 {gi}: BEQ 가 아니다")
    if len({gi for gi, _, _ in todo}) != len(todo):
        raise SchedError(f"scn{sid:03d}: 같은 게이트를 두 번 고친다")
    for gi, kind, spec in todo:
        o = gates[gi]
        if kind == "off":
            out[o : o + 3] = b"\xa9\x00\xea"  # LDA #0 · NOP — Z 가 서서 BEQ 가 OFF 경로로 간다
            continue
        # `voice_from` — 음성 호출이 **다른 게이트**의 ON 경로에 있을 때(씬 18: 음성 첫 문장은 앞 창의 대사라 앞 게이트에서 틀어야 한다) 그 게이트에서 호출 바이트를 가져온다.
        # 가져온 게이트는 `force_off` 에 들어 있어야 한다(ON 경로를 안 타서 음성이 두 번 나가지 않는다).
        src = gates[spec["voice_from"]] if "voice_from" in spec else o
        if "voice_from" in spec and spec["voice_from"] not in spec.get("force_off", []):
            raise SchedError(f"scn{sid:03d}: voice_from {spec['voice_from']} 가 force_off 에 없다 — 음성이 두 번 난다")
        tgt = src + 5 + out[src + 4]
        v = G.VOICE_AT.search(bytes(out), src + 5, tgt)
        if not v:
            raise SchedError(f"scn{sid:03d} 게이트 {gi}: ON 경로에 음성 호출이 없다")
        voice_call = bytes(out[v.start() : v.start() + 7])  # JSR $5815 + 인라인 4B
        # ON 경로가 음성 앞에서 하던 일(플래그 세우기 등)을 같이 옮긴다 — `copy_prefix`. 위치 독립이고 호출·점프가 없는 바이트만(예: `LDA · ORA · STA`)
        if spec.get("copy_prefix"):
            if "voice_from" in spec:  # 음성 게이트의 ON 경로 전체(메시지 없이 플래그만 세우고 끝나는 꼴)를 옮긴다 — 끝의 `BRA`(2B)는 뺀다
                end = o + 5 + out[o + 4]
                prefix = bytes(out[o + 5 : end - 2]) if out[end - 2] == 0x80 else bytes(out[o + 5 : end])
            else:
                prefix = bytes(out[o + 5 : v.start()])
        else:
            prefix = b""
        if len(prefix) > 24:
            raise SchedError(f"scn{sid:03d} 게이트 {gi}: ON 앞부분이 {len(prefix)}B — 손으로 보고 정한다(copy_prefix 상한 24B)")
        tab = table(spec)
        stub_at = BASE + len(out)
        body = prefix + voice_call + bytes([0xA9, 0, 0xA2, 0]) + b"\x20" + G.SCHED.to_bytes(2, "little")
        stub_len = 3 + 2 + len(body) + 3
        tab_at = stub_at + stub_len
        body = prefix + voice_call + bytes([0xA9, tab_at & 0xFF, 0xA2, tab_at >> 8]) + b"\x20" + G.SCHED.to_bytes(2, "little")
        if len(body) > 0x7F:
            raise SchedError(f"scn{sid:03d} 게이트 {gi}: 스텁 본체 {len(body)}B — BEQ 한 바이트에 안 든다")
        stub = bytearray(b"\xad\x4c\xc0")  # LDA $C04C
        stub += bytes([0xF0, len(body)])  # BEQ → LDA #0 (나레이션 OFF: 음성도 시각표도 없이 원판 OFF)
        stub += body
        stub += b"\xa9\x00\x60"  # LDA #0 · RTS
        assert len(stub) == stub_len, (len(stub), stub_len)
        out += stub + tab
        if len(out) > 0x2000:
            raise SchedError(f"scn{sid:03d}: 스텁·표를 붙이면 블록이 {len(out)}B — 뱅크(8KB)를 넘는다")
        out[o : o + 3] = b"\x20" + stub_at.to_bytes(2, "little")
    return bytes(out), len(todo)
