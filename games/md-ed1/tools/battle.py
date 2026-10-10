"""전투 아카이브(0x0CA94C, 110블록) — 몬스터 레코드의 이름과 전투 메시지 스트림.

블록 = 워드 5개(`[?][자료 A][자료 B][코드][끝=길이]`) + `FFFF` + 몬스터 레코드(0x0C 부터 **0x40 간격**,
이름은 레코드 +0x30 에 06 종결 — 반각 가나도 온다, 첫 바이트 비트7 이 서면 빈 슬롯, 마지막 레코드는
이름 뒤에서 절단) + 자료 A(등장 메시지 오프셋 BE16 포함) + 자료 B(코드 진입 워드) + 68000 코드 +
메시지 스트림(끝 00·06·07·0A). 코드는 `lea x(pc),aN` 으로 스트림을 가리켜 엔진 함수(`movea.l
#$85E2,a5`)로 찍는다. ⚠ `lea x(pc),a6` 는 문안 **앞 플래그 바이트**를 가리키는 변수 포인터다(뒤에
`move.b d0,(a6)`) — 그 뒤 1B 부터가 문안이고 자료 A 의 워드가 가리킨다. 로더 `$205CE`(조우 id →
색인 0xCA86E → 블록 색인).

재삽입(제자리 우선): 이름은 제자리(비마지막 레코드 15B, 마지막은 원본 길이 이하) · 스트림은 맞으면
제자리(0 패딩), 안 맞으면 끝에 붙이고 lea 변위·자료 A 워드를 고친다(플래그 문안은 옮기지 않는다) ·
끝 워드 = 새 길이. 문안 속 몬스터 이름은 `{JP이름}` · `{JP이름|가}`(조사) 태그로 쓴다 — 정본은
`monsters()` — 정본 고유명사(`shared/canon/nouns`)에서 읽는다(게임 폴더에 이름 표 없음).
"""

import dataclasses
import hashlib
import json
import re
import struct
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import archives
import common
import dict_names
import scene
import sysmsg

from shared import canon
from shared.text import josa

ARCHIVE = 0xCA94C
COUNT = 110
REC0, REC_STEP, NAME_AT = 0x0C, 0x40, 0x30
NAME_MAX = 15  # 16B 칸 − 06
LEA = re.compile(rb"([\x41\x43\x45\x47\x49\x4b])\xfa(..)", re.DOTALL)  # a6(4D) 는 플래그 포인터
FLAG = re.compile(rb"\x4d\xfa(..)(?:\x1c\x80|\x1c\xbc\x00\xff|\x1c\x86)", re.DOTALL)
SUFFIX = re.compile(r"[Ａ-ＤA-D♀♂]$")
NAME_TAG = re.compile(r"\{([^{}|]+)(?:\|([^{}]+))?\}")
MAP_JSON = common.GAME_DIR / "textmap" / "battle.json"
EXPECT = (
    269,
    100,
    323,
)  # 이름 · 기본 이름 · 고유 스트림(lea·플래그·자료 A + 연쇄 39, 2026-09-06 · 짧은 lea 조각 +3, 09-27)


def blocks(d: bytes):
    return archives.blocks(d, ARCHIVE)


def sections(b: bytes) -> tuple[int, ...]:
    return struct.unpack(">5H", b[:10])


def records(b: bytes) -> list[dict]:
    """[{start, name_at, name(bytes), last, cap}] — cap = 새 이름이 차지할 수 있는 최대 바이트(06 제외)."""
    t = sections(b)
    out = []
    p = REC0
    while p + NAME_AT < t[1]:
        nxt = p + REC_STEP
        last = nxt >= t[1]
        if not b[p] & 0x80:
            q = b.index(0x06, p + NAME_AT)
            name = b[p + NAME_AT : q]
            out.append(
                {
                    "start": p,
                    "name_at": p + NAME_AT,
                    "name": name,
                    "last": last,
                    "cap": (t[1] - (p + NAME_AT) - 1)
                    if last
                    else NAME_MAX,  # 마지막은 06 뒤 패딩까지
                }
            )
        p = nxt
    return out


def base_name(s: str) -> str:
    return SUFFIX.sub("", s).rstrip()


def suffix_of(s: str) -> str:
    m = SUFFIX.search(s)
    return m.group(0) if m else ""


def _stream(b: bytes, tgt: int):
    if not 0 <= tgt < len(b):
        return None
    try:
        st = scene.parse_stream(b, tgt)
    except (ValueError, IndexError):
        return None
    return st if scene._textlike(st) else None


def _short_lea(b: bytes, tgt: int):
    """`lea` 가 가리키는 **짧은 연결 조각**(「は<02>に」 · 「の 左」+goto) — 전각 3자 미만이라 `_textlike` 가
    거르지만 코드가 직접 가리키니 문안이다. 🔴 걸러진 넷(블록 23·73·93×2)이 번역 없이 원문 그대로 남아
    화면에 가나가 새거나(가나 글리프는 표 0 에 없다) 옮겨진 스트림의 빈자리로 goto 했다(2026-09-27).
    가나가 들어 있고 짧은 것만 받는다 — 자료 포인터가 우연히 풀린 것은 가나가 없다."""
    if not 0 <= tgt < len(b):
        return None
    try:
        st = scene.parse_stream(b, tgt)
    except (ValueError, IndexError):
        return None
    return st if st.end - tgt < 40 and _has_kana(st) else None


def refs(b: bytes) -> dict[int, dict]:
    """스트림 시작 → {stream, lea:[명령 자리], words:[자료 A 의 워드 자리], pinned}."""
    t = sections(b)
    out: dict[int, dict] = {}

    def ent(tgt, st):
        return out.setdefault(tgt, {"stream": st, "lea": [], "words": [], "pinned": False})

    for m in LEA.finditer(b, t[3]):
        tgt = m.start() + 2 + struct.unpack(">h", m.group(2))[0]
        st = _stream(b, tgt) or _short_lea(b, tgt)
        if st:
            ent(tgt, st)["lea"].append(m.start())
    for m in FLAG.finditer(b, t[3]):
        tgt = m.start() + 2 + struct.unpack(">h", m.group(1))[0] + 1
        st = _stream(b, tgt)
        if st:
            ent(tgt, st)["pinned"] = True
    p = (
        t[1] + 4
    )  # 자료 A 의 등장 메시지 슬롯(110 중 107 이 문안, 2026-09-05 실측 — 다른 자리는 오탐)
    v = struct.unpack(">H", b[p : p + 2])[0]
    st = _stream(b, v) if t[3] <= v < len(b) else None
    if st:
        ent(v, st)["words"].append(p)
    out.update({k: v2 for k, v2 in chain(b, out).items() if k not in out})
    return dict(sorted(out.items()))


def _has_kana(st: scene.Stream) -> bool:
    txt = b"".join(t.raw for t in st.tokens if t.kind == "text")
    n, i = 0, 0
    while i < len(txt) - 1:
        if scene.is_lead(txt[i]):
            try:
                ch = txt[i : i + 2].decode("cp932")
            except UnicodeDecodeError:
                return False
            n += "぀" <= ch <= "ヿ"
            i += 2
        else:
            i += 1
    return n >= 1


def _score(st) -> tuple[int, int, int]:
    """문안다움 — (가나 수, −잡음). 시작을 한 바이트 잘못 잡으면 기호(0x81··/0x87··)나 뜬금없는
    라틴 글자가 는다(「アギール」→「Aギール」 · 「２回」→「Q回」)."""
    txt = b"".join(t.raw for t in st.tokens if t.kind == "text")
    kana = noise = i = 0
    while i < len(txt) - 1:
        if scene.is_lead(txt[i]):
            try:
                ch = txt[i : i + 2].decode("cp932")
            except UnicodeDecodeError:
                return (0, 0, 0)
            kana += "぀" <= ch <= "ヿ"
            noise += txt[i] in (0x81, 0x84, 0x85, 0x86, 0x87) and not ("぀" <= ch <= "ヿ")
            i += 2
        else:
            noise += 0x41 <= txt[i] <= 0x5A or 0x61 <= txt[i] <= 0x7A  # ⚠ 반각 가나(0xA1~0xDF)는
            # 라틴-1 로는 글자로 보인다 — ASCII 만 센다
            i += 1
    return (kana, -noise, len(txt))  # 같으면 **더 긴 쪽**(=더 앞에서 시작한 쪽)을 고른다


def chain(b: bytes, known: dict[int, dict]) -> dict[int, dict]:
    """참조가 없는 스트림 — 아는 스트림 **끝 뒤로 이어지는 것** + **레코드 영역의 문안**.

    🔴 `lea`·자료 A 워드로만 찾으면 샌다(2026-09-06 실측: 전투 아카이브에 일본어 116런이 남아 있었다).
    시스템 메시지와 같은 기전이다 — `06` 은 끝이 아니라 「여기서 끼워 넣어라」라 그 뒤로 문안이
    이어지고(능력치 이름 꼬리+수치+‘내려갔다’ 꼬리), 보스 등장 문구는 **레코드 영역**에 들어 있다.
    참조를 모르니 **제자리에서만** 다시 쓴다(`plan_block` 이 길이를 넘기면 실패한다).

    ⚠ 시작 자리를 한 바이트 잘못 잡으면 「アギール」이 「Aギール」이 된다 — 후보 둘(패딩 바로 뒤 ·
    플래그 바이트 한 칸 뒤)을 **문안다움으로 견줘** 고른다.
    """
    t = sections(b)
    out: dict[int, dict] = {}

    def add(p: int) -> int | None:
        for q in (
            p - 1,
            p,
            p + 1,
        ):  # 이미 잡힌 자리면 손대지 않는다(한 바이트 어긋난 사본이 생긴다)
            e = known.get(q) or out.get(q)
            if e and q <= p < e["stream"].end:
                return e["stream"].end
        best = None
        for q in (p, p + 1):
            if q >= len(b):
                continue
            st = _stream(b, q)
            if not st or not _has_kana(st):
                continue
            sc = _score(st)
            if best is None or sc > best[0]:
                best = (sc, q, st)
        if best is None:
            return None
        _sc, q, st = best
        out[q] = {"stream": st, "lea": [], "words": [], "pinned": True}
        return st.end

    for q in range(2, t[1]):  # 레코드 영역 — FF 패딩 뒤(또는 플래그 바이트 뒤)가 문안이다
        if b[q - 1] == 0xFF and b[q] != 0xFF:
            add(q)
    for p0 in sorted({e["stream"].end for e in list(known.values()) + list(out.values())}):
        p = p0
        while p < len(b):
            while p < len(b) and b[p] == 0xFF:
                p += 1
            if p in known or p in out:
                break
            nxt = add(p)
            if nxt is None:
                break
            p = nxt
    return out


def jp_key(st: scene.Stream) -> str:
    return hashlib.sha1(b"".join(t.raw for t in st.tokens)).hexdigest()[:10]


def pos_key(st: scene.Stream, n: int, tgt: int) -> str:
    """자리를 가리는 열쇠 — 바이트가 같아도 뜻이 다른 스트림용(있으면 해시 열쇠를 이긴다).
    블록 93 「の 左」+goto 둘은 상대 goto 까지 바이트가 같은데 한쪽은 ‘…주문을 외웠다’, 다른 쪽은
    「…물어뜯었다」로 이어진다 — 해시 하나로는 둘을 못 가른다."""
    return f"{jp_key(st)}@{n}:{tgt:04x}"


def survey(d: bytes):
    names: dict[str, list] = {}
    strs: dict[str, dict] = {}
    for n, (_s, b, _e) in enumerate(blocks(d)):
        for r in records(b):
            names.setdefault(r["name"].decode("cp932", "replace"), []).append((n, r))
        for tgt, e in refs(b).items():
            st = e["stream"]
            x = strs.setdefault(jp_key(st), {"text": st.text(), "where": []})
            x["where"].append((n, tgt, st.end, e))
    return names, strs


def check(d: bytes) -> None:
    names, strs = survey(d)
    bases = {base_name(k) for k in names}
    got = (sum(len(v) for v in names.values()), len(bases), len(strs))
    print(
        f"  전투 블록 {COUNT} · 이름 {got[0]}(고유 {len(names)} · 기본 {got[1]})"
        f" · 스트림 고유 {got[2]} · 참조 {sum(len(v['where']) for v in strs.values())}"
    )
    if got != EXPECT:
        raise SystemExit(f"전투 분모가 갈렸다 {got} (기대 {EXPECT})")


# ── 정본 ───────────────────────────────────────────────────────────────────────



def _glossary(jp: str) -> str:
    for k in (
        jp,
        unicodedata.normalize("NFKC", jp),
        unicodedata.normalize("NFKC", jp).replace("・", ""),
    ):
        # 몬스터 이름 칸은 몬스터 범주가 먼저(カース: 카스 ≠ 아이템 커스)
        v = canon.lookup(k, "monster", "ed1") or canon.lookup(k, None, "ed1")
        if v:
            return v
    return ""


def monsters(d: bytes) -> dict:
    """{기본 JP 이름: {"ours": 한글}} — 정본(`shared/canon/nouns`)에서 읽는다. 게임 폴더에 표가 없다.
    못 찾는 이름은 넣지 않는다(`kr_name` 이 빌드를 세운다)."""
    names, _ = survey(d)
    out = {}
    for k in sorted({base_name(x) for x in names}):
        v = _glossary(k)
        if v:
            out[k] = {"ours": v}
    return out


def seed(d: bytes) -> None:
    _names, strs = survey(d)
    cm = json.loads(MAP_JSON.read_text(encoding="utf-8")) if MAP_JSON.exists() else {}
    out = common.OUT_DIR / "text"
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    for k, e in sorted(strs.items(), key=lambda kv: kv[1]["where"][0][:2]):
        cm.setdefault(k, {"ours": ""})
        w = e["where"]
        kind = (
            "pin"
            if any(x[3]["pinned"] for x in w)
            else ("lea" if any(x[3]["lea"] for x in w) else "word")
        )
        lines.append(f"{k}\t{len(w)}ref\t{kind}\t{w[0][0]:03d}@{w[0][1]:04x}\t{e['text']!r}")
    MAP_JSON.write_text(json.dumps(cm, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "battle.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"  {MAP_JSON}: {len(cm)} · 원문 {out / 'battle.txt'}")


# ── 재삽입 ─────────────────────────────────────────────────────────────────────


def _nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s).replace(" ", "")


def kr_name(jp: str, monsters: dict) -> str:
    """레코드/문안의 JP 이름 → 한글 (반각·전각을 같은 키로, 정본에 없으면 용어집). 접미 Ａ~Ｄ 는 반각으로."""
    base = base_name(jp)
    ent = monsters.get(base)
    if ent is None:
        key = _nfkc(base)
        ent = next((v for k, v in monsters.items() if _nfkc(k) == key), None)
    kr = ent.get("ours", "") if ent else (_glossary(base) or "")
    if not kr:
        raise SystemExit(f"battle: 몬스터 이름 정본이 없다 {base!r}")
    return kr + unicodedata.normalize("NFKC", suffix_of(jp))


def expand_names(text: str, monsters: dict) -> str:
    def rep(m):
        name = kr_name(m.group(1), monsters)
        return josa.attach(name, m.group(2)) if m.group(2) else name

    return NAME_TAG.sub(rep, text)


def drop_goto(st: scene.Stream, ours: str) -> scene.Stream:
    """우리 문안이 끝 코드로 닫히면 원문의 goto 를 버린 스트림 — 재삽입(`plan_block`)과 토큰 경계 게이트
    (`check_refs`)가 **같은 판단**을 쓰게 한 자리. 원문이 남의 스트림 한가운데로 goto 해 꼬리를 빌려 쓰는
    자리(블록 93 「の 左」→「の頭は…」)는 우리 글을 끝까지 제 글로 쓴다 — 옮겨진 스트림에선 상대 goto 가
    성립하지 않는다."""
    if re.search(r"<(00|06|07|0a)>$", ours) and any(t.ref == scene.GOTO for t in st.tokens):
        return dataclasses.replace(st, tokens=[t for t in st.tokens if t.ref != scene.GOTO])
    return st



# 블록 코드가 **외톨이 몬스터의 알파벳을 숨기려고** 이름 칸에 고정 주소로 06 을 쓴다 — `move.b #6,$FF1Exx.l`
# (13FC 0006 00FF xxxx). 쓰는 자리 = 몬스터 레코드가 복사된 배우 칸(`$FF1DBC`+n·0x40+0x30, 첫 레코드가 배우 4)의
# **원문 이름 길이**(알파벳 바로 자리)다. 우리 이름은 길이가 달라서, 길면 마지막 글자 한 바이트가 06 으로 덮여
# 한 칸이 빈 칸이 되고(「캐리온크롤러」→「캐리온크롤 A」, 10-09 쓰기 BP 로 잡음), 짧으면 알파벳이 안 숨는다.
# ⇒ 쓰는 자리를 **우리 알파벳 자리**(우리 이름 길이)로 옮긴다.
LETTER_HIDE = re.compile(rb"\x13\xfc\x00\x06\x00\xff(..)", re.S)
ACTOR0, ACTOR_REC, ACTOR_NAME = 4, 0x40, 0x30  # 첫 몬스터 레코드의 배우 번호 · 칸 크기 · 이름 오프셋


def letter_hide_sites(b: bytes) -> list[tuple[int, int, int]]:
    """[(명령 자리, 레코드 슬롯, 이름 안 오프셋)] — 배우 칸 범위 안의 것만."""
    out = []
    for m in LETTER_HIDE.finditer(b):
        a = 0xFF0000 + struct.unpack(">H", m.group(1))[0] - 0xFF1DBC
        if not 0 <= a < ACTOR_REC * 24:
            continue
        out.append((m.start(), (a - ACTOR_NAME) // ACTOR_REC - ACTOR0, (a - ACTOR_NAME) % ACTOR_REC))
    return out


def plan_block(b: bytes, n: int, textmap: dict, monsters: dict, encode) -> bytes | None:
    """블록 하나의 새 바이트(바뀐 게 없으면 None)."""
    out = bytearray(b)
    changed = False
    errs = []
    for r in records(b):
        jp = r["name"].decode("cp932", "replace")
        if not base_name(jp) in monsters:
            continue
        kr = kr_name(jp, monsters)
        enc = encode(kr)
        if len(enc) > r["cap"]:
            errs.append(f"블록 {n} 이름 {jp!r}→{kr!r} {len(enc)}B > {r['cap']}B")
            continue
        # 우리 이름이 짧으면 **원본 꼬리를 지운다** — 06 뒤라 화면엔 안 나오지만 원문 조각이 남는다
        # (2026-09-06 스캔에서 「ル連」「チＡ」 같은 꼬리가 23건 잡혔다).
        tail = len(r["name"]) - len(enc)
        out[r["name_at"] : r["name_at"] + len(enc) + 1] = enc + b"\x06"
        if tail > 0:
            out[r["name_at"] + len(enc) + 1 : r["name_at"] + len(r["name"]) + 1] = b"\x00" * tail
        changed = True
    # 알파벳 숨김 쓰기의 자리를 우리 이름 기준으로 — 원문과 맞지 않는 것(보스 등)은 건드리지 않는다
    by_slot = {(r["start"] - REC0) // REC_STEP: r for r in records(b)}
    for ins, slot, off in letter_hide_sites(b):
        r = by_slot.get(slot)
        if r is None:
            continue
        jp = r["name"].decode("cp932", "replace")
        if len(base_name(jp).encode("cp932")) != off or not base_name(jp) in monsters:
            continue
        enc = encode(kr_name(jp, monsters))
        new_off = len(enc) - len(encode(unicodedata.normalize("NFKC", suffix_of(jp))))
        new_addr = 0xFF1DBC + (slot + ACTOR0) * ACTOR_REC + ACTOR_NAME + new_off
        if new_addr != 0xFF1DBC + (slot + ACTOR0) * ACTOR_REC + ACTOR_NAME + off:
            out[ins + 6 : ins + 8] = struct.pack(">H", new_addr & 0xFFFF)
            changed = True
    moves = []
    rs = refs(b)
    # 새 문안 본문 — 번역 없는 스트림은 None
    bodies: dict[int, bytes | None] = {}
    for tgt, e in rs.items():
        st = e["stream"]
        ent = textmap.get(pos_key(st, n, tgt)) or textmap.get(jp_key(st))
        if not ent or not ent.get("ours"):
            bodies[tgt] = None
            continue
        ours = expand_names(ent["ours"], monsters)
        st = drop_goto(st, ours)
        bodies[tgt] = b"".join(t.raw for t in sysmsg._tokens_from_ours(st, ours, encode))
    # 🔴 스트림은 **물리적으로 이어서 흐른다** — `0A` 뒤에 바로 다음 스트림(참조 없는 연쇄)이 이어져 한 창 안에서
    # 「…독을 뿜었다. / …는 독에 중독됐다!」 로 읽힌다. 앞 스트림이 길어져 **옮겨지면** 연쇄가 끊겨 뒷 문안이 사라지고 쓰레기가
    # 그려진다(10-10 「조사 대신 쉼표」를 조사로 고치며 1B 가 늘어 처음 드러났다). 옮길 땐 이어지는 스트림을 **함께** 옮긴다.
    absorbed: set[int] = set()
    for tgt, e in rs.items():
        if tgt in absorbed:
            continue
        st = e["stream"]
        body = bodies[tgt]
        if body is None:
            continue
        span = st.end - tgt
        if len(body) <= span:
            out[tgt : tgt + span] = body + b"\x00" * (span - len(body))
        elif not (e["lea"] or e["words"]):
            errs.append(
                f"블록 {n} 스트림 {tgt:#x}: 제자리 {span}B 를 넘는데 참조를 모른다({len(body)}B)"
            )
            continue
        else:  # 플래그 바이트(tgt-1)는 제자리에 남는다 — 문안은 자료 A 워드·lea 로만 닿는다
            full, end = body, st.end
            members = [(tgt, e, 0)]  # (원래 자리, 항목, 옮긴 본문 안 오프셋)
            while end in rs and not (rs[end]["lea"] or rs[end]["words"]) and end not in absorbed:
                nxt = rs[end]
                nb = bodies.get(end)
                if nb is None:
                    nb = b[end : nxt["stream"].end]  # 번역 없는 연쇄는 원본 그대로
                absorbed.add(end)
                members.append((end, nxt, len(full)))
                full += nb
                end = nxt["stream"].end
            out[tgt:end] = b"\x00" * (end - tgt)
            moves.append((tgt, e, full))
        changed = True
    if errs:
        raise SystemExit("\n".join(errs))
    if moves:
        if len(out) & 1:
            out.append(0)
        placed = []
        for _tgt, e, body in moves:
            new = len(out)
            placed.append((new, e, body))
            out += body + (b"\x00" if len(body) & 1 else b"")
            for ins in e["lea"]:
                out[ins + 2 : ins + 4] = struct.pack(">h", new - (ins + 2))
            for p in e["words"]:
                out[p : p + 2] = struct.pack(">H", new)
        out[8:10] = struct.pack(">H", len(out))
        # 자기 검증 — 고친 변위·워드가 정확히 새 자리를 가리키고 거기 새 문안이 있다
        for new, e, body in placed:
            assert out[new : new + len(body)] == body
            for ins in e["lea"]:
                assert ins + 2 + struct.unpack(">h", out[ins + 2 : ins + 4])[0] == new, (
                    n,
                    hex(ins),
                )
            for p in e["words"]:
                assert struct.unpack(">H", out[p : p + 2])[0] == new, (n, hex(p))
    return bytes(out) if changed else None


if __name__ == "__main__":
    d = common.rom()
    if "--seed" in sys.argv:
        seed(d)
    else:
        check(d)
