"""코드 영역 문안 조사 — md-ed2 **census(분모 파악) 단계**. 재삽입은 아직 없다.

    python3 tools/sysmsg.py            # 분모 + 아카이브 밖 SJIS 런 중 참조로 안 잡힌 것(남은 일본어)
    python3 tools/sysmsg.py -v         # 영역별 표

ED1 `sysmsg.py` 와 같은 방법 — 코드의 `lea/pea d(pc)` · `lea/pea abs.l` 참조가 가리키는 자리에서
`scene.parse_stream` 이 문안 스트림으로 파싱되면 문안이다. 하위 문자열·goto/call 대상은 따라간다.

🔴 **ED1 과 다른 점: 코드 영역이 훨씬 크고 대사가 그 안에 있다.** ED2 는 아카이브 밖(0x88F4E 앞)에
SJIS 가 ~2만 자 있고, 0x32000~0x3BFFF(≈40KB)는 **화자 태그(1E 이름 04)가 달린 이벤트 대사**다
(NPC 대화 — 단순 시스템 메시지가 아니다). 그래서 이 영역은 「시스템 메시지」가 아니라 **대본의 둘째 몸통**으로
다뤄야 한다(번역 라운드 몫, status.md).
"""

import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import scene

CODE_END = 0x88F4E  # 첫 LZ 아카이브(gfx_a) 앞까지가 코드·자료 영역
MAX_STREAM = 6000  # ED1 은 400 — ED2 의 이벤트 대사는 05(페이지)로 이어진 긴 스트림이다(0x37345 등)
import hashlib
import json

MAP_JSON = common.GAME_DIR / "textmap" / "sysmsg.json"
EXCLUDE: set[int] = set()
# 워드 오프셋 표: 표 자리 → 항목 수. 코드가 `lea T.l,a3` + `move.w (a3,d0.w),d0` + `lea (a3,d0.w),a1` 로 고른다(주문·아이템 효과 메시지 —
# 참조(lea)가 없어 처음 조사에서 통째로 빠져 있었다). ED1 0x73BC(33) → ED2 0x8150(33, 첫 셋이 같은 항목인 꼴까지 같다).
WORD_TABLES = {0x8150: 33}
# ED1 의 PINNED(06 뒤 꼬리말 제자리 고정) · RELOCATE(꼬리로 옮김) · TAIL_JUMP — ED1 주소라 ED2 에선 **빈 채로 시작**한다.
# 흐르는 스트림이 필요한 자리는 문안을 채우며 흐름 게이트(plan)가 잡는다.
# ED2 대응은 **원문 내용 키**(참조 오프셋을 뺀 토큰열)가 ED1 과 유일하게 맞는 것만 옮겼다(`reuse_ed1.py` 로 대응을 뽑았다 — 2026-10-12).
# 안 옮겨진 ED1 PINNED(0x75ee·0x760f·0x762a… 「06 뒤 꼬리말」)는 ED2 에 같은 원문 스트림이 없거나 갈려 있다 — 해당 칸이 문안으로 들어올 때
# 흐름 게이트가 잡는다.
PINNED: set[int] = {
    0x29D2A,  # ED1 0x324e2 — 「のダメージ !!」 꼬리
}
RELOCATE: tuple[int, ...] = (
    0x29D38,  # ED1 0x24a7a — 도망(복수) · 꼬리로 옮긴다(참조가 절대 주소인 것만 옮길 수 있다)
    0x29D3C,  # ED1 0x24a7e — 도망(단수)
    0x29D4C,  # 「의 공격」·회심·통한·「…에는 효과가 없었다」·「아무 일도 없다」 — 절대 참조라 꼬리로 옮겨 근처 칸을 비운다(TAIL_JUMP 가 쓸 자리)
    0x29D54,
    0x29D60,
    0x29E0E,
    0x29DD9,
    0x2468C,  # ED1 0x1fed2 — 「<0e>을 가지고 있었다.」(원문 17B 칸에 20B)
    0x29DF5,  # ED1 0x24b37 — 「運悪」 묶음(goto 가 16비트라 이어진 것을 함께)
    0x29DFC,  # ED1 0x24b3e
    0x29E00,  # ED1 0x24b42
    0x29E02,  # ED1 0x24b44
    0x29E17,  # ED1 0x24b59
)
# 제자리 묶음에 안 들어가는 스트림 — 제자리엔 goto(3B)만 두고 본문은 **근처(±30KB) 다른 묶음의 남는 칸**(꼬리 이전·고정으로 비워진 자리)에
# 앉힌다. 참조가 pc 상대(16비트)라 먼 꼬리로 못 가는 자리를 위한 길이다(ED1 TAIL_JUMP 와 같은 기전). 값 = 본문 뒤 되돌아갈 자리(없으면 None).
TAIL_JUMP: dict[int, int | None] = {
    0x27CB0: None,
    0x27CC3: None,
    0x31026: None,
    0x249CE: None,  # 「<02>은(는) 정신이 들었다.」 정본 문안이 칸(16B)보다 길다 — 0A 로 끝나 되돌림 없음
    0x8471: None,  # 「회복되었다.」 정본 문안이 칸(13B)보다 1B 길다 — 00 으로 끝
    # 06·0A 로 끝나 **물리적으로 다음 스트림으로 흐르는** 것은 본문 뒤에 goto 를 달아 원래 끝으로 되돌린다(ED1 0x324DD 와 같다)
    0x29D26: 0x29D2A,  # 「<02>에게<06>」 +2B — 뒤 「의 피해!!」(고정)로 흐른다
    0x29E22: 0x29E34,
    0x29E34: 0x29E4E,
}
# 본문을 **줄바꿈(`01`) 앞뒤로 둘로 쪼개** 앞은 제자리 · 뒤는 근처 칸에 앉히고 goto 로 잇는다(마스터 10-12 「b 로 해보자」) — 화면에는 줄바꿈 자리라 안 보인다.
TAIL_SPLIT: set[int] = {0x31026}
_FAKE = 1 << 24
_REACH = 0x7800  # goto 가 16비트 상대(±32KB) — 여유를 두고 30KB
TAIL_SIZE = 0x100  # 빌드가 꼬리에 비워 두는 칸(build.SYSMSG_TAIL)
SJIS_RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]){3,}")


def refs(d: bytes) -> dict[int, list[tuple[str, int]]]:
    """대상 → [(종류, 명령 자리)]. pc 상대는 명령+2 기준 16비트 변위, abs 는 명령+2 의 32비트."""
    out: dict[int, list[tuple[str, int]]] = {}
    for m in re.finditer(
        rb"([\x41\x43\x45\x47\x49\x4b\x4d]\xfa|\x48\x7a)(..)", d[:CODE_END], re.DOTALL
    ):
        t = m.start() + 2 + struct.unpack(">h", m.group(2))[0]
        out.setdefault(t, []).append(("pc", m.start()))
    for m in re.finditer(
        rb"([\x41\x43\x45\x47\x49\x4b\x4d]\xf9|\x48\x79)\x00([\x00-\x0f])(..)",
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
    """문안인가 — 코드·표가 스트림으로 읽힌 것을 거른다(ED1 `_textlike` 와 같은 기준)."""
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


def table_ranges() -> list[tuple[int, int]]:
    """고정 표·00 묶음·이름 칸(tables.py) + 폭이 제각각인 지명 표 — 문안 스트림이 아니라 **표**로 다시 쓰는 자리."""
    import tables

    out = [(t[1], t[1] + (t[2] + 1) * t[4]) for t in tables.TABLES]
    out += [(g[1], g[1] + 0x200) for g in tables.ZGROUPS]
    out += [(t[1], t[1] + t[2] * t[3]) for t in tables.SLOTS]
    out.append((0x3B256, 0x3B5A8))  # 지명 표(개수·오프셋 워드 + 65 레코드, `places.py`)
    return out


def streams(d: bytes) -> dict[int, dict]:
    rs = refs(d)
    out = {}
    tbl = table_ranges()
    for t in sorted(rs):
        if t >= CODE_END or any(
            a <= t < b for a, b in tbl
        ):  # 표(tables.py)가 맡는 자리는 문안 스트림이 아니다
            continue
        try:
            st = scene.parse_stream(d, t)
        except (ValueError, IndexError):
            continue
        via_table = any(
            k.startswith("tbl:") for k, _ in rs[t]
        )  # 표에 실렸다는 것 자체가 문안이라는 증거(ED1)
        if st.end - t > MAX_STREAM or not (via_table or _textlike(st) or _short_kana(st)):
            continue
        out[t] = {"stream": st, "refs": rs[t]}
    # 🔴 묶음 **안**을 가리키는 참조는 _textlike 를 못 넘어도 스트림이다(ED1 2026-09-26). 묶음을 다시 쓰면 그 자리는 남의 바이트가 되는데,
    # 안 세면 참조가 안 옮겨져 **엉뚱한 문안을 가리킨다**.
    for cl in clusters(dict(sorted(out.items()))):
        lo, hi = span(out, cl)
        for t in rs:
            if lo <= t < hi and t not in out and t not in EXCLUDE:
                try:
                    out[t] = {"stream": scene.parse_stream(d, t), "refs": rs[t]}
                except (ValueError, IndexError):
                    pass
    work = [
        tok.target
        for e in out.values()
        for tok in e["stream"].tokens
        if tok.ref in (scene.GOTO, scene.CALL)
    ]
    while work:
        t = work.pop()
        if t in out or not 0 <= t < CODE_END:
            continue
        try:
            st = scene.parse_stream(d, t)
        except (ValueError, IndexError):
            continue
        out[t] = {"stream": st, "refs": []}
        work += [tok.target for tok in st.tokens if tok.ref in (scene.GOTO, scene.CALL)]
    # 🔴 **흐름 꼬리**: `06`·`0A`·`0D` 로 끝나는 스트림은 **물리적으로 다음 스트림으로 흐른다**(수치를 게임이 찍은 뒤 꼬리말이 이어진다 —
    # 「최대 ＨＰ가 ⟨수⟩ ポイント あがった」). 꼬리엔 참조가 없어 위 참조 탐색이 못 찾는다. 다음 자리가 문안으로 파싱되면 스트림으로
    # 세고 **제자리 고정(PINNED)** 으로 둔다(ED1 은 이걸 손으로 열아홉 자리 적었다 — ED2 는 규칙으로 잡는다).
    again = True
    while again:
        again = False
        for e in list(out.values()):
            tk = e["stream"].tokens
            if not tk or tk[-1].kind != "end" or tk[-1].code not in (0x06, 0x0A, 0x0D):
                continue
            n = e["stream"].end
            if n in out or not 0 <= n < CODE_END or any(a <= n < b for a, b in table_ranges()):
                continue
            try:
                st = scene.parse_stream(d, n)
            except (ValueError, IndexError):
                continue
            if st.end - n > 400 or not any(
                t2.kind == "text" and len(t2.raw) >= 2 for t2 in st.tokens
            ):
                continue
            if not (_textlike(st) or _short_kana(st)):
                continue
            out[n] = {"stream": st, "refs": []}
            PINNED.add(n)
            again = True
    return dict(sorted(out.items()))


def leftover(d: bytes, strs: dict[int, dict]) -> list[tuple[int, int]]:
    """코드 영역의 SJIS 런 중 스트림 범위 밖(참조로 못 잡은 것) — (자리, 글자 수)."""
    cov = bytearray(CODE_END)
    for t, e in strs.items():
        cov[t : e["stream"].end] = b"\x01" * (e["stream"].end - t)
    out = []
    for m in SJIS_RUN.finditer(d[:CODE_END]):
        if not cov[m.start()]:
            out.append((m.start(), len(m.group()) // 2))
    return out


# 첫 조사(2026-10-12) 실측 — 파서·정규식을 고치면 바뀐다. 번역 때 분모로 쓴다.
EXPECT = (215, 784)  # 스트림 · 스트림 밖 SJIS 런


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


def check(d: bytes, verbose: bool = False) -> None:
    strs = streams(d)
    cls = clusters(strs)
    tot = sum(span(strs, c)[1] - span(strs, c)[0] for c in cls)
    total_chars = sum(len(m.group()) // 2 for m in SJIS_RUN.finditer(d[:CODE_END]))
    left = leftover(d, strs)
    nref = sum(len(e["refs"]) for e in strs.values())
    spk = sum(1 for e in strs.values() for t in e["stream"].tokens if t.code == 0x1E)
    print(
        f"  코드 영역 문안 스트림 {len(strs)} · 묶음 {len(cls)} · {tot:,}B (참조 명령 {nref} · 화자 태그 스트림 {spk}) · "
        f"SJIS {total_chars:,}자 중 스트림 밖 {sum(n for _, n in left):,}자({len(left)}런)"
    )
    if verbose:
        import collections

        by = collections.Counter()
        for a, n in left:
            by[a >> 12] += n
        print(
            "  남은 일본어 영역별(4KB):", {hex(k << 12): v for k, v in sorted(by.items()) if v > 30}
        )
    if EXPECT is not None and (len(strs), len(left)) != EXPECT:
        raise SystemExit(f"코드 영역 분모가 갈렸다 (기대 {EXPECT})")


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
        check(d, "-v" in sys.argv)


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

        # 묶음 **합계**가 칸을 넘으면 TAIL_JUMP 후보 중 큰 것부터 근처 칸으로 보낸다(ED2: 스트림 하나는 맞아도 둘이 합쳐 넘친다)
        order_j = sorted(
            (t for t in cl if t in TAIL_JUMP and toks[t] is not strs[t]["stream"].tokens),
            key=lambda t: -_len(toks[t]),
        )
        total = sum(_len(toks[t]) for t in cl)
        for t in order_j:
            if total <= hi - lo:
                break
            goto = scene.Token(0, b"\x0f\x00\x00", "ctl", 0x0F, scene.GOTO, _FAKE + t)
            head: list[scene.Token] = []
            rest = list(toks[t])
            if t in TAIL_SPLIT:
                i = next(
                    (k for k, tk in enumerate(rest) if tk.kind != "text" and tk.code == 0x01), None
                )
                if i is not None:
                    head, rest = rest[:i], rest[i:]
            total -= _len(rest) - 3
            body = list(rest)
            if TAIL_JUMP[t] is not None:
                body.append(scene.Token(0, b"\x0f\x00\x00", "ctl", 0x0F, scene.GOTO, TAIL_JUMP[t]))
            jumps[t] = body
            toks[t] = [*head, goto]
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
