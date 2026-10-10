"""시스템 메시지 — 코드가 `lea/pea` 로 직접 가리키는 렌더러 스트림(아이템 획득·레벨업·전투·미니게임).

    python3 tools/sysmsg.py --check   # 분모 재현
    python3 tools/sysmsg.py --seed    # textmap/sysmsg.json 초안(해시만) + work/derived/text/sysmsg.txt(원문)

- 참조: `4?FA dddd`(lea d(pc)) · `487A dddd`(pea) · `4?F9 / 4879 + abs.l`. 코드 영역(< 0x40000, LZ 밖)만.
- 문자열은 씬 모듈과 같은 렌더러(`$978C`) 스트림이다 — 끝은 00·06·07, `0F` goto · `10` call 오프셋,
  **뒤쪽을 공유하는 하위 문자열**(같은 꼬리를 다른 자리에서 가리킨다)이 흔하다. `scene.parse_stream` 을 그대로 쓴다.
- 묶음 = 스트림 범위가 잇닿은 구간. 재삽입은 **묶음 안**에서 스트림을 차례로 다시 쓰고(넘치면 실패),
  goto/call 오프셋과 참조 명령의 변위(pc 상대 16비트 / abs 32비트)를 고친다.
- 창 폭이 문맥마다 달라 **자동 조판은 안 한다** — `ours` 의 `\\n` 이 01, 제어코드는 `<02>`(주인공 이름)
  `<0e>`(아이템 이름) 처럼 raw 태그, 참조는 `<0f:XXXXXX>`(절대 주소) 그대로. 문장급이라 원문은 해시만.
"""

import hashlib
import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import scene

CODE_END = 0x40000
LZ = [(0x085E52, 0x09D86E), (0x0CAB04, 0x0D85B4), (0x0D8814, 0x12261C), (0x1293E0, 0x134DDC)]
MAP_JSON = common.GAME_DIR / "textmap" / "sysmsg.json"
EXPECT = (
    166,
    68,
)  # 스트림 · 묶음 (2026-09-06 — 워드 표 0x73bc · 고정 스트림 19 · _textlike 0x80 고침
#     · 09-26 묶음 안 참조 3 — 0x7402·0x2ba62·0x325a6 · 09-27 짧은 가나 조각 3 — 0x24a68·0x2b272·0x324dd)
EXCLUDE = {0x1ED0C, 0x32E2A}  # '付近入口H鄲 $Kr' — cp932 로 우연히 풀리는 코드. 눈으로 확인해 뺀다

# 워드 오프셋 표: 표 자리 → 항목 수. 코드가 `lea $73bc.l,a3` + `move.w (a3,d0.w),d0` +
# `lea (a3,d0.w),a1` 로 고른다(0x717a·0x71a6·0x7f56). 항목 = 표 자리에서의 **부호 있는 워드 변위**.
# ⚠ 이 표가 가리키는 스트림은 `lea` 참조가 없어 2026-09-06 까지 **통째로 빠져 있었다**
# (주문·아이템 효과 메시지 — MP 부족·주문 봉인 따위). `_textlike` 도 건너뛴다 —
# 표에 실렸다는 것 자체가 문안이라는 증거고, 「<02>は<06>」 같은 한 글자 연결어는 걸러지기 때문이다.
WORD_TABLES = {0x73BC: 33}

# 자리를 못 옮기는 스트림 — **소비자를 아직 못 찾았다.** 06 으로 끊긴 앞 스트림 뒤에 물리적으로
# 이어지는 「수치 뒤 꼬리말」(빼앗음·오름·늘어남·내려감의 과거형)인데, 셋 중 하나를 고르는
# 코드가 lea/pea/절대 상수 어디에도 안 잡힌다(2026-09-06 실측). ⇒ **제자리에, 원본 길이 안에서만**
# 다시 쓴다. 각자 자기 묶음이 되어 앞뒤 스트림 재배치의 영향을 안 받는다.
PINNED = {
    0x762A,
    0x7640,
    0x764C,
    0x7656,  # 수치 뒤 꼬리말(빼앗음·오름·늘어남·내려감)
    0x2A9D6,
    0x2A9EE,  # 능력 강화 물음 둘
    0x3105F,
    0x310A2,  # 오델로 승패 대사(앞의 goto 스트림이 참조를 든다)
    0x4195,  # 🔴 06 바로 뒤가 꼬리의 시작이다 — 0x419B 로 잡아 앞 「ﾎﾟｲﾝﾄ 」(반각 가나)가 번역 없이 남아
    #   화면에 「최대 ＨＰ가 9999ﾎﾟｲﾝﾄ 올랐다」로 떴다(09-27). MP 꼬리(0x41B2)는 처음부터 제자리였다.
    0x75EE,
    0x760F,
    0x76BE,  # 06 뒤로 이어지는 꼬리말(오름·획득·회복)
    0x20202,  # 🔴 같은 부류 — 「ＥＰ 1ﾎﾟｲﾝﾄ 획득했다」(전투 승리, 09-27 인게임)
    0x24AAE,
    0x24B0A,  # 🔴 「<08><0e>+목적격+소지 과거형」 꼬리의 시작 — 0x24B0C 로 잡아 <0e> 가 스트림 밖이라 조사 훅을 못 붙였다(09-27)
    0x24B65,
    0x324BB,
    0x324C2,
    0x324E2,  # 미니게임 전투 문구
}


# 묶음에서 **꼬리로 옮기는** 스트림 — 묶음이 원문 합보다 빠듯해(0x24a68~0x24aad 69B) 조사를 못 넣던 자리.
# 참조가 절대 주소(`lea abs.l`)인 스트림만 옮길 수 있다(pc 상대는 ±32KB). 도망 둘(0x24a7a 복수 · 0x24a7e 단수):
# 단수가 복수의 꼬리를 공유하던 걸 풀어 각자 두고, 단수에 리더 기준 조사 훅(`<ebf0>`)을 단다(마스터 10-09).
RELOCATE = (
    0x24A7A,
    0x24A7E,
    # 「하지만 운 좋게/나쁘게 …에게는 맞지 않았다」 묶음(0x24b1b~) — 원문 「運良く…には」을 PS1 꼴로 늘려(에겐→에게는 · 용케→운 좋게)
    # 묶음이 7B 넘쳐서 옮긴다. goto 가 16비트라 서로 이어진 것(24b37→24b42→24b59)을 **함께** 옮긴다(10-10)
    0x24B37,
    0x24B3E,
    0x24B42,
    0x24B44,
    0x24B59,
    0x1FED2,  # 「<아이템>을 가지고 있었다.」(원문 持っていた) — 17B 칸에 20B
)
# 제자리 칸이 모자라는 **꼬리 스트림**(앞 스트림이 06 으로 끊기고 물리적으로 이어지는 PINNED 자리)을
# 근처 묶음의 **남는 칸**으로 옮기고 제자리엔 goto(3B)만 둔다. 소비자(참조)가 없어 못 옮기던 자리라 들어오는 길은 그대로고,
# goto 가 16비트 상대라 ±32KB 안의 칸만 쓴다(ROM 꼬리는 너무 멀다). 값 = 본문 뒤 되돌아갈 자리(없으면 None).
#   0x76BE = 「回復した。」(HP·MP 회복 공용 꼬리, 끝 00 으로 끝난다)
#   0x324DD = 미니게임 「に<수치>」 — 뒤 04(0x324E1) + 0x324E2(「のダメージ!!」, PINNED)로 되돌아간다
TAIL_JUMP: dict[int, int | None] = {0x76BE: None, 0x324DD: 0x324E1}
_FAKE = 1 << 24  # 옮긴 본문의 자리를 allpos 에 임시로 꽂는 키 오프셋
_REACH = 0x7000

TAIL_SIZE = 0x80  # 빌드가 꼬리에 비워 두는 칸(build.py SYSMSG_TAIL)


def refs(d: bytes) -> dict[int, list[tuple[str, int]]]:
    """대상 → [(종류, 명령 자리)]. pc 상대는 명령+2 기준 16비트 변위, abs 는 명령+2 의 32비트."""
    out: dict[int, list[tuple[str, int]]] = {}
    for m in re.finditer(
        rb"([\x41\x43\x45\x47\x49\x4b\x4d]\xfa|\x48\x7a)(..)", d[:CODE_END], re.DOTALL
    ):
        t = m.start() + 2 + struct.unpack(">h", m.group(2))[0]
        out.setdefault(t, []).append(("pc", m.start()))
    for m in re.finditer(
        rb"([\x41\x43\x45\x47\x49\x4b\x4d]\xf9|\x48\x79)\x00([\x00-\x03])(..)",
        d[:CODE_END],
        re.DOTALL,
    ):
        t = int.from_bytes(m.group(0)[2:6], "big")
        out.setdefault(t, []).append(("abs", m.start()))
    for base, n in WORD_TABLES.items():
        for i in range(n):
            w = base + i * 2
            t = base + struct.unpack(">h", d[w : w + 2])[0]
            out.setdefault(t, []).append((f"tbl:{base:06x}", w))
    return out


def _textlike(st: scene.Stream) -> bool:
    """문안인가 — 코드·표가 스트림으로 읽힌 것을 거른다: 홀로 선 0x80(선두가 못 된다) · 깨진 2B 쌍 ·
    글자보다 많은 제어/영숫자.

    ⚠ **0x80 을 통째로 막으면 안 된다**(2026-09-06). `ム`(83 80)처럼 **뒤 바이트**로는 흔하다 —
    그 탓에 오델로 노인 대사 여럿이 조용히 빠져 있었다.
    """
    txt = b"".join(t.raw for t in st.tokens if t.kind == "text")
    sj = 0
    i = 0
    while i < len(txt):
        if scene.is_lead(txt[i]):
            try:
                txt[i : i + 2].decode("cp932")
            except UnicodeDecodeError:
                return False
            sj += 1
            i += 2
        else:
            if txt[i] == 0x80:
                return False
            i += 1
    if sj < 2:
        return False
    ascii_ = sum(1 for c in txt if 0x21 <= c < 0x7F and not 0x30 <= c <= 0x39)
    ctl = sum(1 for t in st.tokens if t.kind == "ctl")
    return ascii_ <= sj and ctl <= sj + 2


def _short_kana(st: scene.Stream) -> bool:
    """코드가 직접 가리키는 **짧은 연결 조각**(「<02>に<06>」 · 「<0e>は<07>」) — 전각이 두 자가 안 돼 `_textlike`
    가 거르지만 가나가 들었으면 문안이다. 🔴 셋이 번역 없이 남았다(2026-09-27): 전투 대미지 「<02>に」는
    가나 글리프가 표 0 에 없어 **빈 칸 하나(12px)로** 그려져 「슬러그C  7035의 대미지!!」처럼 보였다 —
    화면이 멀쩡해 보여 아무도 못 잡았다. 짧은 것만 받는다(가나 없는 자료 포인터는 여전히 걸러진다)."""
    if st.end - st.start >= 40:
        return False
    for t in st.tokens:
        if t.kind != "text":
            continue
        i, r = 0, t.raw
        while i < len(r) - 1:
            if scene.is_lead(r[i]):
                try:
                    ch = r[i : i + 2].decode("cp932")
                except UnicodeDecodeError:
                    return False
                if "぀" <= ch <= "ヿ":
                    return True
                i += 2
            else:
                i += 1
    return False


def streams(d: bytes) -> dict[int, dict]:
    """주소 → {stream, refs}. 참조된 자리에서 파싱되는 문안 스트림만."""
    import tables

    rs = refs(d)
    out = {}
    tbl = [(t[1], t[1] + (t[2] + 1) * t[4]) for t in tables.TABLES] + [
        (g[1], g[1] + 0x200) for g in tables.ZGROUPS
    ]
    for t in sorted(rs):
        if t >= CODE_END or t in EXCLUDE or any(a <= t < b for a, b in LZ + tbl):
            continue
        try:
            st = scene.parse_stream(d, t)
        except (ValueError, IndexError):
            continue
        if st.end - t > 400 or not (_textlike(st) or _short_kana(st)):
            continue
        out[t] = {"stream": st, "refs": rs[t]}
    for t in PINNED:
        if t not in out:
            out[t] = {"stream": scene.parse_stream(d, t), "refs": []}
    for base, n in WORD_TABLES.items():  # 표가 가리키는 자리는 _textlike 를 안 본다(위 주석)
        for i in range(n):
            w = base + i * 2
            t = base + struct.unpack(">h", d[w : w + 2])[0]
            if t not in out:
                out[t] = {"stream": scene.parse_stream(d, t), "refs": rs.get(t, [])}
    # 🔴 묶음 **안**을 가리키는 참조는 _textlike 를 못 넘어도 스트림이다(2026-09-26). 묶음을 다시 쓰면
    # 그 자리는 남의 바이트가 되는데, 안 세면 참조가 안 옮겨져 **엉뚱한 문안을 가리킨다** — 「<02>に<06>」
    # (주문을 남에게 걸 때 대상 이름, 0x7402)이 한 글자라 걸러져 「…을 외웠다」 한가운데를 가리키고 있었다.
    for cl in clusters(dict(sorted(out.items()))):
        lo, hi = span(out, cl)
        for t in rs:
            if lo <= t < hi and t not in out and t not in EXCLUDE:
                out[t] = {"stream": scene.parse_stream(d, t), "refs": rs[t]}
    # goto/call 대상도 스트림이다(참조 없이 오프셋으로만 이어진다)
    work = [
        tok.target
        for e in out.values()
        for tok in e["stream"].tokens
        if tok.ref in (scene.GOTO, scene.CALL)
    ]
    while work:
        t = work.pop()
        if t in out:
            continue
        st = scene.parse_stream(d, t)
        out[t] = {"stream": st, "refs": []}
        work += [tok.target for tok in st.tokens if tok.ref in (scene.GOTO, scene.CALL)]
    return dict(sorted(out.items()))


def clusters(strs: dict[int, dict]) -> list[list[int]]:
    """잇닿은 스트림 묶음(주소 목록). 하위 문자열은 앞 스트림 범위 안에 있다."""
    out: list[list[int]] = []
    end = -1
    prev_pinned = False
    for t, e in strs.items():
        if t in PINNED or prev_pinned:  # 고정 스트림은 자기 묶음 — 앞뒤와 안 섞인다
            out.append([t])
            end = e["stream"].end
            prev_pinned = t in PINNED
            continue
        if out and t <= end + 8:
            out[-1].append(t)
        else:
            out.append([t])
        end = max(end, e["stream"].end)
        prev_pinned = False
    return out


def span(strs: dict[int, dict], cl: list[int]) -> tuple[int, int]:
    return cl[0], max(strs[t]["stream"].end for t in cl)


def jp_key(st: scene.Stream) -> str:
    return hashlib.sha1(b"".join(t.raw for t in st.tokens)).hexdigest()[:10]


def render(st: scene.Stream) -> str:
    out = []
    for t in st.tokens:
        if t.kind == "text":
            out.append(t.raw.decode("cp932", "replace"))
        elif t.kind == "end":
            out.append(f"<{t.code:02x}>")
        elif t.code == 0x01:
            out.append("\n")
        elif t.ref:
            out.append(f"<{t.code:02x}:{t.target:06x}>")
        elif t.kind == "ctl":
            out.append(f"<{t.raw.hex()}>")
    return "".join(out)


def check(d: bytes) -> None:
    strs = streams(d)
    cls = clusters(strs)
    tot = sum(span(strs, c)[1] - span(strs, c)[0] for c in cls)
    nref = sum(len(e["refs"]) for e in strs.values())
    print(f"  시스템 메시지 스트림 {len(strs)} · 묶음 {len(cls)} · {tot:,}B · 참조 명령 {nref}")
    if (len(strs), len(cls)) != EXPECT:
        raise SystemExit(f"시스템 메시지 분모가 갈렸다 (기대 {EXPECT})")


def seed(d: bytes) -> None:
    strs = streams(d)
    cur = json.loads(MAP_JSON.read_text(encoding="utf-8")) if MAP_JSON.exists() else {}
    lines = []
    for cl in clusters(strs):
        lo, hi = span(strs, cl)
        lines.append(f"# 묶음 {lo:#x}~{hi:#x} ({hi - lo}B)")
        for t in cl:
            st = strs[t]["stream"]
            k = f"{t:06x}"
            cur.setdefault(k, {"jp": jp_key(st), "ours": ""})
            lines.append(f"{k}\t{st.end - t}B\t{len(strs[t]['refs'])}ref\t{render(st)!r}")
    MAP_JSON.parent.mkdir(exist_ok=True)
    MAP_JSON.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    out = common.OUT_DIR / "text" / "sysmsg.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"  {MAP_JSON}: {len(cur)} · 원문 {out}")


if __name__ == "__main__":
    d = common.rom()
    if "--seed" in sys.argv:
        seed(d)
    else:
        check(d)


# ── 재삽입 ─────────────────────────────────────────────────────────────────────

TAG = re.compile(
    r"<((?:[0-9a-f]{2})+)(?::([0-9a-f]{1,6}))?>"
)  # <fc32> 처럼 인자 딸린 제어도 통째로


def _tokens_from_ours(st: scene.Stream, ours: str, encode) -> list[scene.Token]:
    """정본 문안 → 토큰(조판 없음). 참조 태그는 원본 토큰(코드·대상)과 맞대고, 끝 토큰이 없으면 원본 것을 붙인다."""
    refs_left = [t for t in st.tokens if t.ref]
    end = next((t for t in st.tokens if t.kind == "end"), None)
    out: list[scene.Token] = []

    def text(seg: str):
        for i, line in enumerate(seg.split("\n")):
            if i:
                out.append(scene.Token(0, b"\x01", "ctl", 0x01))
            if line:
                out.append(scene.Token(0, encode(line), "text"))

    pos = 0
    for m in TAG.finditer(ours):
        text(ours[pos : m.start()])
        pos = m.end()
        raw = bytes.fromhex(m.group(1))
        code = raw[0]
        if m.group(2):
            tgt = int(m.group(2), 16)
            k = next((t for t in refs_left if t.code == code and t.target == tgt), None)
            if k is None:
                raise SystemExit(
                    f"sysmsg {st.start:#x}: 참조 <{code:02x}:{tgt:06x}> 가 원본에 없다"
                )
            refs_left.remove(k)
            out.append(k)
        elif code in scene.END:
            out.append(scene.Token(0, bytes([code]), "end", code))
        else:
            out.append(scene.Token(0, raw, "ctl", code))
    text(ours[pos:])
    if refs_left:
        raise SystemExit(
            f"sysmsg {st.start:#x}: 원본 참조 {[hex(t.target) for t in refs_left]} 가 정본에 없다"
        )
    if end is not None and not (out and out[-1].kind == "end"):
        out.append(scene.Token(0, end.raw, "end", end.code))
    return out


def _len(toks: list[scene.Token]) -> int:
    return sum(len(t.raw) for t in toks)


def _emit(toks: list[scene.Token], base: int, newpos: dict[int, int]) -> bytes:
    """토큰 → 바이트. goto/call 은 새 자리 기준 오프셋(첫 인자 자리 기준), 셀/코드는 원본 절대 자리 기준."""
    out = bytearray()
    for t in toks:
        if t.ref is None:
            out += t.raw
            continue
        raw = bytearray(t.raw)
        tgt = newpos.get(t.target, t.target) if t.ref in (scene.GOTO, scene.CALL) else t.target
        here = base + len(out)
        if t.code in (0xF5, 0xFB):
            raw[2:4] = struct.pack(">h", tgt - (here + 2))
        else:
            raw[1:3] = struct.pack(">h", tgt - (here + 1))
        out += raw
    return bytes(out)


def plan(
    d: bytes, textmap: dict, encode, tail_at: int | None = None
) -> list[tuple[str, int, bytes]]:
    """정본 → 쓰기 목록 [(라벨, 자리, 바이트)]. 번역이 하나라도 있는 묶음만 다시 쓴다."""
    strs = streams(d)
    rs = refs(d)
    writes: list[tuple[str, int, bytes]] = []
    over: list[str] = []
    plans = []
    allpos: dict[int, int] = {}  # 🔴 자리는 **전 묶음을 다 재 놓고** 쓴다 — goto 가 묶음을 넘는다
    tcur = tail_at  # 꼬리로 옮기는 스트림의 다음 자리
    moved: list[tuple[int, int, list]] = []  # (스트림, 새 자리, 토큰)
    flowinfo: dict[
        int, tuple[int, bool]
    ] = {}  # 스트림 → (새 크기, 다음으로 흐르나) — 흐름 게이트용
    jumps: dict[int, list] = {}  # TAIL_JUMP — 제자리에 안 들어가 근처 칸으로 갈 본문
    for cl in clusters(strs):
        lo, hi = span(strs, cl)
        toks = {}
        touched = False
        for t in cl:
            ent = textmap.get(f"{t:06x}", {})
            st = strs[t]["stream"]
            if ent.get("ours"):
                if ent["jp"] != jp_key(st):
                    raise SystemExit(f"sysmsg {t:#x}: 원문 해시가 갈렸다")
                toks[t] = _tokens_from_ours(st, ent["ours"], encode)
                touched = True
            else:
                toks[t] = st.tokens
        if not touched:
            for t in cl:
                allpos.setdefault(t, t)  # 안 건드린 묶음은 제자리
            continue

        # 배치: 주소 순. 앞 스트림의 새 바이트 접미와 같으면(꼬리 공유) 그 안을 가리킨다
        def is_suffix(child, parent) -> bool:
            """자식 토큰열이 부모의 꼬리인가 — 첫 토큰은 텍스트의 **꼬리 일부**여도 된다(「運良く」의 「く」).
            참조는 (코드, 대상)만 본다(오프셋 값은 자리마다 다르다)."""
            if len(child) > len(parent) or not child:
                return False
            tail = parent[len(parent) - len(child) :]
            for i, (c, q) in enumerate(zip(child, tail, strict=True)):
                if c.kind != q.kind or c.code != q.code:
                    return False
                if c.ref:
                    if c.target != q.target:
                        return False
                elif c.raw != q.raw and not (i == 0 and c.kind == "text" and q.raw.endswith(c.raw)):
                    return False
            return True

        for t in cl:
            if (
                t in TAIL_JUMP
                and toks[t] is not strs[t]["stream"].tokens
                and _len(toks[t]) > hi - lo
            ):
                body = list(toks[t])
                if TAIL_JUMP[t] is not None:
                    body.append(
                        scene.Token(0, b"\x0f\x00\x00", "ctl", 0x0F, scene.GOTO, TAIL_JUMP[t])
                    )
                jumps[t] = body
                toks[t] = [scene.Token(0, b"\x0f\x00\x00", "ctl", 0x0F, scene.GOTO, _FAKE + t)]
        size = {t: _len(toks[t]) for t in cl}

        def _flows(t, toks=toks):
            tk = toks[t]
            return bool(tk) and tk[-1].kind == "end" and tk[-1].code in (0x06, 0x0A, 0x0D)

        # 06 으로 끝난 스트림 **바로 뒤**에 오는 스트림은 꼬리를 남과 공유하면 안 된다(공유하면 06 뒤가 비어 문장이 끊긴다 — 미니게임
        # 「뭐야, 필요 없다고.」가 같은 문안의 뒤쪽 것에 얹혀 쪽 넘김 뒤에 안 나왔다)
        flowers = {  # 06 으로 끝나고 원래 뒤에 다른 스트림이 이어지는 것 — 남의 꼬리에 얹히면 06 뒤가 달라진다
            t
            for t in cl
            if toks[t]
            and toks[t][-1].kind == "end"
            and toks[t][-1].code == 0x06
            and strs[t]["stream"].end in strs
        }
        flow_targets = {
            strs[u]["stream"].end
            for u in cl
            if toks[u] and toks[u][-1].kind == "end" and toks[u][-1].code == 0x06
        }
        newpos: dict[int, int] = {}
        cur = lo
        order = []
        for t in cl:
            if t in RELOCATE and tail_at is not None and toks[t] is not strs[t]["stream"].tokens:
                if any(k != "abs" for k, _ in strs[t]["refs"]):
                    raise SystemExit(f"sysmsg {t:#x}: 참조가 절대 주소가 아니라 못 옮긴다")
                newpos[t] = tcur
                moved.append((t, tcur, toks[t]))
                tcur += size[t]
                continue
            placed = False
            for u in order:
                if (
                    t not in flow_targets
                    and (
                        t not in flowers or strs[u]["stream"].end == strs[t]["stream"].end
                    )  # 흐르는 스트림은 원래 호스트에만 얹는다
                    and size[t] < size[u]
                    and is_suffix(toks[t], toks[u])
                ):
                    newpos[t] = newpos[u] + size[u] - size[t]
                    placed = True
                    break
            if not placed:
                newpos[t] = cur
                cur += size[t]
                order.append(t)
        # 🔴 `06`·`0A`·`0D` 로 끝나는 스트림은 **물리적으로 다음 스트림으로 흐른다**(수치를 게임이 찍은 뒤 꼬리말이 이어진다 — 「최대 ＨＰ가 ⟨수⟩
        # 포인트 올랐다」). 묶음이 왼쪽부터 채워 끝에 0 이 남으면 06 과 다음 스트림 사이에 00 이 끼어 **문장이 거기서 끊긴다**(10-10
        # 마스터 「최대 HP가 18 에서 메시지가 끊겼다」). 다음 스트림이 묶음 끝에 맞닿아 있으면 흐르는 사슬을 오른쪽 끝에 붙인다.
        if order and hi in strs and strs[order[-1]]["stream"].end == hi and _flows(order[-1]):
            chain = [order[-1]]
            j = len(order) - 2
            while j >= 0 and strs[order[j]]["stream"].end == order[j + 1] and _flows(order[j]):
                chain.insert(0, order[j])
                j -= 1
            shift = hi - (newpos[chain[-1]] + size[chain[-1]])
            if shift > 0 and all(t not in RELOCATE for t in chain):
                for t in chain:
                    newpos[t] += shift
        if cur > hi:
            over.append(
                f"{lo:#x}~{hi:#x}: {cur - lo}B > {hi - lo}B  ({', '.join(f'{t:06x}' for t in cl)})"
            )
            continue
        stray = [t for t in rs if lo <= t < hi and t not in newpos and t not in EXCLUDE]
        if stray:  # 다시 쓰는 묶음 안을 가리키는데 안 옮겨지는 참조 — 위 streams() 의 🔴
            raise SystemExit(
                f"sysmsg {lo:#x}: 안 옮겨지는 참조 {', '.join(f'{t:#x}' for t in stray)}"
            )
        for t in cl:
            flowinfo[t] = (
                size[t],
                bool(toks[t]) and toks[t][-1].kind == "end" and toks[t][-1].code == 0x06,
            )
        plans.append((lo, hi, cl, toks, order, newpos, cur, []))
        allpos.update(newpos)
    if over:
        raise SystemExit(
            "sysmsg 묶음이 넘친다 — textmap/sysmsg.json 을 줄인다:\n    " + "\n    ".join(over)
        )
    # 🔴 흐름 게이트 — 06·0A·0D 로 끝나는 스트림 뒤엔 원래 이어지던 스트림이 **바로** 와야 한다(사이에 00 이 끼면 문장이 끊긴다)
    broken = [
        f"{t:#x}→{strs[t]['stream'].end:#x}"
        for t, (sz, fl) in flowinfo.items()
        if fl
        and t in allpos
        and strs[t]["stream"].end in allpos
        and t not in RELOCATE
        and strs[t]["stream"].end not in RELOCATE
        and allpos[t] + sz != allpos[strs[t]["stream"].end]
    ]
    if broken:
        raise SystemExit(
            "sysmsg 흐름이 끊겼다(뒤 스트림이 바로 이어지지 않는다): " + ", ".join(broken)
        )
    for (
        t,
        jb,
    ) in (
        jumps.items()
    ):  # 근처 묶음의 남는 칸에 앉힌다(끝 00 하나는 묶음 마지막 스트림 것이라 남긴다)
        need = _len(jb)
        for pl in sorted(plans, key=lambda q: abs(q[0] - t)):
            lo, hi, cur, extras = pl[0], pl[1], pl[6], pl[7]
            used = sum(_len(b) for _, b in extras)
            at = cur + used
            if t in pl[2] or abs(at - t) > _REACH or at + need > hi:
                continue
            extras.append((at, jb))
            allpos[_FAKE + t] = at
            break
        else:
            raise SystemExit(f"sysmsg {t:#x}: 근처에 옮길 남는 칸이 없다({need}B)")
    for lo, hi, cl, toks, order, newpos, _cur, extras in plans:
        body = bytearray(b"\x00" * (hi - lo))
        for u in order:
            b = _emit(toks[u], newpos[u], allpos)
            body[newpos[u] - lo : newpos[u] - lo + len(b)] = b
        for at, jb in extras:
            b = _emit(jb, at, allpos)
            body[at - lo : at - lo + len(b)] = b
        writes.append((f"sysmsg:{lo:06x}", lo, bytes(body)))
        for t in cl:
            for kind, ins in strs[t]["refs"]:
                if kind.startswith("tbl:"):
                    base = int(kind[4:], 16)
                    disp = newpos[t] - base
                    if not -0x8000 <= disp < 0x8000:
                        raise SystemExit(f"sysmsg {t:#x}: 표 변위 범위 초과 @{ins:#x}")
                    writes.append((f"sysmsg-tbl:{ins:06x}", ins, struct.pack(">h", disp)))
                elif kind == "pc":
                    disp = newpos[t] - (ins + 2)
                    if not -0x8000 <= disp < 0x8000:
                        raise SystemExit(f"sysmsg {t:#x}: pc 변위 범위 초과 @{ins:#x}")
                    writes.append((f"sysmsg-ref:{ins:06x}", ins + 2, struct.pack(">h", disp)))
                else:
                    writes.append((f"sysmsg-ref:{ins:06x}", ins + 2, struct.pack(">I", newpos[t])))
    if moved:
        if tcur - tail_at > TAIL_SIZE:
            raise SystemExit(f"sysmsg 꼬리 칸이 모자란다: {tcur - tail_at}B > {TAIL_SIZE}B")
        for t, pos, tk in moved:
            writes.append((f"sysmsg-moved:{t:06x}", pos, _emit(tk, pos, allpos)))
    return writes


def allowed_tail(at: int) -> dict[str, tuple[int, int]]:
    """꼬리로 옮긴 스트림 자리 — 스트림마다 라벨 하나(구간은 꼬리 칸 전체)."""
    return {f"sysmsg-moved:{t:06x}": (at, at + TAIL_SIZE) for t in RELOCATE}


def allowed(d: bytes) -> dict[str, tuple[int, int]]:
    """빌드의 허용 구간 — 묶음 범위와 참조 명령의 피연산자."""
    strs = streams(d)
    out = {}
    for cl in clusters(strs):
        lo, hi = span(strs, cl)
        out[f"sysmsg:{lo:06x}"] = (lo, hi)
        for t in cl:
            for kind, ins in strs[t]["refs"]:
                if kind.startswith("tbl:"):
                    out[f"sysmsg-tbl:{ins:06x}"] = (ins, ins + 2)
                else:
                    out[f"sysmsg-ref:{ins:06x}"] = (ins + 2, ins + (4 if kind == "pc" else 6))
    return out
