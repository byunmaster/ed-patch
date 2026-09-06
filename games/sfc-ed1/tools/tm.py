"""sfc-ed1 번역 메모리 — SFC 번역 단위 ↔ PS1 ED1 번역본(같은 이야기) 후보 짝짓기.

가나 문안이라 SJIS 축자 대조는 못 쓴다. 대신 **화자**(가나 → glossary → 한국어)와 **고유명사**(사전 치환
`{…}` → glossary → 한국어)가 양쪽에 그대로 있으니 그 겹침 + 위치 + 길이비로 후보를 매긴다.
결과는 **후보**다 — 확정은 사람이 한다(work/derived/tm/, 원문 포함이라 커밋 금지).

⚠ 프로토타입이다. 정렬 품질은 「화자 있는 단위 중 후보가 붙은 비율」과 표본 검토로만 안다.
"""

import argparse
import collections
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: F401, I001
import common

GLOSSARY = common.ROOT / "shared" / "glossary" / "eiyuu.json"
# ⚠ 이 워크트리의 games/ps1-ed1+2 는 main 시점의 낡은 사본이다(창 2,818). 진행 중인 PS1 워크트리가 있으면
#   그쪽(창 5,033)을 먼저 본다 — 번역 메모리는 최신 번역본이어야 뜻이 있다.
_MAIN = common.ROOT.parent.parent.parent if common.ROOT.parent.name == "worktrees" else common.ROOT
_PS1_CANDIDATES = [
    _MAIN / ".claude" / "worktrees" / "ps1-ed1+2" / "games" / "ps1-ed1+2" / "script",
    _MAIN / "games" / "ps1-ed1+2" / "script",
    common.ROOT / "games" / "ps1-ed1+2" / "script",
]
PS1_SCRIPT = next((p for p in _PS1_CANDIDATES if p.is_dir()), _PS1_CANDIDATES[-1])

# SFC 화자는 히라가나 보통명사가 많다 — glossary 는 한자 키라 여기서 잇는다(고유명사는 glossary 직행).
KANA_SPEAKER = {
    "へいし": "兵士",
    "おとこ": "男",
    "おんな": "女",
    "ろうじん": "老人",
    "とうぞく": "盗賊",
    "どうぐや": "道具屋",
    "しんぷ": "神父",
    "かいぞく": "海賊",
    "ぶきや": "武器屋",
    "やくにん": "役人",
    "たいちょう": "隊長",
    "むすめ": "娘",
    "こども": "子供",
    "のうふ": "農夫",
    "りょうし": "漁師",
    "おばあさん": "おばあさん",
    "そんちょう": "村長",
    "けんじゃ": "賢者",
    "やみのしょうにん": "やみの商人",
    "ろうば": "老婆",
    "じじょ": "侍女",
    "しゅうじん": "囚人",
    "せんちょう": "船長",
    "がくしゃ": "学者",
    "ははおや": "母親",
    "しれいかん": "司令官",
    "もんばん": "門番",
    "やどやのしゅじん": "宿屋の主人",
    "ちょうちょう": "町長",
    "しょうにん": "商人",
    "だいとうぞくゲイル": "大盗賊 ゲイル",
    "ディーナひめ": "ディーナ姫",
    "じょうほうや　おさむん": "情報屋 トミー",
    "レジスタンス": "レジスタンス",
    "ギルモアのほし": "ギルモアの星",
    "ひかりのつるぎ": "光の剣",
    "バケモノ": "バケモノ",
    "フ・ーガソン": "ファーガソン",
    "ラルフ・": "ラルフ",
    "りゅうけつ": None,
    "ナイフ": None,
    "ショクダイ": None,
}


def load_glossary() -> dict[str, str]:
    g = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    flat = {}
    for cat in ("person", "place", "item", "monster"):
        for k, v in g["categories"][cat].items():
            flat.setdefault(k, v)
    return flat


def speaker_kr(kana: str, gl: dict[str, str]) -> str | None:
    key = KANA_SPEAKER.get(kana, kana)
    return gl.get(key) if key else None


_KATA_KEYS: list[tuple[str, str]] = []


def nouns_kr(jp: str, gl: dict[str, str]) -> set[str]:
    """문안(사전 치환 `{…}` 포함) 안의 가타카나 고유명사 → 한국어 표기 집합.
    `{セリオスおうじ}` 처럼 이름 뒤에 뭐가 붙으니 **부분 문자열**로 찾는다(glossary 의 가타카나 키, 2자 이상)."""
    global _KATA_KEYS
    if not _KATA_KEYS:
        _KATA_KEYS = sorted(
            ((k, v) for k, v in gl.items() if len(k) >= 2 and re.fullmatch(r"[ァ-ヶー・]+", k)),
            key=lambda kv: -len(kv[0]),
        )
    out = set()
    hay = jp
    for k, v in _KATA_KEYS:
        if k in hay:
            out.add(v)
            hay = hay.replace(k, "＊")
    return out


def load_ps1() -> list[dict]:
    rows = []
    for f in sorted(glob.glob(str(PS1_SCRIPT / "ED1SCN*.json"))):
        scn = int(re.search(r"SCN(\d+)", f).group(1))
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        for k, v in d.items():
            if isinstance(v, dict) and "t" in v:
                rows.append({"scn": scn, "idx": int(k), "s": v.get("s"), "t": v["t"]})
    for i, r in enumerate(rows):
        r["pos"] = i / max(1, len(rows) - 1)
    return rows


def kana_len(jp: str) -> int:
    return len(re.sub(r"<[^<>]*>|\s", "", jp))


def match(units: list[dict], ps1: list[dict], gl: dict[str, str]):
    by_speaker = collections.defaultdict(list)
    for r in ps1:
        if r["s"]:
            by_speaker[r["s"]].append(r)
    out = []
    # 화자 전파 — 같은 조각(END 사이) 안에서는 마지막 화자가 이어진다(페이지 넘김을 넘어서)
    last = None
    prev_seg = None
    for u in units:
        seg = u.get("seg")
        if seg != prev_seg:
            last = None
            prev_seg = seg
        if u["speaker"]:
            last = u["speaker"]
        u["speaker_eff"] = u["speaker"] or last
    for n, u in enumerate(units):
        upos = n / max(1, len(units) - 1)
        kr = speaker_kr(u["speaker_eff"], gl) if u["speaker_eff"] else None
        if not kr or kr not in by_speaker:
            out.append({**u, "kr_speaker": kr, "cands": []})
            continue
        nouns = nouns_kr(u["jp"], gl) - {
            kr
        }  # 화자 이름은 공유 고유명사로 안 센다(같은 화자면 늘 겹친다)
        L = kana_len(u["jp"])
        scored = []
        for r in by_speaker[kr]:
            shared = sum(1 for w in nouns if w in r["t"])
            ratio = len(r["t"]) / max(1, L)  # 한국어 글자 / 가나 글자 — 대략 0.5~0.8
            s_len = max(0.0, 1 - abs(ratio - 0.65) / 0.65)
            s_pos = max(0.0, 1 - abs(r["pos"] - upos) / 0.25)
            score = 2.0 * shared + s_len + s_pos
            if u.get("kana_len", 0) >= 12 and r["t"].count("\n") == 0 and len(r["t"]) < 6:
                score -= 1
            scored.append((round(score, 2), r["scn"], r["idx"], r["t"]))
        scored.sort(reverse=True)
        out.append({**u, "kr_speaker": kr, "nouns": sorted(nouns), "cands": scored[:5]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--dump", action="store_true")
    ap.add_argument(
        "--readings", action="store_true", help="PS1 일문 읽기(pykakasi) ↔ SFC 가나 유사도 정렬"
    )
    a = ap.parse_args()
    if a.readings:
        readings_main(a.dump)
        return
    gl = load_glossary()
    # 비교 단위는 조각(END 사이, 이름 인라인) — units.py --dump 가 만든다
    units = json.loads((common.OUT_DIR / "units" / "segments.json").read_text(encoding="utf-8"))
    units = [u for u in units if u["kana_len"] >= 4]  # 제어만 있는 조각은 뺀다
    ps1 = load_ps1()
    res = match(units, ps1, gl)
    with_sp = [u for u in res if u["speaker_eff"]]
    mapped = [u for u in with_sp if u["kr_speaker"]]
    unmapped = collections.Counter(u["speaker_eff"] for u in with_sp if not u["kr_speaker"])
    with_noun = sum(1 for u in res if u.get("nouns"))
    print(f"고유명사 있는 단위 {with_noun:,}")
    strong = [u for u in mapped if u["cands"] and u["cands"][0][0] >= 2.5]
    mid = [u for u in mapped if u["cands"] and 1.5 <= u["cands"][0][0] < 2.5]
    print(
        f"단위 {len(res):,} · 화자 있음 {len(with_sp):,} · 화자 매핑 {len(mapped):,} · 미매핑 화자 {dict(unmapped)}"
    )
    print(
        f"후보 강함(고유명사 겹침 포함, ≥2.5) {len(strong):,} · 중간 {len(mid):,} · PS1 창 {len(ps1):,}"
    )
    if a.dump:
        d = common.OUT_DIR / "tm"
        d.mkdir(parents=True, exist_ok=True)
        (d / "candidates.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=0), encoding="utf-8"
        )
        print("→", d / "candidates.json")
    if a.stats:
        for u in strong[:6]:
            print(
                "  -",
                u["kr_speaker"],
                u["jp"].replace("\n", "/")[:40],
                "→",
                u["cands"][0][3][:40],
                u["cands"][0][0],
            )


# ── 읽기 기반 정렬 — PS1 일문을 히라가나로 내려 SFC 가나와 문자열 유사도로 짝을 찾는다 ───────────
# pykakasi(사전 기반 한자 읽기)는 오독이 있지만(お前 → おぜん) 2-gram + 순서 비교는 그 정도 잡음을 견딘다.
PS1_JP_CANDIDATES = [p.parent / "work" / "derived" / "scn_jp" for p in _PS1_CANDIDATES]
PS1_JP = next((p for p in PS1_JP_CANDIDATES if p.is_dir()), PS1_JP_CANDIDATES[0])
_STRIP = re.compile(r"<[^<>]*>|\{[cn]\}|[\s、。「」!?！？…・·ー〜～,.\-]")


def to_hira(s: str) -> str:
    out = []
    for ch in s:
        o = ord(ch)
        if 0x30A1 <= o <= 0x30F6:  # 가타카나 → 히라가나
            out.append(chr(o - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def sfc_key(jp: str) -> str:
    """SFC 조각 디코드 → 비교용 히라가나(사전 이름은 중괄호를 벗겨 그대로 둔다)."""
    s = re.sub(r"[{}]", "", jp)
    return to_hira(_STRIP.sub("", s))


def ps1_readings() -> list[dict]:
    """PS1 ED1 JP 창 → 히라가나 키. 느리니(pykakasi) 결과를 work/derived/tm/ 에 캐시한다."""
    cache = common.OUT_DIR / "tm" / "ps1_hira.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    import pykakasi

    kk = pykakasi.kakasi()
    rows = []
    for f in sorted(PS1_JP.glob("ED1SCN*.json")):
        scn = int(re.search(r"SCN(\d+)", f.name).group(1))
        d = json.loads(f.read_text(encoding="utf-8"))
        for e in d["entries"]:
            if e.get("kind") != "block":
                continue
            raw = _STRIP.sub("", e["text"])
            hira = "".join(x["hira"] for x in kk.convert(raw))
            rows.append({"scn": scn, "idx": e["entry_id"], "hira": to_hira(hira), "jp": e["text"]})
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def bigrams(s: str) -> set[str]:
    return {s[i : i + 2] for i in range(len(s) - 1)}


def align_by_reading(segs: list[dict], ps1: list[dict], top: int = 25) -> list[dict]:
    import difflib

    index = collections.defaultdict(list)
    for j, r in enumerate(ps1):
        for g in bigrams(r["hira"]):
            index[g].append(j)
    out = []
    for s in segs:
        key = sfc_key(s["jp"])
        if len(key) < 6:
            out.append({**s, "key": key, "best": None})
            continue
        hits = collections.Counter()
        for g in bigrams(key):
            for j in index.get(g, ()):
                hits[j] += 1
        cands = []
        for j, _n in hits.most_common(top):
            r = ps1[j]
            ratio = difflib.SequenceMatcher(None, key, r["hira"], autojunk=False).ratio()
            cands.append((round(ratio, 3), r["scn"], r["idx"]))
        cands.sort(reverse=True)
        out.append({**s, "key": key, "best": cands[0] if cands else None, "cands": cands[:3]})
    return out


def readings_main(dump: bool) -> None:
    segs = json.loads((common.OUT_DIR / "units" / "segments.json").read_text(encoding="utf-8"))
    ps1 = ps1_readings()
    kr = {(r["scn"], r["idx"]): r for r in load_ps1()}
    res = align_by_reading(segs, ps1)
    scored = [x for x in res if x["best"]]
    hi = [x for x in scored if x["best"][0] >= 0.7]
    mid = [x for x in scored if 0.5 <= x["best"][0] < 0.7]
    print(
        f"조각 {len(res):,}(비교 가능 {len(scored):,}) · PS1 창 {len(ps1):,} · 유사도 ≥0.7 {len(hi):,} · 0.5~0.7 {len(mid):,}"
    )
    byid = {(r["scn"], r["idx"]): r for r in ps1}
    for x in hi[:5] + mid[:3]:
        s_, i = x["best"][1], x["best"][2]
        print(
            f"  {x['best'][0]:.2f} {x['key'][:28]} ↔ {byid[(s_, i)]['hira'][:28]} → {kr.get((s_, i), {}).get('t', '')[:30]}"
        )
    if dump:
        d = common.OUT_DIR / "tm"
        rows = []
        for x in res:
            b = x["best"]
            rows.append(
                {
                    "seg": x["seg"],
                    "addr": x["addr"],
                    "jp": x["jp"],
                    "ratio": b[0] if b else None,
                    "ps1": f"SCN{b[1]}:{b[2]}" if b else None,
                    "kr": kr.get((b[1], b[2]), {}).get("t") if b else None,
                }
            )
        (d / "by_reading.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8"
        )
        print("→", d / "by_reading.json")


if __name__ == "__main__":
    main()
