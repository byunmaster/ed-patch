"""이미 번역한 문안이 PC-98 에 얼마나 붙나 — **번역량의 실제 크기**를 잰다.

`games/ps1-ed1+2/line_dict.json` 은 「타이틀을 넘어가는 유일한 산출물」이다(JP 원문 해시 →
우리 문안). 열쇠 규약은 `shared/text/line_key.py` 가 정본이라 여기서 다시 만들지 않는다.

⚠ **이 스크립트는 재지 붙이지 않는다.** 실제로 붙이는 층은 여러 게임이 쓰므로 `shared/`
승격 후보고, 그건 **main 에서** 한다(status.md 「남은 일」).

⚠ 사전은 **다른 브랜치의 파일**이라 이 워크트리엔 없다. `--dict` 로 경로를 준다.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
from text.line_key import key as line_key
from text.line_key import neutral

_SENT_END = "。！？!?"


def split_sentences(text: str) -> list[str]:
    """중립꼴로 만든 뒤 문장 부호에서 자른다. 3자 미만은 버린다(잡음)."""
    body = neutral(text)
    out, cur = [], ""
    for ch in body:
        cur += ch
        if ch in _SENT_END:
            if len(cur) >= 3:
                out.append(cur)
            cur = ""
    if len(cur) >= 3:
        out.append(cur)
    return out


def sentences_of_ps1(jp_dir: Path) -> set[str]:
    out: set[str] = set()
    for path in sorted(jp_dir.glob("*.json")):
        blob = json.loads(path.read_text(encoding="utf-8"))
        for e in blob.get("entries", []):
            if e.get("text"):
                out.update(split_sentences(e["text"]))
    return out


def pc98_lines() -> list[str]:
    out = []
    for name in ("scn_jp/scenario", "scn_jp/combat", "sys_jp/event", "sys_jp/program"):
        path = common.OUT_DIR / f"{name}.json"
        if not path.exists():
            raise SystemExit(f"덤프가 없다: {path}\n  tools/dump_scn.py · dump_sys.py 를 먼저.")
        for b in json.loads(path.read_text(encoding="utf-8")):
            out.append(normalise(b))
    return out


def normalise(block: dict) -> str:
    """덤퍼 표기를 열쇠가 아는 꼴로.

    🔴 **화자를 앞에 붙인다** — PS1·새턴 덤프는 `%c화자%c\n본문` 한 덩이라, 본문만으로
    열쇠를 만들면 같은 대사가 안 붙는다(실측: 붙는 줄 0.2%).
    """
    text = block["t"].replace("\\n", "\n").replace("<PAGE>", "").replace("<WAIT>", "")
    # 🔴 **꼬리 `%c` 를 빠뜨리면 열쇠가 통째로 안 맞는다.** PS1 블록은 `{c}화자{c}{n}본문{c}`
    #    로 **닫는 마커까지** 들어 있다. 중립꼴이 한 글자 달라 붙는 줄이 0.2% 로 보였다.
    if block.get("s"):
        return f"%c{block['s']}%c\n{text}%c"
    return f"{text}%c"


def main() -> int:
    ap = argparse.ArgumentParser()
    default = common.ROOT / "games" / "ps1-ed1+2" / "line_dict.json"
    ap.add_argument("--dict", default=str(default), help="line_dict.json 경로")
    ap.add_argument("--jp-dir", help="PS1 JP 덤프 폴더(work/derived/scn_jp) — 문장 단위 측정용")
    args = ap.parse_args()

    path = Path(args.dict)
    if not path.exists():
        raise SystemExit(
            f"사전이 없다: {path}\n"
            "  이 워크트리엔 없는 게 정상이다(다른 브랜치의 파일).\n"
            "  --dict 로 ps1-ed1+2 워크트리의 line_dict.json 을 가리킨다."
        )
    dic = json.loads(path.read_text(encoding="utf-8"))["lines"]

    lines = pc98_lines()
    uniq: dict[str, str] = {}
    for n in lines:
        if len(n.strip()) >= 2:
            uniq.setdefault(line_key(n), n)

    hit = {k for k in uniq if k in dic}
    hit_chars = sum(len(uniq[k]) for k in hit)
    all_chars = sum(len(v) for v in uniq.values())
    print(f"사전 {len(dic):,}줄 · PC-98 고유 {len(uniq):,}줄")
    print(
        f"  ① 블록 단위 적중 {len(hit):,} = {len(hit) / len(uniq):.1%}"
        f"  (글자 {hit_chars:,}/{all_chars:,} = {hit_chars / all_chars:.1%})"
    )

    # ② 문장 단위 — 블록 경계가 판마다 달라 ①이 눌린다. 문장으로 자르면 그 영향이 준다.
    if args.jp_dir:
        ps1 = sentences_of_ps1(Path(args.jp_dir))
        mine = Counter()
        for v in uniq.values():
            for sent in split_sentences(v):
                mine[sent] += 1
        common_sents = set(mine) & ps1
        got = sum(len(s) for s in common_sents)
        tot = sum(len(s) for s in mine)
        print(
            f"  ② 문장 단위 겹침 {len(common_sents):,}/{len(mine):,}"
            f"  (글자 {got:,}/{tot:,} = {got / tot:.1%})"
        )
    else:
        print("  ② 문장 단위는 --jp-dir 로 PS1 JP 덤프를 줘야 잰다")

    print("\n  ⚠ 둘 다 하한선이다 — 1989 원작과 1998 리메이크는 문안 자체가 다른 데가 있다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
