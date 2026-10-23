"""음성 자막 편집기 편집값 → `data/opening_sub.json` · `data/ending_sub.json` (마스터 10-18).

    python3 games/pce-ed2/tools/subeditor_apply.py <edits 폴더> [--write]

`<edits 폴더>` = ArtifactData 로 `edits` 컬렉션을 `out_dir` 에 받은 폴더(문서마다 JSON 한 개). 기본은 **무엇이 바뀌는지 보기만** 하고,
`--write` 를 주면 두 JSON 에 쓴다. 쓴 뒤 빌드 게이트(두 `build_pages` + 오프닝 `plan`)를 바로 돌려 예산·줄 폭·쪽 수 위반이면 되돌린다.
편집 문서 꼴: `{clip: "open"|"end", idx, kr, spk, ts, te, cuts, comment, reply}` — 바뀐 항목만 들어 있다.
화자는 롬에 영향이 없는 메모라 `speaker` 키로만 적는다(빌드는 모르는 키를 무시한다).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ending_sub as e
import opening_sub as o

FILES = {"open": o.SUBS, "end": e.SUBS}


def load_edits(folder: Path) -> list[dict]:
    out = []
    for p in sorted(folder.rglob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        d = d.get("data", d) if isinstance(d, dict) else d
        if isinstance(d, dict) and d.get("clip") in FILES and "idx" in d:
            out.append(d)
    return out


def apply_edits(scripts: dict, edits: list[dict]) -> list[str]:
    log = []
    for ed in edits:
        sub = scripts[ed["clip"]]["subs"][ed["idx"]]
        if "kr" in ed:
            log.append(f"{ed['clip']}#{ed['idx'] + 1} 문안: {sub['text']!r} → {ed['kr']!r}")
            sub["text"] = ed["kr"].rstrip("\n")
        if "ts" in ed:
            log.append(f"{ed['clip']}#{ed['idx'] + 1} t0 {sub['t0']} → {ed['ts']}")
            sub["t0"] = ed["ts"]
        if "te" in ed:
            log.append(f"{ed['clip']}#{ed['idx'] + 1} t1 {sub['t1']} → {ed['te']}")
            sub["t1"] = ed["te"]
        if "cuts" in ed:
            log.append(f"{ed['clip']}#{ed['idx'] + 1} cuts {sub.get('cuts')} → {ed['cuts']}")
            if ed["cuts"]:
                sub["cuts"] = ed["cuts"]
            else:
                sub.pop("cuts", None)
        if "spk" in ed:
            log.append(f"{ed['clip']}#{ed['idx'] + 1} 화자 → {ed['spk']!r}")
            if ed["spk"]:
                sub["speaker"] = ed["spk"]
            else:
                sub.pop("speaker", None)
        if ed.get("comment"):
            log.append(f"{ed['clip']}#{ed['idx'] + 1} 코멘트: {ed['comment']!r}")
    return log


def gate(scripts: dict) -> None:
    o.build_pages(scripts["open"])
    e.build_pages(scripts["end"])


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    edits = load_edits(Path(args[0]))
    scripts = {k: json.loads(p.read_text(encoding="utf-8")) for k, p in FILES.items()}
    log = apply_edits(scripts, edits)
    print("\n".join(log) or "바뀐 것 없음")
    if "--write" not in sys.argv:
        return
    gate(scripts)  # 위반이면 여기서 AssertionError — 파일은 아직 안 건드렸다
    for k, p in FILES.items():
        p.write_text(json.dumps(scripts[k], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("썼다 — 빌드 게이트 통과(두 build_pages)")


if __name__ == "__main__":
    main()
