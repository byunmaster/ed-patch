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


def load(drafts: bool = False) -> dict[str, list[dict]]:
    """씬 → 토막 목록(음성이 둘 이상인 장면은 토막이 여럿). 정본이 토막 하나면 dict 로 적어도 된다.
    🔴 `draft` 항목(받아쓰기 자동 초안, 마스터 검수 전 — `voice_draft.py`)은 기본으로 **뺀다**: 제품(OFF 흐름 + 시각표 `patch_block`)과 게이트는 정식만 본다.
    시험 빌드의 비모달 자막(`gwin_rt.on_flow_spec`)과 편집기 자료만 `drafts=True` 로 본다."""
    raw = json.loads(SPEC.read_text("utf-8"))["scenes"] if SPEC.exists() else {}
    out = {k: v if isinstance(v, list) else [v] for k, v in raw.items()}
    return out if drafts else {k: v for k, v in out.items() if not any(seg.get("draft") for seg in v)}


def scene_ids(drafts: bool = False) -> set[int]:
    return {int(k) for k in load(drafts)}


def pages_of(sid: int, key: str, msgs: dict[str, M.Message]) -> int:
    """그 메시지가 화면에 뜰 때의 쪽 수 — 번역이 있으면 조판 결과, 없으면 원문 `\\f` 쪽."""
    m = msgs.get(key)
    if m is None:
        raise SchedError(f"scn{sid:03d}: 열쇠 {key} 가 원문 블록에 없다")
    tr = M.load_translations(sid).get(key)
    if tr is not None and tr["t"]:
        return len(typeset.pages(font.expand_packed(tr["t"]), speaker=M.speaker_kind(m, sid), four=True, keep_windows=typeset.keep_windows(sid)))
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
        errs += _unlisted(sid, si, spec, msgs)
    return errs


def _unlisted(sid: int, si: int, spec: dict, msgs: dict[str, M.Message]) -> list[str]:
    """🔴 표에 없는 창이 표 구간 한가운데 끼면 **그 창이 뒤 대사의 칸을 먹어** 시각이 통째로 밀린다(10-29 씬 6: 장비 문구 세 창이 빠져 검 줄이 ≈450프레임 서고,
    표가 세 칸 모자라 마지막 쪽이 자동 넘김을 잃고 입력 대기가 됐다). 블록 안 위치가 표의 첫·끝 메시지 사이에 있는 **글이 든 메시지**가 표에 없으면 실패 —
    흐름상 구간 밖(앞 장면)이거나 같은 창 이어쓰기면 `unlisted_ok`(열쇠 → 사유)로 적는다. 정적 근사라 놓칠 수 있다(분기 흐름은 에뮬로 확인)."""
    listed = {it["key"] for it in spec["msgs"]}
    pos = [msgs[k].start for k in listed if k in msgs]
    if not pos:
        return []
    lo, hi = min(pos), max(pos)
    ok = spec.get("unlisted_ok", {})
    out = []
    for k, m in msgs.items():
        if k in listed or k in ok or not (lo <= m.start <= hi) or not m.jp.strip():
            continue
        out.append(f"scn{sid:03d} 토막{si}: 표에 없는 창 {k}(블록 {m.start}) 가 표 구간 {lo}~{hi} 안에 있다 — 표에 넣거나 unlisted_ok 에 사유를 적는다")
    return out


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
    for spec in segs:
        if spec.get("bgm_guard"):
            _guard_bgm(sid, out)
        if spec.get("wait_voice_end"):
            _wait_voice_end(sid, out, float(spec["voice_end"]))
        if spec.get("equip_sfx"):
            _equip_sfx(sid, out)
    return bytes(out), len(todo)


# 🔴 음성(ADPCM)과 BGM(CD-DA)은 **같은 CD 드라이브**를 쓴다 — BGM 이 돌면 BIOS 의 ADPCM 반 버퍼 보충(IRQ2)이 「드라이브 사용 중」으로 스트림을 포기한다(마스터 10-30 「하야끄 첫 음절만」:
# 씬 6 의 OFF 흐름이 음성을 튼 바로 그 프레임에 BGM(`JSR $645E`·`$6490` = 곡 15 요청·시작)을 걸어, 음성이 반 버퍼(≈4초, 프레임 247)에서 끊겼다 — 원판 ON 흐름은 그 둘을 건너뛰어 음성 동안 BGM 이 없고
# 음성이 끝난 뒤 다음 장면이 곡을 건다(원판 ON: 11155 BGM 정지 → 15493 재개, 음성 11189~15435 실측). 그래서 ON(음성)일 때만 그 BGM 요청을 건너뛴다.
BGM_REQ = bytes([0x20, 0x5E, 0x64, 0x20, 0x90, 0x64])  # JSR $645E · JSR $6490


def _guard_bgm(sid: int, out: bytearray) -> None:
    sites = [m.start() for m in re.finditer(re.escape(BGM_REQ), bytes(out))]
    if len(sites) != 1:
        raise SchedError(f"scn{sid:03d}: BGM 요청(JSR $645E · $6490)이 {len(sites)}곳(하나여야 — 손으로 본다)")
    stub_at = BASE + len(out)
    # LDA $C04C · BNE 건너뜀(ON = 음성 중) · 원래 두 호출 · RTS
    out += b"\xad\x4c\xc0\xd0\x06" + BGM_REQ + b"\x60"
    if len(out) > 0x2000:
        raise SchedError(f"scn{sid:03d}: BGM 보호 스텁을 붙이면 블록이 {len(out)}B — 뱅크(8KB)를 넘는다")
    o = sites[0]
    out[o : o + 6] = b"\x20" + stub_at.to_bytes(2, "little") + b"\xea\xea\xea"


# 원판 ON 흐름은 연출 박자가 음성 길이와 같아 끝 자리(`LDA $C04C · BEQ · … JSR $589D` 음성 정지)에 닿을 때 음성이 막 끝나 있다. 우리 OFF 흐름은 창 시각표가 끝나는 때 닿아서 음성이 남았는데
# 정지 호출이 잘랐다(씬 6: 음성 71초 중 65초에서 정지 — 끝 6초 실종, 10-30 실측). 그래서 그 자리 앞에서 ON 일 때 **원판이 음성을 멈춘 때**(`voice_end` 초 — 음성 시작에서 잰다.
# 씬 6 = 원판 ON 실측 4246프레임 ≈ 70.8초)까지 기다린다. ADPCM 이 먼저 쉬면 거기서 끝낸다(최대 ≈17초).
# 🔴 처음엔 ADPCM 이 쉴 때까지만 기다렸는데(73.6초) 마지막 대사 뒤 음성 꼬리(무음)가 원판보다 2.8초 길어 대사창 없이 멈춘 화면이 이어졌다(마스터 10-30 「정지된 상태에서 시간이 지나면 풀린다」).
VOICE_END_AT = bytes.fromhex("ad4cc0f00aa9ff856c206b58209d58")  # LDA $C04C · BEQ +10 · LDA #$FF · STA $6C · JSR $586B · JSR $589D


def _voice_end_stub(end_frames: int) -> bytes:
    """ON 이면 ADPCM 이 쉬거나 음성 시작(`sched` 의 b0·b1)에서 `end_frames` 프레임이 지날 때까지 4프레임씩 기다린 뒤 `LDA $C04C` 로 돌아간다."""
    fc = G.FRAMECNT
    lab = G._resident_asm().labels
    b0, b1 = lab["b0"], lab["b1"]
    nh, nl = end_frames >> 8, end_frames & 0xFF
    w = bytearray()
    w += bytes.fromhex("a9ff48")  # LDA #$FF · PHA (제한 횟수)
    wait = len(w)
    w += bytes.fromhex("2045e0" "89ff")  # wait: JSR AD_STAT · BIT #$FF
    fix_done1 = len(w)
    w += b"\xf0\x00"  # BEQ done(ADPCM 쉼)
    w += b"\x38" + b"\xad" + fc.to_bytes(2, "little") + b"\xed" + b0.to_bytes(2, "little") + b"\xaa"  # SEC · LDA cnt · SBC b0 · TAX
    w += b"\xad" + (fc + 1).to_bytes(2, "little") + b"\xed" + b1.to_bytes(2, "little")  # LDA cnt+1 · SBC b1
    w += bytes([0xC9, nh, 0x90, 0x06])  # CMP #nh · BCC wait2 (모자람)
    fix_done2 = len(w)
    w += b"\xd0\x00"  # BNE done (넘음)
    w += bytes([0xE0, nl])  # CPX #nl
    fix_done3 = len(w)
    w += b"\xb0\x00"  # BCS done
    w += bytes.fromhex("a204" "a000" "20d75b")  # wait2: LDX #4 · LDY #0 · JSR $5BD7 (4프레임)
    w += bytes.fromhex("68" "3a")  # PLA · DEC
    fix_out = len(w)
    w += b"\xf0\x00"  # BEQ out
    w += b"\x48"  # PHA
    w += bytes([0x80, (wait - (len(w) + 2)) & 0xFF])  # BRA wait
    done = len(w)
    w += b"\x68"  # done: PLA
    out = len(w)
    w += bytes.fromhex("ad4cc0" "60")  # out: LDA $C04C · RTS (Z = OFF 여부)
    for at, tgt in ((fix_done1, done), (fix_done2, done), (fix_done3, done), (fix_out, out)):
        d = tgt - (at + 2)
        assert 0 <= d < 0x80, (at, tgt)
        w[at + 1] = d
    # 앞머리: LDA $C04C · BEQ out(OFF = 음성 없음) — 머리가 5B 라 본체 오프셋 out 이 그대로 상대 거리다
    head = b"\xad\x4c\xc0" + bytes([0xF0, out])
    return head + bytes(w)


def _wait_voice_end(sid: int, out: bytearray, secs: float) -> None:
    sites = [m.start() for m in re.finditer(re.escape(VOICE_END_AT), bytes(out))]
    if len(sites) != 1:
        raise SchedError(f"scn{sid:03d}: 음성 끝 자리(`LDA $C04C … JSR $589D`)가 {len(sites)}곳(하나여야)")
    stub_at = BASE + len(out)
    out += _voice_end_stub(round(secs * G.FPS))
    if len(out) > 0x2000:
        raise SchedError(f"scn{sid:03d}: 음성 끝 스텁을 붙이면 블록이 {len(out)}B — 뱅크(8KB)를 넘는다")
    o = sites[0]
    out[o : o + 3] = b"\x20" + stub_at.to_bytes(2, "little")


# 원판 ON 흐름의 장비 창(`$A917`)은 메시지 뒤에 효과음 호출(`JSR $981F`)을 하는데 우리 OFF 흐름(게이트 1 강제 OFF)은 그 호출이 없어 장비 효과음이 빠졌다(마스터 10-30 「원본은 효과음 나오면서」).
# OFF 경로의 장비 메시지 표시(`JSR $5B5B`, 뒤에 `LDA #0 · STA $12 · LDA #$C3 · STA $13 · LDA #$18 · STA $F8 · JSR $4FD8` 줄 이음)를 스텁으로 돌려, 나레이션 ON 일 때만 표시 뒤 효과음을 건다.
EQUIP_AT = re.compile(rb"\xa9.\x85\x10\xa9.\x85\x11(\x20\x5b\x5b)\xa9\x00\x85\x12\xa9\xc3\x85\x13\xa9\x18\x85\xf8\x20\xd8\x4f", re.DOTALL)
EQUIP_STUB = bytes.fromhex("205b5b" "ad4cc0" "f003" "201f98" "60")  # JSR $5B5B · LDA $C04C · BEQ +3 · JSR $981F · RTS


def _equip_sfx(sid: int, out: bytearray) -> None:
    ms = list(EQUIP_AT.finditer(bytes(out)))
    if len(ms) != 1:
        raise SchedError(f"scn{sid:03d}: 장비 메시지 표시 자리가 {len(ms)}곳(하나여야)")
    stub_at = BASE + len(out)
    out += EQUIP_STUB
    if len(out) > 0x2000:
        raise SchedError(f"scn{sid:03d}: 장비 효과음 스텁을 붙이면 블록이 {len(out)}B — 뱅크(8KB)를 넘는다")
    o = ms[0].start(1)
    out[o : o + 3] = b"\x20" + stub_at.to_bytes(2, "little")


_GAP_NAME = re.compile(rb"\x09([\x00-\x3f])")


def inline_name(blk: bytes, ms: list, i: int) -> tuple[int | None, int | None]:
    """메시지 `ms[i]` 맨 앞의 `09 nn`(공용 화자 번호 `m.common`)이 **창 머리(화자)** 인가 **본문에 끼우는 이름 변수** 인가 — (이름 변수 번호, 머리 번호).
    · 사이 바이트(앞 메시지 끝~이 메시지 시작)에 `09 xx` 가 있으면 그게 머리 · 이 메시지의 `09` 는 이름 변수 (씬 32 「…라는 건달입니다.」 = 머리 류난 + 이름 로우)
    · 사이가 비었고 앞 메시지가 글로 끝났으면(쪽 넘김·종료가 아님) 이 `09` 는 이름 변수 (씬 41 「…おれは」+이름+「…って」)
    · 아니면 머리(이 메시지가 새 창을 연다) → (None, m.common). 11-04 마스터 「음성자막에 로우가 빠져 있어」 — 엔진은 이름을 끼워 찍는데 편집기·ON 명세는 그 조각을 안 넣었다."""
    m = ms[i]
    if m.common is None:
        return None, None
    if i == 0:
        return None, m.common
    prev = ms[i - 1]
    gap = blk[prev.end : m.start]
    mg = _GAP_NAME.search(gap) if len(gap) <= 6 else None
    if mg:
        return m.common, mg.group(1)[0]
    if not gap and prev.tokens and isinstance(prev.tokens[-1], str):
        return m.common, None
    return None, m.common


def with_inline_name(blk: bytes, ms: list, i: int, kr: str) -> str:
    """이름 변수가 끼는 메시지면 우리 이름(정본)을 앞에 붙인 문안 — 아니면 그대로."""
    nm, _hd = inline_name(blk, ms, i)
    if nm is None or not kr:
        return kr
    import gwin_rt

    return gwin_rt.common_speaker(nm) + kr


def fit_ends(ends: list, n: int) -> list:
    """시각표 쪽 끝 시각 목록을 조판이 낸 쪽 수 `n` 에 맞춘다 — 원문 창 기준으로 한 창에 합쳐(typeset_fit_one) 쪽이 줄었으면 마지막 끝 시각만 남긴다(앞 쪽 끝은 합쳐진다). 늘었으면 그대로 둔다(호출부가 알린다)."""
    return [*ends[: n - 1], ends[-1]] if 0 < n < len(ends) else list(ends)


def tail_join(blk: bytes, ms: list, i: int, tr: dict, parts: bool = False, stop: frozenset | set = frozenset()) -> str | list[tuple[str, str]] | None:
    """메시지 `ms[i]` 의 **같은 창 이어쓰기**를 이은 우리 문안(없으면 None) — 끝이 글자(쪽 넘김·줄바꿈·종료 옵코드가 아님)면 엔진은 다음 메시지 글을 같은 창에 이어 찍는다.
    이음 사이 바이트(gap): `09 nn` = 파티 이름(공용 화자) · `81 42`(。) = 「.」 · 그 밖은 무시(줄바꿈 `01`은 공백으로 — 자막은 조판이 다시 흘린다).
    `parts=True` 면 이은 한 줄이 아니라 **원문 메시지 경계대로** [(열쇠, 문안), …] 로 낸다(앞 조각은 이름·「.」까지, 뒷 조각은 그 뒤 메시지 — 씬 18 #3 을 두 자막으로, 11-04).
    이름 앞에는 글자와 붙지 않게 공백 하나 둔다. 편집기·비모달 자막이 쓴다(11-03: 씬 18 #3 「제 이름은」에서 끊김 · 씬 50 「또」 — 이음 조각을 안 읽었다)."""
    out = (tr.get(ms[i].key) or {}).get("t")
    if out is None:
        return None
    n = 0
    segs = [[ms[i].key, out]]
    while ms[i].tokens and isinstance(ms[i].tokens[-1], str) and i + 1 < len(ms):
        nxt = ms[i + 1]
        gap = blk[ms[i].end : nxt.start]
        kr = (tr.get(nxt.key) or {}).get("t")
        if nxt.key in stop:  # 뒷 조각이 따로 행(편집기 `listed`)이면 거기서 멈춘다 — 같은 문장이 두 행에 들어간다(11-05 씬 50 「헤집혀 있어.」)
            break
        if kr is None or nxt.start < ms[i].end or len(gap) > 12 or (gap and gap[-1] in (0x05, 0x03)):  # 사이 마지막 옵코드가 쪽 넘김이면 새 창 — 이음이 아니다(줄바꿈 `01` 은 같은 창)
            break
        piece = ""
        g = 0
        while g < len(gap):
            m = _GAP_NAME.match(gap, g)
            if m:
                import gwin_rt

                piece += ("" if out.endswith(" ") else " ") + gwin_rt.common_speaker(m.group(1)[0])
                g += 2
            elif gap[g : g + 2] == b"\x81\x42":
                piece += "."
                g += 2
            elif gap[g] == 0x01:
                piece += " "
                g += 1
            else:
                g += 1
        out += piece + kr
        segs[-1][1] += piece.rstrip(" ")
        segs.append([nxt.key, kr.lstrip(" ")])
        i += 1
        n += 1
    if parts:
        return [tuple(x) for x in segs] if n else None
    return out if n else None
