"""전투 메시지를 **정본 → PS1 ED2** 에서 채운다(저본 순서 ① 정본 ed2 battle·system ② PS1 ED2 몬스터 대사 ③ md-ed1 같은 원문).

    python3 tools/fill_battle.py --stats    # 채울 수 있는 수
    python3 tools/fill_battle.py --apply    # `textmap/battle.json` 의 빈 `ours` 만 채운다(`src` 에 출처) + 못 맞춘 목록 work/review/fill_battle.txt

원문 키 = 스트림의 글자(NFKC, 공백·`･` 제거) + **이름 자리 `{name}`**(`<02>`·`<0b>`·`<09 nn>` 와 문안 속 몬스터·인물 이름). 정본 템플릿도 같은 꼴이라 맞대면 된다.
한국어는 템플릿의 `{name}` 을 원문 이름 자리(제어코드 태그 또는 `{JP이름}` 조사 태그)로 돌려놓는다. 병기 조사(`은(는)` 따위)는 **조사 훅**으로
(`<eb0p>` 배우 이름 뒤 · `<ebe0>` 이름 없이 조사로 시작하는 줄 · `{JP|은/는}` 문안 속 몬스터 이름 뒤).
"""

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import battle
import common
import scene

from shared import canon

PAIRS = {"은(는)": 0, "이(가)": 1, "을(를)": 2, "과(와)": 3, "으로(로)": 4}
PAIR_SLASH = {
    "은(는)": "은/는",
    "이(가)": "이/가",
    "을(를)": "을/를",
    "과(와)": "과/와",
    "으로(로)": "으로/로",
}
NAME_TAGS = {0x02, 0x0B}  # 이름 자리 코드(+ `09 nn`)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("%c%s%c", "{name}").replace("%d", "{n}").replace("%c", "")
    return re.sub(r"[\s･・]", "", s)


def names_index(d: bytes) -> list[str]:
    """문안 속에서 {name} 으로 볼 이름들 — 몬스터 기본 이름(정본에 있는 것)과 인물. 긴 것부터."""
    nm, _ = battle.survey(d)
    mons = {battle.base_name(k) for k in nm}
    persons = set(canon.nouns("ed2")["categories"].get("person", {}))
    allnames = sorted({*mons, *persons}, key=lambda x: (-len(x), x))
    return [n for n in allnames if len(n) >= 2]


def jp_template(st, names: list[str]):
    """(키, 슬롯[('tag', 원문 토큰 hex) | ('lit', JP 이름)], 앞 태그 문자열, 끝 태그 문자열) 또는 None(우리가 못 다루는 모양)."""
    parts: list[str] = []
    slots: list = []
    lead, trail = "", ""
    seen_text = False
    in_spk = False
    for t in st.tokens if hasattr(st, "tokens") else st:
        if in_spk:
            if t.kind == "text":
                parts.append("{name}")
                slots.append(("spk", t.raw.decode("cp932", "replace")))
                continue
            if t.code == 0x04:
                in_spk = False
                continue
            return None
        if t.code == 0x1E:
            in_spk = True
            seen_text = True
            continue
        if t.kind == "text":
            seen_text = True
            s = t.raw.decode("cp932", "replace")
            pos = 0
            while pos < len(s):
                hit = next((n for n in names if s.startswith(n, pos)), None)
                if hit:
                    parts.append("{name}")
                    slots.append(("lit", hit))
                    pos += len(hit)
                else:
                    parts.append(s[pos])
                    pos += 1
        elif t.kind == "end":
            trail += f"<{t.code:02x}>"
        elif t.kind == "eof":
            continue
        elif (
            t.ref == scene.CALL
        ):  # 화자 머리·이름을 부르는 하위 스트림 — 이름 자리로 본다(원문 호출 태그를 그대로 되살린다)
            parts.append("{name}")
            slots.append(("call", f"{t.code:02x}:{t.target:06x}"))
        elif t.ref:
            return None  # 이어지는 스트림(goto) — 이 도구는 못 다룬다
        elif t.code in NAME_TAGS or (t.code == 0x09 and len(t.raw) == 2):
            parts.append("{name}")
            slots.append(("tag", t.raw.hex()))
        elif t.code == 0x01:
            parts.append(" ")
        elif t.code in (0x08, 0x05):
            if not seen_text:
                lead += f"<{t.raw.hex()}>"
            else:
                parts.append(f"<{t.raw.hex()}>")
        else:
            return None
    return norm("".join(parts)), slots, lead, trail


def kr_to_ours(kr: str, slots: list, lead: str, trail: str) -> str | None:
    """정본 한국어 템플릿 → 정본 표기(`ours`)."""
    segs = re.split(r"\{name\}", kr)
    if len(segs) - 1 != len(slots):
        return None
    out = lead
    for i, seg in enumerate(segs):
        if i > 0:
            kind, val = slots[i - 1]
            pair = next((p for p in PAIRS if seg.startswith(p)), None)
            if kind in ("tag", "call"):
                out += f"<{val}>"
                if pair:
                    out += f"<eb{PAIRS[pair]:02x}>"
                    seg = seg[len(pair) :]
            elif kind == "spk":  # 화자 머리 `<1e>이름<04>` — 뒤의 줄바꿈은 `<01>`
                out += "<1e>{%s}<04>" % val
                if seg.startswith("\n"):
                    out += "<01>"
                    seg = seg[1:]
            else:  # 문안 속 이름
                if pair:
                    out += "{%s|%s}" % (val, PAIR_SLASH[pair])
                    seg = seg[len(pair) :]
                else:
                    out += "{%s}" % val
        elif i == 0:
            pair = next((p for p in PAIRS if seg.startswith(p)), None)
            if pair:  # 이름 없이 조사로 시작 — 마지막으로 이름을 그린 배우 기준 훅
                out += f"<ebe{PAIRS[pair]:x}>"
                seg = seg[len(pair) :]
        out += seg.replace("\n", " ")
    return out + trail


def sources() -> dict[str, tuple[str, str]]:
    """{정규화된 JP 열쇠: (KR 템플릿, 출처)} — ① 정본 ed2 battle·system ② PS1 ED2 몬스터 대사."""
    out: dict[str, tuple[str, str]] = {}
    for cat in ("battle", "system"):
        for jp, kr in canon.table(cat, "ed2").items():
            out.setdefault(norm(jp), (kr, f"canon:ed2:{cat}"))
    for jp, kr in ps1_jp_kr().items():
        out.setdefault(
            norm(jp), (kr.replace("%c%s%c", "{name}").replace("%c", ""), "ps1:ed2:ED2MON")
        )
    ps1 = common.ROOT / ".." / ".."  # 워크트리 → 본 트리
    for base in (common.ROOT, ps1.resolve()):
        p = base / "games" / "ps1-ed1+2" / "textmap" / "monster_lines_ed2.json"
        if not p.exists():
            p = (
                base
                / ".claude"
                / "worktrees"
                / "ps1-ed1+2"
                / "games"
                / "ps1-ed1+2"
                / "textmap"
                / "monster_lines_ed2.json"
            )
        if p.exists():
            for jp, kr in json.loads(p.read_text(encoding="utf-8")).items():
                if jp.startswith("_") or not isinstance(kr, str):
                    continue
                out.setdefault(norm(jp), (kr.replace("%c%s%c", "{name}"), "ps1:ed2:monster_lines"))
            break
    return out


PS1_CHILD = """
import os, sys, json, hashlib
sys.path.insert(0, '.')
os.environ.setdefault("LOCK_BYPASS", "1")
from common import extract
from ed2_monster_review import MON
here = {}
for g, (lba, size) in sorted(MON.items()):
    data = bytes(extract(lba, size))
    for part in data.split(b"\\x00"):
        if not (4 <= len(part) <= 1024):
            continue
        for k in range(len(part) - 3):
            try:
                t = part[k:].decode("cp932")
            except UnicodeDecodeError:
                continue
            here.setdefault(hashlib.sha1(t.encode()).hexdigest()[:10], t)
keys = json.load(open('../script/ED2MON_LINES.json', encoding='utf-8'))
print(json.dumps({here[k]: v for k, v in keys.items() if k in here and isinstance(v, str)}, ensure_ascii=False))
"""


def ps1_jp_kr() -> dict[str, str]:
    """{PS1 JP 문장: 한국어} — PS1 원본(ED2MON*.BIN)에서 PS1 도구로 JP 를 되살려 `ED2MON_LINES` 해시 열쇠와 잇는다.
    ⚠ 원문(JP)이라 **저장하지 않는다**(저작권) — 실행할 때마다 자식 프로세스로 읽는다. PS1 롬은 메인 트리의 `originals` 에서 읽는다."""
    import subprocess

    tools = common.ROOT.parents[2] / "games" / "ps1-ed1+2" / "tools"
    if not tools.exists():
        return {}
    r = subprocess.run(
        [sys.executable, "-c", PS1_CHILD], cwd=tools, capture_output=True, text=True, check=False
    )
    if r.returncode:
        raise SystemExit(f"PS1 도구 실행 실패: {r.stderr[-300:]}")
    return json.loads(r.stdout)


def ps1_table() -> dict[str, str]:
    """PS1 ED2 몬스터 대사표(`script/ED2MON_LINES.json`: PS1 JP 문장의 sha1 앞 10자 → 한국어, 자리표 `%c%s%c`)."""
    for base in (common.ROOT, common.ROOT.parents[2]):
        for rel in (
            ("games", "ps1-ed1+2", "script", "ED2MON_LINES.json"),
            (
                ".claude",
                "worktrees",
                "ps1-ed1+2",
                "games",
                "ps1-ed1+2",
                "script",
                "ED2MON_LINES.json",
            ),
        ):
            p = base.joinpath(*rel)
            if p.exists():
                return {
                    k: v
                    for k, v in json.loads(p.read_text(encoding="utf-8")).items()
                    if isinstance(v, str)
                }
    return {}


def ps1_variants(st: scene.Stream) -> list[str]:
    """MD 스트림을 PS1 JP 꼴(이름 자리 `%c%s%c`, 끝 `\\n`)로 옮긴 후보들 — PS1 키는 이 문자열의 sha1 이다."""
    parts = []
    for t in st.tokens:
        if t.kind == "text":
            parts.append(t.raw.decode("cp932", "replace"))
        elif t.kind == "end":
            parts.append("\0END")
        elif t.kind == "eof":
            continue
        elif t.ref:
            return []
        elif t.code in NAME_TAGS or (t.code == 0x09 and len(t.raw) == 2):
            parts.append("%c%s%c")
        elif t.code == 0x01:
            parts.append("\0NL")
        else:
            parts.append("")
    s = "".join(parts)
    out = []
    for end in ("", "\n"):
        for nl in ("", "\n", " "):
            for strip in (False, True):
                x = s.replace("\0END", end).replace("\0NL", nl)
                if strip:
                    x = x.replace(" ", "").replace("\u3000", "")
                if x not in out:
                    out.append(x)
    return out


APPEAR = re.compile(r"^(.+?)(?:と(.+?))?が現れた。$")
BATTLE = re.compile(r"^(.+?)との戦闘だ。$")
KANA = re.compile(r"[ぁ-んァ-ヴー一-龥]")


def appear_ours(st: scene.Stream, monsters: dict) -> str | None:
    """등장 문구 「Xが現れた。」·「XとYが現れた。」·「Xとの戦闘だ。」 — 이름이 문자열에 **박혀** 있어 PS1 처럼 정적으로 만든다
    (`{X|이/가}` 조사 태그가 이름 정본으로 받침을 고른다). 가나 앞의 제어 접두(데이터처럼 읽힌 바이트)는 원문 바이트 그대로."""
    pre, text, end = "", "", ""
    seen = False
    for t in st.tokens:
        if t.kind == "end":
            end = f"<{t.code:02x}>"
        elif t.kind == "eof":
            continue
        elif t.kind == "text" and not seen:
            s = t.raw.decode("cp932", "replace")
            m = KANA.search(s)
            if m:
                before = s[: m.start()].encode("cp932")
                if before:
                    pre += f"<{before.hex()}>"
                text += s[m.start() :]
                seen = True
            else:
                pre += f"<{t.raw.hex()}>"
        elif t.kind == "text":
            text += t.raw.decode("cp932", "replace")
        elif not seen:
            if t.ref:
                return None
            pre += f"<{t.raw.hex()}>"
        else:
            return None
    m = APPEAR.match(text)
    b = BATTLE.match(text)
    known = lambda n: bool(battle.base_name(n) in monsters or battle._glossary(battle.base_name(n)))  # noqa: E731, SLF001
    if m:
        a, c = m.group(1), m.group(2)
        if not known(a) or (c and not known(c)):
            return None
        body = ("{%s|과/와} {%s|이/가} 나타났다." % (a, c)) if c else ("{%s|이/가} 나타났다." % a)
    elif b:
        a = b.group(1)
        if not known(a):
            return None
        body = "{%s|과/와}의 전투다." % a
    else:
        return None
    return pre + body + end


def lookup(st_or_toks, names, src, PS1):
    """토큰열 하나 → (정본 표기 `ours`, 출처) 또는 (None, 이유)."""
    tpl = jp_template(st_or_toks, names)
    if tpl is None:
        return None, "형식 밖(goto·미지 제어코드)"
    key, slots, lead, trail = tpl
    s = src.get(key)
    if s is None and hasattr(st_or_toks, "tokens"):  # ② PS1 ED2 몬스터 대사표(해시 열쇠)
        for v in ps1_variants(st_or_toks):
            kr = PS1.get(hashlib.sha1(v.encode()).hexdigest()[:10])
            if kr is not None:
                s = (
                    kr.replace("%c%s%c", "{name}").replace("\n", " ").strip(),
                    "ps1:ed2:ED2MON_LINES",
                )
                break
    if s is None and key.startswith("{name}") and slots and slots[0][0] in ("tag", "call"):
        # 정본은 「は…」 꼴(이름 없이 조사부터)로 적힌 것이 많다 — 앞 이름 자리를 떼고 찾아 한국어 앞에 도로 붙인다
        t = src.get(key[len("{name}") :])
        if t is not None:
            s = ("{name}" + t[0], t[1])
    if s is None:
        return None, "정본·PS1 에 없음"
    ours = kr_to_ours(s[0], slots, lead, trail)
    if ours is None:
        return None, "이름 자리 수가 안 맞음"
    return ours, s[1]


SEP = {0x01: "<01>", 0x05: "<05>"}


def candidates(d: bytes):
    src = sources()
    PS1 = ps1_table()
    names = names_index(d)
    monsters = battle.monsters(d)
    _n, strs = battle.survey(d)
    hits, miss = [], []
    for k, e in strs.items():
        st = e["where"][0][3]["stream"]
        ap = appear_ours(st, monsters)
        if ap is not None:
            hits.append((k, ap, "ours:ed2-appear"))
            continue
        ours, why = lookup(st, names, src, PS1)
        if ours is not None:
            hits.append((k, ours, why))
            continue
        # 한 스트림이 여러 줄(`01`·`05` 로 갈린다)이면 **줄마다** 찾는다 — 정본은 창 한 줄 단위로 적혀 있다
        toks = [t for t in st.tokens if t.kind != "eof"]
        if not any(t.code in SEP for t in toks) or any(t.ref for t in toks):
            miss.append((k, why, st.text()))
            continue
        end = toks[-1] if toks and toks[-1].kind == "end" else None
        body = toks[:-1] if end else toks
        segs, seps, cur = [], [], []
        for t in body:
            if t.code in SEP and t.kind != "text":
                segs.append(cur)
                seps.append(SEP[t.code])
                cur = []
            else:
                cur.append(t)
        segs.append(cur)
        parts, srcs, ok = [], set(), True
        for sg in segs:
            if not sg:
                parts.append("")
                continue
            o, w = lookup(sg, names, src, PS1)
            if o is None:
                ok = False
                why = w + "(줄 단위)"
                break
            parts.append(o)
            srcs.add(w)
        if not ok:
            miss.append((k, why, st.text()))
            continue
        out = parts[0]
        for sep, pt in zip(seps, parts[1:], strict=True):
            out += sep + pt
        out += f"<{end.code:02x}>" if end else ""
        hits.append((k, out, "+".join(sorted(srcs))))
    return hits, miss


if __name__ == "__main__":
    d = common.rom()
    hits, miss = candidates(d)
    bpath = common.GAME_DIR / "textmap" / "battle.json"
    bm = json.loads(bpath.read_text(encoding="utf-8"))
    new = [(k, t, s) for k, t, s in hits if not bm.get(k, {}).get("ours")]
    print(
        f"  전투 메시지 {len(bm)} 중 정본·PS1 ED2 로 채울 것 {len(hits)}(빈 칸 {len(new)}) · 못 맞춤 {len(miss)}"
    )
    if "--apply" in sys.argv:
        for k, t, s in new:
            bm[k]["ours"] = t
            bm[k]["src"] = s
        bpath.write_text(json.dumps(bm, ensure_ascii=False, indent=1), encoding="utf-8")
        out = common.REVIEW_DIR / "fill_battle.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(f"{k}\t{why}\t{jp!r}" for k, why, jp in miss), encoding="utf-8")
        print(f"  채움 {len(new)} · 못 맞춘 목록 {out}")
