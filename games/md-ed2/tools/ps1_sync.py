"""PS1 ED2 와 **같은 원문 쪽(페이지)** 의 한국어를 PS1 문안으로 맞춘다(마스터 10-17 「원문 같으면 같게, 다르면 화자관계 고려」).

    python3 tools/ps1_sync.py            # 건수·사유만(쓰지 않는다) + 목록을 .local/work/inbox/md-ed2/ps1-sync-*.tsv 로
    python3 tools/ps1_sync.py --apply    # script/*.json 의 `ours` 를 고친다

· 단위 = 한 쪽(`\\f` · 원문 `05`): 원문 쪽의 정규화 문장열(`dialog.norm`)이 PS1 한 블록 안의 이어진 문장열과 같고, 우리 쪽 쪽 수가 원문과 같을 때(스트림 단위로 확인).
· 화자: 같거나 우리 쪽이 이름표 없음(NPC 무표) → 맞춘다. 같은 인물의 표기 차(`ALIAS`)도 맞춘다. 실제로 다른 인물이면 그대로 두고 목록으로 남긴다.
· 쪽 머리(화자 `<1e>…<04>`·`<09xx>`·`<01>`)·꼬리(`<00>`·`<06>`·`<07>`) 태그는 우리 것을 지키고 본문만 바꾼다. 본문 가운데 제어 태그(이름 자리·수치·줄바꿈)가 있으면 건드리지 않고 「태그 있음」으로 남긴다.
· PS1 오류 의심(조사·받침 어긋남)은 `check_josa_nouns` 로 걸러 목록으로 — 맞추지 않는다.
원문(JP)이 든 표는 커밋하지 않는다(`.local`).
"""

import collections
import json
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
HEAD = re.compile(r"^(?:<1e>.*?<04>|<09[0-9a-f]{2}>|<01>)+")
TAIL = re.compile(r"(?:<00>|<06>|<07>|<0a>)+$")
# 같은 인물의 이름표 표기 차(PS1 ↔ MD 원문) — 목록에 있으면 같은 화자로 본다
ALIAS = {
    ("めいど", "女中"),
    ("でぃな", "でぃな王妃"),
    ("老人", "\\x25\\x73"),
    ("れいしあ", "\\x25\\x73"),
}


# 아트라스↔레이시아 반말 통일(마스터 10-14, 다섯 기종 원문이 양쪽 반말) — PS1 은 해요체라 맞추면 그 판정을 되돌린다. 이 둘의 쪽은 맞추지 않고 목록으로(별도 라운드).
HOLD_SPEAKERS = {"あとらす", "れいしあ"}


PARTY = {
    "0900": "あとらす",
    "0901": "らんど",
    "0902": "ふろら",
}  # 파티 화자 태그 <09xx> → PS1 화자 열쇠(표본으로 확인)
PARTY_TAG = re.compile(r"<(09[0-9a-f]{2})>")


# 정본 충돌 — PS1 문안이 정본 이름과 다르다(「レジスタンスたち」→정본 「레지스탕스들」, PS1 은 「레지스탕스가」). 정본이 이긴다(관리자 10-18).
CANON_CONFLICT = {"087-1:0eb0#0"}


def same_speaker(md: str, ps1: str) -> bool:
    return not md or md == ps1 or (md, ps1) in ALIAS


def blocks():
    raw = dialog.ps1_raw()
    out = []
    for name, idx, sj, body, _ks, kt in raw["blocks"]:
        js = dialog.split_jp(body)
        kk = dialog.split_kr(kt) if kt else []
        if kt and len(js) == len(kk):
            out.append((name, idx, dialog.norm(sj), [dialog.norm(x) for x in js], kk))
    return out


def plan():
    bl = blocks()
    first = collections.defaultdict(list)
    for bi, b in enumerate(bl):
        for p, k in enumerate(b[3]):
            first[k].append((bi, p))
    maps = textmap.load_all()
    stat: collections.Counter = collections.Counter()
    changes: dict[tuple[int, int, str], str] = {}
    rows = []
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
            jpp = textmap.stream_to_text(st).split("\x0c")
            orp = ours.split("\f")
            if len(jpp) != len(orp):
                stat["쪽 수 불일치(스트림)"] += 1
                continue
            cur, new_pages, touched = "", [], False
            for pi, (jpg, org) in enumerate(zip(jpp, orp, strict=True)):
                sp = SPK.search(jpg)
                if sp:
                    cur = dialog.norm(sp.group(1))
                elif PARTY_TAG.match(org):
                    cur = PARTY.get(PARTY_TAG.match(org).group(1), cur)
                ks_ = [dialog.norm(x) for x in dialog.split_jp(TAG.sub("", SPK.sub("", jpg)))]
                new_pages.append(org)
                if not ks_:
                    continue
                stat["쪽"] += 1
                hit = next(
                    (
                        (bi, p)
                        for bi, p in first.get(ks_[0], [])
                        if bl[bi][3][p : p + len(ks_)] == ks_
                    ),
                    None,
                )
                if not hit:
                    stat["PS1 같은 원문 없음"] += 1
                    continue
                bi, p = hit
                kr = dialog.fix_kr(" ".join(bl[bi][4][p : p + len(ks_)]))
                head = HEAD.match(org)
                head_s = head.group(0) if head else ""
                rest = org[len(head_s) :]
                tail = TAIL.search(rest)
                tail_s = tail.group(0) if tail else ""
                body = rest[: len(rest) - len(tail_s)]
                eq = dialog.norm(TAG.sub("", body)) == dialog.norm(kr) or TAG.sub("", body).replace(
                    " ", ""
                ) == kr.replace(" ", "")
                if eq:
                    stat["이미 같음"] += 1
                    continue
                where = f"{blk:03d}-{k}:{key}#{pi}"
                row = (where, cur, bl[bi][2], TAG.sub("", body), kr, f"{bl[bi][0]}#{bl[bi][1]}")
                if where in CANON_CONFLICT:
                    stat["정본 충돌(정본 유지)"] += 1
                    rows.append(("정본충돌", *row))
                    continue
                if len(dialog.split_kr(TAG.sub("", body))) != len(ks_):
                    stat["문장 수 다름(우리 문장이 더/덜)"] += 1
                    rows.append(("문장수다름", *row))
                    continue
                if {cur, bl[bi][2]} & HOLD_SPEAKERS:
                    stat["아트라스·레이시아 반말 규칙 대기"] += 1
                    rows.append(("반말규칙", *row))
                    continue
                if TAG.search(body):
                    stat["태그 있음(본문 가운데 제어)"] += 1
                    rows.append(("태그있음", *row))
                    continue
                if not same_speaker(cur, bl[bi][2]):
                    stat["화자 다름(다른 인물)"] += 1
                    rows.append(("화자다름", *row))
                    continue
                stat["맞춤"] += 1
                rows.append(("맞춤", *row))
                new_pages[-1] = head_s + kr + tail_s
                touched = True
            if touched:
                changes[(blk, k, key)] = "\f".join(new_pages)
    return stat, changes, rows


def fit_filter(changes: dict[tuple[int, int, str], str]):
    """고친 문안이 칸에 안 들어가는 스트림(제자리 고정 칸 등)을 되돌린다 — 줄여서 맞추지 않고 우리 문안을 둔다(목록 「칸부족」)."""
    import battle
    import build
    import dict_names
    import hangul

    orig = common.rom()
    maps = textmap.load_all()
    names = dict_names.names(orig)
    smap = build.load_sysmsg(orig)
    bmap = json.loads(battle.MAP_JSON.read_text(encoding="utf-8"))
    cs = hangul.Charset(
        orig,
        build.collect_chars(maps, names, smap, bmap, battle.monsters(orig), build.load_captions())
        | set("".join(changes.values())),
    )
    kept: dict[tuple[int, int, str], str] = {}
    dropped = []
    by_mod: dict[tuple[int, int], dict[str, str]] = {}
    for (blk, k, key), new in changes.items():
        by_mod.setdefault((blk, k), {})[key] = new
    for (blk, k), upd in by_mod.items():
        m = maps[(blk, k)]
        mod = scene.parse_module(textmap.module_bytes(orig, blk, k))
        base = {}
        for key, ent in m["streams"].items():
            if ent.get("ours") and key not in upd:
                st = mod.streams.get(int(key, 16))
                if st is not None:
                    base[int(key, 16)] = build.build_stream(
                        st, ent["ours"], cs, raw_text=bool(ent.get("raw"))
                    )
        todo = dict(upd)
        while True:
            rep = dict(base)
            for key, new in todo.items():
                rep[int(key, 16)] = build.build_stream(mod.streams[int(key, 16)], new, cs)
            try:
                scene.reassemble(mod, rep)
                break
            except ValueError as e:
                mm = re.search(r"@(0x[0-9a-f]+)", str(e))
                bad = f"{int(mm.group(1), 16):04x}" if mm else None
                if bad not in todo:
                    # 어느 스트림인지 못 짚으면 이 모듈 전부 되돌린다
                    dropped += [(blk, k, x, str(e)[:60]) for x in todo]
                    todo = {}
                    break
                dropped.append((blk, k, bad, str(e)[:60]))
                del todo[bad]
        for key, new in todo.items():
            kept[(blk, k, key)] = new
    return kept, dropped


def main() -> None:
    stat, changes, rows = plan()
    if "--apply" in sys.argv:
        changes, dropped = fit_filter(changes)
        stat["칸 부족으로 우리 문안 유지"] = len(dropped)
        print("  칸부족:", [f"{b:03d}-{k}:{x}" for b, k, x, _e in dropped])
    out = common.ROOT.parents[2] / ".local" / "work" / "inbox" / "md-ed2"
    out.mkdir(parents=True, exist_ok=True)
    for kind in ("맞춤", "화자다름", "태그있음", "문장수다름", "반말규칙", "정본충돌"):
        (out / f"ps1-sync-{kind}.tsv").write_text(
            "구분\t자리\t화자(MD)\t화자(PS1)\t우리\tPS1\tPS1 출처\n"
            + "\n".join("\t".join(r) for r in rows if r[0] == kind)
            + "\n",
            encoding="utf-8",
        )
    print("  " + " · ".join(f"{k} {v}" for k, v in stat.items()))
    if "--apply" in sys.argv:
        by_mod: dict[tuple[int, int], dict] = {}
        for (blk, k, key), new in changes.items():
            by_mod.setdefault((blk, k), {})[key] = new
        for (blk, k), upd in by_mod.items():
            p = common.GAME_DIR / "script" / f"{blk:03d}-{k}.json"
            d = json.loads(p.read_text(encoding="utf-8"))
            for key, new in upd.items():
                d["streams"][key]["ours"] = new
            p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  script/*.json {len(by_mod)}개 · 스트림 {len(changes)}개를 PS1 문안으로 고쳤다")


if __name__ == "__main__":
    main()
