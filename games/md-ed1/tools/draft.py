"""손으로 쓸 자리의 **작업표** — 원문 + 앞뒤 문맥 + 화자 + PS1 근접 후보.

    python3 tools/draft.py            # work/review/draft/NNN.txt (전 블록)
    python3 tools/draft.py --block 5  # 그 블록만
    python3 tools/draft.py --stats    # 블록별 남은 스트림 수만
    python3 tools/draft.py --propose  # 초벌(textmap/draft_md_only.json) → 스트림별 제안

PS1 재사용이 못 닿는 자리를 모은다. 2026-09-07 기준 **419 스트림**인데 셋으로 갈린다 —
**온문장 266**(고유 240) · **조각 141**(고유 72, 엔진이 이름 삽입 둘레로 이어 붙이는 토막) ·
**글자 아님 12**. 🔴 조각을 문장으로 보고 옮기면 안 된다(`docs/status.md` 「손으로 쓸 자리」).

⚠ **원문이 들어 있다 — `work/review/` 밖으로 내보내지 않는다**(루트 `CLAUDE.md` 「저작권」).

왜 표를 따로 내나 — `rpg-translate` §3-0 이 「**앞뒤 문맥을 먼저 읽는다**」를 첫 항으로 못 박는다.
한 스트림만 보고 옮기면 **경어 등급도 종결 부호도 틀린다**(상대가 누구인지, 방금 무슨 말이
오갔는지에 달렸다). 그래서 표에 **앞뒤 스트림을 같이 싣는다.**

인물·말투 정본은 PS1 쪽이다 — `games/ps1-ed1+2/docs/ed1-story-bible.md`(같은 이야기다).
"""

import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import check_josa
import common
import ps1_reuse as R
import scene
import textmap

OUT = common.REVIEW_DIR / "draft"
# {원문 해시: {"ours", "state"}} — 손으로 쓴 초벌.
# 🔴 **커밋한다.** 판단이 담긴 것은 `work/` 가 아니라 소스다(루트 「제1 원칙」). 열쇠가 **해시**라
# 원문이 안 남으므로 저작권 규약과도 어긋나지 않는다(`textmap/*.json` 과 같은 꼴).
# ⚠ 그래도 **정본이 아니다** — 빌드는 이 파일을 안 읽는다. 정본에는 `--propose` → 유저 판정 →
# `ps1_reuse --apply` 로만 들어간다.
DRAFTS = common.GAME_DIR / "textmap" / "draft_md_only.json"
PROPOSAL = OUT / "draft_proposal.json"
CTX = 2  # 앞뒤로 실을 스트림 수


def key(jp: str) -> str:
    """원문 → 초벌 열쇠. **정규화한 원문의 sha1** 이라 같은 대사면 자리마다 같은 문안이 간다.

    ⚠ 열쇠를 해시로 두는 건 저작권 때문이다 — 커밋되는 파일에 원문을 남기지 않는다
    (루트 `CLAUDE.md` 「저작권」). 그래서 초벌 파일은 커밋해도 된다.
    """
    return hashlib.sha1(R.norm(jp).encode()).hexdigest()[:10]


def propose() -> None:
    """초벌을 **같은 원문을 쓰는 모든 스트림**에 펼친다 — 정본은 안 건드린다."""
    if not DRAFTS.exists():
        raise SystemExit(f"초벌이 없다: {DRAFTS}")
    drafts = json.loads(DRAFTS.read_text(encoding="utf-8"))
    persons = R.names_table()
    d = common.rom()
    bl = archives.blocks(d, archives.ARCHIVES["script"][0])
    out: dict[str, dict[str, dict[str, str]]] = {}
    skew: list[str] = []
    pair: list[str] = []
    hit = 0
    for n, (_s, b, _e) in enumerate(bl):
        mod = scene.parse_module(b)
        p = textmap.SCRIPT_DIR / f"{n:03d}.json"
        cur = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"streams": {}}
        for off in sorted(mod.streams):
            st = mod.streams[off]
            k = f"{off:04x}"
            if cur["streams"].get(k, {}).get("ours") or R.header_text(st) is not None:
                continue
            speakers, pages = R.stream_pages(st)
            if not pages:
                continue
            speakers = [sp for sp in speakers if sp]
            if any(sp not in persons for sp in speakers) or R.name_changes_midpage(st):
                continue
            v = drafts.get(key("".join(pages)))
            if not v or not v.get("ours"):
                continue
            kr = v["ours"].split("\f")
            if len(kr) != len(pages):
                # 🔴 쪽 수가 안 맞으면 **넣지 않는다** — 초벌이 엉뚱한 쪽에 실리거나 마지막 쪽이
                # 통째로 빈다(원문 쪽 수와 1:1 이어야 한다). 실측 2/46 이 이랬다.
                skew.append(f"{n:03d}[{k}] 원문 쪽 {len(pages)} ≠ 초벌 {len(kr)}")
                continue
            ours = R.ours_for(st, kr, [persons[sp] for sp in speakers])
            # 조사 짝은 **펼친 뒤에** 본다(정본 게이트는 골격 없는 조각을 못 본다 — `check_josa` 주석).
            # 🔴 어긋나면 **넣지 않는다.** 한 쪽 안에 제어코드로 갈린 본문 토막이 둘 이상이면
            # `ours_for` 가 문안을 **첫 토막에 몰아넣어** 아이템 삽입(`<0e>`)보다 앞에 놓는다 —
            # 그런 자리는 원문 열쇠로 못 쓰고 **스트림마다 따로 써야** 한다(실측 6).
            bad = [
                m
                for m in check_josa.HOOK.finditer(ours)
                if not (
                    ours[: m.start()].endswith(f"<{check_josa.PAIRED[m.group(1)]}>")
                    or (m.group(1) == "eb" and re.search(r"<09[0-9a-f]{2}>$", ours[: m.start()]))
                )
            ]
            if bad:
                pair.append(
                    f"{n:03d}[{k}] <{bad[0].group(1)}…> 앞이 "
                    f"<{check_josa.PAIRED[bad[0].group(1)]}> 가 아니다 — 스트림마다 따로 써야 한다"
                )
                continue
            out.setdefault(f"{n:03d}", {})[k] = {
                "ours": ours,
                "src": "draft:" + v.get("state", "초벌"),
            }
            hit += 1
    PROPOSAL.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for w in skew:
        print(f"    ⏭ 쪽 수가 안 맞아 건너뜀 — {w}")
    for w in pair:
        print(f"    ⏭ 조사 짝이 안 맞아 건너뜀 — {w}")
    print(f"  초벌 {len(drafts)} 종 → 스트림 {hit} · 블록 {len(out)} → {PROPOSAL}")
    print("  ⚠ 사람 검토 전이다 — 정본에 넣기 전에 `rpg-translate` §4 축 일곱으로 훑는다.")


def main() -> None:
    if "--propose" in sys.argv:
        return propose()
    stats = "--stats" in sys.argv
    only = R._only()
    cp = R.corpus()
    keys = list(cp)
    persons = R.names_table()
    d = common.rom()
    bl = archives.blocks(d, archives.ARCHIVES["script"][0])
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for n, (_s, b, _e) in enumerate(bl):
        if only is not None and n not in only:
            continue
        mod = scene.parse_module(b)
        p = textmap.SCRIPT_DIR / f"{n:03d}.json"
        cur = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"streams": {}}
        offs = sorted(mod.streams)
        todo = []
        for i, off in enumerate(offs):
            st = mod.streams[off]
            key = f"{off:04x}"
            if cur["streams"].get(key, {}).get("ours"):
                continue
            if R.header_text(st) is not None:
                continue
            speakers, pages = R.stream_pages(st)
            if not pages:
                continue
            if R.match_pages(pages, cp) is not None:
                continue  # 물려받을 수 있는 자리 — 제안 파일이 맡는다
            todo.append((i, off, speakers, pages))
        if not todo:
            continue
        total += len(todo)
        if stats:
            print(f"  {n:03d}: {len(todo)}")
            continue
        lines = [
            f"# 블록 {n:03d} — 손으로 쓸 스트림 {len(todo)}",
            "# 인물·말투: games/ps1-ed1+2/docs/ed1-story-bible.md · 표기: shared/canon/nouns/eiyuu.json",
            "# ⚠ 초벌은 사람 검토 전이다. 정본에 넣기 전에 `rpg-translate` §4 축 일곱으로 훑는다.",
            "",
        ]
        for i, off, speakers, pages in todo:
            lines.append(
                f"── {off:04x}  화자={' · '.join(persons.get(s, s) for s in speakers) or '(없음)'}"
            )
            for j in range(max(0, i - CTX), i):
                _sp, pg = R.stream_pages(mod.streams[offs[j]])
                if pg:
                    lines.append(f"   앞  {offs[j]:04x}  {' / '.join(pg)[:100]}")
            for pi, pg in enumerate(pages):
                lines.append(f"   원문 쪽{pi}  {pg}")
                near = difflib.get_close_matches(R.norm(pg), keys, n=1, cutoff=0.55)
                if near:
                    lines.append(f"        ≈PS1  {cp[near[0]][2]}")
            for j in range(i + 1, min(len(offs), i + 1 + CTX)):
                _sp, pg = R.stream_pages(mod.streams[offs[j]])
                if pg:
                    lines.append(f"   뒤  {offs[j]:04x}  {' / '.join(pg)[:100]}")
            lines.append("   초벌  ")
            lines.append("")
        (OUT / f"{n:03d}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"  손으로 쓸 스트림 {total}" + ("" if stats else f" → {OUT}"))


if __name__ == "__main__":
    main()
