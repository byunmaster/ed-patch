#!/usr/bin/env python3
"""번역 정본 — 사전을 붙이고, 남은 걸 검토표로 내고, 번역을 받아 넣는다.

    tools/translate.py seed [--dict …]    사전(JP 원문→우리 문안)을 정본에 자동 반영
    tools/translate.py stat               지금 얼마나 덮였나
    tools/translate.py fit                번역이 원래 자리에 들어가나(재삽입 전략)
    tools/translate.py payload [--n 200]  아직 안 된 것 중 「사람이 볼 값어치」 순으로 검토표
    tools/translate.py apply <검토표…>    검토표의 「번역」을 정본에 넣는다

## 무엇이 정본인가

`games/pc98-ed1/script/scn.json` — **열쇠(JP 원문 sha1) → 우리 문안**. 커밋된다.
🔴 **JP 원문은 안 담는다**(루트 「저작권」). 원문은 `work/derived/` 에만 있고 열쇠는
`shared/text/line_key.py` 가 만든다 — 그래서 정본만 봐서는 원문을 복원할 수 없다.

⚠ **열쇠는 위치가 아니라 원문**이다. 덤프의 `k`/`o`(트랙·오프셋)를 키로 쓰면 재삽입 단위를
세우다 오프셋이 한 번만 밀려도 번역이 통째로 어긋난다. 원문 해시면 **덤퍼를 고쳐도 산다.**

## 왜 사전이 먼저인가

같은 팔콤 원문을 여러 이식판이 나눠 갖는다. `games/ps1-ed1+2/line_dict.json` 이 그
창구고(PS1 이 만들고 새턴이 읽는다), **PC-98 이 셋째 소비자**다. 우리가 PS1 에서 이미
번역한 대사를 여기서 다시 번역하면 **같은 대사가 두 벌로 갈린다** — 새턴에서 실제로
겪었다(파일럿 35줄 중 24가 그 경우, `shared/text/line_key.py`).

⚠ 사전이 덮는 건 하한선이다 — 1989 원작과 1998 리메이크는 문안 자체가 다른 데가 있다.
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
import reuse
from text.line_key import key as line_key

SCRIPT = common.ROOT / "games" / "pc98-ed1" / "script" / "scn.json"
DICT = common.ROOT / "games" / "ps1-ed1+2" / "line_dict.json"
PAYLOAD_DIR = common.REVIEW_DIR / "translate"

# 덤프에는 코드가 SJIS 로 잘못 읽힌 잡음이 섞여 있다(`dump_scn.py` 머리말 — 옵코드를 안
# 따라가고 「텍스트로 보이는 최대 구간」을 뜬다). 사람에게 보일 땐 걸러야 한다.
_NFKC = None
_KANA = re.compile(r"[ぁ-んァ-ヶー]")
_JA = re.compile(r"[ぁ-んァ-ン一-龥、。！？「」…ー]")
_NOISE = re.compile(r"[｡-ﾟ]")  # 반각 가나 — 코드가 이렇게 읽히는 게 대부분이다


def blocks() -> list[dict]:
    """덤프 넷을 한 줄로 이어 읽는다 — `reuse.pc98_lines()` 와 같은 자리를 본다."""
    out = []
    for name in ("scn_jp/scenario", "scn_jp/combat", "sys_jp/event", "sys_jp/program"):
        path = common.OUT_DIR / f"{name}.json"
        if not path.exists():
            raise SystemExit(f"덤프가 없다: {path}\n  tools/dump_scn.py · dump_sys.py 를 먼저.")
        for b in json.loads(path.read_text(encoding="utf-8")):
            b["src"] = name
            out.append(b)
    return out


def looks_text(t: str) -> bool:
    """사람이 볼 값어치가 있나 — 일본어 글자가 3자 이상이고 반각 잡음이 그보다 적다."""
    ja = len(_JA.findall(t))
    return ja >= 3 and len(_NOISE.findall(t)) < ja


def load_script() -> dict:
    if SCRIPT.exists():
        return json.loads(SCRIPT.read_text(encoding="utf-8"))
    return {}


def save_script(data: dict) -> None:
    SCRIPT.parent.mkdir(parents=True, exist_ok=True)
    SCRIPT.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def keyed(bs: list[dict]) -> list[tuple[str, dict]]:
    return [(line_key(reuse.normalise(b)), b) for b in bs]


def cmd_seed(args) -> int:
    dic = json.loads(Path(args.dict).read_text(encoding="utf-8"))["lines"]
    data = load_script()
    bs = keyed(blocks())
    hit = new = upd = 0
    for k, _b in bs:
        if k not in dic:
            continue
        hit += 1
        if k in data:
            # ⚠ 이미 든 판단을 자동으로 밀어내지 않는다(patcher-checklist 6).
            # 🔴 다만 `by="dict"` 는 **판단이 아니라 사전 사본**이다 — 사전 쪽(PS1)이 QA 로
            #    좋아지면 우리도 받아야 한다. `--refresh` 로 그 줄만 다시 긁는다.
            #    `by="human"` 은 우리가 내린 판정이라 **무엇을 줘도 안 건드린다**(`why` 에 근거).
            if args.refresh and data[k].get("by") == "dict" and data[k]["t"] != dic[k]["t"]:
                if args.dry:
                    print(f"  [{k[:8]}] {data[k]['t'][:38]}\n        → {dic[k]['t'][:38]}")
                data[k] = {"t": dic[k]["t"], "by": "dict"}
                upd += 1
            continue
        data[k] = {"t": dic[k]["t"], "by": "dict"}
        new += 1
    if not args.dry:
        save_script(data)
    uniq = {k for k, _ in bs}
    print(f"블록 {len(bs):,} · 고유 열쇠 {len(uniq):,}")
    print(f"사전 적중 {hit:,} 블록 · 정본에 새로 넣은 것 {new:,}")
    human = sum(1 for v in data.values() if v.get("by") == "human")
    if args.refresh:
        print(f"사전이 고쳐져 따라간 것 {upd:,} · 우리 판정이라 그대로 둔 것 {human:,}")
    else:
        stale = sum(
            1
            for k, v in data.items()
            if v.get("by") == "dict" and k in dic and dic[k]["t"] != v["t"]
        )
        if stale:
            print(f"  ⚠ 사전이 그 뒤 고친 줄 {stale:,} — `seed --refresh` 로 받는다")
    print(f"정본 총 {len(data):,} 줄 ({'미저장 --dry' if args.dry else SCRIPT})")
    return 0


GLOSSARY = common.ROOT / "shared" / "glossary" / "eiyuu.json"
PUTTABLE = ("scn_jp/scenario", "scn_jp/combat")  # 재삽입 경로가 있는 자리


def glossary() -> dict[str, str]:
    out: dict[str, str] = {}

    def walk(o, key=None):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, str) and key and not key.startswith("_"):
            out[key] = o

    walk(json.loads(GLOSSARY.read_text(encoding="utf-8")))
    return out


def cmd_names(args) -> int:
    """**런이 통째로 정본 낱말인 자리**를 공용 정본에서 채운다 — 몬스터·아이템·지명.

    🔴 이름은 사람이 다시 옮길 것이 아니다. 정본이 있으면 그대로 쓴다.
    ⚠ **재삽입 경로가 있는 자리만** 넣는다(시나리오·전투). event/program 문자열은 자리가
      오프셋이라 `patch_sys.py` 의 `sys.json` 이 따로 덮는다 — 두 정본이 겹치면 헷갈린다.
    ⚠ 정본이 판정 규칙보다 낡은 자리가 있다(`docs/policy.md` — 지명 접미는 띄운다).
      그래서 넣은 뒤 **`check_glossary.py` 가 우리 안의 갈림을 잡는다.**
    """
    tbl = glossary()
    data = load_script()
    added = 0
    for k, b in keyed(blocks()):
        if b["src"] not in PUTTABLE or k in data:
            continue
        core = b["t"].strip(" \u3000")
        if core in tbl:
            data[k] = {"t": tbl[core], "by": "glossary"}
            added += 1
    print(f"정본에서 채운 이름 {added:,} · 정본 총 {len(data):,}")
    if not args.dry:
        save_script(data)
    return 0


# 전투의 정형. **좁은 것부터** 본다 — 「〜の群れが現れた。」이 「〜が現れた。」에 먼저 걸리면
# 이름에 「の群れ」가 딸려 들어가 정본에서 못 찾는다.
# 자리표: `{a}`·`{b}`·`{n}` 은 이름, `{j}` 는 **바로 앞 글자**의 받침에 맞춘 이/가,
#         `{w}` 는 같은 자로 고른 과/와.
ENC = [
    (r"(?P<a>.+?)と(?P<b>.+?)の群れが\s*現れた ?!*。?$", "{a}{w} {b} 무리{j} 나타났다."),
    (r"(?P<a>.+?)と(?P<b>.+?)が\s*現れた ?!*。?$", "{a}{w} {b}{j} 나타났다."),
    (r"(?P<a>.+?)と(?P<b>.+?)が\\n?現れた ?!*。?$", "{a}{w} {b}{j} 나타났다."),
    (r"(?P<a>.+?)を従えた、?\\n?(?P<b>.+?)が\s*現れた ?!*。?$", "{a}{r} 거느린 {b}{j} 나타났다."),
    (r"(?P<n>.+?)の群れが\s*現れた ?!*。?$", "{n} 무리{j} 나타났다."),
    (r"(?P<n>.+?)たちが\s*現れた ?!*。?$", "{n}들{j} 나타났다."),
    (r"(?P<n>.+?)がペアで現れた ?!*。?$", "{n}{j} 둘 나타났다."),
    (r"(?P<n>.+?)が(?P<c>[０-９0-9]+)匹 ?現れた ?!*。?$", "{n}{j} {c}마리 나타났다."),
    (r"(?P<n>.+?)が\s*現れた ?!*。?$", "{n}{j} 나타났다."),
    # ⚠ 문장 끝은 **원문을 따른다** — 「。」로 닫은 자리에 `!!` 를 붙이면 감정을 지어내는 것이다
    (r"(?P<n>.+?)の群れが\s*襲ってきた ?!!$", "{n} 무리{j} 덮쳐 왔다!!"),
    (r"(?P<n>.+?)の群れが\s*襲ってきた ?。?$", "{n} 무리{j} 덮쳐 왔다."),
    (r"(?P<n>.+?)が\s*襲ってきた ?!!$", "{n}{j} 덮쳐 왔다!!"),
    (r"(?P<n>.+?)が\s*襲ってきた ?。?$", "{n}{j} 덮쳐 왔다."),
]
ENC = [(re.compile(x), y) for x, y in ENC]
LABEL = re.compile(r"(?P<n>.+?)(?P<s>[Ａ-Ｄ])$")


def resolve(tbl: dict, jp: str) -> str | None:
    """이름을 정본에서 찾는다 — **앞에서 깎아 들어가며**.

    🔴 덤퍼가 런 앞에 잡음을 붙여 오는 자리가 많다(`ﾝﾃスライムの群れ`). 그렇다고 반각
       가나를 통째로 버릴 수는 없다 — `ｷｬﾘｵﾝ ｸﾛｰﾗｰ` 처럼 **이름 자체가 반각**인 것이 있다.
       그래서 **한 글자씩 깎으며 정본에 맞는 가장 긴 것**을 고른다.
    """
    # ⚠ 이름이 **반각으로 적힌 자리**도, **정본 키가 반각인 자리**도 있다
    #   (`ﾌｧｲｱｰﾓｽ` · `ｻﾝﾀﾞｰｽﾈｰｶｰ`). 그래서 양쪽을 **NFKC 로 접어** 맞춘다.
    global _NFKC
    if _NFKC is None:
        _NFKC = {unicodedata.normalize("NFKC", k): v for k, v in tbl.items()}
    folded = unicodedata.normalize("NFKC", jp)
    for i in range(len(folded)):
        tail = folded[i:]
        if tail not in _NFKC:
            continue
        # 🔴 깎아 낸 앞부분이 **내용이면 안 된다** — 삼키면 문안이 통째로 사라진다
        #    (「フラワーリザードとオディノンが\s*襲ってきた」의 앞 몬스터처럼. 실측).
        #    가르는 자는 **가나**다 — 진짜 일본어 구절엔 가나가 있고(`幸運の女神に見放された`),
        #    바이너리 잡음은 한자가 한둘 섞이는 꼴이다(`阡ｱｾFﾞ鐵ｧﾃ`). ⚠ 판정은 **원문**으로
        #    한다 — NFKC 를 먹인 잡음은 반각 가나가 진짜 가나로 바뀌어 오판한다.
        raw_prefix = jp[: len(jp) - (len(folded) - i)] if len(folded) >= i else jp[:i]
        if _KANA.search(raw_prefix) or len(_JA.findall(raw_prefix)) > 3:
            return None
        return _NFKC[tail]
    return None


def cmd_encounters(args) -> int:
    """전투의 **정형**을 규칙으로 짓는다 — 「〜が現れた。」과 개체 라벨(`ＡＢＣＤ`).

    🔴 이름은 **공용 정본**에서 오고 조사는 **`shared/text/josa`** 가 붙인다. 손으로 옮기면
       같은 문장을 수십 번 쓰면서 받침을 틀린다 — 실제로 이 축이 검사기에 걸렸다.
    ⚠ 규칙이 **정확히 맞는 것만** 넣는다. 이름이 정본에 없으면 건너뛴다(세어서 보여 준다).
    ⚠ 개체 라벨의 전각 `Ａ` 는 **반각 `A`** 로 간다(방침: 숫자·영문은 반각).
    """
    from text.josa import josa

    tbl = glossary()
    data = load_script()
    added = miss = 0
    for k, b in keyed(blocks()):
        if b["src"] not in PUTTABLE or k in data:
            continue
        # ⚠ 마커가 든 블록은 손대지 않는다 — 정형이 아니고, 규칙으로 지으면
        #   `<PAGE>`·`<WAIT>` 계약이 깨진다(`apply` 가 거부하는 그 축이다).
        if "<PAGE>" in b["t"] or "<WAIT>" in b["t"] or "\\n" in b["t"]:
            continue
        t = b["t"]
        m = LABEL.match(t)
        if m and (kr := resolve(tbl, m.group("n"))):
            data[k] = {"t": kr + chr(ord(m.group("s")) - 0xFEE0), "by": "auto"}
            added += 1
            continue
        for rx, fmt in ENC:
            mm = rx.match(t)
            if not mm:
                continue
            g = mm.groupdict()
            names = {}
            for tag in ("n", "a", "b"):
                if g.get(tag) is not None:
                    kr = resolve(tbl, g[tag])
                    if kr is None:
                        break
                    names[tag] = kr
            else:
                if g.get("c"):
                    names["c"] = "".join(
                        chr(ord(ch) - 0xFEE0) if "０" <= ch <= "９" else ch for ch in g["c"]
                    )
                # ⚠ 조사는 **그 자리 바로 앞 글자**의 받침을 본다 — 「슬라임 무리가」처럼
                #   이름이 아니라 뒤에 붙은 낱말이 앞말인 자리가 있다.
                out = fmt
                for tag, pair in (("j", "이/가"), ("w", "과/와"), ("r", "을/를")):
                    if "{" + tag + "}" not in out:
                        continue
                    before = out.format(
                        **names, **{tag: "\x00"}, **{o: "" for o in ("j", "w", "r") if o != tag}
                    ).split("\x00")[0]
                    out = out.replace("{" + tag + "}", josa(before, pair))
                data[k] = {"t": out.format(**names), "by": "auto"}
                added += 1
                break
            miss += 1
            break
    print(f"정형에서 지은 문안 {added:,} · 이름이 정본에 없어 건너뜀 {miss:,}")
    if not args.dry:
        save_script(data)
    return 0


def cmd_stat(args) -> int:
    data = load_script()
    bs = keyed(blocks())
    text = [(k, b) for k, b in bs if looks_text(b["t"])]
    done = sum(1 for k, _ in text if k in data)
    chars = sum(len(b["t"]) for _, b in text)
    dchars = sum(len(b["t"]) for k, b in text if k in data)
    print(f"정본 {len(data):,} 줄")
    print(f"볼 값어치 있는 블록 {len(text):,} / 전체 {len(bs):,}")
    print(f"  덮인 블록 {done:,} = {done / max(1, len(text)):.1%}")
    print(f"  덮인 글자 {dchars:,} / {chars:,} = {dchars / max(1, chars):.1%}")

    # 🔴 **재삽입 경로가 없는 정본을 센다.** 지금 붙일 수 있는 자리는 **시나리오 영역뿐**이다
    #    (`patch_scn.py` 가 `scn.SCENARIO_RANGE` 만 본다). 전투·event·program 에만 있는 줄은
    #    번역해 둬도 **화면에 안 나온다** — 그런데 `stat` 의 「덮인 비율」에는 잡히므로
    #    조용히 는다. 실패로는 안 친다(경로가 없는 건 「할 일」이지 「결함」이 아니다).
    #    ⚠ 이 자리는 patcher-checklist 「로더가 못 읽는 자료」다 — 주기 점검에서 다시 본다.
    where: dict[str, set[str]] = {}
    for k, b in bs:
        where.setdefault(k, set()).add(b["src"])
    PUT = {"scn_jp/scenario", "scn_jp/combat"}  # 전투도 재삽입 경로가 열렸다(2026-09-06)
    orphan = [k for k in data if k in where and not (where[k] & PUT)]
    lost = [k for k in data if k not in where]
    print(f"  ⚠ 재삽입 경로 없음 {len(orphan):,} 줄 (event/program 문자열에만 있다)")
    if lost:
        print(f"  🔴 원문에 안 붙는 정본 {len(lost):,} 줄 — 덤퍼나 열쇠 규칙이 바뀌었나")
    return 0


def cmd_payload(args) -> int:
    """아직 안 된 것을 **긴 것부터** 낸다 — 긴 블록이 대사고, 짧은 건 잡음이 많다.

    ⚠ 원문이 담기므로 **`work/review/` 밖으로 내보내지 않는다**(루트 「저작권」).
    """
    data = load_script()
    seen = set()
    rows = []
    for k, b in keyed(blocks()):
        if k in data or k in seen or not looks_text(b["t"]):
            continue
        seen.add(k)
        rows.append({"열쇠": k, "화자": b.get("s") or "", "원문": b["t"], "번역": ""})
    rows.sort(key=lambda r: -len(r["원문"]))
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    out = PAYLOAD_DIR / f"{args.name}.json"
    out.write_text(
        json.dumps(rows[: args.n], ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"남은 고유 블록 {len(rows):,} · 검토표에 {min(args.n, len(rows)):,} 줄 → {out}")
    return 0


def contract(t: str) -> tuple[int, int]:
    """구조 계약 — 페이지·대기 마커의 **개수**. 하나만 어긋나도 화면 흐름이 깨진다.

    ⚠ `\\n` 은 안 센다 — 줄나눔은 언어마다 다르고, 조판이 다시 잡는다.
    """
    return t.count("<PAGE>"), t.count("<WAIT>")


def cmd_apply(args) -> int:
    data = load_script()
    # 🔴 원문을 열쇠로 되찾아 **계약을 대조한다.** 검토표만 믿으면 마커가 빠진 줄이
    #    조용히 정본에 들어간다(이 레포가 세는 종류의 사고다 — patcher-checklist 12).
    src = {}
    for k, b in keyed(blocks()):
        src.setdefault(k, b["t"])
    put = skip = bad = broke = 0
    for path in args.files:
        for row in json.loads(Path(path).read_text(encoding="utf-8")):
            k, kr = row.get("열쇠"), (row.get("번역") or "").strip()
            if not kr:
                continue
            if not k or len(k) != 16:
                bad += 1
                continue
            if k in data and not args.force:  # ⚠ 이미 든 판단은 --force 로만 덮는다
                skip += 1
                continue
            if k in src and contract(src[k]) != contract(kr):
                print(f"  ⛔ 계약 어긋남 {k}: 원문 {contract(src[k])} ≠ 번역 {contract(kr)}")
                broke += 1
                continue
            data[k] = {"t": kr, "by": "human"}
            put += 1
    if not args.dry:
        save_script(data)
    print(
        f"넣음 {put:,} · 건너뜀 {skip:,} · 열쇠 이상 {bad:,} · 계약 어긋남 {broke:,} "
        f"· 정본 {len(data):,}"
    )
    return 1 if broke else 0


def _kr_bytes(t: str) -> int:
    """한글은 **빈 한자 자리**에 앉히므로 2B, 반각 부호·숫자·공백은 1B."""
    return sum(2 if "가" <= c <= "힣" else 1 for c in t)


def _jp_bytes(t: str) -> int:
    return sum(1 if (ord(c) < 0x80 or 0xFF61 <= ord(c) <= 0xFF9F) else 2 for c in t)


def _markers(t: str) -> str:
    """마커를 원래 1바이트 코드로 되돌린다 — 양쪽 다 같은 바이트 수라야 견줄 수 있다."""
    return t.replace("<PAGE>", "\x05").replace("<WAIT>", "\x03").replace("\\n", "\x01")


def cmd_fit(args) -> int:
    """번역이 **원래 자리에 들어가나** — 재삽입 전략을 가르는 자.

    `0F <주소 2B>` 가 무조건 점프라(`tools/units.py`), 남는 틈이 **3바이트 이상이면**
    제자리에 넣고 틈을 건너뛸 수 있다. 1~2바이트면 그럴 자리가 없어 **반각 공백으로
    메운다.** 넘치면 밖으로 뺀다.
    """
    data = load_script()
    buckets = {
        "꼭 맞는다": 0,
        "틈 3+ (0F 로 건너뛴다)": 0,
        "틈 1~2 (공백으로 메운다)": 0,
        "넘친다 (밖으로)": 0,
    }
    over = jt = kt = 0
    n = 0
    for k, b in keyed(blocks()):
        if k not in data:
            continue
        n += 1
        d = _jp_bytes(_markers(b["t"])) - _kr_bytes(_markers(data[k]["t"]))
        jt += _jp_bytes(_markers(b["t"]))
        kt += _kr_bytes(_markers(data[k]["t"]))
        if d == 0:
            buckets["꼭 맞는다"] += 1
        elif d >= 3:
            buckets["틈 3+ (0F 로 건너뛴다)"] += 1
        elif d > 0:
            buckets["틈 1~2 (공백으로 메운다)"] += 1
        else:
            buckets["넘친다 (밖으로)"] += 1
            over += -d
    print(f"대조 {n:,} 런 · JP {jt:,}B → KR {kt:,}B = {kt / max(1, jt):.1%}")
    for key, v in buckets.items():
        print(f"  {key:28s} {v:6,} = {v / max(1, n):6.1%}")
    print(f"  밖으로 뺄 때 필요한 바이트 {over:,}B")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--dict", default=str(DICT))
    s.add_argument("--dry", action="store_true")
    s.add_argument(
        "--refresh",
        action="store_true",
        help="사전이 그 뒤 고친 `by=dict` 줄을 다시 받는다 (`by=human` 은 안 건드린다)",
    )
    s.set_defaults(fn=cmd_seed)
    s = sub.add_parser("encounters")
    s.add_argument("--dry", action="store_true")
    s.set_defaults(fn=cmd_encounters)
    s = sub.add_parser("names")
    s.add_argument("--dry", action="store_true")
    s.set_defaults(fn=cmd_names)
    s = sub.add_parser("stat")
    s.set_defaults(fn=cmd_stat)
    s = sub.add_parser("fit")
    s.set_defaults(fn=cmd_fit)
    s = sub.add_parser("payload")
    s.add_argument("--n", type=int, default=200)
    s.add_argument("--name", default="batch")
    s.set_defaults(fn=cmd_payload)
    s = sub.add_parser("apply")
    s.add_argument("files", nargs="+")
    s.add_argument("--force", action="store_true")
    s.add_argument("--dry", action="store_true")
    s.set_defaults(fn=cmd_apply)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
