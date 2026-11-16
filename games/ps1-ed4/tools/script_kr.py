"""대본(씬 대사) 번역 정본 — 조각 색인별 **원문 지문 + 한국어만** 담는다(원문 금지, 저작권).

```
script/<아카이브>__<멤버>.json    {"archive": "/O/SC400.DAT", "member": "..\\\\BIN\\\\OP00000.BIN",
                                    "segments": {"4": {"jp": "<지문10>", "kr": "자, 아빈. 아이멜."}, …}}
```

번역 단위는 **원본 조각**이다(조각 하나 = 한 줄 — `01` 로 이어진 줄들이 한 쪽을 이룬다). 번역자는 원본 조각 구조를 따라 문장을 쓰고, **빌드가 쪽 단위로 다시 조판한다**:
쪽(`typeset.windows`) 안의 모든 조각의 한국어를 이어 krwrap 으로 어절 단위 줄을 나누고, 각 줄을 24칸까지 공백으로 채워 첫 조각에 몰고 나머지 조각은 비운다(`typeset.page_segments`).
🔴 **쪽의 조각이 전부 번역됐을 때만** 그 쪽을 건드린다(절반만 바꾸면 한 쪽에 일본어와 한국어가 섞인다). 조각 하나짜리 쪽(이름창 포함)도 같은 길이다.
🔴 쪽이 3줄을 넘으면 `typeset.TypesetError` — 쪽 늘리기(`scriptedit.rewrite_message`) 몫이다(아직 안 연결 — 보고만 한다).

    python3 tools/script_kr.py show <아카이브 부분문자열> <멤버 부분문자열>    # 원문 대본을 쪽 구조로 보기(번역 작업용 — ⚠ 원문 출력)
    python3 tools/script_kr.py import <파일>                               # 번역 입력 — `## <아카이브> <멤버>` 머리글 뒤 `<조각 색인> <한국어>` 줄들
    python3 tools/script_kr.py trial <파일>                                # import 와 같은 입력을 **저장 없이** 조판 시험(문제 줄만 보고)
    python3 tools/script_kr.py notes                                       # 번역한 멤버 전부의 조판 사유(못 넣은 쪽)
    python3 tools/script_kr.py fill                                        # 같은 원문 조각에 이미 번역한 문안을 퍼뜨린다(auto 표시)
    python3 tools/script_kr.py todo [<아카이브 부분문자열>]                  # 멤버별 번역 진행(조각 수)
    python3 tools/script_kr.py check                                      # 지문·쪽 한도 (게이트)
"""

import glob
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import josa_build
import reinsert
import textenc
import typeset

SCRIPT_DIR = os.path.join(common.ROOT, "script")


def stamp(codes):
    return hashlib.sha1(struct.pack(f"<{len(codes)}H", *codes)).hexdigest()[:10]


def flat(archive, member):
    return archive.strip("/").replace("/", "_") + "__" + member.split("\\")[-1] + ".json"


def path_of(archive, member):
    return os.path.join(SCRIPT_DIR, flat(archive, member))


def load_all():
    """{(아카이브, 멤버): {조각 색인: {"jp","kr"}}}"""
    out = {}
    for p in sorted(glob.glob(os.path.join(SCRIPT_DIR, "*.json"))):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        out[(d["archive"], d["member"])] = {int(k): v for k, v in d["segments"].items()}
    return out


def save(archive, member, rows):
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    p = path_of(archive, member)
    rows = {str(k): v for k, v in sorted(rows.items()) if v.get("kr") is not None}
    if not rows:
        if os.path.exists(p):
            os.remove(p)
        return
    with open(p, "w", encoding="utf-8") as f:
        json.dump(
            {"archive": archive, "member": member, "segments": rows},
            f,
            ensure_ascii=False,
            indent=1,
        )
        f.write("\n")


def put(archive, member, mapping, segs, fixed=()):
    """`mapping` = {조각 색인: 한국어}. `segs` = 원본 조각 코드열 목록(지문 계산용). 기존 줄은 덮어쓴다. `fixed` = 줄을 **합치지 않는** 조각 색인(`"fix": 1` — 세로읽기 같은 줄 구조 연출)."""
    p = path_of(archive, member)
    rows = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            rows = {int(k): v for k, v in json.load(f)["segments"].items()}
    for i, kr in mapping.items():
        if not 0 <= i < len(segs):
            raise SystemExit(f"{member}: 조각 {i} 가 없다(총 {len(segs)})")
        rows[i] = {"jp": stamp(segs[i]), "kr": kr, **({"fix": 1} if i in fixed else {})}
    save(archive, member, rows)
    return len(mapping)


def member_bytes(archive, member, data=None):
    from shared.ps1 import gmf_arc

    data = data or common.read_file(archive)
    for n, o, s in gmf_arc.arc_parse(data)[1]:
        if n == member:
            return data[o : o + s]
    raise SystemExit(f"{archive} 에 {member} 가 없다")


def find_member(arc_part, mem_part):
    """부분문자열로 (아카이브, 멤버) 를 찾는다 — 대본 후보(`..\\BIN\\*.BIN`) 안에서."""
    import dump

    hits, exact = [], []
    for path, nm, data, off, sz in dump.script_members():
        if arc_part in path and mem_part in nm:
            hit = (path, nm, data[off : off + sz])
            hits.append(hit)
            if (
                nm.split("\\")[-1] == mem_part + ".BIN"
            ):  # `AT02000` 이 `AT02000A` 도 부분문자열로 잡는다 — 이름이 꼭 맞으면 그것만
                exact.append(hit)
    return exact or hits


def view_text(codes):
    """보기용 원문 — `EEEE a b`(숫자 그리기 연산: 값 = a+b, 스크립트에 박힌 리터럴)는 `⟦값⟧` 로 보인다. 번역은 그 수를 그냥 숫자로 쓴다."""
    out, i = [], 0
    while i < len(codes):
        if codes[i] == 0xEEEE and i + 2 < len(codes):
            out.append(f"⟦{codes[i + 1] + codes[i + 2]}⟧")
            i += 3
        else:
            out.append(textenc.decode([codes[i]]))
            i += 1
    return "".join(out)


def view(archive, member, mem, *, show_all=False):
    """원문 대본을 쪽 구조로 보여 준다(번역 작업용 — 원문 출력, 커밋·문서 인용 금지).

    한 줄 = 조각 하나(`#색인 원문`). 번역된 조각은 `=#색인 한국어` 로 줄여 보인다(`show_all` 이면 원문). 쪽(또는 끼움 연산이 가른 토막)이 바뀌면 `/` 한 줄,
    토막이 끼움 연산(이름·수 삽입, 색)에 걸려 있으면 `~`(그 토막은 조각마다 한 줄 — 합쳐 옮기지 않는다), 메시지가 바뀌면 빈 줄.
    """
    segs = reinsert.member_segments(mem)
    have = load_all().get((archive, member), {})
    print(f"# {archive} {member} — 조각 {len(segs)} · 번역 {len(have)}")
    seen = set()
    import speakers

    ents = speakers.entities(mem)
    streams = typeset.message_streams(mem)
    for mi_, msg in enumerate(typeset.windows(mem)):
        sp = speakers.speaker_of(mem, streams[mi_], ents) if mi_ < len(streams) else None
        if sp and sp[0] == "n" and sp[1] < len(segs):
            lab = have.get(sp[1], {}).get("kr") or view_text(segs[sp[1]])
        elif sp and sp[0] == "p":
            lab = speakers.PARTY[sp[1]] if sp[1] < len(speakers.PARTY) else f"파티{sp[1]}"
        elif sp:
            lab = f"개체{sp[1]}"
        else:
            lab = "?"
        print(f"▷ {lab}")
        for pi, pg in enumerate(msg):
            if pi:
                print("/")
            for k, i in enumerate(pg):
                seen.add(i)
                pre = "~" if getattr(pg, "rigid", False) and k == 0 else ""
                if i in have and not show_all:
                    print(f"{pre}={i} {have[i]['kr']}")
                else:
                    print(f"{pre}#{i} {view_text(segs[i])}")
        print()
    rest = [i for i in range(len(segs)) if i not in seen]
    if rest:
        print("-- 쪽 밖 조각:", ", ".join(f"#{i}:{view_text(segs[i])[:30]}" for i in rest[:60]))


def page_plan(mem, rows, *, table=None):
    """({조각 색인: 새 문안}, [사유…]) — 쪽 단위로 조판한 결과. 번역이 덜 된 쪽은 건너뛴다."""
    segs = reinsert.member_segments(mem)
    out, notes = {}, []
    for mi, msg in enumerate(typeset.windows(mem)):
        for pi, pg in enumerate(msg):
            texts = []
            ok = True
            for i in pg:
                if not segs[i]:
                    texts.append("")
                elif i in rows and rows[i].get("kr") is not None:
                    texts.append(rows[i]["kr"])
                else:
                    ok = False
                    break
            if not ok or not any(t.strip() for t in texts):
                continue
            try:
                if getattr(pg, "rigid", False) or any(rows.get(i, {}).get("fix") for i in pg):
                    new = typeset.rigid_segments(josa_build.rigid(texts))
                else:
                    new = typeset.page_segments(josa_build.flex(texts), len(pg))
            except typeset.TypesetError as e:
                notes.append(f"m{mi}.{pi} 조각 {pg}: {e}")
                continue
            for i, t in zip(pg, new, strict=True):
                out[i] = t
    # 🔴 쪽 밖 조각(메시지 스트림이 안 가리키는 것 — 머리 쌍 목록 등 다른 경로로 그려진다): 창 폭을 모르니 **원문 길이 안**에서 그대로 넣는다
    seen = {i for msg in typeset.windows(mem) for pg in msg for i in pg}
    for i, row in rows.items():
        if i in seen or row.get("kr") is None or i >= len(segs):
            continue
        kr = josa_build.flex([row["kr"]])[0]
        if len(kr) > max(
            len(segs[i]) + 4, 24
        ):  # 쪽 밖 조각은 어디 그려지는지 모른다 — 원문 길이 + 4 와 한 줄(24)
            notes.append(
                f"쪽 밖 조각 {i}: 한국어 {len(kr)}자 > 원문 {len(segs[i])}+4·한 줄 24(창 폭을 모른다)"
            )
            continue
        out[i] = kr
    return out, notes


def edits(members, *, table=None):
    """(`build` 의 `edits["script"]`, [사유…]) — `members` = `build.identity_gate` 결과. 정본이 있는 멤버만."""
    per, notes = {}, []
    for key, rows in load_all().items():
        if key not in members:
            notes.append(f"{key}: 원본에 없는 멤버")
            continue
        mem = members[key]
        segs = reinsert.member_segments(mem)
        for i, row in rows.items():
            if i >= len(segs) or stamp(segs[i]) != row["jp"]:
                raise SystemExit(
                    f"🔴 {key[1]} 조각 {i}: 원문 지문이 다르다 — 번역이 남의 자리에 붙었다"
                )
        texts, nn = page_plan(mem, rows, table=table)
        notes += [f"{key[1]} {n}" for n in nn]
        if texts:
            per.update(reinsert.edits_for(members, key, texts, table=table))
    return per, notes


def used_chars():
    out = set()
    for rows in load_all().values():
        for row in rows.values():
            out.update(row["kr"])
    out.update(josa_build.EXTRA_CHARS)  # 조사 훅 표지·조사 글리프
    return "".join(sorted(c for c in out if c.strip()))


def check():
    """(번역 조각 수, 멤버 수, [사유]) — 지문·조판. 원본 대본 덤프(`derived/script`)로 읽는다(원본 이미지를 안 연다)."""
    bad, n = [], 0
    derived = {}
    for p in glob.glob(os.path.join(common.OUT_DIR, "script", "*.json")):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        derived[(d["archive"], d["member"])] = [s["codes"] for s in d["segments"]]
    rows_all = load_all()
    for key, rows in rows_all.items():
        segs = derived.get(key)
        if segs is None:
            bad.append(f"{key}: 원본 덤프에 없는 멤버")
            continue
        for i, row in rows.items():
            n += 1
            if i >= len(segs) or stamp(segs[i]) != row["jp"]:
                bad.append(f"{key[1]} #{i}: 원문 지문이 다르다")
    return n, len(rows_all), bad


def import_file(path, dry=False):
    """`## <아카이브> <멤버>` 머리글 뒤 `<조각 색인> <한국어>` 줄들(첫 공백 하나로 가른다)을 정본에 넣는다. 빈 줄·`#` 주석은 무시.
    `dry` — 정본을 안 쓰고 조판 사유(3줄 초과·rigid 한 줄 초과·쪽 밖 한도)와 글리프 없는 글자만 보고한다(번역 에이전트용 `trial`)."""
    import re

    cur, rows, fixed, done = None, {}, set(), 0
    problems = 0

    def flush():
        nonlocal done
        if cur is None or not rows:
            return
        hits = find_member(*cur)
        if len(hits) != 1:
            raise SystemExit(
                f"🔴 {cur}: 멤버를 하나로 못 정했다({len(hits)}) — 부분문자열을 더 길게"
            )
        p, nm, mem = hits[0]
        if dry:
            nonlocal problems
            segs = reinsert.member_segments(mem)
            merged = dict(load_all().get((p, nm), {}))
            for i, kr in rows.items():
                if not 0 <= i < len(segs):
                    print(f"🔴 {cur[1]} 조각 {i} 가 없다(총 {len(segs)})")
                    problems += 1
                    continue
                merged[i] = {"jp": stamp(segs[i]), "kr": kr, **({"fix": 1} if i in fixed else {})}
            _out, notes = page_plan(mem, merged)
            for x in notes:
                print(f"🔴 {cur[1]} {x}")
                problems += 1
            done += len(rows)
            return
        done += put(p, nm, rows, reinsert.member_segments(mem), fixed)

    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln.strip() or ln.startswith("# "):
                continue
            if ln.startswith("## "):
                flush()
                a = ln[3:].split()
                cur, rows, fixed = (a[0], a[1]), {}, set()
                continue
            m = re.match(r"^(\d+)[ \t](.*)$", ln)
            if not m:
                raise SystemExit(f"🔴 읽을 수 없는 줄: {ln[:40]}")
            if cur is None:
                raise SystemExit("🔴 머리글(## 아카이브 멤버) 앞에 번역 줄이 있다")
            if int(m.group(1)) in rows:
                raise SystemExit(f"🔴 {cur} 조각 {m.group(1)} 가 두 번 나온다")
            txt = m.group(2)
            if txt.startswith("|"):  # `|` 로 시작하면 줄 구조를 지킨다(`fix`)
                txt = txt[1:]
                fixed.add(int(m.group(1)))
            rows[int(m.group(1))] = txt
    flush()
    if dry:
        print(f"시험 — 조각 {done} · 문제 {problems}")
        return 1 if problems else 0
    print(f"조각 {done} 개를 넣었다")
    return 0


def fill(min_count=3):
    """원문이 **글자까지 같은** 조각에 이미 번역한 문안을 퍼뜨린다 — 번역 안 된 조각에만, 같은 원문의 번역이 하나로 모일 때만.
    🔴 **전 대본에서 `min_count` 번 이상 나오는 원문만**(상자·획득 문구 · 이름창 · 말줄임표 같은 틀) — 한두 번 나오는 대사는 화자가 다르면 말투가 달라
    (「よいな。」 한 줄이 남의 장면에 퍼졌다) 퍼뜨리지 않는다. 채운 줄은 `"auto": 1` — 다시 돌리면 auto 줄을 걷고 새로 센다."""
    import collections

    import dump

    have = load_all()
    members, count = [], collections.Counter()
    for path, nm, data, off, sz in dump.script_members():
        segs = reinsert.member_segments(data[off : off + sz])
        members.append((path, nm, segs))
        count.update(tuple(c) for c in segs if c)
    kr_of = {}
    for path, nm, segs in members:
        rows = have.get((path, nm), {})
        for i, c in enumerate(segs):
            row = rows.get(i)
            if row and row.get("kr") is not None and not row.get("auto"):
                kr_of.setdefault(tuple(c), set()).add(row["kr"])
    added = dropped = 0
    for path, nm, segs in members:
        rows = {i: r for i, r in have.get((path, nm), {}).items() if not r.get("auto")}
        dropped += len(have.get((path, nm), {})) - len(rows)
        for i, c in enumerate(segs):
            if not c or i in rows or count[tuple(c)] < min_count:
                continue
            ks = kr_of.get(tuple(c))
            if ks and len(ks) == 1:
                rows[i] = {"jp": stamp(c), "kr": next(iter(ks)), "auto": 1}
                added += 1
        save(path, nm, rows)
    print(f"자동 채움 {added} 조각(앞서 채운 {dropped} 개는 걷고 다시 셌다)")
    return 0


def notes_all():
    """번역한 멤버마다 쪽 조판을 돌려 못 넣는 쪽(3줄 초과·rigid 한 줄 초과 …)과 쪽 밖 조각 한도를 모아 보여 준다."""
    import dump

    have = load_all()
    bad = n = 0
    for path, nm, data, off, sz in dump.script_members():
        rows = have.get((path, nm))
        if not rows:
            continue
        out, notes = page_plan(data[off : off + sz], rows)
        n += len(out)
        for x in notes:
            bad += 1
            print(f"{path} {nm.split(chr(92))[-1]} {x}")
    print(f"조판된 조각 {n} · 못 넣은 쪽 {bad}")
    return 1 if bad else 0


def todo(arc_part):
    """멤버별 (번역한 조각 / 전체) — 번역할 순서를 고르는 용."""
    import dump

    have = load_all()
    tot = got = 0
    for path, nm, data, off, sz in dump.script_members():
        if arc_part not in path:
            continue
        n = len(reinsert.member_segments(data[off : off + sz]))
        g = len(have.get((path, nm), {}))
        tot += n
        got += g
        if n:
            print(f"{path} {nm.split(chr(92))[-1]:<16s} {g:>4d}/{n}")
    print(f"합계 {got}/{tot}")
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "show" and len(argv) >= 4:
        common.verify_source()
        for path, nm, mem in find_member(argv[2], argv[3]):
            view(path, nm, mem, show_all="-a" in argv)
        return 0
    if cmd == "import" and len(argv) >= 3:
        common.verify_source()
        return import_file(argv[2])
    if cmd == "trial" and len(argv) >= 3:
        common.verify_source()
        return import_file(argv[2], dry=True)
    if cmd == "notes":
        common.verify_source()
        return notes_all()
    if cmd == "fill":
        common.verify_source()
        return fill()
    if cmd == "todo":
        common.verify_source()
        return todo(argv[2] if len(argv) > 2 else "")
    if cmd == "check":
        n, m, bad = check()
        print(f"대본 번역 — 조각 {n} · 멤버 {m}")
        for b in bad[:20]:
            print("  🔴", b)
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
