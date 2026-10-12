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
import archives
import common
import scene

CODE_END = 0x88F4E  # 첫 LZ 아카이브(gfx_a) 앞까지가 코드·자료 영역
MAX_STREAM = 6000  # ED1 은 400 — ED2 의 이벤트 대사는 05(페이지)로 이어진 긴 스트림이다(0x37345 등)
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


def streams(d: bytes) -> dict[int, dict]:
    rs = refs(d)
    out = {}
    for t in sorted(rs):
        if t >= CODE_END:
            continue
        try:
            st = scene.parse_stream(d, t)
        except (ValueError, IndexError):
            continue
        if st.end - t > MAX_STREAM or not _textlike(st):
            continue
        out[t] = {"stream": st, "refs": rs[t]}
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
EXPECT = (178, 808)  # 스트림 · 스트림 밖 SJIS 런


def check(d: bytes, verbose: bool = False) -> None:
    strs = streams(d)
    total_chars = sum(len(m.group()) // 2 for m in SJIS_RUN.finditer(d[:CODE_END]))
    left = leftover(d, strs)
    lchars = sum(n for _, n in left)
    nref = sum(len(e["refs"]) for e in strs.values())
    spk = sum(1 for e in strs.values() for t in e["stream"].tokens if t.code == 0x1E)
    print(
        f"  코드 영역 문안 스트림 {len(strs)} (참조 명령 {nref} · 화자 태그 스트림 {spk}) · "
        f"SJIS {total_chars:,}자 중 스트림 밖 {lchars:,}자({len(left)}런)"
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


if __name__ == "__main__":
    check(common.rom(), "-v" in sys.argv)
    _ = archives  # 아카이브 범위는 CODE_END 로 갈랐다
