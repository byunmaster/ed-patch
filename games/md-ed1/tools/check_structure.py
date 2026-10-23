"""구조 대조 정적 검사 — 원본(originals)과 **빌드 결과** 의 대본 블록에서 글자 바이트를 빼고 제어 코드 열만 맞댄다.

왜: ss-ed3 가 10-21 재조판 때 대사 끝에 넣은 채움 바이트(FF FF)가 다음 블록 호출을 막아, 블록을 한 장씩 띄우는 하네스·qa 로는
안 보이고 **연속 재생에서만** 대사가 빠졌다(마스터 10-22 「재배치사고 막는 정적검사」). 이 게임도 대사를 다시 쓰고 모듈을 재조립(`scene.reassemble`)
하므로 같은 위험이 있다. 글자는 판정 대상이 아니다 — **제어 코드가 같은 꼴로 이어지는가**만 본다.

검사 (블록마다 · 원본 뿌리/표/항목 → 새 모듈의 같은 자리에서 시작해 참조를 따라가며 쌍으로 걷는다)
  1. 스트림 쌍의 제어 토큰 열이 같다 — 코드 + 인자(참조 변위는 빼고 **착지 쌍**으로 맞댄다). 글자 토큰은 건너뛴다.
     허용(조판이 자리를 바꾸는 것): `01`(줄바꿈) · `05`(쪽 넘김) — 아래 ALLOW.
  2. goto/call/분기 착지가 **새 모듈의 스트림 시작**을 가리킨다(글자 한복판이 아니다) · 원본 착지 하나는 새 착지 하나에만 대응한다.
  3. 이어 읽기 — 원본에서 끝 코드 바로 뒤에 다음 스트림이 붙어 있으면(상점·NPC 사슬 · 조건 분기 꼬리) 새 모듈에서도 **바로 뒤에** 같은 쌍이 붙어 있다.
  4. 채움 — 새로 덧붙은 구간(원본 길이 뒤)에 어떤 스트림에도 안 덮인 바이트가 없다(정렬 1B · 모듈 끝 eof 의 00 만 허용).
  5. 분모 — 대조한 스트림 수 / 원본 스트림 수를 출력한다(안 건드린 블록은 원본 그대로라 「동일 블록」으로 센다).

ALLOW (의도적으로 다른 꼴 — 이 목록에 없는 차이는 전부 실패):
  - `01`·`05`: 조판기(`build.typeset`)가 쪽·줄을 다시 짠다. 렌더러 `$978C` 안에서만 쓰이고 흐름(끝 코드 · 분기)을 안 바꾼다
    (scene.py END 주석 — 끝은 00·06·07·0A·0D 뿐). 개수·자리는 달라도 된다.
  - `EB`·`EC`(조사 훅, `tools/josa.py`): 원본 문안엔 0회라 엔진이 비운 코드(핸들러 `$A4D0` = rts)를 우리 훅이 가져온 것 —
    훅 표 `0xA018`(워드 오프셋)·피연산자 길이 `0x9FE2` 를 빌드가 깐다. 번역 문안이 조사 자리에 넣는다.
  - `03`(시간 이음, 창 유지): 번역 문안이 원문의 이음 자리를 옮길 수 있고 같은 렌더러 안에서만 읽힌다 — 개수는 달라도 된다.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import scene

BASELINE = common.GAME_DIR / "structure_baseline.json"  # 아직 고치지 않은(보고된) 어긋남 — 전투·시스템 메시지 — 새 것만 실패, 고치면 --freeze 로 내린다
FREE = {0x01, 0x05, 0x03, 0xEB, 0xEC}  # 조판·번역이 개수·자리를 바꾸는 제어 코드 — 모듈 docstring 의 ALLOW


def ctl_seq(tokens: list) -> list[tuple]:
    """제어 토큰 열(글자 제외) — 참조 변위는 빼고 (코드, 종류) 만, 그 밖엔 raw."""
    out: list[tuple] = []
    for t in tokens:
        if t.kind == "text":
            continue  # 글자는 판정 대상이 아니다(「글이 있나」는 has_text 로 따로)
        if t.kind == "eof":
            out.append(("eof",))
            continue
        if t.kind == "end":
            out.append(("end", t.code))
            continue
        if t.code in FREE:
            continue
        if t.ref in (scene.GOTO, scene.CALL):
            out.append((t.code, t.ref))
        elif t.ref == scene.MULTI:
            out.append((t.code, t.ref, len(t.targets)))
        elif t.ref == scene.CELL:
            out.append((t.code, t.ref))  # 착지는 따로 절대 오프셋으로 맞댄다
        elif t.ref == scene.CODE:
            out.append((t.code, t.ref))
        else:
            out.append((t.code, t.raw))
    return out


def has_text(tokens: list) -> bool:
    return any(t.kind == "text" and t.raw for t in tokens)


def targets_of(tokens: list) -> list[tuple]:
    """(종류, 착지 …) — goto/call/분기는 스트림 착지, 셀·코드는 모듈 안 절대 오프셋."""
    out = []
    for t in tokens:
        if t.kind != "ctl" or t.ref is None:
            continue
        if t.ref == scene.MULTI:
            out.append((t.ref, t.targets))
        else:
            out.append((t.ref, (t.target,)))
    return out


# 의도적으로 다른 꼴(스트림 단위 면제) — 블록 → {원본 스트림 시작: 근거}. 이 목록에 없는 차이는 전부 실패.
EXEMPT: dict[int, dict[int, str]] = {
    # 배우 이름 레코드 — 스트림처럼 읽히지만 `ff nn` 이름 코드 바이트를 `actor_names.new_block`(build.py) 이 같은 길이로 한글 코드로 바꾼 자료다.
    161: {0x954: "배우 이름 레코드(actor_names.BLOCK) — 이름 코드 바이트를 같은 길이로 교체, 흐름 코드 없음"},
}


def compare_module(orig_b: bytes, new_b: bytes, block: int = -1) -> tuple[list[str], dict]:
    """한 블록 — (어긋남 목록, 통계)."""
    errs: list[str] = []
    stat = {"streams": 0, "paired": 0, "adj": 0, "pad": 0, "moved": 0, "copies": 0, "pg_orig": 0, "pg_new": 0, "zeroed": 0}
    orig = scene.parse_module(orig_b)
    stat["streams"] = len(orig.streams)
    if new_b == orig_b:
        stat["paired"] = len(orig.streams)
        return errs, stat
    new = scene.parse_module(new_b, orig)
    pair: dict[int, int] = {}  # 원본 스트림 → 새 스트림(참조·표·뿌리로 대응이 선 것 — 꼬리 복사본은 여기 안 든다)
    seen: set[tuple[int, int]] = set()
    first: dict[int, int] = {}  # 원본 스트림 → 처음 대응된 새 스트림(복사본 말고 주 사본)
    work: list[tuple[int, int, str]] = []

    extra: dict[int, scene.Stream] = {}  # 모듈 파서가 못 찾은 익명 꼬리 복사본 — 이어 읽기 자리에서 직접 읽는다

    def stream_at(n: int):
        if n in new.streams:
            return new.streams[n]
        if n not in extra:
            try:
                extra[n] = scene.parse_stream(new_b, n)
            except (ValueError, IndexError):
                return None
        return extra[n]

    def add(o: int, n: int, why: str, tail: bool = False) -> None:
        """tail=True 는 이어 읽기 꼬리 — 재조립이 **꼬리 복사본**을 따로 방출하므로(scene.reassemble) 새 자리가 둘일 수 있다."""
        if stream_at(n) is None or (not tail and n not in new.streams):
            errs.append(f"{why}: 원본 {o:#x} 의 새 착지 {n:#x} 가 스트림 시작이 아니다")
            return
        if not tail:
            if o in pair and pair[o] != n:
                errs.append(f"{why}: 원본 스트림 {o:#x} 가 새 자리 둘로 갈렸다 {pair[o]:#x} / {n:#x}")
                return
            pair[o] = n
        if (o, n) in seen:
            return
        seen.add((o, n))
        first.setdefault(o, pair.get(o, n))
        work.append((o, n, why))

    for ins, s in orig.roots.items():
        if ins not in new.roots:
            errs.append(f"뿌리 lea @{ins:#x} 가 새 모듈에서 사라졌다")
            continue
        add(s, new.roots[ins], f"뿌리 @{ins:#x}")
    if len(new.tables) != len(orig.tables):
        errs.append(f"표 항목 수가 갈렸다 {len(orig.tables)} → {len(new.tables)}")
    else:
        for a, c in zip(orig.tables, new.tables, strict=True):
            add(a.target, c.target, f"표 @{a.word:#x}")
    for p, v in orig.entries.items():
        add(v, struct.unpack(">H", new_b[p : p + 2])[0], f"항목 @{p:#x}")

    def visit(o: int, n: int, why: str) -> None:
        so, sn = orig.streams[o], stream_at(n)
        if o in EXEMPT.get(block, {}):
            return
        a, b = ctl_seq(so.tokens), ctl_seq(sn.tokens)
        if has_text(so.tokens) != has_text(sn.tokens):  # 글이 사라졌거나 끼어든 빈 스트림(끝 코드만 있는 06 하나 — 41:0xb72)
            errs.append(f"스트림 {o:#x}→{n:#x} ({why}) 글 유무가 다르다: 원본 {has_text(so.tokens)} / 빌드 {has_text(sn.tokens)}")
            return
        if a != b:
            k = next((i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), min(len(a), len(b)))
            errs.append(
                f"스트림 {o:#x}→{n:#x} ({why}) 제어 열이 다르다 @{k}: 원본 {a[k : k + 3]} / 빌드 {b[k : k + 3]}"
            )
            return
        ro = [t for t in so.tokens if t.kind == "ctl" and t.ref and t.code not in FREE]
        rn = [t for t in sn.tokens if t.kind == "ctl" and t.ref and t.code not in FREE]
        for x, y in zip(ro, rn, strict=True):
            if x.ref in (scene.GOTO, scene.CALL):
                add(x.target, y.target, f"{o:#x} 의 <{x.code:02x}>")
            elif x.ref == scene.MULTI:
                for tx, ty in zip(x.targets, y.targets, strict=True):
                    add(tx, ty, f"{o:#x} 의 <16> 분기")
            elif x.target != y.target:  # 셀·코드 — 제자리 자료라 절대 오프셋이 같아야 한다
                errs.append(
                    f"스트림 {o:#x} 의 <{x.code:02x}> {x.ref} 착지가 움직였다 {x.target:#x} → {y.target:#x}"
                )
        so_t = scene._successor(orig, o)  # 조건 분기 꼬리 · 끝 코드 사슬 — 새 모듈에서도 **바로 뒤**여야 한다(복사본이어도 됨)
        if so_t is not None:
            stat["adj"] += 1
            add(so_t, sn.end, f"{o:#x} 바로 뒤 {so_t:#x}", tail=True)

    while work:
        visit(*work.pop())
    stat["paired"] = len({o for o, _ in seen})
    # 남이 들어오는 바이트 — 원본에서 **다른 스트림 한복판**으로 점프·참조가 들어오는 자리(접미 공유)를 우리가 덮지 않았나(pce-ed1 10-22:
    # A 가 넘쳐 제자리 끝에 둔 점프 스텁이 원본 종료 바이트를 덮었는데 B 의 끝 점프가 바로 그 바이트로 들어와 스텁 주소를 글자로 읽었다).
    # 새 모듈에서도 그 목표가 **다른 새 스트림 안**이면(여전히 공유) 공유 구간은 원본과 바이트까지 같아야 한다.
    o_ext = sorted((s, st.end) for s, st in orig.streams.items())
    n_ext = sorted((s, st.end) for s, st in [*new.streams.items(), *extra.items()])
    for o, n in pair.items():
        if o in EXEMPT.get(block, {}) or not any(s < o < e for s, e in o_ext):
            continue
        so = orig.streams[o]
        if any(s < n < e for s, e in n_ext):
            length = so.end - o
            if new_b[n : n + length] != orig_b[o : o + length]:
                errs.append(
                    f"원본 {o:#x} 는 다른 스트림 한복판으로 들어오는 목표(접미 공유)인데 새 {n:#x} 도 공유 구간이라 "
                    f"바이트가 원본과 같아야 하나 달라졌다(덮인 종료·스텁)"
                )
    # 장부(relocations.py)용 — 옮긴 스트림 · 꼬리 복사본 · 쪽 넘김 수 · 원본 자리를 0 으로 비운 바이트
    stat["moved"] = sum(1 for o, n in pair.items() if o != n)
    stat["copies"] = len(seen) - len(first)  # 같은 원본 스트림의 두 번째 이후 새 사본(꼬리 복사본)
    stat["pg_orig"] = sum(
        1 for o in first for t in orig.streams[o].tokens if t.kind == "ctl" and t.code == 0x05
    )
    stat["pg_new"] = sum(
        1 for n in first.values() for t in (stream_at(n).tokens if stream_at(n) else []) if t.kind == "ctl" and t.code == 0x05
    )
    stat["zeroed"] = sum(
        len(t.raw) for o, n in pair.items() if o != n for t in orig.streams[o].tokens if new_b[t.off : t.off + len(t.raw)] == b"\x00" * len(t.raw)
    )
    # 채움 — 덧붙은 구간(원본 길이 뒤)에 스트림이 안 덮은 바이트
    cov = bytearray(len(new_b))
    for st in [*new.streams.values(), *extra.values()]:
        for t in st.tokens:
            cov[t.off : t.off + len(t.raw)] = b"\x01" * len(t.raw)
    holes = [i for i in range(len(orig_b), len(new_b)) if not cov[i]]
    allow_pad = set()  # 정렬 1B(원본 길이가 홀수일 때) · 모듈 끝 eof 스트림 뒤의 00
    if len(orig_b) & 1 and len(new_b) > len(orig_b):
        allow_pad.add(len(orig_b))
    for st in [*new.streams.values(), *extra.values()]:
        if st.tokens and st.tokens[-1].kind == "eof":
            allow_pad.add(st.end)
    holes = [i for i in holes if i not in allow_pad]
    stat["pad"] = len(holes)
    if holes:
        errs.append(
            f"덧붙은 구간에 스트림이 안 덮은 바이트 {len(holes)}개 @{holes[0]:#x}… = {new_b[holes[0] : holes[0] + 4].hex()}"
        )
    return errs, stat


# ── 전투 · 시스템 메시지 · 자막 — 같은 잣대(제어 열 · 착지 · 이어 읽기 · 채움)를 이 범주들의 짝짓기 규칙으로 ───────────────────────────────────────────

# 글자가 없어도(또는 달라도) 되는 의도적 차이 — 이 목록에 없으면 실패.
EXEMPT_TEXT: dict[tuple[str, int], str] = {
    ("시스템", 0x36A1): "원문 꼬리 「ました。」 — 한국어는 앞 스트림이 문장을 끝내 꼬리를 `<00>` 한 코드로 비웠다(textmap/sysmsg.json 036a1)",
}
CAPTION_FREE = {0x1E, 0x1F}  # 자막 — 들여쓰기 span(1E 공백 1F)을 번역은 평범한 공백으로 쓴다(captions.dlg_layout, 화면 확인 10-13)


def _norm(tokens: list, extra_free: set[int] | None = None, drop_hi: bool = False) -> list:
    seq = ctl_seq(tokens)
    out = []
    for x in seq:
        if isinstance(x[0], int) and (extra_free and x[0] in extra_free or drop_hi and x[0] >= 0xF0):
            continue
        out.append(x)
    return out


def _text_len(tokens: list) -> int:
    return sum(len(t.raw) for t in tokens if t.kind == "text")


def _same(so, sn, cat: str, key: int, orig, new, drop_goto_target=None, caption: bool = False) -> str | None:
    """스트림 한 쌍 — 어긋나면 이유 문자열."""
    a = _norm(so.tokens, CAPTION_FREE if caption else None, caption)
    b = _norm(sn.tokens, CAPTION_FREE if caption else None, caption)
    ta, tb = has_text(so.tokens), has_text(sn.tokens)
    if a != b:
        # 전투 drop_goto — 원본이 goto 로 공용 꼬리를 부르던 걸 우리 문안이 꼬리까지 이어 쓰고 끝 코드로 닫았다(battle.drop_goto): 원본 열 + 착지 스트림 열 == 새 열
        if drop_goto_target is not None and a and a[-1] == (scene.GOTO_CODE, scene.GOTO):
            tgt = drop_goto_target
            if a[:-1] + _norm(tgt.tokens) == b:
                return None
        return f"제어 열이 다르다: 원본 {a[:6]} / 빌드 {b[:6]}"
    if ta != tb and (cat, key) not in EXEMPT_TEXT:
        hook = any(t.kind == "ctl" and t.code in (0xEB, 0xEC) for t in sn.tokens)
        if hook and not tb and _text_len(so.tokens) <= 4:
            return None  # 원문의 조사 한 조각(「は」)을 조사 훅(EB·EC)이 대신 낸다 — tools/josa.py
        return f"글 유무가 다르다: 원본 {ta} / 빌드 {tb}"
    return None


def _follow_stub(orig: bytes, new: bytes, s: int) -> int:
    """제자리에 goto(0F) 스텁만 남기고 본문을 옮긴 곳 — 스텁을 따라간다(battle jumps · sysmsg TAIL_JUMP)."""
    for _ in range(4):
        if new[s] == 0x0F and orig[s] != 0x0F:
            s = s + 1 + struct.unpack(">h", new[s + 1 : s + 3])[0]
        else:
            break
    return s


def _must_adjoin(so, succ_has_ref: bool, six: bool = True) -> bool:
    """끝 코드 뒤에 다음 스트림이 **반드시** 바로 붙어야 하는가 — 다음 스트림이 참조 없이 사슬로만 닿을 때, 그리고(six=True, 시스템 메시지) 06
    (그냥 반환: 게임이 수치를 찍고 이어 읽는다 — sysmsg 흐름 게이트와 같은 규칙). 전투는 다음 스트림이 자기 lea 를 가지면(보스 대사 줄 사이 따위)
    이웃일 뿐이라 six=False."""
    last = so.tokens[-1] if so.tokens else None
    return last is not None and last.kind == "end" and ((six and last.code == 0x06) or (last.code in scene.FLOW and not succ_has_ref))


def compare_battle(orig_rom: bytes, new_rom: bytes) -> tuple[list[str], int, int, int]:
    import battle

    errs: list[str] = []
    total = ok = unmapped = 0
    for b, ((_, jb, _), (_, kb, _)) in enumerate(zip(battle.blocks(orig_rom), battle.blocks(new_rom), strict=True)):
        jr = battle.refs(jb)
        new_start: dict[int, int | None] = {}
        for tgt, e in jr.items():
            if e["lea"]:
                i = e["lea"][0]
                new_start[tgt] = i + 2 + struct.unpack(">h", kb[i + 2 : i + 4])[0]
            elif e["words"]:
                new_start[tgt] = struct.unpack(">H", kb[e["words"][0] : e["words"][0] + 2])[0]
            else:
                new_start[tgt] = None
        # 사슬 — 참조 없는 스트림은 바로 앞 스트림의 새 끝에서 이어진다(앞 스트림 순서대로 전파)
        for tgt in sorted(jr):
            total += 1
            if new_start[tgt] is None:
                prev = [p for p, e in jr.items() if e["stream"].end == tgt and new_start.get(p) is not None]
                if prev:
                    try:
                        new_start[tgt] = scene.parse_stream(kb, _follow_stub(jb, kb, new_start[prev[0]])).end
                    except (ValueError, IndexError):
                        new_start[tgt] = None
            ns = new_start[tgt]
            if ns is None:
                unmapped += 1
                continue
            ns = _follow_stub(jb, kb, ns)
            so = jr[tgt]["stream"]
            try:
                sn = scene.parse_stream(kb, ns)
            except (ValueError, IndexError):
                errs.append(f"전투 블록 {b} 스트림 {tgt:#x}→{ns:#x}: 새 롬에서 안 풀린다")
                continue
            gt = None
            if so.tokens and so.tokens[-1].kind == "ctl" and so.tokens[-1].ref == scene.GOTO:
                gt = jr[so.tokens[-1].target]["stream"] if so.tokens[-1].target in jr else scene.parse_stream(jb, so.tokens[-1].target)
            why = _same(so, sn, "전투", tgt + b * 0x100000, jb, kb, gt)
            if why:
                errs.append(f"전투 블록 {b} 스트림 {tgt:#x}→{ns:#x}: {why}")
                continue
            ok += 1
            # 끝 코드 사슬 — 다음 스트림이 바로 붙어야 하는 자리
            succ = so.end
            if succ in jr and _must_adjoin(so, bool(jr[succ]["lea"] or jr[succ]["words"]), six=False):
                try:
                    nx = scene.parse_stream(kb, _follow_stub(jb, kb, sn.end))
                except (ValueError, IndexError):
                    errs.append(f"전투 블록 {b} 스트림 {tgt:#x}: 끝 코드 뒤 {sn.end:#x} 가 안 풀린다")
                    continue
                w2 = _same(jr[succ]["stream"], nx, "전투", succ + b * 0x100000, jb, kb)
                if w2:
                    errs.append(f"전투 블록 {b} 스트림 {tgt:#x} 바로 뒤 {succ:#x}→{sn.end:#x}: {w2}")
    return errs, ok, total, unmapped


def compare_sysmsg(orig_rom: bytes, new_rom: bytes) -> tuple[list[str], int, int, int]:
    import sysmsg

    S = sysmsg.streams(orig_rom)
    errs: list[str] = []

    def nref(kind: str, ins: int) -> int:
        if kind == "pc":
            return ins + 2 + struct.unpack(">h", new_rom[ins + 2 : ins + 4])[0]
        if kind == "abs":
            return int.from_bytes(new_rom[ins + 2 : ins + 6], "big")
        base = int(kind[4:], 16)  # tbl:<base>
        return base + struct.unpack(">h", new_rom[ins : ins + 2])[0]

    image: dict[int, int] = {}
    for t, e in S.items():
        vals = {nref(k, ins) for k, ins in e["refs"]}
        if len(vals) > 1:
            errs.append(f"시스템 {t:#x}: 참조가 서로 다른 새 자리로 갈렸다 {sorted(hex(v) for v in vals)}")
        if vals:
            image[t] = _follow_stub(orig_rom, new_rom, min(vals))
    # 남이 들어오는 바이트 — 다른 문안 한복판(접미 공유)으로 들어오는 목표의 진입 바이트가 스텁·글자로 덮이지 않았나(pce-ed1 10-22)
    ext = sorted((t, e["stream"].end) for t, e in S.items())
    interior = [t for t, _ in ext if any(a < t < b for a, b in ext)]
    for t in interior:
        if t in image:
            first_new = min({nref(k, ins) for k, ins in S[t]["refs"]})
            if new_rom[first_new] == 0x0F and orig_rom[t] != 0x0F:
                errs.append(f"시스템 {t:#x}: 다른 문안 한복판으로 들어오는 목표인데 새 {first_new:#x} 의 진입 바이트가 점프 스텁이다")
    ok = 0
    seen: set[tuple[int, int]] = set()
    work = list(image.items())
    while work:
        t, ns = work.pop()
        if (t, ns) in seen:
            continue
        seen.add((t, ns))
        so = S[t]["stream"] if t in S else scene.parse_stream(orig_rom, t)
        try:
            sn = scene.parse_stream(new_rom, ns)
        except (ValueError, IndexError):
            errs.append(f"시스템 {t:#x}→{ns:#x}: 새 롬에서 안 풀린다")
            continue
        why = _same(so, sn, "시스템", t, orig_rom, new_rom)
        if why:
            errs.append(f"시스템 {t:#x}→{ns:#x}: {why}")
            continue
        ok += 1
        for x, y in zip(
            [k for k in so.tokens if k.kind == "ctl" and k.ref in (scene.GOTO, scene.CALL)],
            [k for k in sn.tokens if k.kind == "ctl" and k.ref in (scene.GOTO, scene.CALL)],
            strict=False,
        ):
            work.append((x.target, _follow_stub(orig_rom, new_rom, y.target)))
        succ = so.end
        if succ in S and _must_adjoin(so, bool(S[succ]["refs"])):
            if succ in image and image[succ] != sn.end:
                errs.append(f"시스템 {t:#x} 바로 뒤 {succ:#x}: 끝 코드 뒤에 바로 이어지지 않는다(새 끝 {sn.end:#x} ≠ 새 {succ:#x} 자리 {image[succ]:#x})")
            else:
                work.append((succ, sn.end))
    mapped = {t for t, _ in seen}
    return errs, len(mapped & set(S)), len(S), len(set(S) - mapped)


def compare_captions(orig_rom: bytes, new_rom: bytes) -> tuple[list[str], int, int, int]:
    import captions

    errs: list[str] = []
    newbase = {b: int.from_bytes(new_rom[p : p + 4], "big") for ptrs in captions.RELOCATE.values() for b, p in ptrs}
    total = ok = 0
    for name, bases, _area in captions.FAMILIES:
        for base in bases:
            nb = newbase.get(base, base)
            ow, nw = captions.words(orig_rom, base), captions.words(new_rom, nb)
            if len(ow) != len(nw):
                errs.append(f"자막 {name} 표 {base:#x}: 항목 수가 갈렸다 {len(ow)} → {len(nw)}")
                continue
            for (_p, op, arg), (_q, op2, arg2) in zip(ow, nw, strict=True):
                total += 1
                if op != op2:
                    errs.append(f"자막 {name} 표 {base:#x}: 오프코드가 갈렸다 {op} → {op2}")
                elif op != 0:
                    if arg != arg2:
                        errs.append(f"자막 {name} 표 {base:#x}: 오프코드 {op} 의 인자가 갈렸다 {arg} → {arg2}")
                    else:
                        ok += 1
                else:
                    try:
                        so = scene.parse_stream(orig_rom, base + arg)
                        sn = scene.parse_stream(new_rom, nb + arg2)
                    except (ValueError, IndexError):
                        errs.append(f"자막 {name} 표 {base:#x}: 스트림이 안 풀린다")
                        continue
                    why = _same(so, sn, "자막", base + arg, orig_rom, new_rom, caption=True)
                    if why:
                        errs.append(f"자막 {name} {base + arg:#x}→{nb + arg2:#x}: {why}")
                    else:
                        ok += 1
    return errs, ok, total, 0


def run(orig_rom: bytes, new_rom: bytes) -> tuple[int, int, list[str], dict, list]:
    """→ (블록 수, 스트림 수, 어긋남, 합계, 블록별 통계)."""
    base = archives.ARCHIVES["script"][0]
    ob, nb = archives.blocks(orig_rom, base), archives.blocks(new_rom, base)
    errs: list[str] = []
    tot = dict.fromkeys(
        ("streams", "paired", "adj", "pad", "same", "blocks", "moved", "copies", "pg_orig", "pg_new", "zeroed"), 0
    )
    per: list[tuple[int, dict]] = []
    for n, ((_, a, _), (_, b, _)) in enumerate(zip(ob, nb, strict=True)):
        e, st = compare_module(a, b, n)
        tot["blocks"] += 1
        tot["same"] += a == b
        for k in tot:
            if k in st:
                tot[k] += st[k]
        per.append((n, st))
        errs += [f"블록 {n}: {x}" for x in e]
    return tot["blocks"], tot["streams"], errs, tot, per


def main() -> int:
    args = [x for x in sys.argv[1:] if not x.startswith("-")]
    new_path = Path(args[0]) if args else common.BUILD_DIR / common.BUILD_TAG.replace("/", "_") / "ed1-kr.bin"
    if not new_path.exists():
        print(f"  구조 대조 — 빌드 롬이 없다({new_path}) — 안 쟀다")
        return 0
    blocks, streams, errs, tot, _per = run(common.rom(), new_path.read_bytes())
    print(
        f"  구조 대조 [대본] — 블록 {blocks}(원본 그대로 {tot['same']}) · 스트림 {tot['paired']}/{streams} 쌍 대조 · "
        f"사슬 이음 {tot['adj']} · 채움 구멍 {tot['pad']} · 어긋남 {len(errs)}"
    )
    for e in errs[:40]:
        print("   ✗", e)
    orig_rom, new_rom = common.rom(), new_path.read_bytes()
    bad = len(errs)
    import json

    base = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else []
    allerr: list[str] = []
    for label, fn in (("전투", compare_battle), ("시스템 메시지", compare_sysmsg), ("자막", compare_captions)):
        e, ok, total, unm = fn(orig_rom, new_rom)
        known = [x for x in e if x in base]
        new_e = [x for x in e if x not in base]
        print(
            f"  구조 대조 [{label}] — 스트림 {ok}/{total} 대조 · 닿지 않은 원본 스트림 {unm} · 어긋남 {len(e)}"
            + (f" (기준선 {len(known)} · 새 {len(new_e)})" if base else "")
        )
        for x in new_e[:40]:
            print("   ✗", x)
        allerr += e
        bad += len(new_e)
    if "--freeze" in sys.argv:
        BASELINE.write_text(json.dumps(sorted(allerr), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  구조 대조 기준선 갱신 — {len(allerr)}건")
    stale = [x for x in base if x not in allerr]
    if stale:
        print(f"  ℹ 기준선에서 사라진 {len(stale)}건 — `--freeze` 로 내린다")
    import relocations

    return max(1 if bad else 0, relocations.gate(orig_rom, new_rom, "--freeze" in sys.argv))


if __name__ == "__main__":
    raise SystemExit(main())
