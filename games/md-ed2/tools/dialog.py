"""대사(씬 모듈) 채우기 보조 — PS1 ED2 문장 대조 · 검수표 · 정확 일치 자동 채움.

    python3 tools/dialog.py --stats                # 문장·글자 단위 일치율(전 모듈)
    python3 tools/dialog.py --review B K           # work/review/dialog-BBB-K.tsv (원문·가장 가까운 PS1·우리 문안 — 커밋 금지)
    python3 tools/dialog.py --apply B K            # script/BBB-K.json 의 빈 `ours` 를 채운다(화자 머리 + 정확 일치 문장만)

저본 순서(마스터 10-12): ① 정본(`shared/canon`) ② **PS1 ED2 에서 원문이 같은 문장은 PS1 한국어를 그대로** ③ 나머지 구절은 「비슷하게」 직접 번역.
PS1 대본 `script/ED2SCN*.json` 은 번호 → 한국어뿐이라 일본어 원문은 PS1 롬에서 PS1 도구로 되살려 맞댄다 —
⚠ **원문(JP)이라 저장은 `work/derived/`(gitignore) 뿐**이고 커밋되는 정본(`script/`)엔 해시와 우리 문안만 간다.
문장 = `。！？!?` 로 끝나는 덩이. 비교 열쇠는 NFKC · 가타카나→히라가나 · 공백·부호·장음·`･` 제거(표기 차를 흡수한다 — sfc-ed2 와 같은 방식).
PS1 문장의 한국어는 같은 블록의 일본어 문장 수와 한국어 문장 수(`.!?…` 로 끊음)가 같을 때만 1:1 로 잇는다(89%).
"""

import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import archives
import common
import scene
import textmap
from check_ellipsis import fix_text as fix_ellipsis

from shared import canon

CACHE = common.OUT_DIR / "ps1_ed2_dialog.json"
PS1_CHILD = r"""
import json, re
from extract_scn import SCN_FILES, find_text_end, parse_blocks, decode
from common import extract
out = {"blocks": [], "speakers": {}}
for name, lba, size in SCN_FILES:
    if not name.startswith("ED2"):
        continue
    data = extract(lba, size)
    bl = parse_blocks(data[: find_text_end(data)])
    j = json.load(open(f"../script/{name}.json"))
    for idx, (off, raw, kind) in enumerate(bl):
        if kind != "block":
            continue
        m = re.match(r"\{c\}(.*?)\{c\}(.*)", decode(raw), re.S)
        if not m:
            continue
        e = j.get(str(idx)) or {}
        out["blocks"].append([name, idx, m.group(1), m.group(2).replace("{n}", "").replace("{c}", ""), e.get("s"), e.get("t")])
print(json.dumps(out, ensure_ascii=False))
"""


def kata2hira(s: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


# PS1 와 MD 가 같은 대사에서 이름만 다르게 쓴 것(원문 기준) — 비교 열쇠에서 한쪽으로 모으고 한국어도 같이 바꾼다
SWAP_JP = {"スライム": "スラッグ"}
SWAP_KR = {"슬라임": "슬러그"}


def norm(s: str) -> str:
    for a, b in SWAP_JP.items():
        s = s.replace(a, b)
    s = kata2hira(unicodedata.normalize("NFKC", s))
    return re.sub(r"[\s･・·\.．。、，,!！?？～~ー…\-]", "", s)


def split_jp(s: str) -> list[str]:
    return [p for p in re.findall(r"[^。！？!?]+[。！？!?]*", s) if norm(p)]


def split_kr(s: str) -> list[str]:
    return [p.strip() for p in re.findall(r"[^.!?…]+[.!?…]*", s) if p.strip()]


def ps1_raw() -> dict:
    """PS1 ED2 대사 블록(일본어 원문 포함) — 캐시(work/derived)에서, 없으면 PS1 도구를 자식 프로세스로 돌려 만든다."""
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    tools = common.ROOT.parents[2] / "games" / "ps1-ed1+2" / "tools"
    if not tools.exists():
        raise SystemExit("PS1 도구(메인 트리 games/ps1-ed1+2/tools)를 못 찾았다")
    r = subprocess.run(
        [sys.executable, "-c", PS1_CHILD], cwd=tools, capture_output=True, text=True, check=False
    )
    if r.returncode:
        raise SystemExit(f"PS1 도구 실행 실패: {r.stderr[-300:]}")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(r.stdout, encoding="utf-8")
    return json.loads(r.stdout)


_idx = None


def ps1_index() -> dict:
    """{'sent': {열쇠: [(파일, 번호, 한국어 문장)]}, 'list': [(열쇠, 일본어 문장, 한국어 문장)], 'spk': {열쇠: 한국어}}"""
    global _idx
    if _idx is not None:
        return _idx
    raw = ps1_raw()
    sent: dict[str, list] = {}
    lst = []
    spk: dict[str, dict[str, int]] = {}
    for name, idx, sj, body, ks, kt in raw["blocks"]:
        if ks:
            spk.setdefault(norm(sj), {}).setdefault(ks, 0)
            spk[norm(sj)][ks] += 1
        js = split_jp(body)
        kk = split_kr(kt) if kt else []
        if kt and len(js) == len(kk):
            for a, b in zip(js, kk, strict=True):
                sent.setdefault(norm(a), []).append((name, idx, b))
                lst.append((norm(a), a, b))
    _idx = {
        "sent": sent,
        "list": lst,
        "spk": {k: max(v, key=v.get) for k, v in spk.items()},
    }
    return _idx


_SLUG_JOSA = {"이": "가", "은": "는", "을": "를", "과": "와", "으로": "로"}


def _fix_josa_slug(s: str) -> str:
    return re.sub(
        r"슬러그(이|은|을|과|으로)(?![가-힣])", lambda m: "슬러그" + _SLUG_JOSA[m.group(1)], s
    )


def fix_kr(s: str) -> str:
    """PS1 한국어 → 우리 표기(물결은 전각, 점 셋은 …)."""
    s = s.replace("{p}", "").replace(
        "{n}", " "
    )  # PS1 표지: {p} = 쪽 가름 · {n} = 줄바꿈 — 우리는 조판기가 가른다
    for a, b in SWAP_KR.items():
        s = s.replace(a, b)
    s = _fix_josa_slug(
        s
    )  # 슬라임→슬러그 로 이름만 바꾸면 PS1 의 받침 있는 조사가 남는다(「슬러그이」)
    s = s.replace("~", "～").replace("...", "…")
    s = s.replace("～.", "～")  # 번역 규칙 1-7: 물결표 뒤에 마침표를 붙이지 않는다
    return fix_ellipsis(s)  # 번역 규칙 2-11: 「…」 뒤에 말이 이어지면 띄운다(말더듬 예외 포함)


# ── MD 스트림 분석 ───────────────────────────────────────────────────────────
# 한 스트림에 **여러 창·여러 화자**가 이어진다(`<0900>` 이름 머리 · `<10:머리 스트림>` 화자 호출 · `05` 쪽 · 이벤트 코드) — 글 토막(seg)은
# 이런 태그 사이에 낀 글 덩이고, 토막마다 따로 번역한다. 토막 앞 줄바꿈(01)은 **이름 줄 뒤 개행**이라 `<01>` 태그로 되돌려 쓴다.
# (`textmap.stream_to_text` 는 01 을 공백으로 흘려 이 구별을 잃는다 — 기존 시험 번역이 `<0900><01>` 을 손으로 쓴 까닭.)


def tag_of(t: scene.Token) -> str:
    if t.kind == "end":
        return f"<{t.code:02x}>"
    if t.ref:
        return f"<{t.code:02x}:{t.target:04x}>"
    return f"<{t.raw.hex()}>"


def items(st: scene.Stream, mod: scene.Module | None = None):
    """스트림 → [('tag', 태그) | ('page',) | ('seg', 원문 글, 앞 줄바꿈 여부)]. 이름 호출(10→글 스트림)은 ('inline', 태그)."""
    out = []
    cur: list[str] = []
    lead_nl = False
    started = False
    spk: list[str] | None = None

    def flush():
        nonlocal cur, lead_nl, started
        if cur:
            out.append(("seg", "".join(cur), lead_nl))
        cur, lead_nl, started = [], False, False

    for t in st.tokens:
        if spk is not None:  # `<1e>이름<04>` 인라인 화자 머리
            if t.kind == "text":
                spk.append(t.raw.decode("cp932", "replace"))
                continue
            if t.kind == "ctl" and t.code == 0x04:
                out.append(("spk", "".join(spk).strip()))
                spk = None
                continue
            spk = None  # 모양이 다르면 일반 처리로
        if t.kind == "ctl" and t.code == 0x1E:
            flush()
            spk = []
            continue
        if t.kind == "text":
            cur.append(t.raw.decode("cp932", "replace"))
            started = True
        elif t.kind == "eof":
            continue
        elif t.kind == "ctl" and t.code == 0x01:
            if started:
                cur.append(" ")
            else:
                lead_nl = True
        elif t.kind == "ctl" and t.code == 0x05:
            flush()
            out.append(("page",))
        else:
            flush()
            tg = tag_of(t)
            if t.ref and t.code == 0x10 and mod is not None:
                tgt = mod.streams.get(t.target)
                if (
                    tgt is not None
                    and tgt.tokens
                    and not (tgt.tokens[0].kind == "ctl" and tgt.tokens[0].code == 0x1E)
                ):
                    out.append(
                        ("inline", tg)
                    )  # 이름 따위를 끼워 넣는 호출 — 문장이 태그 양옆으로 이어진다
                    continue
            out.append(("tag", tg))
    flush()
    return out


def sheet_text(its) -> str:
    out = []
    for it in its:
        if it[0] == "seg":
            out.append(("<01>" if it[2] else "") + it[1].strip())
        elif it[0] == "page":
            out.append("\f")
        elif it[0] == "spk":
            out.append(f"<1e>{it[1]}<04>")
        else:
            out.append(it[1])
    return "".join(out)


def speaker_kr(jp: str) -> str | None:
    """화자 원문 → 한국어 — ① 정본 speaker · 사전 person ② PS1 화자표."""
    import dict_names

    n = re.sub(r"\s+", "", jp)
    v = canon.lookup(jp, "speaker", "ed2") or canon.lookup(n, "speaker", "ed2")
    if v:
        return v
    v = dict_names.from_dict(jp, ("person",)) or dict_names.from_dict(n, ("person",))
    if v:
        return v
    return ps1_index()["spk"].get(norm(jp))


def name_kr(jp: str) -> str | None:
    """글 토막이 이름 하나뿐이면 사전(person·place·item …)의 우리 표기 — 이름 호출 대상 스트림용."""
    import dict_names

    t = jp.strip()
    if not t or len(t) > 14 or re.search(r"[。！？、!?,.]", t):
        return None
    return dict_names.from_dict(t, ("person", "place", "item", "monster", "term"))


_tm: dict[str, str] | None = None
TAGSPLIT = re.compile(r"<[^>]*>|\f")


def tm_index() -> dict[str, str]:
    """번역 기억 — 이미 번역된 스트림에서 「원문 문장 → 우리 문장」을 거둔다(글 토막 수·문장 수가 같을 때만). 같은 문장을 매번 다르게 쓰면
    LZ 가 못 붙이고(모듈 넷이 한 블록이라 되풀이가 많다) 말투도 갈린다 — 옛 번역을 먼저 따른다."""
    global _tm
    if _tm is not None:
        return _tm
    out: dict[str, str] = {}
    for p in sorted(textmap.SCRIPT_DIR.glob("*.json")):
        j = json.loads(p.read_text(encoding="utf-8"))
        mod = module(int(j["block"]), int(j["mod"]))
        for o, ent in sorted(j["streams"].items()):
            ours = ent.get("ours", "")
            st = mod.streams.get(int(o, 16))
            if not ours or st is None or ent.get("src") == "ps1-exact":
                continue
            # 글 토막 경계(쪽·태그)가 원문과 우리 문안에서 같다는 보장이 없으니 **문장 열**을 통째로 맞댄다(수가 같을 때만)
            jp_sents = [
                x
                for it in items(st, mod)
                if it[0] == "seg" and norm(it[1])
                for x in split_jp(it[1])
            ]
            kr_text = TAGSPLIT.sub("\n", re.sub(r"<1e>.*?<04>", "\n", ours))
            kr_sents = [x for seg in kr_text.split("\n") if seg.strip() for x in split_kr(seg)]
            if len(jp_sents) == len(kr_sents):
                for x, y in zip(jp_sents, kr_sents, strict=True):
                    out.setdefault(norm(x), y)
    _tm = out
    return out


def candidates(body: str):
    """본문 → [(문장, 정확 일치 한국어 | None, 가장 가까운 PS1(일본어, 한국어, 점수))]."""
    ix = ps1_index()
    out = []
    for s in split_jp(body):
        n = norm(s)
        hit = ix["sent"].get(n)
        ko = fix_kr(hit[0][2]) if hit else None
        if hit is None and n in tm_index():  # 우리 옛 번역(번역 기억) — PS1 이 없을 때
            hit, ko = True, tm_index()[n]
        if ko and (
            "{" in ko or "\x1b" in ko
        ):  # PS1 자리표(`{p}` 등)가 든 문장은 그대로 못 쓴다 — 직접 번역
            ko, hit = None, None
        near = None if hit else nearest(n)
        out.append((s, ko, near))
    return out


_bg = None


def nearest(n: str):
    """바이그램 겹침으로 가장 가까운 PS1 문장 — (일본어, 한국어, 점수)."""
    global _bg
    ix = ps1_index()
    if _bg is None:
        _bg = {}
        for i, (k, _j, _kr) in enumerate(ix["list"]):
            for g in {k[a : a + 2] for a in range(len(k) - 1)}:
                _bg.setdefault(g, []).append(i)
    gs = {n[a : a + 2] for a in range(len(n) - 1)}
    if not gs:
        return None
    cnt: dict[int, int] = {}
    for g in gs:
        for i in _bg.get(g, ()):
            cnt[i] = cnt.get(i, 0) + 1
    best = None
    for i, c in cnt.items():
        k = ix["list"][i][0]
        sc = c / (len(gs) + len(k) - 1 - c + 1e-9)
        if best is None or sc > best[0]:
            best = (sc, i)
    if best is None or best[0] < 0.3:
        return None
    _k, j, kr = ix["list"][best[1]]
    return (j, fix_kr(kr), round(best[0], 2))


def fill(st: scene.Stream, mod: scene.Module) -> str | None:
    """자동으로 채울 수 있으면 `ours`, 아니면 None — 모든 글 토막이 정확 일치 문장이고 화자 이름이 정해진 스트림만.
    인라인 이름 호출이 끼면(문장이 태그 양옆으로 이어짐) 직접 번역. 글이 하나도 없는(제어코드뿐인) 스트림은 원문 그대로라 비운다."""
    out = []
    has_text = False
    for it in items(st, mod):
        if it[0] == "seg":
            if not norm(it[1]):
                continue
            nm = name_kr(it[1])
            if nm is not None:  # 이름만 있는 스트림(이름 호출 대상) — 사전/정본 그대로
                has_text = True
                out.append(("<01>" if it[2] else "") + nm)
                continue
            cs = candidates(it[1])
            if not cs or any(c[1] is None for c in cs):
                return None
            has_text = True
            out.append(("<01>" if it[2] else "") + " ".join(c[1] for c in cs))
        elif it[0] == "inline":
            return None
        elif it[0] == "spk":
            kr = speaker_kr(it[1])
            if kr is None:
                return None
            has_text = True
            out.append(f"<1e>{kr}<04>")
        elif it[0] == "page":
            out.append("\f")
        else:
            out.append(it[1])
    return "".join(out) if has_text else None


def module(blk: int, k: int) -> scene.Module:
    return scene.parse_module(textmap.module_bytes(common.rom(), blk, k))


def stats() -> None:
    d = common.rom()
    ix = ps1_index()
    ns = nh = nc = hc = 0
    nstream = nfill = ntext = 0
    for _blk, _k, m in archives.modules(d):
        mod = scene.parse_module(m)
        for st in mod.streams.values():
            nstream += 1
            its = items(st, mod)
            has = False
            for it in its:
                if it[0] != "seg":
                    continue
                for s in split_jp(it[1]):
                    n = norm(s)
                    if len(n) < 3:
                        continue
                    has = True
                    ns += 1
                    nc += len(n)
                    if n in ix["sent"]:
                        nh += 1
                        hc += len(n)
            ntext += has
            nfill += fill(st, mod) is not None
    print(
        f"  PS1 ED2 문장 {len(ix['list'])}(한국어 짝 있음) · MD 스트림 {nstream}(글 있는 {ntext}) · "
        f"문장 {nh}/{ns} ({nh * 100 // max(ns, 1)}%) · 글자 {hc}/{nc} ({hc * 100 // max(nc, 1)}%) · 자동 채움 가능 스트림 {nfill}"
    )


def sheet(blk: int, k: int) -> None:
    """아직 비어 있는 스트림의 작업표 — 구조(태그·`<01>` 줄바꿈·`<1e>화자<04>`) + 토막별 정확 일치(=)·가장 가까운 PS1(~, 점수)."""
    mod = module(blk, k)
    mp = textmap.SCRIPT_DIR / f"{blk:03d}-{k}.json"
    cur = json.loads(mp.read_text(encoding="utf-8"))["streams"] if mp.exists() else {}
    for off in sorted(mod.streams):
        if cur.get(f"{off:04x}", {}).get("ours"):
            continue
        st = mod.streams[off]
        its = items(st, mod)
        if not any(it[0] == "seg" and norm(it[1]) for it in its) and not any(
            it[0] == "spk" for it in its
        ):
            continue  # 글이 없는 스트림은 원문 그대로
        print(f"[{off:04x}] {sheet_text(its)}")
        for it in its:
            if it[0] != "seg" or not norm(it[1]):
                continue
            for s, ko, near in candidates(it[1]):
                if ko:
                    print(f"    = {s.strip()} → {ko}")
                elif near:
                    print(f"    ~ {s.strip()} | {near[0]} → {near[1]} ({near[2]})")
                else:
                    print(f"    - {s.strip()}")
        for it in its:
            if it[0] == "spk":
                print(f"    화자 {it[1]} → {speaker_kr(it[1])}")


def review(blk: int, k: int) -> None:
    mod = module(blk, k)
    p = common.REVIEW_DIR / f"dialog-{blk:03d}-{k}.tsv"
    p.parent.mkdir(parents=True, exist_ok=True)
    cur = {}
    mp = textmap.SCRIPT_DIR / f"{blk:03d}-{k}.json"
    if mp.exists():
        cur = json.loads(mp.read_text(encoding="utf-8"))["streams"]
    rows = ["스트림\t원문(MD)\t정확일치/가장 가까운 PS1(원문)\tPS1 한국어\t점수\t우리 문안\t출처"]
    for off in sorted(mod.streams):
        ent = cur.get(f"{off:04x}", {})
        ours, src = ent.get("ours", ""), ent.get("src", "")
        for it in items(mod.streams[off], mod):
            if it[0] == "spk":
                rows.append(f"{off:04x}\t{it[1]}\t화자\t{speaker_kr(it[1]) or ''}\t\t{ours}\t{src}")
            elif it[0] == "seg" and norm(it[1]):
                for s, ko, near in candidates(it[1]):
                    if ko:
                        rows.append(f"{off:04x}\t{s.strip()}\t=\t{ko}\t1.0\t{ours}\t{src}")
                    elif near:
                        rows.append(
                            f"{off:04x}\t{s.strip()}\t{near[0]}\t{near[1]}\t{near[2]}\t{ours}\t{src}"
                        )
                    else:
                        rows.append(f"{off:04x}\t{s.strip()}\t-\t\t\t{ours}\t{src}")
    p.write_text("\n".join(rows), encoding="utf-8")
    print(f"  {p} ({len(rows) - 1}행)")


_KRTOK = re.compile(r"(<1e>[^<]*<04>)|(<[0-9a-f]{2,}(?::-?[0-9a-f]+)?(?:\|[^>]*)?>)|([^<]+)")


def page_count(st: scene.Stream, mod: scene.Module) -> int:
    return sum(1 for it in items(st, mod) if it[0] == "page")


def repage(st: scene.Stream, mod: scene.Module, ours: str) -> str | None:
    """원문 스트림의 쪽 넘김(`05`)이 번역문에서 빠졌다 — 원문 쪽 경계를 **문장 경계**로 옮겨 `\\f` 를 되살린다.
    원본은 화자·창 머리가 바뀔 때도 앞 글이 쪽으로 끝나야 한 대사씩 멈춘다(마스터 10-13: 대사가 후루룩 넘어간다).
    태그(화자 머리·호출·조건 명령)를 기준 삼아 JP·KR 을 같은 덩이로 자르고, 덩이 안에서는 JP 의 쪽 사이 문장 수 비율로 KR 문장 경계를 고른다.
    태그 수가 안 맞으면 None(손으로)."""
    its = items(st, mod)
    jp_runs: list[list] = [[]]  # 태그 사이 덩이마다 [문장 수 또는 'P', ...]
    jp_t = 0
    for it in its:
        if it[0] == "seg":
            jp_runs[-1].append(len(split_jp(it[1])))
        elif it[0] == "page":
            jp_runs[-1].append("P")
        else:
            jp_t += 1
            jp_runs.append([])
    toks = [m for m in _KRTOK.finditer(ours.replace("\f", "").replace("<84>?", "\x01"))]
    kr_runs: list[list[str]] = [[]]  # 덩이마다 텍스트 토막
    heads: list[str] = []
    for m in toks:
        if m.group(3) is not None or re.fullmatch(r"<e[bc]0[0-4]>", m.group(0)):
            kr_runs[-1].append(m.group(0))  # 조사 훅은 글의 일부다(원문엔 「は」「を」 글자)
        elif m.group(0) == "<01>":
            heads.append(
                None
            )  # 줄바꿈 태그는 덩이 경계가 아니다 — 아래에서 텍스트 앞에 그대로 붙인다
            kr_runs[-1].append("<01>")
        else:
            heads.append(m.group(0))
            kr_runs.append([])
    if len(kr_runs) != len(jp_runs):
        return None
    tags = [
        m.group(0)
        for m in toks
        if m.group(3) is None
        and m.group(0) != "<01>"
        and not re.fullmatch(r"<e[bc]0[0-4]>", m.group(0))
    ]
    out: list[str] = []
    for ri, (jr, kr) in enumerate(zip(jp_runs, kr_runs, strict=True)):
        if ri > 0:
            out.append(tags[ri - 1])
        npage = jr.count("P")
        text = "".join(kr)
        lead = ""
        while text.startswith("<01>"):
            lead += "<01>"
            text = text[4:]
        if npage == 0:
            out.append(lead + text)
            continue
        sents = split_kr(text)
        chunks, cur = [], 0
        for x in jr:
            if x == "P":
                chunks.append(cur)
                cur = 0
            else:
                cur += x
        chunks.append(cur)
        total = sum(chunks) or 1
        nk = len(sents)
        bounds, cum = [], 0
        for c in chunks[:-1]:
            cum += c
            bounds.append(round(nk * cum / total))
        parts, last = [], 0
        for b in [*bounds, nk]:
            parts.append(" ".join(sents[last:b]))
            last = b
        out.append(lead + "\f".join(parts))
    return "".join(out).replace("\x01", "<84>?")


def repage_all(dry: bool = False) -> None:
    n_fix = n_bad = 0
    for mp in sorted(textmap.SCRIPT_DIR.glob("*.json")):
        d = json.loads(mp.read_text(encoding="utf-8"))
        mod = None
        dirty = False
        for off, ent in d["streams"].items():
            ours = ent.get("ours")
            if not ours:
                continue
            if mod is None:
                mod = module(d["block"], d["mod"])
            st = mod.streams.get(int(off, 16))
            if st is None or page_count(st, mod) == ours.count("\f"):
                continue
            new = repage(st, mod, ours)
            if new is None:
                n_bad += 1
                print(f"  ✗ {mp.stem}:{off} 태그 수가 안 맞아 못 옮긴다")
                continue
            ent["ours"] = new
            n_fix += 1
            dirty = True
        if dirty and not dry:
            mp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  쪽 넘김 되살림 {n_fix}개 · 못 옮김 {n_bad}개")


def setfile(blk: int, k: int, path: str) -> None:
    """`{오프셋: ours}` JSON 을 정본에 합친다 — 원문 해시는 그대로, 출처는 `ours:ed2-manual`(직접 번역)."""
    mod = module(blk, k)
    mp = textmap.SCRIPT_DIR / f"{blk:03d}-{k}.json"
    cur = (
        json.loads(mp.read_text(encoding="utf-8"))
        if mp.exists()
        else {"block": blk, "mod": k, "streams": {}}
    )
    new = json.loads(Path(path).read_text(encoding="utf-8"))
    for key, ours in new.items():
        off = int(key, 16)
        if off not in mod.streams:
            raise SystemExit(f"스트림 {key} 가 모듈에 없다")
        ent = cur["streams"].setdefault(
            f"{off:04x}", {"jp": textmap.jp_key(mod.streams[off]), "ours": ""}
        )
        ours = fix_ellipsis(ours)  # 규칙 2-11
        st0 = mod.streams[off]
        if page_count(st0, mod) != ours.count("\f"):  # 원문의 쪽 넘김을 문장 경계로 옮긴다
            ours = repage(st0, mod, ours) or ours
        ent["ours"] = ours
        ent["src"] = "ours:ed2-manual"
    mp.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {mp}: {len(new)}개 반영")


REFTAG = re.compile(r"<([0-9a-f]{2}):(-?[0-9a-f]{1,4})>")


def dup_key(st: scene.Stream) -> str:
    """같은 글·같은 구조의 스트림(모듈마다 되풀이되는 NPC 대사)을 묶는 열쇠 — 참조 태그의 대상 오프셋만 지운다."""
    return re.sub(r"\s+", "", REFTAG.sub(r"<\1:>", textmap.stream_to_text(st)))


def known_templates() -> dict[str, str]:
    """{dup_key: 템플릿} — 이미 번역된 스트림(전 정본)에서. 템플릿의 참조 태그 대상은 `{i}`(그 스트림의 i 번째 참조)로 바꿔 둔다."""
    out: dict[str, str] = {}
    mods: dict[tuple[int, int], scene.Module] = {}
    for p in sorted(textmap.SCRIPT_DIR.glob("*.json")):
        j = json.loads(p.read_text(encoding="utf-8"))
        key = (int(j["block"]), int(j["mod"]))
        mod = mods.setdefault(key, module(*key))
        for o, ent in j["streams"].items():
            ours = ent.get("ours", "")
            st = mod.streams.get(int(o, 16))
            if not ours or st is None:
                continue
            refs = REFTAG.findall(textmap.stream_to_text(st))
            have = REFTAG.findall(ours)
            if len(refs) != len(have) or [r[0] for r in refs] != [h[0] for h in have]:
                continue
            counter = iter(range(len(have)))
            tpl = REFTAG.sub(
                lambda m, c=counter: f"<{m.group(1)}:{{{next(c)}}}>",
                ours.replace("{", "{{").replace("}", "}}"),
            )
            tpl = tpl.replace("{{", "{{").replace("}}", "}}")
            out.setdefault(dup_key(st), tpl)
    return out


def propagate(blk: int, k: int, cur: dict, mod: scene.Module, tpls: dict[str, str]) -> int:
    n = 0
    for off in sorted(mod.streams):
        ent = cur["streams"].setdefault(
            f"{off:04x}", {"jp": textmap.jp_key(mod.streams[off]), "ours": ""}
        )
        if ent.get("ours"):
            continue
        st = mod.streams[off]
        tpl = tpls.get(dup_key(st))
        if tpl is None:
            continue
        refs = REFTAG.findall(textmap.stream_to_text(st))
        try:
            ent["ours"] = tpl.format(*[r[1] for r in refs])
        except (IndexError, KeyError):
            continue
        ent["src"] = "dup"
        n += 1
    return n


def apply(blk: int, k: int) -> None:
    mod = module(blk, k)
    mp = textmap.SCRIPT_DIR / f"{blk:03d}-{k}.json"
    cur = (
        json.loads(mp.read_text(encoding="utf-8"))
        if mp.exists()
        else {"block": blk, "mod": k, "streams": {}}
    )
    n = 0
    for off in sorted(mod.streams):
        st = mod.streams[off]
        ent = cur["streams"].setdefault(f"{off:04x}", {"jp": textmap.jp_key(st), "ours": ""})
        if ent.get("ours"):
            continue
        o = fill(st, mod)
        if o:
            ent["ours"] = o
            ent["src"] = "ps1-exact"
            n += 1
    nd = propagate(blk, k, cur, mod, known_templates())
    mp.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {mp}: PS1 정확 일치 {n} · 같은 글(모듈 간 되풀이) {nd} / 스트림 {len(mod.streams)}")


def apply_all() -> None:
    """전 모듈에 정확 일치 + 같은 글 전파 — 채운 게 있는 모듈만 정본 파일을 만든다(되풀이하면 전파가 퍼진다)."""
    total = 0
    for _ in range(2):  # 전파는 앞 모듈이 채운 것을 뒤 모듈이 받으므로 두 번
        tpls = known_templates()
        total = 0
        for blk, k, m in archives.modules(common.rom()):
            mod = scene.parse_module(m)
            mp = textmap.SCRIPT_DIR / f"{blk:03d}-{k}.json"
            cur = (
                json.loads(mp.read_text(encoding="utf-8"))
                if mp.exists()
                else {"block": blk, "mod": k, "streams": {}}
            )
            n = 0
            for off in sorted(mod.streams):
                st = mod.streams[off]
                ent = cur["streams"].setdefault(
                    f"{off:04x}", {"jp": textmap.jp_key(st), "ours": ""}
                )
                if ent.get("ours"):
                    continue
                o = fill(st, mod)
                if o:
                    ent["ours"], ent["src"] = o, "ps1-exact"
                    n += 1
            n += propagate(blk, k, cur, mod, tpls)
            if n or mp.exists():
                mp.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
            total += n
    print(f"  전 모듈 자동 채움(이번 회) {total}")


def todo(limit: int, start: tuple[int, int] = (0, 0)) -> None:
    """아직 비어 있는 **고유** 스트림(같은 글은 첫 모듈에서 한 번만)의 작업표 — 열쇠 `B-K:오프셋`."""
    seen: set[str] = set()
    shown = 0
    for blk, k, m in archives.modules(common.rom()):
        mod = scene.parse_module(m)
        mp = textmap.SCRIPT_DIR / f"{blk:03d}-{k}.json"
        cur = json.loads(mp.read_text(encoding="utf-8"))["streams"] if mp.exists() else {}
        for off in sorted(mod.streams):
            st = mod.streams[off]
            its = items(st, mod)
            # 제어 자료가 글처럼 읽힌 쓰레기(「､4」·「�?」)는 건너뛴다 — 가나·한자(전각)가 한 글자도 없는 토막
            if not any(
                it[0] == "seg"
                and norm(it[1])
                and "\ufffd" not in it[1]
                and re.search("[\u3040-\u30ff\u4e00-\u9fff]", it[1])
                for it in its
            ):
                continue
            dk = dup_key(st)
            if cur.get(f"{off:04x}", {}).get("ours") or dk in seen:
                seen.add(dk)
                continue
            seen.add(dk)
            if (blk, k) < start:
                continue
            if shown >= limit:
                return
            shown += 1
            print(f"[{blk}-{k}:{off:04x}] {sheet_text(its)}")
            for it in its:
                if it[0] != "seg" or not norm(it[1]):
                    continue
                for s, ko, near in candidates(it[1]):
                    if ko:
                        print(f"    = {s.strip()} → {ko}")
                    elif near:
                        print(f"    ~ {s.strip()} | {near[0]} → {near[1]} ({near[2]})")
                    else:
                        print(f"    - {s.strip()}")
            for it in its:
                if it[0] == "spk" and speaker_kr(it[1]) is None:
                    print(f"    ⚠ 화자 {it[1]} 정본·PS1 에 없음")


def setall(path: str) -> None:
    """`{"B-K:오프셋": ours}` 를 모듈별로 합친다(원문 해시 검증 · 출처 ours:ed2-manual)."""
    new = json.loads(Path(path).read_text(encoding="utf-8"))
    by: dict[tuple[int, int], dict] = {}
    for key, ours in new.items():
        bk, off = key.split(":")
        b, k = bk.split("-")
        by.setdefault((int(b), int(k)), {})[off] = ours
    for (b, k), d in sorted(by.items()):
        tmp = common.OUT_DIR / "_setall.json"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        setfile(b, k, str(tmp))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--stats"]:
        stats()
    elif a[:1] == ["--review"]:
        review(int(a[1]), int(a[2]))
    elif a[:1] == ["--apply"]:
        apply(int(a[1]), int(a[2]))
    elif a[:1] == ["--apply-all"]:
        apply_all()
    elif a[:1] == ["--todo"]:
        todo(int(a[1]) if len(a) > 1 else 20)
    elif a[:1] == ["--repage-all"]:
        repage_all("--dry" in a)
    elif a[:1] == ["--setall"]:
        setall(a[1])
    elif a[:1] == ["--sheet"]:
        sheet(int(a[1]), int(a[2]))
    elif a[:1] == ["--set"]:
        setfile(int(a[1]), int(a[2]), a[3])
    else:
        print(__doc__)
