"""번역 정본 — **원문은 커밋하지 않는다.**

이 레포는 공개를 전제로 관리하므로 문장급 원문을 소스에 남기면 안 된다(루트 CLAUDE.md
「저작권」). 그래서 정본은 **자리(색인) + 우리 문안 + 원문 지문**만 담는다:

```
games/ps1-ed3+4/script/<disc>/<아카이브>_<멤버>.json
  {"archive": "/SCE0/SC000.DAT", "member": "..\\\\DATA\\\\FT0000.BIN",
   "lines": {"63": {"jp": "a3f1c2d4", "kr": "크리스티나。내일 떠날 준비는 다 했니？"}}}
```

- **색인**은 그 멤버의 조각 순서다(ED3=풀 순서 · ED4=표 순서, `scriptmap.parse`).
- 🔴 **`jp` 는 원문 sha1 앞 8자**다. 파서를 고치거나 원본이 바뀌어 색인이 밀리면
  **번역이 남의 자리에 붙는다** — 그 사고를 이 지문 하나가 잡는다(`--check`).
  새턴 ED3 이 같은 장치를 쓴다(`stamp_script.py`).

작업 흐름 — **번역은 `work/review/` 에서 하고 정본으로 옮긴다**:

```
python3 tools/script.py --disc ed3 --review   # 원문+우리문안 검토표 (⚠ 커밋 금지)
   … 검토표의 "kr" 을 채운다 …
python3 tools/script.py --disc ed3 --sync     # 검토표 → 정본 (kr 과 지문만 옮긴다)
python3 tools/script.py --disc ed3 --check    # 지문이 지금 원본과 맞나 (게이트)
```
"""

import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import scriptmap
import textenc
import typeset

SCRIPT_DIR = os.path.join(common.ROOT, "script")
STAMP_LEN = 8


def stamp(jp):
    return hashlib.sha1(jp.encode("utf-8")).hexdigest()[:STAMP_LEN]


def key_of(archive, member):
    """`/SCE0/SC000.DAT` + `..\\DATA\\FT0000.BIN` → `SC000_FT0000`."""
    a = os.path.basename(archive).rsplit(".", 1)[0]
    m = member.rsplit("\\", 1)[-1].rsplit(".", 1)[0]
    return re.sub(r"[^A-Za-z0-9_]", "_", f"{a}_{m}")


def canon_path(disc, key):
    return os.path.join(SCRIPT_DIR, disc, f"{key}.json")


def member_floors(segs):
    """{조각 색인: 폭 바닥} — **창 폭의 대용**(`typeset.budget` 의 `floor`).

    한 멤버의 **대사** 조각들은 같은 창에 나간다. 인게임 실측(2026-09-07)으로 그 창이 약 24칸
    인데 그 멤버의 원문 최대가 23칸이었다 — 원문이 창을 거의 꽉 쓴다는 뜻이라 대용이 된다.
    조각별 예산은 허수다: 같은 화자가 연달아 말하는 창이 4·19·15·21칸으로 널뛴다.

    🔴 **이름창은 아니다.** 「クリスの母」 자리에 「크리스 엄마」(6칸)를 넣었더니 화면에서
       `크리스` 로 **잘렸다** — 그 자리는 5칸 고정 필드다. 이름은 멤버 **앞머리 블록**에
       모여 있으므로(첫 문장 조각 앞) 거기까지는 바닥을 안 깐다.
    ⚠ 상점·메뉴 토막이 뒤에 섞이면 그것도 바닥을 받는다 — 짧은 자리를 길게 쓸 이유가 없어
      실해는 없지만, 그 창이 좁다는 게 드러나면 여기서 갈라야 한다.
    """
    w = max((max((len(x) for x in jp.split("\n")), default=0) for _, jp in segs), default=0)
    head = True
    out = {}
    for i, jp in segs:
        if head and ("\n" in jp or jp.rstrip().endswith(("。", "？", "！"))):
            head = False
        out[i] = 0 if head else w
    return out


def members(disc):
    """[(아카이브, 멤버, [(색인, 원문)…])] — 원본에서 그 자리에서 뽑는다."""
    out = []
    for path, (lba, size) in sorted(common.iso_files(disc).items()):
        if "/SC" not in path or not path.endswith(".DAT"):
            continue
        data = common.read_lba(disc, lba, size)
        try:
            _, ents = common.arc_parse(data)
        except common.ArchiveError:
            continue
        for nm, off, sz in ents:
            if not nm.endswith(".BIN") or sz < 8:
                continue
            try:
                info = scriptmap.parse(data[off : off + sz])
            except Exception:  # noqa: BLE001, S112 — 규격 밖 멤버는 check_script 가 센다
                continue
            segs = [
                (i, textenc.decode(codes, disc)) for i, (_, codes) in enumerate(info["segments"])
            ]
            if any(t.strip() for _, t in segs):
                out.append((path, nm, segs))
    return out


def load(disc):
    """{(아카이브, 멤버): {색인: {"jp":…, "kr":…}}}"""
    out = {}
    d = os.path.join(SCRIPT_DIR, disc)
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(d, fn), encoding="utf-8") as f:
            doc = json.load(f)
        out[(doc["archive"], doc["member"])] = {int(k): v for k, v in doc["lines"].items()}
    return out


def save(disc, archive, member, lines):
    """정본 한 파일. 빈 문안은 안 담는다 — 「아직 안 옮긴 자리」는 파일에 없는 것이다."""
    lines = {str(i): v for i, v in sorted(lines.items()) if v.get("kr")}
    p = canon_path(disc, key_of(archive, member))
    if not lines:
        if os.path.exists(p):
            os.remove(p)
        return
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(
            {"archive": archive, "member": member, "lines": lines}, f, ensure_ascii=False, indent=1
        )


def review_path(disc, key):
    return os.path.join(common.REVIEW_DIR, disc, f"{key}.json")


def write_review(disc):
    """검토표를 뽑는다 — 원문 + 우리 문안 + 조판 예산. ⚠ **커밋 금지**(원문이 들어 있다)."""
    canon = load(disc)
    n = 0
    for archive, member, segs in members(disc):
        have = canon.get((archive, member), {})
        rows = {}
        floors = member_floors(segs)
        for i, jp in segs:
            if not jp.strip():
                continue
            w, ln = typeset.budget(disc, jp, floors.get(i, 0))
            rows[str(i)] = {
                "jp": jp,
                "kr": have.get(i, {}).get("kr", ""),
                "budget": f"{w}칸 × {ln}줄",
            }
        if not rows:
            continue
        p = review_path(disc, key_of(archive, member))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(
                {"archive": archive, "member": member, "lines": rows},
                f,
                ensure_ascii=False,
                indent=1,
            )
        n += 1
    return n


def sync(disc):
    """검토표 → 정본. **kr 과 지문만** 옮긴다(원문은 안 담는다)."""
    src = {(a, m): {i: jp for i, jp in segs} for a, m, segs in members(disc)}
    moved = 0
    d = os.path.join(common.REVIEW_DIR, disc)
    if not os.path.isdir(d):
        raise SystemExit(f"검토표가 없다: {d}\n  먼저: script.py --disc {disc} --review")
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(d, fn), encoding="utf-8") as f:
            doc = json.load(f)
        jp_by_idx = src.get((doc["archive"], doc["member"]), {})
        lines = {}
        for k, row in doc["lines"].items():
            kr = (row.get("kr") or "").strip()
            if not kr:
                continue
            i = int(k)
            if i not in jp_by_idx:
                raise SystemExit(f"{fn}: 색인 {i} 가 원본에 없다 — 검토표가 낡았다")
            lines[i] = {"jp": stamp(jp_by_idx[i]), "kr": kr}
            moved += 1
        save(disc, doc["archive"], doc["member"], lines)
    return moved


def check(disc):
    """[사유] — 지문이 어긋났거나 조판을 넘긴 자리."""
    src = {(a, m): dict(segs) for a, m, segs in members(disc)}
    floors = {(a, m): member_floors(segs) for a, m, segs in members(disc)}
    bad = []
    n = 0
    for (archive, member), lines in sorted(load(disc).items()):
        jp_by_idx = src.get((archive, member))
        if jp_by_idx is None:
            bad.append(f"{member}: 원본에 없는 멤버")
            continue
        fl = floors[(archive, member)]
        for i, row in sorted(lines.items()):
            n += 1
            jp = jp_by_idx.get(i)
            if jp is None:
                bad.append(f"{member}[{i}]: 원본에 없는 자리")
                continue
            if stamp(jp) != row["jp"]:
                bad.append(f"{member}[{i}]: 원문 지문이 다르다 — 번역이 남의 자리에 붙었다")
                continue
            for v in typeset.violations(row["kr"], disc, jp=jp, floor=fl.get(i, 0)):
                bad.append(f"{member}[{i}]: {v}")
    return n, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--review", action="store_true", help="검토표를 뽑는다 (⚠ 커밋 금지)")
    ap.add_argument("--sync", action="store_true", help="검토표 → 정본")
    ap.add_argument("--check", action="store_true", help="지문·조판 (게이트)")
    a = ap.parse_args()
    common.verify_source(a.disc)
    if a.review:
        print(f"{a.disc}: 검토표 {write_review(a.disc)} 파일 → {common.REVIEW_DIR}  ⚠ 커밋 금지")
        return 0
    if a.sync:
        print(f"{a.disc}: 정본으로 옮긴 줄 {sync(a.disc)}")
        return 0
    n, bad = check(a.disc)
    total = sum(
        len(s) for _, _, segs in members(a.disc) for s in [[t for _, t in segs if t.strip()]]
    )
    print(f"{a.disc}: 번역 정본 {n:,}줄 / 원본 {total:,}줄 ({n * 100 // max(total, 1)}%)")
    for m in bad[:12]:
        print(f"  🔴 {m}")
    if len(bad) > 12:
        print(f"  … 그 밖 {len(bad) - 12}")
    if a.check:
        print(f"{a.disc}: 번역 정본 — {'🔴 어긋났다' if bad else '✅ 원본과 맞는다'}")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
