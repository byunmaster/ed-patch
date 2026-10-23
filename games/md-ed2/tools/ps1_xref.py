"""PS1 ED2 와 **정규화 원문이 완전히 같은** 문장 대조표 — 원문|우리|PS1|화자(MD)|화자(PS1)|같은가.

    python3 tools/ps1_xref.py [--out 경로]      # 기본 .local/work/inbox/md-ed2/ps1-xref.tsv (원문 포함 — 커밋 금지)

기준(관리자 10-18): 같은 원문(`dialog.norm`)·같은 화자는 PS1 문안으로 맞춘다. 문장은 `dialog.split_jp` · 한국어는 `split_kr`, 문장 수가 같을 때만 1:1 로 잇는다
(안 맞는 스트림은 「분할 불일치」로 센다 — 대조 못 한 몫). 화자는 스트림 머리 `<1e>…<04>` 의 첫 이름.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import dialog
import scene
import textmap

TAG = re.compile(r"<[^>]*>")
SPK = re.compile(r"<1e>(.*?)<04>")


def clean(s: str) -> str:
    return TAG.sub("", s.replace("\f", " ").replace("\x0c", " ")).strip()


def main() -> None:
    out = (
        Path(sys.argv[sys.argv.index("--out") + 1])
        if "--out" in sys.argv
        else (common.ROOT.parents[2] / ".local" / "work" / "inbox" / "md-ed2" / "ps1-xref.tsv")
    )
    idx = dialog.ps1_index()
    raw = dialog.ps1_raw()
    ps1_spk: dict[str, str] = {}  # (정규화 문장 → PS1 화자 일본어) — 같은 블록 화자
    for _name, _i, sj, body, _ks, _kt in raw["blocks"]:
        for p in dialog.split_jp(body):
            ps1_spk.setdefault(dialog.norm(p), dialog.norm(sj))
    rows, seen, same, diff, diff_spk, total, unsplit = [], 0, 0, 0, 0, 0, 0
    maps = textmap.load_all()
    for blk, k, b in archives.modules(common.rom()):
        m = maps.get((blk, k))
        if not m:
            continue
        mod = scene.parse_module(b)
        for key, ent in m["streams"].items():
            ours = ent.get("ours")
            st = mod.streams.get(int(key, 16))
            if not ours or st is None:
                continue
            jp = textmap.stream_to_text(st)
            spk_m = SPK.search(jp)
            spk_jp = dialog.norm(spk_m.group(1)) if spk_m else ""
            js = dialog.split_jp(clean(SPK.sub("", jp)))
            ks = dialog.split_kr(clean(SPK.sub("", ours)))
            total += len(js)
            if len(js) != len(ks):
                unsplit += len(js)
                continue
            for a, c in zip(js, ks, strict=True):
                hit = idx["sent"].get(dialog.norm(a))
                if not hit:
                    continue
                seen += 1
                p = dialog.fix_kr(hit[0][2])
                eq = dialog.norm(p) == dialog.norm(c) or p.replace(" ", "") == c.replace(" ", "")
                spk_ps1 = ps1_spk.get(dialog.norm(a), "")
                spk_same = (not spk_jp) or (not spk_ps1) or spk_jp == spk_ps1
                same += eq
                diff += not eq
                diff_spk += not spk_same
                rows.append(
                    f"{blk:03d}-{k}:{key}\t{a}\t{c}\t{p}\t{spk_jp}\t{spk_ps1}\t{'=' if eq else 'X'}\t{'화자같음' if spk_same else '화자다름'}\t{hit[0][0]}#{hit[0][1]}"
                )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "자리\t원문 문장\t우리\tPS1\t화자(MD)\t화자(PS1)\t일치\t화자\tPS1 출처\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )
    print(
        f"  PS1 동일 원문 문장 {seen} (전체 문장 {total} 중, 분할 불일치로 못 맞춘 {unsplit}) — 우리=PS1 {same} · 다름 {diff} · 그중 화자 다름 {diff_spk} → {out}"
    )


if __name__ == "__main__":
    main()
