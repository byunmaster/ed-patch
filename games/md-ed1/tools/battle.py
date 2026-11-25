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


def dead_names(b: bytes) -> list[dict]:
    """사용 안 하는 슬롯(플래그 0x80)에 남은 이름 — `records()` 가 건너뛰는 4번째 자리의 잔재(블록 22·44·48·53·107).
    원문이 화면에 뜨진 않지만 「일본어 0」 점검(마스터 10-11)에 걸려 같은 규칙으로 덮는다. 원본 길이를 넘지 않게만 쓴다.
    [{name_at, name(bytes), term}] — term = 이름 바로 뒤가 06 인가(블록 107 은 구역 끝이라 아니다)."""
    t = sections(b)
    seen = {r["name_at"] for r in records(b)}
    out = []
    for m in archives.SJIS_RUN.finditer(b[: t[1]]):
        s_, e_ = m.start(), m.end()
        if s_ in seen or s_ < REC0:
            continue
        try:
            jp = b[s_:e_].decode("cp932")
        except UnicodeDecodeError:
            continue
        if not SUFFIX.search(jp):
            continue
        out.append({"name_at": s_, "name": b[s_:e_], "term": b[e_ : e_ + 1] == b"\x06"})
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
    _fill_ascii_suffix(d, out)
    return out


_ASCII_SFX: set[str] = set()  # 전각 접미가 이름 칸(레코드 cap · 빈 슬롯 원본 길이)에 안 드는 몬스터(원문 기본 이름)


def _fill_ascii_suffix(d: bytes, mons: dict) -> None:
    _ASCII_SFX.clear()
    for _s, b, _e in blocks(d):
        cells = [(r["name"], r["cap"]) for r in records(b)] + [
            (x["name"], len(x["name"])) for x in dead_names(b)
        ]
        for nm, cap in cells:
            jp = nm.decode("cp932", "replace")
            sfx = suffix_of(jp)
            if not sfx or sfx in "ABCD" or unicodedata.normalize("NFKC", sfx) not in FULLWIDTH_LETTER:
                continue
            base = base_name(jp)
            ent = mons.get(base)
            kr = ent["ours"] if ent else _glossary(base) or ""
            if kr and _bytes_len(kr) + 2 > cap:
                _ASCII_SFX.add(base)


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


def _bytes_len(s: str) -> int:
    """엔진 글자 코드 바이트 수 — 한글·전각은 2B, ASCII 는 1B."""
    return sum(2 if ord(c) > 0x7F else 1 for c in s)


FULLWIDTH_LETTER = {c: chr(0xFF21 + i) for i, c in enumerate("ABCD")}  # A→Ａ …


def kr_base(jp: str, monsters: dict) -> str:
    """JP 이름 → 한글 기본 이름(접미 제외)."""
    base = base_name(jp)
    ent = monsters.get(base)
    if ent is None:
        key = _nfkc(base)
        ent = next((v for k, v in monsters.items() if _nfkc(k) == key), None)
    kr = ent.get("ours", "") if ent else (_glossary(base) or "")
    if not kr:
        raise SystemExit(f"battle: 몬스터 이름 정본이 없다 {base!r}")
    return kr


def suffix_used(jp: str, monsters: dict) -> str:
    """이름 끝 접미 — **원판과 같은 글리프**(마스터 11-08 「원본 ABCD로」): 원문이 전각 Ａ~Ｄ 면 전각, 반각 ASCII A~D 면(반각 가나 이름) 반각.
    이름 칸 15B 에 전각 둘이 안 드는 이름(자이언트에이프 14B+2B)만 반각으로 둔다(이름 시작을 앞당기는 길은 엔진 읽기 자리가 많아 보류)."""
    sfx = suffix_of(jp)
    if not sfx:
        return ""
    if sfx in "ABCD":
        return sfx  # 원문 반각 — 그대로
    letter = unicodedata.normalize("NFKC", sfx)
    if letter not in FULLWIDTH_LETTER:
        return letter  # ♀♂ 등
    if base_name(jp) in _ASCII_SFX:
        return letter
    return sfx  # 원문 전각


def kr_name(jp: str, monsters: dict) -> str:
    """레코드/문안의 JP 이름 → 한글 (반각·전각을 같은 키로, 정본에 없으면 용어집). 접미 Ａ~Ｄ 는 원판처럼 전각(칸이 모자란 이름만 반각)."""
    return kr_base(jp, monsters) + suffix_used(jp, monsters)


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


# 소환 알파벳 쓰기 — 「동료를 불렀다」 블록(22·48·53)이 빈 슬롯(플래그 0x80) 이름의 **끝 알파벳**을 소환 횟수로 바꾼다:
# `addi.b #imm,d0`(imm = 전각 Ａ 둘째 바이트 0x60 + 오프셋) → `move.b d0,disp(a2)`(0x1540 + 변위 워드). 변위 = 빈 슬롯 레코드
# 시작 + disp 가 **원문 이름 마지막 바이트**다. 우리 이름은 길이가 다르고 알파벳이 ASCII(Ａ=0x41)라, 그대로 두면
# ① 짧은 이름(블록 22 「카스A」 5B)은 알파벳이 06 뒤에 써져 소환된 것도 「A」로 남고 ② 12B 이름(블록 48)은 0x60+ 값(「`」·a·b)이 찍힌다
# (sfc-ed2 가 같은 부류를 찾아 알려 줬다 10-24). ⇒ 변위를 우리 알파벳 자리로, imm 을 0x1F 낮춰 ASCII 알파벳으로 맞춘다.
# 원문에서도 마지막 바이트를 안 가리키는 자리(블록 53: 빈 슬롯 이름 10B 인데 +0xB)는 원판과 같게 둔다.
SUMMON_LETTER = re.compile(rb"\x06\x00\x00([\x5f-\x68])(?:(?!\x06\x00\x00).){0,32}?\x15\x40\x00([\x30-\x3f])", re.S)
ASCII_FROM_FULLWIDTH = 0x1F  # 전각 Ａ 둘째 바이트 0x60 → ASCII Ａ 0x41


def dead_slot_starts(b: bytes) -> list[int]:
    t = sections(b)
    out, p = [], REC0
    while p + NAME_AT < t[1]:
        if b[p] & 0x80:
            out.append(p)
        p += REC_STEP
    return out


def summon_letter_sites(b: bytes) -> list[tuple[int, int, int, int, dict]]:
    """[(addi 자리, imm, move 자리, disp, 빈 슬롯 이름 dict)] — 쓰는 자리가 빈 슬롯 이름의 마지막 바이트인 것만."""
    deads = dead_names(b)
    starts = dead_slot_starts(b)
    out = []
    for m in SUMMON_LETTER.finditer(b, sections(b)[3]):
        imm, disp = m.group(1)[0], m.group(2)[0]
        for p in starts:
            for d in deads:
                if p + disp == d["name_at"] + len(d["name"]) - 1 and p <= d["name_at"] < p + REC_STEP:
                    out.append((m.start(), imm, m.end() - 4, disp, d))
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
    for r in dead_names(b):
        jp = r["name"].decode("cp932")
        if base_name(jp) not in monsters:
            continue
        enc = encode(kr_name(jp, monsters))
        if len(enc) > len(r["name"]):
            errs.append(f"블록 {n} 빈 슬롯 이름 {jp!r} {len(enc)}B > {len(r['name'])}B")
            continue
        at = r["name_at"]
        out[at : at + len(r["name"])] = enc + b"\x00" * (len(r["name"]) - len(enc))
        if r["term"]:
            out[at + len(enc)] = 0x06
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
        new_off = len(enc) - len(encode(suffix_used(jp, monsters)))
        new_addr = 0xFF1DBC + (slot + ACTOR0) * ACTOR_REC + ACTOR_NAME + new_off
        if new_addr != 0xFF1DBC + (slot + ACTOR0) * ACTOR_REC + ACTOR_NAME + off:
            out[ins + 6 : ins + 8] = struct.pack(">H", new_addr & 0xFFFF)
            changed = True
    # 소환 알파벳 쓰기의 자리·값을 우리 이름 기준으로(위 SUMMON_LETTER 설명)
    for addi, imm, mv, disp, d in summon_letter_sites(b):
        jp = d["name"].decode("cp932", "replace")
        if base_name(jp) not in monsters:
            continue
        enc = encode(kr_name(jp, monsters))
        full = len(enc) >= 2 and enc[-2] == 0x82 and 0x60 <= enc[-1] <= 0x63  # 원판 글리프(전각 Ａ~Ｄ) — 둘째 바이트를 쓴다
        if not (full or (len(enc) >= 1 and 0x41 <= enc[-1] <= 0x44)):
            errs.append(f"블록 {n} 소환 슬롯 이름 {jp!r} 의 끝이 알파벳이 아니다")
            continue
        start = REC0 + ((d["name_at"] - REC0) // REC_STEP) * REC_STEP
        new_disp = d["name_at"] + len(enc) - 1 - start
        out[addi + 3] = imm if full else imm - ASCII_FROM_FULLWIDTH
        out[mv + 3] = new_disp
        changed = True
    moves = []
    jumps = []  # 참조를 몰라 못 옮기는 스트림 — 제자리엔 goto 만 두고 본문은 블록 끝으로(sysmsg.TAIL_JUMP 와 같은 기전)
    rs = refs(b)
    # 새 문안 본문 — 번역 없는 스트림은 None
    bodies: dict[int, bytes | None] = {}
    btoks: dict[int, list] = {}  # 새 문안의 토큰 — 문안 한복판을 겨냥한 쓰기 자리를 옮길 때 쓴다
    newpos: dict[int, int] = {}  # 스트림 시작(원본) → 새 몸이 놓인 자리
    for tgt, e in rs.items():
        st = e["stream"]
        ent = textmap.get(pos_key(st, n, tgt)) or textmap.get(jp_key(st))
        if not ent or not ent.get("ours"):
            bodies[tgt] = None
            continue
        ours = expand_names(ent["ours"], monsters)
        st = drop_goto(st, ours)
        btoks[tgt] = list(sysmsg._tokens_from_ours(st, ours, encode))
        bodies[tgt] = b"".join(t.raw for t in btoks[tgt])
    # 🔴 스트림은 **물리적으로 이어서 흐른다** — `0A` 뒤에 바로 다음 스트림(참조 없는 연쇄)이 이어져 한 창 안에서
    # 「…독을 뿜었다. / …는 독에 중독됐다!」 로 읽힌다. 앞 스트림이 길어져 **옮겨지면** 연쇄가 끊겨 뒷 문안이 사라지고 쓰레기가
    # 그려진다(10-10 「조사 대신 쉼표」를 조사로 고치며 1B 가 늘어 처음 드러났다). 옮길 땐 이어지는 스트림을 **함께** 옮긴다.
    absorbed: set[int] = set()
    moved_heads: dict[int, list] = {}
    for tgt, e in rs.items():
        if tgt in absorbed:
            continue
        st = e["stream"]
        body = bodies[tgt]
        if body is None:
            continue
        span = st.end - tgt
        # 🔴 바로 뒤에 참조 없는 연쇄 스트림이 이어지는데(「…민첩성이 <1e>07」+「<04>내려가고 말았다」, 「…뿜었다.<0a>」+「…중독됐다」) 우리
        # 문안이 **더 짧으면** 제자리에 쓰고 0 으로 메우는 순간 연쇄가 끊겨 꼬리가 사라진다(10-20 qa 「…민첩성이」에서 끝남) —
        # 그런 머리는 연쇄와 **함께 옮긴다**(아래 else 갈래).
        chain_next = st.end in rs and not (rs[st.end]["lea"] or rs[st.end]["words"])
        if chain_next and len(body) < span and not (e["lea"] or e["words"]):
            # 🔴 머리도 **참조 없는 사슬 스트림**(pinned — 블록 53 「…민첩성이 <06>」)이면 제자리에서 0 으로 메우는 순간 06 과 꼬리 사이에 00 이 끼어
            # 「세리오스의 민첩성이 1」에서 끝난다(꼬리 「떨어졌다!!」 증발, 구조 대조 10-22 · 하네스 실측). 사슬 전체를 **붙여서** 제자리에 쓴다 —
            # 남는 0 은 사슬 맨 끝(끝 코드 뒤)으로 간다. 꼬리의 옛 자리는 참조가 없어(이어 읽기로만 닿는다) 비워도 된다.
            group = [(tgt, body)]
            gend = st.end
            while gend in rs and not (rs[gend]["lea"] or rs[gend]["words"]) and gend not in absorbed:
                nb = bodies.get(gend)
                if nb is None:
                    nb = b[gend : rs[gend]["stream"].end]  # 번역 없는 꼬리는 원본 그대로
                group.append((gend, nb))
                gend = rs[gend]["stream"].end
            full = b"".join(x for _p, x in group)
            if len(full) <= gend - tgt:
                out[tgt:gend] = full + b"\x00" * (gend - tgt - len(full))
                off = 0
                for pos, x in group:
                    newpos[pos] = tgt + off
                    off += len(x)
                    if pos != tgt:
                        absorbed.add(pos)
                changed = True
                continue
        if len(body) <= span and not (chain_next and len(body) < span and (e["lea"] or e["words"])):
            out[tgt : tgt + span] = body + b"\x00" * (span - len(body))
            newpos[tgt] = tgt
        elif not (e["lea"] or e["words"]) and span >= 3:
            out[tgt : tgt + span] = b"\x0f\x00\x00" + b"\x00" * (span - 3)
            jumps.append((tgt, st.end, body))
        elif not (e["lea"] or e["words"]):
            errs.append(
                f"블록 {n} 스트림 {tgt:#x}: 제자리 {span}B 를 넘는데 참조를 모른다({len(body)}B)"
            )
            continue
        else:  # 플래그 바이트(tgt-1)는 제자리에 남는다 — 문안은 자료 A 워드·lea 로만 닿는다
            full, end = body, st.end
            members = [(tgt, e, 0)]  # (원래 자리, 항목, 옮긴 본문 안 오프셋)
            moved_heads[tgt] = members
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
    if jumps:
        if len(out) & 1:
            out.append(0)
        for tgt, end, body in jumps:
            new = len(out)
            newpos[tgt] = new
            out[tgt + 1 : tgt + 3] = struct.pack(">h", new - (tgt + 1))
            if body[-1] == 0x0A:  # 0A 은 물리적으로 다음 스트림으로 흐른다 — 원래 끝으로 되돌아간다
                here = new + len(body)
                body += b"\x0f" + struct.pack(">h", end - (here + 1))
            out += body + (b"\x00" if len(body) & 1 else b"")
        out[8:10] = struct.pack(">H", len(out))
    if moves:
        if len(out) & 1:
            out.append(0)
        placed = []
        for _tgt, e, body in moves:
            new = len(out)
            for orig_at, _ent, off in moved_heads[_tgt]:
                newpos[orig_at] = new + off
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
    # 🔴 블록 코드가 **문안 한복판**의 제어 바이트(개행 01·종결 07)를 런타임에 덮어쓰는 자리(`lea d(pc),aN` → `move.b …,(aN)`) —
    # 원판에선 그 바이트가 문안 안에 있지만 우리 문안은 길이가 달라 그 오프셋에 다른 글자가 온다(블록 89 「하이아길도」의 「아」 뒷바이트
    # 0xDA 가 01 로 덮여 「하이 길도」, 블록 67 은 옮겨 간 문안 대신 0 패딩에 써서 「게다가 임프도 함께다!!」 누락, 10-20).
    # 원본 문안의 n번째 같은 제어 토큰을 우리 문안의 n번째 같은 토큰으로 이어 변위를 다시 쓴다.
    for ins, tgt0, k, raw in mid_stream_writes(b, rs):
        if tgt0 not in newpos or tgt0 not in btoks:
            continue  # 안 바뀐 스트림 — 원본 그대로
        at, seen = newpos[tgt0], 0
        for t in btoks[tgt0]:
            if t.raw == raw:
                if seen == k:
                    break
                seen += 1
            at += len(t.raw)
        else:
            errs.append(f"블록 {n} 쓰기 자리 {ins:#x}: 새 문안에 {raw.hex()} 토큰 {k + 1}번째가 없다")
            continue
        disp = at - (ins + 2)
        assert -0x8000 <= disp < 0x8000
        out[ins + 2 : ins + 4] = struct.pack(">h", disp)
        changed = True
    # 🔴 스트림 안의 `10`(call)·`0F`(goto) 는 **토큰 자리 기준 16비트 상대 변위**다 — 원본 토큰을 그대로 쓰면 문안 길이가 달라지거나
    # 스트림이 옮겨졌을 때 변위가 틀어진다(블록 42: 화자 【아크담】 call 둘이 빠지고 도망 갈래에 쓰레기 글자, 최후 대사 화자 call 이
    # 블록 밖을 가리켰다, 10-20 style 검수). 새 토큰 자리 기준으로 다시 쓴다. 목적지가 옮겨졌으면 새 자리.
    for tgt0, e in rs.items():
        toks = btoks.get(tgt0, e["stream"].tokens)
        at = newpos.get(tgt0, tgt0)
        for t in toks:
            if t.ref in (scene.CALL, scene.GOTO) and len(t.raw) == 3:
                dest = newpos.get(t.target, t.target)
                for s0, e2 in rs.items():  # 목적지가 바뀐 문안의 한복판이면 이을 수 없다
                    if s0 < t.target < e2["stream"].end and (s0 in btoks or newpos.get(s0, s0) != s0):
                        errs.append(f"블록 {n} {t.ref} {at:#x} → {t.target:#x} 가 바뀐 스트림 {s0:#x} 한복판")
                        break
                disp = dest - (at + 1)
                assert -0x8000 <= disp < 0x8000
                if out[at + 1 : at + 3] != struct.pack(">h", disp):
                    out[at + 1 : at + 3] = struct.pack(">h", disp)
                    changed = True
            at += len(t.raw)
    # 🔴 몬스터 슬롯 넷(`REC0`+k·0x40, k=0..3)의 **+3 바이트** — 전투 시작 때 게임이 슬롯 넷의 +3 에서 최솟값을 구해 모든 슬롯에서 뺀다
    # (`$2105C`: 최소인 슬롯은 0 이 된다). 기록 영역(`t[1]` 까지)에 문안 스트림이 끼어 있는 블록(108·109 등 보스)은 **그 스트림의 글자 바이트가
    # 가짜 슬롯의 +3** 이라, 스트림을 끝으로 옮기며 원자리를 0 으로 채우거나 제자리에 새 문안(제어 바이트 04 등)을 쓰면 최솟값이 0·4 로 내려가
    # 진짜 슬롯의 +3(0x10)이 0 으로 안 내려간다. 그러면 그림 타일 번호 계산(`$23B62`: +3≠0 이면 `$FF346C` 자료의 타일 수/0xA0 을 더한다)이 갈려
    # 아그니쟈 그림이 줄무늬로 깨졌다(10-24 mednafen 에서 재현). ⇒ 비워 둔 원자리는 원문 바이트로 되돌리고, 그래도 정규화한 값이 원판과 다르면
    # **진짜 슬롯의 +3 을 같은 만큼 옮긴다**(정규화 = 값 − 최솟값 이라 같은 만큼 옮기면 같다).
    slots = [REC0 + k * REC_STEP + 3 for k in range(4) if REC0 + k * REC_STEP + 3 < len(b)]
    for q in slots:
        if out[q] == 0 and b[q] != 0:  # 비워 둔 원자리만(제자리에 새 문안을 쓴 자리는 우리 글자 바이트 — 그대로)
            out[q] = b[q]
            changed = True
    real = [q for q in slots if not b[q - 3] & 0x80]  # 진짜 슬롯(플래그 bit7 없음)
    fake = [q for q in slots if q not in real]
    if real and fake:
        mo, mk = min(b[q] for q in slots), min(out[q] for q in slots)
        if any(b[q] - mo != out[q] - mk for q in real):
            delta = min(out[q] for q in fake) - mo
            for q in real:
                out[q] = b[q] + delta
            changed = True
    if errs:
        raise SystemExit("\n".join(errs))
    return bytes(out) if changed else None


def mid_stream_writes(b: bytes, rs: dict[int, dict]) -> list[tuple[int, int, int, bytes]]:
    """원본 블록에서 `lea d(pc),aN` 의 대상이 **스트림 한복판의 제어 토큰**인 자리 → [(명령 자리, 스트림 시작, 같은 토큰 중 n번째, 토큰 바이트)]."""
    out = []
    for m in re.finditer(rb"([\x41\x43\x45\x47\x49\x4b\x4d])\xfa(..)", b, re.DOTALL):
        i = m.start()
        t = i + 2 + struct.unpack(">h", m.group(2))[0]
        for s0, e in rs.items():
            st = e["stream"]
            if not (s0 < t < st.end):
                continue
            pos = s0
            same: dict[bytes, int] = {}
            for tk in st.tokens:
                if pos == t and tk.kind in ("ctl", "end") and len(tk.raw) == 1:
                    out.append((i, s0, same.get(tk.raw, 0), tk.raw))
                    break
                same[tk.raw] = same.get(tk.raw, 0) + 1
                pos += len(tk.raw)
            break
    return out


def _skeleton(st: scene.Stream) -> list[tuple[str, int]]:
    """번역돼도 변하지 않는 골격 — 화자 표지(1E)·그 닫는 04·끝 코드. (개행·페이지 수는 번역이 바꾼다.)"""
    return [(t.kind, t.code) for t in st.tokens if t.kind == "end" or t.code in (0x1E, 0x04)]


def verify_calls(orig: bytes, new: bytes) -> int:
    """게이트 — 전투 블록 스트림 안의 call(`10`)·goto(`0F`)가 우리 롬에서도 **원판과 같은 골격의 스트림**(번역돼 옮겨졌으면 그 새 자리)을
    가리키는가. 원 스트림 → 새 스트림은 lea·자료 A 워드(재배치가 고쳐 주는 참조)를 따라 짝짓는다. 변위를 원본 그대로 두면 블록 42 처럼
    착지가 엉뚱한 자리(화자 call 이 블록 밖)로 간다. → 검사한 call/goto 수."""
    n_ok = 0
    for n, ((_s, jb, _e), (_s2, kb, _e2)) in enumerate(zip(blocks(orig), blocks(new), strict=True)):
        jr = refs(jb)

        def new_start(e):
            if e["lea"]:
                i = e["lea"][0]
                return i + 2 + struct.unpack(">h", kb[i + 2 : i + 4])[0]
            if e["words"]:
                return struct.unpack(">H", kb[e["words"][0] : e["words"][0] + 2])[0]
            return None

        for tgt, e in jr.items():
            calls = [t for t in e["stream"].tokens if t.ref in (scene.CALL, scene.GOTO)]
            if not calls:
                continue
            ns = new_start(e)
            if ns is None:
                continue
            try:
                nst = scene.parse_stream(kb, ns)
            except (ValueError, IndexError):
                raise SystemExit(f"블록 {n} 스트림 {tgt:#x}: 새 롬 {ns:#x} 가 안 풀린다") from None
            ncalls = [t for t in nst.tokens if t.ref in (scene.CALL, scene.GOTO)]
            if [t.ref for t in calls] != [t.ref for t in ncalls]:
                continue  # drop_goto 로 goto 를 버린 스트림 — 우리 문안은 끝 코드로 닫힌다
            for t, nt in zip(calls, ncalls, strict=True):
                n_ok += 1
                if t.target in jr:  # 원판 착지가 문안 스트림 — 새 착지가 같은 골격이어야 한다
                    want = _skeleton(jr[t.target]["stream"])
                    try:
                        got = _skeleton(scene.parse_stream(kb, nt.target))
                    except (ValueError, IndexError):
                        got = None
                    if got != want:
                        raise SystemExit(
                            f"블록 {n} 스트림 {tgt:#x}→{ns:#x} 의 {t.ref}: 착지 {nt.target:#x} 의 골격이 원판 "
                            f"{t.target:#x} 와 다르다"
                        )
    return n_ok


def verify_mid_writes(orig: bytes, new: bytes) -> int:
    """게이트 — 원판에서 블록 코드가 스트림 한복판 제어 바이트에 쓰는 자리가 우리 롬에서도 **같은 값의 제어 바이트**를 가리키는가.
    (글자 뒷바이트나 0 패딩을 가리키면 「하이 길도」(블록 89)·문장 누락(블록 67)이 된다.) → 검사한 자리 수."""
    n_sites = 0
    for n, ((_s, jb, _e), (_s2, kb, _e2)) in enumerate(zip(blocks(orig), blocks(new), strict=True)):
        for ins, _s0, _k, raw in mid_stream_writes(jb, refs(jb)):
            n_sites += 1
            t = ins + 2 + struct.unpack(">h", kb[ins + 2 : ins + 4])[0]
            if kb[t : t + 1] != raw:
                raise SystemExit(
                    f"블록 {n} 쓰기 자리 {ins:#x} 가 우리 롬에서 제어 바이트 {raw.hex()} 를 안 가리킨다 "
                    f"(@{t:#x} = {kb[t : t + 1].hex()}) — 블록 코드가 문안 글자를 덮어쓴다"
                )
    return n_sites


def verify_summon_letters(orig: bytes, new: bytes) -> int:
    """게이트 — 소환 알파벳 쓰기가 우리 롬에서 **우리 빈 슬롯 이름의 ASCII 알파벳 자리**를 가리키고 값이 A·B·C·D 로 이어지는가. → 검사한 자리 수."""
    n_sites = 0
    for n, ((_s, jb, _e), (_s2, kb, _e2)) in enumerate(zip(blocks(orig), blocks(new), strict=True)):
        for addi, imm, mv, disp, d in summon_letter_sites(jb):
            n_sites += 1
            start = REC0 + ((d["name_at"] - REC0) // REC_STEP) * REC_STEP
            at = d["name_at"]  # 이름은 제자리 — 새 이름은 같은 자리에서 06 또는 00 까지
            end = min(i for i in range(at, at + 17) if kb[i] in (0x06, 0x00))
            nm = kb[at:end]
            last = at + len(nm) - 1
            if start + kb[mv + 3] != last:
                raise SystemExit(
                    f"블록 {n} 소환 알파벳 쓰기 {mv:#x} 가 이름 끝({last - start:#x})이 아니라 {kb[mv + 3]:#x} 를 가리킨다"
                )
            full = len(nm) >= 2 and nm[-2] == 0x82 and 0x60 <= nm[-1] <= 0x63
            ok = kb[addi + 3] == imm if full else (kb[addi + 3] == imm - ASCII_FROM_FULLWIDTH and 0x41 <= nm[-1] <= 0x44)
            if not ok:
                raise SystemExit(f"블록 {n} 소환 알파벳 값이 알파벳으로 이어지지 않는다 ({kb[addi + 3]:#x})")
    return n_sites


def verify_slot_plus3(orig: bytes, new: bytes) -> int:
    """게이트 — 진짜 몬스터 슬롯의 +3 을 게임이 정규화(값 − 슬롯 넷의 최솟값)한 결과가 원판과 같은가(위 plan_block 주석). → 검사한 블록 수."""
    n_ok = 0
    for n, ((_s, jb, _e), (_s2, kb, _e2)) in enumerate(zip(blocks(orig), blocks(new), strict=True)):
        qs = [REC0 + k * REC_STEP + 3 for k in range(4) if REC0 + k * REC_STEP + 3 < len(jb)]
        mo, mk = min(jb[q] for q in qs), min(kb[q] for q in qs)
        for q in qs:
            if jb[q - 3] & 0x80:
                continue  # 가짜(안 쓰는) 슬롯
            if jb[q] - mo != kb[q] - mk:
                raise SystemExit(
                    f"블록 {n} 슬롯 +3({q:#x}) 정규화 값이 원판 {jb[q] - mo:#x} → {kb[q] - mk:#x} — 보스 그림 타일 계산이 틀어진다 "
                    f"[원판 {[hex(jb[x]) for x in qs]} / 새 {[hex(kb[x]) for x in qs]}]"
                )
        n_ok += 1
    return n_ok


if __name__ == "__main__":
    d = common.rom()
    if "--seed" in sys.argv:
        seed(d)
    else:
        check(d)
