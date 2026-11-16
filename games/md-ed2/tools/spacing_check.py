"""띄어쓰기·개행 대조 — 원판 스트림과 구운 롬의 같은 스트림에서 셋을 맞댄다(마스터 10-30 「보물상자처럼 띄어쓰기 개행 제대로 안 된 게」).

    python3 tools/spacing_check.py [롬.bin] [--list]      # 빌드 게이트(check.sh 5e3) — 어긋남이 있으면 실패

배경(pce-ed1 10-30): 변수 삽입 앞 공백이 빠지고 · 쪽/줄 나눔이 빠지고 · 메시지 끝 개행이 빠진 결함 셋. 정본 텍스트가 아니라 **롬 바이트**를 원판과 맞댄다.
 1. 변수 앞 공백 — 원판이 글 덩이 끝 공백 뒤에 변수(09 이름 · 0E 아이템 · 02 · 15 코드 호출 · 10 호출)를 불렀는데 롬은 글자에 붙여 불렀다.
    (조사 훅 EB/EC 는 뒤에 붙는 게 맞으므로 보지 않는다 — 어절 경계만.)
 2. 문장 이음 — 롬 스트림 안에서 문장 끝 부호(. ! ? …) 바로 뒤에 줄·쪽·키 대기 없이 한글이 이어진다.
 3. 끝 개행 — 마지막 글 덩이 뒤의 줄·쪽 코드(01 · 03 · 05)가 원판과 다르다. 허용(창이 닫히거나 메뉴로 넘어가 화면에 안 보이는 꼴, 10-30 실측·원판 대조):
    `01 E07` → `E07`(상점 메뉴 앞) · `01 E00` → `E00`(창 닫힘) · `01 15 E00` → `15 E00`(코드 호출 뒤 닫힘).
대조 단위는 color_check 와 같다(씬 모듈 356 의 짝지은 스트림 + 전투 블록 99).
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import color_check as CC
import common
import scene
import scene_sweep
import struct_check as SC

VAR = {0x09, 0x0E, 0x02, 0x15, 0x10}
BREAK = {0x01, 0x03, 0x05}
END_PUNCT = ".!?…"
TAIL_OK = {
    (("01", "E07"), ("E07",)),
    (("01", "E00"), ("E00",)),
    (("01", "15", "E00"), ("15", "E00")),
    (("0f",), ("01", "0f")),  # 이음 사슬 — 다음 쪽으로 넘어가기 전 줄 바꿈(재조판이 넣는다)
    (("0f",), ("E0a",)),  # 원판은 goto 로 이어지고 롬은 그 꼬리를 스텁 없이 품은 꼴
}


# 쪽·키 대기(03·05) 개수가 원판보다 준 곳 — 줄면 상점·여관처럼 창 닫기 대기에 안 가려지는 자리에서 키를 덜 받아 진행이 어긋난다(pce-ed1 투어 실측, 11-07).
# struct_check 는 배치 코드(01·03·04·05·1E)를 열에서 빼므로 이 대조가 유일하다. 사유가 확인된 곳만 허용한다.
WAIT_OK = {
    "085-3:-b7e": "원문 창 32 → 한글 31(창적음 1) — 머리 두 창이 한 창으로 합쳐진 꼴, 원인 확인 대기",
}


def var_slots(tokens):
    """→ [(코드, 앞이 공백·줄 경계였나)] — 글 덩이 사이에 끼어 글자를 찍는 변수만(뒤에 글이 이어지거나 조사 훅이 붙는 꼴, 그냥 코드 호출은 뺀다)."""
    toks = [t for t in tokens if t.kind != "eof"]
    out, prev = [], "start"
    for i, t in enumerate(toks):
        if t.kind == "text":
            raw = bytes(t.raw)
            prev = "space" if raw.endswith((b" ", b"\x81\x40")) else "text"
        elif t.kind == "ctl":
            if t.code in VAR:
                nxt = toks[i + 1] if i + 1 < len(toks) else None
                if nxt is not None and (
                    nxt.kind == "text" or (nxt.kind == "ctl" and nxt.code in (0xEB, 0xEC))
                ):
                    out.append((t.code, prev == "space"))
            if t.code in BREAK:
                prev = "space"  # 줄·쪽 경계도 어절 경계다
            elif t.code not in (0xEB, 0xEC):
                prev = "ctl"
    return out


def tail(tokens):
    """마지막 글 덩이 뒤의 코드 열 — 줄·쪽(01·03·05) · 끝 코드(E..) · 그 밖의 코드(16진 두 자리)."""
    toks = [t for t in tokens if t.kind != "eof"]
    i = len(toks)
    while i and toks[i - 1].kind != "text":
        i -= 1
    out = []
    for t in toks[i:]:
        if t.kind == "ctl":
            out.append(f"{t.code:02x}")
        elif t.kind == "end":
            out.append(f"E{t.code:02x}")
    return tuple(out)


def joined(tokens, decode):
    """줄·쪽·키 대기 없이 문장 끝 부호 뒤에 한글이 바로 이어지는 자리 → [앞뒤 글]."""
    out, last = [], ""
    for t in tokens:
        if t.kind == "text":
            s = decode(bytes(t.raw))
            if last in END_PUNCT and last and s and "가" <= s[0] <= "힣":
                out.append(last + s[:6])
            last = s[-1] if s else last
        elif (
            t.kind == "ctl"
            and t.code in BREAK
            or t.kind == "end"
            or t.kind == "ctl"
            and t.code in VAR
        ):
            last = ""
    return out


def check_pair(tag, a_tokens, b_tokens, decode, stat, bad):
    if not any(
        "가" <= ch <= "힣" for t in b_tokens if t.kind == "text" for ch in decode(bytes(t.raw))
    ):
        stat["한글 없는 스트림(코드 바이트 오탐)"] += 1
        return
    stat["대조"] += 1
    sa, sb = var_slots(a_tokens), var_slots(b_tokens)
    if [x[0] for x in sa] == [x[0] for x in sb]:
        stat["변수 자리"] += len(sa)
        for (c, was_space), (_, now_space) in zip(sa, sb, strict=True):
            if was_space and not now_space:
                bad.append((tag, "변수 앞 공백", f"코드 {c:02x}"))
    else:
        stat["변수 열 달라 못 쟀다"] += 1
    for j in joined(b_tokens, decode):
        bad.append((tag, "문장 이음", j))
    wa = sum(1 for t in a_tokens if t.kind == "ctl" and t.code in (0x03, 0x05))
    wb = sum(1 for t in b_tokens if t.kind == "ctl" and t.code in (0x03, 0x05))
    stat["대기 대조"] += 1
    if wb < wa:
        if tag in WAIT_OK:
            stat["대기 줄음 허용"] += 1
        else:
            bad.append((tag, "대기 줄음", f"쪽·키 대기(03·05) {wa} → {wb}"))
    ta, tb = tail(a_tokens), tail(b_tokens)
    if any(t.kind == "text" for t in a_tokens) and any(t.kind == "text" for t in b_tokens):
        stat["끝 대조"] += 1
        if ta != tb:
            if (ta, tb) in TAIL_OK:
                stat["끝 허용 꼴"] += 1
            else:
                bad.append((tag, "끝 개행", f"{' '.join(ta)} → {' '.join(tb)}"))


def decoder():
    codes = json.loads(
        (common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")
    )
    rev = {v.to_bytes(2, "big"): k for k, v in codes.items() if isinstance(v, int)}
    return lambda raw: scene_sweep.korean(raw, rev)


def iter_pairs(orig: bytes, kr: bytes, stat=None):
    """→ (자리, 원판 토큰, 롬 토큰) — 씬 모듈 짝지은 스트림 + 전투 블록. 조판 전수 검사(typeset_audit)도 쓴다."""
    import battle
    import pair_texts

    stat = Counter() if stat is None else stat
    km = {(b, k): m for b, k, m in scene_sweep.built_modules(kr)}
    for blk, k, om in archives.modules(orig):
        omod = scene.parse_module(om)
        nm = km[(blk, k)]
        nmod, pair = scene.pair_streams(omod, nm)
        protected = bytearray(
            len(omod.data)
        )  # 표 워드·머리 표 레코드 — 글이 아니라 자료(color_check 와 같다)
        for a in omod.tables:
            protected[a.word : a.word + 2] = b"\x01\x01"
        for e, ln in omod.entries.items():
            protected[e : e + ln] = b"\x01" * ln
        for s, st in sorted(omod.streams.items()):
            n = pair.get(s)
            if n is None:
                continue
            head = b"".join(x.raw for x in st.tokens)[:14]
            if (
                (b"\x4e\x71" in head and st.tokens[0].kind != "text")
                or (
                    st.tokens[0].kind == "ctl"
                    and st.tokens[0].code == 0x16
                    and len(st.tokens[0].raw) >= 8
                )
                or any(protected[x.off] for x in st.tokens if x.kind != "eof")
            ):
                stat["표 머리(글 아님)"] += 1
                continue
            live = [t for t in st.tokens if t.kind != "eof"]
            if not (len(live) == 1 and live[0].ref == scene.GOTO):
                n = SC.resolve(nm, nmod, n)
            wg = bool(live) and live[-1].ref == scene.GOTO
            try:
                nst = nmod.streams.get(n) or scene.parse_stream(nm, n)
                ntoks = CC.follow_tokens(nm, nst, nmod, wg)
            except (ValueError, IndexError):
                continue
            yield f"{blk:03d}-{k}:{s:04x}", st.tokens, ntoks
    ob, kb = list(battle.blocks(orig)), list(battle.blocks(kr))
    for n, ((_s, jb, _e), (_s2, bb, _e2)) in enumerate(zip(ob, kb, strict=True)):
        for it in pair_texts.pair_block(jb, bb, n):
            if it["kr_off"] is None:
                continue
            try:
                st = scene.parse_stream(jb, it["off"])
                a = st.tokens
                live = [t for t in a if t.kind != "eof"]
                wg = bool(live) and live[-1].ref == scene.GOTO
                b = CC.follow_tokens(bb, scene.parse_stream(bb, it["kr_off"]), None, wg)
            except (ValueError, IndexError):
                continue
            yield f"전투{n:03d}:{it['off']:04x}", a, b


def run(orig: bytes, kr: bytes):
    dec = decoder()
    stat, bad = Counter(), []
    for tag, a, b in iter_pairs(orig, kr, stat):
        check_pair(tag, a, b, dec, stat, bad)
    return stat, bad


def selftest() -> bool:
    """검사기 자체 시험 — 가짜 토큰으로 세 부류가 각각 잡히는가."""

    class T:
        def __init__(self, kind, code=None, raw=b""):
            self.kind, self.code, self.raw, self.ref = kind, code, raw, None

    sp = [T("text", raw="가 ".encode()), T("ctl", 0x15), T("text", raw="로".encode())]
    nosp = [T("text", raw="가".encode()), T("ctl", 0x15), T("text", raw="로".encode())]
    stat, bad = Counter(), []
    check_pair("t", sp, nosp, lambda r: r.decode(), stat, bad)
    ok1 = [b[1] for b in bad] == ["변수 앞 공백"]
    stat, bad = Counter(), []
    ok2 = True
    j = joined(
        [T("text", raw="왕자!?".encode()), T("text", raw="자".encode())], lambda r: r.decode()
    )
    ok3 = j == ["?자"]
    stat, bad = Counter(), []
    check_pair(
        "t",
        [T("text", raw="가".encode()), T("ctl", 0x01), T("end", 0x00)],
        [T("text", raw="가".encode()), T("end", 0x07)],
        lambda r: r.decode(),
        stat,
        bad,
    )
    ok4 = [b[1] for b in bad] == ["끝 개행"]
    stat, bad = Counter(), []  # 쪽 대기(05) 가 빠진 번역 — 「대기 줄음」으로 잡혀야 한다(양성 대조)
    check_pair(
        "t",
        [T("text", raw="가".encode()), T("ctl", 0x05), T("text", raw="나".encode()), T("end", 0x00)],
        [T("text", raw="가나".encode()), T("end", 0x00)],
        lambda r: r.decode(),
        stat,
        bad,
    )
    ok5 = [b[1] for b in bad] == ["대기 줄음"]
    return ok1 and ok2 and ok3 and ok4 and ok5


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = Path(args[0]) if args else common.BUILD_DIR / common.BUILD_TAG / "ed2-kr.bin"
    if not selftest():
        print("❌ 검사기 자체 시험 실패 — 가짜 꼴을 못 잡았다")
        sys.exit(1)
    stat, bad = run(common.rom(), path.read_bytes())
    kinds = Counter(b[1] for b in bad)
    print(
        f"띄어쓰기·개행 대조 [md-ed2] — 대조 스트림 {stat['대조']} · 변수 자리 {stat['변수 자리']} (못 잰 열 {stat['변수 열 달라 못 쟀다']}) "
        f"· 끝 대조 {stat['끝 대조']} (허용 꼴 {stat['끝 허용 꼴']}) · 어긋남 {len(bad)}"
        + "".join(f" · {k} {v}" for k, v in sorted(kinds.items()))
        + " · 자체 시험 통과"
    )
    for tag, kind, what in bad[: None if "--list" in sys.argv else 15]:
        print(f"  ✗ {tag} [{kind}] {what}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
