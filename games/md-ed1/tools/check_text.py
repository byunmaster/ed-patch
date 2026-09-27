"""문안 품질 게이트 — **원문 잔존 · 부호 규칙 · 표기 일치** 셋을 결정적으로 본다.

구조 검사(`archives`·`scene`·`captions`·`battle`)는 「바이트가 제자리에 들어갔나」를 보고,
`build.py` 는 「칸을 넘었나」를 본다. 그 둘 다 초록인데 **화면 글이 틀리는** 자리가 남는다 —
정본에 일본어가 섞였거나, 부호가 우리 규칙과 다르거나, 같은 이름을 다른 표기로 쓴 경우다.
PS1 쪽(`check_punct`·`check_jp_leak`·`check_terms`)이 같은 이유로 검사기를 40개 두고 있다.

  python3 tools/check_text.py        # 요약 + 위반 목록(있으면 실패)
  python3 tools/check_text.py -v     # 커버리지까지
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import ast

import battle
import common

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
# 칸이 표기를 이기는 자리 — 근거와 함께 적는다(2026-09-06)
TERM_EXCEPTIONS = {
    "聖なる杖": "아이템 칸 14B — PS1 「성스러운 지팡이」는 15B",
    "ダイヤの杖": "아이템 칸 14B — PS1 「다이아의 지팡이」는 15B",
    "ギルモアの虹": "아이템 칸 14B — PS1 「길모아의 무지개」는 15B",
    "狼の口": "마스터 확정 2026-09-28 — MD·PS1 둘 다 「늑대의입」(HUD·배너 붙임). PS1 브랜치는"
    " 이미 그렇고, 정본 대조가 물고 오는 건 main 에 머지돼 있는 **옛 PS1 사본**이라 갈려 보일"
    " 뿐이다 — ps1-ed1+2 가 라운드 끝에 머지되면 맞춰지니 그때 이 예외를 지운다",
}
# 판정 대기 — 표기가 갈린 걸 **알고** 마스터 판정을 기다리는 자리. 실패로 치지 않고 목록만 보인다.
# 🔴 실패로 두면 `check.sh`(set -e)가 **여기서 멈춰 뒤 검사가 통째로 안 돈다** — 2026-09-16~27 실제로
# 조판 지문·남은 일본어·빌드 게이트가 열하루 동안 안 돌았다(09-27 발견). 판정이 나면 여기서 뺀다.
PENDING = {
    "買いたい": "상점 선택지 — status 「마스터 판정 대기」 3(영업 도구점 화면 미확인)",
    "売りたい": "상점 선택지 — 같은 판정",
}
MAPS = {
    "names": "textmap/names.json",
    "monsters": "textmap/monsters.json",
    "sysmsg": "textmap/sysmsg.json",
    "captions": "textmap/captions.json",
    "battle": "textmap/battle.json",
}


def _entries() -> list[tuple[str, str, str, str]]:
    """[(정본, 열쇠, 원문, 우리 문안)] — 표는 두 겹이라 펼친다."""
    out = []
    for name, rel in MAPS.items():
        p = common.GAME_DIR / rel
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for k, v in d.items():
            if isinstance(v, dict) and "ours" in v:
                out.append((name, k, v.get("jp", ""), v.get("ours", "")))
            elif isinstance(v, dict):  # names.json: 표 이름 → 항목
                for kk, vv in v.items():
                    if isinstance(vv, dict):
                        out.append((f"{name}:{k}", kk, vv.get("jp", ""), vv.get("ours", "")))
    for p in sorted((common.GAME_DIR / "script").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for off, e in d.get("streams", {}).items():
            out.append((f"script:{p.stem}", off, "", e.get("ours", "")))
    return out


def _ps1_canon() -> dict[str, str]:
    """PS1 정본(도구 안 표) + 공용 용어집 → {JP: 한국어}. PS1 이 없으면 용어집만."""
    canon: dict[str, str] = {}
    gl = common.ROOT / "shared" / "glossary" / "eiyuu.json"
    if gl.exists():
        for cat in json.loads(gl.read_text(encoding="utf-8"))["categories"].values():
            if isinstance(cat, dict):
                canon.update({k: v for k, v in cat.items() if isinstance(v, str)})
    ps1 = common.ROOT / "games" / "ps1-ed1+2" / "tools"
    for f, names in (("patch_items.py", {"NAMES", "MONSTERS"}), ("patch_sys_ui.py", {"PLACES"})):
        p = ps1 / f
        if not p.exists():
            continue
        for node in ast.parse(p.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in names:
                try:
                    v = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):  # 계산이 든 표는 건너뛴다
                    continue
                canon.update(dict(v))
    return {unicodedata.normalize("NFKC", k).replace(" ", ""): v for k, v in canon.items()}


def main(verbose: bool = False) -> None:
    ents = _entries()
    canon = _ps1_canon()
    mp = common.GAME_DIR / "textmap" / "monsters.json"
    monsters = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    leaks, puncts, terms, pending = [], [], [], []
    done = {}
    for src, key, jp, ours in ents:
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
        if jp:
            want = canon.get(unicodedata.normalize("NFKC", jp).replace(" ", ""))
            if want and want != ours and jp not in TERM_EXCEPTIONS:
                msg = f"{src}[{key}] {jp}: {ours!r} ≠ 정본 {want!r}"
                (pending if jp in PENDING else terms).append(msg)
    print(
        f"  문안 검사 — 항목 {len(ents)} · 원문 잔존 {len(leaks)} · 부호 {len(puncts)} · 표기 {len(terms)}"
        f" · 판정 대기 {len(pending)}"
    )
    for p in pending:
        print("    ⏸ " + p)
    if verbose:
        for src, (tot, fill) in sorted(done.items()):
            print(f"     {src:22s} {fill}/{tot}")
        for jp, why in TERM_EXCEPTIONS.items():
            print(f"     예외 {jp}: {why}")
    bad = leaks + puncts + terms
    if bad:
        raise SystemExit("\n".join("    " + b for b in bad))


if __name__ == "__main__":
    main("-v" in sys.argv)
