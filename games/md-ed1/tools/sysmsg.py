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
EXPECT = (106, 40)  # 스트림 · 묶음 (2026-09-05 실측 — 0A 를 끝으로 잡은 뒤)
EXCLUDE = {0x1ED0C}  # '付近入口H鄲 $Kr' — cp932 로 우연히 풀리는 코드. 눈으로 확인해 뺀다


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
    return out


def _textlike(st: scene.Stream) -> bool:
    """문안인가 — 코드·표가 스트림으로 읽힌 것을 거른다: 0x80 선두(진짜 SJIS 엔 없다) · 깨진 2B 쌍 ·
    글자보다 많은 제어/영숫자."""
    txt = b"".join(t.raw for t in st.tokens if t.kind == "text")
    if b"\x80" in txt:
        return False
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
            i += 1
    if sj < 2:
        return False
    ascii_ = sum(1 for c in txt if 0x21 <= c < 0x7F and not 0x30 <= c <= 0x39)
    ctl = sum(1 for t in st.tokens if t.kind == "ctl")
    return ascii_ <= sj and ctl <= sj + 2


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
        if st.end - t > 400 or not _textlike(st):
            continue
        out[t] = {"stream": st, "refs": rs[t]}
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
    for t, e in strs.items():
        if out and t <= end + 8:
            out[-1].append(t)
        else:
            out.append([t])
        end = max(end, e["stream"].end)
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


def plan(d: bytes, textmap: dict, encode) -> list[tuple[str, int, bytes]]:
    """정본 → 쓰기 목록 [(라벨, 자리, 바이트)]. 번역이 하나라도 있는 묶음만 다시 쓴다."""
    strs = streams(d)
    writes: list[tuple[str, int, bytes]] = []
    over: list[str] = []
    over: list[str] = []
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

        size = {t: len(_emit(toks[t], t, {})) for t in cl}
        newpos: dict[int, int] = {}
        cur = lo
        order = []
        for t in cl:
            placed = False
            for u in order:
                if size[t] < size[u] and is_suffix(toks[t], toks[u]):
                    newpos[t] = newpos[u] + size[u] - size[t]
                    placed = True
                    break
            if not placed:
                newpos[t] = cur
                cur += size[t]
                order.append(t)
        if cur > hi:
            over.append(
                f"{lo:#x}~{hi:#x}: {cur - lo}B > {hi - lo}B  ({', '.join(f'{t:06x}' for t in cl)})"
            )
            continue
        body = bytearray(b"\x00" * (hi - lo))
        for u in order:
            b = _emit(toks[u], newpos[u], newpos)
            body[newpos[u] - lo : newpos[u] - lo + len(b)] = b
        writes.append((f"sysmsg:{lo:06x}", lo, bytes(body)))
        for t in cl:
            for kind, ins in strs[t]["refs"]:
                if kind == "pc":
                    disp = newpos[t] - (ins + 2)
                    if not -0x8000 <= disp < 0x8000:
                        raise SystemExit(f"sysmsg {t:#x}: pc 변위 범위 초과 @{ins:#x}")
                    writes.append((f"sysmsg-ref:{ins:06x}", ins + 2, struct.pack(">h", disp)))
                else:
                    writes.append((f"sysmsg-ref:{ins:06x}", ins + 2, struct.pack(">I", newpos[t])))
    if over:
        raise SystemExit(
            "sysmsg 묶음이 넘친다 — textmap/sysmsg.json 을 줄인다:\n    " + "\n    ".join(over)
        )
    if over:
        raise SystemExit(
            "sysmsg 묶음이 넘친다 — textmap/sysmsg.json 을 줄인다:\n    " + "\n    ".join(over)
        )
    return writes


def allowed(d: bytes) -> dict[str, tuple[int, int]]:
    """빌드의 허용 구간 — 묶음 범위와 참조 명령의 피연산자."""
    strs = streams(d)
    out = {}
    for cl in clusters(strs):
        lo, hi = span(strs, cl)
        out[f"sysmsg:{lo:06x}"] = (lo, hi)
        for t in cl:
            for kind, ins in strs[t]["refs"]:
                out[f"sysmsg-ref:{ins:06x}"] = (ins + 2, ins + (4 if kind == "pc" else 6))
    return out
