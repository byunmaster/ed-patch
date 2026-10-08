"""문안 품질 게이트 — **원문 잔존 · 부호 규칙 · 이름 자리** 셋을 결정적으로 본다.

구조 검사(`archives`·`scene`·`captions`·`battle`)는 「바이트가 제자리에 들어갔나」를 보고,
`build.py` 는 「칸을 넘었나」를 본다. 그 둘 다 초록인데 **화면 글이 틀리는** 자리가 남는다 —
정본에 일본어가 섞였거나, 부호가 우리 규칙과 다르거나, 이름 자리가 풀리지 않는 경우다.
고유명사 표기 대조는 여기 없다 — 공용 `scripts/check/check_names.py`(어댑터 `names_corpus.py`)가 한다.
PS1 쪽(`check_punct`·`check_jp_leak`·`check_terms`)이 같은 이유로 검사기를 40개 두고 있다.

  python3 tools/check_text.py        # 요약 + 위반 목록(있으면 실패)
  python3 tools/check_text.py -v     # 커버리지까지
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import battle
import common
import dict_names
import field_names
import halfspace

TAG = re.compile(r"<[^>]*>")
NAME_TAG = re.compile(r"\{([^{}|]+)(?:\|[^{}]+)?\}")  # 전투 문안의 몬스터 이름 자리(빌드가 채운다)
KANA_KANJI = re.compile(r"[぀-ヿ㐀-鿿]")
# 부호 규칙(유저 확정 2026-09-05): 온점·쉼표·공백은 반각, 「…」은 전각 하나, 「…」 뒤에 온점 없음
BAD_PUNCT = {
    "。": "반각 온점 `.`",
    "、": "반각 쉼표 `,`",
    "，": "반각 쉼표 `,`",
    "．": "반각 온점 `.`",
    "　": "반각 공백",
    "！": "반각 `!`",
    "？": "반각 `?`",
    "‥": "「…」 하나",
}
MAPS = {
    "sysmsg": "textmap/sysmsg.json",
    "captions": "textmap/captions.json",
    "battle": "textmap/battle.json",
}


def _entries() -> list[tuple[str, str, str, str]]:
    """[(정본, 열쇠, 원문, 우리 문안)] — 표는 두 겹이라 펼친다."""
    out = []
    for cat, tbl in dict_names.names().items():  # 표 이름 → 항목 (사전·정본에서 읽은 값 포함)
        for kk, vv in tbl.items():
            out.append((f"names:{cat}", kk, vv.get("jp", ""), halfspace.plain(vv.get("ours", ""))))
    for jp, v in battle.monsters(common.rom()).items():
        out.append(("monsters", jp, jp, v.get("ours", "")))
    for i, kr, _extra, jp in field_names.ENTRIES:  # 입장 배너 46칸(사전에서 읽은 값)
        out.append(("banner", f"{i:02d}", jp, kr))
    for blk, tbl in field_names.DEST.items():  # 블록 92·93 목적지 표
        for i, (jp, kr) in enumerate(tbl):
            out.append((f"dest:{blk}", f"{i:02d}", jp, kr))
    for name, rel in MAPS.items():
        p = common.GAME_DIR / rel
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for k, v in d.items():
            if isinstance(v, dict) and "ours" in v:
                out.append((name, k, v.get("jp", ""), v.get("ours", "")))
            elif isinstance(v, dict):  # 표 이름 → 항목
                for kk, vv in v.items():
                    if isinstance(vv, dict):
                        out.append((f"{name}:{k}", kk, vv.get("jp", ""), halfspace.plain(vv.get("ours", ""))))
    for p in sorted((common.GAME_DIR / "script").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for off, e in d.get("streams", {}).items():
            out.append((f"script:{p.stem}", off, "", e.get("ours", "")))
    return out


def main(verbose: bool = False) -> None:
    ents = _entries()
    monsters = battle.monsters(common.rom())
    leaks, puncts, terms = [], [], []
    done = {}
    for src, key, _jp, ours in ents:
        tot, fill = done.setdefault(src, [0, 0])
        done[src] = [tot + 1, fill + (1 if ours else 0)]
        if not ours:
            continue
        text = TAG.sub("", ours)
        for nm in NAME_TAG.findall(
            text
        ):  # 이름 자리 — **빌드와 같은 판정**으로 푼다(정본 → 용어집)
            try:
                battle.kr_name(nm, monsters)
            except SystemExit:
                terms.append(f"{src}[{key}]: 이름 자리 {{{nm}}} 를 정본·용어집 어디서도 못 찾는다")
        text = NAME_TAG.sub("", text)
        if KANA_KANJI.search(text):
            leaks.append(
                f"{src}[{key}]: 원문이 남았다 {KANA_KANJI.findall(text)[:5]} — {text[:30]!r}"
            )
        for ch, why in BAD_PUNCT.items():
            if ch in text:
                puncts.append(f"{src}[{key}]: {ch!r} → {why} — {text[:30]!r}")
        if re.search(r"…\s*\.", text):
            puncts.append(f"{src}[{key}]: 「…」 뒤 온점 — {text[:30]!r}")
        if "..." in text:
            puncts.append(f"{src}[{key}]: `...` → 전각 「…」 — {text[:30]!r}")
    print(
        f"  문안 검사 — 항목 {len(ents)} · 원문 잔존 {len(leaks)} · 부호 {len(puncts)} · 이름 자리 {len(terms)}"
    )
    if verbose:
        for src, (tot, fill) in sorted(done.items()):
            print(f"     {src:22s} {fill}/{tot}")
    bad = leaks + puncts + terms
    if bad:
        raise SystemExit("\n".join("    " + b for b in bad))


if __name__ == "__main__":
    main("-v" in sys.argv)
