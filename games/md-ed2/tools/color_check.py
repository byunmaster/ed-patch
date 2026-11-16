"""색 코드 대조 — 원판 스트림과 구운 롬의 같은 스트림에서 글자색을 바꾸는 코드의 개수·순서·글 앞뒤 위치를 맞댄다.

    python3 tools/color_check.py [롬.bin] [--list]      # 빌드 게이트(check.sh 5i) — 어긋남이 있으면 실패

배경(pce-ed1 10-29): 번역 조립기가 원문의 색 전환 옵코드를 한 번도 안 내 35메시지가 엉뚱한 색으로 나왔다 —
빌드·게이트·짝 표 어느 것도 못 잡았다. 이 검사는 정본 텍스트가 아니라 **롬에 들어간 바이트**를 원판과 맞댄다.

엔진(렌더러 `$B738` → 디스패치 `$BF58`, 핸들러 표 `$BFD0`) 에서 글자색을 바꾸는 코드는 다음이다(디스어셈블 실측):
  · 18~1F  색(d0)·창 속성(d1)을 `$FF201B/C` 에 쓰고 옛 값을 `$FF201D/E` 에 저장(`$C45A`) — 1E 는 화자 이름(색 6)
  · EE xx  `$FF201C` 에 쓰고 옛 값을 `$FF201E` 에 저장      EF xx  `$FF201B` 에 쓰고 옛 값을 `$FF201D` 에 저장
  · 04     `$FF201D/E` → `$FF201B/C` (저장해 둔 색 복귀)
  · 0E     (메뉴 선택 창) `$FF201B` 를 6 으로 임시 설정 — 대사 스트림에 안 나온다(나오면 목록에 든다)
대조 단위는 struct_check 와 같다(씬 모듈 356 의 짝지은 스트림 + 전투 블록 99).
 · 색열   = 위 코드(+인자)의 순서열.
 · 위치열 = 색 코드와 「글 덩이(T)」만 남긴 열 — 줄바꿈·▼·쪽·조사 훅은 번역이 정하므로 뺀다. 이름 호출(09)은 글로 센다.
부류: 누락(원판엔 있고 롬엔 없음) · 여분(그 반대) · 위치(색열은 같고 글 덩이와의 앞뒤가 다름) · 순서·인자(같은 코드 수, 다른 열).
"""

import sys
from collections import Counter
from itertools import pairwise
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import scene
import scene_sweep
import struct_check as SC

COLOR = {0x04, 0x0E, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F, 0xEE, 0xEF}
DROP = {0x01, 0x03, 0x05, 0xEB, 0xEC}  # 줄·▼·쪽·조사 훅 — 번역이 정한다
TEXTLIKE = {0x09}  # 이름 변수 호출 — 화면에선 글자


def seqs(tokens):
    """→ (색열, 위치열). 색열 = [(code, 인자 hex)], 위치열 = 색 코드와 'T' 만."""
    col, pos = [], []
    for t in tokens:
        if t.kind in ("eof", "end"):
            continue
        if t.kind == "text" and not t.raw.strip(b"\x20"):
            continue  # 공백뿐인 덩이 — 번역이 이름 앞뒤에 넣는 한 칸
        if t.kind == "text" or (t.kind == "ctl" and t.code in TEXTLIKE):
            if not pos or pos[-1] != "T":
                pos.append("T")
            continue
        if t.code in DROP or t.code not in COLOR:
            continue
        col.append((t.code, bytes(t.raw[1:]).hex()))
        pos.append((t.code, bytes(t.raw[1:]).hex()))
    return col, pos


def follow_tokens(kb: bytes, st, mod, want_goto_end: bool, depth=8):
    """꼬리가 goto 스텁이고 원판엔 그 goto 가 없으면 스텁을 따라 토큰을 이어 붙인다(struct_check.follow_stubs 의 토큰판)."""
    toks = list(st.tokens)
    while depth and not want_goto_end:
        live = [t for t in toks if t.kind != "eof"]
        if not live or live[-1].ref != scene.GOTO:
            break
        tgt = live[-1].target
        st2 = (mod.streams.get(tgt) if mod else None) or scene.parse_stream(kb, tgt)
        toks = live[:-1] + list(st2.tokens)
        depth -= 1
    return toks


def gaps(pos):
    """색 코드 사이마다 글 덩이가 있는지(True/False). 첫 색 앞·마지막 색 뒤는 번역이 조사·꼬리를 바꾸므로 보지 않는다."""
    idx = [i for i, x in enumerate(pos) if x != "T"]
    return tuple("T" in pos[a + 1 : b] for a, b in pairwise(idx))


def classify(oc, op, nc, np_):
    if oc == nc and gaps(op) == gaps(np_):
        return None
    co, cn = Counter(oc), Counter(nc)
    if co - cn and not (cn - co):
        return "누락"
    if cn - co and not (co - cn):
        return "여분"
    if co != cn:
        return "누락+여분"
    if oc != nc:
        return "순서·인자"
    return "위치"


def compare_modules(orig: bytes, kr: bytes):
    km = {(b, k): m for b, k, m in scene_sweep.built_modules(kr)}
    stat = Counter()
    bad = []
    for blk, k, om in archives.modules(orig):
        tag = f"{blk:03d}-{k}"
        nm = km[(blk, k)]
        omod = scene.parse_module(om)
        nmod, pair = scene.pair_streams(omod, nm)
        protected = bytearray(
            len(omod.data)
        )  # 표 워드·머리 표 레코드 — 글이 아니라 자료(별도 게이트가 본다, struct_check 와 같다)
        for a in omod.tables:
            protected[a.word : a.word + 2] = b"\x01\x01"
        for e, ln in omod.entries.items():
            protected[e : e + ln] = b"\x01" * ln
        for s, st in sorted(omod.streams.items()):
            n = pair.get(s)
            if n is None:
                stat["짝 없음"] += 1
                continue
            head = b"".join(x.raw for x in st.tokens)[:14]
            if (b"\x4e\x71" in head and st.tokens[0].kind != "text") or (
                st.tokens[0].kind == "ctl"
                and st.tokens[0].code == 0x16
                and len(st.tokens[0].raw) >= 8
            ):
                stat["표 머리(글 아님)"] += 1
                continue
            if any(protected[x.off] for x in st.tokens if x.kind != "eof"):
                stat["표 머리(글 아님)"] += 1
                continue
            live = [t for t in st.tokens if t.kind != "eof"]
            if not (len(live) == 1 and live[0].ref == scene.GOTO):
                n = SC.resolve(nm, nmod, n)
            wg = bool(live) and live[-1].ref == scene.GOTO
            try:
                nst = nmod.streams.get(n) or scene.parse_stream(nm, n)
                ntoks = follow_tokens(nm, nst, nmod, wg)
            except (ValueError, IndexError):
                stat["새 쪽 해석 실패"] += 1
                continue
            oc, op = seqs(st.tokens)
            nc, np_ = seqs(ntoks)
            stat["대조"] += 1
            stat["색 코드(원판)"] += len(oc)
            if oc:
                stat["색 있는 스트림"] += 1
            kind = classify(oc, op, nc, np_)
            if kind:
                bad.append((tag, s, n, kind, op, np_))
    return stat, bad


def compare_battles(orig: bytes, kr: bytes):
    import battle
    import pair_texts

    ob, kb = list(battle.blocks(orig)), list(battle.blocks(kr))
    stat = Counter()
    bad = []
    for n, ((_s, jb, _e), (_s2, bb, _e2)) in enumerate(zip(ob, kb, strict=True)):
        for it in pair_texts.pair_block(jb, bb, n):
            if it["kr_off"] is None:
                stat["짝 없음"] += 1
                continue
            if n == battle.BOSS_BLOCK and it["off"] in (*battle.BOSS_STREAMS, 0x902, 0x906):
                stat["보스 코드 패치(글 아님)"] += 1
                continue
            try:
                st = scene.parse_stream(jb, it["off"])
                live = [t for t in st.tokens if t.kind != "eof"]
                wg = bool(live) and live[-1].ref == scene.GOTO
                ntoks = follow_tokens(bb, scene.parse_stream(bb, it["kr_off"]), None, wg)
            except (ValueError, IndexError):
                stat["해석 실패"] += 1
                continue
            oc, op = seqs(st.tokens)
            nc, np_ = seqs(ntoks)
            stat["대조"] += 1
            stat["색 코드(원판)"] += len(oc)
            if oc:
                stat["색 있는 스트림"] += 1
            kind = classify(oc, op, nc, np_)
            if kind:
                bad.append((f"전투{n:03d}", it["off"], it["kr_off"], kind, op, np_))
    return stat, bad


def fmt(p):
    return " ".join("T" if x == "T" else f"<{x[0]:02x}{x[1]}>" for x in p)


def selftest() -> bool:
    """검사기 자체 시험 — 롬 사본에서 색 코드 한 바이트(1C→01)를 지우고, 같은 스트림을 맞댔을 때 「누락」으로 잡히는가."""
    for _blk, _k, om in archives.modules(common.rom()):
        omod = scene.parse_module(om)
        for s, st in sorted(omod.streams.items()):
            hit = [t for t in st.tokens if t.kind == "ctl" and t.code == 0x1C]
            if not hit:
                continue
            nm = bytearray(om)
            nm[hit[0].off] = 0x01  # 줄바꿈으로 바꿔 색 코드만 없앤다(인자 없는 1B 대 1B)
            oc, op = seqs(st.tokens)
            nc, np_ = seqs(scene.parse_stream(bytes(nm), s).tokens)
            return classify(oc, op, nc, np_) == "누락"
    return False


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = Path(args[0]) if args else common.BUILD_DIR / common.BUILD_TAG / "ed2-kr.bin"
    kr = path.read_bytes()
    orig = common.rom()
    if not selftest():
        print("❌ 검사기 자체 시험 실패 — 색 코드를 지운 사본을 못 잡았다")
        sys.exit(1)
    ms, mb = compare_modules(orig, kr)
    bs, bb = compare_battles(orig, kr)
    bad = mb + bb
    kinds = Counter(b[3] for b in bad)
    print(
        f"색 코드 대조 [md-ed2] — 대조 스트림 씬 {ms['대조']} · 전투 {bs['대조']} "
        f"(색 있는 스트림 씬 {ms['색 있는 스트림']} · 전투 {bs['색 있는 스트림']} · 원판 색 코드 {ms['색 코드(원판)'] + bs['색 코드(원판)']}개) "
        f"· 대조 못 한 것 {sum(v for k, v in (ms + bs).items() if k not in ('대조', '색 코드(원판)', '색 있는 스트림'))} "
        f"· 어긋남 {len(bad)}"
        + (
            "".join(f" · {k} {v}" for k, v in sorted(kinds.items()))
            + " · 자체 시험(색 코드 한 바이트) 통과"
        )
    )
    for tag, s, n, kind, op, np_ in bad[: None if "--list" in sys.argv else 15]:
        print(f"  ✗ {tag} 원판@{s:#x} 새@{n:#x} [{kind}] 원판 {fmt(op)} / 새 {fmt(np_)}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
