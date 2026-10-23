"""대사 보기 색인 — 캡처(`scene_sweep` 산출)에 정본 열쇠·원문·우리 문안·화자·캡처 경로를 붙인다(검수 세션용).

    python3 tools/sweep_index.py [--out DIR]     # DIR/index2.tsv (기본 .local/work/inbox/md-ed2/sweep/scene)

열: 모듈 | 구운 오프셋 | 정본 열쇠(script/<모듈>.json 의 스트림 키, 한글 문안 일치로 찾는다 — 없으면 -) | 원문(JP) | 우리 문안 | 화자 | 캡처(쪽별, 쉼표)
⚠ 원문(JP)이 든다 — 커밋 금지(`.local` 밖으로 안 낸다). 정본 키는 구운 롬의 스트림이 재배치돼 오프셋이 달라서 **문안 일치**로 잇는다(같은 문안이 여럿이면 첫 것).
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import headless
import scene

TAG = re.compile(r"<[0-9a-fA-F:]+>|[\s\f\n]+")


def norm(s: str) -> str:
    return TAG.sub("", s)


def main() -> None:
    out = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "sweep" / "scene"
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
    orig = {(b, k): m for b, k, m in archives.modules(common.rom())}
    rows = ["모듈\t구운오프셋\t정본키\t원문\t우리문안\t화자\t캡처"]
    seen = set()
    for line in (out / "index.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        mod, off, _txt, cnt, status = line.split("\t")
        if (mod, off) in seen:
            continue
        seen.add((mod, off))
        b, k = (int(x) for x in mod.split("-"))
        js = common.GAME_DIR / "script" / f"{b:03d}-{k}.json"
        streams = json.loads(js.read_text(encoding="utf-8"))["streams"] if js.exists() else {}
        want = norm(_txt)
        key = next(
            (
                sk
                for sk, v in streams.items()
                if want and norm(v.get("ours", "")).startswith(want[:40])
            ),
            "-",
        )
        jp = ours = spk = ""
        if key != "-":
            ours = streams[key]["ours"]
            m = re.match(r"<1e>([^<]*)<04>", ours)
            spk = m.group(1) if m else ""
            try:
                st = scene.parse_stream(orig[(b, k)], int(key, 16))
                jp = "".join(
                    t.raw.decode("cp932", "replace") for t in st.tokens if t.kind == "text"
                )
            except Exception:  # noqa: BLE001
                jp = ""
        caps = sorted((out / mod).glob(f"{off}_*.png"))
        rows.append(
            "\t".join(
                [
                    mod,
                    off,
                    key,
                    jp.replace("\n", " "),
                    ours.replace("\n", "⏎").replace("\f", "⏎⏎"),
                    spk,
                    ",".join(str(p.relative_to(out)) for p in caps),
                ]
            )
        )
    (out / "index2.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"{len(rows) - 1}행 → {out / 'index2.tsv'}")


if __name__ == "__main__":
    main()
